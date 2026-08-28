"""Память о создателях токенов.

Пайплайн разбирает каждый лонч с чистого листа, поэтому один и тот же
деплойер может слить нас трижды подряд — и каждый раз он будет «новым».
Аудитор его тоже не узнает: он видит один токен, а не историю адреса.

Книга репутации закрывает это дёшево и без LLM: адрес, чей токен уже
закрылся глубоким минусом, отсекается на входе, до единого запроса к
Grok. Решение принимается только по собственным закрытым сделкам — это не
чёрный список из интернета и не эвристика, а факт из своего же лога.
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

log = logging.getLogger(__name__)

# Сколько адресов помним. Дальше вытесняем самые старые.
MAX_CREATORS = 50_000


class CreatorRecord(BaseModel):
    """Что мы знаем об адресе по своим же сделкам."""

    creator: str
    tokens_seen: int = 0
    tokens_bought: int = 0
    closed: int = 0
    rugs: int = 0
    realized_pnl_sol: float = 0.0
    worst_pnl_pct: float = 0.0
    last_seen: float = 0.0

    @property
    def is_known_bad(self) -> bool:
        return self.rugs > 0


class ReputationBook(BaseModel):
    """Файл с историей адресов. Читается на старте, пишется после закрытий."""

    version: int = 1
    creators: dict[str, CreatorRecord] = Field(default_factory=dict)
    updated_at: float = 0.0

    # -- диск --------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> ReputationBook:
        file = Path(path)
        if not file.exists():
            return cls()
        try:
            raw: Any = json.loads(file.read_text(encoding="utf-8"))
            return cls.model_validate(raw)
        except Exception as exc:
            log.error("книга репутации %s не читается (%s) — начинаем с пустой", file, exc)
            return cls()

    def save(self, path: str | Path) -> None:
        """Атомарно, как и состояние: половина файла хуже, чем его отсутствие."""
        file = Path(path)
        self.updated_at = time.time()
        tmp = file.with_suffix(file.suffix + f".tmp{os.getpid()}")
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self.model_dump(mode="json"), fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, file)
        except OSError as exc:
            log.error("не удалось сохранить книгу репутации: %s", exc)
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)

    # -- учёт --------------------------------------------------------------

    def _record(self, creator: str) -> CreatorRecord:
        record = self.creators.get(creator)
        if record is None:
            record = CreatorRecord(creator=creator)
            self.creators[creator] = record
            self._evict_if_crowded()
        record.last_seen = time.time()
        return record

    def observe(self, creator: str | None) -> None:
        if creator:
            self._record(creator).tokens_seen += 1

    def record_open(self, creator: str | None) -> None:
        if creator:
            self._record(creator).tokens_bought += 1

    def record_close(
        self,
        creator: str | None,
        *,
        pnl_sol: float,
        pnl_pct: float,
        rug_loss_pct: float,
    ) -> CreatorRecord | None:
        """Закрытие позиции. Глубокий минус засчитывается адресу как слив."""
        if not creator:
            return None
        record = self._record(creator)
        record.closed += 1
        record.realized_pnl_sol += pnl_sol
        record.worst_pnl_pct = min(record.worst_pnl_pct, pnl_pct)
        if rug_loss_pct and -pnl_pct >= rug_loss_pct:
            record.rugs += 1
            log.warning("создатель %s: слив %d, худший результат %.1f%% — "
                        "его следующие токены отсекаются на входе",
                        creator[:8], record.rugs, record.worst_pnl_pct)
        return record

    # -- решение -----------------------------------------------------------

    def verdict(self, creator: str | None, block_after_rugs: int) -> str | None:
        """Причина не связываться с этим адресом, или None."""
        if not creator or block_after_rugs <= 0:
            return None
        record = self.creators.get(creator)
        if record is None:
            return None
        if record.rugs >= block_after_rugs:
            return (f"создатель уже сливал {record.rugs} раз "
                    f"(худшее {record.worst_pnl_pct:.0f}%)")
        return None

    # -- обслуживание ------------------------------------------------------

    def forget_older_than(self, days: float, now: float | None = None) -> int:
        """Забыть адреса, о которых давно ничего не слышно. Сливы не забываем."""
        if days <= 0:
            return 0
        cutoff = (now or time.time()) - days * 86_400
        stale = [
            key for key, record in self.creators.items()
            if record.last_seen < cutoff and not record.is_known_bad
        ]
        for key in stale:
            del self.creators[key]
        return len(stale)

    def _evict_if_crowded(self) -> None:
        """Вытеснять начинаем с чистых адресов: сливы — ценность этой книги."""
        if len(self.creators) <= MAX_CREATORS:
            return
        order = sorted(
            self.creators.items(),
            key=lambda item: (item[1].is_known_bad, item[1].last_seen),
        )
        for key, _ in order:
            if len(self.creators) <= MAX_CREATORS:
                break
            del self.creators[key]

    def summary(self) -> str:
        bad = sum(1 for r in self.creators.values() if r.is_known_bad)
        return f"адресов {len(self.creators)}, из них со сливами {bad}"
