"""Exit rules close open paper positions in replay (STRUCT-003, PAPER-007, TOOL-009).

Each replay cycle evaluates the ported exit rules (engine/exits.py through the
ported PositionWatcher) against every open position at the curve reads the
fixture provides. A firing rule sells through the exit seat's granted exec.place,
through risk and PaperAdapter, and the ledger records the sell and the reason.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.ids import CorrelationId, bind_correlation
from pumpgrok.core.manifests import load_bot_manifests
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.supervisor.scheduler import open_replay_runtime, run_once_replay

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
ROSTER = REPO / "contracts" / "tool-rosters"
SEED = 20260101
MINT = "SmokeMintBBBB2222222222222222222222222222222"
TICKET = "SOL-20260101-001"
# The smoke fixture's curve tick after the sniper's fill; the exit rules read it.
EXIT_TICK = "2026-01-01T00:00:30.000Z"


def _rows(ledger: Path, *types: str) -> list[dict[str, object]]:
    store = LedgerStore(str(ledger))
    try:
        return store.read(types=list(types), limit=None)
    finally:
        store.close()


def _dataset_with_exit_tick(root: Path, name: str, s_lamports: int) -> Path:
    """Smoke ticks plus one curve-only tick at EXIT_TICK moving mint B to ``s_lamports``."""
    dataset = root / name
    dataset.mkdir(parents=True)
    smoke = (SMOKE / "events.jsonl").read_text(encoding="utf-8").splitlines()
    # Drop the smoke exit tick so the test tick is the only curve read at EXIT_TICK.
    lines = [line for line in smoke if json.loads(line)["ts_utc"] != EXIT_TICK]
    tick = {
        "ts_utc": EXIT_TICK,
        "kind": "tick",
        "mint": MINT,
        "name": "Smoke Beta",
        "image_uri": "fixture://smoke/beta.png",
        "created_ts_utc": "2025-12-31T23:40:00.000Z",
        "S": s_lamports,
        "T": 121_500_000_000_000,
        "complete": False,
        "source": "rest",
    }
    data = "\n".join([*lines, json.dumps(tick)]) + "\n"
    (dataset / "events.jsonl").write_text(data, encoding="utf-8")
    manifest = {
        "dataset": name,
        "recorded_from_utc": "2026-01-01T00:00:00.000Z",
        "recorded_to_utc": EXIT_TICK,
        "seed_hint": SEED,
        "sources": {"rest": "hand-authored", "pumpportal": "hand-authored"},
        "sha256": {"events.jsonl": hashlib.sha256(data.encode("utf-8")).hexdigest()},
        "notes": "smoke ticks plus one exit-rule curve tick (test dataset)",
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dataset


def test_take_profit_closes_the_fixture_position_in_one_replay_cycle(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    result = run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger)
    sells = [trade for trade in result.trades if trade.side == "sell"]
    assert [(t.mint, t.outcome, t.rule) for t in sells] == [(MINT, "filled", "take_profit")]
    assert [row["payload"]["reason"] for row in _rows(ledger, "PositionClosed")] == ["take_profit"]
    sell_fills = [row for row in _rows(ledger, "FillRecorded") if row["payload"]["side"] == "sell"]
    assert [row["payload"]["mint"] for row in sell_fills] == [MINT]
    approvals = _rows(ledger, "ApprovalRecorded")
    assert approvals[-1]["payload"]["exit_rule_id"] == "take_profit"


def test_stop_loss_closes_the_fixture_position_in_one_replay_cycle(tmp_path: Path) -> None:
    dataset = _dataset_with_exit_tick(tmp_path, "drop", s_lamports=5_940_000_000)
    ledger = tmp_path / "ledger.sqlite"
    result = run_once_replay(dataset, FilterSettings(), seed=SEED, ledger_path=ledger)
    sells = [trade for trade in result.trades if trade.side == "sell"]
    assert [(t.outcome, t.rule) for t in sells] == [("filled", "stop_loss")]
    assert [row["payload"]["reason"] for row in _rows(ledger, "PositionClosed")] == ["stop_loss"]


def test_exit_seat_cannot_place_a_buy(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger)
    placed_before = len(_rows(ledger, "OrderPlaced"))
    runtime = open_replay_runtime(SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger)
    try:
        manifests = load_bot_manifests(ROSTER)
        with bind_correlation(CorrelationId.new(runtime.ids)):
            place = runtime.registry.find(
                "exec.place",
                max_side_effect=SideEffect.PAPER_WRITE,
                bot=manifests["bot-06-exit"],
            )
            payload = place.spec.input_model(
                ticket_id=TICKET,
                mint=MINT,
                side="buy",
                decision_id=runtime.ids.ulid(),
                size_lamports=10_000_000,
                max_slippage_bps=100,
                approval_id=f"apr-{runtime.ids.ulid()}",
            )
            out = asyncio.run(place(payload)).model_dump(mode="json")
    finally:
        runtime.store.close()
    assert out["status"] == "rejected"
    assert out["reason"] == "seat_may_trade"
    assert len(_rows(ledger, "OrderPlaced")) == placed_before


def test_only_the_exit_seat_may_send_a_rule_sell(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger)
    runtime = open_replay_runtime(SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger)
    try:
        manifests = load_bot_manifests(ROSTER)
        with bind_correlation(CorrelationId.new(runtime.ids)):
            place = runtime.registry.find(
                "exec.place",
                max_side_effect=SideEffect.PAPER_WRITE,
                bot=manifests["bot-04-sniper"],
            )
            payload = place.spec.input_model(
                ticket_id=TICKET,
                mint=MINT,
                side="sell",
                decision_id=runtime.ids.ulid(),
                token_units=1,
                max_slippage_bps=100,
                approval_id=f"apr-{runtime.ids.ulid()}",
                exit_reason="take_profit",
            )
            out = asyncio.run(place(payload)).model_dump(mode="json")
    finally:
        runtime.store.close()
    assert out["status"] == "rejected"
    assert out["reason"] == "exit_reason_seat"
