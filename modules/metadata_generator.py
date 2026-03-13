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
TITLE_MAX_CHARS = 70  # stricter limit for better click-through rate
DESCRIPTION_MAX_CHARS = 5000
TAGS_MAX_TOTAL_CHARS = 500

METADATA_PROMPT_TEMPLATE = """Generate metadata for a Space and Astronomy YouTube Short.

Topic: {topic}
Script: {script}

Respond ONLY with raw JSON in this exact structure:
{{
  "titles": [
    "5 options for a curiosity-driven title under 60 characters total, ending with 🤯 #Shorts"
  ],
  "description": "2-3 sentences max summarizing the space fact. Include 3 relevant keywords.",
  "tags": ["5", "to", "8", "single", "word", "tags"]
}}
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

    @retry(
        retry=retry_if_exception_type((Exception)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=False
    )
    def _call_model(self, topic: str, script: str, model: str) -> dict:
        """Internal method to call the LLM for metadata generation."""
        script_excerpt = script[:300].strip()
        logger.info("Generating metadata with model: %s", model)
        response = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": METADATA_PROMPT_TEMPLATE.format(
                topic=topic, script=script_excerpt)}],
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

    def generate(self, topic: str, script: str) -> dict:
        """Fetch metadata, handle errors, returning a structured dict."""
        
        models_to_try = [cfg.OPENROUTER_MODEL] + cfg.OPENROUTER_FALLBACK_MODELS
        
        try:
            for model in models_to_try:
                try:
                    logger.info("Trying model '%s' for metadata...", model)
                    return self._call_model(topic, script, model)
                except Exception as e:
                    err = str(e)
                    if any(code in err for code in ["400", "402", "404", "429"]) or "No endpoints" in err:
                        logger.warning("Model '%s' skipped (%s)", model, err[:80])
                        continue
                    logger.error("Metadata generator failed on model '%s': %s", model, err)
                    
            logger.error("All OpenRouter models failed for metadata.")
            raise RuntimeError("API failed")
        except Exception:
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
        # Pick the best title out of the 5.
        titles = data.get("titles", [])
        if isinstance(titles, list) and len(titles) > 0:
            import random
            best_title = str(random.choice(titles[:3]))
            # If it's too long, truncate it nicely.
            if len(best_title) > TITLE_MAX_CHARS:
                 best_title = best_title[:TITLE_MAX_CHARS - 10].rsplit(' ', 1)[0] + ' #Shorts'
        else:
            best_title = str(data.get("title", topic))[:TITLE_MAX_CHARS]

        description = str(data.get("description", f"Watch this amazing space fact about {topic}. #Shorts"))
        tags = data.get("tags", [])

        # Ensure space requirements are met in description
        required_hashtags = ["#shorts", "#space", "#astronomy", "#universe"]
        for hashtag in required_hashtags:
            if hashtag.lower() not in description.lower():
                description += f" {hashtag}"

        # Trim description
        description = description[:DESCRIPTION_MAX_CHARS]

        # Validate and trim tags
        if not isinstance(tags, list):
            tags = [topic.split()[0]]
        tags = [str(t).replace(" ", "").replace("#", "") for t in tags if t]
        
        # Ensure mandatory tags are in the final tags array
        mandatory_tags = ["shorts", "space", "astronomy", "universe"]
        for tag in mandatory_tags:
            if tag not in [t.lower() for t in tags]:
                tags.insert(0, tag)

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
            "title": best_title,
            "description": description,
            "tags": valid_tags,
        }

    @staticmethod
    def _fallback_metadata(topic: str) -> dict:
        """Return safe default metadata if LLM fails."""
        fallback_topic = topic[:30] if topic else "Amazing Fact"
        return {
            "title": f"The Truth About {fallback_topic} #Shorts",
            "description": f"Did you know this about {topic}? Like and subscribe for more amazing daily facts! #shorts #viral #facts",
            "tags": ["shorts", "viral", "facts", "interesting", "trending"]
        }
