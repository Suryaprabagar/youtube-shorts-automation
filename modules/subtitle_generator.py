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
        Splits the text into phrases based on punctuation and estimates timestamps.

        Args:
            script_text: The full text of the voiceover.
            duration: The total duration of the audio clip in seconds.

        Returns:
            A list of tuples: (start_time, end_time, text_chunk)
        """
        logger.info(f"Generating subtitles using character-weighted timing for {duration:.1f}s audio.")
        
        # Clean text: remove excessive whitespace and newlines
        clean_text = re.sub(r'\s+', ' ', script_text.strip())
        
        if not clean_text:
            return []

        # 1. Split on sentence boundaries (. ? !)
        # Using regex to keep the punctuation with the preceding phrase
        sentences = re.split(r'(?<=[.!?])\s+', clean_text)
        
        chunks = []
        for s in sentences:
            if not s.strip():
                continue
            # Further split very long sentences if they lack punctuation
            if len(s.split()) > 6:
                words = s.split()
                for i in range(0, len(words), 4):
                    chunks.append(" ".join(words[i:i + 4]))
            else:
                chunks.append(s.strip())

        # 2. Distribute time based on character count per chunk
        # Character count excluding spaces gives better results for timing
        total_chars = sum(len(c.replace(" ", "")) for c in chunks)
        if total_chars == 0:
            return []

        current_time = 0.0
        subtitles = []

        for chunk in chunks:
            chunk_chars = len(chunk.replace(" ", ""))
            # Proportion of total characters in this chunk
            char_ratio = chunk_chars / total_chars
            chunk_duration = duration * char_ratio
            
            start_time = current_time
            end_time = min(start_time + chunk_duration, duration)
            
            # Avoid chunks with zero duration
            if end_time > start_time:
                subtitles.append((start_time, end_time, chunk))
                current_time = end_time

        # Ensure last chunk reaches exact end if slight rounding error
        if subtitles:
            last_start, _, last_text = subtitles[-1]
            subtitles[-1] = (last_start, duration, last_text)

        logger.info(f"Generated {len(subtitles)} synced subtitle phrases.")
        return subtitles
