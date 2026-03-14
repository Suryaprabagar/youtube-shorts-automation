import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)

class SubtitleGenerator:
    """
    Generates time-synced subtitle chunks from a text script without
    the need for Speech-to-Text inference (like Whisper).
    """

    def __init__(self, wpm: int = 150):
        self.wpm = wpm  # Words per minute heuristic

    def generate(self, script_text: str, duration: float) -> List[Tuple[float, float, str]]:
        """
        Splits the text into short phrases (2-4 words) and estimates timestamps.

        Args:
            script_text: The full text of the voiceover.
            duration: The total duration of the audio clip in seconds.

        Returns:
            A list of tuples: (start_time, end_time, text_chunk)
        """
        logger.info(f"Generating subtitles using {self.wpm} WPM heuristic for {duration:.1f}s audio.")
        
        # Clean text: remove excessive whitespace and newlines
        clean_text = re.sub(r'\s+', ' ', script_text.strip())
        words = clean_text.split()
        
        if not words:
            return []

        # 1. Chunk words into phrases of 2-4 words
        chunks = []
        i = 0
        while i < len(words):
            # Randomly pick 2-4 words or until we hit the end
            import random
            chunk_size = random.randint(2, 4)
            chunk_words = words[i:i + chunk_size]
            chunks.append(" ".join(chunk_words))
            i += chunk_size

        # 2. Distribute time based on word count per chunk
        total_words = len(words)
        current_time = 0.0
        subtitles = []

        for chunk in chunks:
            chunk_word_count = len(chunk.split())
            # Proportion of total words in this chunk
            word_ratio = chunk_word_count / total_words
            chunk_duration = duration * word_ratio
            
            start_time = current_time
            end_time = min(start_time + chunk_duration, duration)
            
            subtitles.append((start_time, end_time, chunk))
            current_time = end_time

        # Ensure last chunk reaches exact end if slight rounding error
        if subtitles:
            last_start, _, last_text = subtitles[-1]
            subtitles[-1] = (last_start, duration, last_text)

        logger.info(f"Generated {len(subtitles)} short subtitle phrases.")
        return subtitles
