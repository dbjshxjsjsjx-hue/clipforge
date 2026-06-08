import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import threading

class AnalyticsManager:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.expanduser('~/.clipforge/analytics.db')
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT,
                    original_video TEXT,
                    start_time REAL,
                    duration REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    viral_score INTEGER,
                    segment_type TEXT,
                    ap_filters TEXT,
                    file_size INTEGER,
                    status TEXT DEFAULT 'created'
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clip_id INTEGER,
                    youtube_video_id TEXT,
                    title TEXT,
                    description TEXT,
                    tags TEXT,
                    privacy TEXT,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    FOREIGN KEY (clip_id) REFERENCES clips (id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS processing_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT,
                    input_file TEXT,
                    output_file TEXT,
                    duration REAL,
                    success BOOLEAN,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    clips_created INTEGER DEFAULT 0,
                    clips_uploaded INTEGER DEFAULT 0,
                    total_duration REAL DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    ap_bypass_count INTEGER DEFAULT 0
                )
            ''')
            
            conn.commit()
    
    def log_clip_creation(self, filename, original_video, start_time, duration, viral_score=0, segment_type='auto', ap_filters=None, file_size=0):
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO clips (filename, original_video, start_time, duration, viral_score, segment_type, ap_filters, file_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (filename, original_video, start_time, duration, viral_score, segment_type, json.dumps(ap_filters) if ap_filters else None, file_size))
                
                self._update_daily_stats(conn, clips_created=1, total_duration=duration, total_size=file_size)
                conn.commit()
    
    def log_upload(self, clip_id, youtube_video_id, title, description, tags, privacy, status='success'):
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO uploads (clip_id, youtube_video_id, title, description, tags, privacy, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (clip_id, youtube_video_id, title, description, json.dumps(tags) if tags else None, privacy, status))
                
                conn.execute('UPDATE clips SET status = ? WHERE id = ?', ('uploaded', clip_id))
                
                self._update_daily_stats(conn, clips_uploaded=1)
                conn.commit()
    
    def log_processing(self, operation, input_file, output_file, duration, success=True, error_message=None):
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO processing_logs (operation, input_file, output_file, duration, success, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (operation, input_file, output_file, duration, success, error_message))
                conn.commit()
    
    def _update_daily_stats(self, conn, clips_created=0, clips_uploaded=0, total_duration=0, total_size=0, ap_bypass_count=0):
        today = datetime.now().strftime('%Y-%m-%d')
        
        conn.execute('''
            INSERT INTO daily_stats (date, clips_created, clips_uploaded, total_duration, total_size, ap_bypass_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                clips_created = clips_created + ?,
                clips_uploaded = clips_uploaded + ?,
                total_duration = total_duration + ?,
                total_size = total_size + ?,
                ap_bypass_count = ap_bypass_count + ?
        ''', (today, clips_created, clips_uploaded, total_duration, total_size, ap_bypass_count,
              clips_created, clips_uploaded, total_duration, total_size, ap_bypass_count))
    
    def get_stats(self, days=30):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Общая статистика
            total_clips = conn.execute('SELECT COUNT(*) FROM clips').fetchone()[0]
            total_uploads = conn.execute('SELECT COUNT(*) FROM uploads').fetchone()[0]
            total_duration = conn.execute('SELECT COALESCE(SUM(duration), 0) FROM clips').fetchone()[0]
            total_size = conn.execute('SELECT COALESCE(SUM(file_size), 0) FROM clips').fetchone()[0]
            
            # Статистика по дням
            daily = conn.execute('''
                SELECT * FROM daily_stats 
                WHERE date >= date('now', '-{} days')
                ORDER BY date DESC
            '''.format(days)).fetchall()
            
            # Последние клипы
            recent_clips = conn.execute('''
                SELECT * FROM clips 
                ORDER BY created_at DESC 
                LIMIT 10
            ''').fetchall()
            
            # Последние загрузки
            recent_uploads = conn.execute('''
                SELECT u.*, c.filename FROM uploads u
                JOIN clips c ON u.clip_id = c.id
                ORDER BY u.uploaded_at DESC
                LIMIT 10
            ''').fetchall()
            
            # Логи обработки
            recent_logs = conn.execute('''
                SELECT * FROM processing_logs
                ORDER BY created_at DESC
                LIMIT 20
            ''').fetchall()
            
            return {
                'total_clips': total_clips,
                'total_uploads': total_uploads,
                'total_duration': total_duration,
                'total_size': total_size,
                'daily_stats': [dict(row) for row in daily],
                'recent_clips': [dict(row) for row in recent_clips],
                'recent_uploads': [dict(row) for row in recent_uploads],
                'recent_logs': [dict(row) for row in recent_logs]
            }
    
    def get_clip_stats(self, clip_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            clip = conn.execute('SELECT * FROM clips WHERE id = ?', (clip_id,)).fetchone()
            uploads = conn.execute('SELECT * FROM uploads WHERE clip_id = ?', (clip_id,)).fetchall()
            
            if clip:
                return {
                    'clip': dict(clip),
                    'uploads': [dict(row) for row in uploads]
                }
            return None

# Глобальный экземпляр
analytics = AnalyticsManager()

def log_clip(filename, original_video, start_time, duration, viral_score=0, segment_type='auto', ap_filters=None, file_size=0):
    analytics.log_clip_creation(filename, original_video, start_time, duration, viral_score, segment_type, ap_filters, file_size)

def log_upload(clip_id, youtube_video_id, title, description, tags, privacy, status='success'):
    analytics.log_upload(clip_id, youtube_video_id, title, description, tags, privacy, status)

def log_processing(operation, input_file, output_file, duration, success=True, error_message=None):
    analytics.log_processing(operation, input_file, output_file, duration, success, error_message)

def get_stats(days=30):
    return analytics.get_stats(days)

def get_clip_stats(clip_id):
    return analytics.get_clip_stats(clip_id)