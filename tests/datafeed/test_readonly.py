"""Readonly allowlist: only the five methods reachable (MKT-09 first half)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.datafeed.readonly import (
    ALLOWED_METHODS,
    ReadonlyError,
    check_method,
    guarded_call,
)
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.live_paper import build_live_paper


def test_five_method_set() -> None:
    assert (
        frozenset(
            {
                "getAccountInfo",
                "logsSubscribe",
                "getTransaction",
                "subscribeNewToken",
                "subscribeMigration",
            }
        )
        == ALLOWED_METHODS
    )


def test_send_transaction_refused_before_call() -> None:
    called: list = []
    with pytest.raises(ReadonlyError, match="sendTransaction"):
        guarded_call("sendTransaction", lambda: called.append(True))
    assert called == []


def test_write_method_refused() -> None:
    with pytest.raises(ReadonlyError):
        check_method("getSignaturesForAddress-driven writes")


def test_allowed_pass() -> None:
    check_method("getAccountInfo")


@pytest.mark.parametrize(
    "method",
    [
        "sendTransaction",
        "signTransaction",
        "getSignaturesForAddress",
        "requestAirdrop",
        "subscribeAccount",
    ],
)
def test_write_methods_refused(method: str) -> None:
    """Every non-allowlisted RPC or portal method is refused by name."""
    with pytest.raises(ReadonlyError):
        check_method(method)


@pytest.mark.parametrize(
    "method",
    [
        "getAccountInfo",
        "logsSubscribe",
        "getTransaction",
        "subscribeNewToken",
        "subscribeMigration",
    ],
)
def test_allowlisted_methods_pass(method: str) -> None:
    check_method(method)


def test_root_feed_call_reaches_only_allowlisted(tmp_path: Path) -> None:
    """The live-paper root exposes only the five allowlisted methods (SC 10)."""

    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:

        async def _place(request):  # pragma: no cover - never called here
            raise AssertionError("feed_call must not place")

        desk = build_live_paper(
            mode="paper",
            store=store,
            clock=FixtureClock(0.0),
            place=_place,
            params={"momentum_breakout": {"breakout_bps": 100}},
        )
        seen: list[str] = []

        def _record(name: str) -> None:
            seen.append(name)

        assert desk.feed_call("getAccountInfo", _record, "acct") is None
        assert seen == ["acct"]
        assert desk.allowed_methods == ALLOWED_METHODS
        with pytest.raises(ReadonlyError):
            desk.feed_call("sendTransaction", lambda: seen.append("sent"))
        assert seen == ["acct"]
    finally:
        store.close()
