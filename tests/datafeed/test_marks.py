"""Marks within 60 s on fake Clock; no timer while flat (MKT-08)."""

from __future__ import annotations

from pumpgrok.datafeed.marks import MarksLoop
from pumpgrok.datafeed.mintbook import MintBook
from pumpgrok.replay.clock import FixtureClock


def _loop(book: MintBook, clock: FixtureClock, sink: list) -> MarksLoop:
    return MarksLoop(book, clock, lambda mint: 7, lambda mint, price: sink.append((mint, price)))


def test_flat_means_no_timer() -> None:
    book = MintBook()
    clock = FixtureClock(1_000.0)
    sink: list = []
    loop = _loop(book, clock, sink)
    assert loop.scheduled is False
    assert loop.next_deadline() is None
    assert loop.poll() == ()
    assert sink == []


def test_held_mints_marked_within_60s() -> None:
    book = MintBook()
    book.hold("m1")
    book.hold("m2")
    clock = FixtureClock(1_000.0)
    sink: list = []
    loop = _loop(book, clock, sink)
    assert loop.scheduled is True
    assert loop.poll() == ("m1", "m2")
    assert sink == [("m1", 7), ("m2", 7)]
    # Next cadence: not due immediately, due again after 60 s.
    assert loop.poll() == ()
    clock.advance_to(1_060.0)
    assert loop.poll() == ("m1", "m2")


def test_marks_stop_starting_when_book_empties() -> None:
    book = MintBook()
    book.hold("m1")
    clock = FixtureClock(1_000.0)
    sink: list = []
    loop = _loop(book, clock, sink)
    loop.poll()
    book.release("m1")
    clock.advance_to(2_000.0)
    assert loop.poll() == ()
    assert loop.scheduled is False
    assert loop.next_deadline() is None
