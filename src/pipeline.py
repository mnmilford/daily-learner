"""Nightly pipeline: ingest → extract → generate → save session → update tracker."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import load_config, get_data_dir
from src.ingest import ingest_all
from src.extract.extractor import extract_topics
from src.generate.generator import generate_content
from src.generate import SessionContent
from src.llm import LLMClient
from src.tracker.tracker import Tracker

log = logging.getLogger("daily-learner.pipeline")

_CT = timezone(timedelta(hours=-5))  # CDT; close enough for date boundaries


def _setup_logging(config: dict):
    """Configure file logging for the pipeline."""
    data_dir = get_data_dir(config)
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "pipeline.log"

    handler = logging.FileHandler(log_file)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    ))

    root = logging.getLogger("daily-learner")
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Also log to console
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(console)


def get_yesterday_ct() -> str:
    """Get yesterday's date in CT as YYYY-MM-DD."""
    now_ct = datetime.now(_CT)
    yesterday = now_ct - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def run_pipeline(date_str: str | None = None):
    """Run the full pipeline for a given date (default: yesterday CT)."""
    config = load_config()
    _setup_logging(config)

    if not date_str:
        date_str = get_yesterday_ct()

    log.info(f"Pipeline starting for {date_str}")

    # Step 1: Ingest
    log.info("Ingesting activities...")
    activities = ingest_all(date_str, config)
    log.info(f"Ingested {len(activities)} activities")

    if not activities:
        log.warning(f"No activities found for {date_str}, skipping pipeline")
        return None

    # Step 2: Extract topics
    log.info("Extracting topics...")
    llm = LLMClient(config)
    tracker = Tracker(config)
    existing_ids = tracker.get_all_topic_ids()

    topics = extract_topics(activities, llm, config, existing_ids)
    log.info(f"Extracted {len(topics)} topics")

    if not topics:
        log.warning("No topics extracted, skipping content generation")
        return None

    # Step 3: Generate content
    log.info("Generating learning content...")
    flashcards, questions, challenges = generate_content(topics, llm, config)

    # Step 4: Build and save session
    session = SessionContent(
        date=date_str,
        topics=[{
            "id": t.id,
            "title": t.title,
            "domain": t.domain,
            "summary": t.summary,
            "source_hint": t.source_hint,
            "is_bonus": t.is_bonus,
            "tags": t.tags,
        } for t in topics],
        flashcards=flashcards,
        questions=questions,
        challenges=challenges,
    )

    session_dir = get_data_dir(config) / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / f"{date_str}.json"

    with open(session_path, "w") as f:
        json.dump(session.to_dict(), f, indent=2)

    log.info(f"Session saved to {session_path}")

    # Step 5: Register topics in tracker
    tracker.register_topics([t.id for t in topics], date_str)

    log.info(f"Pipeline complete. {llm.usage_summary()}")
    return str(session_path)


if __name__ == "__main__":
    import sys
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_pipeline(date_arg)
