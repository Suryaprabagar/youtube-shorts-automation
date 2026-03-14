"""
modules/keyword_extractor.py
Extracts 2-3 relevant keywords from a topic or script for video searching.
Lightweight and rule-based for GitHub Actions compatibility.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Common space-related keywords to prioritize
SPACE_KEYWORDS = {
    "black hole", "galaxy", "nebula", "astronaut", "planet", "stars", 
    "cosmos", "universe", "solar system", "moon", "sun", "supernova", 
    "telescope", "milky way", "mars", "jupiter", "saturn", "earth",
    "space exploration", "rocket", "nasa", "spacex", "astronomy",
    "physics", "science", "nebulae", "constellation", "meteor",
    "asteroid", "comet", "alien", "ufo", "wormhole", "time travel"
}

# Stop words to exclude (basic set)
STOP_WORDS = {
    "the", "and", "a", "of", "to", "is", "in", "it", "you", "that", "he",
    "was", "for", "on", "are", "with", "as", "I", "his", "they", "be",
    "at", "one", "have", "this", "from", "or", "had", "by", "hot", "but",
    "some", "what", "there", "we", "can", "out", "other", "were", "all",
    "your", "when", "up", "use", "word", "how", "said", "an", "each",
    "she", "which", "do", "their", "time", "if", "will", "way", "about",
    "many", "then", "them", "write", "would", "like", "so", "these",
    "her", "long", "make", "thing", "see", "him", "two", "has", "look",
    "more", "day", "could", "go", "come", "did", "my", "sound", "no",
    "most", "number", "who", "over", "know", "water", "than", "call",
    "first", "people", "may", "down", "side", "been", "now", "find",
    "happens", "inside", "if", "into", "why", "red"
}

class KeywordExtractor:
    """Extracts keywords from text for video search queries."""

    def __init__(self):
        pass

    def extract(self, topic: str, script: str = "") -> list[str]:
        """
        Extract 2-3 keywords from topic and script.
        Priority:
        1. Multi-word space terms from SPACE_KEYWORDS
        2. Single-word space terms from SPACE_KEYWORDS
        3. Frequent non-stop words
        """
        text = f"{topic} {script}".lower()
        # Remove non-alphanumeric characters but keep spaces
        text = re.sub(r'[^a-z0-9\s]', '', text)
        
        extracted = []
        
        # 1. Check for multi-word space terms first (e.g., "black hole")
        for term in SPACE_KEYWORDS:
            if " " in term and term in text:
                extracted.append(term)
        
        # 2. Check for single-word space terms
        words = text.split()
        for word in words:
            if word in SPACE_KEYWORDS and word not in extracted:
                extracted.append(word)
        
        # 3. If we still need more, pick frequent non-stop words
        if len(extracted) < 3:
            # Simple frequency count for non-stop words
            counts = {}
            for word in words:
                if len(word) > 3 and word not in STOP_WORDS and word not in extracted:
                    counts[word] = counts.get(word, 0) + 1
            
            # Sort by frequency and take the top ones
            sorted_words = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            for word, count in sorted_words:
                if word not in extracted:
                    extracted.append(word)
                if len(extracted) >= 5: # Get a few extra candidates
                    break

        # Limit to 3 most relevant for the primary return, but others can be used as fallbacks
        results = extracted[:3]
        
        # If still empty, use a generic fallback
        if not results:
            results = ["space", "universe", "science"]
            
        logger.info(f"Extracted keywords: {results}")
        return results

if __name__ == "__main__":
    # Quick test
    extractor = KeywordExtractor()
    print(extractor.extract("What happens inside a black hole?", "The center of a black hole is a singularity..."))
    print(extractor.extract("Why is Mars red?", "Mars is often called the Red Planet because of iron oxide..."))
