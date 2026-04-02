from celery import shared_task
from .services.download_service import DownloadService
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def extract_video_info_task(self, url):
    """Task to extract video information using yt-dlp."""
    try:
        service = DownloadService()
        return service._extract_info_logic(url)
    except Exception as exc:
        logger.error(f"Task extraction failed for {url}: {str(exc)}")
        # Retry for temporary failures (like bot detection)
        if "bot" in str(exc).lower() or "sign in" in str(exc).lower():
             raise self.retry(exc=exc)
        raise exc

@shared_task(bind=True, max_retries=2)
def get_streaming_info_task(self, url, format_id):
    """Task to get direct streaming URL and headers."""
    try:
        service = DownloadService()
        return service._get_streaming_logic(url, format_id)
    except Exception as exc:
        logger.error(f"Task streaming info failed for {url}: {str(exc)}")
        raise self.retry(exc=exc)
