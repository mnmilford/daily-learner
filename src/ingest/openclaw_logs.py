"""Parse OpenClaw JSONL log files into Activity objects."""

import json
import os
import re

from src.config import resolve_date_path
from src.ingest import Activity

# Patterns to filter out noise
_NOISE_PATTERNS = [
    r"nextAt",
    r"delayMs",
    r"image.*resize",
    r"networkInterfaces",
    r"SIGTERM",
    r"heartbeat.*check",
    r"Gateway service check",
    r"systemctl.*is-enabled",
    r"compaction.*skipped",
    r"Memory usage",
]

_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)

# Interesting log patterns
_KEEP_PATTERNS = [
    r"error",
    r"failed",
    r"tool.*call",
    r"model.*change",
    r"session.*save",
    r"session.*create",
    r"warning",
    r"skill",
    r"provider",
    r"config.*update",
    r"webhook",
    r"api",
]

_KEEP_RE = re.compile("|".join(_KEEP_PATTERNS), re.IGNORECASE)


def ingest_openclaw(date_str: str, config: dict) -> list[Activity]:
    """Parse OpenClaw log for the given date, filtering noise."""
    log_dir = config["sources"]["openclaw_log_dir"]
    pattern = config["sources"]["openclaw_log_pattern"]
    filename = resolve_date_path(pattern, date_str)
    filepath = os.path.join(log_dir, filename)

    if not os.path.exists(filepath):
        return []

    interesting = []

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = entry.get("0", "")
            meta = entry.get("_meta", {})
            level = meta.get("logLevelName", "")

            # Skip noise
            if _NOISE_RE.search(msg):
                continue

            # Keep errors/warnings and interesting entries
            if level in ("ERROR", "WARN") or _KEEP_RE.search(msg):
                interesting.append({
                    "msg": msg[:500],  # Truncate long messages
                    "level": level,
                    "time": entry.get("time", ""),
                })

    if not interesting:
        return []

    # Group by theme — deduplicate similar messages
    seen_prefixes = set()
    unique = []
    for item in interesting:
        prefix = item["msg"][:80]
        if prefix not in seen_prefixes:
            seen_prefixes.add(prefix)
            unique.append(item)

    # Cap at 30 most interesting entries
    unique = unique[:30]

    # Create a single activity summarizing the log
    content_lines = []
    for item in unique:
        level_tag = f"[{item['level']}]" if item['level'] else ""
        content_lines.append(f"{level_tag} {item['msg']}")

    return [Activity(
        source="openclaw_log",
        title=f"OpenClaw log activity ({date_str})",
        content='\n'.join(content_lines),
        tags=["devops", "automation"],
        timestamp=date_str,
    )]
