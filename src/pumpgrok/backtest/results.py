"""Shared per-fill result model for backtest and paper comparison (BT-02, PAP-01).

Backtest fills and paper ledger fills build from the same Fill model over the
same window, so a backtest result and the paper ledger compare field for
field. Money stays integer base units (lamports, token units); Decimal is
used only for ratios (price, filled fraction) and latency seconds. No wall
clock, no network, no forward-looking statements; every figure describes a
fill that already settled.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from decimal import Decimal
from typing import Any

from pumpgrok.core.adapter import Fill
from pumpgrok.replay.clock import parse_ts_utc

__all__ = [
    "OUTCOMES",
    "FillDetail",
    "SharedResult",
    "WindowComparison",
]

#: Outcomes a per-fill detail can carry: the adapter Fill statuses plus the
#: place tool statuses for attempts that never reached the adapter.
OUTCOMES: tuple[str, str, str, str] = ("filled", "partial", "rejected", "unknown")


@dataclass(frozen=True)
class FillDetail:
    """One fill with the per-fill fields BT-02 requires.

    price_avg is lamports per token base unit; venue_fee_lamports and
    network_cost_lamports are integer base units; latency_s is Decimal
    seconds; filled_fraction is a Decimal ratio; outcome names the terminal
    status. An attempt that never filled carries zeroed money fields and a
    rejected or unknown outcome.
    """

    price_avg: Decimal
    venue_fee_lamports: int
    network_cost_lamports: int
    latency_s: Decimal
    filled_fraction: Decimal
    outcome: str

    def __post_init__(self) -> None:
        """Fail closed on negative money, non-finite ratios or unknown outcomes."""
        for name in ("venue_fee_lamports", "network_cost_lamports"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative int")
        for name in ("price_avg", "latency_s", "filled_fraction"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be a finite non-negative Decimal")
        if self.outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {OUTCOMES}")

    @classmethod
    def from_fill(cls, fill: Fill, *, latency_s: Decimal) -> FillDetail:
        """One detail from an adapter Fill plus its seeded confirmation latency.

        The Fill model carries no latency field, so the caller supplies the
        latency the confirmation draw produced (paper path) or the harness
        synthesized (backtest path).
        """
        return cls(
            price_avg=fill.price_avg,
            venue_fee_lamports=fill.venue_fee_lamports,
            network_cost_lamports=fill.network_cost_lamports,
            latency_s=latency_s,
            filled_fraction=fill.filled_fraction,
            outcome=fill.status.value,
        )

    @classmethod
    def from_ledger_payload(cls, payload: Mapping[str, Any]) -> FillDetail:
        """One detail from a FillRecorded ledger payload.

        Outcome is filled when the recorded fraction reached 1, else partial.
        Force-close rows carry no latency key, so absent latency reads as zero.
        """
        fraction = Decimal(str(payload["filled_fraction"]))
        outcome = "filled" if fraction >= 1 else "partial"
        return cls(
            price_avg=Decimal(str(payload["price_avg"])),
            venue_fee_lamports=int(payload["venue_fee_lamports"]),
            network_cost_lamports=int(payload["network_cost_lamports"]),
            latency_s=Decimal(str(payload.get("latency_s", "0"))),
            filled_fraction=fraction,
            outcome=outcome,
        )

    @classmethod
    def empty(cls, outcome: str) -> FillDetail:
        """Zeroed detail for an attempt that never filled (rejected, unknown)."""
        return cls(
            price_avg=Decimal("0"),
            venue_fee_lamports=0,
            network_cost_lamports=0,
            latency_s=Decimal("0"),
            filled_fraction=Decimal("0"),
            outcome=outcome,
        )


@dataclass(frozen=True)
class WindowComparison:
    """Field-for-field verdict for two shared results over one window."""

    matched: bool
    differences: tuple[str, ...] = ()


@dataclass(frozen=True)
class SharedResult:
    """One evaluation window both engines describe with the same Fill model.

    run_id references the run manifest id from backtest.manifest, dataset
    names the recorded fixture, window bounds are epoch seconds, and fills
    holds the window fills in ledger order. Backtest builds from synthesized
    fills; paper builds from FillRecorded ledger rows; compare pairs them.
    """

    run_id: str
    dataset: str
    window_start_ts: float
    window_end_ts: float
    fills: tuple[FillDetail, ...] = ()

    @classmethod
    def from_fills(
        cls,
        *,
        run_id: str,
        dataset: str,
        window_start_ts: float,
        window_end_ts: float,
        fills: Sequence[Fill],
        latencies: Sequence[Decimal],
    ) -> SharedResult:
        """One result from backtest fills plus one latency per fill, in order."""
        if not run_id or not dataset:
            raise ValueError("run_id and dataset must be non-empty")
        if window_end_ts < window_start_ts:
            raise ValueError("window_end_ts must not precede window_start_ts")
        if len(fills) != len(latencies):
            raise ValueError("fills and latencies must pair one to one")
        details = tuple(
            FillDetail.from_fill(fill, latency_s=latency)
            for fill, latency in zip(fills, latencies, strict=True)
        )
        return cls(
            run_id=run_id,
            dataset=dataset,
            window_start_ts=window_start_ts,
            window_end_ts=window_end_ts,
            fills=details,
        )

    @classmethod
    def from_ledger_rows(
        cls,
        *,
        run_id: str,
        dataset: str,
        window_start_ts: float,
        window_end_ts: float,
        rows: Sequence[Mapping[str, Any]],
    ) -> SharedResult:
        """One result from paper ledger rows: FillRecorded rows inside the window.

        Other event types never become fills. Rows are read in ledger order and
        the window is half-open: start is included, end is excluded.
        """
        if not run_id or not dataset:
            raise ValueError("run_id and dataset must be non-empty")
        if window_end_ts < window_start_ts:
            raise ValueError("window_end_ts must not precede window_start_ts")
        details: list[FillDetail] = []
        for row in rows:
            if row.get("type") != "FillRecorded":
                continue
            payload = row.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("FillRecorded row without a payload mapping")
            stamp = parse_ts_utc(str(row["ts_utc"]))
            if window_start_ts <= stamp < window_end_ts:
                details.append(FillDetail.from_ledger_payload(payload))
        return cls(
            run_id=run_id,
            dataset=dataset,
            window_start_ts=window_start_ts,
            window_end_ts=window_end_ts,
            fills=tuple(details),
        )

    def compare(self, other: SharedResult) -> WindowComparison:
        """Pair two results fill by fill and report every field mismatch.

        Both results must name the same dataset and window bounds; comparing
        across windows raises instead of reporting a misleading diff.
        """
        if self.dataset != other.dataset:
            raise ValueError("shared results span different datasets")
        if (
            self.window_start_ts != other.window_start_ts
            or self.window_end_ts != other.window_end_ts
        ):
            raise ValueError("shared results span different windows")
        differences: list[str] = []
        if len(self.fills) != len(other.fills):
            differences.append(f"fills: {len(self.fills)} != {len(other.fills)}")
        for index, (ours, theirs) in enumerate(zip(self.fills, other.fills, strict=False)):
            for model_field in dataclass_fields(FillDetail):
                ours_value = getattr(ours, model_field.name)
                theirs_value = getattr(theirs, model_field.name)
                if ours_value != theirs_value:
                    differences.append(
                        f"fills[{index}].{model_field.name}: {ours_value} != {theirs_value}"
                    )
        return WindowComparison(matched=not differences, differences=tuple(differences))
