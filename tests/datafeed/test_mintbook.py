"""Mint book ledger (MKT-05)."""

from __future__ import annotations

from pumpgrok.datafeed.mintbook import MintBook


def test_hold_release() -> None:
    book = MintBook()
    assert len(book) == 0
    assert bool(book) is False
    book.hold("m1")
    book.hold("m2")
    assert book.is_held("m1") is True
    assert book.held() == frozenset({"m1", "m2"})
    book.release("m1")
    assert book.is_held("m1") is False
    assert len(book) == 1
