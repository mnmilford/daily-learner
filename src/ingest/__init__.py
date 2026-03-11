"""Ingest module — parses raw data sources into Activity objects."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Activity:
    """A single learnable activity extracted from a data source."""
    source: str          # "memory", "openclaw_log", "session"
    title: str           # Short description
    content: str         # Full text content
    tags: list[str] = field(default_factory=list)
    timestamp: Optional[str] = None


def ingest_all(date_str: str, config: dict) -> list[Activity]:
    """Run all ingestors for the given date and return combined activities."""
    from src.ingest.memory_logs import ingest_memory
    from src.ingest.openclaw_logs import ingest_openclaw
    from src.ingest.sessions import ingest_sessions

    activities = []
    activities.extend(ingest_memory(date_str, config))
    activities.extend(ingest_openclaw(date_str, config))
    activities.extend(ingest_sessions(date_str, config))
    return activities
