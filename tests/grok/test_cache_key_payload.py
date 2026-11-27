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
