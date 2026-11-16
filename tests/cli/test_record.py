"""Replay maintenance verbs: trim, rebuild-ticks and import (16-04). Synthetic data only.

Datasets are built under tmp_path. ``run --record`` and ``live serve`` are plan 16-08.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import shutil
import sqlite3
import struct
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.cli import main
from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_LEDGER, EXIT_OK
from pumpgrok.datafeed.logs import PUMP_PROGRAM_ID
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay import maintenance
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, CorruptFixture, load_dataset
from pumpgrok.replay.live_recorder import FEED_NAME, GAPS_NAME, seal_directory

_START = 1_800_000_000.0
_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_TRUNCATED = "Log truncated"
_TRADE_DISC = hashlib.sha256(b"event:TradeEvent").digest()[:8]
_ORDER_MINT = "MintWithOrder1111111111111111111111111111"
_QUIET_MINT = "MintQuiet22222222222222222222222222222222"
_GAPS = (
    b'{"start_ts_utc":"2027-01-15T08:00:00Z","end_ts_utc":"2027-01-15T08:03:00Z",'
    b'"reason":"DataStale"}\n'
)


def _b58(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    out = ""
    while number:
        number, rem = divmod(number, 58)
        out = _ALPHABET[rem] + out
    pad = len(raw) - len(raw.lstrip(b"\0"))
    return "1" * pad + out


MINT_RAW = bytes([1]) * 32
MINT = _b58(MINT_RAW)
OTHER_RAW = bytes([2]) * 32
OTHER = _b58(OTHER_RAW)
USER_RAW = bytes([3]) * 32


def _u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def _i64(value: int) -> bytes:
    return struct.pack("<q", value)


def _trade_event(mint_raw: bytes, *, vsol: int, vtok: int) -> bytes:
    """Borsh-encode a TradeEvent in the field order the pump decoder reads."""
    text = b"swap"
    return b"".join(
        [
            _TRADE_DISC,
            mint_raw,
            _u64(1_000),
            _u64(2_000),
            b"\x01",
            USER_RAW,
            _i64(1_767_225_600),
            _u64(vsol),
            _u64(vtok),
            _u64(7),
            _u64(8),
            bytes(32),
            _u64(0),
            _u64(0),
            bytes(32),
            _u64(0),
            _u64(0),
            b"\x00",
            _u64(0),
            _u64(0),
            _u64(0),
            _i64(0),
            struct.pack("<I", len(text)) + text,
            b"\x00",
        ]
    )


def _trade_logs(event: bytes) -> list[str]:
    data = "Program data: " + base64.b64encode(event).decode("ascii")
    return [f"Program {PUMP_PROGRAM_ID} invoke [1]", data, f"Program {PUMP_PROGRAM_ID} success"]


def _config(ts: float, capacity: int = 4) -> dict[str, Any]:
    return {"ts": ts, "stream": "config", "payload": {"watch_capacity": capacity}}


def _portal_create(ts: float, mint: str) -> dict[str, Any]:
    payload = {"txType": "create", "mint": mint, "signature": f"create-{mint[:6]}"}
    payload.update({"name": "Pump", "symbol": "PMP"})
    return {"ts": ts, "stream": "pumpportal", "payload": payload}


def _logs(ts: float, signature: str, logs: list[str]) -> dict[str, Any]:
    value = {"signature": signature, "err": None, "logs": logs}
    notification = {"context": {"slot": 1}, "value": value}
    payload = {
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {"result": notification, "subscription": 7},
    }
    return {"ts": ts, "stream": "logs", "payload": payload}


def _transaction(ts: float, signature: str, logs: list[str]) -> dict[str, Any]:
    meta = {"err": None, "logMessages": logs}
    response = {"jsonrpc": "2.0", "id": 1, "result": {"meta": meta}}
    payload = {"signature": signature, "response": response}
    return {"ts": ts, "stream": "transaction", "payload": payload}


def _tick(ts: float, mint: str, vsol: int, vtok: int) -> dict[str, Any]:
    return {
        "kind": "tick",
        "mint": mint,
        "ts_utc": format_ts_utc(ts),
        "S": vsol,
        "T": vtok,
        "complete": False,
        "source": "rpc",
    }


def _scenario() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Frames as a recording holds them, and the ticks a faithful rebuild must reproduce."""
    frames = [
        _config(_START),
        _portal_create(_START + 1, MINT),
        _logs(_START + 2, "sig-a", _trade_logs(_trade_event(MINT_RAW, vsol=30, vtok=700))),
        _logs(_START + 3, "sig-b", _trade_logs(_trade_event(OTHER_RAW, vsol=40, vtok=800))),
        _logs(_START + 4, "sig-c", [f"Program {PUMP_PROGRAM_ID} invoke [1]", _TRUNCATED]),
        _transaction(
            _START + 4, "sig-c", _trade_logs(_trade_event(MINT_RAW, vsol=31, vtok=690))
        ),
    ]
    ticks = [_tick(_START + 2, MINT, 30, 700), _tick(_START + 4, MINT, 31, 690)]
    return frames, ticks


def _encode_lines(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n" for row in rows)


def _recorded(
    root: Path, name: str, frames: list[dict[str, Any]], ticks: list[dict[str, Any]]
) -> Path:
    """A sealed dataset: its raw feed, and the derived ticks a live recording would hold."""
    directory = root / "datasets" / name
    directory.mkdir(parents=True)
    (directory / FEED_NAME).write_bytes(_encode_lines(frames))
    (directory / EVENTS_NAME).write_bytes(_encode_lines(ticks))
    seal_directory(
        directory,
        recorded_from_utc=str(ticks[0]["ts_utc"]),
        recorded_to_utc=str(ticks[-1]["ts_utc"]),
        sources={"rpc": "rpc"},
        notes="synthetic feed",
    )
    return directory


def _rows(count: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(count):
        rows.append(
            {
                "kind": "tick",
                "mint": _ORDER_MINT if index % 4 == 0 else _QUIET_MINT,
                "ts_utc": format_ts_utc(_START + index),
                "S": 1_000 + index,
                "T": 2_000 + index,
                "complete": False,
                "source": "rpc",
            }
        )
    return rows


def _orders(_directory: Path) -> frozenset[str]:
    return frozenset({_ORDER_MINT})


def _plain_dataset(root: Path, name: str, rows: list[dict[str, object]]) -> Path:
    directory = root / "datasets" / name
    directory.mkdir(parents=True)
    (directory / EVENTS_NAME).write_bytes(_encode_lines(rows))
    (directory / GAPS_NAME).write_bytes(_GAPS)
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
            ts_utc=format_ts_utc(_START),
            source="paper",
            correlation_id="corr-1",
            idempotency_key="key-1",
            type="ConfigChanged",
            payload={"n": 1},
        )
        store.append(
            ts_utc=format_ts_utc(_START + 1),
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


# --- trim -------------------------------------------------------------------------------------


def test_trim_keeps_order_mints_and_is_byte_identical_on_rerun(tmp_path: Path) -> None:
    rows = _rows(400)
    _plain_dataset(tmp_path, "smoke", rows)

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
    _plain_dataset(tmp_path, "smoke", _rows(400))
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
    _plain_dataset(tmp_path, "smoke", _rows(120))
    trimmed = maintenance.trim(
        "smoke", root=tmp_path, max_events=10_000, seed=3, mints_with_orders=_orders
    )
    assert (trimmed / GAPS_NAME).read_bytes() == _GAPS
    assert all(row["kind"] == "tick" for row in load_dataset(trimmed).events)
    assert not (trimmed / FEED_NAME).exists()


def test_trim_refuses_an_existing_target_and_a_bad_name(tmp_path: Path) -> None:
    _plain_dataset(tmp_path, "smoke", _rows(40))
    maintenance.trim("smoke", root=tmp_path, max_events=10, seed=1, mints_with_orders=_orders)
    with pytest.raises(maintenance.MaintenanceRefused) as exc:
        maintenance.trim("smoke", root=tmp_path, max_events=10, seed=1, mints_with_orders=_orders)
    assert exc.value.fields["kind"] == "usage"
    with pytest.raises(maintenance.MaintenanceRefused) as bad:
        maintenance.trim(
            "../smoke", root=tmp_path, max_events=10, seed=1, mints_with_orders=_orders
        )
    assert bad.value.fields["kind"] == "usage"


# --- rebuild-ticks ----------------------------------------------------------------------------


def test_rebuild_reproduces_the_recorded_ticks_byte_for_byte(tmp_path: Path) -> None:
    frames, ticks = _scenario()
    source = _recorded(tmp_path, "live", frames, ticks)

    rebuilt = maintenance.rebuild_ticks("live", root=tmp_path)

    assert (rebuilt / EVENTS_NAME).read_bytes() == (source / EVENTS_NAME).read_bytes()
    assert (rebuilt / FEED_NAME).read_bytes() == (source / FEED_NAME).read_bytes()
    assert len(load_dataset(rebuilt).events) == len(ticks)


def test_rebuild_output_does_not_change_when_the_derived_file_is_deleted_or_corrupt(
    tmp_path: Path,
) -> None:
    frames, ticks = _scenario()
    source = _recorded(tmp_path, "live", frames, ticks)
    first = maintenance.rebuild_ticks("live", root=tmp_path)
    expected = (first / EVENTS_NAME).read_bytes()
    shutil.rmtree(first)

    (source / EVENTS_NAME).unlink()
    deleted = maintenance.rebuild_ticks("live", root=tmp_path)
    assert (deleted / EVENTS_NAME).read_bytes() == expected
    shutil.rmtree(deleted)

    (source / EVENTS_NAME).write_bytes(b'{"corrupt":true}\n')
    corrupt = maintenance.rebuild_ticks("live", root=tmp_path)
    assert (corrupt / EVENTS_NAME).read_bytes() == expected


def test_rebuild_refuses_a_truncated_notification_with_no_recorded_response(tmp_path: Path) -> None:
    frames, ticks = _scenario()
    frames = [frame for frame in frames if frame["stream"] != "transaction"]
    _recorded(tmp_path, "live", frames, ticks)

    with pytest.raises(CorruptFixture):
        maintenance.rebuild_ticks("live", root=tmp_path)
    assert not (tmp_path / "datasets" / "live-rebuilt").exists()


def test_rebuild_refuses_an_unrequested_response_and_a_missing_config(tmp_path: Path) -> None:
    frames, ticks = _scenario()
    unused = _trade_logs(_trade_event(MINT_RAW, vsol=1, vtok=1))
    extra = _transaction(_START + 5, "sig-unused", unused)
    _recorded(tmp_path, "extra", [*frames, extra], ticks)
    with pytest.raises(CorruptFixture):
        maintenance.rebuild_ticks("extra", root=tmp_path)

    no_config = [frame for frame in frames if frame["stream"] != "config"]
    _recorded(tmp_path, "noconfig", no_config, ticks)
    with pytest.raises(CorruptFixture):
        maintenance.rebuild_ticks("noconfig", root=tmp_path)


def test_rebuild_refuses_a_dataset_with_no_raw_feed(tmp_path: Path) -> None:
    _, ticks = _scenario()
    directory = tmp_path / "datasets" / "derived"
    directory.mkdir(parents=True)
    (directory / EVENTS_NAME).write_bytes(_encode_lines(ticks))
    seal_directory(
        directory,
        recorded_from_utc=str(ticks[0]["ts_utc"]),
        recorded_to_utc=str(ticks[-1]["ts_utc"]),
        sources={"rpc": "rpc"},
        notes="derived only",
    )
    with pytest.raises(CorruptFixture):
        maintenance.rebuild_ticks("derived", root=tmp_path)


def test_cli_rebuild_ticks_writes_the_rebuilt_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    frames, ticks = _scenario()
    _recorded(tmp_path / "var", "live", frames, ticks)

    assert main(["replay", "rebuild-ticks", "--dataset", "live"]) == EXIT_OK
    assert (tmp_path / "var" / "datasets" / "live-rebuilt" / EVENTS_NAME).is_file()


# --- import -----------------------------------------------------------------------------------


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


# --- parsing and guards -----------------------------------------------------------------------


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
    forbidden_prefixes = ("pumpgrok.grok", "pumpgrok.tools", "pumpgrok.execution.live")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    assert not {name.split(".")[0] for name in imported} & forbidden_roots
    assert not {name for name in imported if name.startswith(forbidden_prefixes)}
