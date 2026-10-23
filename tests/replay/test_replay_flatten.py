"""G7: kill-switch flatten closes an open paper position through PaperAdapter.

After the smoke cycle opens a position, a ``flatten_request`` resolved from the
risk seat's roster grant sells it with reason ``kill_flatten``. The sell lands as
one ``FillRecorded`` plus one ``PositionClosed``, and the flatten reports a
non-empty ``flatten_outcomes``. The exit rules are switched off for the opening cycle
(the smoke fixture would otherwise take profit before the flatten), so the position is
still open when the kill switch flattens it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pumpgrok.config.settings import ExitsSettings, FilterSettings
from pumpgrok.core.ids import CorrelationId, bind_correlation
from pumpgrok.core.manifests import load_bot_manifests
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.supervisor.scheduler import open_replay_runtime, run_once_replay

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
ROSTER = REPO / "contracts" / "tool-rosters"
SEED = 20260101
MINT = "SmokeMintBBBB2222222222222222222222222222222"
TICKET = "SOL-20260101-001"


def _open_units(ledger: Path) -> int:
    store = LedgerStore(str(ledger))
    try:
        state = initial_state(source="replay", initial_equity_lamports=0, day_utc="")
        for event in store.read(limit=None):
            state = reduce(state, event)
    finally:
        store.close()
    pos = state.positions.get(MINT)
    return 0 if pos is None else pos.token_units


def test_kill_switch_flatten_closes_open_replay_position(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    rules_off = ExitsSettings(
        stop_loss_pct=0, take_profit_pct=0, trailing_stop_pct=0, max_hold_seconds=0
    )
    opened = run_once_replay(
        SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger, exits=rules_off
    )
    assert [t.outcome for t in opened.trades if t.side == "buy"] == ["rejected", "filled"]
    assert _open_units(ledger) > 0

    runtime = open_replay_runtime(SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger)
    try:
        last_stamp = max(parse_ts_utc(str(e["ts_utc"])) for e in load_dataset(SMOKE).events)
        runtime.clock.advance_to(last_stamp)
        manifests = load_bot_manifests(ROSTER)
        with bind_correlation(CorrelationId.new(runtime.ids)):
            flatten = runtime.registry.find(
                "risk.kill_switch",
                max_side_effect=SideEffect.PAPER_WRITE,
                bot=manifests["bot-02-risk"],
            )
            payload = flatten.spec.input_model(
                action="flatten_request", reason="G7 test flatten of open paper position"
            )
            out = asyncio.run(flatten(payload)).model_dump(mode="json")
    finally:
        runtime.store.close()

    assert out["flatten_status"] == "completed"
    assert out["flatten_outcomes"] == [
        {"mint": MINT, "ticket_id": TICKET, "status": "closed", "detail": ""}
    ]
    store = LedgerStore(str(ledger))
    try:
        sells = [
            row
            for row in store.read(types=["FillRecorded"], limit=None)
            if row["payload"]["side"] == "sell"
        ]
        closed = store.read(types=["PositionClosed"], limit=None)
    finally:
        store.close()
    assert [row["payload"]["mint"] for row in sells] == [MINT]
    assert [row["payload"]["reason"] for row in closed][-1] == "kill_flatten"
    assert _open_units(ledger) == 0
