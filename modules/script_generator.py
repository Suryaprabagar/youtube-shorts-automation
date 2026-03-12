"""
modules/script_generator.py
Generates a 45-55 second YouTube Shorts voiceover script using OpenRouter LLM.

Uses the OpenAI-compatible SDK pointed at OpenRouter's endpoint.
Free-tier model: meta-llama/llama-3-8b-instruct:free
"""

import logging
import re
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config as cfg

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a professional YouTube Shorts scriptwriter. "
    "You write engaging, fast-paced voiceover scripts that hook viewers "
    "in the first 3 seconds and deliver one compelling insight. "
    "Keep scripts punchy, conversational, and free of filler words."
)

USER_PROMPT_TEMPLATE = """Write a YouTube Shorts voiceover script on this topic:

Topic: {topic}

Requirements:
- Target length: STRICTLY MAXIMUM 60 WORDS.
- Must start with a VERY strong verbal hook in the first sentence to grab attention.
- Use curiosity-based storytelling. Build tension or reveal a surprising fact.
- Tone: fast-paced, engaging, conversational, and energetic.
- Do NOT include scene directions, [MUSIC], [CUT], or any production notes.
- Output ONLY the voiceover text, nothing else.
"""


class ScriptGenerator:
    """Calls OpenRouter to generate a voiceover script for a given topic."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for script generation.")
        self._client = OpenAI(
            api_key=api_key,
            base_url=cfg.OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://github.com/youtube-shorts-automation",
                "X-Title": "YouTube Shorts Automation",
            },
        )

    def generate(self, topic: str) -> str:
        """Try primary model then fallbacks, return first successful script."""
        models_to_try = [cfg.OPENROUTER_MODEL] + cfg.OPENROUTER_FALLBACK_MODELS
        for model in models_to_try:
            try:
                logger.info("Trying model: %s", model)
                return self._call_model(topic, model)
            except Exception as e:
                err = str(e)
                if any(code in err for code in ["400", "402", "404", "429"]) or "No endpoints" in err or "rate-limit" in err.lower() or "empty or none" in err.lower():
                    logger.warning("Model '%s' skipped (%s), trying next...", model, err[:80])
                    continue
                logger.error("Model '%s' failed unexpectedly: %s", model, err)
                
        logger.error("All OpenRouter models failed or were unavailable.")
        logger.warning("Using hardcoded fallback script to prevent pipeline crash.")
        return self._get_fallback_script(topic)

    def _get_fallback_script(self, topic: str) -> str:
        """In case LLM API completely fails, return a generic working script."""
        fallbacks = [
            f"Here is a crazy secret about {topic}. Most people go their whole lives without realizing the truth. But scientists recently discovered something that changes everything we thought we knew. If you look closely at the details, a hidden pattern emerges. Knowing this will completely shift your perspective. Subscribe for more mind-blowing facts!",
            f"Did you know the untold truth behind {topic}? It sounds impossible, but historians and researchers have confirmed it. What started as a simple rumor actually turned out to be one of the greatest mysteries of our time. The evidence is right in front of us, but we barely notice it. Hit subscribe if you love uncovering wild secrets!",
            f"Stop scrolling. What I'm about to tell you about {topic} will blow your mind. For years, experts kept this hidden from the public. But the truth always comes out. Once you understand how this works, you'll never look at the world the same way again. Drop a like if you learned something new today!"
        ]
        import random
        return random.choice(fallbacks)

    def _call_model(self, topic: str, model: str) -> str:
        """Call one model and return the cleaned script."""
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(topic=topic)},
            ],
            max_tokens=400,
            temperature=0.8,
        )
        raw_content = response.choices[0].message.content
        if not raw_content:
            raise ValueError("Model returned empty or None content")
        raw_script = raw_content.strip()
        script = self._clean_script(raw_script)
        word_count = len(script.split())
        logger.info("Script generated with '%s' — %d words.", model, word_count)
        return script

    @staticmethod
    def _clean_script(text: str) -> str:
        """Remove unwanted LLM preamble/postamble and production notes."""
        # Remove lines that look like metadata or production notes
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip lines with markdown headers, brackets, or production directions
            if stripped.startswith("#") or re.match(r"^\[.*\]$", stripped):
                continue
            if stripped.lower().startswith(("here is", "here's", "script:", "voiceover:")):
                continue
            cleaned.append(stripped)
        return " ".join(cleaned)
