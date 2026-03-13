"""
modules/topic_generator.py
Generates a fresh YouTube Shorts topic for each automation run.

Strategy:
  - Maintains a large pool of evergreen topics across multiple niches.
  - Each run picks a random topic so the channel stays varied.
  - No database needed — randomness alone ensures good distribution over time.
"""

import json
import os
import random
import logging
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
SPACE_TOPICS_FILE = os.path.join(DATA_DIR, "space_topics.json")
TOPIC_HISTORY_FILE = os.path.join(DATA_DIR, "topic_history.json")


class TopicGenerator:
    """Selects a random space topic from the dataset, ensuring no duplicates."""

    def __init__(self):
        self._ensure_data_files()
        self._pool = self._load_json(SPACE_TOPICS_FILE, [])
        self._history = self._load_json(TOPIC_HISTORY_FILE, [])

    def _ensure_data_files(self):
        """Ensure the data directory and files exist."""
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(SPACE_TOPICS_FILE):
            # Fallback if the file was somehow deleted
            default_topics = [
                "[Space] The terrifying size of the largest known black hole, TON 618",
                "[Space] What happens if you fall into a supermassive black hole?",
                "[Space] The strangest planet in our solar system explained in 60 seconds",
                "[Space] The mind-bending scale of the observable universe",
                "[Space] The strange fact that we are all made of stardust"
            ]
            self._save_json(SPACE_TOPICS_FILE, default_topics)
            logger.warning("space_topics.json not found, created a minimal fallback.")
            
        if not os.path.exists(TOPIC_HISTORY_FILE):
            self._save_json(TOPIC_HISTORY_FILE, [])

    def _load_json(self, filepath: str, default):
        """Helper to load JSON with fallback."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Error loading %s: %s", filepath, e)
            return default

    def _save_json(self, filepath: str, data):
        """Helper to save JSON."""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to save %s: %s", filepath, e)

    def generate(self, category: str = "space") -> str:
        """
        Return a fresh space topic.
        We ignore the `category` arg from main.py since we are purely Space now.
        """
        # Find topics not yet used
        available_topics = [t for t in self._pool if t not in self._history]
        
        # If we exhausted the entire pool, reset history!
        if not available_topics:
            logger.warning("All topics used! Resetting topic history.")
            self._history = []
            available_topics = self._pool
            
        # If pool is completely empty for some reason
        if not available_topics:
            base_topic = "A terrifying discovery about black holes"
        else:
            base_topic = random.choice(available_topics)
            
        # Ensure it has the [Space] prefix if it doesn't already
        if not base_topic.startswith("[Space]"):
            final_topic = f"[Space] {base_topic}"
        else:
            final_topic = base_topic

        # Update history
        self._history.append(base_topic)
        self._save_json(TOPIC_HISTORY_FILE, self._history)

        logger.info("Final selected topic: %s", final_topic)
        return final_topic
