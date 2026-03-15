"""
modules/video_downloader.py
Downloads a stock space video from Pexels API matching the given topic/keyword.

KEY FIXES IN THIS VERSION:
  1. No `orientation=portrait` restriction — accepts landscape AND portrait so the
     full Pexels space-video pool is available (most cinematic space footage is
     landscape, capping to portrait was starving the search).
  2. Multi-field space detection — checks `alt`, Pexels page URL slug (always
     present and descriptive), and `user.name` for space keywords. Alt alone is
     unreliable because it is frequently empty on Pexels.
  3. Negative keyword blocklist — explicitly rejects videos whose combined
     metadata contains people/food/animal terms.
  4. Portrait clips still preferred via +3 score bonus.
  5. Landscape flag returned so the editor (video_editor.py) can apply
     blur-pad conversion to make any landscape clip vertical.
  6. Randomised top-N selection prevents same clip every run.
  7. Used-ID persistence (data/used_video_ids.json) prevents same clip across runs.

NEW WORKFLOW (sync fix):
  - download_space_video(topic) → returns (path, duration_seconds, description)
  - The caller (main.py) passes duration to ScriptGenerator so the script
    is written to MATCH the video length exactly.
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
PREFERRED_QUALITY = ["hd", "sd", "hd+", "uhd"]
REQUEST_TIMEOUT = 30

# How many top-scored candidates to randomly pick from (prevents same clip each run)
TOP_N_RANDOM = 5

# Path to persist used video IDs between runs
USED_IDS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "used_video_ids.json")
MAX_USED_IDS = 100  # Rolling window

# ── Space content detection ────────────────────────────────────────────────────

# Keywords whose presence in alt/url/username → video IS space-related
SPACE_POSITIVE_KEYWORDS = {
    "space", "galaxy", "galaxies", "nebula", "nebulae", "star", "stars",
    "planet", "planets", "cosmos", "universe", "astronaut", "milky",
    "milky-way", "milkyway", "black-hole", "blackhole", "supernova",
    "telescope", "solar", "moon", "sun", "mars", "jupiter", "saturn",
    "earth-orbit", "astronomer", "astronomy", "rocket", "nasa", "spacex",
    "comet", "asteroid", "meteor", "night-sky", "nightsky", "timelapse",
    "time-lapse", "cosmic", "orbit", "spacecraft", "satellite", "hubble",
    "stellar", "astrophoto", "astrophotography", "aurora", "constellation",
    "exoplanet", "quasar", "pulsar", "interstellar", "deep-space",
    "space-exploration", "launch", "observatory",
}

# Keywords whose presence → video is NOT space-related (reject regardless)
NEGATIVE_KEYWORDS = {
    "child", "children", "kid", "kids", "baby", "babies", "toddler",
    "woman", "man", "people", "person", "girl", "boy", "family",
    "beach", "ocean", "sea", "forest", "mountain", "city", "urban",
    "food", "cook", "cooking", "kitchen", "restaurant", "coffee",
    "dog", "cat", "animal", "bird", "horse", "fish",
    "wedding", "yoga", "gym", "fitness", "dance", "sport", "football",
    "fashion", "makeup", "hair",
}

# Space-specific fallback queries tried in order if topic keywords yield nothing
SPACE_FALLBACK_QUERIES = [
    "galaxy nebula space",
    "stars cosmos universe",
    "planet solar system",
    "astronaut space exploration",
    "milky way night sky",
    "black hole astronomy",
    "space timelapse stars",
    "nebula astrophotography",
]


class VideoDownloader:
    """Downloads stock space videos from Pexels (landscape or portrait)."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("PEXELS_API_KEY is required for video download.")
        self.api_key = api_key
        self._headers = {"Authorization": api_key}
        self.extractor = KeywordExtractor()
        self._used_ids = self._load_used_ids()

    # ── PRIMARY METHOD ────────────────────────────────────────────────────────

    def download_space_video(
        self,
        topic: str,
        output_path: str = cfg.VIDEO_RAW_PATH,
    ) -> Tuple[str, float, str]:
        """
        Download the best-scoring space video for the given topic.

        Returns:
            (local_file_path, actual_duration_in_seconds, video_description)

        Accepts both landscape and portrait videos. The editor handles converting
        landscape clips to 1080×1920 via FFmpeg blur-pad before compositing.
        """
        keywords = self.extractor.extract(topic)
        logger.info("Keywords for space video search: %s", keywords)

        # Build search query list: specific first, generic fallbacks last
        search_queries = []
        if len(keywords) >= 2:
            search_queries.append(f"{keywords[0]} {keywords[1]} space")
        for kw in keywords:
            search_queries.append(f"{kw} space")
            search_queries.append(f"{kw} astronomy")
        search_queries.extend(SPACE_FALLBACK_QUERIES)

        # Deduplicate while preserving order
        seen_q: set = set()
        unique_queries: List[str] = []
        for q in search_queries:
            if q not in seen_q:
                seen_q.add(q)
                unique_queries.append(q)

        video_url = None
        pexels_duration = None
        video_description = ""
        chosen_video_id = None

        # ── Pass 1: space-filtered search ────────────────────────────────────
        for query in unique_queries:
            logger.info("Searching Pexels (space-filtered): '%s'", query)
            data = self._search_pexels(query)
            if data:
                result = self._pick_best_video(data.get("videos", []), require_space=True)
                if result:
                    video_url, pexels_duration, video_description, chosen_video_id = result
                    logger.info(
                        "Selected video (filtered) id=%s dur=%.1fs desc='%s'",
                        chosen_video_id, pexels_duration, video_description[:80],
                    )
                    break
            logger.warning("No space-filtered result for '%s', trying next...", query)

        # ── Pass 2: relaxed (any video) if filter found nothing ───────────────
        if not video_url:
            logger.warning("Space filter yielded nothing — relaxing content filter.")
            for query in unique_queries:
                data = self._search_pexels(query)
                if data:
                    result = self._pick_best_video(data.get("videos", []), require_space=False)
                    if result:
                        video_url, pexels_duration, video_description, chosen_video_id = result
                        logger.info(
                            "Selected video (relaxed) id=%s dur=%.1fs desc='%s'",
                            chosen_video_id, pexels_duration, video_description[:80],
                        )
                        break

        if not video_url:
            raise RuntimeError("No suitable space video found on Pexels after all queries.")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self._stream_download(video_url, output_path)

        if chosen_video_id:
            self._mark_used(chosen_video_id)

        real_duration = self._probe_duration(output_path) or pexels_duration
        real_duration = min(real_duration, cfg.SHORTS_MAX_DURATION)

        logger.info("Video saved: %s (%.2fs)", output_path, real_duration)
        return output_path, real_duration, video_description

    # ── SEGMENT DOWNLOAD ──────────────────────────────────────────────────────

    def download_segments(self, topic: str, script: str, n_segments: int = 3) -> List[str]:
        """Download n unique video clips to use as timeline segments."""
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

    # ── Legacy compat ─────────────────────────────────────────────────────────

    def download(self, topic: str, script: str = None, output_path: str = cfg.VIDEO_RAW_PATH) -> str:
        path, _, _ = self.download_space_video(topic, output_path)
        return path

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _search_pexels(self, query: str) -> Optional[dict]:
        """Search Pexels — no orientation filter so landscape clips are included."""
        # Ensure 'space' appears somewhere in the query for Pexels relevance
        if "space" not in query.lower() and "astronomy" not in query.lower():
            query = f"{query} space"
        params = {
            "query": query,
            "per_page": 30,
            # No orientation param — accept both landscape and portrait
        }
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
            logger.error("Pexels API error for query '%s': %s", query, e)
            return None

    def _extract_text_fields(self, video: dict) -> str:
        """
        Combine all available text from a Pexels video object into one string.
        Checks alt, page URL slug, and user name — all normalised to lowercase.
        The URL slug is the MOST RELIABLE field (e.g. /video/galaxy-nebula-12345/).
        """
        alt = (video.get("alt") or "").lower()
        url = (video.get("url") or "").lower()
        # Extract the slug part of the URL (between /video/ and the trailing id)
        url_slug = re.sub(r"https?://[^/]+/video/", "", url)
        url_slug = re.sub(r"-\d+/?$", "", url_slug)   # strip trailing numeric id
        user_name = (video.get("user", {}).get("name") or "").lower()
        return f"{alt} {url_slug} {user_name}"

    def _is_space_related(self, combined: str) -> bool:
        """Return True if at least one space keyword is present."""
        for kw in SPACE_POSITIVE_KEYWORDS:
            if kw in combined:
                return True
        return False

    def _has_negative_keyword(self, combined: str) -> bool:
        """Return True if any negative (non-space) keyword is present."""
        for kw in NEGATIVE_KEYWORDS:
            if kw in combined:
                return True
        return False

    def _pick_best_video(
        self, videos: list, require_space: bool = True
    ) -> Optional[Tuple[str, float, str, int]]:
        """
        Score and select the best video.
        Returns (url, duration, description, video_id) or None.

        Scoring:
          +3  portrait orientation (height > width) — preferred for Shorts
          +2  HD quality
          +1  duration 20-59s (ideal for Shorts)
          -1  duration < 15s or > 70s
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

            # Build combined text for content detection
            combined = self._extract_text_fields(video)

            # Always reject if negative keywords present
            if self._has_negative_keyword(combined):
                logger.debug(
                    "Rejecting video id=%s (negative keyword) combined='%s'",
                    video_id, combined[:80],
                )
                continue

            # Space filter
            if require_space and not self._is_space_related(combined):
                logger.debug(
                    "Rejecting non-space video id=%s combined='%s'",
                    video_id, combined[:80],
                )
                continue

            score = 0
            duration = float(video.get("duration", 0))
            w = video.get("width", 0)
            h = video.get("height", 0)

            # Duration scoring
            if 20 <= duration <= 59:
                score += 1
            elif duration < MIN_DURATION or duration > MAX_DURATION:
                score -= 1

            # Orientation — portrait preferred (+3), landscape still accepted
            if h > w:
                score += 3

            # Find best quality file
            best_url = None
            best_quality = None
            for quality in PREFERRED_QUALITY:
                for vf in video.get("video_files", []):
                    if vf.get("quality") == quality and best_url is None:
                        best_url = vf["link"]
                        best_quality = quality

            if best_quality and best_quality.startswith("hd"):
                score += 2
            elif best_quality == "sd":
                score += 1

            # Fallback: first available file
            if best_url is None and video.get("video_files"):
                best_url = video["video_files"][0]["link"]

            if best_url:
                alt = (video.get("alt") or "").strip()
                user = video.get("user", {}).get("name", "")
                description = f"{alt} (by {user})".strip(" ()") if alt else f"Space video by {user}"
                scored.append((score, duration, best_url, description, video_id))

        if not scored:
            return None

        # Sort desc by score, then randomly pick from top N to vary output
        scored.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored[: min(TOP_N_RANDOM, len(scored))]
        chosen = random.choice(top_candidates)
        best_score, best_duration, best_url, best_desc, best_id = chosen
        logger.info(
            "Video selected: id=%s score=%d dur=%.1fs desc='%s'",
            best_id, best_score, best_duration, best_desc[:60],
        )
        return best_url, best_duration, best_desc, best_id

    def _probe_duration(self, path: str) -> Optional[float]:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1",
                 path],
                capture_output=True, text=True, timeout=15,
            )
            return float(result.stdout.strip())
        except Exception as e:
            logger.warning("ffprobe failed: %s", e)
            return None

    def _stream_download(self, url: str, output_path: str) -> None:
        logger.info("Downloading video from Pexels...")
        with requests.get(url, stream=True, timeout=90) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        logger.info("Video saved to %s", output_path)

    # ── Used-ID persistence ───────────────────────────────────────────────────

    def _load_used_ids(self) -> set:
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
        str_id = str(video_id)
        self._used_ids.add(str_id)
        try:
            os.makedirs(os.path.dirname(USED_IDS_PATH), exist_ok=True)
            current_list = list(self._used_ids)
            if len(current_list) > MAX_USED_IDS:
                current_list = current_list[-MAX_USED_IDS:]
                self._used_ids = set(current_list)
            with open(USED_IDS_PATH, "w", encoding="utf-8") as f:
                json.dump({"used_ids": current_list}, f, indent=2)
            logger.info("Marked video id=%s as used (%d total).", str_id, len(current_list))
        except Exception as e:
            logger.warning("Could not save used_video_ids.json: %s", e)