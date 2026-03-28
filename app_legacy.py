from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
import yt_dlp
import os
import uuid
from werkzeug.utils import secure_filename
from datetime import datetime
import logging

app = Flask(__name__)
app.secret_key = "8f2c9e4b-3c12-4f67-bf23-59a4e64d48a3"
DOWNLOAD_DIR = "downloads"
HISTORY_FILE = "download_history.txt"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Setup basic logging
logging.basicConfig(level=logging.INFO)

def save_history(url, filename, filesize_mb=None):
    filesize_str = f"{filesize_mb:.2f} MB" if filesize_mb is not None else "N/A"
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()}\t{url}\t{filename}\t{filesize_str}\n")
    logging.info(f"Saved history: {filename} ({filesize_str}) from {url}")

# ✅ Enhanced: Get all available formats (even if filesize missing)
def get_video_formats(url, cookies_path=None):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
    }

    if cookies_path:
        ydl_opts["cookiefile"] = cookies_path

    formats = []
    seen = set()

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        for f in info.get("formats", []):
            # ❌ Skip broken protocols
            if f.get("protocol") in ("mhtml", "http_dash_segments"):
                continue

            # Only video OR audio
            if f.get("vcodec") == "none" and f.get("acodec") == "none":
                continue

            # Resolution label
            if f.get("height"):
                resolution = f"{f['height']}p"
            elif f.get("acodec") != "none" and f.get("vcodec") == "none":
                resolution = "audio"
            else:
                continue

            ext = f.get("ext")

            # Real or approx filesize
            size = f.get("filesize") or f.get("filesize_approx")

            # Estimate if missing
            if not size and f.get("tbr") and info.get("duration"):
                size = f["tbr"] * info["duration"] * 1024 / 8

            if not size:
                continue  # hide zero-size junk

            size_mb = round(size / (1024 * 1024), 2)

            key = (resolution, ext, size_mb)
            if key in seen:
                continue
            seen.add(key)

            formats.append({
                "format_id": f["format_id"],
                "ext": ext,
                "resolution": resolution,
                "filesize": size_mb
            })

    return sorted(formats, key=lambda x: (x["resolution"] != "audio", x["resolution"]))

# Routes
@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/get_formats', methods=['POST'])
def get_formats():
    url = request.form.get('url')
    cookies_file = request.files.get("cookies")
    cookies_path = None
    

    if cookies_file and cookies_file.filename:
        cookies_path = os.path.join(DOWNLOAD_DIR, secure_filename(cookies_file.filename))
        cookies_file.save(cookies_path)

    try:
        formats = get_video_formats(url, cookies_path)
        if not formats:
            return jsonify({"error": "No formats found. Check if the video is private or unavailable."}), 404
        return jsonify({"formats": formats})
    except Exception as e:
        return jsonify({"error": f"Failed to get formats: {str(e)}"}), 500
    finally:
        if cookies_path and os.path.exists(cookies_path):
            os.remove(cookies_path)


@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url').splitlines()[0].strip()
    format_id = request.form.get('format_id')
    cookies_file = request.files.get("cookies")
    cookies_path = None

    if cookies_file:
        cookies_path = os.path.join(DOWNLOAD_DIR, secure_filename(cookies_file.filename))
        cookies_file.save(cookies_path)

    unique_id = str(uuid.uuid4())
    output_path = os.path.join(DOWNLOAD_DIR, f"{unique_id}.%(ext)s")
   
    ydl_opts = {
    'format': f"{format_id}+bestaudio/best",
    'merge_output_format': 'mp4',
    'postprocessors': [{
        'key': 'FFmpegVideoConvertor',
        'preferedformat': 'mp4'
    }],
    }

    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path  # ✅ correct key


    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url)
            filename = ydl.prepare_filename(info)

        final_path = filename
        save_history(url, os.path.basename(final_path))
        return send_file(final_path, as_attachment=True)

    except Exception as e:
        return f"Download failed: {str(e)}", 500
    finally:
        if cookies_path and os.path.exists(cookies_path):
            os.remove(cookies_path)


@app.route("/history")
def history():
    if not os.path.exists(HISTORY_FILE):
        return render_template("history.html", history=[])

    history_data = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 4:
                date, url, filename, filesize = parts
                history_data.append({
                    "date": date,
                    "url": url,
                    "filename": filename,
                    "filesize": filesize
                })

    return render_template("history.html", history=history_data)

@app.route('/clear_history', methods=['POST'])
def clear_history():
    try:
        with open(HISTORY_FILE, 'w', encoding="utf-8") as f:
            f.write('')
        flash("Download history cleared successfully.", "success")
        app.logger.info("Download history cleared")
    except Exception as e:
        flash(f"Failed to clear history: {str(e)}", "danger")
        app.logger.error(f"Failed to clear history: {e}")
    return redirect(url_for('history'))
@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/help")
def help_page():
    return render_template("help.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")





if __name__ == '__main__':
    app.run(debug=True)