"""CLI entry point for Daily Learner."""

from datetime import datetime, timedelta, timezone

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import load_config, get_data_dir

console = Console()
_CT = timezone(timedelta(hours=-5))


def _today_ct() -> str:
    return datetime.now(_CT).strftime("%Y-%m-%d")


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """Daily Learner — spaced repetition from your daily work."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(session_cmd)


@main.command("review")
def review_cmd():
    """Review-only session (skip new content)."""
    _run_session(review_only=True)


@main.command("session")
def session_cmd():
    """Run today's interactive learning session."""
    _run_session(review_only=False)


def _run_session(review_only: bool):
    """Common session runner."""
    config = load_config()
    today = _today_ct()

    from src.tracker.tracker import Tracker
    from src.deliver.session import run_session

    tracker = Tracker(config)
    data_dir = get_data_dir(config)

    # Find the most recent session file
    session_dir = data_dir / "sessions"
    session_path = session_dir / f"{today}.json"

    if not session_path.exists():
        # Try yesterday
        yesterday = (datetime.now(_CT) - timedelta(days=1)).strftime("%Y-%m-%d")
        session_path = session_dir / f"{yesterday}.json"

    if not session_path.exists():
        # Find any recent session
        if session_dir.exists():
            files = sorted(session_dir.glob("*.json"), reverse=True)
            if files:
                session_path = files[0]

    run_session(str(session_path), tracker, today, config, review_only=review_only)


@main.command("generate")
@click.argument("date", required=False)
def generate_cmd(date):
    """Run the pipeline for a specific date (default: yesterday)."""
    from src.pipeline import run_pipeline

    result = run_pipeline(date)
    if result:
        console.print(f"[green]Session generated:[/green] {result}")
    else:
        console.print("[yellow]No content generated (no activities found).[/yellow]")


@main.command("stats")
def stats_cmd():
    """Show progress statistics."""
    config = load_config()
    from src.tracker.tracker import Tracker
    tracker = Tracker(config)
    stats = tracker.get_stats()

    table = Table(title="Daily Learner Stats", show_header=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total topics", str(stats["total_topics"]))
    table.add_row("Reviewed", str(stats["reviewed"]))
    table.add_row("Graduated", str(stats["graduated"]))
    table.add_row("Unreviewed", str(stats["unreviewed"]))
    table.add_row("Avg confidence", f"{stats['avg_confidence']}/5")
    table.add_row("Current streak", f"{stats['streak']} day{'s' if stats['streak'] != 1 else ''}")
    table.add_row("Total sessions", str(stats["total_sessions"]))

    # Review queue
    today = _today_ct()
    queue = tracker.get_review_queue(today)
    table.add_row("Review queue", str(len(queue)))

    console.print(table)


@main.command("topics")
def topics_cmd():
    """List all tracked topics with status."""
    config = load_config()
    from src.tracker.tracker import Tracker
    tracker = Tracker(config)
    topic_list = tracker.get_topic_list()

    if not topic_list:
        console.print("[yellow]No topics tracked yet. Run 'learner generate' first.[/yellow]")
        return

    table = Table(title="Tracked Topics")
    table.add_column("Topic ID", style="cyan")
    table.add_column("Confidence", justify="center")
    table.add_column("Reviews", justify="center")
    table.add_column("Next Review")
    table.add_column("Status")

    for t in topic_list:
        conf = t["confidence"]
        conf_color = {0: "dim", 1: "red", 2: "yellow", 3: "bright_yellow", 4: "green", 5: "bright_green"}.get(conf, "white")

        status = "[bright_green]GRADUATED" if t["graduated"] else "[dim]active"
        table.add_row(
            t["id"],
            f"[{conf_color}]{conf}/5[/{conf_color}]",
            str(t["times_reviewed"]),
            t.get("next_review", "-"),
            status,
        )

    console.print(table)


if __name__ == "__main__":
    main()
