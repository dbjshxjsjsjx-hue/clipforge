from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import json
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import uuid
import logging

# Импорт наших модулей
from viral_analyzer import analyze_video_viral
from ap_bypass import get_ap_filters, build_ap_command
from analytics import log_clip, log_upload, log_processing, get_stats
from title_templates import generate_metadata, generate_title, generate_description, generate_hashtags, get_template_categories
from account_manager import add_account, remove_account, get_account, set_current_account, get_all_accounts, rotate_account, get_random_account, get_account_stats, toggle_account
from playlist_processor import process_url, download_video, download_playlist, process_series, auto_clip_series, get_video_info
from scheduler import get_scheduler_status, add_scheduled_upload, remove_scheduled_upload, get_scheduled_uploads, start_scheduler, stop_scheduler

app = Flask(__name__, template_folder='templates', static_folder='static')

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('clipforge.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Установить уровень логирования для всех модулей
for handler in logging.root.handlers:
    handler.setLevel(logging.DEBUG)

logging.getLogger('werkzeug').setLevel(logging.INFO)

app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

# Директории
BASE_DIR = Path(__file__).parent
UPLOADS_DIR = BASE_DIR / 'uploads'
CLIPS_DIR = BASE_DIR / 'clips'
CONFIG_FILE = BASE_DIR / 'config.json'
QUEUE_FILE = BASE_DIR / 'queue.json'

UPLOADS_DIR.mkdir(exist_ok=True)
CLIPS_DIR.mkdir(exist_ok=True)

# Конфигурация по умолчанию
DEFAULT_CONFIG = {
    "youtube_accounts": [],
    "ap_settings": {
        "intensity": "auto",
        "enabled": True
    },
    "scheduler": {
        "enabled": False,
        "interval": 60,
        "max_per_day": 5,
        "time_priority": "auto"
    },
    "templates": {
        "default_category": "viral",
        "auto_generate": True
    }
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def load_queue():
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, 'r') as f:
            return json.load(f)
    return []

def save_queue(queue):
    with open(QUEUE_FILE, 'w') as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)

# Инициализация
if not CONFIG_FILE.exists():
    save_config(DEFAULT_CONFIG)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        config = request.json
        save_config(config)
        return jsonify({"status": "ok"})
    return jsonify(load_config())

@app.route('/api/upload', methods=['POST'])
def upload():
    if 'video' not in request.files:
        return jsonify({"error": "No video file"}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    filename = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4()}_{filename}"
    filepath = UPLOADS_DIR / unique_name
    file.save(filepath)
    
    return jsonify({
        "status": "ok",
        "filename": unique_name,
        "original_name": filename,
        "path": str(filepath)
    })

@app.route('/api/download-url', methods=['POST'])
def download_url():
    data = request.json
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({"error": "URL не указан"}), 400
    
    # Проверяем поддерживаемые платформы
    supported_platforms = [
        'youtube.com', 'youtu.be',
        'rutube.ru',
        'vkvideo.ru', 'vk.com/video',
        'twitch.tv',
        'tiktok.com'
    ]
    
    is_supported = any(platform in url for platform in supported_platforms)
    if not is_supported:
        return jsonify({"error": "Неподдерживаемая платформа. Поддерживаются: YouTube, Rutube, VK Видео, Twitch, TikTok"}), 400
    
    # Добавляем https:// если нет протокола
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        # Генерируем имя файла
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        output_name = f"url_{url_hash}.mp4"
        output_path = UPLOADS_DIR / output_name

        # Скачиваем через yt-dlp с дополнительными опциями для обхода ограничений
        import subprocess
        # Пробуем разные стратегии загрузки
        download_attempts = [
            # Попытка 1: скачать с принудительным remux в mp4 + отключение SSL (самая надежная для Windows)
            [
                'yt-dlp',
                '--remux-video', 'mp4',
                '--merge-output-format', 'mp4',
                '-f', 'best[height<=1080][ext=mp4]/best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 2: с обходом SABR через player_client=web_embedded + отключение SSL
            [
                'yt-dlp',
                '--extractor-args', 'youtube:player_client=web_embedded',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 3: с обходом SABR через player_skip=webpage,configs,js + отключение SSL
            [
                'yt-dlp',
                '--extractor-args', 'youtube:player_skip=webpage,configs,js;player_client=android',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 4: с User-Agent мобильного устройства + отключение SSL
            [
                'yt-dlp',
                '--user-agent', 'Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 5: с форматом mp4 и меньшим качеством + отключение SSL
            [
                'yt-dlp',
                '-f', 'best[ext=mp4][height<=720]/best[height<=720]/worst',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 6: с использованием iOS клиента + отключение SSL
            [
                'yt-dlp',
                '--extractor-args', 'youtube:player_client=ios',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 7: с использованием tv_embedded клиента + отключение SSL
            [
                'yt-dlp',
                '--extractor-args', 'youtube:player_client=tv_embedded',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 8: с конкурентными фрагментами + отключение SSL
            [
                'yt-dlp',
                '--concurrent-fragments', '5',
                '--extractor-args', 'youtube:player_client=web',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 9: скачать как аудио + видео отдельно + отключение SSL
            [
                'yt-dlp',
                '--merge-output-format', 'mp4',
                '-f', 'bestvideo[height<=1080]+bestaudio/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 10: скачать с YouTube Premium + отключение SSL
            [
                'yt-dlp',
                '--extractor-args', 'youtube:player_client=web;player_skip=webpage,configs,js',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 11: скачать с принудительным remux + отключение SSL
            [
                'yt-dlp',
                '--remux-video', 'mp4',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 12: скачать с --no-part + отключение SSL
            [
                'yt-dlp',
                '--no-part',
                '--remux-video', 'mp4',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 13: скачать с --hls-prefer-native + отключение SSL
            [
                'yt-dlp',
                '--hls-prefer-native',
                '--remux-video', 'mp4',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 14: скачать с --prefer-free-formats + отключение SSL
            [
                'yt-dlp',
                '--prefer-free-formats',
                '--remux-video', 'mp4',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ],
            # Попытка 15: скачать с --abort-on-unavailable-fragment + отключение SSL
            [
                'yt-dlp',
                '--abort-on-unavailable-fragment',
                '--skip-unavailable-fragments',
                '--remux-video', 'mp4',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '--no-check-certificate',
                '--legacy-server-connect',
                '--no-warnings',
                '-o', str(output_path),
                url
            ]
        ]
        
        # Проверяем наличие cookies
        cookies_path = Path.home() / '.clipforge' / 'cookies.txt'
        if cookies_path.exists():
            download_attempts.insert(0, [
                'yt-dlp',
                '--cookies', str(cookies_path),
                '--extractor-args', 'youtube:player_client=web',
                '-f', 'best[height<=1080]/best',
                '--no-playlist',
                '--no-update',
                '--socket-timeout', '60',
                '--retries', '10',
                '--fragment-retries', '10',
                '--no-check-certificates',
                '-o', str(output_path),
                url
            ])
        
        last_error = ""
        for attempt_num, attempt_args in enumerate(download_attempts, 1):
            logger.info(f"Download attempt {attempt_num}/{len(download_attempts)} for {url}")
            result = subprocess.run(
                attempt_args,
                capture_output=True, text=True, timeout=600
            )
            
            if result.returncode == 0 and output_path.exists():
                logger.info(f"Download successful on attempt {attempt_num}")
                break
            else:
                last_error = result.stderr
                logger.warning(f"Download attempt {attempt_num} failed: {last_error[:500]}")
        else:
            # Все попытки неудачны
            logger.error(f"All download attempts failed for {url}")
            return jsonify({"error": f"Ошибка загрузки: {last_error}"}), 500
        
        if not output_path.exists():
            return jsonify({"error": "Файл не был загружен"}), 500
        
        # Проверяем что файл не пустой и не поврежден
        file_size = output_path.stat().st_size
        if file_size == 0:
            output_path.unlink()
            return jsonify({"error": "Загружен пустой файл"}), 500
        
        logger.info(f"Downloaded file size: {file_size} bytes")
        
        # Проверяем что файл является валидным видео через ffprobe
        try:
            probe_result = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                '-of', 'json', str(output_path)
            ], capture_output=True, text=True, timeout=30)
            
            if probe_result.returncode != 0:
                # Файл поврежден — пробуем исправить через ffmpeg
                logger.warning(f"Downloaded file appears corrupted, attempting repair: {output_path}")
                fixed_path = output_path.with_suffix('.fixed.mp4')
                
                # Сначала пробуем просто пересобрать контейнер
                repair_result = subprocess.run([
                    'ffmpeg', '-y', '-i', str(output_path),
                    '-c', 'copy', '-movflags', '+faststart',
                    str(fixed_path)
                ], capture_output=True, text=True, timeout=120)
                
                if repair_result.returncode == 0 and fixed_path.exists() and fixed_path.stat().st_size > 0:
                    # Проверяем что исправленный файл валиден
                    fixed_probe = subprocess.run([
                        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'json', str(fixed_path)
                    ], capture_output=True, text=True, timeout=30)
                    
                    if fixed_probe.returncode == 0:
                        output_path.unlink()
                        fixed_path.rename(output_path)
                        logger.info(f"File repaired successfully: {output_path}")
                    else:
                        # Простое копирование не помогло — пробуем перекодировать
                        logger.warning(f"Container repair failed, trying full re-encode: {output_path}")
                        reencoded_path = output_path.with_suffix('.reencoded.mp4')
                        reencode_result = subprocess.run([
                            'ffmpeg', '-y', '-i', str(output_path),
                            '-c:v', 'libx264', '-crf', '23', '-preset', 'fast',
                            '-c:a', 'aac', '-b:a', '128k',
                            '-movflags', '+faststart',
                            str(reencoded_path)
                        ], capture_output=True, text=True, timeout=300)
                        
                        if reencode_result.returncode == 0 and reencoded_path.exists() and reencoded_path.stat().st_size > 0:
                            reencoded_probe = subprocess.run([
                                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'json', str(reencoded_path)
                            ], capture_output=True, text=True, timeout=30)
                            
                            if reencoded_probe.returncode == 0:
                                output_path.unlink()
                                if fixed_path.exists():
                                    fixed_path.unlink()
                                reencoded_path.rename(output_path)
                                logger.info(f"File re-encoded successfully: {output_path}")
                            else:
                                output_path.unlink()
                                if fixed_path.exists():
                                    fixed_path.unlink()
                                reencoded_path.unlink()
                                return jsonify({"error": "Загруженный файл поврежден и не удалось исправить даже перекодированием. Попробуйте другой URL или используйте cookies."}), 500
                        else:
                            output_path.unlink()
                            if fixed_path.exists():
                                fixed_path.unlink()
                            if reencoded_path.exists():
                                reencoded_path.unlink()
                            return jsonify({"error": "Загруженный файл поврежден и не удалось исправить. Попробуйте другой URL или используйте cookies."}), 500
                else:
                    output_path.unlink()
                    if fixed_path.exists():
                        fixed_path.unlink()
                    return jsonify({"error": "Загруженный файл поврежден и не удалось исправить. Попробуйте другой URL или используйте cookies."}), 500
            else:
                probe_data = json.loads(probe_result.stdout)
                duration = float(probe_data.get('format', {}).get('duration', 0))
                if duration < 1:
                    output_path.unlink()
                    return jsonify({"error": f"Видео слишком короткое ({duration:.1f}с). Минимум 1 секунда."}), 400
                
                logger.info(f"Video validated: duration={duration:.1f}s, size={file_size} bytes")
        except Exception as e:
            logger.warning(f"Could not validate video file: {e}")
            # Не удалось проверить — продолжаем с предупреждением
        
        return jsonify({
            "status": "ok",
            "filename": output_name,
            "original_name": output_name,
            "path": str(output_path),
            "url": url,
            "size": file_size,
            "duration": duration if 'duration' in locals() else None
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Превышено время загрузки (10 минут). Для длинных видео попробуйте снова или используйте cookies."}), 500
    except FileNotFoundError:
        return jsonify({"error": "yt-dlp не установлен. Установите: pip install yt-dlp"}), 500
    except Exception as e:
        return jsonify({"error": f"Ошибка: {str(e)}"}), 500


@app.route('/api/download-url-info', methods=['POST'])
def download_url_info():
    """Получает информацию о видео по URL без скачивания"""
    data = request.json
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({"error": "URL не указан"}), 400
    
    try:
        import subprocess
        result = subprocess.run([
            'yt-dlp',
            '--no-update',
            '--dump-json',
            '--no-download',
            url
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            return jsonify({"error": f"Ошибка получения информации: {result.stderr}"}), 500
        
        import json
        video_info = json.loads(result.stdout)
        
        return jsonify({
            "status": "ok",
            "title": video_info.get('title', ''),
            "duration": video_info.get('duration', 0),
            "uploader": video_info.get('uploader', ''),
            "thumbnail": video_info.get('thumbnail', ''),
            "formats_count": len(video_info.get('formats', [])),
            "url": url
        })
        
    except Exception as e:
        return jsonify({"error": f"Ошибка: {str(e)}"}), 500


@app.route('/api/analyze', methods=['POST'])
def analyze_video():
    data = request.json
    video_path = UPLOADS_DIR / data.get('filename')
    
    if not video_path.exists():
        return jsonify({"error": "File not found"}), 404
    
    try:
        # Используем умный анализ
        segments = analyze_video_viral(str(video_path), min_duration=8, max_duration=60)
        
        # Генерируем preview-клипы для каждого сегмента (полная длительность момента)
        previews = []
        for idx, seg in enumerate(segments[:5]):  # Только топ-5 для preview
            preview_name = f"preview_{uuid.uuid4().hex[:8]}.mp4"
            preview_path = CLIPS_DIR / preview_name
            
            try:
                # Создаем preview на ПОЛНУЮ длительность момента
                preview_start = seg['start']
                preview_duration = seg['duration']
                
                logger.info(f"Creating preview for segment {idx}: start={preview_start}, duration={preview_duration}")
                
                subprocess.run([
                    'ffmpeg', '-y',
                    '-ss', str(preview_start),
                    '-i', str(video_path),
                    '-t', str(preview_duration),
                    '-vf', 'scale=480:-2',
                    '-c:v', 'libx264', '-crf', '28', '-preset', 'ultrafast',
                    '-c:a', 'aac', '-b:a', '64k',
                    '-movflags', '+faststart',
                    str(preview_path)
                ], check=True, capture_output=True, timeout=60)
                
                logger.info(f"Preview created: {preview_name}, size={preview_path.stat().st_size if preview_path.exists() else 0}")
                
                previews.append({
                    'segment_index': idx,
                    'url': f"/clips/{preview_name}",
                    'start': preview_start,
                    'duration': preview_duration
                })
            except Exception as e:
                logger.warning(f"Failed to create preview for segment {idx}: {e}")
        
        return jsonify({
            "status": "ok",
            "segments": segments,
            "previews": previews
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/create-clip', methods=['POST'])
def create_clip():
    print("DEBUG create_clip entered")
    logger.info(f"create_clip called with data: {request.json}")
    data = request.json
    video_path = UPLOADS_DIR / data.get('filename')
    start = data.get('start', 0)
    duration = data.get('duration', 15)
    config = load_config()

    if not video_path.exists():
        return jsonify({"error": "File not found"}), 404
    
    # Генерируем имя выходного файла
    output_name = f"clip_{uuid.uuid4().hex[:8]}.mp4"
    output_path = CLIPS_DIR / output_name
    
    # Получаем АП-фильтры
    ap_config = config.get('ap_settings', {})
    
    # Базовые параметры для вертикального формата (9:16) — Shorts/Reels/TikTok
    # Высокое качество: CRF 18 (почти без потерь), пресет slow (максимальное качество)
    base_cmd = [
        'ffmpeg', '-y', '-i', str(video_path),
        '-ss', str(start),
        '-t', str(duration),
        # Вертикальный формат 9:16, 1080x1920
        '-vf', 'split[original][copy];[copy]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=80,boxblur=luma_radius=50:luma_power=5[blurred];[original]scale=1080:1920:force_original_aspect_ratio=decrease[scaled];[blurred][scaled]overlay=(W-w)/2:(H-h)/2:format=auto',
        # Высокое качество видео
        '-c:v', 'libx264',
        '-crf', '18',  # Высокое качество (0-51, меньше = лучше, 18 = почти без потерь)
        '-preset', 'slow',  # Максимальное сжатие с лучшим качеством
        '-profile:v', 'high',
        '-level', '4.2',
        '-movflags', '+faststart',
        # Аудио высокого качества
        '-c:a', 'aac',
        '-b:a', '192k',  # Увеличенный битрейт аудио
        '-ar', '48000',
        # Метаданные для Shorts
        '-metadata', 'title=ClipForge Short',
        str(output_path)
    ]
    
    if ap_config.get('enabled', True):
        # Применяем АП-фильтры поверх вертикального формата
        filters = get_ap_filters(ap_config.get('intensity', 'auto'))
        
        # Объединяем вертикальный формат с АП-фильтрами
        vf_filters = 'split[original][copy];[copy]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=80,boxblur=luma_radius=50:luma_power=5[blurred];[original]scale=1080:1920:force_original_aspect_ratio=decrease[scaled];[blurred][scaled]overlay=(W-w)/2:(H-h)/2:format=auto'
        
        # Добавляем АП-фильтры если есть
        if filters.get('video_filters'):
            ap_vf = ','.join(filters['video_filters'])
            vf_filters = f'{ap_vf},{vf_filters}'
        
        cmd = [
            'ffmpeg', '-y', '-i', str(video_path),
            '-ss', str(start),
            '-t', str(duration),
            '-vf', vf_filters,
            '-c:v', 'libx264',
            '-crf', '18',
            '-preset', 'slow',
            '-profile:v', 'high',
            '-level', '4.2',
            '-movflags', '+faststart',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-ar', '48000',
        ]
        
        # Добавляем аудио фильтры если есть
        if filters.get('audio_filters'):
            af = ','.join(filters['audio_filters'])
            cmd.extend(['-af', af])
        
        cmd.extend([
            '-metadata', 'title=ClipForge Short',
            str(output_path)
        ])
    else:
        cmd = base_cmd
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Добавляем субтитры автоматически
        subtitle_error = None
        try:
            from subtitle_generator import add_subtitles_to_clip

            # Получаем стиль субтитров из конфигурации или запроса
            subtitle_style = data.get('subtitle_style', None)
            subtitle_enabled = data.get('subtitles', True)

            logger.info(f"Subtitle processing: enabled={subtitle_enabled}, style={subtitle_style}")

            if subtitle_enabled:
                subtitled_path = output_path.with_name(f"subtitled_{output_name}")
                result_path = add_subtitles_to_clip(
                    str(output_path),
                    str(subtitled_path),
                    language='auto',
                    style=subtitle_style
                )
                logger.info(f"add_subtitles_to_clip returned: {result_path}")
                # Заменяем оригинальный файл на версию с субтитрами
                if subtitled_path.exists():
                    logger.info(f"Subtitled file created: {subtitled_path}")
                    try:
                        # Попытка атомарного переименования (Windows может требовать shutil.move)
                        output_path.unlink()
                        subtitled_path.rename(output_path)
                    except Exception as rename_e:
                        logger.warning(f"Rename failed, trying shutil.move: {rename_e}")
                        import shutil
                        shutil.move(str(subtitled_path), str(output_path))
                    output_name = f"subtitled_{output_name}"
                else:
                    logger.warning(f"Subtitled file not found after generation: {subtitled_path}")
                    subtitle_error = "Файл с субтитрами не был создан (возможно речь не распознана)"
        except ImportError as e:
            logger.error(f"Subtitle module import failed: {e}", exc_info=True)
            subtitle_error = "Модуль субтитров не установлен (pip install openai-whisper)"
        except RuntimeError as e:
            logger.error(f"Subtitle runtime error: {e}", exc_info=True)
            subtitle_error = str(e)
        except Exception as e:
            logger.error(f"Subtitle generation failed: {e}", exc_info=True)
            subtitle_error = f"Ошибка генерации субтитров: {str(e)}"
        
        # Логируем создание клипа
        file_size = output_path.stat().st_size
        log_clip(
            filename=output_name,
            original_video=data.get('filename'),
            start_time=start,
            duration=duration,
            viral_score=data.get('score', 0),
            segment_type=data.get('type', 'manual'),
            ap_filters=filters if ap_config.get('enabled', True) else None,
            file_size=file_size
        )
        
        return jsonify({
            "status": "ok",
            "clip": {
                "id": output_name,
                "filename": output_name,
                "start": start,
                "duration": duration,
                "path": str(output_path),
                "created": datetime.now().isoformat()
            },
            "subtitle_error": subtitle_error
        })
    except subprocess.CalledProcessError as e:
        log_processing('create_clip', str(video_path), str(output_path), duration, False, e.stderr.decode())
        return jsonify({"error": f"FFmpeg error: {e.stderr.decode()}"}), 500

@app.route('/api/clips', methods=['GET'])
def list_clips():
    clips = []
    for f in sorted(CLIPS_DIR.glob('*.mp4')):
        stat = f.stat()
        clips.append({
            "id": f.name,
            "filename": f.name,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "url": f"/clips/{f.name}"
        })
    return jsonify({"clips": clips})

@app.route('/api/clip/<clip_id>', methods=['DELETE'])
def delete_clip(clip_id):
    clip_path = CLIPS_DIR / secure_filename(clip_id)
    if clip_path.exists():
        clip_path.unlink()
        return jsonify({"status": "ok"})
    return jsonify({"error": "Not found"}), 404

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """Serve uploaded video files with proper MIME type"""
    return send_from_directory(UPLOADS_DIR, filename, mimetype='video/mp4')

@app.route('/clips/<path:filename>')
def serve_clip(filename):
    """Serve clip video files with proper MIME type"""
    return send_from_directory(CLIPS_DIR, filename, mimetype='video/mp4')

@app.route('/api/queue', methods=['GET', 'POST'])
def queue():
    if request.method == 'POST':
        data = request.json
        queue = load_queue()
        queue.append({
            "id": str(uuid.uuid4()),
            "clip_id": data.get('clip_id'),
            "title": data.get('title', ''),
            "description": data.get('description', ''),
            "scheduled_time": data.get('scheduled_time'),
            "status": "pending",
            "created": datetime.now().isoformat()
        })
        save_queue(queue)
        return jsonify({"status": "ok"})
    
    return jsonify({"queue": load_queue()})

@app.route('/api/stats')
def stats():
    return jsonify(get_stats())

# === НОВЫЕ API ЭНДПОИНТЫ ===

@app.route('/api/templates/categories')
def template_categories():
    return jsonify({"categories": get_template_categories()})

@app.route('/api/templates/generate', methods=['POST'])
def generate_template():
    data = request.json
    category = data.get('category', 'viral')
    variables = data.get('variables', {})
    
    metadata = generate_metadata(category, variables)
    return jsonify({"status": "ok", "metadata": metadata})

@app.route('/api/accounts', methods=['GET', 'POST', 'DELETE'])
def accounts():
    if request.method == 'POST':
        data = request.json
        account_id = add_account(
            name=data.get('name'),
            client_secrets_path=data.get('client_secrets'),
            credentials_path=data.get('credentials'),
            proxy=data.get('proxy'),
            description=data.get('description', '')
        )
        return jsonify({"status": "ok", "account_id": account_id})
    
    elif request.method == 'DELETE':
        data = request.json
        remove_account(data.get('account_id'))
        return jsonify({"status": "ok"})
    
    return jsonify(get_account_stats())

@app.route('/api/accounts/switch', methods=['POST'])
def switch_account():
    data = request.json
    account = set_current_account(data.get('account_id'))
    if account:
        return jsonify({"status": "ok", "account": account})
    return jsonify({"error": "Account not found"}), 404

@app.route('/api/accounts/rotate', methods=['POST'])
def rotate():
    account = rotate_account()
    if account:
        return jsonify({"status": "ok", "account": account})
    return jsonify({"error": "No active accounts"}), 400

@app.route('/api/playlist/parse', methods=['POST'])
def parse_playlist():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL required"}), 400
    
    result = process_url(url)
    return jsonify({"status": "ok", "info": result})

@app.route('/api/playlist/download', methods=['POST'])
def download_playlist_endpoint():
    data = request.json
    url = data.get('url')
    max_videos = data.get('max_videos')
    
    if not url:
        return jsonify({"error": "URL required"}), 400
    
    result = download_playlist(url, max_videos)
    return jsonify(result)

@app.route('/api/series/process', methods=['POST'])
def process_series_endpoint():
    data = request.json
    urls = data.get('urls', [])
    auto_numbering = data.get('auto_numbering', True)
    prefix = data.get('prefix', 'Episode')
    
    if not urls:
        return jsonify({"error": "URLs required"}), 400
    
    result = process_series(urls, auto_numbering, prefix)
    return jsonify(result)

@app.route('/api/scheduler/status')
def scheduler_status():
    return jsonify(get_scheduler_status())

@app.route('/api/scheduler/start', methods=['POST'])
def start_scheduler_endpoint():
    start_scheduler()
    return jsonify({"status": "ok"})

@app.route('/api/scheduler/stop', methods=['POST'])
def stop_scheduler_endpoint():
    stop_scheduler()
    return jsonify({"status": "ok"})

@app.route('/api/scheduler/tasks', methods=['GET', 'POST', 'DELETE'])
def scheduler_tasks():
    if request.method == 'POST':
        data = request.json
        task_id = add_scheduled_upload(
            video_path=data.get('video_path'),
            title=data.get('title'),
            description=data.get('description'),
            tags=data.get('tags', []),
            category=data.get('category', '22'),
            privacy=data.get('privacy', 'public'),
            scheduled_time=data.get('scheduled_time'),
            repeat=data.get('repeat')
        )
        return jsonify({"status": "ok", "task_id": task_id})
    
    elif request.method == 'DELETE':
        data = request.json
        remove_scheduled_upload(data.get('task_id'))
        return jsonify({"status": "ok"})
    
    return jsonify({"tasks": get_scheduled_uploads()})

@app.route('/api/video/info', methods=['POST'])
def video_info():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL required"}), 400
    
    result = get_video_info(url)
    return jsonify(result)


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Bad request"}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)