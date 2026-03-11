"""Flask web app for Daily Learner."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request, render_template, send_from_directory

from src.config import load_config, get_data_dir
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
    _tracker = Tracker(_get_config())  # Reload each time for fresh data
    return _tracker


def _today():
    return datetime.now(_CT).strftime("%Y-%m-%d")


def _load_all_sessions():
    """Load all session files, return dict keyed by date."""
    data_dir = get_data_dir(_get_config())
    session_dir = data_dir / "sessions"
    sessions = {}
    if session_dir.exists():
        for f in sorted(session_dir.glob("*.json")):
            try:
                sessions[f.stem] = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                pass
    return sessions


def _merge_session_content(sessions: dict) -> dict:
    """Merge content from all sessions into unified lookups."""
    topic_lookup = {}
    fc_by_topic = {}
    q_by_topic = {}
    ch_by_topic = {}

    for s in sessions.values():
        for t in s.get("topics", []):
            if t["id"] not in topic_lookup:
                topic_lookup[t["id"]] = t
        for fc in s.get("flashcards", []):
            fc_by_topic.setdefault(fc["topic_id"], []).append(fc)
        for q in s.get("questions", []):
            q_by_topic.setdefault(q["topic_id"], []).append(q)
        for ch in s.get("challenges", []):
            ch_by_topic.setdefault(ch["topic_id"], []).append(ch)

    return {
        "topics": topic_lookup,
        "flashcards": fc_by_topic,
        "questions": q_by_topic,
        "challenges": ch_by_topic,
    }


@app.route("/learn")
def index():
    return render_template("index.html")


@app.route("/learn/api/stats")
def api_stats():
    tracker = _get_tracker()
    stats = tracker.get_stats()
    stats["today"] = _today()
    stats["review_queue"] = len(tracker.get_review_queue(_today()))
    return jsonify(stats)


@app.route("/learn/api/session")
def api_session():
    """Get today's session items — new + review queue."""
    today = _today()
    tracker = _get_tracker()
    config = _get_config()
    sessions = _load_all_sessions()
    merged = _merge_session_content(sessions)

    # Figure out which topics to show
    new_ids = set(tracker.get_new_topics(today))
    review_ids = set(tracker.get_review_queue(today)) - new_ids

    # Only include topics that have content
    has_content = set(merged["flashcards"].keys()) | set(merged["questions"].keys()) | set(merged["challenges"].keys())
    new_ids = [tid for tid in new_ids if tid in has_content]
    review_ids = [tid for tid in review_ids if tid in has_content]

    # Cap reviews
    review_cfg = config.get("review", {})
    max_review = max(3, int(12 * review_cfg.get("review_ratio", 0.25)))
    review_ids = review_ids[:max_review]

    all_ids = new_ids + review_ids

    # Build items list
    items = []
    for tid in all_ids:
        topic = merged["topics"].get(tid, {"id": tid, "title": tid})
        is_new = tid in new_ids

        for fc in merged["flashcards"].get(tid, []):
            items.append({
                "type": "flashcard",
                "topic_id": tid,
                "topic_title": topic.get("title", tid),
                "topic_summary": topic.get("summary", ""),
                "is_new": is_new,
                "front": fc["front"],
                "back": fc["back"],
            })

        for q in merged["questions"].get(tid, []):
            items.append({
                "type": "question",
                "topic_id": tid,
                "topic_title": topic.get("title", tid),
                "topic_summary": topic.get("summary", ""),
                "is_new": is_new,
                "question": q["question"],
                "model_answer": q["model_answer"],
                "hint": q.get("hint", ""),
            })

        for ch in merged["challenges"].get(tid, []):
            items.append({
                "type": "challenge",
                "topic_id": tid,
                "topic_title": topic.get("title", tid),
                "topic_summary": topic.get("summary", ""),
                "is_new": is_new,
                "scenario": ch["scenario"],
                "hint": ch.get("hint", ""),
                "solution": ch["solution"],
            })

    return jsonify({
        "date": today,
        "total_items": len(items),
        "new_count": len(new_ids),
        "review_count": len(review_ids),
        "items": items,
    })


@app.route("/learn/api/review", methods=["POST"])
def api_review():
    """Record a review with confidence rating."""
    data = request.json
    topic_id = data.get("topic_id")
    confidence = data.get("confidence", 3)

    if not topic_id:
        return jsonify({"error": "topic_id required"}), 400

    confidence = max(1, min(5, int(confidence)))
    tracker = _get_tracker()
    tracker.record_review(topic_id, confidence, _today())

    return jsonify({"ok": True, "topic_id": topic_id, "confidence": confidence})


@app.route("/learn/api/complete", methods=["POST"])
def api_complete():
    """Mark a session as complete."""
    tracker = _get_tracker()
    tracker.record_session(_today())
    stats = tracker.get_stats()
    return jsonify({"ok": True, "stats": stats})


@app.route("/learn/api/topics")
def api_topics():
    """List all tracked topics."""
    tracker = _get_tracker()
    topics = tracker.get_topic_list()

    sessions = _load_all_sessions()
    merged = _merge_session_content(sessions)

    # Enrich with topic metadata
    for t in topics:
        info = merged["topics"].get(t["id"], {})
        t["title"] = info.get("title", t["id"])
        t["domain"] = info.get("domain", "other")
        t["summary"] = info.get("summary", "")

    return jsonify(topics)


@app.route("/learn/api/generate", methods=["POST"])
def api_generate():
    """Trigger pipeline for a date."""
    data = request.json or {}
    date = data.get("date")

    from src.pipeline import run_pipeline
    try:
        result = run_pipeline(date)
        if result:
            return jsonify({"ok": True, "session_path": result})
        return jsonify({"ok": False, "message": "No activities found for that date"}), 404
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


def run_server(host="0.0.0.0", port=8090):
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_server()
