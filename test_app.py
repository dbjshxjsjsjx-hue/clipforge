import pytest
import json
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index(client):
    """Тест главной страницы"""
    rv = client.get('/')
    assert rv.status_code == 200

def test_config_get(client):
    """Тест получения конфигурации"""
    rv = client.get('/api/config')
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert 'youtube_accounts' in data

def test_upload_no_file(client):
    """Тест загрузки без файла"""
    rv = client.post('/api/upload')
    assert rv.status_code == 400

def test_download_url_empty(client):
    """Тест скачивания с пустым URL"""
    rv = client.post('/api/download-url', json={})
    assert rv.status_code == 400

def test_analyze_not_found(client):
    """Тест анализа несуществующего файла"""
    rv = client.post('/api/analyze', json={'filename': 'nonexistent.mp4'})
    assert rv.status_code == 404

def test_create_clip_not_found(client):
    """Тест создания клипа из несуществующего файла"""
    rv = client.post('/api/create-clip', json={'filename': 'nonexistent.mp4'})
    assert rv.status_code == 404
