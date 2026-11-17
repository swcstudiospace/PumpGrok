"""STR-01: the strategy protocol, its read-only context, Intent, and the version id.

A hook receives one frozen StrategyContext and returns Intents. The context
carries immutable snapshots only: no store, no clock, no ledger handle.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import uuid
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, ClassVar

import pytest

from pumpgrok.strategies import (
    Intent,
    Strategy,
    StrategyContext,
    TapePoint,
    TickSnapshot,
    version_id,
)
from pumpgrok.upgrade.bounds import KeyBound

SAMPLE_BODY = """
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from pumpgrok.strategies import Intent, StrategyContext
from pumpgrok.upgrade.bounds import KeyBound


class SampleStrategy:
    strategy_id: ClassVar[str] = "sample"
    BOUNDS: ClassVar[Mapping[str, KeyBound]] = {
        "threshold": KeyBound(minimum=1, maximum=10),
    }
    DEFAULTS: ClassVar[Mapping[str, Any]] = {"threshold": 5}

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]:
        if context.tick.price_lamports < self.DEFAULTS["threshold"]:
            return ()
        return (
            Intent(
                strategy_id=self.strategy_id,
                mint=context.tick.mint,
                side="buy",
                size_lamports=1_000,
                decision_id="d-1",
                reason="threshold crossed",
                version_id=context.version_id,
            ),
        )
"""


def _tick() -> TickSnapshot:
    return TickSnapshot(
        mint="MintA",
        ts=1_000.0,
        launch_ts=900.0,
        price_lamports=7,
        unique_buyers=6,
        curve_progress=0.05,
    )


def _load_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> type[Strategy]:
    name = f"strat_src_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text(body, encoding="ascii")
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module(name)
    cls: type[Strategy] = module.SampleStrategy
    return cls


class _DefaultsOnly:
    strategy_id: ClassVar[str] = "defaults_only"
    BOUNDS: ClassVar[dict[str, KeyBound]] = {"rate": KeyBound(minimum=1, maximum=9)}
    DEFAULTS: ClassVar[dict[str, Any]] = {"rate": 3}


def test_version_id_is_stable_for_identical_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cls = _load_sample(tmp_path, monkeypatch, SAMPLE_BODY)
    params = dict(cls.DEFAULTS)
    assert version_id(cls, params) == version_id(cls, params)


def test_version_id_changes_when_one_default_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cls = _load_sample(tmp_path, monkeypatch, SAMPLE_BODY)
    base = dict(cls.DEFAULTS)
    changed = {**base, "threshold": 6}
    assert version_id(cls, base) != version_id(cls, changed)


def test_version_id_changes_when_module_source_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cls = _load_sample(tmp_path, monkeypatch, SAMPLE_BODY)
    params = dict(cls.DEFAULTS)
    before = version_id(cls, params)
    module_file = Path(importlib.import_module(cls.__module__).__file__ or "")
    module_file.write_text(SAMPLE_BODY + "\n# code edit\n", encoding="ascii")
    after = version_id(cls, params)
    assert before != after


def test_version_id_is_sha256_hex() -> None:
    value = version_id(_DefaultsOnly, dict(_DefaultsOnly.DEFAULTS))
    assert len(value) == 64
    assert all(ch in "0123456789abcdef" for ch in value)


def test_strategy_context_rejects_attribute_assignment() -> None:
    ctx = StrategyContext(now=1.0, version_id="v", tick=_tick(), tape=())
    with pytest.raises(FrozenInstanceError):
        ctx.now = 2.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        ctx.tape = (TapePoint(ts=1.0, price_lamports=1),)  # type: ignore[misc]


def test_strategy_context_exposes_only_snapshot_fields() -> None:
    names = {field.name for field in dataclasses.fields(StrategyContext)}
    assert names == {"now", "version_id", "tick", "tape"}
    forbidden = {"ledger", "store", "clock", "set_clock", "write", "db"}
    assert not (names & forbidden)


def test_intent_rejects_float_size_lamports() -> None:
    with pytest.raises(TypeError):
        Intent(
            strategy_id="sample",
            mint="MintA",
            side="buy",
            size_lamports=1.5,  # type: ignore[arg-type]
            decision_id="d-1",
            reason="float size",
            version_id="v",
        )


def test_intent_rejects_bool_size_lamports() -> None:
    with pytest.raises(TypeError):
        Intent(
            strategy_id="sample",
            mint="MintA",
            side="buy",
            size_lamports=True,  # type: ignore[arg-type]
            decision_id="d-1",
            reason="bool size",
            version_id="v",
        )


def test_intent_rejects_unknown_side() -> None:
    with pytest.raises(ValueError):
        Intent(
            strategy_id="sample",
            mint="MintA",
            side="hold",  # type: ignore[arg-type]
            size_lamports=1,
            decision_id="d-1",
            reason="bad side",
            version_id="v",
        )


def test_intent_is_frozen() -> None:
    intent = Intent(
        strategy_id="sample",
        mint="MintA",
        side="sell",
        size_lamports=10,
        decision_id="d-2",
        reason="exit",
        version_id="v",
    )
    with pytest.raises(FrozenInstanceError):
        intent.size_lamports = 20  # type: ignore[misc]


def test_hook_gets_one_context_and_returns_one_stamped_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cls = _load_sample(tmp_path, monkeypatch, SAMPLE_BODY)
    params = dict(cls.DEFAULTS)
    vid = version_id(cls, params)
    ctx = StrategyContext(
        now=1_000.0,
        version_id=vid,
        tick=_tick(),
        tape=(TapePoint(ts=999.0, price_lamports=7),),
    )
    intents = cls().on_tick(ctx)  # type: ignore[attr-defined]
    assert len(intents) == 1
    assert intents[0].version_id == vid
    assert intents[0].mint == "MintA"
    assert intents[0].size_lamports == 1_000


def test_hook_cannot_reach_a_ledger_handle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cls = _load_sample(tmp_path, monkeypatch, SAMPLE_BODY)
    ctx = StrategyContext(now=1.0, version_id="v", tick=_tick(), tape=())
    reachable = set(vars(ctx)) | {name for name in dir(ctx) if not name.startswith("__")}
    assert reachable <= {"now", "version_id", "tick", "tape"}
    assert all(not hasattr(ctx, name) for name in ("ledger", "store", "clock"))
    assert "on_tick" in dir(cls)
    hook_params = list(_hook_parameters(cls.on_tick))
    assert hook_params == ["context"]


def _hook_parameters(func: Any) -> list[str]:
    return [p.name for p in inspect.signature(func).parameters.values() if p.name != "self"]
