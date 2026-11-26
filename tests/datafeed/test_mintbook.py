"""Mint book: records are bounded to the watch set and follow migration."""

from __future__ import annotations

from pumpgrok.datafeed.mintbook import MintBook
from pumpgrok.datafeed.watchset import WatchSet

TS = "2026-01-01T00:00:00.000000Z"
TS2 = "2026-01-01T00:00:05.000000Z"


def test_admitted_creation_is_recorded_as_created() -> None:
    book = MintBook(watch=WatchSet(max_watched_mints=2))
    assert book.admit_created("M1", TS) is True
    record = book.record("M1")
    assert record is not None
    assert (record.mint, record.stage, record.stage_ts_utc) == ("M1", "created", TS)
    assert len(book) == 1


def test_overflowing_creation_leaves_no_record() -> None:
    watch = WatchSet(max_watched_mints=1)
    book = MintBook(watch=watch)
    assert book.admit_created("M1", TS) is True
    assert book.admit_created("M2", TS) is False
    assert book.record("M2") is None
    assert len(book) == 1
    assert watch.overflow == 1


def test_duplicate_creation_is_idempotent() -> None:
    watch = WatchSet(max_watched_mints=2)
    book = MintBook(watch=watch)
    assert book.admit_created("M1", TS) is True
    assert book.admit_created("M1", TS2) is True
    record = book.record("M1")
    assert record is not None and record.stage_ts_utc == TS
    assert len(book) == 1
    assert watch.overflow == 0


def test_migration_updates_stage_only_for_a_watched_mint() -> None:
    book = MintBook(watch=WatchSet(max_watched_mints=2))
    assert book.mark_migrated("M9", TS2) is False
    assert book.admit_created("M1", TS) is True
    assert book.mark_migrated("M1", TS2) is True
    record = book.record("M1")
    assert record is not None
    assert (record.stage, record.stage_ts_utc) == ("migrated", TS2)


def test_displaced_candidate_record_is_pruned_from_the_book() -> None:
    watch = WatchSet(max_watched_mints=2)
    book = MintBook(watch=watch)
    assert book.admit_created("C1", TS) is True
    assert book.admit_created("C2", TS) is True
    assert watch.pin("H1") is True
    assert book.record("C2") is None
    assert book.record("C1") is not None
    assert len(book) == 1


def test_release_drops_the_record_and_frees_the_slot() -> None:
    watch = WatchSet(max_watched_mints=1)
    book = MintBook(watch=watch)
    assert book.admit_created("M1", TS) is True
    book.release("M1")
    assert book.record("M1") is None
    assert len(book) == 0
    assert book.admit_created("M2", TS) is True
