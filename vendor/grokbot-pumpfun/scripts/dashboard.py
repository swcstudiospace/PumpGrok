#!/usr/bin/env python3
"""CLI-дашборд по логу: что происходит прямо сейчас.

    python scripts/dashboard.py logs/trades.jsonl
    python scripts/dashboard.py logs/trades.jsonl --watch 5   # обновлять раз в 5с
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.log import read_log

WIDTH = 62


def day_key(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


def hms(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


def rule(title: str = "") -> str:
    if not title:
        return "─" * WIDTH
    return f"── {title} " + "─" * max(0, WIDTH - len(title) - 4)


def render(path: str, tail: int) -> str:
    records = list(read_log(path))
    out: list[str] = []
    if not records:
        return f"Лог {path} пуст или не найден."

    today = day_key(time.time())
    todays = [r for r in records if day_key(r.get("ts", 0)) == today]

    buys = [r for r in records if r.get("type") == "buy"]
    closes = [r for r in records if r.get("type") == "close"]
    closed_mints = Counter(r["mint"] for r in closes)
    open_positions = [r for r in buys if closed_mints[r["mint"]] == 0]

    today_buys = [r for r in todays if r.get("type") == "buy"]
    today_skips = [r for r in todays if r.get("type") == "skip"]
    today_closes = [r for r in todays if r.get("type") == "close"]
    today_pnl = sum(r.get("pnl_sol", 0.0) for r in today_closes)
    total_pnl = sum(r.get("pnl_sol", 0.0) for r in closes)
    modes = Counter(r.get("mode", "?") for r in records[-50:])
    mode = modes.most_common(1)[0][0] if modes else "?"

    out.append(rule(f"grokbot-pumpfun · {mode}"))
    out.append(f"сегодня ({today} UTC): куплено {len(today_buys)}   "
               f"пропущено {len(today_skips)}   закрыто {len(today_closes)}")
    out.append(f"PnL сегодня: {today_pnl:+.4f} SOL      всего: {total_pnl:+.4f} SOL")

    out.append(rule(f"открытые позиции: {len(open_positions)}"))
    if open_positions:
        for record in open_positions[-10:]:
            age = (time.time() - record.get("ts", 0)) / 60
            score = (record.get("scores") or {}).get("total", 0.0)
            out.append(
                f"  {(record.get('symbol') or record['mint'])[:12]:<12} "
                f"{record.get('size_sol', 0):.4f} SOL  score {score:.3f}  "
                f"{age:6.1f} мин  {record.get('tx_hash', '')[:16]}"
            )
    else:
        out.append("  нет")

    if today_skips:
        out.append(rule("отсев сегодня"))
        reasons = Counter(r.get("reason", "?") for r in today_skips)
        for reason, count in reasons.most_common(6):
            out.append(f"  {reason[:30]:<30} {count:>5}")

    out.append(rule(f"последние события ({tail})"))
    for record in records[-tail:]:
        out.append("  " + format_event(record))
    out.append(rule())
    return "\n".join(out)


def format_event(record: dict) -> str:
    ts = hms(record.get("ts", 0))
    kind = record.get("type", "?")
    label = record.get("symbol") or record.get("mint", "?")[:10]
    if kind == "buy":
        score = (record.get("scores") or {}).get("total", 0.0)
        return f"{ts}  BUY   {label:<12} {record.get('size_sol', 0):.4f} SOL  score {score:.3f}"
    if kind == "close":
        return (f"{ts}  CLOSE {label:<12} {record.get('pnl_sol', 0):+.4f} SOL "
                f"({record.get('pnl_pct', 0):+.1f}%)  {record.get('reason', '')}")
    if kind == "skip":
        return f"{ts}  skip  {label:<12} [{record.get('stage', '?')}] {record.get('reason', '')}"
    return f"{ts}  {kind}"


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI-дашборд по логу пайплайна")
    parser.add_argument("log", nargs="?", default="logs/trades.jsonl")
    parser.add_argument("--tail", type=int, default=12, help="сколько последних событий показать")
    parser.add_argument("--watch", type=float, default=0.0, help="обновлять раз в N секунд")
    args = parser.parse_args()

    if not args.watch:
        print(render(args.log, args.tail))
        return 0

    try:
        while True:
            print("\033[2J\033[H" + render(args.log, args.tail), flush=True)
            time.sleep(args.watch)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
