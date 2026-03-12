"""
modules/youtube_uploader.py
Uploads the final Short to YouTube using the YouTube Data API v3.

Authentication: OAuth 2.0 Refresh Token flow.
The user generates a refresh token ONCE locally (see README.md) and stores
it as a GitHub Secret. This module exchanges the refresh token for an
access token on every run — no browser interaction needed in CI.
"""

import logging
import os
import time
import json
import socket
import requests as http_requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Optional

import config as cfg

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_UPLOAD_CHUNK_SIZE = 1024 * 1024 * 5    # 5 MB resumable chunks


class YouTubeUploader:
    """Authenticates via OAuth Refresh Token and uploads a Short to YouTube."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ):
        if not all([client_id, client_secret, refresh_token]):
            raise ValueError(
                "YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN "
                "are all required. See README.md → 'YouTube OAuth Setup'."
            )
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._service = None

    def _build_service(self):
        """Create authenticated YouTube API service using refresh token."""
        logger.info("Authenticating with YouTube API via OAuth refresh token...")

        credentials = Credentials(
            token=None,
            refresh_token=self._refresh_token,
            token_uri=cfg.YOUTUBE_TOKEN_URI,
            client_id=self._client_id,
            client_secret=self._client_secret,
            scopes=SCOPES,
        )

        # This call exchanges the refresh token for a fresh access token
        credentials.refresh(Request())
        logger.info("OAuth token refreshed successfully.")

        self._service = build(
            cfg.YOUTUBE_API_SERVICE_NAME,
            cfg.YOUTUBE_API_VERSION,
            credentials=credentials,
            cache_discovery=False,
        )

    @retry(
        retry=retry_if_exception_type((HttpError, socket.error, IOError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _execute_upload(self, request) -> str:
        """Executes the resumable upload request with retry logic."""
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info(f"Upload progress: {progress}%")
        
        video_id = response.get("id")
        return video_id

    def upload(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list,
        category_id: str = "22",
        privacy_status: str = "public",
    ) -> str:
        """
        Upload a video to YouTube.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if self._service is None:
            self._build_service()

        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        logger.info("Uploading '%s' (%.1f MB) to YouTube...", video_path, file_size_mb)

        # Ensure #Shorts is in the title or description for Shorts classification
        if "#Shorts" not in title and "#Shorts" not in description:
            description = "#Shorts\n\n" + description

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags,
                "categoryId": category_id,
                "defaultLanguage": "en",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            chunksize=YOUTUBE_UPLOAD_CHUNK_SIZE,
            resumable=True,
        )

        request = self._service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        video_id = self._execute_upload(request)
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("✅ Upload successful! Video URL: %s", video_url)
        return video_id
