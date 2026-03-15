"""
modules/video_downloader.py
Downloads a vertical stock space video from Pexels API matching the given topic/keyword.

NEW WORKFLOW (sync fix):
  - download_space_video(topic) → returns (path, duration_seconds, description)
  - The caller (main.py) passes duration to ScriptGenerator so the script
    is written to MATCH the video length exactly — eliminating A/V sync issues.
  - The description is also passed to the script generator so the script
    is visually relevant to what appears in the video.

VIDEO QUALITY SCORING:
  Pexels results are ranked by a quality score instead of being random.
  Scoring prefers: portrait orientation > HD quality > duration fit for Shorts.
  Space content filter: videos with irrelevant alt-text (no space keywords)
  are discarded before scoring.

ANTI-REPEAT:
  Used Pexels video IDs are persisted to data/used_video_ids.json.
  Previously seen IDs are skipped so every run gets a fresh clip.

Pexels API: https://www.pexels.com/api/
"""

import json
import logging
import os
import random
import re
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

# How many top-scored candidates to randomly pick from (prevents same clip each run)
TOP_N_RANDOM = 5

# Path to persist used video IDs between runs
USED_IDS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "used_video_ids.json")
MAX_USED_IDS = 100  # Keep only the most recent N IDs to avoid unbounded growth

# Keywords that must appear in a video's alt/description text to be considered space-related
SPACE_CONTENT_KEYWORDS = {
    "space", "galaxy", "nebula", "star", "stars", "planet", "cosmos",
    "universe", "astronaut", "milky way", "black hole", "supernova",
    "telescope", "solar", "moon", "sun", "mars", "jupiter", "saturn",
    "earth orbit", "astronomer", "astronomy", "rocket", "nasa", "spacex",
    "comet", "asteroid", "meteor", "night sky", "timelapse sky",
    "cosmic", "orbit", "spacecraft", "satellite", "hubble", "stellar",
}

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
        self._used_ids = self._load_used_ids()

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
        search_queries.extend([f"{kw} space" for kw in keywords])
        search_queries.extend(SPACE_FALLBACK_QUERIES)

        # Deduplicate while preserving order
        seen = set()
        unique_queries = []
        for q in search_queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)

        video_url = None
        pexels_duration = None
        video_description = ""
        chosen_video_id = None

        # --- Pass 1: space-filtered search ---
        for query in unique_queries:
            logger.info("Searching Pexels (space-filtered): '%s'", query)
            data = self._search_pexels(query)
            if data:
                result = self._pick_best_video(data.get("videos", []), require_space=True)
                if result:
                    video_url, pexels_duration, video_description, chosen_video_id = result
                    logger.info(
                        "Selected video (filtered) id=%s, dur=%.1fs, desc='%s'",
                        chosen_video_id,
                        pexels_duration,
                        video_description[:80],
                    )
                    break
            logger.warning("No space-filtered result for '%s', trying next...", query)

        # --- Pass 2: relaxed (accept any portrait video) if nothing found above ---
        if not video_url:
            logger.warning("Space filter yielded nothing — relaxing content filter.")
            for query in unique_queries:
                logger.info("Searching Pexels (relaxed): '%s'", query)
                data = self._search_pexels(query)
                if data:
                    result = self._pick_best_video(data.get("videos", []), require_space=False)
                    if result:
                        video_url, pexels_duration, video_description, chosen_video_id = result
                        logger.info(
                            "Selected video (relaxed) id=%s, dur=%.1fs, desc='%s'",
                            chosen_video_id,
                            pexels_duration,
                            video_description[:80],
                        )
                        break
                logger.warning("No relaxed result for '%s', trying next...", query)

        if not video_url:
            raise RuntimeError("No suitable space video found on Pexels after all queries.")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self._stream_download(video_url, output_path)

        # Mark this ID as used so it won't be reused in future runs
        if chosen_video_id:
            self._mark_used(chosen_video_id)

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
        # Always ensure "space" is in the query to bias Pexels content
        if "space" not in query.lower():
            query = f"{query} space"
        params = {"query": query, "per_page": 30, "orientation": "portrait"}
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

    def _is_space_related(self, video: dict) -> bool:
        """Return True if the video's alt/tags contain at least one space keyword."""
        alt = (video.get("alt") or "").lower()
        user_name = (video.get("user", {}).get("name") or "").lower()
        combined = f"{alt} {user_name}"
        for kw in SPACE_CONTENT_KEYWORDS:
            if kw in combined:
                return True
        return False

    def _pick_best_video(
        self, videos: list, require_space: bool = True
    ) -> Optional[Tuple[str, float, str, int]]:
        """
        Score and select the best video.
        Returns (url, duration, description, video_id) or None.

        Scoring criteria (higher is better):
          +3  portrait orientation (height > width)
          +2  HD quality file available
          +1  duration between 20-59s (ideal for Shorts)
          -1  very short (<15s) or very long (>70s)

        Selection:
          Randomly pick from the top-N scored candidates to avoid the same
          clip being chosen every run.

        Filters applied before scoring:
          - Skip videos whose ID is already in `used_ids`
          - Skip videos with no valid download URL
          - If require_space=True, skip videos with non-space alt text
        """
        if not videos:
            return None

        scored = []
        for video in videos:
            video_id = video.get("id")

            # Skip previously used videos
            if video_id and str(video_id) in self._used_ids:
                logger.debug("Skipping already-used video id=%s", video_id)
                continue

            # Space content filter
            if require_space and not self._is_space_related(video):
                logger.debug(
                    "Skipping non-space video id=%s alt='%s'",
                    video_id,
                    str(video.get("alt", ""))[:60],
                )
                continue

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
                user = video.get("user", {}).get("name", "")
                alt = video.get("alt", "") or ""
                description = f"{alt} (by {user})".strip(" ()")
                scored.append((score, duration, best_url, description, video_id))

        if not scored:
            return None

        # Sort by score descending, then randomly choose from the top-N candidates
        scored.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored[: min(TOP_N_RANDOM, len(scored))]
        chosen = random.choice(top_candidates)
        best_score, best_duration, best_url, best_desc, best_id = chosen
        logger.info(
            "Video selected: id=%s score=%d duration=%.1fs desc='%s'",
            best_id,
            best_score,
            best_duration,
            best_desc[:60],
        )
        return best_url, best_duration, best_desc, best_id

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

    # ── Used-ID persistence ───────────────────────────────────────────────────

    def _load_used_ids(self) -> set:
        """Load previously used video IDs from disk."""
        try:
            if os.path.exists(USED_IDS_PATH):
                with open(USED_IDS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    ids = set(str(i) for i in data.get("used_ids", []))
                    logger.info("Loaded %d used video IDs from history.", len(ids))
                    return ids
        except Exception as e:
            logger.warning("Could not load used_video_ids.json: %s", e)
        return set()

    def _mark_used(self, video_id) -> None:
        """Persist a newly used video ID to disk."""
        str_id = str(video_id)
        self._used_ids.add(str_id)
        try:
            os.makedirs(os.path.dirname(USED_IDS_PATH), exist_ok=True)
            # Keep only the most recent MAX_USED_IDS entries
            current_list = list(self._used_ids)
            if len(current_list) > MAX_USED_IDS:
                current_list = current_list[-MAX_USED_IDS:]
                self._used_ids = set(current_list)
            with open(USED_IDS_PATH, "w", encoding="utf-8") as f:
                json.dump({"used_ids": current_list}, f, indent=2)
            logger.info("Marked video id=%s as used (%d total).", str_id, len(current_list))
        except Exception as e:
            logger.warning("Could not save used_video_ids.json: %s", e)