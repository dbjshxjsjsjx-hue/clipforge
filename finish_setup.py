# Create requirements.txt and startup script
import os

# Requirements for Flask backend
requirements = '''flask==3.0.0
flask-cors==4.0.0
werkzeug==3.0.1
requests==2.31.0
python-dotenv==1.0.0
'''

with open('/workspace/clipforge-web/requirements.txt', 'w') as f:
    f.write(requirements)

# Create startup script
startup = '''#!/bin/bash

echo "🎬 ClipForge Web Interface"
echo "=========================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден. Установите Python 3.8+"
    exit 1
fi

# Check if FFmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ FFmpeg не найден. Установите FFmpeg:"
    echo "   macOS: brew install ffmpeg"
    echo "   Ubuntu: sudo apt install ffmpeg"
    exit 1
fi

# Create directories
mkdir -p uploads clips

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

echo "📦 Установка зависимостей..."
source venv/bin/activate
pip install -r requirements.txt

echo "🚀 Запуск сервера..."
echo "Откройте http://localhost:5000 в браузере"
echo ""

python app.py
'''

with open('/workspace/clipforge-web/start.sh', 'w') as f:
    f.write(startup)

os.chmod('/workspace/clipforge-web/start.sh', 0o755)

# Create README
readme = '''# ClipForge Web Interface

Веб-интерфейс для автоматической нарезки клипов с АП-обходом.

## Быстрый старт

```bash
# 1. Перейдите в директорию
cd clipforge-web

# 2. Запустите
./start.sh

# 3. Откройте в браузере
http://localhost:5000
```

## Возможности

- 📤 Загрузка видео через drag & drop
- 🔍 Автоматический анализ вирусных моментов
- ✂️ Создание клипов с АП-обходом
- ⚙️ Настройка модификаций видео
- 📊 Дашборд со статистикой

## Требования

- Python 3.8+
- FFmpeg
- Современный браузер

## Структура

```
clipforge-web/
├── app.py              # Flask бэкенд
├── requirements.txt  # Python зависимости
├── start.sh           # Скрипт запуска
├── templates/
│   └── index.html     # Веб-интерфейс
├── static/
│   ├── style.css      # Стили
│   └── app.js         # JavaScript логика
├── uploads/           # Загруженные видео
└── clips/             # Созданные клипы
```
'''

with open('/workspace/clipforge-web/README.md', 'w') as f:
    f.write(readme)

print("✅ ClipForge Web создан!")
print("\n📁 Структура проекта:")

for root, dirs, files in os.walk('/workspace/clipforge-web'):
    level = root.replace('/workspace/clipforge-web', '').count(os.sep)
    indent = '  ' * level
    folder = os.path.basename(root) or 'clipforge-web'
    print(f'{indent}{folder}/')
    subindent = '  ' * (level + 1)
    for file in sorted(files):
        size = os.path.getsize(os.path.join(root, file))
        print(f'{subindent}{file} ({size} bytes)')

print(f"\n🚀 Запуск:")
print(f"   cd /workspace/clipforge-web")
print(f"   ./start.sh")
print(f"\n🌐 Откройте: http://localhost:5000")
