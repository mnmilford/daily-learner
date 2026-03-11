"""Generate module — creates learning content from topics."""

from dataclasses import dataclass, field


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
    topics: list[dict] = field(default_factory=list)
    flashcards: list[Flashcard] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    challenges: list[Challenge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "topics": self.topics,
            "flashcards": [vars(f) for f in self.flashcards],
            "questions": [vars(q) for q in self.questions],
            "challenges": [vars(c) for c in self.challenges],
        }
