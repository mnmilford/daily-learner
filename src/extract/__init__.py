"""Extract module — identifies learnable topics from activities."""

from dataclasses import dataclass, field


@dataclass
class Topic:
    """A learnable concept extracted from daily activities."""
    id: str              # Stable slug, e.g. "gemini-structured-output"
    title: str           # Human-readable title
    domain: str          # Category: api, architecture, ml-fundamentals, etc.
    summary: str         # 2-3 sentence explanation
    source_hint: str     # Which activity surfaced this
    is_bonus: bool = False  # True if injected as related topic
    tags: list[str] = field(default_factory=list)
