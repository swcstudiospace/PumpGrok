"""Watch set bounded; held mints pinned; overflow counted (MKT-05, T-13-01a)."""

from __future__ import annotations

from pumpgrok.datafeed.watchset import WatchSet


def test_cap_never_exceeded_and_overflow_counted() -> None:
    watch = WatchSet(3)
    assert watch.discover("a") is True
    assert watch.discover("b") is True
    assert watch.discover("c") is True
    assert watch.discover("d") is False
    assert watch.discover("e") is False
    assert len(watch) == 3
    assert watch.overflow == 2
    assert watch.watched() == frozenset({"a", "b", "c"})


def test_held_mints_pinned_never_evicted() -> None:
    watch = WatchSet(2)
    watch.pin("held")
    assert watch.discover("x") is True
    assert watch.discover("y") is False  # full; held stays
    assert "held" in watch.watched()
    assert watch.remove("held") is False  # pinned refuses removal
    assert "held" in watch.watched()


def test_flood_stays_bounded() -> None:
    watch = WatchSet(5)
    for i in range(100):
        watch.discover(f"m{i}")
    assert len(watch) == 5
    assert watch.overflow == 95
