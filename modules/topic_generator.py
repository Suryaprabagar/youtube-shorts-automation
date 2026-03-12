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
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    logger.warning("pytrends is not installed. Trending topics will be disabled.")
    PYTRENDS_AVAILABLE = False

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
    """Selects a random topic from the curated pool or fetches a trending one."""

    def __init__(self):
        self._pool = TOPIC_POOL.copy()
        if PYTRENDS_AVAILABLE:
            # We use a longer timeout and fewer retries
            self._pytrends = TrendReq(hl='en-US', tz=360, timeout=(10,25))
        else:
            self._pytrends = None

    def _get_trending_topic(self) -> str | None:
        """Attempt to fetch a trending topic from Google Trends related to our niches."""
        if not self._pytrends:
            return None
            
        try:
            logger.info("Fetching real-time trending topics from Google Trends...")
            # categories: all=all, b=business, e=entertainment, m=health/sci/tech, t=sci/tech
            # Let's fetch tech/sci/health related daily trends if possible
            realtime_df = self._pytrends.trending_searches(pn='united_states')
            
            if not realtime_df.empty:
                trends = realtime_df[0].tolist()
                
                # Filter out obvious junk if needed, or just pick a random one
                selected_trend = random.choice(trends[:10])
                logger.info(f"Using trending topic keyword: {selected_trend}")
                return f"The untold truth about {selected_trend}"
                
        except Exception as e:
            logger.warning(f"Failed to fetch trending topics: {e}")
            
        return None

    def generate(self, series_data: dict = None) -> str:
        """
        Return a topic string.
        If series_data is provided, format it as a series title.
        """
        seed = int(datetime.utcnow().strftime("%Y%m%d%H"))
        random.seed(seed)
        
        base_topic = None
        
        # 1. 30% chance to try for a trending topic (so we don't spam trends constantly)
        if random.random() < 0.30:
            base_topic = self._get_trending_topic()
            
        # 2. Fallback to our curated pool
        if not base_topic:
            base_topic = random.choice(self._pool)
            
        # 3. Format with Series Info if available
        if series_data:
            series_title = series_data.get("title", "Deep Dive")
            ep_num = series_data.get("episode_number", 1)
            final_topic = f"{series_title} #{ep_num}: {base_topic}"
        else:
            final_topic = base_topic

        logger.info("Final selected topic: %s", final_topic)
        return final_topic
