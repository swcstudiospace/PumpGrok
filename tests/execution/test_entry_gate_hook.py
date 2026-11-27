"""Entry hook gates buys only; exit and flatten sells pass (V4-12)."""

from __future__ import annotations

import pytest

from pumpgrok.execution.entry_hook import EntryHook, EntryRefusedError

HOOK = EntryHook()


def test_buy_rpc_refused() -> None:
    with pytest.raises(EntryRefusedError):
        HOOK.check_place(side="buy", curve_source="rpc")


def test_buy_completed_refused() -> None:
    with pytest.raises(EntryRefusedError):
        HOOK.check_place(side="buy", curve_source="fixture", complete=True)


def test_buy_replay_allowed() -> None:
    HOOK.check_place(side="buy", curve_source="fixture")


def test_sells_never_blocked() -> None:
    HOOK.check_place(side="sell", curve_source="rpc", complete=True)
    HOOK.check_place(side="flatten", curve_source="rpc", complete=True)
