"""
modules/script_generator.py
Generates a YouTube Shorts voiceover script using OpenRouter LLM.

SYNC FIX:
  generate(topic, video_duration) now accepts the actual video duration in seconds.
  The LLM is instructed to write a script whose spoken length matches the video,
  eliminating the audio/video desync that occurred when the script was written blindly.

VIDEO-AWARE:
  generate() also accepts an optional video_description so the LLM can reference
  the actual footage being shown, making the narration more relevant.

Word-rate reference (gTTS default speed ~140 wpm):
  30s → ~70 words | 40s → ~93 words | 50s → ~117 words | 59s → ~137 words
"""

import logging
import re
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config as cfg

logger = logging.getLogger(__name__)

# gTTS speaks at roughly 140 words per minute at normal speed
GTTS_WPM = 140

SYSTEM_PROMPT = (
    "You are a professional YouTube Shorts scriptwriter specializing in Space and Astronomy. "
    "You write engaging, fast-paced voiceover scripts that hook viewers instantly "
    "and deliver mind-blowing facts about the universe. "
    "Keep scripts simple, conversational, and free of filler words. "
    "You always hit the exact word count requested — never more, never less."
)

USER_PROMPT_TEMPLATE = """Write a YouTube Shorts voiceover script about this space topic:

Topic: {topic}
{video_context}
⚠️ CRITICAL LENGTH REQUIREMENT:
The background video is exactly {duration:.0f} seconds long.
You MUST write a script of EXACTLY {target_words} words (±5 words).
At 140 words per minute (gTTS speed), {target_words} words = {duration:.0f} seconds of speech.
If the script is too long or too short, the audio will not match the video.

Script structure (do NOT label these sections):
1. HOOK — one curiosity-driven opening sentence
2. EXPLANATION — simple context about the topic
3. SURPRISING FACT — one mind-blowing detail
4. CLOSING HOOK — a question or statement that makes them want more

Rules:
- Output ONLY the raw spoken words — no labels, headers, stage directions, or markdown.
- No [MUSIC], [CUT], (pause), or any production notes.
- Do NOT start with "Here is" or "Script:".

Example (for a 30-second / ~70-word script):
"What happens exactly at the edge of a black hole? It is called the event horizon, the point of no return. But here is the wild part — if you fell in, time would slow so much that you would watch the entire future of the universe unfold before crossing it. Would you take that risk?"
"""

VIDEO_CONTEXT_TEMPLATE = (
    "Video context: The background footage shows '{description}'. "
    "Reference what is visible in the video where relevant.\n"
)


class ScriptGenerator:
    """Generates a voiceover script sized to match a specific video duration."""

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

    def generate(
        self,
        topic: str,
        video_duration: float = 45.0,
        video_description: str = "",
    ) -> str:
        """
        Generate a script sized to match the given video duration.

        Args:
            topic:             The space topic to write about.
            video_duration:    Actual video duration in seconds (from VideoDownloader).
                               The script word count is calculated from this so that
                               gTTS audio length ≈ video length.
            video_description: Optional description of the chosen Pexels footage.
                               Included in the LLM prompt so the script is relevant
                               to what is visually shown.

        Returns:
            Clean voiceover script string.
        """
        # Calculate target word count from duration
        target_words = int((video_duration / 60.0) * GTTS_WPM)
        # Keep within sensible Shorts bounds
        target_words = max(60, min(target_words, 140))
        logger.info(
            "Generating script for %.1fs video → target: %d words", video_duration, target_words
        )

        models_to_try = [cfg.OPENROUTER_MODEL] + cfg.OPENROUTER_FALLBACK_MODELS

        for model in models_to_try:
            try:
                logger.info("Trying model: %s", model)
                script = self._call_model(
                    topic, video_duration, target_words, model, video_description
                )
                actual_words = len(script.split())
                logger.info(
                    "Script generated with '%s' — %d words (target %d), estimated audio: %.1fs",
                    model,
                    actual_words,
                    target_words,
                    (actual_words / GTTS_WPM) * 60,
                )
                return script
            except Exception as e:
                err = str(e)
                if (
                    any(code in err for code in ["400", "402", "404", "429"])
                    or "No endpoints" in err
                    or "rate-limit" in err.lower()
                    or "empty or none" in err.lower()
                    or "NoneType" in err
                ):
                    logger.warning("Model '%s' skipped (%s), trying next...", model, err[:80])
                    continue
                logger.error("Model '%s' failed unexpectedly: %s", model, err)

        logger.warning("All models failed — using fallback script.")
        return self._fallback_script(topic, target_words)

    def _call_model(
        self,
        topic: str,
        duration: float,
        target_words: int,
        model: str,
        video_description: str = "",
    ) -> str:
        video_context = ""
        if video_description:
            safe_desc = video_description[:200]  # cap length
            video_context = VIDEO_CONTEXT_TEMPLATE.format(description=safe_desc)

        prompt = USER_PROMPT_TEMPLATE.format(
            topic=topic,
            duration=duration,
            target_words=target_words,
            video_context=video_context,
        )
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.8,
        )
        raw = response.choices[0].message.content
        if not raw:
            raise ValueError("Model returned empty or None content")
        return self._clean_script(raw.strip())

    @staticmethod
    def _clean_script(text: str) -> str:
        """Strip LLM preamble, markdown, and production notes."""
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#") or re.match(r"^\[.*\]$", stripped):
                continue
            if stripped.lower().startswith(("here is", "here's", "script:", "voiceover:")):
                continue
            cleaned.append(stripped)
        return " ".join(cleaned)

    def _fallback_script(self, topic: str, target_words: int) -> str:
        """Emergency fallback — builds a script roughly at the target word count."""
        base = (
            f"Here is something incredible about {topic}. "
            "For years scientists thought they understood it, but recent discoveries changed everything. "
            "The deeper you look, the more mysterious the universe becomes. "
            "What we know now is just the beginning of a much bigger story. "
            "Space is not empty — it is full of secrets waiting to be found. "
            "Every answer leads to ten more questions. "
            "Subscribe if you want to keep exploring the cosmos with us."
        )
        words = base.split()
        while len(words) < target_words:
            words += base.split()
        return " ".join(words[:target_words])