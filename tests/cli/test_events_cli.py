"""events dlq list, replay, and purge use the sidecar path from settings."""

from __future__ import annotations

import json
import socket
import sqlite3
from pathlib import Path

import pytest

from pumpgrok.cli import EXIT_CONFIG, EXIT_OK, main
from pumpgrok.config.settings import load_settings
from pumpgrok.events.dlq import replay
from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.store import EventStore
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH


def _seed(path: Path, name: str) -> str:
    event = Event(
        kind=EventKind.trade,
        entity_id="mint",
        payload={"n": name},
        occurred_at=name,
    )
    store = EventStore(path)
    store.write_dlq(event, reason="poison")
    return event.event_id


def test_dlq_list_replay_and_purge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    sidecar = tmp_path / "custom-events.sqlite"
    monkeypatch.setenv("PUMPGROK_EVENTS__ENABLED", "true")
    monkeypatch.setenv("PUMPGROK_EVENTS__SIDECAR_PATH", str(sidecar))
    event_id = _seed(sidecar, "row-a")
    other = _seed(sidecar, "row-b")

    assert main(["events", "dlq", "list"]) == EXIT_OK
    listed = json.loads(capsys.readouterr().out)
    assert {row["event_id"] for row in listed} == {event_id, other}

    assert main(["events", "dlq", "replay", event_id]) == EXIT_OK
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["event_id"] == event_id
    with sqlite3.connect(sidecar) as db:
        pending = db.execute("SELECT event_id FROM pending").fetchall()
        remaining = db.execute("SELECT event_id FROM dlq").fetchall()
    assert pending == [(event_id,)]
    assert remaining == [(other,)]

    assert main(["events", "dlq", "purge", other]) == EXIT_OK
    capsys.readouterr()
    with sqlite3.connect(sidecar) as db:
        assert db.execute("SELECT COUNT(*) FROM dlq").fetchone() == (0,)
    assert not (tmp_path / PAPER_LEDGER_PATH).exists()
    assert not (tmp_path / "var" / "desk" / "events.sqlite").exists()


def test_disabled_events_refuses_without_socket_or_paper_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PUMPGROK_EVENTS__ENABLED", "false")

    def _refuse_socket(*_args: object, **_kwargs: object) -> socket.socket:
        raise AssertionError("socket opened")

    monkeypatch.setattr(socket, "socket", _refuse_socket)
    monkeypatch.setattr(socket, "create_connection", _refuse_socket)
    assert main(["events", "dlq", "list"]) == EXIT_CONFIG
    captured = capsys.readouterr()
    assert "refused" in captured.err
    assert not (tmp_path / PAPER_LEDGER_PATH).exists()
    assert not (tmp_path / "var" / "desk" / "events.sqlite").exists()


def test_load_settings_does_not_open_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    load_settings()
    assert not (tmp_path / "var" / "desk" / "events.sqlite").exists()
    assert not (tmp_path / PAPER_LEDGER_PATH).exists()


def test_failed_replay_move_leaves_dlq_row(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    event_id = _seed(sidecar, "row-fail")
    store = EventStore(sidecar)
    try:
        store._db.execute("ALTER TABLE pending RENAME TO pending_hidden")
        with pytest.raises(sqlite3.OperationalError):
            replay(store, event_id)
        store._db.execute("ALTER TABLE pending_hidden RENAME TO pending")
        assert store.list_dlq() == [{"event_id": event_id, "reason": "poison"}]
        assert store.load_pending() == []
    finally:
        store.close()
