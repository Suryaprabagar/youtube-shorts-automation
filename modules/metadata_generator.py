"""
modules/metadata_generator.py
Generates YouTube video metadata (title, description, tags) using OpenRouter LLM.

Ensures all metadata fits within YouTube's character limits.
"""

import json
import logging
import re
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config as cfg

logger = logging.getLogger(__name__)

# YouTube character limits
TITLE_MAX_CHARS = 100
DESCRIPTION_MAX_CHARS = 5000
TAGS_MAX_TOTAL_CHARS = 500

METADATA_PROMPT = """Generate YouTube Shorts metadata for a video about this topic:

Topic: {topic}
Script excerpt: {script_excerpt}

Return ONLY valid JSON in exactly this format, no other text:
{{
  "title": "An engaging title under 70 characters with relevant emoji",
  "description": "A 3-5 sentence description. Mention the key insight. Add 5-8 relevant hashtags at the end including #Shorts.",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10"]
}}

Rules:
- Title: max 70 characters, must include one emoji, be click-worthy
- Description: engaging, SEO-friendly, end with hashtags
- Tags: 10 single/two-word tags most relevant to the topic, no spaces within a tag
"""


class MetadataGenerator:
    """Generates title, description, and tags for a YouTube Short."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for metadata generation.")
        self._client = OpenAI(
            api_key=api_key,
            base_url=cfg.OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://github.com/youtube-shorts-automation",
                "X-Title": "YouTube Shorts Automation",
            },
        )

    def generate(self, topic: str, script: str) -> dict:
        """Try primary model then fallbacks. Falls back to hardcoded metadata if all fail."""
        script_excerpt = script[:300].strip()
        models_to_try = [cfg.OPENROUTER_MODEL] + cfg.OPENROUTER_FALLBACK_MODELS
        for model in models_to_try:
            try:
                logger.info("Generating metadata with model: %s", model)
                response = self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": METADATA_PROMPT.format(
                        topic=topic, script_excerpt=script_excerpt)}],
                    max_tokens=500,
                    temperature=0.7,
                )
                raw_content = response.choices[0].message.content
                if not raw_content:
                    raise ValueError("Model returned empty or None content")
                raw = raw_content.strip()
                metadata = self._parse_and_validate(raw, topic)
                logger.info("Metadata generated — title: '%s'", metadata["title"])
                return metadata
            except Exception as e:
                err = str(e)
                if any(code in err for code in ["400", "402", "404", "429"]) or "No endpoints" in err or "rate-limit" in err.lower() or "empty or none" in err.lower():
                    logger.warning("Model '%s' skipped (%s), trying next...", model, err[:80])
                    continue
                raise
        logger.warning("All LLM models failed for metadata — using fallback.")
        return self._fallback_metadata(topic)

    def _parse_and_validate(self, raw: str, topic: str) -> dict:
        """Parse LLM JSON response and enforce YouTube character limits."""
        # Extract JSON block (handle markdown code fences)
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            logger.warning("Could not parse JSON from LLM response. Using fallback metadata.")
            return self._fallback_metadata(topic)

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            logger.warning("JSON decode error. Using fallback metadata.")
            return self._fallback_metadata(topic)

        # Ensure required keys exist
        title = str(data.get("title", topic))[:TITLE_MAX_CHARS]
        description = str(data.get("description", f"Watch this Short about {topic}. #Shorts"))
        tags = data.get("tags", [])

        # Ensure #Shorts is in description
        if "#Shorts" not in description and "#shorts" not in description:
            description += "\n\n#Shorts #YouTubeShorts"

        # Trim description
        description = description[:DESCRIPTION_MAX_CHARS]

        # Validate and trim tags
        if not isinstance(tags, list):
            tags = [topic.split()[0]]
        tags = [str(t).replace(" ", "").replace("#", "") for t in tags if t]
        # Trim tags to fit within total character limit
        total_chars = 0
        valid_tags = []
        for tag in tags:
            if total_chars + len(tag) + 1 <= TAGS_MAX_TOTAL_CHARS:
                valid_tags.append(tag)
                total_chars += len(tag) + 1
            else:
                break

        return {
            "title": title,
            "description": description,
            "tags": valid_tags,
        }

    @staticmethod
    def _fallback_metadata(topic: str) -> dict:
        """Return safe default metadata if LLM fails."""
        short_topic = topic[:60]
        return {
            "title": f"🎯 {short_topic}"[:TITLE_MAX_CHARS],
            "description": (
                f"Did you know? {topic}\n\n"
                "Watch this YouTube Short to learn something amazing in under 60 seconds!\n\n"
                "#Shorts #YouTubeShorts #Facts #Learning #Knowledge"
            ),
            "tags": ["facts", "shorts", "learning", "knowledge", "tips",
                     "interesting", "science", "mindblowing", "education", "did-you-know"],
        }
