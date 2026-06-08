
# === ИНТЕГРАЦИЯ СУБТИТРОВ ===
from subtitle_generator import (
    generate_subtitles, 
    burn_subtitles_ffmpeg, 
    add_subtitles_to_clip,
    get_subtitle_generator
)

@app.route('/api/subtitles/generate', methods=['POST'])
def generate_subtitles_endpoint():
    """Генерирует субтитры для видео"""
    data = request.json
    filename = data.get('filename')
    language = data.get('language', 'auto')
    
    if not filename:
        return jsonify({"error": "Filename required"}), 400
    
    video_path = UPLOADS_DIR / filename
    if not video_path.exists():
        return jsonify({"error": "File not found"}), 404
    
    try:
        srt_path = CLIPS_DIR / f"{Path(filename).stem}.srt"
        segments = generate_subtitles(str(video_path), str(srt_path), language)
        
        return jsonify({
            "status": "ok",
            "srt_path": str(srt_path),
            "segments_count": len(segments),
            "segments": segments[:10]  # Первые 10 сегментов для превью
        })
    except Exception as e:
        logger.error(f"Subtitle generation error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/subtitles/burn', methods=['POST'])
def burn_subtitles_endpoint():
    """Накладывает субтитры на видео"""
    data = request.json
    filename = data.get('filename')
    srt_filename = data.get('srt_filename')
    
    if not filename:
        return jsonify({"error": "Filename required"}), 400
    
    video_path = UPLOADS_DIR / filename
    if not video_path.exists():
        return jsonify({"error": "Video file not found"}), 404
    
    # Если SRT не указан, генерируем автоматически
    if srt_filename:
        srt_path = CLIPS_DIR / srt_filename
        if not srt_path.exists():
            return jsonify({"error": "SRT file not found"}), 404
    else:
        # Автоматическая генерация
        srt_path = CLIPS_DIR / f"{Path(filename).stem}.srt"
        try:
            generate_subtitles(str(video_path), str(srt_path))
        except Exception as e:
            return jsonify({"error": f"Auto-generation failed: {e}"}), 500
    
    try:
        output_name = f"subtitled_{Path(filename).name}"
        output_path = CLIPS_DIR / output_name
        
        burn_subtitles_ffmpeg(str(video_path), str(srt_path), str(output_path))
        
        return jsonify({
            "status": "ok",
            "output_path": str(output_path),
            "filename": output_name
        })
    except Exception as e:
        logger.error(f"Subtitle burn error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/subtitles/auto', methods=['POST'])
def auto_subtitles_endpoint():
    """Полный pipeline: генерация + наложение субтитров"""
    data = request.json
    filename = data.get('filename')
    language = data.get('language', 'auto')
    
    if not filename:
        return jsonify({"error": "Filename required"}), 400
    
    video_path = UPLOADS_DIR / filename
    if not video_path.exists():
        return jsonify({"error": "File not found"}), 404
    
    try:
        output_name = f"subtitled_{uuid.uuid4().hex[:8]}_{filename}"
        output_path = CLIPS_DIR / output_name
        
        result = add_subtitles_to_clip(str(video_path), str(output_path), language)
        
        return jsonify({
            "status": "ok",
            "output_path": result,
            "filename": output_name
        })
    except Exception as e:
        logger.error(f"Auto subtitle error: {e}")
        return jsonify({"error": str(e)}), 500
