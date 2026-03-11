"""Parse daily memory markdown files into Activity objects."""

import os
import re
from pathlib import Path

from src.config import resolve_date_path
from src.ingest import Activity

# Keyword → tag mapping for auto-tagging
_TAG_KEYWORDS = {
    "api": ["api", "endpoint", "rest", "graphql", "webhook"],
    "llm-patterns": ["llm", "prompt", "model", "gemini", "claude", "gpt", "token", "context"],
    "devops": ["systemd", "service", "docker", "deploy", "cron", "nginx", "systemctl"],
    "security": ["auth", "token", "credential", "ssh", "firewall", "ssl", "tls"],
    "architecture": ["architecture", "pattern", "design", "refactor", "module"],
    "automation": ["automation", "script", "pipeline", "cron", "scheduled"],
    "networking": ["network", "dns", "ip", "port", "proxy", "gateway"],
    "data": ["database", "sqlite", "json", "yaml", "csv", "schema"],
    "ml-fundamentals": ["training", "inference", "embedding", "vector", "fine-tune"],
}


def _auto_tag(text: str) -> list[str]:
    """Extract tags based on keyword matching."""
    text_lower = text.lower()
    tags = []
    for tag, keywords in _TAG_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            tags.append(tag)
    return tags


def ingest_memory(date_str: str, config: dict) -> list[Activity]:
    """Parse a memory markdown file for the given date."""
    memory_dir = config["sources"]["memory_dir"]
    pattern = config["sources"]["memory_pattern"]
    filename = resolve_date_path(pattern, date_str)
    filepath = os.path.join(memory_dir, filename)

    if not os.path.exists(filepath):
        return []

    text = Path(filepath).read_text()
    activities = []

    # Split on ## headers
    sections = re.split(r'^## ', text, flags=re.MULTILINE)

    for section in sections[1:]:  # Skip content before first ##
        lines = section.strip().split('\n')
        title = lines[0].strip()
        body = '\n'.join(lines[1:]).strip()

        if not body:
            continue

        # Extract bullet points as content
        bullets = [line.strip() for line in body.split('\n') if line.strip().startswith('-')]
        content = '\n'.join(bullets) if bullets else body

        tags = _auto_tag(f"{title} {content}")

        activities.append(Activity(
            source="memory",
            title=title,
            content=content,
            tags=tags,
            timestamp=date_str,
        ))

    return activities
