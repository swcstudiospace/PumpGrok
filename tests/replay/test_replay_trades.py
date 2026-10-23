"""G1: a fixture paper cycle decides and trades through the registry (AUTO-006, PAPER-004).

The smoke fixture carries token evidence, so the engine filter admits mint B.
The sniper seat places the buy through ``exec.place`` resolved from its roster
grant; the risk engine and PaperAdapter approve or veto it, and the ledger
records the outcome. Evidence-less datasets still never trade.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.bot import BotManifest
from pumpgrok.core.errors import PermissionDenied
from pumpgrok.core.ids import CorrelationId, bind_correlation
from pumpgrok.core.manifests import load_bot_manifests
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.runner import ledger_events_hash
from pumpgrok.supervisor.scheduler import open_replay_runtime, run_once_replay

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
ROSTER = REPO / "contracts" / "tool-rosters"
SEED = 20260101
GRADUATED_MINT = "SmokeMintBBBB2222222222222222222222222222222"


def _rows(ledger: Path, *types: str) -> list[dict[str, object]]:
    store = LedgerStore(str(ledger))
    try:
        return store.read(types=list(types), limit=None)
    finally:
        store.close()


def _manifest(seat: str) -> BotManifest:
    return load_bot_manifests(ROSTER)[seat]


def _evidence_free_dataset(root: Path) -> Path:
    """Smoke ticks with every evidence field stripped: the fail-closed control."""
    dataset = root / "bare"
    dataset.mkdir(parents=True)
    keep = ("ts_utc", "kind", "mint", "S", "T", "complete", "source")
    lines = []
    for raw in (SMOKE / "events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(raw)
        lines.append(json.dumps({key: event[key] for key in keep}) + "\n")
    data = "".join(lines)
    (dataset / "events.jsonl").write_text(data, encoding="utf-8")
    manifest = {
        "dataset": "bare",
        "recorded_from_utc": "2026-01-01T00:00:00.000Z",
        "recorded_to_utc": "2026-01-01T00:00:03.000Z",
        "seed_hint": SEED,
        "sources": {"rest": "hand-authored", "pumpportal": "hand-authored"},
        "sha256": {"events.jsonl": hashlib.sha256(data.encode("utf-8")).hexdigest()},
        "notes": "synthetic evidence-free control dataset",
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dataset


def test_smoke_cycle_opens_one_paper_position(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    result = run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger)
    assert result.decision == "buy"
    assert result.reason == "ok"
    filled = [trade for trade in result.trades if trade.outcome == "filled" and trade.side == "buy"]
    assert [(t.side, t.mint) for t in filled] == [("buy", GRADUATED_MINT)]
    fills = [row for row in _rows(ledger, "FillRecorded") if row["payload"]["side"] == "buy"]
    assert [(f["payload"]["side"], f["payload"]["mint"]) for f in fills] == [
        ("buy", GRADUATED_MINT)
    ]
    assert len(_rows(ledger, "PositionOpened")) == 1
    assert result.events_hash == ledger_events_hash(ledger)


def test_graduated_candidate_is_vetoed_with_reason(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    result = run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger)
    refused = [trade for trade in result.trades if trade.outcome == "rejected"]
    assert len(refused) == 1
    assert refused[0].side == "buy"
    assert refused[0].reason == "post_graduation_no_reserves"
    rejected = _rows(ledger, "OrderRejected")
    assert [row["payload"]["reason"] for row in rejected] == ["post_graduation_no_reserves"]


def test_trades_resolve_exec_place_only_for_granted_seats(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger)
    runtime = open_replay_runtime(SMOKE, FilterSettings(), seed=SEED, ledger_path=ledger)
    try:
        with bind_correlation(CorrelationId.new(runtime.ids)):
            with pytest.raises(PermissionDenied):
                runtime.registry.find(
                    "exec.place",
                    max_side_effect=SideEffect.PAPER_WRITE,
                    bot=_manifest("bot-02-risk"),
                )
            sniper = runtime.registry.find(
                "exec.place",
                max_side_effect=SideEffect.PAPER_WRITE,
                bot=_manifest("bot-04-sniper"),
            )
        assert sniper.spec.name == "exec.place"
    finally:
        runtime.store.close()


def test_evidence_free_dataset_never_trades(tmp_path: Path) -> None:
    dataset = _evidence_free_dataset(tmp_path)
    ledger = tmp_path / "ledger.sqlite"
    result = run_once_replay(dataset, FilterSettings(), seed=SEED, ledger_path=ledger)
    assert result.decision == "skip"
    assert result.reason == "no_metadata"
    assert result.trades == ()
    assert _rows(ledger, "FillRecorded", "OrderPlaced") == []


def test_two_runs_with_trades_hash_identically(tmp_path: Path) -> None:
    first = run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "a.sqlite")
    second = run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "b.sqlite")
    assert first.events_hash == second.events_hash
    assert first.trades == second.trades
    assert first.events_hash == ledger_events_hash(tmp_path / "a.sqlite")
