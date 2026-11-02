"""Replay hash pins: the library entry behind `pumpgrok verify`, measured in a clean directory.

CONTEXT D-08 and D-09. A pin is a recorded value that a test compares against; nothing here
scores or judges a hash (D-04). Measurement calls the same CLI verb as `pumpgrok verify`, so a
pinned value is the value the operator command prints.

The verb writes var/replay/<dataset>/ledger.sqlite and reads the operator ledger relative to the
current working directory. Callers therefore run it from an empty directory: tests use
monkeypatch.chdir(tmp_path), and --regen uses a fresh temporary directory.

    uv run python -m tests.replay.pin_support --regen

--regen prints the measured pins and never writes them. A re-pin is a deliberate edit of the pins
JSON plus a CHANGELOG before and after entry.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pumpgrok.cli import main as cli_main

PINS_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "replay" / "pins"
SMOKE_10M_EVENTS_HASH = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d"
TRADING_SMOKE_FIXTURE = "smoke"

_HASH_LINE = re.compile(r"^events\.hash=([0-9a-f]{64})$", re.MULTILINE)
_CHAIN_LINE = re.compile(r"^verify=CONSISTENT seq=(\d+) events=(\d+)$", re.MULTILINE)


class PinError(RuntimeError):
    """`pumpgrok verify` failed, or its output no longer has the expected shape."""


@dataclass(frozen=True)
class VerifyRun:
    fixture: str
    events_hash: str
    seq: int
    events_read: int
    ledger: Path


@contextlib.contextmanager
def pinned_process_state() -> Iterator[None]:
    """Hold the process state a pin depends on, and restore it on exit.

    Every PUMPGROK_* variable is removed for the run: an exported PUMPGROK_REPLAY__SEED
    or PUMPGROK_PROFILE would move the pinned row ids and hashes. The root logger's
    handlers and level are saved and restored, because the verb configures logging
    in-process and would otherwise leave its handler and INFO level behind.
    """
    exported = {name: value for name, value in os.environ.items() if name.startswith("PUMPGROK_")}
    for name in exported:
        del os.environ[name]
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    level_before = root.level
    try:
        yield
    finally:
        for name in [name for name in os.environ if name.startswith("PUMPGROK_")]:
            del os.environ[name]
        os.environ.update(exported)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                handler.close()
        root.handlers[:] = handlers_before
        root.setLevel(level_before)


def verify_fixture(fixture: str) -> VerifyRun:
    """Run `pumpgrok verify --fixture <fixture>` in-process from the current directory."""
    captured = io.StringIO()
    with pinned_process_state(), contextlib.redirect_stdout(captured):
        code = cli_main(["verify", "--fixture", fixture])
    output = captured.getvalue()
    if code != 0:
        raise PinError(f"pumpgrok verify --fixture {fixture} exited {code}")
    hashed = _HASH_LINE.search(output)
    chained = _CHAIN_LINE.search(output)
    if hashed is None or chained is None:
        raise PinError(f"unexpected verify output for {fixture!r}: {output!r}")
    return VerifyRun(
        fixture=fixture,
        events_hash=hashed.group(1),
        seq=int(chained.group(1)),
        events_read=int(chained.group(2)),
        ledger=Path.cwd() / "var" / "replay" / fixture / "ledger.sqlite",
    )


def ledger_rows(ledger: Path) -> list[dict[str, Any]]:
    """Every event row in seq order: seq, ts, type, source, idempotency_key, payload digest."""
    conn = sqlite3.connect(str(ledger))
    try:
        rows = conn.execute(
            "SELECT seq, ts_utc, type, source, idempotency_key, payload_json"
            " FROM events ORDER BY seq ASC;"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "seq": seq,
            "ts": ts,
            "type": event_type,
            "source": source,
            "idempotency_key": key,
            "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }
        for seq, ts, event_type, source, key, payload in rows
    ]


def load_pin(name: str) -> Any:
    """The recorded pin tests/fixtures/replay/pins/<name>.json: an object or a row list."""
    return json.loads((PINS_DIR / f"{name}.json").read_text(encoding="utf-8"))


def measure_pins() -> dict[str, Any]:
    """Measure every pin in a fresh directory. Pure measurement: nothing is written."""
    with tempfile.TemporaryDirectory() as scratch, contextlib.chdir(scratch):
        smoke_10m = verify_fixture("smoke-10m")
        trading = verify_fixture(TRADING_SMOKE_FIXTURE)
        rows = ledger_rows(trading.ledger)
    return {
        "smoke-10m": {
            "fixture": smoke_10m.fixture,
            "events_hash": smoke_10m.events_hash,
            "seq": smoke_10m.seq,
            "events_read": smoke_10m.events_read,
        },
        "trading_smoke": {
            "fixture": trading.fixture,
            "events_hash": trading.events_hash,
            "seq": trading.seq,
            "events_read": trading.events_read,
            "row_count": len(rows),
            "rows_file": "trading_smoke_rows.json",
        },
        "trading_smoke_rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["--regen"]:
        print("usage: python -m tests.replay.pin_support --regen (prints pins, writes nothing)")
        return 2
    print(json.dumps(measure_pins(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
