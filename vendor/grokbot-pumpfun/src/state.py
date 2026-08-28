"""Состояние, которое обязано пережить рестарт.

Процесс, торгующий сутками, будет перезапущен: деплой, OOM, ребут хоста.
Если после рестарта он забудет открытые позиции и счётчики дня, то купит
то же самое второй раз и превысит дневной лимит убытка — оба лимита
считаются от нуля.

Файл пишется атомарно: сначала во временный, потом os.replace. Так на
диске никогда не лежит наполовину записанный JSON, даже если процесс
убили в момент сохранения.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .models import Position

log = logging.getLogger(__name__)

STATE_VERSION = 1


class PipelineState(BaseModel):
    """Снимок всего, что нельзя потерять."""

    version: int = STATE_VERSION
    day: str = ""                                   # сутки UTC, к которым относятся счётчики
    trades_today: int = 0
    realized_pnl_sol: float = 0.0
    grok_calls_today: int = 0
    positions: dict[str, Position] = Field(default_factory=dict)
    updated_at: float = 0.0

    @property
    def is_empty(self) -> bool:
        return not self.positions and not self.trades_today and not self.realized_pnl_sol


class StateStore:
    """Атомарное чтение и запись состояния в один JSON-файл."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> PipelineState | None:
        """Прочитать состояние. None, если файла нет или он испорчен."""
        if not self.path.exists():
            return None
        try:
            raw: Any = json.loads(self.path.read_text(encoding="utf-8"))
            state = PipelineState.model_validate(raw)
        except Exception as exc:
            backup = self.path.with_suffix(self.path.suffix + ".corrupt")
            log.error(
                "состояние %s не читается (%s) — отложено в %s, стартуем с чистого",
                self.path, exc, backup,
            )
            with contextlib.suppress(OSError):
                os.replace(self.path, backup)
            return None

        if state.version != STATE_VERSION:
            log.warning("состояние версии %d, ожидалась %d — счётчики дня сброшены",
                        state.version, STATE_VERSION)
        return state

    def save(self, state: PipelineState) -> None:
        """Записать состояние атомарно. Сбой записи не роняет торговлю."""
        state.updated_at = time.time()
        tmp = self.path.with_suffix(self.path.suffix + f".tmp{os.getpid()}")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(state.model_dump(mode="json"), fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except OSError as exc:
            log.error("не удалось сохранить состояние в %s: %s", self.path, exc)
            tmp.unlink(missing_ok=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def describe(state: PipelineState) -> str:
    """Строка для стартового лога."""
    age = max(0.0, time.time() - state.updated_at) / 60 if state.updated_at else 0.0
    return (
        f"день {state.day or '?'}, сделок {state.trades_today}, "
        f"PnL {state.realized_pnl_sol:+.4f} SOL, "
        f"открытых позиций {len(state.positions)}, "
        f"вызовов Grok {state.grok_calls_today}, "
        f"записано {age:.0f} мин назад"
    )
