"""Resync seeds exactly the held mints (MKT-06)."""

from __future__ import annotations

import random
from pathlib import Path

from pumpgrok.datafeed.mintbook import MintBook
from pumpgrok.datafeed.resync import resync_held
from pumpgrok.events.sources import SourceStatus, SourceSupervisor
from pumpgrok.replay.clock import FixtureClock


def test_resync_seeds_held_mints(tmp_path: Path) -> None:
    clock = FixtureClock(1_000.0)
    supervisor = SourceSupervisor(clock, random.Random(1), path=tmp_path / "events.sqlite")
    book = MintBook()
    book.hold("m2")
    book.hold("m1")
    seeded = resync_held(supervisor, book)
    assert seeded == ("m1", "m2")
    assert supervisor.held_mints == ("m1", "m2")
    assert supervisor.status_at(clock.now()) is SourceStatus.resyncing
    supervisor.close()


def test_resync_empty_book(tmp_path: Path) -> None:
    clock = FixtureClock(1_000.0)
    supervisor = SourceSupervisor(clock, random.Random(1), path=tmp_path / "events.sqlite")
    assert resync_held(supervisor, MintBook()) == ()
    supervisor.close()
