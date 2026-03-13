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
        Splits the text into sentences and estimates timestamps based
        on standard reading speed (or evenly distributing by word count).

        Args:
            script_text: The full text of the voiceover.
            duration: The total duration of the audio clip in seconds.

        Returns:
            A list of tuples: (start_time, end_time, text_chunk)
        """
        logger.info("Generating subtitles from script heuristically (No STT)")
        
        # Split by typical sentence ending punctuation
        import re
        sentences = re.split(r'(?<=[.!?]) +', script_text.strip())
        
        if not sentences or (len(sentences) == 1 and not sentences[0]):
            return []

        # Filter out empty strings
        sentences = [s for s in sentences if s]

        # Distribute time based on character count per sentence
        total_chars = sum(len(s) for s in sentences)
        if total_chars == 0:
            return []

        subtitles = []
        current_time = 0.0

        for sentence in sentences:
            # Proportion of time this sentence takes
            char_ratio = len(sentence) / total_chars
            sentence_duration = duration * char_ratio
            
            start_time = current_time
            # Prevent overlap and ensure it doesn't exceed total duration
            end_time = min(start_time + sentence_duration, duration)
            
            subtitles.append((start_time, end_time, sentence))
            current_time = end_time

        logger.info(f"Generated {len(subtitles)} subtitle chunks.")
        return subtitles
