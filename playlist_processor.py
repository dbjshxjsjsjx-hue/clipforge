import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import tempfile

class PlaylistProcessor:
    def __init__(self):
        self.download_dir = Path.home() / '.clipforge' / 'downloads'
        self.download_dir.mkdir(parents=True, exist_ok=True)
    
    def parse_url(self, url):
        """Парсит URL и определяет тип контента"""
        parsed = urlparse(url)
        
        if 'youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc:
            return self._parse_youtube_url(url)
        elif 'twitch.tv' in parsed.netloc:
            return {'type': 'twitch', 'url': url}
        elif 'tiktok.com' in parsed.netloc:
            return {'type': 'tiktok', 'url': url}
        else:
            return {'type': 'unknown', 'url': url}
    
    def _parse_youtube_url(self, url):
        """Парсит YouTube URL"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        if 'list' in params:
            return {
                'type': 'youtube_playlist',
                'playlist_id': params['list'][0],
                'url': url
            }
        elif 'v' in params:
            return {
                'type': 'youtube_video',
                'video_id': params['v'][0],
                'url': url
            }
        elif 'youtu.be' in parsed.netloc:
            video_id = parsed.path.strip('/')
            return {
                'type': 'youtube_video',
                'video_id': video_id,
                'url': url
            }
        else:
            return {'type': 'youtube_unknown', 'url': url}
    
    def download_video(self, url, output_path=None):
        """Скачивает видео по URL"""
        if output_path is None:
            output_path = self.download_dir / f'video_{os.urandom(4).hex()}.mp4'
        
        try:
            # Используем yt-dlp для скачивания
            cmd = [
                'yt-dlp',
                '-f', 'best[height<=720]',
                '-o', str(output_path),
                '--no-playlist',
                url
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            
            return {
                'success': True,
                'path': str(output_path),
                'filename': output_path.name
            }
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'error': f'Download failed: {e.stderr.decode()}'
            }
        except FileNotFoundError:
            return {
                'success': False,
                'error': 'yt-dlp not found. Please install it.'
            }
    
    def download_playlist(self, url, max_videos=None):
        """Скачивает плейлист"""
        try:
            # Получаем список видео
            cmd = [
                'yt-dlp',
                '--flat-playlist',
                '--print', '%(id)s %(title)s',
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            videos = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split(' ', 1)
                    if len(parts) == 2:
                        video_id, title = parts
                        videos.append({
                            'id': video_id,
                            'title': title,
                            'url': f'https://youtube.com/watch?v={video_id}'
                        })
            
            if max_videos:
                videos = videos[:max_videos]
            
            # Скачиваем каждое видео
            downloaded = []
            for i, video in enumerate(videos):
                output_path = self.download_dir / f'playlist_{i:03d}_{video["id"]}.mp4'
                result = self.download_video(video['url'], output_path)
                
                if result['success']:
                    downloaded.append({
                        **video,
                        'local_path': result['path']
                    })
            
            return {
                'success': True,
                'total': len(videos),
                'downloaded': len(downloaded),
                'videos': downloaded
            }
            
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'error': f'Playlist download failed: {e.stderr}'
            }
        except FileNotFoundError:
            return {
                'success': False,
                'error': 'yt-dlp not found. Please install it.'
            }
    
    def process_series(self, urls, auto_numbering=True, prefix='Episode'):
        """Обрабатывает серию видео (сериал)"""
        results = []
        
        for i, url in enumerate(urls):
            # Скачиваем
            download_result = self.download_video(url)
            
            if not download_result['success']:
                results.append({
                    'index': i,
                    'url': url,
                    'success': False,
                    'error': download_result['error']
                })
                continue
            
            video_path = download_result['path']
            
            # Генерируем номер
            if auto_numbering:
                episode_number = i + 1
                title = f'{prefix} {episode_number:02d}'
            else:
                title = f'{prefix} {i+1}'
            
            results.append({
                'index': i,
                'url': url,
                'success': True,
                'video_path': video_path,
                'title': title,
                'episode_number': episode_number if auto_numbering else i + 1
            })
        
        return {
            'success': True,
            'total': len(urls),
            'processed': len([r for r in results if r['success']]),
            'episodes': results
        }
    
    def auto_clip_series(self, series_results, clip_duration=60, max_clips_per_episode=3):
        """Автоматически нарезает сериал на клипы"""
        from viral_analyzer import analyze_video_viral
        
        all_clips = []
        
        for episode in series_results.get('episodes', []):
            if not episode['success']:
                continue
            
            video_path = episode['video_path']
            
            # Анализируем вирусные моменты
            segments = analyze_video_viral(video_path, min_duration=8, max_duration=clip_duration)
            
            # Берем топ сегментов
            top_segments = segments[:max_clips_per_episode]
            
            for j, segment in enumerate(top_segments):
                clip_info = {
                    'episode': episode['episode_number'],
                    'episode_title': episode['title'],
                    'clip_index': j + 1,
                    'start': segment['start'],
                    'duration': segment['duration'],
                    'score': segment['score'],
                    'type': segment['type'],
                    'video_path': video_path,
                    'suggested_title': f"{episode['title']} - Clip {j+1}"
                }
                all_clips.append(clip_info)
        
        return {
            'success': True,
            'total_clips': len(all_clips),
            'clips': all_clips
        }
    
    def get_video_info(self, url):
        """Получает информацию о видео без скачивания"""
        try:
            cmd = [
                'yt-dlp',
                '--print', '%(title)s',
                '--print', '%(duration)s',
                '--print', '%(uploader)s',
                '--print', '%(view_count)s',
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')
            
            if len(lines) >= 4:
                return {
                    'success': True,
                    'title': lines[0],
                    'duration': int(lines[1]) if lines[1].isdigit() else 0,
                    'uploader': lines[2],
                    'views': int(lines[3]) if lines[3].isdigit() else 0
                }
            else:
                return {'success': False, 'error': 'Could not parse video info'}
                
        except subprocess.CalledProcessError as e:
            return {'success': False, 'error': f'Info fetch failed: {e.stderr}'}
        except FileNotFoundError:
            return {'success': False, 'error': 'yt-dlp not found'}

# Глобальный экземпляр
playlist_processor = PlaylistProcessor()

def process_url(url):
    return playlist_processor.parse_url(url)

def download_video(url, output_path=None):
    return playlist_processor.download_video(url, output_path)

def download_playlist(url, max_videos=None):
    return playlist_processor.download_playlist(url, max_videos)

def process_series(urls, auto_numbering=True, prefix='Episode'):
    return playlist_processor.process_series(urls, auto_numbering, prefix)

def auto_clip_series(series_results, clip_duration=60, max_clips_per_episode=3):
    return playlist_processor.auto_clip_series(series_results, clip_duration, max_clips_per_episode)

def get_video_info(url):
    return playlist_processor.get_video_info(url)