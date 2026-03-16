"""Generate module — creates learning content from topics."""

from dataclasses import dataclass, field


@dataclass
class LearningItem:
    topic_id: str
    item_type: str
    prompt: str
    answer: str = ""
    hint: str = ""
    choices: list[str] = field(default_factory=list)
    correct_index: int | None = None
    rationale: str = ""
    rubric_points: list[str] = field(default_factory=list)
    type_label: str = ""

    def to_dict(self) -> dict:
        return vars(self)


@dataclass
class Flashcard:
    topic_id: str
    front: str
    back: str


@dataclass
class Question:
    topic_id: str
    question: str
    model_answer: str
    hint: str = ""


@dataclass
class Challenge:
    topic_id: str
    scenario: str
    hint: str
    solution: str


@dataclass
class SessionContent:
    """All generated content for one day's learning session."""
    date: str
    difficulty_level: str | None = None
    persona_id: str | None = None
    topics: list[dict] = field(default_factory=list)
    items: list[LearningItem] = field(default_factory=list)
    flashcards: list[Flashcard] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    challenges: list[Challenge] = field(default_factory=list)

    def to_dict(self) -> dict:
        flashcards = self.flashcards or []
        questions = self.questions or []
        challenges = self.challenges or []

        if self.items:
            flashcards = []
            questions = []
            challenges = []
            for item in self.items:
                if item.item_type == "flashcard":
                    flashcards.append(
                        Flashcard(topic_id=item.topic_id, front=item.prompt, back=item.answer)
                    )
                elif item.item_type == "short_answer":
                    questions.append(
                        Question(
                            topic_id=item.topic_id,
                            question=item.prompt,
                            model_answer=item.answer,
                            hint=item.hint,
                        )
                    )
                elif item.item_type == "challenge":
                    challenges.append(
                        Challenge(
                            topic_id=item.topic_id,
                            scenario=item.prompt,
                            hint=item.hint,
                            solution=item.answer,
                        )
                    )

        return {
            "date": self.date,
            "difficulty_level": self.difficulty_level,
            "persona_id": self.persona_id,
            "topics": self.topics,
            "items": [item.to_dict() for item in self.items],
            "flashcards": [vars(f) for f in flashcards],
            "questions": [vars(q) for q in questions],
            "challenges": [vars(c) for c in challenges],
        }
