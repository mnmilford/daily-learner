"""Flask web app for Daily Learner."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request, render_template

from src.config import get_data_dir, load_config
from src.evaluator import EvaluationContext, EvaluationError, get_evaluator
from src.learner_profile import get_level, get_onboarding_quiz
from src.pipeline import run_pipeline
from src.preferences import PreferencesStore
from src.session_items import normalize_session_items
from src.tracker.tracker import Tracker

_CT = timezone(timedelta(hours=-5))

app = Flask(
    __name__,
    template_folder=Path(__file__).parent / "templates",
    static_folder=Path(__file__).parent / "static",
    static_url_path="/learn/static",
)

_config = None
_tracker = None


def _get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def _get_tracker():
    global _tracker
    _tracker = Tracker(_get_config())
    return _tracker


def _get_preferences_store():
    return PreferencesStore(_get_config())


def _today():
    return datetime.now(_CT).strftime("%Y-%m-%d")


def _load_all_sessions():
    data_dir = get_data_dir(_get_config())
    session_dir = data_dir / "sessions"
    sessions = {}
    if session_dir.exists():
        for session_file in sorted(session_dir.glob("*.json")):
            try:
                sessions[session_file.stem] = json.loads(session_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
    return sessions


def _merge_session_content(sessions: dict) -> dict:
    topic_lookup = {}
    items_by_topic = {}

    for session in sessions.values():
        for topic in session.get("topics", []):
            if topic["id"] not in topic_lookup:
                topic_lookup[topic["id"]] = topic
        for item in normalize_session_items(session):
            items_by_topic.setdefault(item["topic_id"], []).append(item)

    return {"topics": topic_lookup, "items": items_by_topic}


def _max_review_items(config: dict) -> int:
    review_cfg = config.get("review", {})
    return max(3, int(12 * review_cfg.get("review_ratio", 0.25)))


@app.route("/learn")
def index():
    return render_template("index.html")


@app.route("/learn/api/stats")
def api_stats():
    tracker = _get_tracker()
    stats = tracker.get_stats()
    stats["today"] = _today()
    stats["review_queue"] = len(tracker.get_review_queue(_today()))
    stats["preferences"] = _get_preferences_store().get_preferences()
    return jsonify(stats)


@app.route("/learn/api/preferences", methods=["GET", "POST"])
def api_preferences():
    store = _get_preferences_store()
    if request.method == "GET":
        return jsonify(store.get_preferences())

    data = request.json or {}
    updated = store.update_preferences(data)
    return jsonify({"ok": True, "preferences": updated})


@app.route("/learn/api/onboarding", methods=["GET", "POST"])
def api_onboarding():
    store = _get_preferences_store()
    if request.method == "GET":
        return jsonify(
            {
                "quiz": get_onboarding_quiz(),
                "state": store.get_onboarding_state(),
            }
        )

    data = request.json or {}
    if data.get("skip"):
        return jsonify({"ok": True, "state": store.skip_onboarding()})

    answers = data.get("answers", {})
    apply_recommendation = bool(data.get("apply_recommendation", False))
    result = store.submit_onboarding(answers, apply_recommendation=apply_recommendation)
    return jsonify({"ok": True, "result": result, "preferences": store.get_preferences()})


@app.route("/learn/api/session")
def api_session():
    today = _today()
    tracker = _get_tracker()
    config = _get_config()
    preferences = _get_preferences_store().get_preferences()
    sessions = _load_all_sessions()
    merged = _merge_session_content(sessions)

    new_ids = list(set(tracker.get_new_topics(today)))
    review_ids = [tid for tid in tracker.get_review_queue(today) if tid not in new_ids]

    has_content = set(merged["items"].keys())
    new_ids = [tid for tid in new_ids if tid in has_content]
    review_ids = [tid for tid in review_ids if tid in has_content][:_max_review_items(config)]
    all_ids = new_ids + review_ids

    items = []
    for topic_id in all_ids:
        topic = merged["topics"].get(topic_id, {"id": topic_id, "title": topic_id})
        is_new = topic_id in new_ids
        for item in merged["items"].get(topic_id, []):
            items.append(
                {
                    **item,
                    "topic_title": topic.get("title", topic_id),
                    "topic_summary": topic.get("summary", ""),
                    "is_new": is_new,
                    "difficulty_level": item.get("difficulty_level") or preferences["difficulty_level"],
                    "persona_id": item.get("persona_id") or preferences["persona_id"],
                }
            )

    return jsonify(
        {
            "date": today,
            "total_items": len(items),
            "new_count": len(new_ids),
            "review_count": len(review_ids),
            "items": items,
            "preferences": preferences,
        }
    )


@app.route("/learn/api/answer", methods=["POST"])
def api_answer():
    data = request.json or {}
    item = data.get("item") or {}
    item_type = item.get("item_type")

    if not item_type:
        return jsonify({"error": "item.item_type required"}), 400

    if item_type == "multiple_choice":
        selected_index = data.get("selected_index")
        if selected_index is None:
            return jsonify({"error": "selected_index required"}), 400

        correct_index = item.get("correct_index")
        if correct_index is None:
            return jsonify({"error": "multiple_choice item missing correct_index"}), 400

        choices = item.get("choices", [])
        correct_answer = ""
        if isinstance(correct_index, int) and 0 <= correct_index < len(choices):
            correct_answer = choices[correct_index]
        is_correct = int(selected_index) == int(correct_index)
        return jsonify(
            {
                "ok": True,
                "evaluation": {
                    "correctness": "correct" if is_correct else "incorrect",
                    "score": 4.8 if is_correct else 1.8,
                    "feedback": "Nice. You picked the right answer." if is_correct else "Not quite. Check the rationale and the correct answer.",
                    "strengths": ["Selected the correct answer."] if is_correct else [],
                    "missing_points": [] if is_correct else ["Review why the correct option is better than the distractors."],
                    "correct_index": correct_index,
                    "correct_answer": correct_answer,
                    "rationale": item.get("rationale", ""),
                },
            }
        )

    if item_type == "short_answer":
        learner_answer = (data.get("answer") or "").strip()
        if not learner_answer:
            return jsonify({"error": "answer required"}), 400

        preferences = _get_preferences_store().get_preferences()
        difficulty = get_level(item.get("difficulty_level") or preferences["difficulty_level"])
        try:
            evaluator = get_evaluator(_get_config(), preferences.get("evaluation_mode"))
            evaluation = evaluator.evaluate(
                EvaluationContext(
                    prompt=item.get("prompt", ""),
                    learner_answer=learner_answer,
                    exemplar_answer=item.get("answer", ""),
                    rubric_points=item.get("rubric_points", []),
                    topic_title=item.get("topic_title", item.get("topic_id", "Topic")),
                    difficulty_label=difficulty["label"],
                )
            )
        except EvaluationError as exc:
            return jsonify({"error": str(exc), "mode": preferences.get("evaluation_mode")}), 409
        except Exception as exc:
            return jsonify({"error": str(exc), "mode": preferences.get("evaluation_mode")}), 502

        return jsonify({"ok": True, "evaluation": evaluation})

    return jsonify({"error": f"Unsupported item type {item_type}"}), 400


@app.route("/learn/api/review", methods=["POST"])
def api_review():
    data = request.json or {}
    topic_id = data.get("topic_id")
    confidence = data.get("confidence", 3)

    if not topic_id:
        return jsonify({"error": "topic_id required"}), 400

    confidence = max(1, min(5, int(confidence)))
    tracker = _get_tracker()
    tracker.record_review(topic_id, confidence, _today())

    store = _get_preferences_store()
    adaptive = store.record_answer_outcome(
        item_type=data.get("item_type", "flashcard"),
        confidence=confidence,
        correctness=data.get("correctness"),
        mastery_score=data.get("mastery_score"),
        used_hint=bool(data.get("used_hint", False)),
    )
    preferences = store.get_preferences()

    response = {
        "ok": True,
        "topic_id": topic_id,
        "confidence": confidence,
        "preferences": preferences,
        "adaptive_status": preferences.get("adaptive_state", {}),
    }
    if adaptive.updated:
        response["adaptive_update"] = {
            "previous_level": adaptive.previous_level,
            "new_level": adaptive.new_level,
            "reason": adaptive.reason,
            "decision": adaptive.decision,
            "cooldown_remaining": adaptive.cooldown_remaining,
            "preferences": preferences,
        }
    return jsonify(response)


@app.route("/learn/api/complete", methods=["POST"])
def api_complete():
    tracker = _get_tracker()
    tracker.record_session(_today())
    stats = tracker.get_stats()
    return jsonify({"ok": True, "stats": stats})


@app.route("/learn/api/topics")
def api_topics():
    tracker = _get_tracker()
    topics = tracker.get_topic_list()

    sessions = _load_all_sessions()
    merged = _merge_session_content(sessions)

    for topic in topics:
        info = merged["topics"].get(topic["id"], {})
        topic["title"] = info.get("title", topic["id"])
        topic["domain"] = info.get("domain", "other")
        topic["summary"] = info.get("summary", "")

    return jsonify(topics)


@app.route("/learn/api/generate", methods=["POST"])
def api_generate():
    data = request.json or {}
    date = data.get("date")
    preferences = _get_preferences_store().get_preferences()

    try:
        result = run_pipeline(date, preferences)
        if result:
            return jsonify({"ok": True, "session_path": result, "preferences": preferences})
        return jsonify({"ok": False, "message": "No activities found for that date"}), 404
    except Exception as exc:  # pragma: no cover - surface pipeline failure to client
        return jsonify({"ok": False, "message": str(exc)}), 500


def run_server(host="0.0.0.0", port=8090):
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_server()
