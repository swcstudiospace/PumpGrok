"""Regression: a successful adapter quote must pass QuoteOut validation (Greptile P1).

``Quote`` carries ``price_impact_pct`` (Decimal); ``QuoteOut`` carries
``price_impact`` (str) and forbids extra fields. ``run_quote`` must rename and
convert that field at the boundary, so every successful quote returns instead
of raising a ValidationError.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pumpgrok.core.adapter import Quote
from pumpgrok.execution.not_yet_implemented import NotYetImplementedAdapter
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.exec.quote import QuoteIn, QuoteOut, build_quote_tool, run_quote

MINT = "So11111111111111111111111111111111111111112"
OTHER = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class _QuotingAdapter(NotYetImplementedAdapter):
    """Adapter double that returns one fixed successful curve quote."""

    def __init__(self, quote: Quote) -> None:
        self._quote = quote

    async def quote(
        self, input_mint: str, output_mint: str, amount: int, slippage_bps: int
    ) -> Quote:
        return self._quote


def _quote() -> Quote:
    return Quote(
        quote_id="q-1",
        in_amount=1_000_000,
        out_amount=52_000,
        other_amount_threshold=51_480,
        price_impact_pct=Decimal("0.0123"),
        route_plan=[{"venue": "curve"}],
        context_slot=321,
        source="curve",
        expires_at=datetime(2016, 7, 30, 0, 0, 30, tzinfo=UTC),
    )


async def test_run_quote_returns_validated_payload_for_successful_quote() -> None:
    clock = FixtureClock(start=1469918176.385)
    result: dict[str, Any] = await run_quote(
        QuoteIn(input_mint=OTHER, output_mint=MINT, amount=1_000_000),
        _QuotingAdapter(_quote()),
        clock,
    )

    # price_impact_pct is renamed to price_impact and kept as its exact string.
    assert result["price_impact"] == "0.0123"
    assert "price_impact_pct" not in result
    assert result["quote_id"] == "q-1"
    assert result["out_amount"] == 52_000
    assert result["other_amount_threshold"] == 51_480
    assert result["route_plan"] == [{"venue": "curve"}]
    assert result["context_slot"] == 321
    assert result["source"] == "curve"
    # The returned payload is itself a valid QuoteOut.
    assert QuoteOut.model_validate(result).price_impact == "0.0123"


async def test_quote_tool_call_succeeds_end_to_end() -> None:
    clock = FixtureClock(start=1469918176.385)
    tool = build_quote_tool(_QuotingAdapter(_quote()), clock)
    out = await tool(QuoteIn(input_mint=OTHER, output_mint=MINT, amount=1_000_000))
    assert isinstance(out, QuoteOut)
    assert out.price_impact == "0.0123"
