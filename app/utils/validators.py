from urllib.parse import urlparse


def is_valid_video_url(url):
    """
    Validates that the provided URL is a valid video URL from supported platforms.
    Also acts as a safety check against command injection and SSRF.
    """
    if not url:
        return False

    # Basic URL structure check
    parsed = urlparse(url)
    if not all([parsed.scheme, parsed.netloc]):
        return False

    # Enforce strict http/https scheme to prevent SSRF or file reads
    if parsed.scheme.lower() not in ['http', 'https']:
        return False

    # Check for dangerous characters (yt-dlp handles many, but extra safety is
    # good)
    if any(char in url for char in [';', '&', '|', '>', '<', '`', '$']):
        return False

    # List of allowed domains (can be expanded)
    allowed_domains = [
        'youtube.com', 'youtu.be', 'vimeo.com', 'facebook.com',
        'instagram.com', 'tiktok.com', 'twitter.com', 'x.com'
    ]

    domain = parsed.netloc.lower()
    if domain.startswith('www.'):
        domain = domain[4:]

    return any(domain == d or domain.endswith('.' + d)
               for d in allowed_domains)
