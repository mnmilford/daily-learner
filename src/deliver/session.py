"""Interactive review session using rich terminal UI."""

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.prompt import Prompt, IntPrompt
from rich.text import Text

from src.session_items import normalize_session_items
from src.tracker.tracker import Tracker

console = Console()

_CONFIDENCE_COLORS = {1: "red", 2: "yellow", 3: "bright_yellow", 4: "green", 5: "bright_green"}


def _load_session(session_path: str) -> dict | None:
    """Load a session JSON file."""
    p = Path(session_path)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def _ask_confidence() -> int:
    """Prompt for confidence rating 1-5."""
    labels = Text()
    for i in range(1, 6):
        color = _CONFIDENCE_COLORS[i]
        labels.append(f"  {i}", style=f"bold {color}")
    labels.append("  (1=no clue, 5=nailed it)")
    console.print(labels)
    while True:
        try:
            val = IntPrompt.ask("[bold]Confidence[/bold]", default=3)
            if 1 <= val <= 5:
                return val
            console.print("[red]Please enter 1-5[/red]")
        except (ValueError, KeyboardInterrupt):
            return 3


def _load_all_sessions(config: dict) -> list[dict]:
    """Load all available session files."""
    from src.config import get_data_dir
    session_dir = get_data_dir(config) / "sessions"
    sessions = []
    if session_dir.exists():
        for f in sorted(session_dir.glob("*.json")):
            try:
                sessions.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
    return sessions


def _select_items(session: dict, tracker: Tracker, today: str, config: dict) -> dict:
    """Select which items to show based on review ratios."""
    review_cfg = config.get("review", {})
    review_ratio = review_cfg.get("review_ratio", 0.25)

    # Get new topics from today's session
    session_topic_ids = [t["id"] for t in session.get("topics", [])]
    new_ids = set(tracker.get_new_topics(today)) & set(session_topic_ids)

    # Get review queue
    review_ids = set(tracker.get_review_queue(today)) - new_ids

    # Build content lookups from ALL session files (so review items have content)
    all_sessions = _load_all_sessions(config)
    topic_lookup = {}
    items_by_topic = {}

    for s in all_sessions:
        for t in s.get("topics", []):
            if t["id"] not in topic_lookup:
                topic_lookup[t["id"]] = t
        for item in normalize_session_items(s):
            items_by_topic.setdefault(item["topic_id"], []).append(item)

    # Calculate how many of each
    total_items = sum(len(v) for v in items_by_topic.values())
    max_items = max(total_items, 12)

    # Select topic IDs to include — only those with actual content
    selected_new = [tid for tid in new_ids if tid in items_by_topic]
    selected_review = [tid for tid in review_ids if tid in items_by_topic]
    selected_review = selected_review[:max(2, int(max_items * review_ratio))]
    selected_ids = selected_new + selected_review

    return {
        "topic_ids": selected_ids,
        "topic_lookup": topic_lookup,
        "items_by_topic": items_by_topic,
        "new_ids": new_ids,
        "review_ids": set(selected_review),
    }


def run_session(session_path: str, tracker: Tracker, today: str, config: dict, review_only: bool = False):
    """Run an interactive review session."""
    session = _load_session(session_path)
    if not session:
        console.print("[red]No session file found. Run 'learner generate' first.[/red]")
        return

    items = _select_items(session, tracker, today, config)
    topic_ids = items["topic_ids"]

    if review_only:
        topic_ids = [tid for tid in topic_ids if tid in items["review_ids"]]
        if not topic_ids:
            console.print("[yellow]No topics due for review today.[/yellow]")
            return

    if not topic_ids:
        console.print("[yellow]No content available for today. Run 'learner generate' first.[/yellow]")
        return

    stats = tracker.get_stats()

    # Welcome panel
    streak_text = f"Streak: {stats['streak']} day{'s' if stats['streak'] != 1 else ''}" if stats['streak'] else "Start your streak!"
    console.print(Panel(
        f"[bold]Daily Learner[/bold] — {today}\n"
        f"Topics: {len(topic_ids)} | {streak_text}",
        style="bright_blue",
    ))

    # Count total items
    total = 0
    for tid in topic_ids:
        total += len(items["items_by_topic"].get(tid, []))

    current = 0
    confidences = []

    try:
        for tid in topic_ids:
            topic_info = items["topic_lookup"].get(tid, {})
            badge = "[green]NEW[/green]" if tid in items["new_ids"] else "[blue]REVIEW[/blue]"

            console.print(Rule(f"{badge} {topic_info.get('title', tid)}"))

            if topic_info.get("summary"):
                console.print(f"[dim]{topic_info['summary']}[/dim]\n")

            for item in items["items_by_topic"].get(tid, []):
                current += 1
                console.print(f"[dim]({current}/{total})[/dim]")
                title = item.get("type_label", item["item_type"].replace("_", " ").title())

                if item["item_type"] == "flashcard":
                    console.print(Panel(item["prompt"], title=title, border_style="cyan"))
                    Prompt.ask("[dim]Press Enter to reveal[/dim]", default="")
                    console.print(Panel(item["answer"], title="Answer", border_style="green"))
                elif item["item_type"] == "multiple_choice":
                    option_lines = [f"{idx + 1}. {choice}" for idx, choice in enumerate(item.get("choices", []))]
                    prompt_text = item["prompt"]
                    if item.get("hint"):
                        prompt_text += f"\n\n[dim]Hint: {item['hint']}[/dim]"
                    if option_lines:
                        prompt_text += "\n\n" + "\n".join(option_lines)
                    console.print(Panel(prompt_text, title=title, border_style="yellow"))
                    Prompt.ask("[bold]Your answer (1-4)[/bold]", default="1")
                    rationale = item.get("rationale", "")
                    answer_text = item["answer"]
                    if rationale:
                        answer_text += f"\n\nWhy: {rationale}"
                    console.print(Panel(answer_text, title="Answer", border_style="green"))
                elif item["item_type"] == "short_answer":
                    hint_text = f"\n[dim]Hint: {item.get('hint', '')}[/dim]" if item.get("hint") else ""
                    console.print(Panel(item["prompt"] + hint_text, title=title, border_style="yellow"))
                    Prompt.ask("[bold]Your answer[/bold]", default="(skipped)")
                    console.print(Panel(item["answer"], title="Model Answer", border_style="green"))
                else:
                    prompt_text = item["prompt"]
                    if item.get("hint"):
                        prompt_text += f"\n\n[dim]Hint: {item['hint']}[/dim]"
                    console.print(Panel(prompt_text, title=title, border_style="magenta"))
                    Prompt.ask("[dim]Try it in your terminal, then press Enter[/dim]", default="")
                    console.print(Panel(item["answer"], title="Solution", border_style="green"))

                c = _ask_confidence()
                confidences.append(c)
                tracker.record_review(tid, c, today)
                console.print()

    except KeyboardInterrupt:
        console.print("\n[yellow]Session interrupted.[/yellow]")

    # Summary
    tracker.record_session(today)
    updated_stats = tracker.get_stats()

    avg_conf = sum(confidences) / len(confidences) if confidences else 0

    console.print(Rule("Session Complete"))
    summary = Table(show_header=False, box=None)
    summary.add_row("Topics covered", str(len(topic_ids)))
    summary.add_row("Items reviewed", str(len(confidences)))
    summary.add_row("Avg confidence", f"{avg_conf:.1f}/5")
    summary.add_row("Streak", f"{updated_stats['streak']} day{'s' if updated_stats['streak'] != 1 else ''}")
    summary.add_row("Total topics tracked", str(updated_stats['total_topics']))
    console.print(Panel(summary, title="Summary", border_style="bright_blue"))
