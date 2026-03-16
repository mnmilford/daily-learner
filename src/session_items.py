"""Helpers for normalizing legacy and vNext session item schemas."""

from copy import deepcopy


def _base_item(session: dict, topic: dict, item_type: str, topic_id: str, index: int) -> dict:
    session_date = session.get("date", "unknown")
    return {
        "item_id": f"{session_date}:{topic_id}:{item_type}:{index}",
        "item_type": item_type,
        "topic_id": topic_id,
        "topic_title": topic.get("title", topic_id),
        "topic_summary": topic.get("summary", ""),
        "difficulty_level": session.get("difficulty_level"),
        "persona_id": session.get("persona_id"),
    }


def normalize_session_items(session: dict) -> list[dict]:
    if session.get("items"):
        items = []
        for index, raw in enumerate(session["items"]):
            item = deepcopy(raw)
            item.setdefault("item_type", item.get("type", "flashcard"))
            item.setdefault("item_id", f"{session.get('date', 'unknown')}:{item.get('topic_id', 'unknown')}:{item['item_type']}:{index}")
            items.append(item)
        return items

    topics = {topic["id"]: topic for topic in session.get("topics", [])}
    items = []

    for index, flashcard in enumerate(session.get("flashcards", [])):
        topic_id = flashcard["topic_id"]
        topic = topics.get(topic_id, {"id": topic_id})
        item = _base_item(session, topic, "flashcard", topic_id, index)
        item.update(
            {
                "prompt": flashcard["front"],
                "answer": flashcard["back"],
                "type_label": "Flashcard",
            }
        )
        items.append(item)

    for index, question in enumerate(session.get("questions", [])):
        topic_id = question["topic_id"]
        topic = topics.get(topic_id, {"id": topic_id})
        item = _base_item(session, topic, "short_answer", topic_id, index)
        item.update(
            {
                "prompt": question["question"],
                "answer": question["model_answer"],
                "hint": question.get("hint", ""),
                "rubric_points": [],
                "type_label": "Short Answer",
            }
        )
        items.append(item)

    for index, challenge in enumerate(session.get("challenges", [])):
        topic_id = challenge["topic_id"]
        topic = topics.get(topic_id, {"id": topic_id})
        item = _base_item(session, topic, "challenge", topic_id, index)
        item.update(
            {
                "prompt": challenge["scenario"],
                "answer": challenge["solution"],
                "hint": challenge.get("hint", ""),
                "type_label": "CLI Challenge",
            }
        )
        items.append(item)

    return items
