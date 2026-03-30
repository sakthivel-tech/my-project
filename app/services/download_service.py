import yt_dlp
import os
import sys
import logging


class DownloadService:
    def __init__(self, cookies_path=None):
        if not cookies_path:
            default_paths = [
                os.environ.get('YTDLP_COOKIES_PATH', ''),
                '/etc/secrets/cookies.txt',
                os.path.join(os.getcwd(), 'cookies', 'cookies.txt.txt'),
                os.path.join(os.getcwd(), 'cookies', 'cookies.txt'),
                os.path.join(os.getcwd(), 'cookies.txt')
            ]
            for path in default_paths:
                if os.path.exists(path):
                    cookies_path = path
                    break

        self.cookies_path = cookies_path
        self.logger = logging.getLogger(__name__)

    def get_formats(self, url):
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
            "source_address": "0.0.0.0",
            "force_ipv4": True,
            "format": "best",
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            },
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios"]
                }
            },
            "legacyserverconnect": True}

        if self.cookies_path:
            ydl_opts["cookiefile"] = self.cookies_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = []
                seen = set()

                for f in info.get("formats", []):
                    if f.get("protocol") in ("mhtml", "http_dash_segments"):
                        continue

                    if f.get("vcodec") == "none" and f.get("acodec") == "none":
                        continue

                    resolution = "audio"
                    if f.get("height"):
                        resolution = f"{f['height']}p"
                    elif f.get("acodec") == "none":
                        continue

                    ext = f.get("ext")
                    size = f.get("filesize") or f.get("filesize_approx")

                    if not size and f.get("tbr") and info.get("duration"):
                        size = f["tbr"] * info["duration"] * 1024 / 8

                    if size:
                        size_mb = round(size / (1024 * 1024), 2)
                    else:
                        size_mb = "Unknown"
                        
                    key = (resolution, ext, size_mb)

                    if key in seen:
                        continue
                    seen.add(key)

                    formats.append({
                        "format_id": f["format_id"],
                        "ext": ext,
                        "resolution": resolution,
                        "filesize": size_mb,
                        # Direct URL for streaming/redirect
                        "url": f.get("url")
                    })

                return {
                    "title": info.get("title"),
                    "thumbnail": info.get("thumbnail"),
                    "duration": info.get("duration"),
                    "formats": sorted(
                        formats,
                        key=lambda x: (
                            x["resolution"] != "audio",
                            x["resolution"]))}
        except Exception as e:
            self.logger.error(f"Error extracting formats: {str(e)}")
            raise

    def get_download_url(self, url, format_id):
        # Returns direct URL and required headers for streaming
        ydl_opts = {
            "quiet": True,
            "format": format_id,
            "noplaylist": True,
            "source_address": "0.0.0.0",
            "force_ipv4": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            },
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios"]
                }
            },
            "legacyserverconnect": True}

        if self.cookies_path:
            ydl_opts["cookiefile"] = self.cookies_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                # YouTube needs these headers to allow the stream
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                }
                if info.get('http_headers'):
                    headers.update(info['http_headers'])

                return info.get("url"), info.get(
                    "title"), info.get("filesize"), headers
        except Exception as e:
            self.logger.error(f"Error getting download URL: {str(e)}")
            raise

    def stream_video(self, url, format_id):
        """
        Streams video/audio directly to the browser (piped streaming).
        If merging is required, ffmpeg is used to pipe matroska.
        """
        import subprocess
        import requests

        ydl_opts_info = {
            'quiet': True,
            'no_playlist': True,
            "source_address": "0.0.0.0",
            "force_ipv4": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ["android", "ios"]
                }
            },
            'legacyserverconnect': True}
        if self.cookies_path:
            ydl_opts_info["cookiefile"] = self.cookies_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)

                needs_audio = False
                chosen = next((f for f in info.get('formats', [])
                              if f['format_id'] == format_id), None)
                if chosen and chosen.get(
                        'vcodec') != 'none' and chosen.get('acodec') == 'none':
                    needs_audio = True

                if needs_audio:
                    v_url = chosen['url']
                    audio = next(
                        (f for f in reversed(
                            info['formats']) if f.get('acodec') != 'none' and (
                            f.get('vcodec') == 'none' or not f.get('vcodec'))), None)
                    if not audio:
                        audio = next(
                            (f for f in info['formats'] if f.get('acodec') != 'none'), None)

                    a_url = audio['url'] if audio else v_url
                    ua = info.get(
                        'http_headers',
                        {}).get(
                        'User-Agent',
                        'Mozilla/5.0')

                    # Ensure headers from yt-dlp are converted to ffmpeg format
                    headers_list = []
                    for k, v in info.get('http_headers', {}).items():
                        headers_list.append(f"{k}: {v}")
                    headers_str = "\r\n".join(
                        headers_list) + "\r\n" if headers_list else ""

                    ffmpeg_cmd = [
                        'ffmpeg',
                        '-reconnect', '1',
                        '-reconnect_streamed', '1',
                        '-reconnect_delay_max', '5'
                    ]

                    if headers_str:
                        ffmpeg_cmd.extend(['-headers', headers_str])
                    else:
                        ffmpeg_cmd.extend(['-user_agent', ua])

                    if self.cookies_path and os.path.exists(self.cookies_path):
                        # Use cookies via ffmpeg option if possible (it's safest to read and attach, or use -cookies)
                        # We will rely on ffmpeg's cookies format if supported, but typically yt-dlp handles cookies natively via URL tokens.
                        # ffmpeg supports reading Netscape cookie format:
                        ffmpeg_cmd.extend(['-cookies', self.cookies_path])

                    ffmpeg_cmd.extend(['-i', v_url])

                    ffmpeg_cmd.extend([
                        '-reconnect', '1',
                        '-reconnect_streamed', '1',
                        '-reconnect_delay_max', '5'
                    ])

                    if headers_str:
                        ffmpeg_cmd.extend(['-headers', headers_str])
                    else:
                        ffmpeg_cmd.extend(['-user_agent', ua])

                    if self.cookies_path and os.path.exists(self.cookies_path):
                        ffmpeg_cmd.extend(['-cookies', self.cookies_path])

                    ffmpeg_cmd.extend(['-i', a_url])

                    ffmpeg_cmd.extend([
                        '-c:v', 'copy',
                        '-c:a', 'copy',
                        '-map', '0:v:0',
                        '-map', '1:a:0',
                        '-f', 'matroska',
                        'pipe:1'
                    ])

                    process = subprocess.Popen(
                        ffmpeg_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        close_fds=True)

                    def generate_ffmpeg():
                        try:
                            while True:
                                chunk = process.stdout.read(65536)
                                if not chunk:
                                    break
                                yield chunk
                        finally:
                            process.stdout.close()
                            # Clean up ffmpeg safely
                            if process.poll() is None:
                                process.kill()
                            process.wait()

                    ext = 'mkv'
                    filesize = chosen.get('filesize')
                    if not filesize and audio:
                        filesize = None
                    return generate_ffmpeg(), info.get('title'), filesize, ext

                else:
                    v_url = chosen['url']
                    headers = info.get('http_headers', {})

                    # For requests streams, ensure cookies are loaded correctly
                    # if cookie file exists
                    session = requests.Session()
                    if self.cookies_path and os.path.exists(self.cookies_path):
                        import http.cookiejar
                        cookie_jar = http.cookiejar.MozillaCookieJar(
                            self.cookies_path)
                        try:
                            cookie_jar.load(
                                ignore_discard=True, ignore_expires=True)
                            session.cookies.update(cookie_jar)
                        except Exception as e:
                            self.logger.warning(
                                f"Could not load cookies for requests: {str(e)}")

                    try:
                        r_head = session.head(
                            v_url, headers=headers, allow_redirects=True, timeout=10)
                        filesize = int(
                            r_head.headers.get(
                                'Content-Length',
                                chosen.get('filesize') or 0))
                    except BaseException:
                        filesize = chosen.get('filesize') or 0

                    def generate_requests():
                        with session.get(v_url, headers=headers, stream=True, timeout=15) as r:
                            r.raise_for_status()
                            for chunk in r.iter_content(chunk_size=65536):
                                if chunk:
                                    yield chunk

                    ext = chosen.get('ext', 'mp4') if chosen else 'mp4'
                    # Default audio container in youtube is usually webm, if
                    # it's m4a the ext is m4a.
                    if chosen and chosen.get('vcodec') == 'none':
                        if ext == 'webm':
                            ext = 'weba'  # Or keep as webm, but weba indicates audio only

                    return generate_requests(), info.get('title'), filesize, ext

        except Exception as e:
            self.logger.error(f"Streaming failed: {str(e)}")
            raise
