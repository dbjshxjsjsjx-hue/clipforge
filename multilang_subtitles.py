import logging
from typing import List, Dict, Optional
from pathlib import Path
import tempfile
import subprocess

logger = logging.getLogger(__name__)

class MultilangSubtitleGenerator:
    """Генератор мультиязычных субтитров с автопереводом"""
    
    def __init__(self, subtitle_generator):
        self.subtitle_generator = subtitle_generator
        self.supported_languages = {
            'en': 'English', 'ru': 'Russian', 'es': 'Spanish', 'fr': 'French',
            'de': 'German', 'it': 'Italian', 'pt': 'Portuguese', 'zh': 'Chinese',
            'ja': 'Japanese', 'ko': 'Korean', 'ar': 'Arabic', 'hi': 'Hindi'
        }
    
    def translate_segments(self, segments: List[Dict], target_language: str,
                          source_language: str = 'auto') -> List[Dict]:
        """Переводит сегменты субтитров на целевой язык"""
        try:
            import argostranslate.package
            import argostranslate.translate
            
            argostranslate.package.update_package_index()
            available_packages = argostranslate.package.get_available_packages()
            
            package_to_install = next(
                (pkg for pkg in available_packages
                 if pkg.from_code == source_language and pkg.to_code == target_language),
                None
            )
            
            if package_to_install:
                argostranslate.package.install_from_path(package_to_install.download())
            
            translated = []
            for seg in segments:
                translated_text = argostranslate.translate.translate(
                    seg['text'], source_language, target_language
                )
                translated.append({
                    **seg, 'text': translated_text, 'translated': True,
                    'source_language': source_language, 'target_language': target_language
                })
            return translated
            
        except ImportError:
            logger.warning("argostranslate not installed. Use: pip install argostranslate")
            return segments
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return segments
    
    def generate_multilang_subtitles(self, video_path: str, languages: List[str],
                                    output_dir: str, source_language: str = 'auto') -> Dict[str, str]:
        """Генерирует субтитры на нескольких языках"""
        from subtitle_generator import get_subtitle_generator
        
        gen = get_subtitle_generator()
        temp_dir = Path(tempfile.mkdtemp())
        audio_path = temp_dir / 'audio.wav'
        gen.extract_audio(video_path, str(audio_path))
        segments = gen.transcribe(str(audio_path), source_language)
        
        detected_language = source_language if source_language != 'auto' else 'en'
        results = {}
        
        for lang in languages:
            if lang == detected_language:
                srt_path = Path(output_dir) / f"subtitles_{lang}.srt"
                gen.segments_to_srt(segments, str(srt_path))
                results[lang] = str(srt_path)
            else:
                translated = self.translate_segments(segments, lang, detected_language)
                srt_path = Path(output_dir) / f"subtitles_{lang}.srt"
                gen.segments_to_srt(translated, str(srt_path))
                results[lang] = str(srt_path)
        
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        return results
    
    def create_multilang_video(self, video_path: str, languages: List[str],
                              output_path: str, source_language: str = 'auto',
                              style: Optional[Dict] = None) -> str:
        """Создает видео с субтитрами на основном языке"""
        output_dir = Path(output_path).parent
        subtitle_files = self.generate_multilang_subtitles(
            video_path, languages, str(output_dir), source_language
        )
        primary_lang = languages[0]
        primary_srt = subtitle_files[primary_lang]
        
        from subtitle_generator import burn_subtitles_ffmpeg
        burn_subtitles_ffmpeg(video_path, primary_srt, output_path, style)
        return output_path


def translate_subtitles(segments: List[Dict], target_language: str,
                       source_language: str = 'auto') -> List[Dict]:
    translator = MultilangSubtitleGenerator(None)
    return translator.translate_segments(segments, target_language, source_language)
