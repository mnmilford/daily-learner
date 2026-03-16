# Daily Learner

A CLI and web tool that turns your daily work into spaced-repetition learning sessions. It analyzes logs, memory files, and agent conversations, extracts learnable technical concepts via LLM, generates difficulty-aware study items, and delivers interactive review sessions with progress tracking.

Built for [OpenClaw](https://github.com/nicholasgasior/openclaw) users, but adaptable to any workflow that produces structured logs.

## How it works

1. **Nightly pipeline** (cron) ingests the day's data:
   - OpenClaw JSONL logs (errors, tool calls, model events)
   - Daily memory markdown files
   - Agent session transcripts (Telegram conversations, direct sessions)

2. **LLM extraction** identifies 5-10 learnable technical concepts and generates:
   - Flashcards
   - Multiple-choice questions
   - AI-evaluated short-answer prompts
   - CLI challenges

3. **Morning review** — interactive terminal session or web UI with spaced repetition:
   - New topics from yesterday + review queue from prior days
   - Sticky learner level / persona preferences
   - Short-answer grading modes: Off, BYOK, and a stubbed Built-in path for later hosted billing
   - Optional onboarding quiz to recommend a starting level
   - Assistive AI grading for short answers
   - Rate confidence 1-5 after each item
   - Spacing intervals: 1 → 3 → 7 → 14 → 30 days
   - Streak tracking

## Install

```bash
cd /path/to/daily-learner
pip install -e .
```

## Setup

1. Set your Gemini API key — either:
   - In `~/.openclaw/openclaw.json` under `env.GEMINI_API_KEY` (auto-detected), or
   - As environment variable `GEMINI_API_KEY`, or
   - In `~/.daily-learner/config.yaml` under `llm.api_key`

2. Configure data sources in `~/.daily-learner/config.yaml` (optional — defaults work for standard OpenClaw installs):
   ```yaml
   sources:
     memory_dir: "~/.openclaw/workspace/memory"
     openclaw_log_dir: "/tmp/openclaw"
     session_dir: "~/.openclaw/agents/main/sessions"
   ```

3. Set up the nightly cron (generates content after midnight):
   ```bash
   crontab -e
   # Add: 30 5 * * * /path/to/daily-learner/bin/learner-pipeline.sh >> ~/.daily-learner/logs/cron.log 2>&1
   ```

## Usage

```bash
# Generate content for a specific date (or yesterday by default)
learner generate 2026-03-09

# Run today's interactive session
learner

# Start the web UI
learner web --port 8090

# Review-only (skip new content)
learner review

# View progress stats
learner stats

# List all tracked topics
learner topics
```

## Stack

- Python 3.12, Click, Rich
- Gemini 2.5 Flash (structured JSON output, ~$0.01/day)
- JSON tracker (no database needed)
- System crontab for scheduling
- Flask web UI for preferences, onboarding, and mixed item types

## License

MIT
