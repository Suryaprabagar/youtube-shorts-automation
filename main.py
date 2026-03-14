"""
main.py — YouTube Shorts Automation Orchestrator

Full pipeline:
  1. Generate topic
  2. Generate script (OpenRouter LLM)
  3. Generate voiceover (gTTS)
  4. Download background video (Pexels)
  5. Edit + combine into final MP4 (MoviePy / FFmpeg)
  6. Generate metadata (title / description / tags)
  7. Upload to YouTube (OAuth 2.0)

Run locally:   python main.py
Run in CI:     Triggered automatically by GitHub Actions cron
"""

import logging
import sys
import traceback

from config import Config
from modules.topic_generator import TopicGenerator
from modules.script_generator import ScriptGenerator
from modules.voice_generator import VoiceGenerator
from modules.video_downloader import VideoDownloader
from modules.video_editor import VideoEditor
from modules.metadata_generator import MetadataGenerator
from modules.youtube_uploader import YouTubeUploader
from modules.youtube_analytics import YouTubeAnalytics
from modules.keyword_extractor import KeywordExtractor

# ── Root logger ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


def run_pipeline(cfg: Config) -> None:
    """Execute the full YouTube Shorts generation and upload pipeline."""

    logger.info("=" * 60)
    logger.info("🚀 Starting YouTube Shorts automation pipeline")
    logger.info("=" * 60)

    # ── Step 0: Analytics & Category Management ──────────────────────────────────
    logger.info("\n📊 STEP 0/7 — Analyzing data & selecting category...")
    
    # 0.1 Category Rotation Logic
    categories = ["space", "animals", "science", "technology", "psychology"]
    
    # Try to grab the GitHub Actions run number. If running locally, default to a random choice or file.
    import os
    run_number_str = os.environ.get("GITHUB_RUN_NUMBER")
    if run_number_str and run_number_str.isdigit():
        run_number = int(run_number_str)
        category_index = run_number % len(categories)
        selected_category = categories[category_index]
        logger.info(f"GitHub Run Number {run_number} detected. Selected Category: {selected_category}")
    else:
        import random
        selected_category = random.choice(categories)
        logger.info(f"Local run detected. Randomly selected Category: {selected_category}")

    # 0.2 Analytics (Optional bias factor we can log)
    analytics = YouTubeAnalytics(
        client_id=cfg.youtube_client_id,
        client_secret=cfg.youtube_client_secret,
        refresh_token=cfg.youtube_refresh_token,
    )
    best_series_id = analytics.update_analytics()
    if best_series_id:
        logger.info(f"Analytics suggests '{best_series_id}' performs best, but we are honoring category rotation.")

    # ── Step 1: Generate Topic ─────────────────────────────────────────────────
    logger.info("\n📌 STEP 1/7 — Generating topic...")
    topic_gen = TopicGenerator()
    topic = topic_gen.generate(category=selected_category)
    logger.info("Topic: %s", topic)

    # ── Step 1.5: Extract Keywords ──────────────────────────────────────────────
    logger.info("\n🔑 STEP 1.5/7 — Extracting keywords...")
    keyword_extractor = KeywordExtractor()
    keywords = keyword_extractor.extract(topic)
    logger.info("Keywords: %s", keywords)

    # ── Step 2: Generate Script ────────────────────────────────────────────────
    logger.info("\n✍️  STEP 2/7 — Generating script...")
    script_gen = ScriptGenerator(api_key=cfg.openrouter_api_key)
    script = script_gen.generate(topic)
    logger.info("Script preview: %s...", script[:100])

    # ── Step 3: Generate Voiceover ─────────────────────────────────────────────
    logger.info("\n🎙️  STEP 3/7 — Generating voiceover...")
    voice_gen = VoiceGenerator(language=cfg.tts_language, slow=cfg.tts_slow)
    voice_path = voice_gen.generate(script)
    logger.info("Voiceover saved: %s", voice_path)

    # ── Step 4: Download Background Video ─────────────────────────────────────
    logger.info("\n🎬 STEP 4/7 — Downloading background video segments from Pexels...")
    video_dl = VideoDownloader(api_key=cfg.pexels_api_key)
    # Use multi-segment download for better variety (Bug 4 fix)
    video_paths = video_dl.download_segments(topic=topic, script=script, n_segments=3)
    logger.info(f"Downloaded {len(video_paths)} background segments.")

    # ── Step 5: Edit + Combine into Final Short ────────────────────────────────
    logger.info("\n🎞️  STEP 5/7 — Editing video (crop → overlay → merge audio)...")
    editor = VideoEditor()
    final_video_path = editor.edit(
        video_path=video_paths[0], # Fallback for FFmpeg or single clip
        audio_path=voice_path,
        script=script,
        topic=topic,
        video_paths=video_paths,   # Multi-segment list
    )
    logger.info("Final video saved: %s", final_video_path)

    # ── Step 6: Generate Metadata ──────────────────────────────────────────────
    logger.info("\n📝 STEP 6/7 — Generating title, description, and tags...")
    meta_gen = MetadataGenerator(api_key=cfg.openrouter_api_key)
    metadata = meta_gen.generate(topic=topic, script=script)
    logger.info("Title: %s", metadata["title"])
    logger.info("Tags: %s", metadata["tags"])

    # ── Step 7: Upload to YouTube ──────────────────────────────────────────────
    logger.info("\n📤 STEP 7/7 — Uploading to YouTube...")
    uploader = YouTubeUploader(
        client_id=cfg.youtube_client_id,
        client_secret=cfg.youtube_client_secret,
        refresh_token=cfg.youtube_refresh_token,
    )
    video_id = uploader.upload(
        video_path=final_video_path,
        title=metadata["title"],
        description=metadata["description"],
        tags=metadata["tags"],
        category_id=cfg.video_category_id,
        privacy_status=cfg.video_privacy,
    )

    logger.info("\n" + "=" * 60)
    logger.info("✅ Pipeline complete!")
    logger.info("🎉 YouTube Short published: https://www.youtube.com/watch?v=%s", video_id)
    logger.info("=" * 60)


def main():
    """Entry point — load config, run pipeline, handle top-level errors."""
    try:
        cfg = Config()
        run_pipeline(cfg)
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.error("❌ Pipeline failed with an unhandled error!")
        logger.error("Error: %s", str(e))
        logger.debug(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
