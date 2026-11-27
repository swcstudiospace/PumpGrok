"""Review finding 12: CLI paper trades refuse explicitly until a curve source is verified.

The operator CLI binds no curve price source and the RPC curve layout is ASSUMED, so no paper
fill can be priced honestly from the CLI. An allowed trading seat reaches the seat guard
(forbidden owners, then the registry grant check) and is then refused with code ``unavailable``
(exit 1, the CLI refusal convention). The refusal runs before any tool, adapter or ledger
write, and writes no ledger event. Offline; no network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.core.approvals import parse_human_phrase, record_human_approval
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.manifests import roster_tool_names
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.tickets import allocate_ticket
from pumpgrok.replay.clock import WallClock, format_ts_utc
from pumpgrok.replay.rng import make_rng

_MINT = "So11111111111111111111111111111111111111112"
_SIDE_SEAT = {"buy": "bot-04-sniper", "sell": "bot-06-exit"}
_SIDE_KIND = {"buy": "human_buy", "sell": "human_sell"}


def _seed_approved_trade(tmp_path: Path, side: str) -> tuple[str, str]:
    """Create a ticket and a human approval for ``side``; return their ids."""
    clock = WallClock()
    ts_utc = format_ts_utc(clock.now())
    store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
    try:
        store.set_meta("initial_equity_lamports", str(RiskBudget().paper_equity_lamports))
        ticket_id = allocate_ticket(
            store,
            ts_utc=ts_utc,
            source="paper",
            correlation_id="t",
            seat=_SIDE_SEAT[side],
            title="lead",
        )
        approval_id = f"apr-{IdFactory(clock, make_rng()).ulid()}"
        record = parse_human_phrase(
            f"approve {ticket_id} {_MINT} 0.2 100",
            kind=_SIDE_KIND[side],  # type: ignore[arg-type]
            by="human:alice",
            approval_id=approval_id,
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        record_human_approval(store, record, ts_utc=ts_utc, source="paper", correlation_id="t")
    finally:
        store.close()
    return ticket_id, approval_id


def _grant_roster(seat: str) -> None:
    """Record an authenticated operator allow for every roster tool of ``seat``.

    Grants are ConfigChanged rows in the paper ledger, so they are written before the ledger
    snapshot the test compares against. The operator key is created in the working directory.
    """
    oc.init_key(Path("var") / "operator")
    store = LedgerStore(str(Path("var") / "ledger.sqlite"))
    try:
        for tool in sorted(roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat)):
            oc.record_tool_choice(
                store, seat=seat, tool=tool, decision="allow", now=datetime.now(UTC)
            )
    finally:
        store.close()


def _ledger_events(tmp_path: Path) -> list[dict[str, object]]:
    store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
    try:
        return list(store.read(limit=10000))
    finally:
        store.close()


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_approved_paper_trade_refused_unavailable_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    side: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    ticket_id, approval_id = _seed_approved_trade(tmp_path, side)
    _grant_roster(_SIDE_SEAT[side])
    before = _ledger_events(tmp_path)

    argv = [
        "paper",
        side,
        "--ticket",
        ticket_id,
        "--mint",
        _MINT,
        "--size-sol",
        "0.2",
        "--slippage-bps",
        "100",
        "--approval-id",
        approval_id,
        "--seat",
        _SIDE_SEAT[side],
    ]

    code = main(argv)

    assert code == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == {
        "ok": False,
        "code": "unavailable",
        "message": payload["message"],
    }
    assert "verified curve price source" in payload["message"]
    assert f"paper {side} failed: unavailable" in captured.err
    after = _ledger_events(tmp_path)
    assert after == before
    kinds = [event["type"] for event in after]
    assert "FillRecorded" not in kinds
    assert "OrderPlaced" not in kinds
