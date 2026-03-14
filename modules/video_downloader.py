"""
modules/video_downloader.py
Downloads a vertical stock video from Pexels API matching the given topic/keyword.

Pexels API: https://www.pexels.com/api/
"""

import logging
import os
import random
import requests
from typing import Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config as cfg
from modules.keyword_extractor import KeywordExtractor

logger = logging.getLogger(__name__)

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PREFERRED_ORIENTATIONS = ["portrait"]
MIN_DURATION = 15
MAX_DURATION = 70
PREFERRED_QUALITY = ["hd", "sd"]
REQUEST_TIMEOUT = 30

class VideoDownloader:
    """Downloads a vertical stock video from Pexels for a given topic keyword."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("PEXELS_API_KEY is required for video download.")
        self.api_key = api_key
        self._headers = {"Authorization": api_key}
        self.extractor = KeywordExtractor()

    @retry(
        retry=retry_if_exception_type((requests.RequestException, RuntimeError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def download(self, topic: str, script: str = None, output_path: str = cfg.VIDEO_RAW_PATH) -> str:
        """
        Search Pexels for a vertical video matching the topic and download it.
        Uses KeywordExtractor to try multiple queries.
        """
        keywords = self.extractor.extract(topic, script)
        logger.info(f"Using extracted keywords for search: {keywords}")

        # Try multiple search queries based on keywords
        search_queries = keywords.copy()
        
        # Add combined queries for better results if we have multiple keywords
        if len(keywords) >= 2:
            search_queries.insert(0, f"{keywords[0]} {keywords[1]}")
            
        # Add generic fallback as last resort
        search_queries.append("space universe galaxy")
        
        video_url = None
        for query in search_queries:
            logger.info(f"Searching Pexels for: '{query}'")
            pexels_data = self._search_pexels(query)
            if pexels_data:
                video_url = self._select_best_video_url(pexels_data.get("videos", []), query)
                if video_url:
                    logger.info(f"Found suitable video for query: '{query}'")
                    break
            logger.warning(f"No suitable video found for query: '{query}', trying next...")

        if not video_url:
            raise RuntimeError(f"Could not find a suitable video on Pexels after trying all keywords.")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self._stream_download(video_url, output_path)
        return output_path

    def download_segments(self, topic: str, script: str, n_segments: int = 4) -> List[str]:
        """
        Splits the script into n segments and downloads a unique video clip for each.
        Returns a list of local file paths.
        """
        import re
        # Clean and split script into sentences
        clean_script = re.sub(r'\s+', ' ', script.strip())
        sentences = re.split(r'(?<=[.!?])\s+', clean_script)
        sentences = [s for s in sentences if s.strip()]
        
        if not sentences:
            # Fallback to single download if no sentences found
            return [self.download(topic, script)]

        # Chunk sentences into n segments
        avg = len(sentences) / float(n_segments)
        segment_texts = []
        last = 0.0
        while last < len(sentences):
            segment_texts.append(" ".join(sentences[int(last):int(last + avg)]))
            last += avg
        
        # Ensure we don't have more than n_segments
        segment_texts = segment_texts[:n_segments]
        
        video_paths = []
        logger.info(f"Downloading {len(segment_texts)} video segments...")
        
        for i, seg_text in enumerate(segment_texts):
            seg_path = os.path.join(cfg.OUTPUT_DIR, f"segment_{i}.mp4")
            try:
                # Use first few words of segment as extra topic context
                seg_topic = f"{topic} {' '.join(seg_text.split()[:3])}"
                path = self.download(seg_topic, seg_text, output_path=seg_path)
                video_paths.append(path)
            except Exception as e:
                logger.error(f"Failed to download segment {i}: {e}")
                # If we have at least one segment, we can proceed, otherwise fallback
                continue
        
        if not video_paths:
            logger.warning("All segment downloads failed. Falling back to single video.")
            return [self.download(topic, script)]
            
        return video_paths

    def _search_pexels(self, query: str) -> Optional[dict]:
        """Call Pexels API to search for videos."""
        params = {
            "query": query,
            "per_page": 10,
            "orientation": "portrait"
        }
        try:
            resp = requests.get(PEXELS_SEARCH_URL, headers=self._headers, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("videos"):
                return None
            return data
        except Exception as e:
            logger.error(f"Pexels API error: {e}")
            return None

    def _select_best_video_url(self, videos: list, query: str) -> Optional[str]:
        """Selects the best video URL from a list of Pexels video objects."""
        if not videos:
            return None

        # Preference terms for filtering
        preference_terms = ["astronaut", "planet", "nebula", "galaxy", "space animation"]
        
        # Sort videos: prioritized ones first
        def get_priority(v):
            description = str(v.get("url", "")).lower()
            # If the description or tags (if available) contain preference terms, higher priority
            priority = 0
            for term in preference_terms:
                if term in description:
                    priority += 1
            return priority

        # Filter by duration and orientation (though API should handle orientation)
        suitable = [
            v for v in videos
            if MIN_DURATION <= v.get("duration", 0) <= MAX_DURATION
        ]
        
        if not suitable:
            suitable = videos # Relax duration filter if no match

        # Sort by priority (most relevant first)
        suitable.sort(key=get_priority, reverse=True)

        # Pick the best quality for the selected video
        for video in suitable:
            video_files = video.get("video_files", [])
            # Sort by quality preference
            for quality in PREFERRED_QUALITY:
                for vf in video_files:
                    if vf.get("quality") == quality:
                        return vf["link"]
            
            # If no HD/SD preference, take first available
            if video_files:
                return video_files[0]["link"]

        return None

    def _stream_download(self, url: str, output_path: str) -> None:
        """Stream-download a video file to disk."""
        logger.info("Downloading video data...")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        logger.info(f"Video saved to {output_path}")
