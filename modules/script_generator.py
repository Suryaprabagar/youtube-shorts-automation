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
- Target length: 45-55 seconds when read aloud at normal speed (~120-140 words)
- Start with a hook that grabs attention immediately (question or bold statement)
- Deliver ONE clear, interesting insight or story
- End with a memorable closing line or call-to-action
- Tone: conversational, energetic, factual
- Do NOT include scene directions, [MUSIC], [CUT], or any production notes
- Output ONLY the voiceover text, nothing else
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

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def generate(self, topic: str) -> str:
        """Generate and return a clean voiceover script string."""
        logger.info("Generating script for topic: %s", topic)

        response = self._client.chat.completions.create(
            model=cfg.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(topic=topic)},
            ],
            max_tokens=400,
            temperature=0.8,
        )

        raw_script = response.choices[0].message.content.strip()
        script = self._clean_script(raw_script)

        word_count = len(script.split())
        logger.info("Script generated — %d words.", word_count)

        if word_count < 80:
            logger.warning("Script seems short (%d words). May be under 45 seconds.", word_count)
        elif word_count > 180:
            logger.warning("Script may be too long (%d words). Trimming recommendation.", word_count)

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
