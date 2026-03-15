"""
modules/subtitle_generator.py
Generates time-synced subtitle chunks from a text script without
the need for Speech-to-Text inference (like Whisper).

Also provides `to_ffmpeg_drawtext()` to burn subtitles via FFmpeg
`drawtext` filter — no ImageMagick needed.
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Characters that must be escaped in FFmpeg drawtext expressions
_FFMPEG_ESCAPE = str.maketrans({
    "'": "\u2019",    # replace ASCII apostrophe with typographic one
    ":": "\\:",
    "\\": "\\\\",
    "%": "\\%",
})


class SubtitleGenerator:
    """
    Generates time-synced subtitle chunks from a text script.
    Uses character-weighted timing (no Whisper / STT needed).
    """

    FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    def __init__(self, wpm: int = 150):
        self.wpm = wpm  # words per minute heuristic

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate(self, script_text: str, duration: float) -> List[Tuple[float, float, str]]:
        """
        Split the text into phrases and estimate timestamps.

        Args:
            script_text: Full voiceover text.
            duration:    Total audio duration in seconds.

        Returns:
            List of (start_time, end_time, text_chunk) tuples.
        """
        logger.info(
            "Generating subtitles using character-weighted timing for %.1fs audio.", duration
        )

        clean_text = re.sub(r"\s+", " ", script_text.strip())
        if not clean_text:
            return []

        chunks = self._split_into_chunks(clean_text)
        return self._assign_timestamps(chunks, duration)

    def to_ffmpeg_drawtext(
        self,
        subtitles: List[Tuple[float, float, str]],
        video_width: int = 1080,
        video_height: int = 1920,
        font_size: int = 60,
    ) -> str:
        """
        Convert subtitle list to an FFmpeg ``drawtext`` filter string.

        Each phrase is rendered only during its time window using
        ``enable='between(t,start,end)'``.  The result can be used
        directly as the value passed to ``-vf`` in an FFmpeg command.

        Args:
            subtitles:    Output of generate().
            video_width:  Target video width  (default 1080).
            video_height: Target video height (default 1920).
            font_size:    Font size in pixels (default 60).

        Returns:
            A single FFmpeg filter-graph string, e.g.
            "drawtext=...,drawtext=..."
        """
        if not subtitles:
            return ""

        # y position: 80% down the frame (bottom area for Shorts)
        y_pos = int(video_height * 0.80)

        parts = []
        for start, end, text in subtitles:
            safe_text = text.strip().translate(_FFMPEG_ESCAPE)
            # Split long lines: wrap at ~30 chars
            wrapped = self._wrap_text(safe_text, max_chars=30)

            entry = (
                f"drawtext="
                f"fontfile={self.FONT_PATH}:"
                f"text='{wrapped}':"
                f"fontsize={font_size}:"
                f"fontcolor=white:"
                f"bordercolor=black:"
                f"borderw=3:"
                f"x=(w-text_w)/2:"
                f"y={y_pos}:"
                f"enable='between(t,{start:.3f},{end:.3f})'"
            )
            parts.append(entry)

        logger.info("Built FFmpeg drawtext filter with %d subtitle entries.", len(parts))
        return ",".join(parts)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _split_into_chunks(self, clean_text: str) -> List[str]:
        """Split text on sentence boundaries, then break long ones."""
        sentences = re.split(r"(?<=[.!?])\s+", clean_text)
        chunks: List[str] = []
        for s in sentences:
            if not s.strip():
                continue
            words = s.split()
            if len(words) > 6:
                for i in range(0, len(words), 4):
                    chunk = " ".join(words[i : i + 4])
                    if chunk:
                        chunks.append(chunk)
            else:
                chunks.append(s.strip())
        return chunks

    def _assign_timestamps(
        self, chunks: List[str], duration: float
    ) -> List[Tuple[float, float, str]]:
        """Distribute duration across chunks proportional to character count."""
        total_chars = sum(len(c.replace(" ", "")) for c in chunks)
        if total_chars == 0:
            return []

        current_time = 0.0
        subtitles: List[Tuple[float, float, str]] = []

        for chunk in chunks:
            chunk_chars = len(chunk.replace(" ", ""))
            char_ratio = chunk_chars / total_chars
            chunk_duration = duration * char_ratio

            start_time = current_time
            end_time = min(start_time + chunk_duration, duration)

            if end_time > start_time:
                subtitles.append((start_time, end_time, chunk))
                current_time = end_time

        # Ensure last chunk terminates exactly at duration
        if subtitles:
            last_start, _, last_text = subtitles[-1]
            subtitles[-1] = (last_start, duration, last_text)

        logger.info("Generated %d synced subtitle phrases.", len(subtitles))
        return subtitles

    @staticmethod
    def _wrap_text(text: str, max_chars: int = 30) -> str:
        """Wrap text at word boundaries; use FFmpeg line-break escape."""
        words = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            if current and len(current) + 1 + len(word) > max_chars:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(current)
        return r"\n".join(lines)
