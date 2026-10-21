"""Deterministic JSON and idempotency keys (interfaces.md 2.4, R28).

`canonical_json` is also the byte form the ledger hash chain is computed over.
Floats are rejected: money is int, ratios are Decimal (serialised as str).
There is no `default=str` coercion: untrusted leaves fail loudly instead.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any


def _normalize(value: object, path: str) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, float):  # pragma: no cover - bool/int guard above excludes float
            raise TypeError(f"{path}: float leaves are forbidden")
        return value
    if isinstance(value, float):
        raise TypeError(f"{path}: float leaves are forbidden (money is int, ratios are Decimal)")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise TypeError(f"{path}: non-finite Decimal is forbidden")
        return str(value)
    if isinstance(value, list):
        return [_normalize(v, f"{path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"{path}: keys must be str, got {type(k).__name__}")
            normalized[k] = _normalize(v, f"{path}.{k}")
        return normalized
    raise TypeError(f"{path}: leaf of type {type(value).__name__} is not JSON-scalar")


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Sorted keys, no whitespace, ints/strings/bools/None/lists/dicts only.

    Decimal is serialised as str (R28). Float leaves and any other type raise
    TypeError; no `default=str` coercion.
    """
    return json.dumps(_normalize(dict(payload), "$"), sort_keys=True, separators=(",", ":"))


def derive_idempotency_key(
    tool: str,
    bot: str,
    payload: Mapping[str, Any],
    *,
    scope: str | None = None,
) -> str:
    """sha256 over (tool, bot, scope, canonical payload) -> 32 hex chars.

    Fields named `correlation_id` are excluded so that a retry under a new
    correlation id still collapses onto the first attempt.
    """
    body = {k: v for k, v in payload.items() if k != "correlation_id"}
    digest = hashlib.sha256(
        canonical_json({"tool": tool, "bot": bot, "scope": scope, "payload": body}).encode()
    ).hexdigest()
    return digest[:32]


def exec_place_key(ticket_id: str, side: str, decision_id: str) -> str:
    """R23: exec.place idempotency over (ticket_id, side, decision_id) only.

    Payload, tool and bot are excluded, so a repeat returns the first Fill.
    `derive_idempotency_key` is unchanged (replay hash stability).
    """
    digest = hashlib.sha256(
        canonical_json(
            {"ticket_id": ticket_id, "side": str(side), "decision_id": decision_id}
        ).encode()
    ).hexdigest()
    return digest[:32]


def exec_cancel_key(order_id: str) -> str:
    """exec.cancel idempotency over the order id only."""
    digest = hashlib.sha256(canonical_json({"order_id": order_id}).encode()).hexdigest()
    return digest[:32]
