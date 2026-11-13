"""Strict parsing of model answers (GRK-05, output side).

Input sanitization (NFKC, control and format characters removed) lives in
``pumpgrok.grok.gateway.sanitize`` because the cache key depends on it.

An answer is accepted only when the whole reply is exactly one JSON object,
with no duplicate keys, no non-finite numbers, and no keys beyond the
result model. Prose, code fences and trailing text are refused. Error
messages never echo model text, so an injected key name cannot reach logs.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from pumpgrok.core.errors import PumpgrokError

__all__ = ["StrictParseError", "parse_strict"]


class StrictParseError(PumpgrokError):
    """A model answer is not exactly one valid object of the requested schema."""

    code = "grok_answer_invalid"


def _reject_constant(name: str) -> Any:
    raise StrictParseError("non-finite number in model answer", constant=name)


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictParseError("duplicate key in model answer")
        result[key] = value
    return result


def parse_strict[T: BaseModel](raw: str, model: type[T]) -> T:
    """Parse ``raw`` as one JSON object that validates against ``model`` exactly."""
    if not isinstance(raw, str):
        raise StrictParseError("model answer is not text")
    try:
        data: Any = json.loads(
            raw,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except StrictParseError:
        raise
    except json.JSONDecodeError:
        raise StrictParseError("model answer is not JSON") from None
    if not isinstance(data, dict):
        raise StrictParseError("model answer is not a JSON object")
    allowed = set(model.model_fields)
    extra = [key for key in data if key not in allowed]
    if extra:
        raise StrictParseError("model answer has keys outside the schema", extra=len(extra))
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise StrictParseError(
            "model answer violates the schema", errors=exc.error_count()
        ) from None
