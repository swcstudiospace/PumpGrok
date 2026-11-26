<<<<<<< HEAD
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
=======
"""Watch set admission: held pins are never dropped; candidate overflow is counted."""

from __future__ import annotations

import pytest

from pumpgrok.datafeed.watchset import WatchSet


def test_pins_within_capacity_are_held_and_not_degraded() -> None:
    watch = WatchSet(max_watched_mints=3)
    assert watch.pin("H1") is True
    assert watch.pin("H2") is True
    assert watch.held == ("H1", "H2")
    assert watch.degraded is False
    assert "H1" in watch


def test_candidates_overflow_deterministically_and_are_counted() -> None:
    watch = WatchSet(max_watched_mints=2)
    assert watch.admit_candidate("C1") is True
    assert watch.admit_candidate("C2") is True
    assert watch.admit_candidate("C3") is False
    assert watch.admit_candidate("C4") is False
    assert watch.candidates == ("C1", "C2")
    assert watch.overflow == 2
    assert watch.displaced == 0
    assert watch.degraded is False


def test_readmitting_a_watched_candidate_is_idempotent_not_overflow() -> None:
    watch = WatchSet(max_watched_mints=1)
    assert watch.admit_candidate("C1") is True
    assert watch.admit_candidate("C1") is True
    assert watch.candidates == ("C1",)
    assert watch.overflow == 0


def test_held_pin_displaces_the_newest_candidate_and_keeps_every_position() -> None:
    watch = WatchSet(max_watched_mints=2)
    assert watch.admit_candidate("C1") is True
    assert watch.admit_candidate("C2") is True
    assert watch.pin("H1") is True
    assert watch.held == ("H1",)
    assert watch.candidates == ("C1",)
    assert watch.displaced == 1
    assert watch.degraded is False


def test_pinning_an_existing_candidate_promotes_it_without_growing_the_set() -> None:
    watch = WatchSet(max_watched_mints=2)
    assert watch.admit_candidate("C1") is True
    assert watch.admit_candidate("C2") is True
    assert watch.pin("C1") is True
    assert watch.held == ("C1",)
    assert watch.candidates == ("C2",)
    assert watch.displaced == 0
    assert watch.overflow == 0


def test_held_capacity_refuses_impossible_admission_and_signals_degraded() -> None:
    watch = WatchSet(max_watched_mints=2)
    assert watch.pin("H1") is True
    assert watch.pin("H2") is True
    assert watch.pin("H3") is False
    assert watch.held == ("H1", "H2")
    assert "H3" not in watch
    assert watch.refused_held == 1
    assert watch.degraded is True


def test_release_frees_the_slot_and_never_evicts_held_coverage() -> None:
    watch = WatchSet(max_watched_mints=2)
    assert watch.pin("H1") is True
    assert watch.admit_candidate("C1") is True
    assert watch.admit_candidate("C2") is False
    assert watch.held == ("H1",)
    watch.release("H1")
    assert "H1" not in watch
    assert watch.held == ()
    assert watch.pin("H2") is True


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "2"])
def test_capacity_must_be_a_positive_integer(bad: object) -> None:
    with pytest.raises(ValueError):
        WatchSet(max_watched_mints=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "   "])
def test_blank_mint_is_rejected(bad: str) -> None:
    watch = WatchSet(max_watched_mints=2)
    with pytest.raises(ValueError):
        watch.pin(bad)
    with pytest.raises(ValueError):
        watch.admit_candidate(bad)
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
