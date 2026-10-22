"""A sell approval never covers more than the size it states (review finding 3).

A SOL-notional ``human_sell`` approval carries ``size_lamports`` only. The
adapter prefers ``token_units`` over ``size_lamports``, so a request that also
carries units would sell a different amount than the one approved. Such a
request must not match.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord

_APPROVAL_ID = "apr-01ARYZ6S41TSV4RRFF7Q3V9J6Q"
_DECISION_ID = "01ARYZ6S41TSV4RRFF7Q3V9J6Q"
_MINT = "7xKXtg2CW87d97TXJSDpbD5HgznomR9rzme8H7Xwq"
_TICKET = "SOL-20260101-001"
_SIZE = 1_000_000


def _sell_approval(**over: object) -> ApprovalRecord:
    fields: dict[str, object] = {
        "id": _APPROVAL_ID,
        "kind": "human_sell",
        "ticket_id": _TICKET,
        "mint": _MINT,
        "size_lamports": _SIZE,
        "max_slippage_bps": 100,
        "approved_by": "human:alice",
        "raw_message": f"approve {_TICKET} {_MINT} 0.001 100",
        "at": datetime.fromtimestamp(1469918176.385, UTC),
    }
    fields.update(over)
    return ApprovalRecord(**fields)


def _sell_request(**over: object) -> OrderRequest:
    fields: dict[str, object] = {
        "ticket_id": _TICKET,
        "mint": _MINT,
        "side": "sell",
        "decision_id": _DECISION_ID,
        "size_lamports": _SIZE,
        "token_units": None,
        "max_slippage_bps": 100,
        "approval_id": _APPROVAL_ID,
        "correlation_id": _DECISION_ID,
    }
    fields.update(over)
    return OrderRequest(**fields)


def test_sol_sell_approval_matches_sol_sized_request() -> None:
    assert _sell_approval().matches(_sell_request())


def test_sol_sell_approval_refuses_request_with_larger_units() -> None:
    # Regression: the same SOL notional with a much larger unit count used to match.
    approval = _sell_approval()
    assert not approval.matches(_sell_request(token_units=5_000_000))


def test_sol_sell_approval_refuses_request_with_any_units() -> None:
    # Units that equal the position would still sell a different amount than approved.
    approval = _sell_approval()
    assert not approval.matches(_sell_request(token_units=1))
    assert not approval.matches(_sell_request(token_units=500_000))


def test_sol_sell_approval_refuses_units_only_request() -> None:
    # Without the approved notional the approval cannot be shown to bind this sell.
    approval = _sell_approval()
    assert not approval.matches(_sell_request(size_lamports=None, token_units=500_000))


def test_unit_sell_approval_matches_only_its_units() -> None:
    approval = _sell_approval(size_lamports=None, token_units=500_000)
    assert approval.matches(_sell_request(size_lamports=None, token_units=500_000))
    assert not approval.matches(_sell_request(size_lamports=None, token_units=600_000))


def test_mixed_sell_approval_requires_both_legs_to_agree() -> None:
    approval = _sell_approval(token_units=500_000)
    assert approval.matches(_sell_request(token_units=500_000))
    assert not approval.matches(_sell_request(token_units=600_000))
    assert not approval.matches(_sell_request(size_lamports=2_000_000, token_units=500_000))


def test_buy_approval_still_matches_sol_sized_buy() -> None:
    buy = _sell_approval(kind="human_buy")
    assert buy.matches(_sell_request(side="buy"))
    assert not buy.matches(_sell_request(side="buy", token_units=5_000_000))
