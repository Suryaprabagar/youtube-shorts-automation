"""
modules/topic_generator.py
Generates a fresh YouTube Shorts topic for each automation run.

Strategy:
  - Maintains a large pool of evergreen topics across multiple niches.
  - Each run picks a random topic so the channel stays varied.
  - No database needed — randomness alone ensures good distribution over time.
"""

import random
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Topic pool ─────────────────────────────────────────────────────────────────
TOPIC_POOL = [
    # Psychology & Mind
    "The psychological trick that makes people trust you instantly",
    "Why your brain lies to you every single day",
    "The 3-second rule that changes how you make decisions",
    "What happens to your brain when you stop scrolling social media",
    "The surprising reason you can't remember your dreams",
    "How to rewire your brain for success in 21 days",
    "The psychology behind why people procrastinate",
    "Why talking to yourself out loud actually makes you smarter",

    # Science & Space
    "A mind-blowing fact about black holes nobody talks about",
    "The strangest planet in our solar system explained in 60 seconds",
    "How a single bacterium can end a civilization",
    "Why the ocean floor is still more mysterious than outer space",
    "The quantum physics trick that powers your smartphone",
    "What would happen if you fell into a black hole",
    "The scientific reason time feels faster as you get older",
    "How scientists discovered water on the moon",

    # History & Civilization
    "The ancient technology that took centuries to rediscover",
    "The strangest law from ancient Rome that still makes sense",
    "How one small decision changed the entire course of World War II",
    "The forgotten civilization that was more advanced than ancient Egypt",
    "Why the Library of Alexandria was not actually burned down once",
    "The medieval invention that accidentally saved millions of lives",
    "The real story behind one of history's greatest mysteries",
    "A historical coincidence so strange it sounds impossible",

    # Personal Growth & Productivity
    "The 2-minute rule that will end your procrastination forever",
    "Why waking up at 5 AM does not actually make you more productive",
    "The one journaling habit that successful people swear by",
    "How to learn any skill twice as fast using science",
    "The counterintuitive reason rest makes you more productive",
    "Why the best students study less but score higher",
    "One small habit that compounds into massive results over a year",
    "How to stop overthinking and make better decisions instantly",

    # Technology & AI
    "The AI feature hiding in your phone that most people ignore",
    "How ChatGPT actually works explained in 60 seconds",
    "The technology that will make smartphones obsolete",
    "Why the internet almost did not exist",
    "The clever algorithm that Netflix uses to keep you watching",
    "A simple cybersecurity trick that protects all your passwords",
    "How self-driving cars see the world around them",
    "The sneaky way apps drain your phone battery faster",

    # Health & Fitness
    "The one exercise that burns more calories than running",
    "Why drinking water first thing in the morning changes everything",
    "The sleep position that actually damages your spine over time",
    "What fasting for 16 hours does to your body explained simply",
    "The superfood in your kitchen that fights inflammation",
    "Why stress makes you eat more and how to stop it",
    "The breathing technique Navy SEALs use to stay calm under pressure",
    "How to fix your posture in just 5 minutes a day",

    # Money & Finance
    "The compound interest trick that turns 100 dollars into millions",
    "Why most lottery winners go broke within 5 years",
    "The simple budgeting rule that changed how millionaires save money",
    "One money mistake you are probably making right now",
    "How credit card companies make money even when you pay on time",
    "The investing habit you can start with just 10 dollars per week",
    "Why the richest people in history always had this one thing in common",
    "A financial mindset shift that separates the wealthy from everyone else",

    # Life Hacks & Everyday
    "The kitchen trick that keeps vegetables fresh for twice as long",
    "Why cold showers are scientifically proven to boost your mood",
    "The clever Google search trick most people never learn",
    "How to memorize anything in under 10 minutes using a proven method",
    "The reason you should never charge your phone to 100 percent",
    "A simple trick to fall asleep faster backed by neuroscience",
    "How to read 52 books a year without reading more than 20 minutes a day",
    "The airport trick that gets you through security twice as fast",
]


class TopicGenerator:
    """Selects a random topic from the curated pool each run."""

    def __init__(self):
        self._pool = TOPIC_POOL.copy()

    def generate(self) -> str:
        """Return a randomly selected topic string."""
        # Seed with current hour so cron runs within the same hour are stable
        # but different cron windows get different topics
        seed = int(datetime.utcnow().strftime("%Y%m%d%H"))
        random.seed(seed)
        topic = random.choice(self._pool)
        logger.info("Selected topic: %s", topic)
        return topic
