import subprocess
import json
import tempfile
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class AnimatedSubtitleGenerator:
    """Генератор анимированных субтитров (word-by-word highlighting)"""
    
    def __init__(self, style: Optional[Dict] = None):
        self.style = style or self._default_style()
    
    def _default_style(self) -> Dict:
        """Стиль как в CapCut/TikTok"""
        return {
            'fontname': 'Arial Black',
            'fontsize': '48',
            'primarycolour': '&H00FFFFFF',
            'secondarycolour': '&H00808080',
            'outlinecolour': '&H00000000',
            'backcolour': '&H00000000',
            'bold': '1',
            'outline': '4',
            'shadow': '2',
            'alignment': '2',
            'marginv': '100'
        }
    
    def generate_animated_ass(self, segments: List[Dict], output_path: str):
        """Генерирует ASS с анимированными словами"""
        style = self.style
        style_str = ','.join([
            style['fontname'], style['fontsize'], style['primarycolour'],
            style['secondarycolour'], style['outlinecolour'], style['backcolour'],
            style['bold'], '0', '0', '0', '0', '100', '100', '0', '1',
            style['outline'], style['shadow'], style['alignment'], '10', '10',
            style['marginv']
        ])
        
        header = f"""[Script Info]
Title: Animated Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style_str}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        def format_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            centis = int((seconds % 1) * 100)
            return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"
        
        dialogues = []
        for segment in segments:
            words = segment.get('words', [])
            if not words:
                continue
            
            for i, word in enumerate(words):
                word_start = word['start']
                word_end = word['end']
                word_text = word['word'].strip()
                
                prev_words = [w['word'].strip() for w in words[max(0, i-3):i]]
                next_words = [w['word'].strip() for w in words[i+1:min(len(words), i+4)]]
                
                text_parts = []
                for pw in prev_words:
                    text_parts.append(f"{{\\c{style['secondarycolour']}\\alpha&H80&}}{pw}")
                text_parts.append(f"{{\\c{style['primarycolour']}\\alpha&H00&\\b1}}{word_text}")
                for nw in next_words:
                    text_parts.append(f"{{\\c{style['secondarycolour']}\\alpha&H80&}}{nw}")
                
                text = ' '.join(text_parts)
                dialogues.append(
                    f"Dialogue: 0,{format_time(word_start)},{format_time(word_end)},Default,,0,0,0,,{text}"
                )
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(header)
            f.write('\n'.join(dialogues))
        
        logger.info(f"Animated ASS saved: {output_path}")
    
    def burn_animated_subtitles(self, video_path: str, segments: List[Dict], output_path: str):
        """Накладывает анимированные субтитры на видео"""
        temp_dir = Path(tempfile.mkdtemp())
        try:
            ass_path = temp_dir / 'animated.ass'
            self.generate_animated_ass(segments, str(ass_path))
            
            cmd = [
                'ffmpeg', '-y', '-i', str(video_path),
                '-vf', f"subtitles={str(ass_path).replace(':', '\\:')}",
                '-c:v', 'libx264', '-crf', '18', '-preset', 'slow',
                '-c:a', 'copy', '-movflags', '+faststart', str(output_path)
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"Animated subtitles burned: {output_path}")
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def create_animated_clip(self, video_path: str, start: float, duration: float,
                            segments: List[Dict], output_path: str):
        """Создает клип с анимированными субтитрами"""
        temp_dir = Path(tempfile.mkdtemp())
        try:
            temp_clip = temp_dir / 'clip.mp4'
            cmd = [
                'ffmpeg', '-y', '-i', str(video_path), '-ss', str(start), '-t', str(duration),
                '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black',
                '-c:v', 'libx264', '-crf', '18', '-preset', 'slow',
                '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', str(temp_clip)
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            self.burn_animated_subtitles(str(temp_clip), segments, output_path)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


def add_animated_subtitles(video_path: str, segments: List[Dict], 
                          output_path: str, style: Optional[Dict] = None) -> str:
    generator = AnimatedSubtitleGenerator(style)
    generator.burn_animated_subtitles(video_path, segments, output_path)
    return output_path
