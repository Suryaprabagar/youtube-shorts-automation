"""
modules/voice_generator.py
Converts a script into an MP3 voiceover using gTTS (Google Text-to-Speech).

gTTS is free, requires no API key, and produces natural-sounding speech.
Output: output/voice.mp3
"""

import logging
import os
from gtts import gTTS
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

import config as cfg

logger = logging.getLogger(__name__)


class VoiceGenerator:
    """Converts a script string to an MP3 file using gTTS."""

    def __init__(self, language: str = "en", slow: bool = False):
        self.language = language
        self.slow = slow

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_fixed(3),
        reraise=True,
    )
    def generate(self, script: str, output_path: str = cfg.VOICE_PATH) -> str:
        """
        Convert script text to speech and save as MP3.

        Args:
            script: The voiceover text.
            output_path: Destination path for the MP3 file.

        Returns:
            Absolute path to the generated MP3 file.
        """
        if not script or not script.strip():
            raise ValueError("Script text is empty. Cannot generate voice.")

        logger.info("Generating voiceover with gTTS (lang=%s, slow=%s)...", self.language, self.slow)

        tts = gTTS(text=script, lang=self.language, slow=self.slow)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        tts.save(output_path)

        # Validate output
        if not os.path.exists(output_path):
            raise RuntimeError(f"gTTS did not create output file at: {output_path}")

        size_kb = os.path.getsize(output_path) / 1024
        logger.info("Voiceover saved to '%s' (%.1f KB).", output_path, size_kb)
        return output_path
