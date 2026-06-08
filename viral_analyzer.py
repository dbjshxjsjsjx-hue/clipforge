import json
import os
import subprocess
import numpy as np
from pathlib import Path
from datetime import datetime
import tempfile
import wave
import struct

class ViralAnalyzer:
    def __init__(self):
        self.audio_cache = {}
        self.scene_cache = {}
    
    def analyze_video(self, video_path, min_duration=8, max_duration=60):
        """Комплексный анализ видео для поиска вирусных моментов"""
        segments = []
        
        # 1. Анализ аудио (пики громкости, смех)
        audio_segments = self._analyze_audio(video_path, min_duration, max_duration)
        segments.extend(audio_segments)
        
        # 2. Детекция смены сцен
        scene_segments = self._detect_scenes(video_path, min_duration, max_duration)
        segments.extend(scene_segments)
        
        # 3. Анализ диалогов (резкие изменения)
        dialog_segments = self._analyze_dialog(video_path, min_duration, max_duration)
        segments.extend(dialog_segments)
        
        # 4. ML-скоринг вирусности
        scored_segments = self._score_virality(segments, video_path)
        
        # Удаляем дубликаты и сортируем
        unique_segments = self._merge_segments(scored_segments)
        unique_segments.sort(key=lambda x: x['score'], reverse=True)
        
        return unique_segments[:20]
    
    def _analyze_audio(self, video_path, min_duration, max_duration):
        """Анализ аудио: пики громкости, смех, эмоциональные всплески"""
        segments = []
        
        try:
            # Извлекаем аудио во временный файл
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name
            
            subprocess.run([
                'ffmpeg', '-y', '-i', str(video_path),
                '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '1',
                tmp_path
            ], check=True, capture_output=True)
            
            # Читаем аудио данные
            with wave.open(tmp_path, 'rb') as wav:
                n_frames = wav.getnframes()
                sample_rate = wav.getframerate()
                duration = n_frames / sample_rate
                
                # Читаем сэмплы
                data = wav.readframes(n_frames)
                samples = struct.unpack(f'{n_frames}h', data)
                
                # Анализируем громкость по секундам
                window_size = sample_rate  # 1 секунда
                volumes = []
                
                for i in range(0, len(samples), window_size):
                    window = samples[i:i+window_size]
                    if window:
                        rms = np.sqrt(np.mean(np.array(window)**2))
                        volumes.append(rms)
                
                # Находим пики громкости
                mean_vol = np.mean(volumes)
                std_vol = np.std(volumes)
                threshold = mean_vol + 1.5 * std_vol
                
                for i, vol in enumerate(volumes):
                    if vol > threshold:
                        start = max(0, i - 2)
                        end = min(len(volumes), i + 3)
                        segment_duration = min(end - start, max_duration)
                        segment_duration = max(segment_duration, min_duration)
                        
                        segments.append({
                            'start': start,
                            'duration': segment_duration,
                            'score': min(100, int((vol / threshold) * 50)),
                            'type': 'audio_peak',
                            'reason': f'Пик громкости: {vol:.0f} vs средн. {mean_vol:.0f}'
                        })
                
                # Находим резкие изменения громкости (смех, крики)
                for i in range(1, len(volumes) - 1):
                    change = abs(volumes[i] - volumes[i-1])
                    if change > 2 * std_vol:
                        start = max(0, i - 1)
                        end = min(len(volumes), i + 4)
                        segment_duration = min(end - start, max_duration)
                        segment_duration = max(segment_duration, min_duration)
                        
                        segments.append({
                            'start': start,
                            'duration': segment_duration,
                            'score': min(100, int((change / std_vol) * 30)),
                            'type': 'audio_change',
                            'reason': f'Резкое изменение громкости'
                        })
            
            os.unlink(tmp_path)
            
        except Exception as e:
            print(f"Audio analysis error: {e}")
        
        return segments
    
    def _detect_scenes(self, video_path, min_duration, max_duration):
        """Детекция смены сцен через анализ кадров"""
        segments = []
        
        try:
            # Используем ffmpeg scene detection
            result = subprocess.run([
                'ffmpeg', '-i', str(video_path),
                '-vf', 'select=gt(scene\,0.3),showinfo',
                '-f', 'null', '-'
            ], capture_output=True, text=True)
            
            # Парсим таймстампы смены сцен
            scene_changes = []
            for line in result.stderr.split('\n'):
                if 'pts_time:' in line:
                    try:
                        time_str = line.split('pts_time:')[1].split()[0]
                        scene_changes.append(float(time_str))
                    except (IndexError, ValueError):
                        pass
            
            # Создаем сегменты вокруг смен сцен
            for i, scene_time in enumerate(scene_changes):
                if i < len(scene_changes) - 1:
                    duration = scene_changes[i+1] - scene_time
                    duration = min(duration, max_duration)
                    duration = max(duration, min_duration)
                else:
                    duration = min_duration
                
                segments.append({
                    'start': max(0, scene_time - 1),
                    'duration': duration,
                    'score': 70,
                    'type': 'scene_change',
                    'reason': 'Смена сцены'
                })
            
        except Exception as e:
            print(f"Scene detection error: {e}")
        
        return segments
    
    def _analyze_dialog(self, video_path, min_duration, max_duration):
        """Анализ диалогов: резкие изменения, паузы, эмоции"""
        segments = []
        
        try:
            # Извлекаем аудио и анализируем спектр
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name
            
            subprocess.run([
                'ffmpeg', '-y', '-i', str(video_path),
                '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                tmp_path
            ], check=True, capture_output=True)
            
            with wave.open(tmp_path, 'rb') as wav:
                n_frames = wav.getnframes()
                sample_rate = wav.getframerate()
                
                data = wav.readframes(n_frames)
                samples = struct.unpack(f'{n_frames}h', data)
                
                # Анализируем энергию голоса (частоты 85-255 Hz для мужчин, 165-335 для женщин)
                window_size = int(sample_rate * 0.5)  # 0.5 секунды
                voice_activity = []
                
                for i in range(0, len(samples), window_size):
                    window = np.array(samples[i:i+window_size])
                    if len(window) > 0:
                        # Простая энергия в диапазоне голоса
                        energy = np.sum(window**2) / len(window)
                        voice_activity.append(energy)
                
                # Находим паузы и резкие изменения
                mean_energy = np.mean(voice_activity)
                std_energy = np.std(voice_activity)
                
                for i in range(1, len(voice_activity) - 1):
                    # Резкое изменение = эмоциональный всплеск
                    change = abs(voice_activity[i] - voice_activity[i-1])
                    if change > 2 * std_energy and voice_activity[i] > mean_energy:
                        start = max(0, i * 0.5 - 1)
                        duration = min(10, max_duration)
                        
                        segments.append({
                            'start': start,
                            'duration': duration,
                            'score': min(100, int((change / std_energy) * 25)),
                            'type': 'dialog_emotion',
                            'reason': 'Эмоциональный всплеск в диалоге'
                        })
            
            os.unlink(tmp_path)
            
        except Exception as e:
            print(f"Dialog analysis error: {e}")
        
        return segments
    
    def _score_virality(self, segments, video_path):
        """ML-подобный скоринг вирусности на основе комбинации факторов"""
        if not segments:
            return segments
        
        # Получаем длительность видео
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of', 'json', str(video_path)
            ], capture_output=True, text=True, check=True)
            
            info = json.loads(result.stdout)
            total_duration = float(info['format']['duration'])
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError):
            total_duration = 0
        
        # Факторы вирусности:
        # 1. Длительность (8-30 секунд оптимально)
        # 2. Тип контента (аудио пики > сцены > диалоги)
        # 3. Позиция в видео (начало и конец лучше)
        # 4. Концентрация событий (много событий = вирусно)
        
        for seg in segments:
            score = seg.get('score', 50)
            
            # Фактор длительности
            duration = seg.get('duration', 15)
            if 8 <= duration <= 30:
                score += 15
            elif duration > 60:
                score -= 10
            
            # Фактор позиции
            start = seg.get('start', 0)
            if total_duration > 0:
                position_ratio = start / total_duration
                if position_ratio < 0.1 or position_ratio > 0.9:
                    score += 10  # Начало и конец вируснее
            
            # Фактор типа
            seg_type = seg.get('type', '')
            if 'audio_peak' in seg_type:
                score += 10
            elif 'scene_change' in seg_type:
                score += 5
            
            # Нормализация
            seg['score'] = min(100, max(0, score))
        
        return segments
    
    def _merge_segments(self, segments):
        """Удаляет дубликаты и объединяет близкие сегменты"""
        if not segments:
            return segments
        
        # Сортируем по началу
        segments.sort(key=lambda x: x['start'])
        
        merged = []
        for seg in segments:
            if not merged:
                merged.append(seg)
                continue
            
            last = merged[-1]
            # Если сегменты близко (менее 3 секунд), объединяем
            if abs(seg['start'] - last['start']) < 3:
                last['score'] = max(last['score'], seg['score'])
                last['duration'] = max(last['duration'], seg['duration'])
                last['reason'] = f"{last['reason']} + {seg['reason']}"
                if 'type' in seg and seg['type'] not in last.get('type', ''):
                    last['type'] = f"{last.get('type', '')}+{seg['type']}"
            else:
                merged.append(seg)
        
        return merged

# Глобальный экземпляр
analyzer = ViralAnalyzer()

def analyze_video_viral(video_path, min_duration=8, max_duration=60):
    return analyzer.analyze_video(video_path, min_duration, max_duration)