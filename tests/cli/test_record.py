"""Replay maintenance verbs: trim and import (16-04). Synthetic datasets only, built in tmp_path.

``run --record`` and ``live serve`` are plan 16-08 and are not covered here.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_LEDGER, EXIT_NOT_IMPLEMENTED, EXIT_OK
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay import maintenance
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, load_dataset
from pumpgrok.replay.live_recorder import GAPS_NAME, seal_directory

_T0 = 1_800_000_000.0
_ORDER_MINT = "MintWithOrder1111111111111111111111111111"
_QUIET_MINT = "MintQuiet22222222222222222222222222222222"
_GAPS = (
    b'{"start_ts_utc":"2027-01-15T08:00:00Z","end_ts_utc":"2027-01-15T08:03:00Z",'
    b'"reason":"DataStale"}\n'
)


def _orders(_directory: Path) -> frozenset[str]:
    return frozenset({_ORDER_MINT})


def _rows(count: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(count):
        rows.append(
            {
                "kind": "tick",
                "mint": _ORDER_MINT if index % 4 == 0 else _QUIET_MINT,
                "ts_utc": format_ts_utc(_T0 + index),
                "S": 1_000 + index,
                "T": 2_000 + index,
                "complete": False,
                "source": "rpc",
            }
        )
    return rows


def _dataset(root: Path, name: str, rows: list[dict[str, object]], gaps: bytes | None) -> Path:
    directory = root / "datasets" / name
    directory.mkdir(parents=True)
    body = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    (directory / EVENTS_NAME).write_text(body, encoding="utf-8")
    if gaps is not None:
        (directory / GAPS_NAME).write_bytes(gaps)
    seal_directory(
        directory,
        recorded_from_utc=str(rows[0]["ts_utc"]),
        recorded_to_utc=str(rows[-1]["ts_utc"]),
        sources={"rpc": "rpc"},
        notes="synthetic test dataset",
    )
    return directory


def _ledger(path: Path, *, second_source: str = "paper", tamper: bool = False) -> Path:
    store = LedgerStore(str(path))
    try:
        store.append(
            ts_utc=format_ts_utc(_T0),
            source="paper",
            correlation_id="corr-1",
            idempotency_key="key-1",
            type="ConfigChanged",
            payload={"n": 1},
        )
        store.append(
            ts_utc=format_ts_utc(_T0 + 1),
            source=second_source,
            correlation_id="corr-2",
            idempotency_key="key-2",
            type="ConfigChanged",
            payload={"n": 2},
        )
    finally:
        store.close()
    if tamper:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("DROP TRIGGER IF EXISTS events_append_only_u")
            conn.execute("UPDATE events SET payload_json = ? WHERE seq = 1", ('{"n":9}',))
            conn.commit()
        finally:
            conn.close()
    return path


def test_trim_keeps_order_mints_and_is_byte_identical_on_rerun(tmp_path: Path) -> None:
    rows = _rows(400)
    _dataset(tmp_path, "smoke", rows, gaps=None)

    first = maintenance.trim(
        "smoke", root=tmp_path, max_events=10_000, seed=7, mints_with_orders=_orders
    )
    first_events = (first / EVENTS_NAME).read_bytes()
    first_manifest = (first / MANIFEST_NAME).read_bytes()
    shutil.rmtree(first)

    second = maintenance.trim(
        "smoke", root=tmp_path, max_events=10_000, seed=7, mints_with_orders=_orders
    )
    assert (second / EVENTS_NAME).read_bytes() == first_events
    assert (second / MANIFEST_NAME).read_bytes() == first_manifest

    kept = list(load_dataset(second).events)
    assert all(row in kept for row in rows if row["mint"] == _ORDER_MINT)
    assert 0 < len(kept) < len(rows)


def test_trim_keeps_the_last_n_kept_events(tmp_path: Path) -> None:
    _dataset(tmp_path, "smoke", _rows(400), gaps=None)
    full = maintenance.trim(
        "smoke", root=tmp_path, max_events=10_000, seed=7, mints_with_orders=_orders
    )
    full_events = list(load_dataset(full).events)
    shutil.rmtree(full)

    capped = maintenance.trim(
        "smoke", root=tmp_path, max_events=5, seed=7, mints_with_orders=_orders
    )
    assert list(load_dataset(capped).events) == full_events[-5:]


def test_trim_copies_gaps_unchanged_and_inserts_no_gap_row(tmp_path: Path) -> None:
    _dataset(tmp_path, "smoke", _rows(120), gaps=_GAPS)
    trimmed = maintenance.trim(
        "smoke", root=tmp_path, max_events=10_000, seed=3, mints_with_orders=_orders
    )
    assert (trimmed / GAPS_NAME).read_bytes() == _GAPS
    assert all(row["kind"] == "tick" for row in load_dataset(trimmed).events)
    assert not (trimmed / "feed.jsonl").exists()


def test_trim_refuses_an_existing_target_and_a_bad_name(tmp_path: Path) -> None:
    _dataset(tmp_path, "smoke", _rows(40), gaps=None)
    maintenance.trim("smoke", root=tmp_path, max_events=10, seed=1, mints_with_orders=_orders)
    with pytest.raises(maintenance.MaintenanceRefused) as exc:
        maintenance.trim("smoke", root=tmp_path, max_events=10, seed=1, mints_with_orders=_orders)
    assert exc.value.fields["kind"] == "usage"
    with pytest.raises(maintenance.MaintenanceRefused) as bad:
        maintenance.trim(
            "../smoke", root=tmp_path, max_events=10, seed=1, mints_with_orders=_orders
        )
    assert bad.value.fields["kind"] == "usage"


def test_import_copies_verified_paper_ledger_and_writes_sidecar(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "source.sqlite")
    data = ledger.read_bytes()

    target = maintenance.import_dataset(ledger, name="imp", root=tmp_path / "var")

    assert target == tmp_path / "var" / "replay" / "imp"
    assert (target / maintenance.IMPORTED_LEDGER_NAME).read_bytes() == data
    digest = hashlib.sha256(data).hexdigest()
    sidecar = (target / maintenance.IMPORTED_DIGEST_NAME).read_text(encoding="utf-8")
    assert sidecar == f"{digest}  {maintenance.IMPORTED_LEDGER_NAME}\n"


@pytest.mark.parametrize(
    ("second_source", "tamper"),
    [("replay", False), ("manual", False), ("paper", True)],
)
def test_import_refuses_unverified_or_foreign_ledgers_without_writing(
    tmp_path: Path, second_source: str, tamper: bool
) -> None:
    ledger = _ledger(tmp_path / "source.sqlite", second_source=second_source, tamper=tamper)
    with pytest.raises(maintenance.MaintenanceRefused) as exc:
        maintenance.import_dataset(ledger, name="bad", root=tmp_path / "var")
    assert exc.value.fields["kind"] == "ledger"
    assert not (tmp_path / "var" / "replay" / "bad").exists()


def test_import_refuses_an_existing_target(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "source.sqlite")
    maintenance.import_dataset(ledger, name="imp", root=tmp_path / "var")
    with pytest.raises(maintenance.MaintenanceRefused) as exc:
        maintenance.import_dataset(ledger, name="imp", root=tmp_path / "var")
    assert exc.value.fields["kind"] == "usage"


def test_cli_import_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    good = _ledger(tmp_path / "good.sqlite")
    replayed = _ledger(tmp_path / "replayed.sqlite", second_source="replay")

    assert main(["replay", "import", "--from", str(good), "--dataset", "cli-imp"]) == EXIT_OK
    assert (tmp_path / "var" / "replay" / "cli-imp" / "imported-ledger.sqlite").is_file()
    assert main(["replay", "import", "--from", str(replayed), "--dataset", "cli-x"]) == (
        EXIT_LEDGER
    )
    assert main(["replay", "import", "--from", str(good), "--dataset", "cli-imp"]) == EXIT_CONFIG


def test_cli_rebuild_ticks_is_not_implemented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["replay", "rebuild-ticks", "--dataset", "anything"]) == EXIT_NOT_IMPLEMENTED


def test_cli_trim_arguments_are_required_and_positive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    missing_keep = ["replay", "trim", "--dataset", "x", "--max-events", "5"]
    assert main(missing_keep) == EXIT_CONFIG
    zero = ["replay", "trim", "--dataset", "x", "--max-events", "0", "--keep-mints-with-fills"]
    assert main(zero) == EXIT_CONFIG


def test_maintenance_module_imports_no_network_or_live_client() -> None:
    source = Path(maintenance.__file__).read_text(encoding="utf-8")
    forbidden_roots = {"httpx", "websockets", "aiohttp", "requests", "socket", "urllib"}
    forbidden_prefixes = (
        "pumpgrok.grok",
        "pumpgrok.datafeed",
        "pumpgrok.tools",
        "pumpgrok.execution",
    )
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    assert not {name.split(".")[0] for name in imported} & forbidden_roots
    assert not {name for name in imported if name.startswith(forbidden_prefixes)}
