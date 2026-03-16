"""Short-answer evaluation providers and mode routing."""

from dataclasses import dataclass

from src.llm import LLMClient, LLMError


class EvaluationError(Exception):
    pass


@dataclass
class EvaluationContext:
    prompt: str
    learner_answer: str
    exemplar_answer: str
    rubric_points: list[str]
    topic_title: str
    difficulty_label: str


class BaseEvaluator:
    mode = "off"

    def evaluate(self, context: EvaluationContext) -> dict:
        raise NotImplementedError


class OffEvaluator(BaseEvaluator):
    mode = "off"

    def evaluate(self, context: EvaluationContext) -> dict:
        return {
            "mode": self.mode,
            "available": False,
            "correctness": None,
            "score": None,
            "feedback": "AI evaluation is off. Compare your answer against the reference answer and self-rate your confidence.",
            "strengths": [],
            "missing_points": [],
            "exemplar_answer": context.exemplar_answer,
            "rubric_points": context.rubric_points,
        }


class ByokEvaluator(BaseEvaluator):
    mode = "byok"

    def __init__(self, config: dict):
        self.llm = LLMClient(config)

    def evaluate(self, context: EvaluationContext) -> dict:
        result = self.llm.evaluate_short_answer(
            prompt=context.prompt,
            learner_answer=context.learner_answer,
            exemplar_answer=context.exemplar_answer,
            rubric_points=context.rubric_points,
            topic_title=context.topic_title,
            difficulty_label=context.difficulty_label,
        )
        result["mode"] = self.mode
        result["available"] = True
        result["exemplar_answer"] = context.exemplar_answer
        result["rubric_points"] = context.rubric_points
        return result


class HostedEvaluator(BaseEvaluator):
    mode = "hosted"

    def __init__(self, config: dict):
        self.config = config

    def evaluate(self, context: EvaluationContext) -> dict:
        raise EvaluationError(
            "Hosted evaluation is not enabled on this deployment yet. Use BYOK for now, or switch evaluation mode to Off."
        )


def get_evaluator(config: dict, mode: str | None) -> BaseEvaluator:
    normalized = (mode or "off").strip().lower()
    if normalized == "off":
        return OffEvaluator()
    if normalized == "byok":
        try:
            return ByokEvaluator(config)
        except LLMError as exc:
            raise EvaluationError(
                f"BYOK evaluation is selected, but no working model key is configured: {exc}"
            ) from exc
    if normalized == "hosted":
        return HostedEvaluator(config)
    raise EvaluationError(f"Unknown evaluation mode: {mode}")
