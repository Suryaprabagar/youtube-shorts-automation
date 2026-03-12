"""
modules/series_manager.py
Manages the various YouTube Shorts series and their episodic counters.

Creates and reads from a local JSON file (data/series_state.json) to persist
the latest generated episode for each series across runs.
"""

import os
import json
import logging
import random

import config as cfg

logger = logging.getLogger(__name__)

SERIES_STATE_FILE = os.path.join(cfg.OUTPUT_DIR, "..", "data", "series_state.json")

# Define our core series
AVAILABLE_SERIES = [
    {"id": "tech_secrets", "title": "Tech Secrets", "weight": 1.0},
    {"id": "ai_facts", "title": "AI Facts", "weight": 1.0},
    {"id": "psychology_hacks", "title": "Psychology Hacks", "weight": 1.0},
    {"id": "space_mysteries", "title": "Space Mysteries", "weight": 0.8},
    {"id": "history_uncovered", "title": "History Uncovered", "weight": 0.5},
]

class SeriesManager:
    """Manages progression of episodic content series."""

    def __init__(self):
        self.state_file = SERIES_STATE_FILE
        self.state = self._load_state()

    def _load_state(self) -> dict:
        """Load series state from disk or initialize if missing."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read {self.state_file}: {e}. Reinitializing.")

        # Initialize default state
        default_state = {s["id"]: 0 for s in AVAILABLE_SERIES}
        # Add metadata for tracking
        default_state["_last_series"] = None
        self._save_state(default_state)
        return default_state

    def _save_state(self, state: dict):
        """Persist state to disk."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save series state to {self.state_file}: {e}")

    def select_next_series(self, bias_series_id: str = None) -> dict:
        """
        Selects the next series to produce an episode for.
        Can be biased towards a specific series (e.g., from analytics).
        
        Returns:
            dict: Contains 'id', 'title', and the 'episode_number' for the new short.
        """
        # Pick series
        if bias_series_id and any(s["id"] == bias_series_id for s in AVAILABLE_SERIES):
            selected = next(s for s in AVAILABLE_SERIES if s["id"] == bias_series_id)
        else:
            # Prevent picking the exact same series twice in a row if possible
            last_series = self.state.get("_last_series")
            choices = [s for s in AVAILABLE_SERIES if s["id"] != last_series]
            if not choices:
                choices = AVAILABLE_SERIES
                
            weights = [s["weight"] for s in choices]
            selected = random.choices(choices, weights=weights, k=1)[0]

        series_id = selected["id"]
        
        # Ensure series exists in state (in case of new series added to code)
        if series_id not in self.state:
            self.state[series_id] = 0
            
        # Increment episode
        next_episode = self.state[series_id] + 1
        
        logger.info(f"Selected Series: '{selected['title']}' - Episode #{next_episode}")
        
        return {
            "id": series_id,
            "title": selected["title"],
            "episode_number": next_episode
        }

    def commit_episode(self, series_id: str, new_episode_number: int):
        """
        Call this after successful upload to persist the incremented episode.
        This prevents skipping episodes if the pipeline fails midway.
        """
        self.state[series_id] = new_episode_number
        self.state["_last_series"] = series_id
        self._save_state(self.state)
        logger.info(f"Committed Series State: {series_id} is now at episode {new_episode_number}")

