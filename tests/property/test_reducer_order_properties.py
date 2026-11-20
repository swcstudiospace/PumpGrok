"""QLT-07: ledger reducer ordering invariants (ledger/reducer.py is a pure left fold).

The reducer folds stored rows in seq order. These properties hold for any generated row list: the
fold stamps each seq, folding a prefix then the rest equals folding the whole list, unknown event
types only append to unknown_events, and buy fills commute on every field that is a sum. Peak
equity is an order-dependent running maximum, so it is excluded from the commutation comparison.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from pumpgrok.ledger.reducer import LedgerState, dump_state, initial_state, reduce

SEQ_STEP = st.integers(min_value=1, max_value=5)
AMOUNT = st.integers(min_value=0, max_value=10**9)
MINT = st.sampled_from(["mintA", "mintB", "mintC"])
KIND = st.sampled_from(["known", "unknown"])
ROW_COUNT = 12
FILL_COUNT = 6


def _genesis() -> LedgerState:
    return initial_state(source="paper", initial_equity_lamports=10**12, day_utc="2026-01-01")


def _event(seq: int, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": seq,
        "type": type_,
        "ts_utc": "2026-01-01T00:00:00.000000Z",
        "correlation_id": f"cid-{seq}",
        "payload": payload,
    }


def _rows(steps: list[int], kinds: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seq = 0
    for index, step in enumerate(steps):
        seq += step
        if kinds[index] == "unknown":
            rows.append(_event(seq, "FutureThing", {"n": index}))
        else:
            rows.append(_event(seq, "HaltSet", {"reason": f"halt-{index}"}))
    return rows


def _opens(mints: list[str]) -> list[dict[str, Any]]:
    return [
        _event(index + 1, "PositionOpened", {"mint": mint, "ticket_id": f"t-{mint}"})
        for index, mint in enumerate(sorted(set(mints)))
    ]


def _fills(mints: list[str], amounts: list[int]) -> list[dict[str, Any]]:
    return [
        _event(
            1000 + index,
            "FillRecorded",
            {
                "mint": mint,
                "side": "buy",
                "filled_units": 1,
                "cash_delta_lamports": -amount,
                "venue_fee_lamports": amount % 7,
                "network_cost_lamports": amount % 3,
            },
        )
        for index, (mint, amount) in enumerate(zip(mints, amounts, strict=True))
    ]


def _fold(rows: list[dict[str, Any]], start: LedgerState | None = None) -> LedgerState:
    state = _genesis() if start is None else start
    for row in rows:
        state = reduce(state, row)
    return state


@settings(max_examples=200, deadline=None)
@given(
    steps=st.lists(SEQ_STEP, min_size=1, max_size=ROW_COUNT),
    kinds=st.lists(KIND, min_size=ROW_COUNT, max_size=ROW_COUNT),
)
def test_fold_stamps_each_row_seq_and_ends_at_the_last_seq(
    steps: list[int], kinds: list[str]
) -> None:
    rows = _rows(steps, kinds)
    state = _genesis()
    for row in rows:
        state = reduce(state, row)
        assert state.seq == row["seq"]
    assert state.seq == rows[-1]["seq"]


@settings(max_examples=200, deadline=None)
@given(
    steps=st.lists(SEQ_STEP, min_size=1, max_size=ROW_COUNT),
    kinds=st.lists(KIND, min_size=ROW_COUNT, max_size=ROW_COUNT),
    cut=st.integers(min_value=0, max_value=ROW_COUNT),
)
def test_folding_a_prefix_then_the_rest_equals_folding_the_whole(
    steps: list[int], kinds: list[str], cut: int
) -> None:
    rows = _rows(steps, kinds)
    split = min(cut, len(rows))
    whole = _fold(rows)
    resumed = _fold(rows[split:], start=_fold(rows[:split]))
    assert resumed == whole


@settings(max_examples=200, deadline=None)
@given(
    steps=st.lists(SEQ_STEP, min_size=1, max_size=ROW_COUNT),
    kinds=st.lists(KIND, min_size=ROW_COUNT, max_size=ROW_COUNT),
)
def test_unknown_events_only_append_to_unknown_events(steps: list[int], kinds: list[str]) -> None:
    rows = _rows(steps, kinds)
    expected = [f"{row['seq']}:FutureThing" for row in rows if row["type"] == "FutureThing"]
    state = _fold(rows)
    assert state.unknown_events == expected
    known_only = [row for row in rows if row["type"] != "FutureThing"]
    observed = dump_state(state)
    baseline = dump_state(_fold(known_only))
    for name in ("unknown_events", "seq"):
        observed.pop(name)
        baseline.pop(name)
    assert observed == baseline


@settings(max_examples=200, deadline=None)
@given(
    mints=st.lists(MINT, min_size=FILL_COUNT, max_size=FILL_COUNT),
    amounts=st.lists(AMOUNT, min_size=FILL_COUNT, max_size=FILL_COUNT),
    order=st.permutations(list(range(FILL_COUNT))),
)
def test_buy_fills_commute_on_every_summed_field(
    mints: list[str], amounts: list[int], order: list[int]
) -> None:
    opens = _opens(mints)
    fills = _fills(mints, amounts)
    reordered = [fills[index] for index in order]
    straight = dump_state(_fold([*opens, *fills]))
    shuffled = dump_state(_fold([*opens, *reordered]))
    for state in (straight, shuffled):
        state.pop("peak_equity_lamports")
        state.pop("seq")
    assert straight == shuffled
