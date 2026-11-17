"""Response cache: canonical key, per-agent TTLs, negative cache, LRU, persistence (GRK-02)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from pumpgrok.grok.cache import (
    MAX_ROWS,
    NEGATIVE_TTL_S,
    TTL_S_BY_AGENT,
    CacheUnavailable,
    ResponseCache,
    cache_key,
)
from pumpgrok.replay.clock import FixtureClock

START = 1_800_000_000.0
PROMPT_SHA = "c" * 64


def key_for(name: str) -> str:
    return cache_key(
        agent="narrative",
        model="grok-test",
        prompt_sha=PROMPT_SHA,
        schema="verdict.v1",
        sanitizer_version="1",
        fields={"mint": name, "prerank": Decimal("0.80")},
    )


def test_ttls_are_the_reviewed_values() -> None:
    assert TTL_S_BY_AGENT == {
        "narrative": 86400,
        "auditor": 300,
        "timing": 900,
        "checker": 60,
    }
    assert NEGATIVE_TTL_S == 30
    assert MAX_ROWS == 5000


@pytest.mark.parametrize(("agent", "ttl"), sorted(TTL_S_BY_AGENT.items()))
def test_success_entry_expires_at_its_agent_ttl(tmp_path: Path, agent: str, ttl: int) -> None:
    clock = FixtureClock(start=START)
    cache = ResponseCache(tmp_path / "c.sqlite", clock)
    cache.put_ok(key_for(agent), agent=agent, response="verdict")

    clock.advance_to(START + ttl - 1)
    hit = cache.get(key_for(agent))
    assert hit is not None
    assert hit.status == "ok"
    assert hit.response == "verdict"

    clock.advance_to(START + ttl)
    assert cache.get(key_for(agent)) is None


def test_negative_entry_expires_after_thirty_seconds(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    cache = ResponseCache(tmp_path / "c.sqlite", clock)
    cache.put_error(key_for("neg"), agent="checker")

    clock.advance_to(START + NEGATIVE_TTL_S - 1)
    hit = cache.get(key_for("neg"))
    assert hit is not None
    assert hit.status == "error"
    assert hit.response is None

    clock.advance_to(START + NEGATIVE_TTL_S)
    assert cache.get(key_for("neg")) is None


def test_unknown_agent_is_refused(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite", FixtureClock(start=START))
    with pytest.raises(ValueError):
        cache.put_ok(key_for("x"), agent="oracle", response="nope")


def test_lru_evicts_least_recently_used_row(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    cache = ResponseCache(tmp_path / "c.sqlite", clock, max_rows=3)
    for name in ("k1", "k2", "k3"):
        cache.put_ok(key_for(name), agent="narrative", response=name)
    assert cache.get(key_for("k1")) is not None  # touch k1; k2 is now least recent
    cache.put_ok(key_for("k4"), agent="narrative", response="k4")

    assert cache.count() == 3
    assert cache.get(key_for("k2")) is None
    assert cache.get(key_for("k1")) is not None
    assert cache.get(key_for("k3")) is not None
    assert cache.get(key_for("k4")) is not None


def test_expired_rows_are_purged_on_write(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    cache = ResponseCache(tmp_path / "c.sqlite", clock)
    cache.put_error(key_for("gone"), agent="checker")
    clock.advance_to(START + NEGATIVE_TTL_S)
    cache.put_ok(key_for("fresh"), agent="checker", response="v")

    assert cache.count() == 1


def test_entries_survive_reopen(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    ResponseCache(tmp_path / "c.sqlite", clock).put_ok(
        key_for("persist"), agent="narrative", response="kept"
    )

    reopened = ResponseCache(tmp_path / "c.sqlite", clock)
    hit = reopened.get(key_for("persist"))
    assert hit is not None
    assert hit.response == "kept"


def test_unopenable_store_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(CacheUnavailable):
        ResponseCache(tmp_path / "missing-dir" / "c.sqlite", FixtureClock(start=START))
