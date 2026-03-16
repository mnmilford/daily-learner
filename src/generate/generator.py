"""Generate learning content (flashcards, questions, challenges) from topics."""

import logging

from src.extract import Topic
from src.generate import LearningItem
from src.llm import LLMClient
from src.learner_profile import get_level, get_persona

log = logging.getLogger("daily-learner.generate")

_CONTENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "topic_id": {"type": "STRING"},
                    "item_type": {"type": "STRING", "enum": ["flashcard", "multiple_choice", "short_answer", "challenge"]},
                    "prompt": {"type": "STRING"},
                    "answer": {"type": "STRING"},
                    "hint": {"type": "STRING"},
                    "choices": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "correct_index": {"type": "INTEGER"},
                    "rationale": {"type": "STRING"},
                    "rubric_points": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "type_label": {"type": "STRING"},
                },
                "required": ["topic_id", "item_type", "prompt", "answer"],
            },
        }
    },
    "required": ["items"],
}


def generate_content(
    topics: list[Topic],
    llm: LLMClient,
    config: dict,
) -> list[LearningItem]:
    """Generate learning content for a batch of topics."""

    if not topics:
        return []

    pipeline_cfg = config.get("pipeline", {})
    fc_per = pipeline_cfg.get("flashcards_per_topic", 2)
    mcq_per = pipeline_cfg.get("multiple_choice_per_topic", 1)
    q_per = pipeline_cfg.get("short_answer_per_topic", pipeline_cfg.get("questions_per_topic", 1))
    ch_per = pipeline_cfg.get("challenges_per_batch", 1)
    learner_cfg = config.get("learner_profile", {})
    level = get_level(learner_cfg.get("difficulty_level", config.get("learner", {}).get("default_difficulty_level", "follow-if-slowed-down")))
    persona = get_persona(learner_cfg.get("persona_id", config.get("learner", {}).get("default_persona", "lil-mike")))

    all_items = []

    # Process in batches of 3-4 topics
    batch_size = 3
    for i in range(0, len(topics), batch_size):
        batch = topics[i:i + batch_size]
        items = _generate_batch(batch, llm, fc_per, mcq_per, q_per, ch_per, level, persona)
        all_items.extend(items)

    counts: dict[str, int] = {}
    for item in all_items:
        counts[item.item_type] = counts.get(item.item_type, 0) + 1

    log.info("Generated items by type: %s", counts)
    return all_items


def _generate_batch(
    topics: list[Topic],
    llm: LLMClient,
    fc_per: int,
    mcq_per: int,
    q_per: int,
    ch_per: int,
    level: dict,
    persona: dict,
) -> list[LearningItem]:
    """Generate content for a batch of topics in a single LLM call."""

    topic_text = ""
    for t in topics:
        topic_text += f"\n- [{t.id}] {t.title} ({t.domain}): {t.summary}\n"

    prompt = f"""Generate Daily Learner content for these technical topics.

LEARNER PROFILE:
- Persona: {persona["label"]} — {persona["system_style"]}
- Difficulty level: {level["label"]}
- Difficulty guidance: {level["description"]}
- Generation guidance: {level["generation_style"]}

TOPICS:
{topic_text}

GENERATE:
- {fc_per} flashcards per topic (concise front question, detailed back answer)
- {mcq_per} multiple-choice question(s) per topic (4 answer choices, one correct answer, strong distractors, brief rationale)
- {q_per} short-answer question(s) per topic (requires 2-3 sentence response)
- {ch_per} CLI challenge(s) total for the batch (practical terminal scenario with hint and solution)

STYLE GUIDE:
- Flashcards: specific, testable questions, not vague definitions
- Multiple choice: 4 choices, exactly one correct answer, plausible distractors, concise explanation of why the right answer is right; set answer to the exact correct choice text and correct_index to its zero-based index
- Short answer: scenario-based, practical, should reward explanation not keyword matching; include 2-4 rubric points
- Challenges: realistic CLI or systems task with hint and a working solution command
- Reference actual tools/commands where relevant (systemctl, curl, jq, git, docker, etc.)
- Avoid patronizing wording at every level
- Match the abstraction level to the learner profile. Lower levels need concrete examples and explicit definitions. Higher levels need tradeoffs, failure modes, and transfer.
- Set type_label to one of: Flashcard, Multiple Choice, Short Answer, CLI Challenge"""

    result = llm.generate(prompt, schema=_CONTENT_SCHEMA)
    items = []
    for raw in result.get("items", []):
        raw.setdefault("choices", [])
        raw.setdefault("rubric_points", [])
        raw.setdefault("hint", "")
        raw.setdefault("rationale", "")
        raw.setdefault("type_label", _type_label(raw.get("item_type", "flashcard")))
        if raw.get("item_type") == "multiple_choice":
            choices = raw.get("choices", [])
            correct_index = raw.get("correct_index")
            if choices and isinstance(correct_index, int) and 0 <= correct_index < len(choices):
                raw["answer"] = choices[correct_index]
        items.append(LearningItem(**raw))

    return items


def _type_label(item_type: str) -> str:
    return {
        "flashcard": "Flashcard",
        "multiple_choice": "Multiple Choice",
        "short_answer": "Short Answer",
        "challenge": "CLI Challenge",
    }.get(item_type, "Learning Item")
