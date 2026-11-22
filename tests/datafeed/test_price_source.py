"""LivePriceSource fail-closed matrix (MKT-07)."""

from __future__ import annotations

from pumpgrok.datafeed.events import CurveTick, GapEvent
from pumpgrok.datafeed.price import LivePriceSource

TS = "2026-11-21T00:00:00.000000Z"
TS30 = "2026-11-21T00:00:30.000000Z"


def _tick(mint: str = "m1", *, complete: bool = False, source: str = "replay") -> CurveTick:
    return CurveTick.model_validate(
        {
            "mint": mint,
            "ts_utc": TS,
            "virtual_sol_reserves_lamports": 42_000_000_000,
            "virtual_token_reserves_units": 766_428_571,  # pragma: allowlist secret
            "real_sol_reserves_lamports": 12_000_000_000,
            "real_token_reserves_units": 500_000_000_000,
            "total_supply_units": 1_000_000_000_000,
            "complete": complete,
            "curve_source": source,
        }
    )


def test_disconnected_yields_none() -> None:
    src = LivePriceSource()
    src.on_tick(_tick())
    assert src.price("m1", now_epoch=0.0) is None
    assert src.entry_allowed("m1") is False


def test_connected_replay_prices() -> None:
    src = LivePriceSource()
    src.set_connected(True)
    src.on_tick(_tick())
    assert src.price("m1", now_epoch=0.0) == 42_000_000_000
    assert src.entry_allowed("m1") is True


def test_rpc_never_prices_while_assumed() -> None:
    src = LivePriceSource()
    src.set_connected(True)
    src.on_tick(_tick(source="rpc"))
    assert src.price("m1", now_epoch=0.0) is None
    assert src.entry_allowed("m1") is False


def test_completed_curve_refuses_entry() -> None:
    src = LivePriceSource()
    src.set_connected(True)
    src.on_tick(_tick(complete=True))
    assert src.entry_allowed("m1") is False
    # Price still readable for exit marks; the refusal is entry-only.
    assert src.price("m1", now_epoch=0.0) == 42_000_000_000


def test_gap_holds_position() -> None:
    src = LivePriceSource()
    src.set_connected(True)
    src.on_tick(_tick())
    assert src.is_stale("m1") is False
    src.on_gap(
        GapEvent.model_validate(
            {
                "mint": "m1",
                "ts_utc": TS30,
                "reason": "timeout",
                "from_ts_utc": TS,
                "to_ts_utc": TS30,
            }
        )
    )
    assert src.is_stale("m1") is True
    assert src.price("m1", now_epoch=1_795_219_230.0) == 42_000_000_000  # held, not new


def test_timeout_marks_zero() -> None:
    src = LivePriceSource(timeout_s=120.0)
    src.set_connected(True)
    src.on_tick(_tick())
    assert src.price("m1", now_epoch=1_795_219_200.0) == 42_000_000_000
    assert src.price("m1", now_epoch=1_795_219_400.0) == 0
