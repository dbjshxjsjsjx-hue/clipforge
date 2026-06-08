import json
import random
import re
from datetime import datetime
from pathlib import Path

class TitleTemplates:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path.home() / '.clipforge' / 'templates.json'
        self.config_path = config_path
        self.templates = self._load_templates()
    
    def _load_templates(self):
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return self._default_templates()
    
    def _default_templates(self):
        return {
            'gaming': {
                'titles': [
                    'Эпичный момент в {game}',
                    'Когда {action} в {game}',
                    '{game} - Лучший момент',
                    'Невероятное в {game}',
                    'Смешной момент в {game}',
                ],
                'descriptions': [
                    'Лучший момент из {game}. Подпишись для больше контента!',
                    'Эпичный момент в {game}. Ставь лайк если понравилось!',
                    'Смешной момент из {game}. Комментируй что думаешь!',
                ],
                'hashtags': ['#gaming', '#{game}', '#gamer', '#gameplay', '#clips']
            },
            'funny': {
                'titles': [
                    'Когда {subject} {action}',
                    'Смешной момент с {subject}',
                    'Это было невероятно: {subject}',
                    'Лучший прикол с {subject}',
                    'Когда {action} и {reaction}',
                ],
                'descriptions': [
                    'Смешной момент с {subject}. Подпишись!',
                    'Эпичный прикол. Ставь лайк!',
                    'Невероятный момент. Комментируй!',
                ],
                'hashtags': ['#funny', '#lol', '#meme', '#viral', '#comedy']
            },
            'reaction': {
                'titles': [
                    'Реакция на {subject}',
                    'Когда видишь {subject}',
                    'Лучшая реакция на {subject}',
                    'Невероятная реакция',
                    'Когда {action} и {reaction}',
                ],
                'descriptions': [
                    'Реакция на {subject}. Подпишись!',
                    'Лучшая реакция. Ставь лайк!',
                    'Невероятный момент. Комментируй!',
                ],
                'hashtags': ['#reaction', '#viral', '#trending', '#meme', '#funny']
            },
            'tutorial': {
                'titles': [
                    'Как {action} в {subject}',
                    'Туториал: {action}',
                    'Гайд по {subject}',
                    'Как научиться {action}',
                    'Секреты {subject}',
                ],
                'descriptions': [
                    'Туториал по {subject}. Подпишись!',
                    'Гайд как {action}. Ставь лайк!',
                    'Секреты {subject}. Комментируй!',
                ],
                'hashtags': ['#tutorial', '#guide', '#howto', '#tips', '#{subject}']
            },
            'viral': {
                'titles': [
                    'ВИРУСНО: {subject} {action}',
                    'ЭТО НЕВЕРОЯТНО: {subject}',
                    'ВЗОРВАЛ ИНТЕРНЕТ: {subject}',
                    'ТРЕНД: {subject} {action}',
                    'ВАУ: {subject} {action}',
                ],
                'descriptions': [
                    'Вирусный момент с {subject}. Подпишись!',
                    'Трендовый момент. Ставь лайк!',
                    'Невероятный момент. Комментируй!',
                ],
                'hashtags': ['#viral', '#trending', '#wow', '#amazing', '#{subject}']
            }
        }
    
    def generate_title(self, category='viral', variables=None, template_index=None):
        """Генерирует тайтл из шаблона"""
        if variables is None:
            variables = {}
        
        cat_templates = self.templates.get(category, self.templates['viral'])
        titles = cat_templates['titles']
        
        if template_index is not None and 0 <= template_index < len(titles):
            template = titles[template_index]
        else:
            template = random.choice(titles)
        
        return self._fill_template(template, variables)
    
    def generate_description(self, category='viral', variables=None, template_index=None):
        """Генерирует описание из шаблона"""
        if variables is None:
            variables = {}
        
        cat_templates = self.templates.get(category, self.templates['viral'])
        descriptions = cat_templates['descriptions']
        
        if template_index is not None and 0 <= template_index < len(descriptions):
            template = descriptions[template_index]
        else:
            template = random.choice(descriptions)
        
        return self._fill_template(template, variables)
    
    def generate_hashtags(self, category='viral', variables=None, count=5):
        """Генерирует хештеги"""
        if variables is None:
            variables = {}
        
        cat_templates = self.templates.get(category, self.templates['viral'])
        hashtags = cat_templates['hashtags']
        
        # Заполняем переменные
        filled_hashtags = [self._fill_template(h, variables) for h in hashtags]
        
        # Выбираем случайные
        if count >= len(filled_hashtags):
            return filled_hashtags
        return random.sample(filled_hashtags, count)
    
    def generate_full_metadata(self, category='viral', variables=None):
        """Генерирует полный набор метаданных"""
        if variables is None:
            variables = {}
        
        return {
            'title': self.generate_title(category, variables),
            'description': self.generate_description(category, variables),
            'tags': self.generate_hashtags(category, variables),
            'category': category
        }
    
    def _fill_template(self, template, variables):
        """Заполняет шаблон переменными"""
        result = template
        for key, value in variables.items():
            placeholder = f'{{{key}}}'
            result = result.replace(placeholder, str(value))
        
        # Удаляем незаполненные плейсхолдеры
        result = re.sub(r'\{[^}]+\}', '', result)
        result = re.sub(r'\s+', ' ', result).strip()
        
        return result
    
    def add_template(self, category, title_template, description_template, hashtags):
        """Добавляет новый шаблон"""
        if category not in self.templates:
            self.templates[category] = {'titles': [], 'descriptions': [], 'hashtags': []}
        
        self.templates[category]['titles'].append(title_template)
        self.templates[category]['descriptions'].append(description_template)
        self.templates[category]['hashtags'].extend(hashtags)
        
        self._save_templates()
    
    def _save_templates(self):
        os.makedirs(self.config_path.parent, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.templates, f, indent=2, ensure_ascii=False)
    
    def get_categories(self):
        return list(self.templates.keys())
    
    def get_templates_for_category(self, category):
        return self.templates.get(category, {})

import os

# Глобальный экземпляр
templates_manager = TitleTemplates()

def generate_metadata(category='viral', variables=None):
    return templates_manager.generate_full_metadata(category, variables)

def generate_title(category='viral', variables=None):
    return templates_manager.generate_title(category, variables)

def generate_description(category='viral', variables=None):
    return templates_manager.generate_description(category, variables)

def generate_hashtags(category='viral', variables=None, count=5):
    return templates_manager.generate_hashtags(category, variables, count)

def add_custom_template(category, title, description, hashtags):
    templates_manager.add_template(category, title, description, hashtags)

def get_template_categories():
    return templates_manager.get_categories()