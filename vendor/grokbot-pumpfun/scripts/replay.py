#!/usr/bin/env python3
"""Реплей лога: что пайплайн купил, что пропустил и с каким итогом.

    python scripts/replay.py logs/trades.jsonl
    python scripts/replay.py logs/trades.jsonl --since 2026-08-26
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.log import TradeLog, read_log

BUCKETS = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]


def parse_since(value: str | None) -> float:
    if not value:
        return 0.0
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()


def bucket_of(score: float) -> str:
    for low, high in BUCKETS:
        if low <= score < high:
            return f"{low:.1f}-{min(high, 1.0):.1f}"
    return "?"


def bar(count: int, total: int, width: int = 28) -> str:
    if not total:
        return ""
    return "█" * max(1, round(count / total * width)) if count else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Сводка по логу пайплайна")
    parser.add_argument("log", nargs="?", default="logs/trades.jsonl")
    parser.add_argument("--since", help="YYYY-MM-DD, только записи с этой даты")
    parser.add_argument("--rotated", action="store_true",
                        help="считать вместе с повёрнутыми копиями (.1, .2, ...)")
    args = parser.parse_args()

    since = parse_since(args.since)
    source = TradeLog(args.log).read_all() if args.rotated else read_log(args.log)
    records = [r for r in source if r.get("ts", 0) >= since]
    if not records:
        print(f"В {args.log} нет записей" + (f" с {args.since}" if args.since else ""))
        return 1

    buys = [r for r in records if r.get("type") == "buy"]
    skips = [r for r in records if r.get("type") == "skip"]
    closes = [r for r in records if r.get("type") == "close"]

    span_start = min(r.get("ts", 0) for r in records)
    span_end = max(r.get("ts", 0) for r in records)

    print()
    print("=" * 62)
    print(f"  РЕПЛЕЙ  {args.log}")
    print(f"  период: {fmt_ts(span_start)} — {fmt_ts(span_end)}")
    modes = Counter(r.get("mode", "?") for r in records)
    print(f"  режим:  {', '.join(f'{m} ({n})' for m, n in modes.most_common())}")
    print("=" * 62)

    seen = len(buys) + len(skips)
    print(f"\nТокенов рассмотрено: {seen}")
    print(f"  куплено:   {len(buys)}")
    print(f"  пропущено: {len(skips)}")
    if seen:
        print(f"  конверсия: {len(buys) / seen * 100:.2f}%")

    # -- почему отсеивали --------------------------------------------------
    if skips:
        print("\nПричины пропуска")
        by_stage: dict[str, Counter] = defaultdict(Counter)
        for record in skips:
            by_stage[record.get("stage", "?")][record.get("reason", "?")] += 1
        for stage in sorted(by_stage, key=lambda s: -sum(by_stage[s].values())):
            stage_total = sum(by_stage[stage].values())
            print(f"  [{stage}]  {stage_total}")
            for reason, count in by_stage[stage].most_common():
                print(f"      {reason[:28]:<28} {count:>5}  {bar(count, len(skips))}")

    # -- скоринг -----------------------------------------------------------
    scored = [r for r in records if (r.get("scores") or {}).get("total") is not None]
    if scored:
        print("\nРаспределение итогового скоринга")
        hist = Counter(bucket_of(r["scores"]["total"]) for r in scored)
        for low, high in BUCKETS:
            label = f"{low:.1f}-{min(high, 1.0):.1f}"
            count = hist.get(label, 0)
            print(f"  {label:<10} {count:>5}  {bar(count, len(scored))}")
        components = ("audit", "narrative", "timing", "metrics")
        print("\n  средние по компонентам:")
        for name in components:
            values = [r["scores"].get(name, 0.0) for r in scored]
            print(f"    {name:<10} {sum(values) / len(values):.3f}")

    # -- деньги ------------------------------------------------------------
    if closes:
        pnl = sum(r.get("pnl_sol", 0.0) for r in closes)
        wins = [r for r in closes if r.get("pnl_sol", 0.0) > 0]
        losses = [r for r in closes if r.get("pnl_sol", 0.0) <= 0]
        holds = [r.get("hold_seconds", 0.0) for r in closes]
        print("\nЗакрытые позиции")
        print(f"  закрыто:      {len(closes)}")
        print(f"  прибыльных:   {len(wins)}  ({len(wins) / len(closes) * 100:.1f}%)")
        print(f"  убыточных:    {len(losses)}")
        print(f"  суммарный PnL: {pnl:+.4f} SOL")
        if wins:
            print(f"  лучшая:       {max(r['pnl_sol'] for r in wins):+.4f} SOL")
        if losses:
            print(f"  худшая:       {min(r['pnl_sol'] for r in losses):+.4f} SOL")
        print(f"  среднее удержание: {sum(holds) / len(holds) / 60:.1f} мин")

        print("\n  Чем кончаются позиции")
        print(f"    {'правило':<16} {'сделок':>6} {'PnL':>10} {'средний %':>10} {'держали':>9}")
        by_reason: dict[str, list[dict]] = defaultdict(list)
        for record in closes:
            by_reason[record.get("reason", "?")].append(record)
        for reason in sorted(by_reason, key=lambda r: -len(by_reason[r])):
            group = by_reason[reason]
            pnl_sum = sum(r.get("pnl_sol", 0.0) for r in group)
            pct = sum(r.get("pnl_pct", 0.0) for r in group) / len(group)
            hold = sum(r.get("hold_seconds", 0.0) for r in group) / len(group) / 60
            print(f"    {reason:<16} {len(group):>6} {pnl_sum:>+10.4f} "
                  f"{pct:>+10.1f} {hold:>7.0f}м")

        # -- создатели -----------------------------------------------------
        by_creator: dict[str, list[dict]] = defaultdict(list)
        for record in closes:
            creator = record.get("creator")
            if creator:
                by_creator[creator].append(record)
        repeats = {c: rows for c, rows in by_creator.items() if len(rows) > 1}
        if repeats:
            print("\n  Создатели, чьи токены брали не по одному разу")
            for creator, rows in sorted(repeats.items(), key=lambda kv: -len(kv[1]))[:5]:
                pnl_sum = sum(r.get("pnl_sol", 0.0) for r in rows)
                worst = min(r.get("pnl_pct", 0.0) for r in rows)
                print(f"    {creator[:12]:<14} сделок {len(rows):>2}  "
                      f"PnL {pnl_sum:>+8.4f}  худшая {worst:>+7.1f}%")
    elif buys:
        print("\nЗакрытых позиций нет — все покупки ещё в рынке.")

    open_mints = {r["mint"] for r in buys} - {r["mint"] for r in closes}
    if open_mints:
        print(f"\nОткрыто сейчас: {len(open_mints)} — {', '.join(sorted(open_mints)[:5])}")
    print()
    return 0


def fmt_ts(ts: float) -> str:
    if not ts:
        return "?"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


if __name__ == "__main__":
    raise SystemExit(main())
