"""Fixtures for the promotion tests: one temp ledger per test, closed at teardown."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pumpgrok.ledger.store import LedgerStore


@pytest.fixture
def ledger_path(tmp_path) -> str:
    return str(tmp_path / "ledger.sqlite")


@pytest.fixture
def store(ledger_path: str) -> Iterator[LedgerStore]:
    ledger = LedgerStore(ledger_path)
    try:
        yield ledger
    finally:
        ledger.close()
