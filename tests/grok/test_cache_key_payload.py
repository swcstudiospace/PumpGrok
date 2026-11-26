<<<<<<< HEAD
"""Cache key payload is ints/strings only; floats raise TypeError."""

import pytest

from pumpgrok.grok.cache import build_cache_key_payload, canonical_request_hash


def test_key_payload_types() -> None:
    payload = build_cache_key_payload(
        agent="scout", model="fast", prompt_hash="abc", consequence_id="c-1"
    )
    assert payload["version"] == 1
    assert all(isinstance(v, (int, str)) for v in payload.values())


def test_float_in_payload_raises() -> None:
    with pytest.raises(TypeError):
        canonical_request_hash({"version": 1, "ratio": 0.5})  # type: ignore[dict-item]


def test_hash_is_stable_and_distinct() -> None:
    a = build_cache_key_payload(
        agent="scout", model="fast", prompt_hash="abc", consequence_id="c-1"
    )
    b = build_cache_key_payload(
        agent="scout", model="fast", prompt_hash="xyz", consequence_id="c-1"
    )
    assert canonical_request_hash(a) == canonical_request_hash(dict(a))
    assert canonical_request_hash(a) != canonical_request_hash(b)
    assert len(canonical_request_hash(a)) == 64
=======
"""Cache key payload: reviewed ints and strings only, hashed by canonical_request_hash (GRK-02)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from pumpgrok.grok.cache import cache_key, scalar_fields
from pumpgrok.replay.recorder import canonical_request_hash

PROMPT_SHA = "a" * 64


def base_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "agent": "narrative",
        "model": "grok-test",
        "prompt_sha": PROMPT_SHA,
        "schema": "verdict.v1",
        "sanitizer_version": "1",
        "fields": {"mint": "M1", "buyers": 9, "prerank": Decimal("0.80")},
    }
    kwargs.update(overrides)
    return kwargs


def test_key_is_canonical_request_hash_over_the_reviewed_payload() -> None:
    expected = canonical_request_hash(
        {
            "kind": "event",
            "agent": "narrative",
            "model": "grok-test",
            "prompt_sha": PROMPT_SHA,
            "schema": "verdict.v1",
            "sanitizer_version": "1",
            "input": {"mint": "M1", "buyers": 9, "prerank": "0.80"},
        }
    )
    assert cache_key(**base_kwargs()) == expected


def test_decimal_is_stringified_and_scalars_pass_through() -> None:
    assert scalar_fields({"a": 1, "b": "x", "c": Decimal("0.50")}) == {
        "a": 1,
        "b": "x",
        "c": "0.50",
    }


def test_payload_holds_only_ints_and_strings() -> None:
    payload = scalar_fields({"a": 1, "b": "x", "c": Decimal("2.5")})
    assert all(type(value) in (int, str) for value in payload.values())


@pytest.mark.parametrize(
    "bad",
    [1.5, True, None, [1], {"x": 1}, Decimal("NaN"), Decimal("Infinity")],
)
def test_unreviewed_leaf_types_are_refused(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        scalar_fields({"field": bad})


@pytest.mark.parametrize("name", ["span_id", "seed", "created_at", "ts", "correlation_id", ""])
def test_fields_canonical_request_hash_would_strip_are_refused(name: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        scalar_fields({name: "v"})


@pytest.mark.parametrize(
    "override",
    [
        {"agent": "auditor"},
        {"model": "grok-other"},
        {"prompt_sha": "d" * 64},
        {"schema": "verdict.v2"},
        {"sanitizer_version": "2"},
        {"fields": {"mint": "M2", "buyers": 9, "prerank": Decimal("0.80")}},
        {"fields": {"mint": "M1", "buyers": 10, "prerank": Decimal("0.80")}},
        {"fields": {"mint": "M1", "buyers": 9, "prerank": Decimal("0.81")}},
    ],
)
def test_every_keyed_field_changes_the_key(override: dict[str, Any]) -> None:
    assert cache_key(**base_kwargs(**override)) != cache_key(**base_kwargs())


def test_field_order_does_not_change_the_key() -> None:
    first = cache_key(**base_kwargs(fields={"a": 1, "b": "x"}))
    second = cache_key(**base_kwargs(fields={"b": "x", "a": 1}))
    assert first == second


def test_sanitizer_version_is_part_of_the_key() -> None:
    assert cache_key(**base_kwargs(sanitizer_version="1")) != cache_key(
        **base_kwargs(sanitizer_version="1.1")
    )
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
