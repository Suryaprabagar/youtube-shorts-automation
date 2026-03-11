"""
modules/video_editor.py
Assembles the final YouTube Short by combining background video + voiceover.

Pipeline:
  1. Load background video → resize/crop to 1080×1920 (9:16 portrait)
  2. Load audio track from voiceover MP3
  3. Loop or trim the video to match audio duration (capped at 59s)
  4. Overlay a semi-transparent title card with the topic text
  5. Export final MP4 using H.264 + AAC at 30fps

Primary engine: MoviePy
Fallback engine: FFmpeg subprocess (if MoviePy fails)
"""

import logging
import os
import subprocess
import textwrap
from typing import Optional

import config as cfg

logger = logging.getLogger(__name__)


class VideoEditor:
    """Combines video + audio and exports a YouTube Shorts-ready MP4."""

    def __init__(self):
        self.width = cfg.SHORTS_WIDTH     # 1080
        self.height = cfg.SHORTS_HEIGHT   # 1920
        self.fps = cfg.SHORTS_FPS         # 30
        self.max_duration = cfg.SHORTS_MAX_DURATION   # 59

    def edit(
        self,
        video_path: str = cfg.VIDEO_RAW_PATH,
        audio_path: str = cfg.VOICE_PATH,
        output_path: str = cfg.FINAL_VIDEO_PATH,
        topic: str = "",
    ) -> str:
        """
        Create the final Short MP4.

        Args:
            video_path: Path to background video.
            audio_path: Path to voiceover MP3.
            output_path: Destination for final MP4.
            topic: Topic text to overlay as title card.

        Returns:
            Absolute path to final video.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            return self._edit_with_moviepy(video_path, audio_path, output_path, topic)
        except Exception as e:
            logger.warning("MoviePy failed (%s). Falling back to FFmpeg.", e)
            return self._edit_with_ffmpeg(video_path, audio_path, output_path)

    # ── MoviePy path ───────────────────────────────────────────────────────────

    def _edit_with_moviepy(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        topic: str,
    ) -> str:
        from moviepy.editor import (
            VideoFileClip, AudioFileClip, CompositeVideoClip,
            TextClip, ColorClip,
        )

        logger.info("Editing video with MoviePy...")

        # Load audio and clamp duration
        audio_clip = AudioFileClip(audio_path)
        target_duration = min(audio_clip.duration, self.max_duration)

        # Load + resize + crop background video
        bg_clip = VideoFileClip(video_path, audio=False)
        bg_clip = self._resize_crop(bg_clip, target_duration)

        # Build title overlay
        layers = [bg_clip]
        if topic:
            title_layer = self._build_title_overlay(topic, target_duration)
            if title_layer:
                layers.append(title_layer)

        # Composite + attach audio
        final = CompositeVideoClip(layers, size=(self.width, self.height))
        final = final.set_audio(audio_clip.subclip(0, target_duration))
        final = final.set_duration(target_duration)

        # Export
        logger.info("Exporting final video to '%s'...", output_path)
        final.write_videofile(
            output_path,
            fps=self.fps,
            codec="libx264",
            audio_codec="aac",
            bitrate=cfg.SHORTS_VIDEO_BITRATE,
            audio_bitrate=cfg.SHORTS_AUDIO_BITRATE,
            threads=2,
            preset="ultrafast",
            verbose=False,
            logger=None,
        )

        # Cleanup clips
        for clip in [final, audio_clip, bg_clip]:
            try:
                clip.close()
            except Exception:
                pass

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info("Final video saved (%.1f MB, %.1fs).", size_mb, target_duration)
        return output_path

    def _resize_crop(self, clip, target_duration):
        """Resize and center-crop clip to 1080×1920. Loop if shorter than target."""
        from moviepy.editor import vfx

        # Loop if video is shorter than needed
        if clip.duration < target_duration:
            n_loops = int(target_duration / clip.duration) + 2
            clip = clip.loop(n_loops)

        clip = clip.subclip(0, target_duration)

        # Scale so the shortest dimension matches our target, then crop
        clip_ratio = clip.w / clip.h
        target_ratio = self.width / self.height

        if clip_ratio > target_ratio:
            # Video is wider than target → scale to height, crop width
            new_h = self.height
            new_w = int(clip.w * (self.height / clip.h))
        else:
            # Video is taller/squarer → scale to width, crop height
            new_w = self.width
            new_h = int(clip.h * (self.width / clip.w))

        clip = clip.resize((new_w, new_h))

        # Center crop
        x_center = clip.w / 2
        y_center = clip.h / 2
        clip = clip.crop(
            x_center=x_center,
            y_center=y_center,
            width=self.width,
            height=self.height,
        )
        return clip

    def _build_title_overlay(self, topic: str, duration: float) -> Optional[object]:
        """Build a centered, wrapped title card with a dark gradient background."""
        try:
            from moviepy.editor import TextClip, ColorClip, CompositeVideoClip

            # Wrap long topics
            wrapped = "\n".join(textwrap.wrap(topic, width=30))

            text_clip = TextClip(
                wrapped,
                fontsize=60,
                color="white",
                font="DejaVu-Sans-Bold",
                align="center",
                method="caption",
                size=(self.width - 80, None),
            ).set_position(("center", 0.72), relative=True).set_duration(duration)

            # Dark bar behind text for readability
            bar_height = 200
            bar = (
                ColorClip(size=(self.width, bar_height), color=(0, 0, 0))
                .set_opacity(0.55)
                .set_position(("center", 0.70), relative=True)
                .set_duration(duration)
            )

            return CompositeVideoClip([bar, text_clip], size=(self.width, self.height))
        except Exception as e:
            logger.warning("Could not render title overlay: %s", e)
            return None

    # ── FFmpeg fallback path ───────────────────────────────────────────────────

    def _edit_with_ffmpeg(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
    ) -> str:
        """
        Fallback: use FFmpeg CLI to merge video + audio and crop to 9:16.
        No text overlay in fallback mode.
        """
        logger.info("Editing video with FFmpeg fallback...")

        # First get audio duration
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        audio_dur = min(float(result.stdout.strip()), self.max_duration)

        # FFmpeg filter: scale + crop to 1080x1920, loop video, trim to audio duration
        vf = (
            f"scale=w={self.width}:h={self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",          # loop video indefinitely
            "-i", video_path,
            "-i", audio_path,
            "-vf", vf,
            "-t", str(audio_dur),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-b:v", cfg.SHORTS_VIDEO_BITRATE,
            "-c:a", "aac",
            "-b:a", cfg.SHORTS_AUDIO_BITRATE,
            "-r", str(self.fps),
            "-shortest",
            "-map", "0:v:0",
            "-map", "1:a:0",
            output_path,
        ]

        logger.info("Running FFmpeg: %s", " ".join(cmd))
        subprocess.run(cmd, check=True, capture_output=True)

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info("FFmpeg output saved: '%s' (%.1f MB).", output_path, size_mb)
        return output_path
