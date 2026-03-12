"""
modules/youtube_analytics.py
Fetches analytics from previous YouTube uploads to figure out which topics perform best.
Saves local state to bias future generations.
"""

import os
import json
import logging
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config as cfg

logger = logging.getLogger(__name__)

ANALYTICS_STATE_FILE = os.path.join(cfg.OUTPUT_DIR, "..", "data", "analytics_state.json")


class YouTubeAnalytics:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._service = None
        self.state_file = ANALYTICS_STATE_FILE

    def _build_service(self):
        """Create authenticated YouTube API service."""
        credentials = Credentials(
            token=None,
            refresh_token=self._refresh_token,
            token_uri=cfg.YOUTUBE_TOKEN_URI,
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        credentials.refresh(Request())
        self._service = build(
            cfg.YOUTUBE_API_SERVICE_NAME,
            cfg.YOUTUBE_API_VERSION,
            credentials=credentials,
            cache_discovery=False,
        )

    def _load_historical_data(self) -> dict:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"video_stats": {}, "best_series_id": None}

    def _save_historical_data(self, data: dict):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save analytics: {e}")

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        reraise=False, # We don't want analytics failure to crash the pipeline
    )
    def update_analytics(self) -> str | None:
        """
        Fetches latest video stats, updates local DB, and returns the ID of the 
        best performing series (if determinable) to guide the next generation.
        """
        if not self._refresh_token:
            logger.warning("No refresh token provided. Skipping analytics fetch.")
            return None

        if self._service is None:
            self._build_service()

        logger.info("Fetching recent videos and analytics from YouTube...")

        try:
            # 1. Get channel's uploads playlist ID
            channels_response = self._service.channels().list(
                part="contentDetails",
                mine=True
            ).execute()

            if not channels_response.get("items"):
                logger.warning("No channel found for authenticated user.")
                return None

            uploads_playlist_id = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

            # 2. Get recent 10 videos
            playlistitems_response = self._service.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=10
            ).execute()

            video_ids = []
            video_series_map = {} # Maps videoId to series_id (parsed from description if possible)
            
            for item in playlistitems_response.get("items", []):
                snippet = item["snippet"]
                v_id = snippet["resourceId"]["videoId"]
                desc = snippet.get("description", "").lower()
                title = snippet.get("title", "").lower()
                
                video_ids.append(v_id)
                
                # Super rough heuristic to see which series this matches
                from modules.series_manager import AVAILABLE_SERIES
                for s in AVAILABLE_SERIES:
                    if s["title"].lower() in title or s["title"].lower() in desc:
                        video_series_map[v_id] = s["id"]
                        break

            if not video_ids:
                return None

            # 3. Get stats for these videos
            stats_response = self._service.videos().list(
                part="statistics",
                id=",".join(video_ids)
            ).execute()

            data = self._load_historical_data()
            
            series_performance = {} # total views per series
            
            for item in stats_response.get("items", []):
                v_id = item["id"]
                stats = item.get("statistics", {})
                views = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                
                data["video_stats"][v_id] = {
                    "views": views,
                    "likes": likes
                }
                
                s_id = video_series_map.get(v_id)
                if s_id:
                    if s_id not in series_performance:
                        series_performance[s_id] = 0
                    series_performance[s_id] += views

            best_series = None
            if series_performance:
                best_series = max(series_performance, key=series_performance.get)
                data["best_series_id"] = best_series
                logger.info(f"Analytics found best performing series so far: {best_series}")

            self._save_historical_data(data)
            return best_series

        except Exception as e:
            logger.warning(f"Failed to fetch YouTube analytics: {e}")
            return None
