#!/usr/bin/env python3
"""Подбор весов и порога по собственному логу.

Каждая запись лога хранит скоринг, разложенный по компонентам, поэтому
итог можно пересчитать с другими весами, не вызывая агентов заново. Скрипт
отвечает на два вопроса:

  * как порог меняет число кандидатов и результат по закрытым сделкам;
  * какие веса дали бы лучший результат на том же материале.

    python scripts/tune.py logs/trades.jsonl
    python scripts/tune.py logs/trades.jsonl --fine --top 20

ЧЕСТНАЯ ОГОВОРКА, которую стоит прочитать до того, как менять конфиг.
Результат считается только по сделкам, которые реально были совершены и
закрыты: чем кончился бы токен, отсеянный порогом, лог не знает и знать не
может. Поэтому таблица показывает, что порог **сохраняет или теряет** из
уже известного, а не «сколько бы вы заработали». Веса, подобранные по
двум десяткам сделок, — это подгонка под шум, а не настройка.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.log import TradeLog, read_log
from src.models import Config

COMPONENTS = ("audit", "narrative", "timing", "metrics")
THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85)

# Ниже этого числа закрытых сделок любые выводы — совпадение.
MEANINGFUL_SAMPLE = 30


class Candidate(NamedTuple):
    """Токен, доживший до скоринга, и то, чем он кончился."""

    mint: str
    parts: tuple[float, float, float, float]
    bought: bool
    pnl_sol: float | None          # None — позиция не закрывалась


def load_candidates(path: str, rotated: bool) -> list[Candidate]:
    source = TradeLog(path).read_all() if rotated else read_log(path)
    records = list(source)

    pnl: dict[str, float] = {}
    for record in records:
        if record.get("type") == "close":
            mint = record.get("mint", "")
            pnl[mint] = pnl.get(mint, 0.0) + float(record.get("pnl_sol") or 0.0)

    seen: set[str] = set()
    candidates: list[Candidate] = []
    for record in records:
        scores = record.get("scores")
        if not scores or record.get("type") == "close":
            continue
        mint = record.get("mint", "")
        if mint in seen:
            continue
        seen.add(mint)
        parts = tuple(float(scores.get(name) or 0.0) for name in COMPONENTS)
        bought = record.get("type") == "buy"
        candidates.append(
            Candidate(mint=mint, parts=parts, bought=bought,  # type: ignore[arg-type]
                      pnl_sol=pnl.get(mint) if bought else None)
        )
    return candidates


def total(parts: tuple[float, ...], weights: tuple[float, ...]) -> float:
    return sum(part * weight for part, weight in zip(parts, weights, strict=True))


class Outcome(NamedTuple):
    passed: int
    kept_trades: int
    kept_pnl: float
    lost_trades: int
    lost_pnl: float

    @property
    def score(self) -> float:
        """Чем выше, тем лучше набор: сохранённая прибыль минус упущенная."""
        return self.kept_pnl - max(0.0, self.lost_pnl)


def evaluate(
    candidates: list[Candidate], weights: tuple[float, ...], threshold: float
) -> Outcome:
    passed = kept = lost = 0
    kept_pnl = lost_pnl = 0.0
    for candidate in candidates:
        if total(candidate.parts, weights) >= threshold:
            passed += 1
            if candidate.pnl_sol is not None:
                kept += 1
                kept_pnl += candidate.pnl_sol
        elif candidate.pnl_sol is not None:
            lost += 1
            lost_pnl += candidate.pnl_sol
    return Outcome(passed, kept, round(kept_pnl, 6), lost, round(lost_pnl, 6))


def rank(row: tuple[Outcome, tuple[float, ...], float]) -> tuple[float, int, float]:
    """Ключ сортировки наборов.

    При равном результате предпочитаем тот, что оставил больше сделок и
    меньше опирается на один компонент: вес 1.00 на одной оценке — это
    почти всегда подгонка, а не находка.
    """
    outcome, weights, _ = row
    return (outcome.score, outcome.kept_trades, -max(weights))


def simplex(step: float) -> list[tuple[float, ...]]:
    """Все наборы из четырёх весов с данным шагом, дающие в сумме единицу."""
    steps = round(1.0 / step)
    grid: list[tuple[float, ...]] = []
    for a, b, c in itertools.product(range(steps + 1), repeat=3):
        d = steps - a - b - c
        if d < 0:
            continue
        grid.append(tuple(round(x * step, 4) for x in (a, b, c, d)))
    return grid


def current_weights(config_path: str | None) -> tuple[float, ...]:
    if config_path and Path(config_path).exists():
        weights = Config.load(config_path, env={}).scoring.weights.model_dump()
    else:
        weights = Config().scoring.weights.model_dump()
    raw = [max(0.0, float(weights[name])) for name in COMPONENTS]
    stotal = sum(raw) or 1.0
    return tuple(round(value / stotal, 4) for value in raw)


def fmt_weights(weights: tuple[float, ...]) -> str:
    return " ".join(f"{name[:4]}={value:.2f}" for name, value in zip(COMPONENTS, weights,
                                                                    strict=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Подбор весов и порога по логу")
    parser.add_argument("log", nargs="?", default="logs/trades.jsonl")
    parser.add_argument("--config", default="config.yaml", help="откуда взять текущие веса")
    parser.add_argument("--rotated", action="store_true", help="считать и повёрнутые копии")
    parser.add_argument("--fine", action="store_true", help="шаг сетки 0.05 вместо 0.10")
    parser.add_argument("--top", type=int, default=10, help="сколько наборов показать")
    args = parser.parse_args()

    candidates = load_candidates(args.log, args.rotated)
    if not candidates:
        print(f"В {args.log} нет записей со скорингом — подбирать не на чем.")
        return 1

    closed = [c for c in candidates if c.pnl_sol is not None]
    weights = current_weights(args.config)

    print()
    print("=" * 68)
    print(f"  ПОДБОР ПО ЛОГУ  {args.log}")
    print(f"  кандидатов со скорингом: {len(candidates)}   "
          f"закрытых сделок: {len(closed)}")
    print(f"  текущие веса: {fmt_weights(weights)}")
    print("=" * 68)

    if len(closed) < MEANINGFUL_SAMPLE:
        print(f"\n  ОСТОРОЖНО: закрытых сделок {len(closed)}, это меньше "
              f"{MEANINGFUL_SAMPLE}.\n  Любой подбор на таком материале — подгонка "
              "под шум. Смотрите\n  на таблицу как на описание того, что уже "
              "случилось, и не более.")

    # -- порог при текущих весах ------------------------------------------
    print("\nПорог при текущих весах")
    print(f"  {'порог':>6}  {'кандидатов':>10}  {'сделок':>7}  {'их PnL':>10}  "
          f"{'отсеяно':>8}  {'их PnL':>10}")
    for threshold in THRESHOLDS:
        outcome = evaluate(candidates, weights, threshold)
        print(f"  {threshold:>6.2f}  {outcome.passed:>10}  {outcome.kept_trades:>7}  "
              f"{outcome.kept_pnl:>+10.4f}  {outcome.lost_trades:>8}  "
              f"{outcome.lost_pnl:>+10.4f}")
    print("\n  «отсеяно» — сделки, которые этот порог НЕ пропустил бы;")
    print("  их PnL со знаком минус означает, что порог спас бы эти деньги.")

    if not closed:
        print("\nЗакрытых сделок нет — сравнивать наборы весов не на чем.")
        return 0

    # -- сетка весов -------------------------------------------------------
    step = 0.05 if args.fine else 0.10
    grid = simplex(step)
    print(f"\nПеребор весов: {len(grid)} наборов × {len(THRESHOLDS)} порогов")

    # Для каждого набора весов оставляем только лучший порог: иначе верх
    # таблицы занимает один и тот же набор, размноженный по всей шкале.
    best_by_weights: dict[tuple[float, ...], tuple[Outcome, tuple[float, ...], float]] = {}
    for candidate_weights in grid:
        for threshold in THRESHOLDS:
            outcome = evaluate(candidates, candidate_weights, threshold)
            if outcome.kept_trades == 0:
                continue          # набор, не оставляющий ни одной сделки, бесполезен
            row = (outcome, candidate_weights, threshold)
            current = best_by_weights.get(candidate_weights)
            if current is None or rank(row) > rank(current):
                best_by_weights[candidate_weights] = row

    results = sorted(best_by_weights.values(), key=rank, reverse=True)
    base = evaluate(candidates, weights, 0.65)

    print(f"\nЛучшие {args.top} по «сохранённая прибыль минус упущенная»")
    print(f"  {'#':>2}  {'веса':<38} {'порог':>5}  {'сделок':>6}  {'PnL':>10}")
    for index, (outcome, candidate_weights, threshold) in enumerate(results[:args.top], 1):
        print(f"  {index:>2}  {fmt_weights(candidate_weights):<38} {threshold:>5.2f}  "
              f"{outcome.kept_trades:>6}  {outcome.kept_pnl:>+10.4f}")

    print(f"\n  для сравнения, текущие веса при пороге 0.65: "
          f"{base.kept_trades} сделок, PnL {base.kept_pnl:+.4f}")
    print("\n  Ещё раз: чем кончились бы отсеянные токены, лог не знает.")
    print("  Эта таблица — про уже случившееся, а не про будущий доход.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
