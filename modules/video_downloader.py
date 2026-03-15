"""
modules/video_downloader.py
Downloads a vertical stock video from Pexels API matching the given topic/keyword.

NEW WORKFLOW (sync fix):
  - download_space_video(topic) → returns (path, duration_seconds, description)
  - The caller (main.py) passes duration to ScriptGenerator so the script
    is written to MATCH the video length exactly — eliminating A/V sync issues.
  - The description is also passed to the script generator so the script
    is visually relevant to what appears in the video.

VIDEO QUALITY SCORING:
  Pexels results are now ranked by a quality score instead of being random.
  Scoring prefers: portrait orientation > HD quality > duration fit for Shorts.

Pexels API: https://www.pexels.com/api/
"""

import logging
import os
import subprocess
import requests
from typing import Optional, List, Tuple

import config as cfg
from modules.keyword_extractor import KeywordExtractor

logger = logging.getLogger(__name__)

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
MIN_DURATION = 15
MAX_DURATION = 70
PREFERRED_QUALITY = ["hd", "sd"]
REQUEST_TIMEOUT = 30

# Space-specific fallback queries tried in order if topic keywords yield nothing
SPACE_FALLBACK_QUERIES = [
    "space galaxy stars",
    "nebula cosmos",
    "planet universe",
    "astronaut space",
    "milky way night sky",
    "black hole space",
    "solar system planets",
    "stars timelapse",
]


class VideoDownloader:
    """Downloads vertical stock space videos from Pexels."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("PEXELS_API_KEY is required for video download.")
        self.api_key = api_key
        self._headers = {"Authorization": api_key}
        self.extractor = KeywordExtractor()

    # ── PRIMARY METHOD (new workflow) ─────────────────────────────────────────

    def download_space_video(
        self,
        topic: str,
        output_path: str = cfg.VIDEO_RAW_PATH,
    ) -> Tuple[str, float, str]:
        """
        Download the best-scoring space video for the given topic.

        Returns:
            (local_file_path, actual_duration_in_seconds, video_description)

        The returned duration is the REAL video duration (via ffprobe), clamped
        to SHORTS_MAX_DURATION. Pass this to ScriptGenerator so the script fits
        the video exactly — this is the core fix for the audio/video sync bug.

        The description string contains the Pexels video's user and alt text
        which is passed to the LLM so the voiceover script is relevant to the
        actual footage selected.
        """
        keywords = self.extractor.extract(topic)
        logger.info("Keywords for space video search: %s", keywords)

        # Build search query list: specific first, generic fallbacks last
        search_queries = []
        if len(keywords) >= 2:
            search_queries.append(f"{keywords[0]} {keywords[1]} space")
        search_queries.extend(keywords)
        search_queries.extend(SPACE_FALLBACK_QUERIES)

        video_url = None
        pexels_duration = None
        video_description = ""

        for query in search_queries:
            logger.info("Searching Pexels: '%s'", query)
            data = self._search_pexels(query)
            if data:
                result = self._pick_best_video(data.get("videos", []))
                if result:
                    video_url, pexels_duration, video_description = result
                    logger.info(
                        "Selected video — Pexels duration: %.1fs, description: '%s'",
                        pexels_duration,
                        video_description[:80],
                    )
                    break
            logger.warning("No result for '%s', trying next...", query)

        if not video_url:
            raise RuntimeError("No suitable space video found on Pexels after all queries.")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self._stream_download(video_url, output_path)

        # Use ffprobe for the real duration (Pexels metadata can be slightly off)
        real_duration = self._probe_duration(output_path) or pexels_duration
        real_duration = min(real_duration, cfg.SHORTS_MAX_DURATION)

        logger.info("Video saved: %s (%.2fs)", output_path, real_duration)
        return output_path, real_duration, video_description

    # ── SEGMENT DOWNLOAD (used by video editor for variety) ───────────────────

    def download_segments(self, topic: str, script: str, n_segments: int = 3) -> List[str]:
        """
        Download n unique video clips to use as timeline segments.
        Called AFTER the script is generated in the new workflow.
        """
        import re
        sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", script.strip()))
        sentences = [s for s in sentences if s.strip()]

        if not sentences:
            path, _, _ = self.download_space_video(topic)
            return [path]

        avg = len(sentences) / float(n_segments)
        segment_texts, last = [], 0.0
        while last < len(sentences):
            segment_texts.append(" ".join(sentences[int(last) : int(last + avg)]))
            last += avg
        segment_texts = segment_texts[:n_segments]

        video_paths = []
        for i, seg_text in enumerate(segment_texts):
            seg_path = os.path.join(cfg.OUTPUT_DIR, f"segment_{i}.mp4")
            try:
                seg_topic = f"{topic} {' '.join(seg_text.split()[:3])}"
                path, _, _ = self.download_space_video(seg_topic, seg_path)
                video_paths.append(path)
            except Exception as e:
                logger.error("Segment %d download failed: %s", i, e)

        if not video_paths:
            logger.warning("All segments failed — falling back to single video.")
            path, _, _ = self.download_space_video(topic)
            return [path]

        return video_paths

    # ── Legacy single download (backwards compat) ────────────────────────────

    def download(self, topic: str, script: str = None, output_path: str = cfg.VIDEO_RAW_PATH) -> str:
        """Legacy method — returns path only (no duration or description)."""
        path, _, _ = self.download_space_video(topic, output_path)
        return path

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _search_pexels(self, query: str) -> Optional[dict]:
        params = {"query": query, "per_page": 15, "orientation": "portrait"}
        try:
            resp = requests.get(
                PEXELS_SEARCH_URL,
                headers=self._headers,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return data if data.get("videos") else None
        except Exception as e:
            logger.error("Pexels API error: %s", e)
            return None

    def _pick_best_video(self, videos: list) -> Optional[Tuple[str, float, str]]:
        """
        Score and select the best video. Returns (url, duration, description).

        Scoring criteria (higher is better):
          +3  portrait orientation (height > width)
          +2  HD quality file available
          +1  duration between 20-59s (ideal for Shorts)
          -1  very short (<15s) or very long (>70s)
        """
        if not videos:
            return None

        scored = []
        for video in videos:
            score = 0
            duration = float(video.get("duration", 0))

            # Duration scoring
            if 20 <= duration <= 59:
                score += 1
            elif duration < MIN_DURATION or duration > MAX_DURATION:
                score -= 1

            # Find best file
            best_url = None
            best_quality = None
            width = video.get("width", 0)
            height = video.get("height", 0)

            # Portrait orientation preference
            if height > width:
                score += 3

            for quality in PREFERRED_QUALITY:
                for vf in video.get("video_files", []):
                    if vf.get("quality") == quality:
                        if best_url is None:
                            best_url = vf["link"]
                            best_quality = quality

            if best_quality == "hd":
                score += 2
            elif best_quality == "sd":
                score += 1

            # Fallback: use first available file
            if best_url is None and video.get("video_files"):
                best_url = video["video_files"][0]["link"]

            if best_url:
                # Build a description from Pexels metadata
                user = video.get("user", {}).get("name", "")
                alt = video.get("alt", "") or ""
                description = f"{alt} (by {user})".strip(" ()")
                scored.append((score, duration, best_url, description))

        if not scored:
            return None

        # Sort by score descending, pick the best
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_duration, best_url, best_desc = scored[0]
        logger.info(
            "Video selected: score=%d, duration=%.1fs, desc='%s'",
            best_score, best_duration, best_desc[:60],
        )
        return best_url, best_duration, best_desc

    def _probe_duration(self, path: str) -> Optional[float]:
        """Get exact video duration via ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return float(result.stdout.strip())
        except Exception as e:
            logger.warning("ffprobe failed: %s", e)
            return None

    def _stream_download(self, url: str, output_path: str) -> None:
        logger.info("Downloading video data...")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        logger.info("Video saved to %s", output_path)