import yt_dlp
import os
import sys
import logging
import subprocess
import requests
import http.cookiejar

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

    def _execute_with_retry(self, action_name, func, url=None):
        """
        Executes a yt-dlp function block across multiple signature strategies.
        This intelligently bypasses 'bot detection' by rotating configurations.
        """
        strategies = [
            # Strategy 1: Default Desktop Web (Required when passing Desktop Browser Cookies securely)
            {"extractor_args": {"youtube": {"player_client": ["web"]}}},
            # Strategy 2: Android/iOS (Highest success on unauthenticated networks)
            {"extractor_args": {"youtube": {"player_client": ["android", "ios"]}}},
            # Strategy 3: Web Creator + TV (Highly successful Cloud API fallback without cookies)
            {"extractor_args": {"youtube": {"player_client": ["web_creator", "tv"]}}},
            # Strategy 4: Bare metadata
            {}
        ]

        last_error = None
        for i, strategy_config in enumerate(strategies):
            try:
                self.logger.info(f"[{action_name}] Extracting '{url}' | Attempt {i+1}/4 | Config: {strategy_config}")

                # Base secure configuration for Render
                ydl_opts = {
                    "quiet": True,
                    "source_address": "0.0.0.0",
                    "force_ipv4": True,
                    "legacyserverconnect": True
                }

                if self.cookies_path:
                    ydl_opts["cookiefile"] = self.cookies_path

                # Inject dynamic strategy
                ydl_opts.update(strategy_config)

                # Return the execution payload precisely
                result = func(ydl_opts)
                if not result:
                    raise ValueError(f"[{action_name}] Function returned empty payload.")
                
                self.logger.info(f"[{action_name}] SUCCESS on Attempt {i+1}!")
                return result

            except Exception as e:
                error_msg = str(e).lower()
                last_error = e
                self.logger.warning(f"[{action_name}] Strategy {i+1} failed: {error_msg}")

                # Break immediately on permanent URL errors to save bandwidth
                if any(err in error_msg for err in ["private video", "members-only", "unavailable", "copyright"]):
                    self.logger.error(f"[{action_name}] Permanent fetch error: {error_msg}")
                    raise e
                    
                continue

        self.logger.error(f"[{action_name}] ALL STRATEGIES EXHAUSTED for '{url}'. Render IP may be hard-blocked. Provide cookies.txt!")
        raise last_error

    def get_formats(self, url):
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
                    # Throw error so the retry loop engages!
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

        # Route the extraction through the retry engine
        return self._execute_with_retry("get_formats", _extract, url=url)

    def get_download_url(self, url, format_id):
        def _extract(opts):
            opts_copy = opts.copy()
            opts_copy.update({
                "format": format_id,
                "noplaylist": True
            })
            
            with yt_dlp.YoutubeDL(opts_copy) as ydl:
                info = ydl.extract_info(url, download=False)
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                }
                if info.get('http_headers'):
                    headers.update(info['http_headers'])

                url_payload = info.get("url")
                if not url_payload:
                    raise ValueError("Blocked: Payload 'url' not found in response.")

                return url_payload, info.get("title"), info.get("filesize"), headers

        return self._execute_with_retry(f"get_download_url [{format_id}]", _extract, url=url)

    def stream_video(self, url, format_id):
        def _extract_and_stream(opts):
            opts_copy = opts.copy()
            opts_copy.update({'no_playlist': True})
            
            with yt_dlp.YoutubeDL(opts_copy) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Double-verify info load
                if not info or not info.get('formats'):
                    raise ValueError("Blocked: Required streaming metadata is totally missing.")

                needs_audio = False
                chosen = next((f for f in info.get('formats', []) if f['format_id'] == format_id), None)
                
                if not chosen:
                    raise ValueError(f"Could not locate matching format_id {format_id}")
                    
                if chosen.get('vcodec') != 'none' and chosen.get('acodec') == 'none':
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
                    ua = info.get('http_headers', {}).get('User-Agent', 'Mozilla/5.0')

                    headers_list = []
                    for k, v in info.get('http_headers', {}).items():
                        headers_list.append(f"{k}: {v}")
                    headers_str = "\r\n".join(headers_list) + "\r\n" if headers_list else ""

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

                    session = requests.Session()
                    if self.cookies_path and os.path.exists(self.cookies_path):
                        cookie_jar = http.cookiejar.MozillaCookieJar(self.cookies_path)
                        try:
                            cookie_jar.load(ignore_discard=True, ignore_expires=True)
                            session.cookies.update(cookie_jar)
                        except Exception as e:
                            self.logger.warning(f"Could not load cookies for requests: {str(e)}")

                    try:
                        r_head = session.head(v_url, headers=headers, allow_redirects=True, timeout=10)
                        filesize = int(r_head.headers.get('Content-Length', chosen.get('filesize') or 0))
                    except BaseException:
                        filesize = chosen.get('filesize') or 0

                    def generate_requests():
                        with session.get(v_url, headers=headers, stream=True, timeout=15) as r:
                            r.raise_for_status()
                            for chunk in r.iter_content(chunk_size=65536):
                                if chunk:
                                    yield chunk

                    ext = chosen.get('ext', 'mp4') if chosen else 'mp4'
                    if chosen and chosen.get('vcodec') == 'none':
                        if ext == 'webm':
                            ext = 'weba'

                    return generate_requests(), info.get('title'), filesize, ext

        return self._execute_with_retry("stream_video", _extract_and_stream, url=url)
