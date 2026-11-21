"""Readonly allowlist: only the five methods reachable (MKT-09 first half)."""

from __future__ import annotations

import pytest

from pumpgrok.datafeed.readonly import (
    ALLOWED_METHODS,
    ReadonlyError,
    check_method,
    guarded_call,
)


def test_five_method_set() -> None:
    assert ALLOWED_METHODS == frozenset(
        {"getAccountInfo", "logsSubscribe", "getTransaction", "subscribeNewToken", "subscribeMigration"}
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
