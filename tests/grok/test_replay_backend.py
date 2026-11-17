"""Replay backend for the Grok gateway: recorded hashes answer, misses raise (GRK-08).

The replay transport reuses ``ReplayLlm`` and the gateway's own request key,
so a live recording and its replay share one hash. It has no HTTP client.
Sockets are blocked for the whole module to prove no network path exists.
A request that needs a call and has no record raises ``ReplayMissingRecord``
before the gateway runs: it never reaches the breaker, the cache or the
fallback ladder.
"""

from __future__ import annotations

import asyncio
import socket
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.errors import ReplayMissingRecord
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import Candidate, GrokGateway, GrokRequest, _request_key, sanitize
from pumpgrok.grok.transport import ReplayTransport, admit_replay
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.recorder import ReplayLlm

START = 1_800_000_000.0
PROMPT_SHA = "b" * 64
CONTENT = '{"verdict":"ok"}'


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("replay must never open a connection")

    monkeypatch.setattr(asyncio.BaseEventLoop, "create_connection", blocked)
    monkeypatch.setattr(asyncio.BaseEventLoop, "sock_connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def _candidate(prerank: str = "0.8") -> Candidate:
    return Candidate(
        mint="MINT1",
        created_at=START - 600,
        first_trade_at=START - 300,
        unique_buyers=9,
        prerank=Decimal(prerank),
        last_decision_at=None,
    )


def _request(text: str, *, event_id: str = "ev-1", prerank: str = "0.8") -> GrokRequest:
    return GrokRequest(
        event_id=event_id,
        agent="narrative",
        model="grok-test",
        prompt_sha=PROMPT_SHA,
        schema="verdict.v1",
        input={"mint": "MINT1"},
        text=text,
        candidate=_candidate(prerank),
    )


def _key(request: GrokRequest) -> str:
    return _request_key(request, sanitize(request.text))


def _row(request_hash: str, outcome: str, response: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_hash": request_hash,
        "outcome": outcome,
        "latency_s": 0.5,
        "response": response,
    }


def _stack(
    tmp_path: Path, clock: FixtureClock, rows: list[dict[str, Any]]
) -> tuple[GrokGateway, ReplayTransport, LayeredBudget]:
    replay = ReplayTransport(ReplayLlm.from_rows(rows))
    budget = LayeredBudget(tmp_path / "budget.sqlite", clock)
    gateway = GrokGateway(
        clock=clock,
        transport=replay,
        cache=ResponseCache(tmp_path / "cache.sqlite", clock),
        budget=budget,
    )
    return gateway, replay, budget


async def test_recorded_hash_answers_without_network(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    request = _request("market-a")
    rows = [_row(_key(request), "ok", {"content": CONTENT})]
    gateway, replay, _ = _stack(tmp_path, clock, rows)

    outcome = await admit_replay(gateway, replay, request, clock=clock)

    assert outcome.status == "fresh"
    assert outcome.response == CONTENT


async def test_recorded_timeout_and_error_replay_as_failures(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    timed = _request("market-timeout", event_id="ev-t")
    failed = _request("market-error", event_id="ev-e")
    rows = [
        _row(_key(timed), "timeout", {"note": "recorded"}),
        _row(_key(failed), "error", {"note": "recorded"}),
    ]
    gateway, replay, _ = _stack(tmp_path, clock, rows)

    timeout_outcome = await admit_replay(gateway, replay, timed, clock=clock)
    error_outcome = await admit_replay(gateway, replay, failed, clock=clock)

    assert (timeout_outcome.status, timeout_outcome.reason) == ("rule_fallback", "timeout")
    assert (error_outcome.status, error_outcome.reason) == ("rule_fallback", "transport_error")


async def test_recorded_ok_without_content_is_a_failure_not_an_answer(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    request = _request("market-nocontent")
    rows = [_row(_key(request), "ok", {"model": "grok-replay"})]
    gateway, replay, _ = _stack(tmp_path, clock, rows)

    outcome = await admit_replay(gateway, replay, request, clock=clock)

    assert outcome.status == "rule_fallback"
    assert outcome.response is None


async def test_miss_raises_naming_the_hash_and_spends_nothing(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    request = _request("never-recorded")
    gateway, replay, budget = _stack(tmp_path, clock, [])

    with pytest.raises(ReplayMissingRecord) as excinfo:
        await admit_replay(gateway, replay, request, clock=clock)

    assert excinfo.value.fields["request_hash"] == _key(request)
    assert sum(budget.usage().values()) == 0


async def test_miss_escapes_even_when_the_breaker_is_open(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    failing = [_row(_key(_request(f"fail-{i}")), "error", {}) for i in range(3)]
    gateway, replay, _ = _stack(tmp_path, clock, failing)
    for index in range(3):
        await admit_replay(gateway, replay, _request(f"fail-{index}"), clock=clock)
    assert gateway.llm_available is False

    with pytest.raises(ReplayMissingRecord):
        await admit_replay(gateway, replay, _request("unseen"), clock=clock)


async def test_prefilter_skip_needs_no_record(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    gateway, replay, _ = _stack(tmp_path, clock, [])

    outcome = await admit_replay(gateway, replay, _request("low-rank", prerank="0.1"), clock=clock)

    assert outcome.status == "prefilter_skip"


async def test_second_identical_request_is_served_from_cache_without_a_charge(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    request = _request("market-hit")
    rows = [_row(_key(request), "ok", {"content": CONTENT})]
    gateway, replay, budget = _stack(tmp_path, clock, rows)

    first = await admit_replay(gateway, replay, request, clock=clock)
    again = _request("market-hit", event_id="ev-2")
    second = await admit_replay(gateway, replay, again, clock=clock)

    assert first.status == "fresh"
    assert second.status == "cache_hit"
    assert budget.usage()["minute"] == 1
