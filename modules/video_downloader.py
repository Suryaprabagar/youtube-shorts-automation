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

    def generate_keywords(self, topic: str, script: str = None) -> tuple[str, str]:
        """
        Extract the best search keyword and a fallback category from the topic.
        Since this is a space channel, we force the fallback to 'space' or 'galaxy'.
        Returns: (primary_keyword, fallback_category)
        """
        fallback_category = "space"
        
        # Space-specific terms to look for
        space_terms = [
            "space", "galaxy", "nebula", "astronaut", "planet",
            "milky way", "universe", "stars", "cosmos", "black hole",
            "solar system", "moon", "sun", "supernova", "telescope"
        ]
        
        # 1. Search the raw topic and script for these terms directly first
        text_to_analyze = topic.lower()
        if script:
            text_to_analyze += " " + script.lower()
            
        for term in ["black hole", "milky way", "solar system"]:  # Check multi-word first
            if term in text_to_analyze:
                logger.info("Pexels keywords extracted -> primary: '%s', fallback: '%s'", term, fallback_category)
                return term, fallback_category
                
        for term in space_terms:
            if term in text_to_analyze:
                 # Prefer a 2-word combo if possible
                 words = text_to_analyze.split()
                 if term in set(words):
                    idx = words.index(term)
                    if idx > 0 and len(words[idx-1]) > 3:
                        primary_query = f"{words[idx-1]} {term}"
                    else:
                        primary_query = term
                    logger.info("Pexels keywords extracted -> primary: '%s', fallback: '%s'", primary_query, fallback_category)
                    return primary_query, fallback_category

        # Fallback if nothing matched (rare for a space channel)
        primary_query = random.choice(["galaxy", "deep space", "nebula"])
            
        logger.info("Pexels keywords extracted -> primary: '%s', fallback: '%s'", primary_query, fallback_category)
        return primary_query, fallback_category

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
        keyword, fallback_category = self.generate_keywords(topic, script)
        
        # The _search_pexels method now returns the full data, not just the URL.
        # We need to adapt the call and subsequent logic.
        pexels_data = self._search_pexels(keyword)
        video_url = None
        if pexels_data:
            video_url = self._select_best_video_url(pexels_data.get("videos", []))

        if not video_url:
            # Fallback: try with the category extracted from the topic
            logger.warning("No results for '%s', retrying with fallback '%s'", keyword, fallback_category)
            pexels_data_fallback = self._search_pexels(fallback_category)
            if pexels_data_fallback:
                video_url = self._select_best_video_url(pexels_data_fallback.get("videos", []))

        if not video_url:
            raise RuntimeError(f"Could not find a suitable video on Pexels for '{keyword}' or '{fallback_category}'.")

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
