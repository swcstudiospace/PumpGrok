"""Id edge tests: ULID monotonicity/width, atomic writes, and the uuid ban (R29)."""

from __future__ import annotations

import ast
import json
import random
import re
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.atomic_write import atomic_write_json
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation, next_span

REPO_ROOT = Path(__file__).resolve().parents[2]
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class _FixtureClock:
    """Fixed clock double: time only moves when advanced explicitly."""

    def __init__(self, now: float) -> None:
        self._now = now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def now(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._now

    def utc_iso(self) -> str:
        return datetime.fromtimestamp(self._now, UTC).isoformat()

    async def sleep(self, seconds: float) -> None:
        return None

    @asynccontextmanager
    async def timeout(self, seconds: float) -> AsyncIterator[None]:
        yield None


def _decode(crockford: str) -> int:
    value = 0
    for ch in crockford:
        value = value * 32 + _CROCKFORD.index(ch)
    return value


def test_ulids_monotonic_under_fixed_clock() -> None:
    factory = IdFactory(_FixtureClock(1469918176.385), random.Random(11))
    ulids = [factory.ulid() for _ in range(1000)]
    assert all(ULID_RE.match(u) for u in ulids)
    assert ulids == sorted(ulids)
    assert len(set(ulids)) == 1000


def test_ulids_carry_80_bit_randomness() -> None:
    ms = 1469918176385
    seed = 7
    factory = IdFactory(_FixtureClock(ms / 1000), random.Random(seed))
    expected_rand = random.Random(seed).getrandbits(80)
    first = factory.ulid()
    assert first.startswith("01ARYZ6S41")
    assert (_decode(first) & ((1 << 80) - 1)) == expected_rand
    rest = [factory.ulid() for _ in range(199)]
    lows = {_decode(u) & ((1 << 80) - 1) for u in [first, *rest]}
    assert len(lows) == 200
    assert max(lows) > (1 << 79)


def test_atomic_write_round_trips_and_leaves_no_tmp(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    atomic_write_json(target, {"b": 2, "a": [1]})
    assert json.loads(target.read_text(encoding="utf-8")) == {"b": 2, "a": [1]}
    leftovers = [p for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == []


def test_atomic_write_fails_loudly_and_leaves_no_tmp(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(OSError):
        atomic_write_json(blocker / "state.json", {"a": 1})
    assert not (blocker / "state.json").exists()


def test_atomic_write_non_os_failure_leaves_no_tmp(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        atomic_write_json(tmp_path / "state.json", {"amt": object()})
    assert list(tmp_path.iterdir()) == []


def test_uuid_is_banned_from_src_pumpgrok() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "src" / "pumpgrok").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                a.name == "uuid" or a.name.startswith("uuid.") for a in node.names
            ):
                offenders.append(f"{path}:{node.lineno}: import uuid")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "uuid" or (node.module or "").startswith("uuid."):
                    offenders.append(f"{path}:{node.lineno}: from uuid import")
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "uuid"
            ):
                offenders.append(f"{path}:{node.lineno}: uuid.{node.attr}")
    assert offenders == [], f"uuid usage banned by R29: {offenders}"


def test_span_numbering_restarts_per_root_and_stays_unique_within_one() -> None:
    root_a = CorrelationId("01ARYZ6S41TSV4RRFF7Q3V9J6A")
    root_b = CorrelationId("01ARYZ6S41TSV4RRFF7Q3V9J6B")
    with bind_correlation(root_a):
        first = next_span(root_a)
        assert first == f"{root_a}.1"
        with bind_correlation(first):
            assert next_span(first) == f"{root_a}.2"
    with bind_correlation(root_b):
        assert next_span(root_b) == f"{root_b}.1"
