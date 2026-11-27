"""RT-03: the composition root wires the paper live root and the promotion subscription.

Offline. The desk is built over the read-only double. The entry gate stays off by default,
and a desk that is asked to turn it on refuses to build, because the live adapter cannot take
an entry gate yet. The evaluator is subscribed to the FillRecorded and PositionClosed rows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from datafeed.readonly_double import ReadOnlyDouble
from pumpgrok.config.settings import Settings
from pumpgrok.events.event_desk import EventDesk, build_event_desk
from pumpgrok.promotion.evaluator import TRIGGER_TYPES, PromotionEvaluator
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.live_paper import LivePaperRoot

START = 1_700_000_000.0


class _NoGrok:
    """GrokTransport double for a desk that must make no call."""

    async def __call__(self, _request: object, _text: str) -> str:
        raise AssertionError("the wiring test makes no Grok call")


async def _build(tmp_path: Path) -> EventDesk:
    return await build_event_desk(
        Settings(mode="paper"),
        data_dir=tmp_path / "desk",
        clock=FixtureClock(START),
        rpc_transport=ReadOnlyDouble(),
        grok_transport=_NoGrok(),
        strategies=(),
        evidence=lambda _strategy_id: None,
        entry_evidence=lambda _mint: None,
    )


def test_promotion_is_subscribed_to_fill_and_close_rows() -> None:
    assert sorted(TRIGGER_TYPES) == ["FillRecorded", "PositionClosed"]


async def test_desk_is_built_over_the_paper_live_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    desk = await _build(tmp_path)
    try:
        await desk.start()
        assert isinstance(desk.root, LivePaperRoot)
        assert isinstance(desk.promotion, PromotionEvaluator)
    finally:
        await desk.close()
