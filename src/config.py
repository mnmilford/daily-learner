"""Config loader — merges default config with user overrides."""

import os
import json
from pathlib import Path

import yaml


_DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "default-config.yaml"
_USER_CONFIG = Path("~/.daily-learner/config.yaml").expanduser()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _expand_paths(d: dict) -> dict:
    """Expand ~ in string values that look like paths."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _expand_paths(v)
        elif isinstance(v, str) and ("~" in v or v.startswith("/")):
            result[k] = os.path.expanduser(v)
        else:
            result[k] = v
    return result


def _resolve_api_key(config: dict) -> str:
    """Resolve the Gemini API key from the configured source."""
    source = config.get("llm", {}).get("api_key_source", "")

    if source == "openclaw_config":
        oc_path = Path("~/.openclaw/openclaw.json").expanduser()
        if oc_path.exists():
            oc = json.loads(oc_path.read_text())
            key = oc.get("env", {}).get("GEMINI_API_KEY", "")
            if key:
                return key

    # Fallback to environment variable
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key

    # Fallback to explicit key in config
    return config.get("llm", {}).get("api_key", "")


def load_config() -> dict:
    """Load and merge config, resolve paths and API key."""
    with open(_DEFAULT_CONFIG) as f:
        config = yaml.safe_load(f)

    if _USER_CONFIG.exists():
        with open(_USER_CONFIG) as f:
            user = yaml.safe_load(f) or {}
        config = _deep_merge(config, user)

    config = _expand_paths(config)
    config["llm"]["api_key"] = _resolve_api_key(config)
    return config


def resolve_date_path(template: str, date_str: str) -> str:
    """Replace {date} placeholder in a path template."""
    return template.replace("{date}", date_str)


def get_data_dir(config: dict) -> Path:
    """Get the runtime data directory, creating it if needed."""
    d = Path(config["data_dir"])
    d.mkdir(parents=True, exist_ok=True)
    return d
