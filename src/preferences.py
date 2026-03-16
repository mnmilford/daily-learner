"""Single-user learner preferences and onboarding state."""

import json
from dataclasses import dataclass
from datetime import datetime, UTC

from src.config import get_data_dir
from src.learner_profile import get_level, get_levels, get_persona, get_personas, score_onboarding


def _default_preferences(config: dict) -> dict:
    learner_cfg = config.get("learner", {})
    default_level = learner_cfg.get("default_difficulty_level", "follow-if-slowed-down")
    default_persona = learner_cfg.get("default_persona", "lil-mike")
    default_evaluation_mode = learner_cfg.get("default_evaluation_mode", "off")
    return {
        "persona_id": default_persona,
        "difficulty_level": default_level,
        "evaluation_mode": default_evaluation_mode,
        "adaptive_difficulty_enabled": False,
        "onboarding_completed": False,
        "onboarding_recommendation": None,
        "domain_scores": {},
    }


def _default_adaptive_state() -> dict:
    return {
        "last_decision": None,
        "last_level_change": None,
        "last_change_answer_index": None,
        "change_log": [],
    }


def _default_store_data(config: dict) -> dict:
    return {
        "preferences": _default_preferences(config),
        "answer_history": [],
        "adaptive_state": _default_adaptive_state(),
    }


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _level_ids() -> list[str]:
    return [level["id"] for level in get_levels()]


def _evaluation_modes() -> list[dict]:
    return [
        {
            "id": "off",
            "label": "Off",
            "description": "Do not use AI grading. Reveal the reference answer and self-rate manually.",
        },
        {
            "id": "byok",
            "label": "Bring Your Own Key",
            "description": "Use your configured model key for AI grading. Best current mode for active testing.",
        },
        {
            "id": "hosted",
            "label": "Built-in",
            "description": "Use a platform-provided evaluator. This deployment does not enable it yet.",
        },
    ]


def _trim_list(values: list, keep: int):
    if len(values) > keep:
        del values[:-keep]


@dataclass
class AdaptiveResult:
    updated: bool
    previous_level: str | None = None
    new_level: str | None = None
    reason: str | None = None
    decision: str | None = None
    cooldown_remaining: int = 0


class PreferencesStore:
    def __init__(self, config: dict):
        self.config = config
        self.path = get_data_dir(config) / "preferences.json"
        self._data = self._load()

    def _load(self) -> dict:
        data = _default_store_data(self.config)
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
            except json.JSONDecodeError:
                raw = {}
            data["preferences"].update(raw.get("preferences", {}))
            data["answer_history"] = raw.get("answer_history", [])
            adaptive_state = _default_adaptive_state()
            adaptive_state.update(raw.get("adaptive_state", {}))
            adaptive_state["change_log"] = adaptive_state.get("change_log", [])
            data["adaptive_state"] = adaptive_state
        return data

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))

    def _policy(self) -> dict:
        learner_cfg = self.config.get("learner", {})
        return {
            "window": int(learner_cfg.get("adaptive_window", 10)),
            "min_answers": int(learner_cfg.get("adaptive_min_answers", 8)),
            "history_limit": int(learner_cfg.get("adaptive_history_limit", 60)),
            "cooldown_answers": int(learner_cfg.get("adaptive_cooldown_answers", 8)),
            "promote_threshold": float(learner_cfg.get("adaptive_promote_threshold", 4.4)),
            "demote_threshold": float(learner_cfg.get("adaptive_demote_threshold", 2.4)),
            "promote_strong_streak": int(learner_cfg.get("adaptive_promote_strong_streak", 3)),
            "demote_weak_streak": int(learner_cfg.get("adaptive_demote_weak_streak", 3)),
            "promote_min_high_mastery": int(learner_cfg.get("adaptive_promote_min_high_mastery", 5)),
            "demote_min_low_mastery": int(learner_cfg.get("adaptive_demote_min_low_mastery", 4)),
            "promote_max_incorrect": int(learner_cfg.get("adaptive_promote_max_incorrect", 1)),
        }

    def _signal_summary(self, events: list[dict]) -> dict:
        total = len(events)
        if not total:
            return {
                "total": 0,
                "avg_mastery": 0.0,
                "high_mastery_count": 0,
                "low_mastery_count": 0,
                "correct_count": 0,
                "partial_count": 0,
                "incorrect_count": 0,
                "hint_count": 0,
                "high_confidence_count": 0,
                "low_confidence_count": 0,
                "strong_streak": 0,
                "weak_streak": 0,
                "item_type_mix": {},
            }

        avg_mastery = sum(float(event.get("mastery_score", 0.0)) for event in events) / total
        high_mastery_count = sum(1 for event in events if float(event.get("mastery_score", 0.0)) >= 4.5)
        low_mastery_count = sum(1 for event in events if float(event.get("mastery_score", 0.0)) <= 2.3)
        correct_count = sum(1 for event in events if event.get("correctness") == "correct")
        partial_count = sum(1 for event in events if event.get("correctness") == "partial")
        incorrect_count = sum(1 for event in events if event.get("correctness") == "incorrect")
        hint_count = sum(1 for event in events if event.get("used_hint"))
        high_confidence_count = sum(1 for event in events if int(event.get("confidence", 0)) >= 4)
        low_confidence_count = sum(1 for event in events if int(event.get("confidence", 0)) <= 2)
        item_type_mix: dict[str, int] = {}
        for event in events:
            item_type = event.get("item_type", "other")
            item_type_mix[item_type] = item_type_mix.get(item_type, 0) + 1

        strong_streak = 0
        weak_streak = 0
        for event in reversed(events):
            mastery = float(event.get("mastery_score", 0.0))
            confidence = int(event.get("confidence", 0))
            correctness = event.get("correctness")
            used_hint = bool(event.get("used_hint"))
            strong = mastery >= 4.4 and confidence >= 4 and correctness != "incorrect" and not used_hint
            weak = mastery <= 2.4 or confidence <= 2 or correctness == "incorrect"

            if strong and weak_streak == 0:
                strong_streak += 1
            elif strong_streak == 0 and weak:
                weak_streak += 1
            else:
                break

        return {
            "total": total,
            "avg_mastery": round(avg_mastery, 2),
            "high_mastery_count": high_mastery_count,
            "low_mastery_count": low_mastery_count,
            "correct_count": correct_count,
            "partial_count": partial_count,
            "incorrect_count": incorrect_count,
            "hint_count": hint_count,
            "high_confidence_count": high_confidence_count,
            "low_confidence_count": low_confidence_count,
            "strong_streak": strong_streak,
            "weak_streak": weak_streak,
            "item_type_mix": item_type_mix,
        }

    def _current_level_index(self, prefs: dict) -> int:
        levels = _level_ids()
        current = prefs.get("difficulty_level", levels[1])
        return levels.index(current) if current in levels else 1

    def _cooldown_remaining(self, answer_count: int, adaptive_state: dict, policy: dict) -> int:
        last_change_index = adaptive_state.get("last_change_answer_index")
        if last_change_index is None:
            return 0
        delta = answer_count - int(last_change_index)
        return max(0, policy["cooldown_answers"] - delta)

    def _decision_payload(self, *, decision: str, reason: str, summary: dict, cooldown_remaining: int) -> dict:
        readiness = "steady"
        if summary["total"] < self._policy()["min_answers"]:
            readiness = "insufficient-data"
        elif cooldown_remaining > 0:
            readiness = "cooldown"
        elif decision == "promote":
            readiness = "promote"
        elif decision == "demote":
            readiness = "demote"
        elif summary["strong_streak"] >= max(2, self._policy()["promote_strong_streak"] - 1):
            readiness = "promotion-watch"
        elif summary["weak_streak"] >= max(2, self._policy()["demote_weak_streak"] - 1):
            readiness = "demotion-watch"

        return {
            "decision": decision,
            "reason": reason,
            "summary": summary,
            "cooldown_remaining": cooldown_remaining,
            "readiness": readiness,
            "timestamp": _utc_now(),
        }

    def _record_level_change(
        self,
        *,
        previous_level: str,
        new_level: str,
        reason: str,
        summary: dict,
        answer_count: int,
    ):
        adaptive_state = self._data.setdefault("adaptive_state", _default_adaptive_state())
        change = {
            "timestamp": _utc_now(),
            "previous_level": previous_level,
            "new_level": new_level,
            "reason": reason,
            "summary": summary,
        }
        adaptive_state["last_level_change"] = change
        adaptive_state["last_change_answer_index"] = answer_count
        adaptive_state.setdefault("change_log", []).append(change)
        _trim_list(adaptive_state["change_log"], 12)

    def _evaluate_adaptive_change(self, prefs: dict, history: list[dict]) -> AdaptiveResult:
        policy = self._policy()
        adaptive_state = self._data.setdefault("adaptive_state", _default_adaptive_state())

        if not prefs.get("adaptive_difficulty_enabled"):
            summary = self._signal_summary(history[-policy["window"] :])
            adaptive_state["last_decision"] = self._decision_payload(
                decision="disabled",
                reason="Adaptive difficulty is turned off.",
                summary=summary,
                cooldown_remaining=0,
            )
            return AdaptiveResult(updated=False, decision="disabled", reason="Adaptive difficulty is turned off.")

        recent = history[-policy["window"] :]
        summary = self._signal_summary(recent)
        answer_count = len(history)
        cooldown_remaining = self._cooldown_remaining(answer_count, adaptive_state, policy)

        if summary["total"] < policy["min_answers"]:
            reason = f"Need {policy['min_answers'] - summary['total']} more scored answers before changing levels."
            adaptive_state["last_decision"] = self._decision_payload(
                decision="hold",
                reason=reason,
                summary=summary,
                cooldown_remaining=cooldown_remaining,
            )
            return AdaptiveResult(updated=False, decision="hold", reason=reason, cooldown_remaining=cooldown_remaining)

        if cooldown_remaining > 0:
            reason = f"Cooldown active. Need {cooldown_remaining} more scored answers before another level change."
            adaptive_state["last_decision"] = self._decision_payload(
                decision="hold",
                reason=reason,
                summary=summary,
                cooldown_remaining=cooldown_remaining,
            )
            return AdaptiveResult(updated=False, decision="hold", reason=reason, cooldown_remaining=cooldown_remaining)

        levels = _level_ids()
        current_index = self._current_level_index(prefs)
        current_level = prefs["difficulty_level"]

        promote_ready = (
            current_index < len(levels) - 1
            and summary["avg_mastery"] >= policy["promote_threshold"]
            and summary["high_mastery_count"] >= policy["promote_min_high_mastery"]
            and summary["incorrect_count"] <= policy["promote_max_incorrect"]
            and summary["strong_streak"] >= policy["promote_strong_streak"]
            and summary["low_confidence_count"] == 0
        )
        demote_ready = (
            current_index > 0
            and summary["avg_mastery"] <= policy["demote_threshold"]
            and summary["low_mastery_count"] >= policy["demote_min_low_mastery"]
            and summary["weak_streak"] >= policy["demote_weak_streak"]
        )

        if promote_ready:
            new_level = levels[current_index + 1]
            reason = (
                f"Promoted after {summary['total']} recent answers averaged {summary['avg_mastery']}/5, "
                f"with {summary['high_mastery_count']} high-mastery answers and a strong streak of {summary['strong_streak']}."
            )
            prefs["difficulty_level"] = new_level
            self._record_level_change(
                previous_level=current_level,
                new_level=new_level,
                reason=reason,
                summary=summary,
                answer_count=answer_count,
            )
            adaptive_state["last_decision"] = self._decision_payload(
                decision="promote",
                reason=reason,
                summary=summary,
                cooldown_remaining=policy["cooldown_answers"],
            )
            return AdaptiveResult(
                updated=True,
                previous_level=current_level,
                new_level=new_level,
                reason=reason,
                decision="promote",
                cooldown_remaining=policy["cooldown_answers"],
            )

        if demote_ready:
            new_level = levels[current_index - 1]
            reason = (
                f"Lowered difficulty after {summary['total']} recent answers averaged {summary['avg_mastery']}/5, "
                f"with {summary['low_mastery_count']} low-mastery answers and a weak streak of {summary['weak_streak']}."
            )
            prefs["difficulty_level"] = new_level
            self._record_level_change(
                previous_level=current_level,
                new_level=new_level,
                reason=reason,
                summary=summary,
                answer_count=answer_count,
            )
            adaptive_state["last_decision"] = self._decision_payload(
                decision="demote",
                reason=reason,
                summary=summary,
                cooldown_remaining=policy["cooldown_answers"],
            )
            return AdaptiveResult(
                updated=True,
                previous_level=current_level,
                new_level=new_level,
                reason=reason,
                decision="demote",
                cooldown_remaining=policy["cooldown_answers"],
            )

        if summary["strong_streak"] >= max(2, policy["promote_strong_streak"] - 1):
            reason = "Performance is trending strong, but the promotion rules are not fully met yet."
        elif summary["weak_streak"] >= max(2, policy["demote_weak_streak"] - 1):
            reason = "Performance is trending rough, but the demotion rules are not fully met yet."
        else:
            reason = "Holding steady. Recent answers do not justify a level change."

        adaptive_state["last_decision"] = self._decision_payload(
            decision="hold",
            reason=reason,
            summary=summary,
            cooldown_remaining=0,
        )
        return AdaptiveResult(updated=False, decision="hold", reason=reason)

    def _adaptive_view(self, prefs: dict) -> dict:
        policy = self._policy()
        adaptive_state = self._data.setdefault("adaptive_state", _default_adaptive_state())
        history = self._data.setdefault("answer_history", [])
        recent = history[-policy["window"] :]
        summary = self._signal_summary(recent)
        cooldown_remaining = self._cooldown_remaining(len(history), adaptive_state, policy)

        return {
            "enabled": bool(prefs.get("adaptive_difficulty_enabled")),
            "policy": policy,
            "recent_summary": summary,
            "cooldown_remaining": cooldown_remaining,
            "last_decision": adaptive_state.get("last_decision"),
            "last_level_change": adaptive_state.get("last_level_change"),
            "change_log": list(reversed(adaptive_state.get("change_log", []))),
            "recent_history": list(reversed(history[-12:])),
        }

    def get_preferences(self) -> dict:
        prefs = _default_preferences(self.config)
        prefs.update(self._data.get("preferences", {}))
        level = get_level(prefs["difficulty_level"])
        persona = get_persona(prefs["persona_id"])
        return {
            **prefs,
            "level": level,
            "persona": persona,
            "available_levels": get_levels(),
            "available_personas": get_personas(),
            "available_evaluation_modes": _evaluation_modes(),
            "adaptive_state": self._adaptive_view(prefs),
        }

    def update_preferences(self, patch: dict) -> dict:
        prefs = self._data.setdefault("preferences", _default_preferences(self.config))

        if "persona_id" in patch:
            prefs["persona_id"] = get_persona(patch["persona_id"])["id"]
        if "difficulty_level" in patch:
            prefs["difficulty_level"] = get_level(patch["difficulty_level"])["id"]
        if "evaluation_mode" in patch:
            modes = {mode["id"] for mode in _evaluation_modes()}
            requested = str(patch["evaluation_mode"]).strip().lower()
            prefs["evaluation_mode"] = requested if requested in modes else "off"
        if "adaptive_difficulty_enabled" in patch:
            prefs["adaptive_difficulty_enabled"] = bool(patch["adaptive_difficulty_enabled"])

        self._save()
        return self.get_preferences()

    def get_onboarding_state(self) -> dict:
        prefs = self.get_preferences()
        return {
            "completed": prefs["onboarding_completed"],
            "recommendation": prefs["onboarding_recommendation"],
            "domain_scores": prefs.get("domain_scores", {}),
        }

    def submit_onboarding(self, answers: dict[str, str], apply_recommendation: bool = False) -> dict:
        result = score_onboarding(answers)
        prefs = self._data.setdefault("preferences", _default_preferences(self.config))
        prefs["onboarding_completed"] = True
        prefs["onboarding_recommendation"] = result["recommended_level"]["id"]
        prefs["domain_scores"] = result["domain_scores"]
        if apply_recommendation:
            prefs["difficulty_level"] = result["recommended_level"]["id"]
        self._save()
        return {
            "completed": True,
            "recommendation": result["recommended_level"],
            "applied": apply_recommendation,
            "domain_scores": result["domain_scores"],
        }

    def skip_onboarding(self) -> dict:
        prefs = self._data.setdefault("preferences", _default_preferences(self.config))
        prefs["onboarding_completed"] = True
        self._save()
        return self.get_onboarding_state()

    def record_answer_outcome(
        self,
        *,
        item_type: str,
        confidence: int,
        correctness: str | None = None,
        mastery_score: float | None = None,
        used_hint: bool = False,
    ) -> AdaptiveResult:
        prefs = self._data.setdefault("preferences", _default_preferences(self.config))
        history = self._data.setdefault("answer_history", [])
        event_score = mastery_score if mastery_score is not None else float(confidence)
        if used_hint:
            event_score = max(1.0, event_score - 0.3)
        if correctness == "incorrect":
            event_score = min(event_score, 2.0)
        elif correctness == "correct":
            event_score = max(event_score, 3.5)

        history.append(
            {
                "timestamp": _utc_now(),
                "item_type": item_type,
                "confidence": confidence,
                "correctness": correctness,
                "mastery_score": round(event_score, 2),
                "used_hint": used_hint,
                "difficulty_level_at_answer": prefs.get("difficulty_level"),
            }
        )

        _trim_list(history, self._policy()["history_limit"])
        result = self._evaluate_adaptive_change(prefs, history)
        self._save()
        return result
