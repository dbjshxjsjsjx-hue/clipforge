// ClipForge Web Interface
class ClipForgeApp {
    constructor() {
        this.currentTab = 'dashboard';
        this.config = {};
        this.currentVideo = null;
        this.segments = [];
        this.selectedSegments = new Set();
        this.init();
    }

    async init() {
        await this.loadConfig();
        this.setupTabs();
        this.setupUpload();
        this.setupSettings();
        this.loadStats();
        this.loadClips();
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            this.config = await response.json();
            this.applyConfig();
        } catch (e) {
            console.error('Failed to load config:', e);
        }
    }

    applyConfig() {
        // Apply settings to UI
        if (this.config.ap_settings) {
            document.getElementById('ap-enabled').checked = this.config.ap_settings.enabled !== false;
            document.getElementById('auto-ap').checked = this.config.ap_settings.auto || false;
            document.getElementById('speed-mod').value = this.config.ap_settings.speed_mod || 0;
            document.getElementById('zoom').value = this.config.ap_settings.zoom || 0;
            document.getElementById('color-shift').value = this.config.ap_settings.color_shift || 0;
            document.getElementById('mirror').checked = this.config.ap_settings.mirror || false;
            document.getElementById('add-border').checked = this.config.ap_settings.add_border || false;
            document.getElementById('audio-pitch').checked = this.config.ap_settings.audio_pitch || false;
            
            // Update slider values display
            document.getElementById('speed-value').textContent = (this.config.ap_settings.speed_mod || 0) + '%';
            document.getElementById('zoom-value').textContent = (this.config.ap_settings.zoom || 0) + '%';
            document.getElementById('color-value').textContent = (this.config.ap_settings.color_shift || 0) + '%';
        }
    }

    setupTabs() {
        const tabs = document.querySelectorAll('.nav-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const tabId = tab.dataset.tab;
                this.switchTab(tabId);
            });
        });
    }

    switchTab(tabId) {
        // Update active tab
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');

        // Show content
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.getElementById(`tab-${tabId}`).classList.add('active');

        this.currentTab = tabId;

        // Load data for tab
        if (tabId === 'clips') {
            this.loadClips();
        } else if (tabId === 'dashboard') {
            this.loadStats();
        }
    }

    setupUpload() {
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('file-input');
        const urlInput = document.getElementById('url-input');
        const urlUploadBtn = document.getElementById('url-upload-btn');

        dropZone.addEventListener('click', () => fileInput.click());

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.uploadFile(files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.uploadFile(e.target.files[0]);
            }
        });

        // URL upload
        urlUploadBtn.addEventListener('click', () => {
            const url = urlInput.value.trim();
            if (url) {
                this.uploadFromUrl(url);
            }
        });

        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const url = urlInput.value.trim();
                if (url) {
                    this.uploadFromUrl(url);
                }
            }
        });
    }

    async uploadFromUrl(url) {
        this.showModal('Загрузка видео по ссылке... Это может занять несколько минут для длинных видео.');

        try {
            const response = await fetch('/api/download-url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            const result = await response.json();
            this.hideModal();

            if (result.status === 'ok') {
                this.currentVideo = result;
                document.getElementById('url-input').value = '';
                setTimeout(() => {
                    this.analyzeVideo(result.filename);
                }, 500);
            } else {
                alert('Ошибка загрузки: ' + result.error);
            }
        } catch (e) {
            this.hideModal();
            alert('Ошибка: ' + e.message);
        }
    }

    async uploadFile(file) {
        const progressBar = document.getElementById('upload-progress');
        const progressFill = document.getElementById('progress-fill');
        const progressText = document.getElementById('progress-text');

        progressBar.style.display = 'block';
        progressFill.style.width = '0%';
        progressText.textContent = '0%';

        const formData = new FormData();
        formData.append('video', file);

        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.status === 'ok') {
                progressFill.style.width = '100%';
                progressText.textContent = '100%';
                this.currentVideo = result;
                setTimeout(() => {
                    this.analyzeVideo(result.filename);
                }, 500);
            } else {
                alert('Upload failed: ' + result.error);
            }
        } catch (e) {
            alert('Upload error: ' + e.message);
        }
    }

    async analyzeVideo(filename) {
        this.showModal('Анализ видео...');

        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename })
            });

            const result = await response.json();
            this.hideModal();

            if (result.status === 'ok') {
                this.segments = result.segments;
                this.showSegments(result.segments);
            } else {
                alert('Analysis failed: ' + result.error);
            }
        } catch (e) {
            this.hideModal();
            alert('Analysis error: ' + e.message);
        }
    }

    showSegments(segments) {
        const container = document.getElementById('segments-list');
        const card = document.getElementById('analysis-card');
        const previewContainer = document.getElementById('video-preview-container');

        container.innerHTML = '';
        this.selectedSegments.clear();

        // Setup video preview
        const previewVideo = document.getElementById('preview-video');
        if (this.currentVideo) {
            previewVideo.src = `/uploads/${this.currentVideo.filename}`;
            previewContainer.style.display = 'block';
        }

        segments.forEach((segment, index) => {
            const div = document.createElement('div');
            div.className = 'segment-item';
            div.dataset.index = index;

            const scoreColor = segment.score > 80 ? '#24CFA4' : 
                              segment.score > 60 ? '#f59e0b' : '#ef4444';

            div.innerHTML = `
                <div class="segment-score" style="background: ${scoreColor}">${segment.score}</div>
                <div class="segment-info">
                    <div class="segment-title">Момент ${index + 1}</div>
                    <div class="segment-meta">${segment.start}s - ${segment.duration}s | Тип: ${segment.type}</div>
                </div>
                <button class="segment-preview-btn" data-index="${index}">▶ Просмотр</button>
            `;

            div.addEventListener('click', (e) => {
                if (e.target.classList.contains('segment-preview-btn')) {
                    e.stopPropagation();
                    this.previewSegment(index);
                    return;
                }
                div.classList.toggle('selected');
                if (div.classList.contains('selected')) {
                    this.selectedSegments.add(index);
                } else {
                    this.selectedSegments.delete(index);
                }
            });

            container.appendChild(div);
        });

        card.style.display = 'block';

        // Setup create buttons
        document.getElementById('create-all-btn').onclick = () => this.createAllClips();
        document.getElementById('create-selected-btn').onclick = () => this.createSelectedClips();
    }

    previewSegment(index) {
        const segment = this.segments[index];
        const previewVideo = document.getElementById('preview-video');
        const previewTitle = document.getElementById('preview-segment-title');
        const previewMeta = document.getElementById('preview-segment-meta');
        
        if (!previewVideo.src) {
            previewVideo.src = `/uploads/${this.currentVideo.filename}`;
        }
        
        previewVideo.currentTime = segment.start;
        previewVideo.play();
        
        // Auto-pause after segment duration
        const pauseTimeout = setTimeout(() => {
            previewVideo.pause();
        }, segment.duration * 1000);
        
        previewVideo.addEventListener('pause', () => {
            clearTimeout(pauseTimeout);
        }, { once: true });
        
        previewTitle.textContent = `Момент ${index + 1}`;
        previewMeta.textContent = `Начало: ${segment.start}с | Длительность: ${segment.duration}с | Оценка: ${segment.score} | ${segment.type}`;
        
        // Update time display
        previewVideo.addEventListener('timeupdate', () => {
            document.getElementById('preview-current').textContent = 
                this.formatTime(previewVideo.currentTime);
            document.getElementById('preview-duration').textContent = 
                this.formatTime(previewVideo.duration || 0);
        }, { once: true });
    }

    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    async createAllClips() {
        await this.createClips(this.segments.map((_, i) => i));
    }

    async createSelectedClips() {
        if (this.selectedSegments.size === 0) {
            alert('Выберите хотя бы один момент');
            return;
        }
        await this.createClips(Array.from(this.selectedSegments));
    }

    async createClips(indices) {
        this.showModal('Создание клипов...');

        for (const index of indices) {
            const segment = this.segments[index];
            document.getElementById('processing-text').textContent = 
                `Создание клипа ${index + 1} из ${indices.length}...`;

            try {
                await fetch('/api/create-clip', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        filename: this.currentVideo.filename,
                        start: segment.start,
                        duration: segment.duration,
                        score: segment.score,
                        type: segment.type
                    })
                });
            } catch (e) {
                console.error('Failed to create clip:', e);
            }
        }

        this.hideModal();
        this.loadClips();
        this.loadStats();
        alert('Клипы созданы!');
    }

    async loadClips() {
        try {
            const response = await fetch('/api/clips');
            const result = await response.json();
            this.renderClips(result.clips);
        } catch (e) {
            console.error('Failed to load clips:', e);
        }
    }

    renderClips(clips) {
        const container = document.getElementById('all-clips');
        const recentContainer = document.getElementById('recent-clips');
        const clipPlayerContainer = document.getElementById('clip-player-container');

        if (clips.length === 0) {
            const empty = `
                <div class="empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#A5A5A5" stroke-width="1.5">
                        <polygon points="23 7 16 12 23 17 23 7"/>
                        <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                    </svg>
                    <p>Пока нет клипов. Загрузите видео и создайте первый клип!</p>
                </div>
            `;
            container.innerHTML = empty;
            recentContainer.innerHTML = empty;
            if (clipPlayerContainer) clipPlayerContainer.style.display = 'none';
            return;
        }

        const clipsHtml = clips.map(clip => `
            <div class="clip-card" data-id="${clip.id}" data-url="${clip.url}">
                <div class="clip-preview" onclick="app.playClip('${clip.id}', '${clip.url}', '${clip.filename}')">${clip.duration || '15'}с ▶</div>
                <div class="clip-title">${clip.filename}</div>
                <div class="clip-meta">
                    <span>${(clip.size / 1024 / 1024).toFixed(1)} MB</span>
                    <span>${new Date(clip.created).toLocaleDateString('ru-RU')}</span>
                </div>
            </div>
        `).join('');

        container.innerHTML = clipsHtml;

        // Show recent clips in dashboard
        const recentClips = clips.slice(0, 5);
        recentContainer.innerHTML = recentClips.map(clip => `
            <div class="clip-card" data-id="${clip.id}" data-url="${clip.url}">
                <div class="clip-preview" onclick="app.playClip('${clip.id}', '${clip.url}', '${clip.filename}')">${clip.duration || '15'}с ▶</div>
                <div class="clip-title">${clip.filename}</div>
                <div class="clip-meta">
                    <span>${(clip.size / 1024 / 1024).toFixed(1)} MB</span>
                    <span>${new Date(clip.created).toLocaleDateString('ru-RU')}</span>
                </div>
            </div>
        `).join('');
    }

    playClip(id, url, filename) {
        const clipPlayerContainer = document.getElementById('clip-player-container');
        const clipPlayer = document.getElementById('clip-player');
        const clipPlayerTitle = document.getElementById('clip-player-title');
        const clipPlayerMeta = document.getElementById('clip-player-meta');
        
        if (!clipPlayerContainer || !clipPlayer) return;
        
        clipPlayer.src = url;
        clipPlayer.play();
        
        clipPlayerTitle.textContent = filename;
        clipPlayerMeta.textContent = `ID: ${id}`;
        
        clipPlayerContainer.style.display = 'block';
        
        // Scroll to player
        clipPlayerContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    async loadStats() {
        try {
            const response = await fetch('/api/stats');
            const stats = await response.json();

            document.getElementById('stat-total-clips').textContent = stats.total_clips;
            document.getElementById('stat-queue').textContent = stats.queue_size;
            document.getElementById('stat-uploads').textContent = stats.total_uploads;
            document.getElementById('stat-size').textContent = 
                (stats.clips_size / 1024 / 1024).toFixed(0) + ' MB';
        } catch (e) {
            console.error('Failed to load stats:', e);
        }
    }

    setupSettings() {
        // Sliders
        const sliders = ['speed-mod', 'zoom', 'color-shift'];
        sliders.forEach(id => {
            const slider = document.getElementById(id);
            const valueDisplay = document.getElementById(id.replace('-mod', '-value').replace('-shift', '-value'));
            
            slider.addEventListener('input', () => {
                valueDisplay.textContent = slider.value + '%';
            });
        });

        // Toggles
        const toggles = ['ap-enabled', 'mirror', 'add-border', 'audio-pitch', 'auto-ap'];
        toggles.forEach(id => {
            document.getElementById(id).addEventListener('change', () => {
                // просто логируем изменение
            });
        });

        // Save button
        document.getElementById('save-settings').addEventListener('click', () => {
            this.saveSettings();
        });
    }

    updateProtectionLevel() {
        let level = 0;
        
        if (document.getElementById('ap-enabled').checked) {
            if (document.getElementById('speed-mod').value != 0) level += 20;
            if (document.getElementById('zoom').value > 0) level += 15;
            if (document.getElementById('color-shift').value > 0) level += 15;
            if (document.getElementById('mirror').checked) level += 15;
            if (document.getElementById('add-border').checked) level += 15;
            if (document.getElementById('audio-pitch').checked) level += 20;
        }

        level = Math.min(level, 100);

        const bar = document.getElementById('protection-bar');
        const text = document.getElementById('protection-text');

        bar.style.width = level + '%';
        
        let status = 'Низкая защита';
        if (level > 50) status = 'Средняя защита';
        if (level > 80) status = 'Высокая защита';

        text.textContent = `${level}% — ${status}`;
    }

    async saveSettings() {
        const config = {
            ap_settings: {
                enabled: document.getElementById('ap-enabled').checked,
                auto: document.getElementById('auto-ap').checked,
                speed_mod: parseInt(document.getElementById('speed-mod').value),
                zoom: parseInt(document.getElementById('zoom').value),
                color_shift: parseInt(document.getElementById('color-shift').value),
                mirror: document.getElementById('mirror').checked,
                add_border: document.getElementById('add-border').checked,
                audio_pitch: document.getElementById('audio-pitch').checked
            },
            scheduler: {
                enabled: document.getElementById('scheduler-enabled').checked,
                interval: document.getElementById('scheduler-interval').value,
                max_per_day: parseInt(document.getElementById('max-per-day').value)
            }
        };

        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            alert('Настройки сохранены!');
        } catch (e) {
            alert('Ошибка сохранения: ' + e.message);
        }
    }

    showModal(text) {
        document.getElementById('processing-text').textContent = text;
        document.getElementById('processing-modal').classList.add('active');
    }

    hideModal() {
        document.getElementById('processing-modal').classList.remove('active');
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.app = new ClipForgeApp();
});
