<<<<<<< HEAD
"""Record/replay CLI verbs: sealed datasets and byte-identical reruns (REC-03)."""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.cli import main as cli_main
from pumpgrok.cli.serve_feed import FeedServer, health_probe
from pumpgrok.replay.fixtures import load_dataset

SMOKE = Path("tests/fixtures/replay/smoke")
FROM_TS = "2026-01-01T00:00:00.000Z"
TO_TS = "2026-01-01T00:00:01.250Z"


def test_record_seals_dataset(tmp_path: Path) -> None:
    target = tmp_path / "recorded"
    code = cli_main(["run", "--record", str(target), "--replay", str(SMOKE)])
    assert code == 0
    dataset = load_dataset(target)
    assert dataset.manifest.dataset == "recorded"
    assert len(dataset.events) == len(load_dataset(SMOKE).events)


def test_serve_health_probe(tmp_path: Path) -> None:

    server = FeedServer(SMOKE, 0)
    server.start()
    try:
        probe = health_probe(server.port)
        assert probe["ok"] is True
        assert probe["dataset"] == "smoke"
    finally:
        server.stop()


def test_replay_verbs_rerun_identical(tmp_path: Path) -> None:
    # trim: two runs produce byte-equal dataset trees
    first = tmp_path / "trim-a"
    second = tmp_path / "trim-b"
    args = ["replay", "trim", "--from", str(SMOKE), "--name", "trimmed"]
    tail = ["--from-ts", FROM_TS, "--to-ts", TO_TS]
    assert cli_main([*args, "--to", str(first), *tail]) == 0
    assert cli_main([*args, "--to", str(second), *tail]) == 0
    for name in ("manifest.json", "events.jsonl"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    # rebuild-ticks: two runs produce a byte-equal tick file
    ticks_a = tmp_path / "ticks-a.json"
    ticks_b = tmp_path / "ticks-b.json"
    base = ["replay", "rebuild-ticks", "--from", str(SMOKE)]
    assert cli_main([*base, "--to", str(ticks_a)]) == 0
    assert cli_main([*base, "--to", str(ticks_b)]) == 0
    assert ticks_a.read_bytes() == ticks_b.read_bytes()
    # import: byte-equal for the same external tick file
    ticks_file = tmp_path / "ticks.json"
    source = load_dataset(SMOKE)
    ticks_file.write_bytes(
        b"\n".join(json.dumps(event, sort_keys=True).encode() for event in source.events) + b"\n"
    )
    i1 = tmp_path / "imp-a"
    i2 = tmp_path / "imp-b"
    imp = ["replay", "import", "--source", str(ticks_file), "--name", "imported"]
    assert cli_main([*imp, "--to", str(i1)]) == 0
    assert cli_main([*imp, "--to", str(i2)]) == 0
    for name in ("manifest.json", "events.jsonl"):
        assert (i1 / name).read_bytes() == (i2 / name).read_bytes()
    load_dataset(i1)  # sealed, loadable
=======
"""Replay maintenance verbs and the record/serve verbs (16-04, 16-08). Synthetic data only.

Datasets are built under tmp_path. Transports are fakes; no test opens a socket.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import struct
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.cli import main, verbs_state
from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_LEDGER, EXIT_LIVE, EXIT_OK
from pumpgrok.datafeed import feed_loop
from pumpgrok.datafeed import transport as datafeed_transport
from pumpgrok.datafeed.logs import PUMP_PROGRAM_ID
from pumpgrok.datafeed.transport import RecordingJsonRpc
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay import maintenance
from pumpgrok.replay.clock import FixtureClock, WallClock, format_ts_utc
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, CorruptFixture, load_dataset
from pumpgrok.replay.live_recorder import FEED_NAME, GAPS_NAME, LiveRecorder, seal_directory

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
        _transaction(_START + 4, "sig-c", _trade_logs(_trade_event(MINT_RAW, vsol=31, vtok=690))),
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
            payload={"source": "paper", "by": "test-operator", "keys_changed": ["n"]},
        )
        store.append(
            ts_utc=format_ts_utc(_START + 1),
            source=second_source,
            correlation_id="corr-2",
            idempotency_key="key-2",
            type="ConfigChanged",
            payload={"source": second_source, "by": "test-operator", "keys_changed": ["n"]},
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


# --- run --record and live serve (16-08) -----------------------------------------------------

_RPC = "https://rpc.example.invalid"
_QUERY_SECRET = "querysecretvalue"
_HEADER_SECRET = "headersecretvalue"


class _FakeRpc:
    """JSON-RPC double. Answers getTransaction from a fixture dict and records every call."""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = {} if responses is None else responses
        self.calls: list[dict[str, Any]] = []

    async def send(self, url: str, frame: dict[str, Any]) -> object:
        self.calls.append(frame)
        if frame.get("method") != "getTransaction":
            return {"jsonrpc": "2.0", "id": 1, "result": 1}
        params = frame.get("params")
        signature = params[0] if isinstance(params, list) and params else ""
        return self.responses[str(signature)]


class _Logged:
    """Recorder double that keeps call order and forwards to a real LiveRecorder."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.calls: list[str] = []

    def record_frame(self, raw: dict[str, object]) -> None:
        self.calls.append("frame")
        self.inner.record_frame(raw)

    def record(self, observation: Any) -> None:
        self.calls.append("observation")
        self.inner.record(observation)

    def record_gap(self, gap: Any) -> None:
        self.inner.record_gap(gap)

    def seal(self, *ledgers: Any) -> None:
        self.inner.seal(*ledgers)


def _open_factory(
    frames: dict[str, list[dict[str, Any]]],
) -> Callable[..., AsyncIterator[dict[str, Any]]]:
    async def _open(url: str, *, stream: str) -> AsyncIterator[dict[str, Any]]:
        for frame in frames[stream]:
            yield frame

    return _open


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    frames: dict[str, list[dict[str, Any]]],
    responses: dict[str, dict[str, Any]],
) -> _FakeRpc:
    fake = _FakeRpc(responses)
    monkeypatch.setattr(datafeed_transport, "open_websocket", _open_factory(frames))
    monkeypatch.setattr(datafeed_transport, "make_read_transport", lambda endpoint: fake)
    return fake


def _logging_factory(holder: dict[str, _Logged]) -> Callable[..., _Logged]:
    def _factory(dataset_dir: Path, *, clock: Any) -> _Logged:
        logged = _Logged(LiveRecorder(dataset_dir, clock=clock))
        holder["logged"] = logged
        return logged

    return _factory


def _secret_create() -> dict[str, Any]:
    raw = _portal_create(0.0, MINT)["payload"]
    if not isinstance(raw, dict):
        raise AssertionError("portal create payload is not an object")
    payload: dict[str, Any] = raw
    payload["uri"] = (
        "https://example.invalid/meta?api-key="
        + _QUERY_SECRET
        + "&key="
        + _QUERY_SECRET
        + "&token="
        + _QUERY_SECRET
    )
    payload["headers"] = {"Authorization": "Bearer " + _HEADER_SECRET}
    return payload


def _record_streams() -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    full = _trade_logs(_trade_event(MINT_RAW, vsol=31, vtok=690))
    frames = {
        "pumpportal": [_secret_create()],
        "logs": [
            _logs(0.0, "sig-a", _trade_logs(_trade_event(MINT_RAW, vsol=30, vtok=700)))["payload"],
            _logs(0.0, "sig-c", [f"Program {PUMP_PROGRAM_ID} invoke [1]", _TRUNCATED])["payload"],
        ],
    }
    response = {"jsonrpc": "2.0", "id": 1, "result": {"meta": {"err": None, "logMessages": full}}}
    return frames, {"sig-c": response}


def _feed_rows(directory: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (directory / FEED_NAME).read_text().splitlines()]


@pytest.fixture
def frozen_record_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give `run --record` a clock that never advances, so its record deadline never fires.

    `_run_record` builds the feed loop clock with WallClock(), and the loop ends once
    monotonic() reaches start + duration. Under CPU load, startup can use up that window, so
    no frame is recorded and sealing refuses. With a frozen clock the loop ends only when both
    fake sources close, which they do once their frames are exhausted. The fakes never block,
    so no clock timeout fires.
    """
    monkeypatch.setattr(verbs_state, "WallClock", lambda: FixtureClock(start=_START))


@pytest.mark.usefixtures("frozen_record_clock")
def test_record_with_replay_or_bad_duration_is_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--record", "set", "--replay", "dir", "--duration", "1"]) == EXIT_CONFIG
    assert main(["run", "--record", "set"]) == EXIT_CONFIG
    assert main(["run", "--record", "set", "--duration", "0"]) == EXIT_CONFIG
    assert main(["run", "--record", "set", "--duration", "-1"]) == EXIT_CONFIG
    assert not (tmp_path / "var" / "datasets").exists()


@pytest.mark.usefixtures("frozen_record_clock")
def test_record_live_mode_exits_3_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["run", "--mode", "live", "--record", "live-set", "--duration", "1"])
    assert code == EXIT_LIVE
    assert not (tmp_path / "var" / "datasets").exists()


@pytest.mark.usefixtures("frozen_record_clock")
def test_record_seals_dataset_and_stamps_observations_at_frame_ts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    frames, responses = _record_streams()
    _install_fakes(monkeypatch, frames, responses)
    holder: dict[str, _Logged] = {}
    monkeypatch.setattr(feed_loop, "recorder_factory", _logging_factory(holder))
    assert main(["run", "--record", "recorded", "--duration", "1"]) == EXIT_OK
    directory = tmp_path / "var" / "datasets" / "recorded"
    loaded = load_dataset(directory)
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert FEED_NAME in manifest["sha256"]
    rows = _feed_rows(directory)
    configs = [row for row in rows if row["stream"] == "config"]
    assert len(configs) == 1
    assert configs[0]["payload"] == {"watch_capacity": feed_loop.WATCH_CAPACITY}
    logs = [row for row in rows if row["stream"] == "logs"]
    txs = [row for row in rows if row["stream"] == "transaction"]
    assert len(txs) == 1
    assert set(txs[0]["payload"]) == {"signature", "response"}
    assert txs[0]["payload"]["signature"] == "sig-c"
    events = list(loaded.events)
    assert len(events) == 2
    assert events[0]["ts_utc"] == format_ts_utc(logs[0]["ts"])
    assert events[1]["ts_utc"] == format_ts_utc(logs[1]["ts"])
    assert events[1]["ts_utc"] == format_ts_utc(txs[0]["ts"])
    calls = holder["logged"].calls
    assert calls[0] == "frame"
    seen_frame = False
    for name in calls:
        if name == "frame":
            seen_frame = True
        else:
            assert seen_frame
    text = (directory / FEED_NAME).read_text(encoding="utf-8")
    assert "REDACTED" in text
    assert _QUERY_SECRET not in text
    assert _HEADER_SECRET not in text
    rebuilt = maintenance.rebuild_ticks("recorded", root=tmp_path / "var")
    assert (rebuilt / EVENTS_NAME).read_bytes() == (directory / EVENTS_NAME).read_bytes()


@pytest.mark.usefixtures("frozen_record_clock")
def test_record_refuses_a_non_fresh_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    taken = tmp_path / "var" / "datasets" / "taken"
    taken.mkdir(parents=True)
    (taken / "foreign.txt").write_text("x", encoding="utf-8")
    assert main(["run", "--record", "taken", "--duration", "1"]) == EXIT_CONFIG
    assert (taken / "foreign.txt").is_file()
    assert not (taken / FEED_NAME).exists()


@pytest.mark.usefixtures("frozen_record_clock")
def test_record_mints_restricts_events_and_rejects_a_bad_mint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    bad = ["run", "--record", "bad", "--duration", "1", "--mints", "not-a-mint"]
    assert main(bad) == EXIT_CONFIG
    frames = {
        "pumpportal": [
            _portal_create(0.0, MINT)["payload"],
            _portal_create(0.0, OTHER)["payload"],
        ],
        "logs": [
            _logs(0.0, "sig-m", _trade_logs(_trade_event(MINT_RAW, vsol=30, vtok=700)))["payload"],
            _logs(0.0, "sig-o", _trade_logs(_trade_event(OTHER_RAW, vsol=40, vtok=800)))["payload"],
        ],
    }
    _install_fakes(monkeypatch, frames, {})
    assert main(["run", "--record", "filtered", "--duration", "1", "--mints", MINT]) == EXIT_OK
    events = list(load_dataset(tmp_path / "var" / "datasets" / "filtered").events)
    assert events
    assert {row["mint"] for row in events} == {MINT}


def test_live_serve_mode_live_exits_3_without_calling_the_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    called: list[str] = []

    def _factory(endpoint: str) -> _FakeRpc:
        called.append(endpoint)
        return _FakeRpc()

    monkeypatch.setattr(datafeed_transport, "make_read_transport", _factory)
    code = main(["live", "serve", "--mode", "live", "--rpc", _RPC])
    assert code == EXIT_LIVE
    assert called == []


def test_live_serve_other_mode_is_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["live", "serve", "--mode", "replay", "--rpc", _RPC]) == EXIT_CONFIG
    missing = main(["live", "serve"])
    assert missing != 0
    assert "--rpc" in capsys.readouterr().err


def test_live_serve_once_is_one_paper_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(datafeed_transport, "make_read_transport", lambda endpoint: _FakeRpc())
    assert main(["live", "serve", "--rpc", _RPC, "--once"]) == EXIT_OK
    assert feed_loop.cycles_run == 1


def test_recording_jsonrpc_refuses_a_method_outside_the_allowlist() -> None:
    rpc = RecordingJsonRpc(_RPC, _FakeRpc(), None, WallClock())
    with pytest.raises(ValueError, match="not permitted"):
        asyncio.run(rpc.rpc("sendTransaction", []))


def test_live_serve_does_not_read_the_confirmation_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    original = os.environ.get

    def _guarded(key: str, default: str | None = None) -> str | None:
        if key == "PUMPGROK_CONFIRMATION_KEY":
            raise AssertionError("confirmation key was read")
        return original(key, default)

    monkeypatch.setattr(os.environ, "get", _guarded)
    monkeypatch.setattr(datafeed_transport, "make_read_transport", lambda endpoint: _FakeRpc())
    assert main(["live", "serve", "--rpc", _RPC, "--once"]) == EXIT_OK
    text = Path(feed_loop.__file__).read_text(encoding="utf-8")
    transport_text = Path(datafeed_transport.__file__).read_text(encoding="utf-8")
    assert "LiveAdapter" not in text
    assert "LiveAdapter" not in transport_text


def test_dispatch_refuses_live_before_settings_and_wallet() -> None:
    source = Path(datafeed_transport.__file__).parents[1].joinpath("cli", "dispatch.py")
    body = source.read_text(encoding="utf-8").split("def _dispatch", 1)[1]
    assert body.index("_refuse_disabled_live") < body.index("load_settings")
    assert body.index("load_settings") < body.index("_confirm_live_wallet")


def test_record_tests_import_no_llm_or_signing_module() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    blocked = ("llm", "live_adapter", "solders", "keypair", "nacl")
    assert not [name for name in names if any(part in name for part in blocked)]
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
