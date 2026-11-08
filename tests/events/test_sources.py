"""SourceSupervisor owns backoff, staleness, resync, and cursors."""

from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path

from pumpgrok.events.constants import (
    BACKOFF_FACTOR,
    BACKOFF_INITIAL_S,
    BACKOFF_JITTER_S,
    BACKOFF_MAX_S,
    STABLE_S,
    STALE_AFTER_S,
)
from pumpgrok.events.models import EventKind
from pumpgrok.events.sources import CURSOR_ROW, CURSOR_SCHEMA, SourceStatus, SourceSupervisor
from pumpgrok.events.store import EventStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng

_REPO = Path(__file__).resolve().parents[2]
_SOURCES = _REPO / "src" / "pumpgrok" / "events" / "sources.py"


def _delay(step: int, rng: object) -> float:
    base = min(BACKOFF_INITIAL_S * (BACKOFF_FACTOR**step), BACKOFF_MAX_S)
    draw = rng.random()  # type: ignore[attr-defined]
    return float(base) + float(draw) * BACKOFF_JITTER_S


def _supervisor(tmp_path: Path, *, seed: int = 7) -> SourceSupervisor:
    return SourceSupervisor(FixtureClock(0.0), make_rng(seed), path=tmp_path / "events.sqlite")


def test_silence_boundary_and_never_framed(tmp_path: Path) -> None:
    clock = FixtureClock(0.0)
    supervisor = SourceSupervisor(clock, make_rng(1), path=tmp_path / "events.sqlite")
    assert supervisor.last_frame_at is None
    assert supervisor.status_at(121.0) is not SourceStatus.stale
    assert supervisor.status_at(121.0) == SourceStatus.live

    supervisor.note_frame(0.0)
    assert supervisor.status_at(120.0) == SourceStatus.live
    assert supervisor.status_at(120.0) is not SourceStatus.stale
    assert supervisor.status_at(121.0) == SourceStatus.stale
    assert STALE_AFTER_S == 120.0
    supervisor.close()


def test_backoff_resets_only_after_stable_span(tmp_path: Path) -> None:
    clock = FixtureClock(0.0)
    rng = make_rng(7)
    twin = make_rng(7)
    supervisor = SourceSupervisor(clock, rng, path=tmp_path / "events.sqlite")
    supervisor.note_failure()
    clock.advance_to(STABLE_S - 1.0)
    supervisor.note_frame()
    short = supervisor.next_delay_s()
    assert short == _delay(1, twin)
    assert 2.0 <= short < 3.0

    clock.advance_to(clock.now() + STABLE_S)
    supervisor.note_frame()
    reset = supervisor.next_delay_s()
    assert reset == _delay(0, twin)
    assert 1.0 <= reset < 2.0
    supervisor.close()


def test_resync_records_mints_until_good_frame(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor.resync(("mint-a", "mint-b"))
    assert supervisor.held_mints == ("mint-a", "mint-b")
    assert supervisor.status_at(0.0) == SourceStatus.resyncing
    tree = ast.parse(_SOURCES.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "LedgerStore" not in imported
    assert not any(
        name == "pumpgrok.ledger" or name.startswith("pumpgrok.ledger.") for name in modules
    )
    supervisor.note_frame()
    assert supervisor.status_at(0.0) == SourceStatus.live
    assert supervisor.held_mints == ("mint-a", "mint-b")
    supervisor.close()


def test_corrupt_cursor_starts_clean(tmp_path: Path) -> None:
    path = tmp_path / "events.sqlite"
    store = EventStore(path)
    store.close()
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO cursors (name, value) VALUES (?, ?);",
        (CURSOR_ROW, "{"),
    )
    db.commit()
    db.close()

    clock = FixtureClock(0.0)
    supervisor = SourceSupervisor(clock, make_rng(3), path=path)
    assert supervisor.cursor_reset is True
    assert supervisor.cursor == {"schema": CURSOR_SCHEMA}
    supervisor.close()

    again = SourceSupervisor(clock, make_rng(3), path=path)
    assert again.cursor_reset is False
    assert again.cursor == {"schema": CURSOR_SCHEMA}
    again.close()


def test_bad_schema_version_resets_without_raising(tmp_path: Path) -> None:
    path = tmp_path / "events.sqlite"
    store = EventStore(path)
    store.close()
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO cursors (name, value) VALUES (?, ?);",
        (CURSOR_ROW, json.dumps({"schema": 99})),
    )
    db.commit()
    db.close()

    supervisor = SourceSupervisor(FixtureClock(0.0), make_rng(4), path=path)
    assert supervisor.cursor_reset is True
    assert supervisor.cursor == {"schema": CURSOR_SCHEMA}
    supervisor.close()


def test_source_status_is_not_a_second_event_kind() -> None:
    assert {member.value for member in SourceStatus} == {
        "live",
        "stale",
        "resyncing",
        "disconnected",
    }
    assert SourceStatus is not EventKind
    assert not issubclass(SourceStatus, EventKind)
    text = _SOURCES.read_text(encoding="utf-8")
    assert "class EventKind" not in text
    assert "DegradedState" not in text
    assert "WS_STALE_S" not in text
    assert SourceSupervisor.__module__ == "pumpgrok.events.sources"


def test_sources_open_no_socket_client() -> None:
    tree = ast.parse(_SOURCES.read_text(encoding="utf-8"))
    banned = {"httpx", "websockets", "websocket", "socket", "tenacity"}
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.append(node.module.split(".")[0])
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "time"
            and node.attr == "sleep"
        ):
            found.append("time.sleep")
    assert banned.isdisjoint(found)
    assert "time.sleep" not in found
