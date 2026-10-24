"""Live gate fails fast (SEC-004, GOLIVE-001, GOLIVE-002).

`run --mode live` with any R21 precondition unmet exits 3, prints one
``[x]``/``[ ]`` line per id on stderr in R21 order, and sends nothing.
`live confirm` writes the HMAC record bound to the config hash and never
changes the mode. Metrics count source=paper events only; a replay row
refuses the window. No signing symbols exist outside execution/live.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import hashlib
import hmac
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import load_settings
from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.errors import LiveGateError
from pumpgrok.core.ids import IdFactory
from pumpgrok.execution.live import PRECONDITION_IDS, LiveAdapterStub, LiveGate, Precondition
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng

EPOCH_START = 1767225600.0  # 2026-01-01T00:00:00Z
MINT = "So11111111111111111111111111111111111111112"
CID = "01J0000000000000000000000000"


def _append(store: LedgerStore, seq: int, type: str, payload: dict, ts: str) -> None:
    store.append(
        ts_utc=ts,
        source=payload.pop("envelope_source", "paper"),
        correlation_id=CID,
        idempotency_key=f"gate-{type}-{seq}",
        type=type,
        payload=payload,
    )


def _ulid() -> str:
    """One fresh ULID from the seeded factory (valid for every id pattern)."""
    return IdFactory(FixtureClock(start=EPOCH_START), make_rng()).ulid()


def test_live_run_exits_3_with_nine_ordered_lines(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PUMPGROK_LIVE_ENABLE", raising=False)
    code = main(["run", "--mode", "live", "--once"])
    assert code == 3
    err = capsys.readouterr().err
    assert err.startswith("LIVE GATE: refusing to start in mode=live. 9 of 9")
    marked = [line for line in err.splitlines() if line.startswith("  [")]
    assert len(marked) == 9
    ids = []
    for line in marked:
        parts = line.split()
        ids.append(parts[2] if parts[1].isdigit() else parts[3])
    assert tuple(ids) == PRECONDITION_IDS


def test_live_mode_with_paper_overlay_still_runs_gate(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PUMPGROK_PROFILE", "paper")
    monkeypatch.delenv("PUMPGROK_LIVE_ENABLE", raising=False)
    code = main(["run", "--mode", "live", "--once"])
    assert code == 3
    assert "LIVE GATE" in capsys.readouterr().err


def test_precondition_1_requires_live_enabled_flag(tmp_path: Path) -> None:
    """Row 1 needs effective mode live AND [live] enabled = true (R21, D4)."""
    gate = LiveGate(
        mode="live",
        environ={"PUMPGROK_LIVE_ENABLE": "1"},
        root=tmp_path,
        live_enabled=False,
    )
    by_id = {item.id: item for item in gate.evaluate()}
    assert by_id["mode_live"].met is False
    assert "[live] enabled" in by_id["mode_live"].reason


def test_precondition_1_met_when_mode_live_and_enabled(tmp_path: Path) -> None:
    """Row 1 holds with mode live plus the flag; later rows still fail fast."""
    gate = LiveGate(
        mode="live",
        environ={"PUMPGROK_LIVE_ENABLE": "1"},
        root=tmp_path,
        live_enabled=True,
    )
    by_id = {item.id: item for item in gate.evaluate()}
    assert by_id["mode_live"].met is True
    assert by_id["live_enable_env"].met is True


@pytest.mark.parametrize("target", PRECONDITION_IDS)
def test_live_gate_fails_fast_per_precondition(
    tmp_path: Path, monkeypatch, capsys, target: str
) -> None:
    """Each precondition fails independently with exactly its own id on stderr.

    Rows 5-9 are hard-coded False, so input-only variation cannot isolate
    them; patching the evaluator to return all rows met except the target is
    the approved proof. Row 8 stays structurally unmet (no live adapter
    ships) and row 9 reads halt/kill/breaker state where readable.
    """
    monkeypatch.chdir(tmp_path)
    rows = tuple(
        Precondition(number=index, id=name, met=(name != target), reason="patched")
        for index, name in enumerate(PRECONDITION_IDS, start=1)
    )
    monkeypatch.setattr(LiveGate, "evaluate", lambda self: rows)
    code = main(["run", "--mode", "live", "--once"])
    assert code == 3
    err = capsys.readouterr().err
    assert err.startswith("LIVE GATE: refusing to start in mode=live.")
    unmet = [line for line in err.splitlines() if line.startswith("  [ ]")]
    assert len(unmet) == 1
    assert f" {target} " in unmet[0]


def test_paper_mode_never_evaluates_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A paper run never reaches LiveGate.evaluate, so no precondition is read."""
    gate = LiveGate(mode="paper", environ={"PUMPGROK_LIVE_ENABLE": "1"}, root=tmp_path)
    assert gate.check()[0] == "mode_live"
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PUMPGROK_LIVE_ENABLE", raising=False)
    smoke = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"
    calls: list[LiveGate] = []
    real_evaluate = LiveGate.evaluate

    def _spy(self: LiveGate) -> tuple[Precondition, ...]:
        calls.append(self)
        return real_evaluate(self)

    monkeypatch.setattr(LiveGate, "evaluate", _spy)
    assert main(["run", "--mode", "paper", "--once", "--replay", str(smoke)]) == 0
    assert calls == []


def test_mature_paper_window_meets_days_and_thresholds(tmp_path: Path) -> None:
    var = tmp_path / "var"
    var.mkdir()
    store = LedgerStore(var / "ledger.sqlite")
    try:
        for seq in range(55):
            _append(
                store,
                seq,
                "PositionClosed",
                {
                    "source": "paper",
                    "mint": MINT,
                    "price_exit": "0.00005800",
                    "proceeds_lamports": 203000000,
                    "realized_pnl_lamports": 3000000,
                    "reason": "take_profit",
                },
                f"2026-08-01T10:{seq % 60:02d}:00Z",
            )
        _append(
            store,
            56,
            "MarkToMarket",
            {
                "source": "paper",
                "ts_source": "curve",
                "cash_lamports": 9000000000,
                "equity_lamports": 11500000000,
                "unrealized_lamports": 0,
            },
            "2026-10-20T12:00:00Z",
        )
    finally:
        store.close()
    gate = LiveGate(mode="live", environ={"PUMPGROK_LIVE_ENABLE": "1"}, root=tmp_path)
    by_id = {item.id: item for item in gate.evaluate()}
    assert by_id["min_paper_days"].met is True
    assert by_id["performance_thresholds"].met is True


def test_replay_ledger_is_refused_for_metrics(tmp_path: Path) -> None:
    var = tmp_path / "var"
    var.mkdir()
    store = LedgerStore(var / "ledger.sqlite")
    try:
        _append(
            store,
            1,
            "PositionClosed",
            {
                "envelope_source": "replay",
                "source": "replay",
                "mint": MINT,
                "price_exit": "0.00005800",
                "proceeds_lamports": 203000000,
                "realized_pnl_lamports": 3000000,
                "reason": "take_profit",
            },
            "2026-08-01T10:00:00Z",
        )
    finally:
        store.close()
    by_id = {item.id: item for item in LiveGate(mode="live", environ={}, root=tmp_path).evaluate()}
    assert by_id["min_paper_days"].met is False
    assert "replay ledger" in by_id["min_paper_days"].reason
    assert by_id["performance_thresholds"].met is False
    assert "replay ledger" in by_id["performance_thresholds"].reason


def test_paper_metrics_ignore_replay_rows(tmp_path: Path) -> None:
    var = tmp_path / "var"
    var.mkdir()
    store = LedgerStore(var / "ledger.sqlite")
    try:
        for seq in range(55):
            _append(
                store,
                seq,
                "PositionClosed",
                {
                    "source": "paper",
                    "mint": MINT,
                    "price_exit": "0.00005800",
                    "proceeds_lamports": 203000000,
                    "realized_pnl_lamports": 3000000,
                    "reason": "take_profit",
                },
                f"2026-08-01T10:{seq % 60:02d}:00Z",
            )
        _append(
            store,
            90,
            "PositionClosed",
            {
                "envelope_source": "replay",
                "source": "replay",
                "mint": MINT,
                "price_exit": "0.00005800",
                "proceeds_lamports": 203000000,
                "realized_pnl_lamports": -999999999999,
                "reason": "stop_loss",
            },
            "2026-08-01T11:00:00Z",
        )
    finally:
        store.close()
    by_id = {item.id: item for item in LiveGate(mode="live", environ={}, root=tmp_path).evaluate()}
    assert "replay ledger" in by_id["performance_thresholds"].reason


def _stub(tmp_path: Path) -> tuple[LiveAdapterStub, LedgerStore]:
    ledger = LedgerStore(tmp_path / "ledger.sqlite")
    clock = FixtureClock(start=EPOCH_START)
    adapter = LiveAdapterStub(
        gate=LiveGate(mode="live", environ={}, root=tmp_path),
        ledger=ledger,
        clock=clock,
        ids=IdFactory(clock, make_rng()),
    )
    return adapter, ledger


def test_place_and_cancel_raise_after_audit_row(tmp_path: Path, caplog) -> None:
    adapter, ledger = _stub(tmp_path)
    decision = _ulid()
    request = OrderRequest(
        ticket_id="SOL-20260101-001",
        mint=MINT,
        side=Side.BUY,
        decision_id=decision,
        size_lamports=1000,
        max_slippage_bps=100,
        approval_id=f"apr-{decision}",
        correlation_id="01J0000000000000000000000",
    )
    with caplog.at_level("CRITICAL"):
        with pytest.raises(LiveGateError) as place_refused:
            asyncio.run(adapter.place(request))
        with pytest.raises(LiveGateError) as cancel_refused:
            asyncio.run(adapter.cancel("ord-1", "SOL-20260101-001", "dec-1"))
    assert "adapter_registered" in place_refused.value.fields["unmet"]
    assert "adapter_registered" in cancel_refused.value.fields["unmet"]
    assert any("live_write_attempted" in record.message for record in caplog.records)
    try:
        rows = ledger._db.execute(
            "SELECT payload_json FROM events WHERE type='LiveWriteAttempted' ORDER BY seq"
        ).fetchall()
    finally:
        ledger.close()
    methods = [json.loads(str(payload))["method"] for (payload,) in rows]
    assert methods == ["place", "cancel"]


def test_live_confirm_writes_hmac_record_without_changing_mode(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "PUMPGROK_CONFIRMATION_KEY",
        "operator-secret-for-tests",  # pragma: allowlist secret: test placeholder, not a credential
    )
    monkeypatch.delenv("PUMPGROK_LIVE_ENABLE", raising=False)
    monkeypatch.setattr("pumpgrok.cli._utc_now", lambda: datetime(2026, 1, 1, tzinfo=UTC))
    code = main(
        [
            "live",
            "confirm",
            "--by",
            "human:alice",
            "--notional-cap",
            "0.1",
            "--expires",
            "2026-12-31T00:00:00Z",
        ]
    )
    assert code == 0
    record = json.loads((tmp_path / "var" / "live_confirmation.json").read_text())
    assert record["confirmed_by"] == "human:alice"
    assert record["notional_cap_lamports"] == 100000000
    assert record["expires_at"] == "2026-12-31T00:00:00Z"
    assert record["statement"].startswith("I confirm live trading")
    body = {key: record[key] for key in record if key != "signature"}
    expected = hmac.new(
        b"operator-secret-for-tests",
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).digest()
    assert base64.b64decode(record["signature"]) == expected
    conn = sqlite3.connect(tmp_path / "var" / "ledger.sqlite")
    try:
        rows = conn.execute(
            "SELECT payload_json FROM events WHERE type='ApprovalRecorded'"
        ).fetchall()
    finally:
        conn.close()
    approvals = [json.loads(str(payload)) for (payload,) in rows]
    assert any(
        a.get("kind") == "live_gate" and a.get("approved_by") == "human:alice" for a in approvals
    )
    out = capsys.readouterr().out
    assert "confirmation_record" in out
    assert load_settings().effective_mode == "paper"


def test_no_signing_symbols_outside_live_package() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "execution/live" in path.as_posix():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in ("Keypair", "send_transaction"):
                offenders.append(f"{path}:{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in ("sign", "send_transaction"):
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == []


def test_live_flag_requires_both_sources(tmp_path: Path, monkeypatch) -> None:
    """INV-C-04: TOML live alone never gates live; env-only stays paper."""
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "operator.toml"
    config.write_text('[execution]\nmode = "live"\n', encoding="utf-8")
    monkeypatch.setenv("PUMPGROK_CONFIG", str(config))
    monkeypatch.delenv("PUMPGROK_LIVE_ENABLE", raising=False)
    settings = load_settings()
    assert settings.effective_mode == "live"
    assert settings.live.enabled is False
    gate = LiveGate(
        mode=settings.effective_mode,
        environ={},
        root=tmp_path,
        live_enabled=settings.live.enabled,
    )
    by_id = {item.id: item for item in gate.evaluate()}
    assert by_id["mode_live"].met is False
    assert "[live] enabled" in by_id["mode_live"].reason
    monkeypatch.delenv("PUMPGROK_CONFIG")
    monkeypatch.setenv("PUMPGROK_LIVE_ENABLE", "1")
    assert load_settings().effective_mode == "paper"


def test_adapter_precondition_always_unmet_in_this_release(tmp_path: Path) -> None:
    """INV-C-03: precondition (8) is structurally unmet; nothing ships."""
    gate = LiveGate(mode="live", environ={"PUMPGROK_LIVE_ENABLE": "1"}, root=tmp_path)
    by_id = {item.id: item for item in gate.evaluate()}
    assert by_id["adapter_registered"].met is False


def test_live_gate_refuses_replay_source(tmp_path: Path) -> None:
    """INV-C-09: the gate refuses any ledger containing source=replay rows."""
    var = tmp_path / "var"
    var.mkdir()
    store = LedgerStore(var / "ledger.sqlite")
    try:
        _append(
            store,
            1,
            "PositionClosed",
            {
                "envelope_source": "replay",
                "source": "replay",
                "mint": MINT,
                "price_exit": "0.00005800",
                "proceeds_lamports": 203000000,
                "realized_pnl_lamports": 3000000,
                "reason": "take_profit",
            },
            "2026-08-01T10:00:00Z",
        )
    finally:
        store.close()
    gate = LiveGate(mode="live", environ={"PUMPGROK_LIVE_ENABLE": "1"}, root=tmp_path)
    by_id = {item.id: item for item in gate.evaluate()}
    assert by_id["min_paper_days"].met is False
    assert "replay ledger" in by_id["min_paper_days"].reason
    assert by_id["performance_thresholds"].met is False
