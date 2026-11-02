"""Trading smoke pin: the fixture that admits a trade (CONTEXT D-08).

smoke-10m admits no trade, so it proves little about risk, adapter or exit edits. This pin runs
the smoke fixture through the verify entry in an empty working directory (D-09) and compares its
events.hash, chain length and full row dump with the recorded pins. A move is a deliberate re-pin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pin_support import TRADING_SMOKE_FIXTURE, VerifyRun, ledger_rows, load_pin, verify_fixture


@pytest.fixture(scope="module")
def trading_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[VerifyRun, list[dict[str, Any]]]:
    scratch: Path = tmp_path_factory.mktemp("trading-smoke")
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(scratch)
        run = verify_fixture(TRADING_SMOKE_FIXTURE)
        rows = ledger_rows(run.ledger)
    return run, rows


def test_pin_names_the_smoke_fixture_with_a_64_char_hash_and_seq_above_one() -> None:
    pin = load_pin("trading_smoke")
    assert pin["fixture"] == TRADING_SMOKE_FIXTURE
    assert len(pin["events_hash"]) == 64
    assert pin["seq"] > 1


def test_events_hash_and_chain_length_match_the_pin(
    trading_run: tuple[VerifyRun, list[dict[str, Any]]],
) -> None:
    run, _ = trading_run
    pin = load_pin("trading_smoke")
    assert run.events_hash == pin["events_hash"]
    assert (run.seq, run.events_read) == (pin["seq"], pin["events_read"])


def test_row_count_matches_the_pin(trading_run: tuple[VerifyRun, list[dict[str, Any]]]) -> None:
    _, rows = trading_run
    assert len(rows) == load_pin("trading_smoke")["row_count"]


def test_full_row_dump_matches_the_pinned_rows(
    trading_run: tuple[VerifyRun, list[dict[str, Any]]],
) -> None:
    _, rows = trading_run
    assert rows == load_pin("trading_smoke_rows")
