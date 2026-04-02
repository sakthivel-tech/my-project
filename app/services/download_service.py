import yt_dlp
import os
import logging
import subprocess
import requests
import http.cookiejar
import redis
import json
import hashlib
from flask import current_app

class DownloadService:
    def __init__(self, cookies_path=None):
        if not cookies_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            default_paths = [
                os.environ.get('YTDLP_COOKIES_PATH', ''),
                '/etc/secrets/cookies.txt',
                os.path.join(base_dir, 'cookies', 'cookies.txt.txt'),
                os.path.join(base_dir, 'cookies', 'cookies.txt'),
                os.path.join(base_dir, 'cookies.txt'),
                os.path.join(os.getcwd(), 'cookies', 'cookies.txt')
            ]
            for path in default_paths:
                if path and os.path.isfile(path):
                    cookies_path = path
                    break

        self.cookies_path = cookies_path
        self.logger = logging.getLogger(__name__)
        
        # Initialize Redis for caching
        try:
            # Check for standard config or environment fallbacks
            redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
            if 'localhost' in redis_url:
                redis_url = (os.environ.get('INTERNAL_REDIS_URL') or 
                             os.environ.get('REDIS_URL') or 
                             redis_url)
            
            self.redis_client = redis.from_url(redis_url)
        except Exception as e:
            self.logger.warning(f"Redis initialization failed: {str(e)}")
            self.redis_client = None

    def _get_cache_key(self, url):
        return f"yt_formats:{hashlib.md5(url.encode()).hexdigest()}"

    def get_formats(self, url):
        """Web-server facing method to get quality formats."""
        # 1. Check Cache
        if self.redis_client:
            cached = self.redis_client.get(self._get_cache_key(url))
            if cached:
                self.logger.info(f"Cache HIT for {url}")
                return json.loads(cached)

        # 2. Trigger Celery Task and wait (Synchronous wait for async worker)
        from .tasks import extract_video_info_task
        try:
            self.logger.info(f"Triggering Celery task for {url}")
            result = extract_video_info_task.delay(url)
            data = result.get(timeout=45) # Wait up to 45 seconds
            
            # 3. Cache result
            if self.redis_client and data:
                self.redis_client.setex(
                    self._get_cache_key(url),
                    current_app.config.get('CACHE_DEFAULT_TIMEOUT', 3600),
                    json.dumps(data)
                )
            return data
        except Exception as e:
            self.logger.error(f"Celery task failed or timed out: {str(e)}")
            # Fallback to local extraction if worker fails (optional, but requested separation)
            raise e

    def _extract_info_logic(self, url):
        """The actual yt-dlp extraction logic (to be run in Worker)."""
        def _extract(opts):
            opts_copy = opts.copy()
            opts_copy.update({
                "skip_download": True,
                "noplaylist": True,
                "format": "best"
            })
            
            with yt_dlp.YoutubeDL(opts_copy) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise ValueError("No video information returned")
                    
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
                        "url": f.get("url")
                    })

                if not formats:
                    raise ValueError("Blocked: Extracted formats array is empty.")

                return {
                    "title": info.get("title"),
                    "thumbnail": info.get("thumbnail"),
                    "duration": info.get("duration"),
                    "formats": sorted(
                        formats,
                        key=lambda x: (x["resolution"] != "audio", x["resolution"])
                    )
                }

        return self._execute_with_retry("extract_info", _extract, url=url)

    def _get_ydl_opts(self, strategy_config):
        """Centralized yt-dlp options configuration."""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "ignoreerrors": True,
            "source_address": "0.0.0.0",
            "force_ipv4": True,
            "legacyserverconnect": True,
            "referer": "https://www.youtube.com/",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        if self.cookies_path:
            ydl_opts["cookiefile"] = self.cookies_path
            
        ydl_opts.update(strategy_config)
        return ydl_opts

    def _execute_with_retry(self, action_name, func, url=None):
        strategies = [
            # Strategy 1: Android/iOS (Highest success on unauthenticated networks)
            {"extractor_args": {"youtube": {"player_client": ["android", "ios"]}}},
            # Strategy 2: Web Creator + TV (Highly successful Cloud API fallback)
            {"extractor_args": {"youtube": {"player_client": ["web_creator", "tv"]}}},
            # Strategy 3: Default Desktop Web
            {"extractor_args": {"youtube": {"player_client": ["web"]}}},
            # Strategy 4: Bare metadata
            {}
        ]

        last_error = None
        for i, strategy_config in enumerate(strategies):
            try:
                self.logger.info(f"[{action_name}] Attempt {i+1}/4 | Config: {strategy_config}")
                ydl_opts = self._get_ydl_opts(strategy_config)
                result = func(ydl_opts)
                if not result:
                    raise ValueError("Function returned empty payload.")
                return result
            except Exception as e:
                error_msg = str(e).lower()
                last_error = e
                self.logger.warning(f"[{action_name}] Strategy {i+1} failed: {error_msg}")
                if any(err in error_msg for err in ["private video", "members-only", "unavailable", "copyright"]):
                    raise e
                continue

        raise last_error

    def _get_streaming_logic(self, url, format_id):
        """Worker logic to get streaming metadata."""
        def _extract(opts):
            opts_copy = opts.copy()
            opts_copy.update({'no_playlist': True})
            with yt_dlp.YoutubeDL(opts_copy) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise ValueError("Required streaming metadata is missing.")
                return info
        return self._execute_with_retry("get_streaming_info", _extract, url=url)

    def stream_video(self, url, format_id):
        """Web-server handles streaming, using data extracted by Worker."""
        from .tasks import get_streaming_info_task
        try:
            result = get_streaming_info_task.delay(url, format_id)
            info = result.get(timeout=30)
            
            # Now proceed with streaming logic (same as before but using 'info')
            return self._process_streaming_info(info, format_id)
        except Exception as e:
            self.logger.error(f"Streaming info task failed: {str(e)}")
            raise e

    def _process_streaming_info(self, info, format_id):
        """Logic to handle ffmpeg or requests streaming based on info."""
        needs_audio = False
        chosen = next((f for f in info.get('formats', []) if f['format_id'] == format_id), None)
        
        if not chosen:
            raise ValueError(f"Could not locate matching format_id {format_id}")
            
        if chosen.get('vcodec') != 'none' and chosen.get('acodec') == 'none':
            needs_audio = True

        if needs_audio:
            # FFMPEG Logic
            v_url = chosen['url']
            audio = next((f for f in reversed(info['formats']) if f.get('acodec') != 'none' and (f.get('vcodec') == 'none' or not f.get('vcodec'))), None)
            if not audio:
                audio = next((f for f in info['formats'] if f.get('acodec') != 'none'), None)

            a_url = audio['url'] if audio else v_url
            headers_list = [f"{k}: {v}" for k, v in info.get('http_headers', {}).items()]
            headers_str = "\r\n".join(headers_list) + "\r\n" if headers_list else ""

            ffmpeg_cmd = [
                'ffmpeg', '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5'
            ]
            if headers_str:
                ffmpeg_cmd.extend(['-headers', headers_str])
            if self.cookies_path and os.path.exists(self.cookies_path):
                ffmpeg_cmd.extend(['-cookies', self.cookies_path])
            
            ffmpeg_cmd.extend(['-i', v_url])
            ffmpeg_cmd.extend(['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5'])
            if headers_str:
                ffmpeg_cmd.extend(['-headers', headers_str])
            if self.cookies_path and os.path.exists(self.cookies_path):
                ffmpeg_cmd.extend(['-cookies', self.cookies_path])
                
            ffmpeg_cmd.extend(['-i', a_url])
            ffmpeg_cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-map', '0:v:0', '-map', '1:a:0', '-f', 'matroska', 'pipe:1'])

            process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, close_fds=True)

            def generate_ffmpeg():
                try:
                    while True:
                        chunk = process.stdout.read(65536)
                        if not chunk: break
                        yield chunk
                finally:
                    process.stdout.close()
                    if process.poll() is None: process.kill()
                    process.wait()

            return generate_ffmpeg(), info.get('title'), chosen.get('filesize'), 'mkv'

        else:
            # Requests Logic
            v_url = chosen['url']
            headers = info.get('http_headers', {})
            session = requests.Session()
            if self.cookies_path and os.path.exists(self.cookies_path):
                cookie_jar = http.cookiejar.MozillaCookieJar(self.cookies_path)
                try:
                    cookie_jar.load(ignore_discard=True, ignore_expires=True)
                    session.cookies.update(cookie_jar)
                except Exception: pass

            try:
                r_head = session.head(v_url, headers=headers, allow_redirects=True, timeout=10)
                filesize = int(r_head.headers.get('Content-Length', chosen.get('filesize') or 0))
            except Exception:
                filesize = chosen.get('filesize') or 0

            def generate_requests():
                with session.get(v_url, headers=headers, stream=True, timeout=15) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk: yield chunk

            ext = chosen.get('ext', 'mp4')
            if chosen.get('vcodec') == 'none' and ext == 'webm':
                ext = 'weba'
            return generate_requests(), info.get('title'), filesize, ext
