"""Extract learnable topics from activities using LLM."""

import logging

from src.extract import Topic
from src.llm import LLMClient

log = logging.getLogger("daily-learner.extract")

DOMAINS = [
    "api", "architecture", "ml-fundamentals", "devops", "security",
    "data", "llm-patterns", "automation", "networking", "other",
]

_EXTRACT_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "title": {"type": "STRING"},
            "domain": {"type": "STRING", "enum": DOMAINS},
            "summary": {"type": "STRING"},
            "source_hint": {"type": "STRING"},
            "is_bonus": {"type": "BOOLEAN"},
            "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["id", "title", "domain", "summary", "source_hint", "is_bonus"],
    },
}


def extract_topics(
    activities: list,
    llm: LLMClient,
    config: dict,
    existing_topic_ids: list[str] | None = None,
) -> list[Topic]:
    """Use LLM to identify learnable topics from daily activities."""

    if not activities:
        log.warning("No activities to extract topics from")
        return []

    # Build activity summary for the prompt
    activity_text = ""
    for i, act in enumerate(activities, 1):
        activity_text += f"\n--- Activity {i} [{act.source}]: {act.title} ---\n"
        activity_text += act.content[:1500] + "\n"

    topics_per_day = config.get("pipeline", {}).get("topics_per_day", 7)
    existing_ids = existing_topic_ids or []

    prompt = f"""Analyze these daily activities from a technical AI/infrastructure hobbyist and extract learnable concepts.

ACTIVITIES:
{activity_text}

INSTRUCTIONS:
1. Identify {topics_per_day - 2} to {topics_per_day} distinct, learnable technical concepts from these activities.
2. For each concept, create a clear title, categorize into a domain, and write a 2-3 sentence summary explaining the concept.
3. Add 1-2 bonus related topics that weren't directly in the activities but would be valuable to learn alongside them. Mark these with is_bonus: true.
4. Use lowercase-hyphenated IDs (e.g., "systemd-drop-in-overrides", "gemini-structured-output").
5. Focus on concepts that are practical and hands-on — things a developer would benefit from deeply understanding.
6. The source_hint should briefly note which activity surfaced this topic.

EXISTING TOPIC IDS TO AVOID (already learned):
{', '.join(existing_ids[-50:]) if existing_ids else 'none'}

Prioritize: API design, LLM tool patterns, DevOps automation, system architecture, networking, security practices."""

    result = llm.generate(prompt, schema=_EXTRACT_SCHEMA)

    topics = []
    for item in result:
        topics.append(Topic(
            id=item["id"],
            title=item["title"],
            domain=item["domain"],
            summary=item["summary"],
            source_hint=item["source_hint"],
            is_bonus=item.get("is_bonus", False),
            tags=item.get("tags", []),
        ))

    log.info(f"Extracted {len(topics)} topics ({sum(1 for t in topics if t.is_bonus)} bonus)")
    return topics
