import random
import json
import os
from pathlib import Path

class APBypass:
    def __init__(self):
        self.filters_pool = {
            'speed': [
                {'name': 'speed_up', 'filter': 'setpts=0.95*PTS', 'audio': 'atempo=1.05', 'weight': 0.3},
                {'name': 'speed_down', 'filter': 'setpts=1.05*PTS', 'audio': 'atempo=0.95', 'weight': 0.2},
                {'name': 'micro_speed', 'filter': 'setpts=0.98*PTS', 'audio': 'atempo=1.02', 'weight': 0.5},
            ],
            'zoom': [
                {'name': 'zoom_in', 'filter': 'crop=iw/1.02:ih/1.02:(iw-iw/1.02)/2:(ih-ih/1.02)/2', 'weight': 0.3},
                {'name': 'zoom_out', 'filter': 'crop=iw/0.98:ih/0.98:(iw-iw/0.98)/2:(ih-ih/0.98)/2', 'weight': 0.2},
                {'name': 'micro_zoom', 'filter': 'crop=iw/1.01:ih/1.01:(iw-iw/1.01)/2:(ih-ih/1.01)/2', 'weight': 0.5},
            ],
            'color': [
                {'name': 'warm', 'filter': 'hue=h=5:s=1.02', 'weight': 0.25},
                {'name': 'cool', 'filter': 'hue=h=-5:s=1.02', 'weight': 0.25},
                {'name': 'saturation', 'filter': 'hue=h=0:s=1.05', 'weight': 0.3},
                {'name': 'contrast', 'filter': 'eq=contrast=1.02', 'weight': 0.2},
            ],
            'transform': [
                {'name': 'hflip', 'filter': 'hflip', 'weight': 0.3},
                {'name': 'vflip', 'filter': 'vflip', 'weight': 0.1},
                {'name': 'rotate', 'filter': 'transpose=1', 'weight': 0.1},
                {'name': 'border', 'filter': 'pad=iw+20:ih+20:10:10:black', 'weight': 0.5},
            ],
            'audio': [
                {'name': 'pitch_up', 'filter': 'asetrate=44100*1.02,aresample=44100', 'weight': 0.3},
                {'name': 'pitch_down', 'filter': 'asetrate=44100*0.98,aresample=44100', 'weight': 0.2},
                {'name': 'volume', 'filter': 'volume=1.05', 'weight': 0.3},
                {'name': 'compress', 'filter': 'acompressor=threshold=-20dB:ratio=3', 'weight': 0.2},
            ],
            'noise': [
                {'name': 'grain', 'filter': 'noise=alls=5:allf=t+u', 'weight': 0.2},
                {'name': 'blur', 'filter': 'gblur=sigma=0.5', 'weight': 0.1},
                {'name': 'sharpen', 'filter': 'unsharp=3:3:0.5', 'weight': 0.3},
            ],
            'frame': [
                {'name': 'fps', 'filter': 'fps=fps=29.97', 'weight': 0.3},
                {'name': 'fps_up', 'filter': 'fps=fps=30.03', 'weight': 0.2},
                {'name': 'interlace', 'filter': 'interlace', 'weight': 0.1},
            ]
        }
        
        self.combinations = [
            {'name': 'light', 'filters': ['micro_speed', 'micro_zoom'], 'probability': 0.3},
            {'name': 'medium', 'filters': ['speed_up', 'zoom_in', 'warm'], 'probability': 0.4},
            {'name': 'heavy', 'filters': ['speed_up', 'zoom_in', 'warm', 'hflip', 'pitch_up'], 'probability': 0.2},
            {'name': 'extreme', 'filters': ['speed_up', 'zoom_in', 'warm', 'hflip', 'pitch_up', 'grain', 'border'], 'probability': 0.1},
        ]
    
    def get_random_combination(self, intensity='auto'):
        """Получает случайную комбинацию фильтров"""
        if intensity == 'auto':
            # Выбираем на основе вероятностей
            weights = [c['probability'] for c in self.combinations]
            combination = random.choices(self.combinations, weights=weights)[0]
        else:
            # Ищем по имени
            combination = next((c for c in self.combinations if c['name'] == intensity), self.combinations[1])
        
        return self._build_filters(combination['filters'])
    
    def get_unique_combination(self, used_combinations=None):
        """Генерирует уникальную комбинацию, которой не было раньше"""
        if used_combinations is None:
            used_combinations = []
        
        max_attempts = 50
        for _ in range(max_attempts):
            combo = self.get_random_combination()
            combo_key = json.dumps(combo, sort_keys=True)
            
            if combo_key not in used_combinations:
                used_combinations.append(combo_key)
                return combo
        
        # Если не удалось найти уникальную, возвращаем случайную
        return self.get_random_combination()
    
    def _build_filters(self, filter_names):
        """Строит список фильтров по их именам"""
        video_filters = []
        audio_filters = []
        
        for name in filter_names:
            for category, filters in self.filters_pool.items():
                for f in filters:
                    if f['name'] == name:
                        if 'filter' in f:
                            video_filters.append(f['filter'])
                        if 'audio' in f:
                            audio_filters.append(f['audio'])
        
        return {
            'video_filters': video_filters,
            'audio_filters': audio_filters,
            'names': filter_names
        }
    
    def build_ffmpeg_command(self, input_path, output_path, filters, start=0, duration=None):
        """Строит команду FFmpeg с комбинированными фильтрами"""
        cmd = ['ffmpeg', '-y', '-i', str(input_path)]
        
        # Добавляем видео фильтры
        vf = filters.get('video_filters', [])
        if vf:
            cmd.extend(['-vf', ','.join(vf)])
        
        # Добавляем аудио фильтры
        af = filters.get('audio_filters', [])
        if af:
            cmd.extend(['-af', ','.join(af)])
        
        # Добавляем время
        if start > 0:
            cmd.extend(['-ss', str(start)])
        if duration:
            cmd.extend(['-t', str(duration)])
        
        # Кодеки
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '128k',
            str(output_path)
        ])
        
        return cmd
    
    def get_effectiveness_report(self, test_results=None):
        """Генерирует отчет об эффективности обхода"""
        if test_results is None:
            test_results = []
        
        report = {
            'total_tests': len(test_results),
            'successful': sum(1 for r in test_results if r.get('success', False)),
            'failed': sum(1 for r in test_results if not r.get('success', False)),
            'combinations_used': {},
            'recommendations': []
        }
        
        # Анализируем какие комбинации работают лучше
        for result in test_results:
            combo = result.get('combination', 'unknown')
            if combo not in report['combinations_used']:
                report['combinations_used'][combo] = {'success': 0, 'fail': 0}
            
            if result.get('success', False):
                report['combinations_used'][combo]['success'] += 1
            else:
                report['combinations_used'][combo]['fail'] += 1
        
        # Генерируем рекомендации
        if report['successful'] / max(report['total_tests'], 1) > 0.8:
            report['recommendations'].append('Текущие настройки эффективны')
        else:
            report['recommendations'].append('Рекомендуется увеличить интенсивность модификаций')
        
        return report

# Глобальный экземпляр
ap_bypass = APBypass()

def get_ap_filters(intensity='auto'):
    return ap_bypass.get_random_combination(intensity)

def build_ap_command(input_path, output_path, filters, start=0, duration=None):
    return ap_bypass.build_ffmpeg_command(input_path, output_path, filters, start, duration)