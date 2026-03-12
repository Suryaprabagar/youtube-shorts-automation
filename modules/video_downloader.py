"""
modules/video_downloader.py
Downloads a vertical stock video from Pexels API matching the given topic/keyword.

Pexels API: https://www.pexels.com/api/
Free tier: 200 requests/hour, 20,000/month
"""

import logging
import os
import re
import requests
import math
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config as cfg

logger = logging.getLogger(__name__)

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PREFERRED_ORIENTATIONS = ["portrait"]   # vertical/portrait for Shorts
MIN_DURATION = 15   # seconds
MAX_DURATION = 70   # seconds
PREFERRED_QUALITY = ["hd", "sd"]       # prefer HD, fall back to SD
REQUEST_TIMEOUT = 30                    # seconds


class VideoDownloader:
    """Downloads a vertical stock video from Pexels for a given topic keyword."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("PEXELS_API_KEY is required for video download.")
        self.api_key = api_key # Store api_key directly for use in _search_pexels
        self._headers = {"Authorization": api_key}

    def generate_keyword(self, topic: str, script: str = None) -> str:
        """Extract a short 1-3 word search keyword from the topic/script."""
        # Prioritize the topic for the search keyword since it's more concise 
        # and relevant than the first words of the script's hook.
        text_to_analyze = topic
        
        stop_words = {
            "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
            "in", "on", "at", "to", "for", "of", "with", "that", "this", "you",
            "why", "how", "what", "when", "who", "your", "my", "our", "their",
            "will", "can", "do", "does", "from", "by", "as", "it", "its", "here",
            "crazy", "secret", "about", "did", "know", "untold", "truth", "stop",
            "scrolling"
        }
        
        # Strip punctuation and common words
        words = re.sub(r"[^a-zA-Z\s]", "", text_to_analyze).lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        # If we have a series format "Tech Secrets #1: The quantum...", strip the title part
        if "#" in topic and ":" in topic:
            topic_core = topic.split(":", 1)[1].strip()
            topic_words = re.sub(r"[^a-zA-Z\s]", "", topic_core).lower().split()
            topic_keywords = [w for w in topic_words if w not in stop_words and len(w) > 2]
            if topic_keywords:
                query = " ".join(topic_keywords[:2])
                logger.info("Pexels search keyword from topic core: '%s'", query)
                return query

        if keywords:
            # Grab top most common/meaningful nouns empirically (just pick first 2-3)
            query = " ".join(keywords[:2])
        else:
            query = "nature background"
            
        logger.info("Pexels search keyword: '%s'", query)
        return query

    @retry(
        retry=retry_if_exception_type((requests.RequestException, RuntimeError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def download(self, topic: str, script: str = None, output_path: str = cfg.VIDEO_RAW_PATH) -> str:
        """
        Search Pexels for a vertical video matching the topic and download it.

        Args:
            topic: Topic string used to derive a search keyword.
            script: Optional script content for better keyword extraction.
            output_path: Where to save the downloaded video.

        Returns:
            Absolute path to the downloaded video.
        """
        keyword = self.generate_keyword(topic, script)
        
        # The _search_pexels method now returns the full data, not just the URL.
        # We need to adapt the call and subsequent logic.
        pexels_data = self._search_pexels(keyword)
        video_url = None
        if pexels_data:
            video_url = self._select_best_video_url(pexels_data.get("videos", []))

        if not video_url:
            # Fallback: try with a generic keyword
            logger.warning("No results for '%s', retrying with 'nature background'", keyword)
            pexels_data_fallback = self._search_pexels("nature background")
            if pexels_data_fallback:
                video_url = self._select_best_video_url(pexels_data_fallback.get("videos", []))

        if not video_url:
            raise RuntimeError("Could not find a suitable video on Pexels.")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self._stream_download(video_url, output_path)
        return output_path

    @retry(
        retry=retry_if_exception_type((Exception)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _search_pexels(self, keyword: str) -> Optional[dict]:
        """Call Pexels API to search for orientatation=portrait videos."""
        url = "https://api.pexels.com/videos/search"
        headers = {"Authorization": self.api_key}
        # Request a few more results since we'll try to find an exact matching short one
        params = {
            "query": keyword, # Removed 'background' from query to allow broader exact matching
            "per_page": 10,
            "orientation": "portrait"
        }
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        
        data = resp.json()
        if not data.get("videos"):
            logger.warning("No Pexels videos found for keyword '%s'", keyword)
            return None
        return data

    def _select_best_video_url(self, videos: list) -> str | None:
        """Selects the best video URL from a list of Pexels video objects."""
        if not videos:
            return None

        # Filter by duration
        suitable = [
            v for v in videos
            if MIN_DURATION <= v.get("duration", 0) <= MAX_DURATION
        ]
        if not suitable:
            suitable = videos  # relax filter if nothing matches

        # Pick the first suitable video and select the best quality file
        video = suitable[0]
        video_files = video.get("video_files", [])

        # Sort by quality preference
        for quality in PREFERRED_QUALITY:
            for vf in video_files:
                if vf.get("quality") == quality:
                    logger.info(
                        "Selected Pexels video ID=%s, quality=%s, duration=%ds",
                        video.get("id"), quality, video.get("duration"),
                    )
                    return vf["link"]

        # If no preferred quality, return the first available
        if video_files:
            return video_files[0]["link"]
        return None

    def _stream_download(self, url: str, output_path: str) -> None:
        """Stream-download a video file to disk with progress logging."""
        logger.info("Downloading video from Pexels...")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            logger.info(
                "Video downloaded to '%s' (%.1f MB).",
                output_path, downloaded / (1024 * 1024),
            )
