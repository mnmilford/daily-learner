"""Generate learning content (flashcards, questions, challenges) from topics."""

import logging

from src.extract import Topic
from src.generate import Flashcard, Question, Challenge
from src.llm import LLMClient

log = logging.getLogger("daily-learner.generate")

_CONTENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "flashcards": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "topic_id": {"type": "STRING"},
                    "front": {"type": "STRING"},
                    "back": {"type": "STRING"},
                },
                "required": ["topic_id", "front", "back"],
            },
        },
        "questions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "topic_id": {"type": "STRING"},
                    "question": {"type": "STRING"},
                    "model_answer": {"type": "STRING"},
                    "hint": {"type": "STRING"},
                },
                "required": ["topic_id", "question", "model_answer"],
            },
        },
        "challenges": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "topic_id": {"type": "STRING"},
                    "scenario": {"type": "STRING"},
                    "hint": {"type": "STRING"},
                    "solution": {"type": "STRING"},
                },
                "required": ["topic_id", "scenario", "hint", "solution"],
            },
        },
    },
    "required": ["flashcards", "questions", "challenges"],
}


def generate_content(
    topics: list[Topic],
    llm: LLMClient,
    config: dict,
) -> tuple[list[Flashcard], list[Question], list[Challenge]]:
    """Generate learning content for a batch of topics."""

    if not topics:
        return [], [], []

    pipeline_cfg = config.get("pipeline", {})
    fc_per = pipeline_cfg.get("flashcards_per_topic", 2)
    q_per = pipeline_cfg.get("questions_per_topic", 1)
    ch_per = pipeline_cfg.get("challenges_per_batch", 1)

    all_flashcards = []
    all_questions = []
    all_challenges = []

    # Process in batches of 3-4 topics
    batch_size = 3
    for i in range(0, len(topics), batch_size):
        batch = topics[i:i + batch_size]
        fc, q, ch = _generate_batch(batch, llm, fc_per, q_per, ch_per)
        all_flashcards.extend(fc)
        all_questions.extend(q)
        all_challenges.extend(ch)

    log.info(f"Generated {len(all_flashcards)} flashcards, {len(all_questions)} questions, {len(all_challenges)} challenges")
    return all_flashcards, all_questions, all_challenges


def _generate_batch(
    topics: list[Topic],
    llm: LLMClient,
    fc_per: int,
    q_per: int,
    ch_per: int,
) -> tuple[list[Flashcard], list[Question], list[Challenge]]:
    """Generate content for a batch of topics in a single LLM call."""

    topic_text = ""
    for t in topics:
        topic_text += f"\n- [{t.id}] {t.title} ({t.domain}): {t.summary}\n"

    prompt = f"""Generate learning content for these technical topics. Write for a hands-on technical learner — no patronizing, prioritize practical understanding.

TOPICS:
{topic_text}

GENERATE:
- {fc_per} flashcards per topic (concise front question, detailed back answer)
- {q_per} short-answer question(s) per topic (requires 2-3 sentence response)
- {ch_per} CLI challenge(s) total for the batch (practical terminal scenario with hint and solution)

STYLE GUIDE:
- Flashcard fronts: specific, testable questions (not "What is X?")
- Flashcard backs: direct answers with practical context
- Questions: scenario-based, connect to real-world usage (self-hosting, LLM tooling, APIs)
- Challenges: give a realistic CLI scenario, provide a hint, and a working solution command
- Reference actual tools/commands where relevant (systemctl, curl, jq, git, docker, etc.)"""

    result = llm.generate(prompt, schema=_CONTENT_SCHEMA)

    flashcards = [Flashcard(**fc) for fc in result.get("flashcards", [])]
    questions = [Question(**q) for q in result.get("questions", [])]
    challenges = [Challenge(**ch) for ch in result.get("challenges", [])]

    return flashcards, questions, challenges
