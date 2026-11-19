"""Replay maintenance under concurrent writers: a WAL-mode import and a racing rebuild claim.

Synthetic data only. No network, no live client.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay import maintenance
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.replay.fixtures import EVENTS_NAME
from pumpgrok.replay.live_recorder import FEED_NAME, seal_directory

_START = 1_800_000_000.0


def _append(store: LedgerStore, seq: int) -> None:
    store.append(
        ts_utc=format_ts_utc(_START + seq),
        source="paper",
        correlation_id=f"corr-{seq}",
        idempotency_key=f"key-{seq}",
        type="ConfigChanged",
        payload={"source": "paper", "by": "test-operator", "keys_changed": ["n"]},
    )


def test_import_includes_rows_still_in_the_wal_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    store = LedgerStore(str(source))
    try:
        _append(store, 0)
        _append(store, 1)
        # Fold the first two rows into the main file, then commit two more that stay in -wal.
        checkpoint = sqlite3.connect(str(source))
        try:
            checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        finally:
            checkpoint.close()
        _append(store, 2)
        _append(store, 3)
        assert Path(f"{source}-wal").stat().st_size > 0

        target = maintenance.import_dataset(source, name="imp", root=tmp_path / "var")
    finally:
        store.close()

    assert sorted(p.name for p in (tmp_path / "var" / "replay").iterdir()) == ["imp"]
    imported_bytes = (target / maintenance.IMPORTED_LEDGER_NAME).read_bytes()
    digest = hashlib.sha256(imported_bytes).hexdigest()
    sidecar = (target / maintenance.IMPORTED_DIGEST_NAME).read_text(encoding="utf-8")
    assert sidecar == f"{digest}  {maintenance.IMPORTED_LEDGER_NAME}\n"

    imported = LedgerStore(str(target / maintenance.IMPORTED_LEDGER_NAME))
    try:
        assert imported.count() == 4
        assert imported.verify()
    finally:
        imported.close()


def _rebuildable(root: Path, name: str) -> Path:
    """A sealed dataset whose feed holds only the config frame: enough to claim and replay."""
    directory = root / "datasets" / name
    directory.mkdir(parents=True)
    config = {"ts": _START, "stream": "config", "payload": {"watch_capacity": 4}}
    (directory / FEED_NAME).write_bytes(json.dumps(config, separators=(",", ":")).encode() + b"\n")
    (directory / EVENTS_NAME).write_bytes(b"")
    seal_directory(
        directory,
        recorded_from_utc=format_ts_utc(_START),
        recorded_to_utc=format_ts_utc(_START),
        sources={"rpc": "rpc"},
        notes="synthetic feed",
    )
    return directory


def test_rebuild_refuses_a_second_claim_while_the_first_holds_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "var"
    _rebuildable(root, "live")
    target = root / "datasets" / "live-rebuilt"
    refusals: list[maintenance.MaintenanceRefused] = []
    winner_present: list[bool] = []
    started: list[bool] = []

    async def racing_replay(*_args: Any, **_kwargs: Any) -> None:
        # The first rebuild is in flight when a second one of the same dataset starts.
        if not started:
            started.append(True)
            try:
                await asyncio.to_thread(maintenance.rebuild_ticks, "live", root=root)
            except maintenance.MaintenanceRefused as exc:
                refusals.append(exc)
            winner_present.append(target.is_dir())

    monkeypatch.setattr(maintenance, "_replay", racing_replay)

    assert maintenance.rebuild_ticks("live", root=root) == target
    assert len(refusals) == 1
    assert refusals[0].fields["kind"] == "usage"
    assert winner_present == [True]
