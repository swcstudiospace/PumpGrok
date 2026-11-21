"""Sanitizer plus strict JSON parse (GRK-02, T-14-01-01).

Untrusted model output is parsed as data only. Trailing text, code fences,
or an injected instruction string inside the payload make the parse fail;
the transport result is rejected rather than repaired.
"""

from __future__ import annotations

import json
from typing import Any

_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard previous",
    "system:",
    "you are now",
)


class StrictParseError(ValueError):
    """Model output was not a single strict JSON object free of injection."""


def sanitize_prompt(text: str) -> str:
    """Trim surrounding whitespace only. Content is the caller's; parse enforces shape."""
    return text.strip()


def _has_injection(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in _INJECTION_MARKERS)
    if isinstance(value, dict):
        return any(_has_injection(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_injection(v) for v in value)
    return False


def parse_strict_json(text: str) -> dict[str, Any]:
    """Parse exactly one JSON object. Anything else raises StrictParseError."""
    candidate = text.strip()
    if candidate.startswith("```"):
        raise StrictParseError("code-fenced JSON is not accepted")
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise StrictParseError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise StrictParseError("top-level JSON must be an object")
    if _has_injection(parsed):
        raise StrictParseError("injected instruction in payload")
    return parsed
