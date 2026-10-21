"""WR-03: tool envelopes carry the injected Clock's timestamp (never wall time)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools._common import meta_now, utcnow
from pumpgrok.tools.desk.docs_search import DocsSearchIn, build_docs_search_tool

START = 1469918176.385
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_utcnow_reads_injected_clock() -> None:
    clock = FixtureClock(start=START)
    assert utcnow(clock) == datetime.fromtimestamp(START, UTC)


def test_meta_now_carries_clock_timestamp() -> None:
    clock = FixtureClock(start=START)
    meta = meta_now("desk", None, clock)
    assert meta.fetched_at == datetime.fromtimestamp(START, UTC)
    assert meta.correlation_id == "none"
    assert meta.freshness_s == 0.0


async def test_tool_envelope_carries_clock_timestamp() -> None:
    clock = FixtureClock(start=START)
    tool = build_docs_search_tool(REPO_ROOT, clock)
    out = await tool(DocsSearchIn(query="TOOL_CATALOG", limit=1))
    assert out.meta.fetched_at == datetime.fromtimestamp(START, UTC)
