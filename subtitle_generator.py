import subprocess
import json
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import re
import logging

logger = logging.getLogger(__name__)

class SubtitleGenerator:
    """Генератор субтитров с использованием локального whisper.cpp или faster-whisper"""
    
    def __init__(self, model_size="base", device="cpu"):
        self.model_size = model_size
        self.device = device
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Проверяет наличие необходимых зависимостей"""
        # Проверяем ffmpeg
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("FFmpeg не найден. Установите: sudo apt install ffmpeg")
        
        # Проверяем whisper (faster-whisper или whisper.cpp)
        self.whisper_backend = None
        
        # Пробуем оригинальный whisper (самый простой в установке)
        try:
            import whisper
            self.whisper_backend = 'whisper'
            logger.info("Используется оригинальный whisper")
        except ImportError:
            pass
        
        # Пробуем faster-whisper (Python, требует компиляции av)
        if not self.whisper_backend:
            try:
                import faster_whisper
                self.whisper_backend = 'faster_whisper'
                logger.info("Используется faster-whisper")
            except ImportError:
                pass
        
        # Пробуем whisper.cpp (CLI)
        if not self.whisper_backend:
            try:
                result = subprocess.run(['whisper-cli', '-h'], capture_output=True, text=True)
                if result.returncode == 0:
                    self.whisper_backend = 'whisper_cpp'
                    logger.info("Используется whisper.cpp")
            except FileNotFoundError:
                pass
        
        if not self.whisper_backend:
            raise RuntimeError(
                "Не найден ни один из whisper бэкендов.\n"
                "Установите один из:\n"
                "  pip install faster-whisper\n"
                "  pip install openai-whisper\n"
                "  или установите whisper.cpp"
            )
    
    def extract_audio(self, video_path: str, output_path: Optional[str] = None) -> str:
        """Извлекает аудио из видео"""
        if output_path is None:
            output_path = str(Path(video_path).with_suffix('.wav'))
        
        cmd = [
            'ffmpeg', '-y', '-i', str(video_path),
            '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"Аудио извлечено: {output_path}")
        return output_path
    
    def transcribe(self, audio_path: str, language: str = 'auto') -> List[Dict]:
        """Распознает речь и возвращает сегменты с таймингом"""
        
        if self.whisper_backend == 'faster_whisper':
            return self._transcribe_faster_whisper(audio_path, language)
        elif self.whisper_backend == 'whisper_cpp':
            return self._transcribe_whisper_cpp(audio_path, language)
        elif self.whisper_backend == 'whisper':
            return self._transcribe_whisper(audio_path, language)
        else:
            raise RuntimeError("Нет доступного бэкенда для распознавания")
    
    def _transcribe_faster_whisper(self, audio_path: str, language: str) -> List[Dict]:
        """Распознавание через faster-whisper"""
        from faster_whisper import WhisperModel
        
        model = WhisperModel(self.model_size, device=self.device, compute_type="int8")
        
        segments, info = model.transcribe(
            audio_path,
            language=None if language == 'auto' else language,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        result = []
        for segment in segments:
            result.append({
                'start': segment.start,
                'end': segment.end,
                'text': segment.text.strip(),
                'words': [
                    {
                        'start': word.start,
                        'end': word.end,
                        'word': word.word.strip()
                    }
                    for word in (segment.words or [])
                ]
            })
        
        return result
    
    def _transcribe_whisper_cpp(self, audio_path: str, language: str) -> List[Dict]:
        """Распознавание через whisper.cpp"""
        output_file = tempfile.mktemp(suffix='.json')
        
        cmd = [
            'whisper-cli',
            '-m', f'ggml-{self.model_size}.bin',
            '-f', audio_path,
            '-oj',  # JSON output
            '-of', output_file.replace('.json', ''),
        ]
        
        if language != 'auto':
            cmd.extend(['-l', language])
        
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Читаем результат
        with open(output_file, 'r') as f:
            data = json.load(f)
        
        os.unlink(output_file)
        
        return [
            {
                'start': seg['offsets']['from'] / 1000.0,
                'end': seg['offsets']['to'] / 1000.0,
                'text': seg['text'].strip(),
                'words': []
            }
            for seg in data.get('transcription', [])
        ]
    
    def _transcribe_whisper(self, audio_path: str, language: str) -> List[Dict]:
        """Распознавание через оригинальный whisper"""
        import whisper
        
        model = whisper.load_model(self.model_size)
        
        result = model.transcribe(
            audio_path,
            language=None if language == 'auto' else language,
            word_timestamps=True
        )
        
        return [
            {
                'start': seg['start'],
                'end': seg['end'],
                'text': seg['text'].strip(),
                'words': [
                    {
                        'start': word['start'],
                        'end': word['end'],
                        'word': word['word'].strip()
                    }
                    for word in seg.get('words', [])
                ]
            }
            for seg in result.get('segments', [])
        ]
    
    def segments_to_srt(self, segments: List[Dict], output_path: str):
        """Конвертирует сегменты в SRT формат"""
        def format_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(segments, 1):
                f.write(f"{i}\n")
                f.write(f"{format_time(seg['start'])} --> {format_time(seg['end'])}\n")
                f.write(f"{seg['text']}\n\n")
        
        logger.info(f"SRT сохранен: {output_path}")
    
    def segments_to_ass(self, segments: List[Dict], output_path: str, 
                       style: Optional[Dict] = None):
        """Конвертирует сегменты в ASS формат с кастомными стилями"""
        
        default_style = {
            'fontname': 'Arial',
            'fontsize': '24',
            'primarycolour': '&H00FFFFFF',
            'secondarycolour': '&H000000FF',
            'outlinecolour': '&H00000000',
            'backcolour': '&H00000000',
            'bold': '1',
            'italic': '0',
            'borderstyle': '1',
            'outline': '2',
            'shadow': '1',
            'alignment': '2',  # Center bottom
            'marginv': '30'
        }
        
        if style:
            default_style.update(style)
        
        style_str = ','.join([
            default_style['fontname'],
            default_style['fontsize'],
            default_style['primarycolour'],
            default_style['secondarycolour'],
            default_style['outlinecolour'],
            default_style['backcolour'],
            default_style['bold'],
            default_style['italic'],
            '0', '0',
            default_style['borderstyle'],
            default_style['outline'],
            default_style['shadow'],
            default_style['alignment'],
            '10', '10',
            default_style['marginv']
        ])
        
        header = f"""[Script Info]
Title: Generated by ClipForge
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style_str}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        def format_ass_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            centis = int((seconds % 1) * 100)
            return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(header)
            for seg in segments:
                start = format_ass_time(seg['start'])
                end = format_ass_time(seg['end'])
                text = seg['text'].replace('\n', '\\N')
                f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
        
        logger.info(f"ASS сохранен: {output_path}")
    
    def burn_subtitles(self, video_path: str, subtitle_path: str, 
                      output_path: str, style: Optional[Dict] = None):
        """Накладывает субтитры на видео (hardcoded)"""
        
        logger.info(f"burn_subtitles: video={video_path}, subs={subtitle_path}, output={output_path}")
        
        # Определяем формат субтитров
        ext = Path(subtitle_path).suffix.lower()
        
        if ext == '.ass':
            # ASS субтитры с кастомными стилями (уже применены в _srt_to_ass)
            vf = f"subtitles={subtitle_path}"
        elif ext == '.srt':
            # SRT субтитры - конвертируем в ASS для лучшего контроля стилей
            ass_path = str(Path(subtitle_path).with_suffix('.ass'))
            self._srt_to_ass(subtitle_path, ass_path, style)
            subtitle_path = ass_path
            vf = f"subtitles={subtitle_path}"
        else:
            raise ValueError(f"Неподдерживаемый формат субтитров: {ext}")
        
        cmd = [
            'ffmpeg', '-y', '-i', str(video_path),
            '-vf', vf,
            '-c:v', 'libx264',
            '-crf', '18',
            '-preset', 'slow',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            str(output_path)
        ]
        
        logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"ffmpeg completed: returncode={result.returncode}")
        logger.info(f"Субтитры наложены: {output_path}")
    
    def _srt_to_ass(self, srt_path: str, ass_path: str, style: Optional[Dict] = None):
        """Конвертирует SRT в ASS с кастомными стилями для TikTok/Shorts"""
        
        # Читаем SRT
        segments = []
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Парсим SRT
        pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for _, start, end, text in matches:
            # Конвертируем время
            def parse_time(t):
                h, m, s = t.split(':')
                s, ms = s.split(',')
                return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
            
            segments.append({
                'start': parse_time(start),
                'end': parse_time(end),
                'text': text.strip()
            })
        
        # Создаем ASS с TikTok-стилем
        self.segments_to_ass(segments, ass_path, style)
    
    def generate_tiktok_style(self) -> Dict:
        """Возвращает стиль субтитров для TikTok/Shorts/Reels"""
        return {
            'fontname': 'Arial Black',
            'fontsize': '48',
            'primarycolour': '&H00FFFFFF',  # Белый
            'outlinecolour': '&H00000000',   # Черная обводка
            'backcolour': '&H00000000',
            'bold': '1',
            'outline': '4',
            'shadow': '2',
            'alignment': '2',  # По центру внизу
            'marginv': '100'   # Отступ снизу
        }
    
    def process_video(self, video_path: str, output_path: str,
                     language: str = 'auto', burn_in: bool = True,
                     style: Optional[Dict] = None) -> Tuple[str, str]:
        """Полный pipeline: извлечение аудио -> распознавание -> субтитры -> наложение"""
        
        video_path = Path(video_path)
        output_path = Path(output_path)
        
        logger.info(f"process_video: video={video_path}, output={output_path}, lang={language}, burn_in={burn_in}")
        
        # Создаем временную директорию
        temp_dir = Path(tempfile.mkdtemp())
        logger.info(f"Created temp dir: {temp_dir}")
        
        try:
            # 1. Извлекаем аудио
            audio_path = temp_dir / 'audio.wav'
            logger.info(f"Extracting audio to {audio_path}")
            self.extract_audio(str(video_path), str(audio_path))
            logger.info(f"Audio extracted successfully, size={audio_path.stat().st_size if audio_path.exists() else 0}")
            
            # 2. Распознаем речь
            logger.info(f"Transcribing audio with language={language}")
            segments = self.transcribe(str(audio_path), language)
            logger.info(f"Transcription complete: {len(segments)} segments found")
            
            if not segments:
                logger.warning("Речь не распознана")
                return str(video_path), None
            
            # 3. Создаем субтитры
            srt_path = temp_dir / 'subtitles.srt'
            logger.info(f"Creating SRT: {srt_path}")
            self.segments_to_srt(segments, str(srt_path))
            logger.info(f"SRT created, size={srt_path.stat().st_size if srt_path.exists() else 0}")
            
            if not burn_in:
                logger.info("burn_in=False, returning SRT path only")
                return str(srt_path), None
            
            # 4. Накладываем субтитры
            if style is None:
                style = self.generate_tiktok_style()
                logger.info(f"Using default TikTok style: {style}")
            else:
                logger.info(f"Using custom style: {style}")
            
            ass_path = temp_dir / 'subtitles.ass'
            logger.info(f"Creating ASS: {ass_path}")
            self.segments_to_ass(segments, str(ass_path), style)
            logger.info(f"ASS created, size={ass_path.stat().st_size if ass_path.exists() else 0}")
            
            logger.info(f"Burning subtitles: video={video_path}, ass={ass_path}, output={output_path}")
            self.burn_subtitles(str(video_path), str(ass_path), str(output_path), style)
            
            if output_path.exists():
                logger.info(f"Output file created: {output_path}, size={output_path.stat().st_size}")
            else:
                logger.error(f"Output file NOT created: {output_path}")
            
            return str(output_path), str(srt_path)
            
        except Exception as e:
            logger.error(f"process_video failed: {e}", exc_info=True)
            raise
        finally:
            # Очищаем временные файлы
            import shutil
            logger.info(f"Cleaning up temp dir: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def process_video_with_segments(self, video_path: str, segments: List[Dict],
                                     output_path: str, style: Optional[Dict] = None) -> str:
        """Накладывает субтитры на видео используя готовые сегменты"""
        
        if not segments:
            return video_path
        
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            srt_path = temp_dir / 'subtitles.srt'
            self.segments_to_srt(segments, str(srt_path))
            
            if style is None:
                style = self.generate_tiktok_style()
            
            ass_path = temp_dir / 'subtitles.ass'
            self.segments_to_ass(segments, str(ass_path), style)
            
            self.burn_subtitles(str(video_path), str(ass_path), str(output_path), style)
            
            return str(output_path)
            
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


# Глобальный экземпляр для удобства использования
_subtitle_generator = None

def get_subtitle_generator(model_size="base", device="cpu"):
    """Возвращает глобальный экземпляр генератора субтитров"""
    global _subtitle_generator
    if _subtitle_generator is None:
        _subtitle_generator = SubtitleGenerator(model_size, device)
    return _subtitle_generator

def generate_subtitles(video_path: str, output_srt: str, language: str = 'auto') -> List[Dict]:
    """Генерирует SRT субтитры для видео"""
    gen = get_subtitle_generator()
    
    temp_dir = Path(tempfile.mkdtemp())
    try:
        audio_path = temp_dir / 'audio.wav'
        gen.extract_audio(video_path, str(audio_path))
        segments = gen.transcribe(str(audio_path), language)
        gen.segments_to_srt(segments, output_srt)
        return segments
    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

def burn_subtitles_ffmpeg(video_path: str, srt_path: str, output_path: str,
                         style: Optional[Dict] = None) -> str:
    """Накладывает SRT субтитры на видео через FFmpeg"""
    gen = get_subtitle_generator()
    gen.burn_subtitles(video_path, srt_path, output_path, style)
    return output_path

def add_subtitles_to_clip(video_path: str, output_path: str, 
                         language: str = 'auto', style: Optional[Dict] = None) -> str:
    """Полный pipeline: генерация + наложение субтитров"""
    logger.info(f"add_subtitles_to_clip called: video={video_path}, output={output_path}, lang={language}, style={style}")
    try:
        gen = get_subtitle_generator()
        logger.info(f"Subtitle generator initialized, backend={gen.whisper_backend}")
        output, srt_path = gen.process_video(video_path, output_path, language, burn_in=True, style=style)
        logger.info(f"Subtitle processing complete: output={output}, srt={srt_path}")
        return output
    except Exception as e:
        logger.error(f"add_subtitles_to_clip failed: {e}", exc_info=True)
        raise
