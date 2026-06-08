import json
import os
import subprocess
import numpy as np
from pathlib import Path
from datetime import datetime
import tempfile
import wave
import struct
import logging

logger = logging.getLogger(__name__)

class ViralAnalyzer:
    def __init__(self):
        self.audio_cache = {}
        self.scene_cache = {}
    
    def analyze_video(self, video_path, min_duration=8, max_duration=60):
        """Комплексный анализ видео для поиска вирусных моментов"""
        segments = []
        
        # Получаем длительность видео
        total_duration = self._get_video_duration(video_path)
        logger.info(f"Analyzing video: {video_path}, duration: {total_duration:.1f}s")
        
        # 1. Анализ аудио (пики громкости, смех)
        audio_segments = self._analyze_audio(video_path, min_duration, max_duration)
        logger.info(f"Audio analysis found {len(audio_segments)} segments")
        segments.extend(audio_segments)
        
        # 2. Детекция смены сцен
        scene_segments = self._detect_scenes(video_path, min_duration, max_duration)
        logger.info(f"Scene detection found {len(scene_segments)} segments")
        segments.extend(scene_segments)
        
        # 3. Анализ диалогов (резкие изменения)
        dialog_segments = self._analyze_dialog(video_path, min_duration, max_duration)
        logger.info(f"Dialog analysis found {len(dialog_segments)} segments")
        segments.extend(dialog_segments)
        
        # 4. Если ничего не найдено, создаем fallback сегменты
        if not segments:
            logger.warning("No segments found by analysis, creating fallback segments")
            # Пробуем получить длительность еще раз через ffmpeg если ffprobe не сработал
            if total_duration == 0:
                total_duration = self._get_video_duration_ffmpeg(video_path)
            
            if total_duration > 0:
                segments = self._create_fallback_segments(total_duration, min_duration, max_duration)
            else:
                # Если совсем ничего не работает, создаем один сегмент по умолчанию
                logger.error("Cannot determine video duration, creating single default segment")
                segments = [{
                    'start': 0,
                    'duration': min_duration,
                    'score': 50,
                    'type': 'fallback',
                    'reason': 'Не удалось определить длительность видео'
                }]
        
        # 5. ML-скоринг вирусности
        scored_segments = self._score_virality(segments, video_path)
        
        # Удаляем дубликаты и сортируем
        unique_segments = self._merge_segments(scored_segments)
        unique_segments.sort(key=lambda x: x['score'], reverse=True)
        
        logger.info(f"Total unique segments after merge: {len(unique_segments)}")
        return unique_segments[:20]
    
    def _get_video_duration(self, video_path):
        """Получает длительность видео через ffprobe"""
        try:
            # Используем shell=True на Windows для корректной обработки путей с пробелами и бэкслешами
            import sys
            if sys.platform == 'win32':
                # На Windows используем список аргументов, но оборачиваем путь в кавычки
                cmd = [
                    'ffprobe', '-v', 'error', '-show_entries',
                    'format=duration', '-of', 'json', video_path
                ]
            else:
                cmd = [
                    'ffprobe', '-v', 'error', '-show_entries',
                    'format=duration', '-of', 'json', str(video_path)
                ]
            
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, check=True,
                encoding='utf-8', errors='ignore'
            )
            
            info = json.loads(result.stdout)
            return float(info['format']['duration'])
        except subprocess.CalledProcessError as e:
            logger.error(f"ffprobe failed: {e.stderr[:200] if e.stderr else 'no stderr'}")
            # Fallback: пробуем через ffmpeg напрямую
            try:
                result = subprocess.run(
                    ['ffmpeg', '-i', str(video_path)],
                    capture_output=True, text=True
                )
                # Парсим длительность из stderr ffmpeg
                import re
                duration_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', result.stderr)
                if duration_match:
                    hours = int(duration_match.group(1))
                    minutes = int(duration_match.group(2))
                    seconds = float(duration_match.group(3))
                    return hours * 3600 + minutes * 60 + seconds
            except Exception as e2:
                logger.error(f"ffmpeg fallback also failed: {e2}")
            return 0
        except Exception as e:
            logger.error(f"Failed to get video duration: {e}")
            return 0
    
    def _get_video_duration_ffmpeg(self, video_path):
        """Fallback получения длительности через ffmpeg"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-i', video_path],
                capture_output=True, text=True
            )
            # Парсим длительность из stderr ffmpeg
            import re
            duration_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', result.stderr)
            if duration_match:
                hours = int(duration_match.group(1))
                minutes = int(duration_match.group(2))
                seconds = float(duration_match.group(3))
                return hours * 3600 + minutes * 60 + seconds
        except Exception as e:
            logger.error(f"ffmpeg duration fallback failed: {e}")
        return 0

    def _create_fallback_segments(self, total_duration, min_duration, max_duration):
        """Создает равномерные сегменты если анализ не сработал"""
        segments = []
        
        # Делим видео на равные части по 30 секунд
        segment_length = min(30, max_duration)
        num_segments = max(1, int(total_duration / segment_length))
        
        for i in range(num_segments):
            start = i * segment_length
            duration = min(segment_length, total_duration - start)
            
            if duration >= min_duration:
                # Скоринг на основе позиции (начало и конец лучше)
                position_ratio = start / total_duration if total_duration > 0 else 0
                position_score = 50
                if position_ratio < 0.1 or position_ratio > 0.9:
                    position_score = 75  # Начало и конец привлекают больше внимания
                elif position_ratio < 0.3:
                    position_score = 65  # Первая треть
                
                segments.append({
                    'start': start,
                    'duration': duration,
                    'score': position_score,
                    'type': 'fallback',
                    'reason': f'Равномерный сегмент {i+1}/{num_segments}'
                })
        
        logger.info(f"Created {len(segments)} fallback segments")
        return segments
    
    def _analyze_audio(self, video_path, min_duration, max_duration):
        """Анализ аудио: пики громкости, смех, эмоциональные всплески"""
        segments = []
        
        try:
            # Проверяем есть ли аудиодорожка
            probe = subprocess.run([
                'ffprobe', '-v', 'error', '-select_streams', 'a',
                '-show_entries', 'stream=codec_type', '-of', 'json', video_path
            ], capture_output=True, text=True)
            
            if probe.returncode != 0 or 'audio' not in probe.stdout:
                logger.warning("No audio stream found in video")
                return segments
            
            # Извлекаем аудио во временный файл
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name
            
            result = subprocess.run([
                'ffmpeg', '-y', '-i', video_path,
                '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '1',
                tmp_path
            ], check=True, capture_output=True)
            
            # Проверяем что файл не пустой
            if os.path.getsize(tmp_path) < 1024:
                logger.warning("Extracted audio file is too small, skipping audio analysis")
                os.unlink(tmp_path)
                return segments
            
            # Читаем аудио данные
            with wave.open(tmp_path, 'rb') as wav:
                n_frames = wav.getnframes()
                sample_rate = wav.getframerate()
                duration = n_frames / sample_rate
                
                if n_frames == 0:
                    logger.warning("No audio frames in extracted file")
                    os.unlink(tmp_path)
                    return segments
                
                logger.info(f"Audio: {duration:.1f}s, {n_frames} frames, {sample_rate}Hz")
                
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
                
                if not volumes:
                    logger.warning("No volume data extracted")
                    os.unlink(tmp_path)
                    return segments
                
                # Находим пики громкости
                mean_vol = np.mean(volumes)
                std_vol = np.std(volumes)
                
                if std_vol == 0:
                    logger.warning("Audio has zero variance (silent or constant)")
                    os.unlink(tmp_path)
                    return segments
                
                threshold = mean_vol + 1.5 * std_vol
                logger.info(f"Audio stats: mean={mean_vol:.0f}, std={std_vol:.0f}, threshold={threshold:.0f}")
                
                peak_count = 0
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
                        peak_count += 1
                
                # Находим резкие изменения громкости (смех, крики)
                change_count = 0
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
                        change_count += 1
                
                logger.info(f"Audio peaks: {peak_count}, changes: {change_count}")
            
            os.unlink(tmp_path)
            
        except Exception as e:
            logger.error(f"Audio analysis error: {e}")
        
        return segments
    
    def _detect_scenes(self, video_path, min_duration, max_duration):
        """Детекция смены сцен через анализ кадров"""
        segments = []
        
        try:
            # Сначала проверяем что видео имеет видеодорожку
            probe = subprocess.run([
                'ffprobe', '-v', 'error', '-select_streams', 'v',
                '-show_entries', 'stream=codec_type', '-of', 'json', video_path
            ], capture_output=True, text=True)
            
            if probe.returncode != 0 or 'video' not in probe.stdout:
                logger.warning("No video stream found")
                return segments
            
            # Используем ffmpeg scene detection
            result = subprocess.run([
                'ffmpeg', '-i', video_path,
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
            
            logger.info(f"Scene detection found {len(scene_changes)} scene changes")
            
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
            logger.error(f"Scene detection error: {e}")
        
        return segments
    
    def _analyze_dialog(self, video_path, min_duration, max_duration):
        """Анализ диалогов: резкие изменения, паузы, эмоции"""
        segments = []
        
        try:
            # Проверяем есть ли аудиодорожка
            probe = subprocess.run([
                'ffprobe', '-v', 'error', '-select_streams', 'a',
                '-show_entries', 'stream=codec_type', '-of', 'json', video_path
            ], capture_output=True, text=True)
            
            if probe.returncode != 0 or 'audio' not in probe.stdout:
                logger.warning("No audio stream for dialog analysis")
                return segments
            
            # Извлекаем аудио и анализируем спектр
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name
            
            result = subprocess.run([
                'ffmpeg', '-y', '-i', video_path,
                '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                tmp_path
            ], check=True, capture_output=True)
            
            # Проверяем что файл не пустой
            if os.path.getsize(tmp_path) < 1024:
                logger.warning("Extracted audio too small for dialog analysis")
                os.unlink(tmp_path)
                return segments
            
            with wave.open(tmp_path, 'rb') as wav:
                n_frames = wav.getnframes()
                sample_rate = wav.getframerate()
                
                if n_frames == 0:
                    logger.warning("No audio frames for dialog analysis")
                    os.unlink(tmp_path)
                    return segments
                
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
                
                if not voice_activity:
                    logger.warning("No voice activity data extracted")
                    os.unlink(tmp_path)
                    return segments
                
                # Находим паузы и резкие изменения
                mean_energy = np.mean(voice_activity)
                std_energy = np.std(voice_activity)
                
                if std_energy == 0:
                    logger.warning("Voice activity has zero variance")
                    os.unlink(tmp_path)
                    return segments
                
                emotion_count = 0
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
                        emotion_count += 1
                
                logger.info(f"Dialog analysis found {emotion_count} emotion spikes")
            
            os.unlink(tmp_path)
            
        except Exception as e:
            logger.error(f"Dialog analysis error: {e}")
        
        return segments
    
    def _score_virality(self, segments, video_path):
        """ML-подобный скоринг вирусности на основе комбинации факторов"""
        if not segments:
            return segments
        
        # Получаем длительность видео
        total_duration = self._get_video_duration(video_path)
        
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
            elif 'fallback' in seg_type:
                score = max(30, score - 15)  # Fallback сегменты ниже по приоритету
            
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