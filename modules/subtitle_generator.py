import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

class SubtitleGenerator:
    """
    Generates time-synced subtitle chunks from a text script without
    the need for Speech-to-Text inference (like Whisper).
    """

    def generate(self, script_text: str, duration: float) -> List[Tuple[float, float, str]]:
        """
        Splits the text into 4-6 word chunks and estimates timestamps based
        on standard reading speed (or evenly distributing by word count).

        Args:
            script_text: The full text of the voiceover.
            duration: The total duration of the audio clip in seconds.

        Returns:
            A list of tuples: (start_time, end_time, text_chunk)
        """
        logger.info("Generating subtitles from script heuristically (No STT)")
        
        # Clean and split the script into words
        words = script_text.split()
        if not words:
            return []

        # Target 4 words per chunk
        chunk_size = 4
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk_text = " ".join(words[i:i + chunk_size])
            chunks.append(chunk_text)

        # Distribute time based on character count per chunk
        total_chars = sum(len(c) for c in chunks)
        if total_chars == 0:
            return []

        subtitles = []
        current_time = 0.0

        for chunk in chunks:
            # Proportion of time this chunk takes
            char_ratio = len(chunk) / total_chars
            chunk_duration = duration * char_ratio
            
            start_time = current_time
            end_time = start_time + chunk_duration
            
            subtitles.append((start_time, end_time, chunk))
            current_time = end_time

        logger.info(f"Generated {len(subtitles)} subtitle chunks.")
        return subtitles
