"""Learner profile definitions and onboarding quiz data."""

from copy import deepcopy


_LEVELS = [
    {
        "id": "barely-computer",
        "label": "I barely know what a computer is",
        "short_label": "Brand new",
        "description": "Brand-new to technical concepts. Needs plain language, examples, and minimal jargon.",
        "generation_style": (
            "Use plain language, define jargon immediately, and ask concrete concept questions. "
            "Prefer worked examples over abstraction."
        ),
    },
    {
        "id": "follow-if-slowed-down",
        "label": "I can follow if you slow down",
        "short_label": "Guided learner",
        "description": "Early learner who can follow technical explanations when they are scaffolded.",
        "generation_style": (
            "Use friendly but direct explanations, introduce one new idea at a time, and include hints "
            "that anchor the learner to real examples."
        ),
    },
    {
        "id": "use-tools-not-explain",
        "label": "I can use the tools, not explain them",
        "short_label": "Builder in progress",
        "description": (
            "Passionate self-taught builders and vibecoders who can use the tooling but are still "
            "building the underlying mental model."
        ),
        "generation_style": (
            "Assume hands-on familiarity with tools, but still explain the why behind the steps. "
            "Use practical scenarios plus gentle conceptual scaffolding."
        ),
    },
    {
        "id": "work-with-this-regularly",
        "label": "I work with this stuff regularly",
        "short_label": "Working professional",
        "description": (
            "Regular practitioners and working professionals in industry who use these systems on the job, "
            "but are not necessarily researchers."
        ),
        "generation_style": (
            "Use realistic professional scenarios, concise explanations, and tradeoff-oriented questions. "
            "Do not over-explain familiar operational basics."
        ),
    },
    {
        "id": "practicing-ai-researcher",
        "label": "I am a practicing AI researcher",
        "short_label": "Research depth",
        "description": "Advanced learner comfortable with abstract reasoning, caveats, and research language.",
        "generation_style": (
            "Use concise, high-density explanations, emphasize transfer and edge cases, and assume strong "
            "technical literacy."
        ),
    },
]

_PERSONAS = [
    {
        "id": "lil-mike",
        "label": "Lil Mike",
        "description": (
            "Observant, curious, playful, and slightly eccentric. Warm and human, never parody, never smug."
        ),
        "system_style": (
            "Write like an observant guide with a little personality. Stay crisp, encouraging, and a touch "
            "playful. Avoid camp, parody, and insider references that depend on private context."
        ),
    }
]

_QUIZ = [
    {
        "id": "terminal_comfort",
        "prompt": "How comfortable are you in a terminal?",
        "options": [
            {"id": "brand_new", "label": "I avoid the terminal unless I absolutely have to.", "score": 0},
            {"id": "follow_guides", "label": "I can follow commands from a guide, but I do not improvise much.", "score": 1},
            {"id": "tool_user", "label": "I use command-line tools often, but I cannot always explain why commands work.", "score": 2},
            {"id": "ops_regular", "label": "I use the terminal regularly for work or serious projects.", "score": 3},
            {"id": "deep_systems", "label": "I am comfortable debugging systems and reading unfamiliar docs quickly.", "score": 4},
        ],
    },
    {
        "id": "coding_debugging",
        "prompt": "What feels most like your coding/debugging experience?",
        "options": [
            {"id": "new", "label": "I am still learning what code is doing line by line.", "score": 0},
            {"id": "guided", "label": "I can edit code with guidance, but debugging still feels mysterious.", "score": 1},
            {"id": "builder", "label": "I can build things with tools and AI help, but my explanations lag behind my output.", "score": 2},
            {"id": "professional", "label": "I debug and ship code or systems regularly.", "score": 3},
            {"id": "advanced", "label": "I can reason about systems, abstractions, and failure modes in depth.", "score": 4},
        ],
    },
    {
        "id": "ai_ml_depth",
        "prompt": "Which statement best fits your AI/ML background?",
        "options": [
            {"id": "heard_terms", "label": "I know the buzzwords, but most of the mechanics are fuzzy.", "score": 0},
            {"id": "can_follow", "label": "I can follow explanations about models if they are paced well.", "score": 1},
            {"id": "build_with_tools", "label": "I use AI tools a lot, but I am still building the conceptual model underneath them.", "score": 2},
            {"id": "practitioner", "label": "I work with AI systems professionally.", "score": 3},
            {"id": "research", "label": "I read papers or design experiments as part of my work.", "score": 4},
        ],
    },
    {
        "id": "web_api_mental_model",
        "prompt": "How do APIs and web systems feel to you?",
        "options": [
            {"id": "opaque", "label": "Mostly opaque. I copy examples and hope.", "score": 0},
            {"id": "emerging", "label": "I understand the broad shape, but the details still blur together.", "score": 1},
            {"id": "practical", "label": "I can use APIs and services productively, even if I cannot teach the topic cleanly yet.", "score": 2},
            {"id": "professional", "label": "I integrate and troubleshoot APIs or services as part of real work.", "score": 3},
            {"id": "expert", "label": "I reason comfortably about protocols, tradeoffs, and architecture.", "score": 4},
        ],
    },
]


def get_levels() -> list[dict]:
    return deepcopy(_LEVELS)


def get_level(level_id: str) -> dict:
    for level in _LEVELS:
        if level["id"] == level_id:
            return deepcopy(level)
    return deepcopy(_LEVELS[1])


def get_personas() -> list[dict]:
    return deepcopy(_PERSONAS)


def get_persona(persona_id: str) -> dict:
    for persona in _PERSONAS:
        if persona["id"] == persona_id:
            return deepcopy(persona)
    return deepcopy(_PERSONAS[0])


def get_onboarding_quiz() -> list[dict]:
    return deepcopy(_QUIZ)


def score_onboarding(answers: dict[str, str]) -> dict:
    level_scores = []
    domain_scores: dict[str, int] = {}

    for question in _QUIZ:
        selected = answers.get(question["id"])
        for option in question["options"]:
            if option["id"] == selected:
                level_scores.append(option["score"])
                domain_scores[question["id"]] = option["score"]
                break

    if not level_scores:
        level_index = 1
    else:
        avg_score = sum(level_scores) / len(level_scores)
        level_index = max(0, min(round(avg_score), len(_LEVELS) - 1))

    recommended = deepcopy(_LEVELS[level_index])
    return {
        "recommended_level": recommended,
        "domain_scores": domain_scores,
        "answered_questions": len(level_scores),
    }
