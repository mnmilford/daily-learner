"""Spaced repetition tracker — JSON-backed per-topic progress tracking."""

import fcntl
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.config import get_data_dir

log = logging.getLogger("daily-learner.tracker")


class Tracker:
    def __init__(self, config: dict):
        self.data_dir = get_data_dir(config)
        self.tracker_path = self.data_dir / "tracker.json"
        self.review_cfg = config.get("review", {})
        self.intervals = self.review_cfg.get("spacing_intervals", [1, 3, 7, 14, 30])
        self.graduation_threshold = self.review_cfg.get("graduation_threshold", 3)
        self.low_confidence_cutoff = self.review_cfg.get("low_confidence_cutoff", 2)
        self._data = self._load()

    def _load(self) -> dict:
        if not self.tracker_path.exists():
            return {"topics": {}, "stats": {"streak": 0, "last_session": None, "total_sessions": 0}}

        with open(self.tracker_path) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _save(self):
        self.tracker_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tracker_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(self._data, f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def get_all_topic_ids(self) -> list[str]:
        return list(self._data["topics"].keys())

    def register_topics(self, topic_ids: list[str], date_str: str):
        """Register new topics in the tracker."""
        for tid in topic_ids:
            if tid not in self._data["topics"]:
                self._data["topics"][tid] = {
                    "first_seen": date_str,
                    "times_reviewed": 0,
                    "last_reviewed": None,
                    "confidence": 0,
                    "next_review": date_str,
                    "graduated": False,
                    "interval_index": 0,
                }
        self._save()

    def get_review_queue(self, today: str) -> list[str]:
        """Get topic IDs due for review on or before today."""
        due = []
        for tid, info in self._data["topics"].items():
            if info["graduated"]:
                continue
            nr = info.get("next_review", today)
            if nr <= today:
                due.append(tid)
        return due

    def get_new_topics(self, today: str) -> list[str]:
        """Get topic IDs first seen today that haven't been reviewed."""
        new = []
        for tid, info in self._data["topics"].items():
            if info["first_seen"] == today and info["times_reviewed"] == 0:
                new.append(tid)
        return new

    def record_review(self, topic_id: str, confidence: int, today: str):
        """Record a review with confidence rating 1-5."""
        if topic_id not in self._data["topics"]:
            return

        info = self._data["topics"][topic_id]
        info["times_reviewed"] += 1
        info["last_reviewed"] = today
        info["confidence"] = confidence

        # Calculate next review date
        if confidence <= self.low_confidence_cutoff:
            # Reset to shortest interval
            info["interval_index"] = 0
        else:
            # Advance interval
            info["interval_index"] = min(
                info.get("interval_index", 0) + 1,
                len(self.intervals) - 1,
            )

        interval_days = self.intervals[info["interval_index"]]
        next_date = datetime.strptime(today, "%Y-%m-%d") + timedelta(days=interval_days)
        info["next_review"] = next_date.strftime("%Y-%m-%d")

        # Check graduation
        if (confidence >= 5
                and info["times_reviewed"] >= self.graduation_threshold):
            info["graduated"] = True

        self._save()

    def record_session(self, today: str):
        """Record that a session was completed today."""
        stats = self._data["stats"]
        last = stats.get("last_session")

        if last:
            last_date = datetime.strptime(last, "%Y-%m-%d")
            today_date = datetime.strptime(today, "%Y-%m-%d")
            if (today_date - last_date).days == 1:
                stats["streak"] = stats.get("streak", 0) + 1
            elif (today_date - last_date).days > 1:
                stats["streak"] = 1
            # Same day = no streak change
        else:
            stats["streak"] = 1

        stats["last_session"] = today
        stats["total_sessions"] = stats.get("total_sessions", 0) + 1
        self._save()

    def get_stats(self) -> dict:
        """Get summary statistics."""
        topics = self._data["topics"]
        stats = self._data["stats"]

        total = len(topics)
        graduated = sum(1 for t in topics.values() if t["graduated"])
        reviewed = sum(1 for t in topics.values() if t["times_reviewed"] > 0)

        # Count by domain (need topic info from session files)
        avg_confidence = 0
        if reviewed:
            avg_confidence = sum(
                t["confidence"] for t in topics.values() if t["times_reviewed"] > 0
            ) / reviewed

        return {
            "total_topics": total,
            "graduated": graduated,
            "reviewed": reviewed,
            "unreviewed": total - reviewed,
            "streak": stats.get("streak", 0),
            "total_sessions": stats.get("total_sessions", 0),
            "avg_confidence": round(avg_confidence, 1),
        }

    def get_topic_list(self) -> list[dict]:
        """Get all topics with their tracker info."""
        result = []
        for tid, info in sorted(self._data["topics"].items()):
            result.append({"id": tid, **info})
        return result
