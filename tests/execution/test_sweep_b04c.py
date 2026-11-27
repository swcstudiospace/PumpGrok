"""Sweep B04c (EXEC-EX-33/34/36): regressions that fail on the pre-sweep base.

EXEC-EX-33 deposit-writer validation; EXEC-EX-34 single table-exists reader
shared with ``pumpgrok.ledger.deposit_reader``; EXEC-EX-36 PumpPortal term
removed (EXEC-D-36 accept recommended: no production use).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import pumpgrok.execution.deposits as deposits
import pumpgrok.ledger.deposit_reader as deposit_reader
from pumpgrok.execution.deposits import open_deposits, opening_deposit_writer
from pumpgrok.execution.fees import PAPER_DEFAULT_FEE_MODEL, FeeModelV2
from pumpgrok.ledger.store import LedgerStore


def test_writer_refuses_empty_mint() -> None:
    with pytest.raises(ValueError, match="mint"):
        opening_deposit_writer("", 1_000)


def test_writer_refuses_negative_deposit() -> None:
    with pytest.raises(ValueError, match="deposit_lamports"):
        opening_deposit_writer("Mint111111111111111111111111111111111111111", -1)


def test_writer_refuses_bool_deposit() -> None:
    with pytest.raises(ValueError, match="deposit_lamports"):
        opening_deposit_writer("Mint111111111111111111111111111111111111111", True)


def test_writer_accepts_valid_inputs() -> None:
    writer = opening_deposit_writer("Mint111111111111111111111111111111111111111", 0)
    assert callable(writer)


def test_deposits_shares_the_single_table_exists_reader() -> None:
    assert deposits._table_exists is deposit_reader._table_exists


def test_open_deposits_empty_without_sidecar_table(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    assert open_deposits(store) == {}


def test_pumpportal_term_is_removed() -> None:
    assert not hasattr(FeeModelV2, "pumpportal_fee")
    assert "pumpportal_fee_bps" not in FeeModelV2.__dataclass_fields__
    assert not hasattr(FeeModelV2, "buy_debit_v2")


def test_default_buy_debit_has_no_extra_term() -> None:
    model = PAPER_DEFAULT_FEE_MODEL
    filled = 1_000_000
    assert model.buy_debit(filled) == filled + model.network_cost()
    assert model.buy_net(filled) == filled - model.venue_fee(filled)
