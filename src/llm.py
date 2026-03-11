"""Gemini REST API wrapper with structured JSON output support."""

import json
import time
import logging

import requests

log = logging.getLogger("daily-learner.llm")

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, config: dict):
        llm_cfg = config["llm"]
        self.api_key = llm_cfg["api_key"]
        self.model = llm_cfg["model"]
        self.max_output = llm_cfg.get("max_output_tokens", 4000)
        self.temperature = llm_cfg.get("temperature", 0.7)
        self.thinking_budget = llm_cfg.get("thinking_budget", 0)
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        if not self.api_key:
            raise LLMError("No Gemini API key configured. Set GEMINI_API_KEY or configure in openclaw.json")

    def generate(self, prompt: str, schema: dict | None = None) -> dict | str:
        """Call Gemini API. If schema is provided, returns parsed JSON dict. Otherwise returns text."""
        url = f"{_BASE_URL}/{self.model}:generateContent?key={self.api_key}"

        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_output,
                "thinkingConfig": {"thinkingBudget": self.thinking_budget},
            },
        }

        if schema:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = schema

        for attempt in range(3):
            try:
                resp = requests.post(url, json=body, timeout=60)

                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    log.warning(f"Rate limited, retrying in {wait}s...")
                    time.sleep(wait)
                    continue

                if resp.status_code != 200:
                    raise LLMError(f"Gemini API error {resp.status_code}: {resp.text[:500]}")

                data = resp.json()

                # Track token usage
                usage = data.get("usageMetadata", {})
                self.total_input_tokens += usage.get("promptTokenCount", 0)
                self.total_output_tokens += usage.get("candidatesTokenCount", 0)

                # Extract text from response
                candidates = data.get("candidates", [])
                if not candidates:
                    raise LLMError("No candidates in response")

                parts = candidates[0].get("content", {}).get("parts", [])
                text = ""
                for part in parts:
                    if "text" in part:
                        text = part["text"]
                        break

                if not text:
                    raise LLMError("No text in response")

                if schema:
                    return json.loads(text)
                return text

            except requests.exceptions.Timeout:
                if attempt < 2:
                    log.warning(f"Timeout, retrying ({attempt + 1}/3)...")
                    time.sleep(2)
                    continue
                raise LLMError("Gemini API timed out after 3 attempts")

        raise LLMError("Gemini API failed after 3 attempts")

    def usage_summary(self) -> str:
        return f"Tokens used: {self.total_input_tokens} in / {self.total_output_tokens} out"
