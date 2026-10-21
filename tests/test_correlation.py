"""Correlation chains: one ULID root, child spans `<ulid>.<n>` on log records and rows (OBS-002)."""

from __future__ import annotations

import io
import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from pumpgrok.core.correlation import is_child_span, root_of
from pumpgrok.core.idempotency import derive_idempotency_key
from pumpgrok.core.ids import (
    ULID_RE,
    CorrelationId,
    IdFactory,
    bind_correlation,
    current_correlation,
    next_span,
)
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.logging import setup_logging
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng

# 2026-01-01T00:00:00Z
EPOCH_START = 1767225600.0


@pytest.fixture
def root_handlers() -> Iterator[None]:
    root = logging.getLogger()
    saved = list(root.handlers)
    level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in saved:
            root.removeHandler(handler)
    root.setLevel(level)


def test_correlation_id_chain(tmp_path: Path, root_handlers: None) -> None:
    ids = IdFactory(FixtureClock(start=EPOCH_START), make_rng())
    root = CorrelationId.new(ids)
    assert re.fullmatch(ULID_RE, str(root)) and not is_child_span(str(root))

    buffer = io.StringIO()
    setup_logging(mode="paper", profile="paper", environ={}, stream=buffer)
    store = LedgerStore(tmp_path / "ledger.sqlite")
    log = logging.getLogger("pumpgrok.test.chain")

    spans: list[str] = []
    with bind_correlation(root):
        for call in ("lookup", "simulate"):
            span = next_span(current_correlation())
            spans.append(str(span))
            with bind_correlation(span):
                log.info(f"tool call {call}")
                store.append(
                    ts_utc="2026-01-01T00:00:00.000001Z",
                    source="paper",
                    correlation_id=str(span),
                    idempotency_key=derive_idempotency_key(
                        "tool_call", "desk", {"call": call}, scope=str(span)
                    ),
                    type="JournalNote",
                    payload={"source": "paper", "seat": "desk", "note_kind": "note", "text": call},
                )

    assert spans == [f"{root}.1", f"{root}.2"]
    assert all(root_of(span) == str(root) for span in spans)

    records = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
    assert [record["correlation_id"] for record in records] == spans

    rows = store._db.execute("SELECT correlation_id FROM events ORDER BY seq").fetchall()
    assert [row[0] for row in rows] == spans
    store.close()


def test_unbound_log_has_null_correlation(root_handlers: None) -> None:
    buffer = io.StringIO()
    setup_logging(mode="paper", profile="paper", environ={}, stream=buffer)
    logging.getLogger("pumpgrok.test.unbound").info("no cycle yet")
    record = json.loads(buffer.getvalue().splitlines()[0])
    assert record["correlation_id"] is None
