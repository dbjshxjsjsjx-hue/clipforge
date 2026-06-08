import json
import os
import time
import threading
import schedule
from datetime import datetime, timedelta
from pathlib import Path

class PublishScheduler:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.expanduser('~/.clipforge/scheduler.json')
        self.config_path = config_path
        self.config_dir = os.path.dirname(config_path)
        self.tasks = []
        self.running = False
        self.thread = None
        self._load_config()
    
    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.tasks = data.get('tasks', [])
            except Exception:
                self.tasks = []
        else:
            self.tasks = []
            self._save_config()
    
    def _save_config(self):
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump({'tasks': self.tasks}, f, indent=2, ensure_ascii=False)
    
    def add_task(self, video_path, title, description, tags, category, privacy, scheduled_time, repeat=None):
        task = {
            'id': f"task_{int(time.time())}_{len(self.tasks)}",
            'video_path': video_path,
            'title': title,
            'description': description,
            'tags': tags,
            'category': category,
            'privacy': privacy,
            'scheduled_time': scheduled_time,
            'repeat': repeat,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'executed_at': None
        }
        self.tasks.append(task)
        self._save_config()
        return task['id']
    
    def remove_task(self, task_id):
        self.tasks = [t for t in self.tasks if t['id'] != task_id]
        self._save_config()
    
    def get_tasks(self, status=None):
        if status:
            return [t for t in self.tasks if t['status'] == status]
        return self.tasks
    
    def _execute_task(self, task):
        from youtube_uploader import YouTubeUploader
        uploader = YouTubeUploader()
        try:
            result = uploader.upload_video(
                task['video_path'],
                task['title'],
                task['description'],
                task['tags'],
                task['category'],
                task['privacy']
            )
            task['status'] = 'completed'
            task['executed_at'] = datetime.now().isoformat()
            task['result'] = result
        except Exception as e:
            task['status'] = 'failed'
            task['error'] = str(e)
        self._save_config()
    
    def _check_tasks(self):
        now = datetime.now()
        for task in self.tasks:
            if task['status'] != 'pending':
                continue
            scheduled = datetime.fromisoformat(task['scheduled_time'])
            if scheduled <= now:
                self._execute_task(task)
                if task['repeat']:
                    next_time = scheduled + timedelta(**task['repeat'])
                    self.add_task(
                        task['video_path'],
                        task['title'],
                        task['description'],
                        task['tags'],
                        task['category'],
                        task['privacy'],
                        next_time.isoformat(),
                        task['repeat']
                    )
    
    def start(self):
        if self.running:
            return
        self.running = True
        schedule.every(1).minutes.do(self._check_tasks)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
    
    def _run(self):
        while self.running:
            schedule.run_pending()
            time.sleep(1)
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

scheduler = PublishScheduler()

def get_scheduler_status():
    return {
        'running': scheduler.running,
        'tasks_count': len(scheduler.tasks),
        'pending': len(scheduler.get_tasks('pending')),
        'completed': len(scheduler.get_tasks('completed')),
        'failed': len(scheduler.get_tasks('failed'))
    }

def add_scheduled_upload(video_path, title, description, tags, category, privacy, scheduled_time, repeat=None):
    return scheduler.add_task(video_path, title, description, tags, category, privacy, scheduled_time, repeat)

def remove_scheduled_upload(task_id):
    scheduler.remove_task(task_id)

def get_scheduled_uploads():
    return scheduler.get_tasks()

def start_scheduler():
    scheduler.start()

def stop_scheduler():
    scheduler.stop()