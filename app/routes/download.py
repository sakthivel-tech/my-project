from flask import Blueprint, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from ..__init__ import limiter
from ..services.download_service import DownloadService
from ..models import db, DownloadHistory
from ..utils.validators import is_valid_video_url

download_bp = Blueprint('download', __name__)


@download_bp.route('/get_formats', methods=['POST'])
@login_required
@limiter.limit("5 per minute")
def get_formats():
    url = request.form.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400

    if not is_valid_video_url(url):
        return jsonify({"error": "Invalid or unsupported video URL"}), 400

    try:
        service = DownloadService()
        data = service.get_formats(url)
        return jsonify(data)
    except Exception as e:
        error_msg = str(e)
        if "sign in" in error_msg.lower() or "bot" in error_msg.lower() or "exhausted" in error_msg.lower() or "player response" in error_msg.lower():
            return jsonify({"error": "YouTube active bot blocker triggered on the cloud server. Please try again later or upload a cookies.txt file to permanently bypass this."}), 500
        elif "Private video" in error_msg or "private" in error_msg.lower():
            return jsonify({"error": "This video is private or members-only."}), 400
        elif "unavailable" in error_msg.lower():
            return jsonify({"error": "This video is unavailable outside of its designated region."}), 400
        return jsonify({"error": f"Failed to extract video formats: {error_msg}"}), 500


@download_bp.route('/download', methods=['POST'])
@login_required
@limiter.limit("2 per minute")
def download():
    url = request.form.get('url')
    format_id = request.form.get('format_id')

    if not url or not format_id:
        flash('Missing URL or Format ID', 'danger')
        return redirect(url_for('main.index'))

    if not is_valid_video_url(url):
        flash('Invalid or unsupported video URL', 'danger')
        return redirect(url_for('main.index'))

    try:
        service = DownloadService()
        generator_or_filepath, title, filesize, ext = service.stream_video(
            url, format_id)

        filesize_mb = None
        if filesize:
            try:
                filesize_mb = float(filesize) / (1024 * 1024)
            except (ValueError, TypeError):
                pass

        # Save to history
        history = DownloadHistory(
            user_id=current_user.id,
            url=url,
            title=title,
            filesize_mb=filesize_mb,
            platform='YouTube'
        )
        db.session.add(history)
        db.session.commit()

        from flask import Response
        safe_title = "".join(
            [c if c.isalnum() or c in " .-_()" else "_" for c in title])

        mime_types = {
            'mp4': 'video/mp4',
            'webm': 'video/webm',
            'mkv': 'video/x-matroska',
            'm4a': 'audio/mp4',
            'mp3': 'audio/mpeg',
            'weba': 'audio/webm',
        }
        content_type = mime_types.get(ext, 'video/mp4')

        headers = {
            'Content-Disposition': f'attachment; filename="{safe_title}.{ext}"',
            'Content-Type': content_type,
        }
        if filesize:
            headers['Content-Length'] = str(filesize)

        return Response(
            generator_or_filepath,
            headers=headers,
            mimetype=content_type
        )

    except Exception as e:
        current_app.logger.error(
            f"Download route error for user {current_user.id}: {str(e)}",
            exc_info=True)
        flash(f'Download failed: {str(e)}', 'danger')
        return redirect(url_for('main.index'))
