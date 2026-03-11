"""Parse OpenClaw agent sessions for the target date."""

import json
import os
from datetime import datetime, timedelta, timezone

import yaml

from src.ingest import Activity

# Central Time offset (handle CDT/CST)
_CT_OFFSET_CDT = timezone(timedelta(hours=-5))
_CT_OFFSET_CST = timezone(timedelta(hours=-6))


def _parse_ts(ts) -> datetime | None:
    """Parse a timestamp (ISO string or epoch ms) to datetime."""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _date_matches(dt: datetime, date_str: str) -> bool:
    """Check if a datetime falls on the target date in CT."""
    # Use CDT (March-November) as default; close enough for filtering
    ct = dt.astimezone(_CT_OFFSET_CDT)
    return ct.strftime("%Y-%m-%d") == date_str


def _find_sessions_for_date(date_str: str, config: dict) -> list[str]:
    """Use sessions.json index to find session files active on the target date."""
    index_path = config["sources"]["session_index"]

    if not os.path.exists(index_path):
        return []

    with open(index_path) as f:
        index = json.load(f)

    session_files = []
    for key, meta in index.items():
        if isinstance(meta, dict):
            updated = meta.get("updatedAt")
            if updated:
                dt = _parse_ts(updated)
                if dt and _date_matches(dt, date_str):
                    sf = meta.get("sessionFile", "")
                    if sf and os.path.exists(sf):
                        session_files.append(sf)

    return session_files


def ingest_sessions(date_str: str, config: dict) -> list[Activity]:
    """Parse agent sessions active on the target date."""
    # Also scan all session files in the directory for broader coverage
    session_dir = config["sources"]["session_dir"]
    session_files = set(_find_sessions_for_date(date_str, config))

    # Scan directory for any session files modified on the target date
    if os.path.isdir(session_dir):
        for fname in os.listdir(session_dir):
            if fname.endswith(".jsonl"):
                fpath = os.path.join(session_dir, fname)
                session_files.add(fpath)

    activities = []

    for sf in session_files:
        messages = _extract_messages(sf, date_str)
        if messages:
            # Group into conversation turns
            turns = _group_turns(messages)
            if turns:
                content = '\n\n'.join(turns[:20])  # Cap at 20 turns
                activities.append(Activity(
                    source="session",
                    title=f"Agent conversation ({date_str})",
                    content=content,
                    tags=["llm-patterns", "automation"],
                    timestamp=date_str,
                ))

    return activities


def _extract_messages(filepath: str, date_str: str) -> list[dict]:
    """Extract message entries matching the target date."""
    messages = []

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "message":
                continue

            ts_str = entry.get("timestamp")
            if not ts_str:
                continue

            dt = _parse_ts(ts_str)
            if not dt or not _date_matches(dt, date_str):
                continue

            msg = entry.get("message", {})
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Handle content that's a list of parts
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = '\n'.join(text_parts)

            if content and role in ("user", "assistant"):
                messages.append({"role": role, "content": content[:1000]})

    return messages


def _group_turns(messages: list[dict]) -> list[str]:
    """Group messages into readable conversation turns."""
    turns = []
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"].strip()
        # Skip system/heartbeat noise
        if "HEARTBEAT" in content[:50] or "Read HEARTBEAT" in content[:50]:
            continue
        turns.append(f"[{role}]: {content[:500]}")
    return turns
