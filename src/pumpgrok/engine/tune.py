"""Weight and threshold grid search over a closed-trades log.

Port of the retired oracle ``scripts/tune.py``. The math (``total``,
``evaluate``, ``rank``, ``simplex``) is 1:1; the surroundings change: the
vendor reads its own ``TradeLog`` rotation, while this module reads plain
JSONL trade records, so the unported ``TradeLog`` stays out of the picture.
Weights come from ``ScoringSettings`` (normalized, so any scale works) and
there is no ``--config``/``--rotated`` pair to keep in sync.

Output goes through ``sys.stdout.write`` (ruff T20), and the branchy vendor
``main`` is split into line builders so no function trips the PL
complexity rules. Every signature is typed for mypy strict.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, NamedTuple

from pumpgrok.config.settings import ConfigError, ScoringWeights, load_settings

COMPONENTS = ("audit", "narrative", "timing", "metrics")
THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85)

#: Fewer closed trades than this and any ranking is noise, not signal.
MEANINGFUL_SAMPLE = 30


class Candidate(NamedTuple):
    """One token that survived to scoring, and how it ended."""

    mint: str
    parts: tuple[float, ...]
    bought: bool
    pnl_lamports: int | None


class Outcome(NamedTuple):
    """What one (weights, threshold) pair would have done."""

    passed: int
    kept_trades: int
    kept_pnl: int
    lost_trades: int
    lost_pnl: int

    @property
    def score(self) -> int:
        """Higher is better: kept profit minus missed profit, in lamports."""
        return self.kept_pnl - max(0, self.lost_pnl)


def total(parts: tuple[float, ...], weights: tuple[float, ...]) -> float:
    """Weighted component sum. Parts and weights line up by position."""
    return sum(part * weight for part, weight in zip(parts, weights, strict=True))


def evaluate(
    candidates: Sequence[Candidate], weights: tuple[float, ...], threshold: float
) -> Outcome:
    """Split candidates into kept and missed at one threshold."""
    passed = kept = lost = 0
    kept_pnl = lost_pnl = 0
    for candidate in candidates:
        if total(candidate.parts, weights) >= threshold:
            passed += 1
            if candidate.pnl_lamports is not None:
                kept += 1
                kept_pnl += candidate.pnl_lamports
        elif candidate.pnl_lamports is not None:
            lost += 1
            lost_pnl += candidate.pnl_lamports
    return Outcome(passed, kept, kept_pnl, lost, lost_pnl)


def rank(row: tuple[Outcome, tuple[float, ...], float]) -> tuple[int, int, float]:
    """Sort key for (outcome, weights, threshold) rows.

    Ties break toward more kept trades, then away from single-component
    bets: 1.00 on one score is usually overfit, not insight.
    """
    outcome, weights, _ = row
    return (outcome.score, outcome.kept_trades, -max(weights))


def simplex(step: float) -> list[tuple[float, ...]]:
    """Every four-weight mix at the given step that sums to one."""
    steps = round(1.0 / step)
    grid: list[tuple[float, ...]] = []
    for a, b, c in itertools.product(range(steps + 1), repeat=3):
        rest = steps - a - b - c
        if rest < 0:
            continue
        grid.append(tuple(round(value * step, 4) for value in (a, b, c, rest)))
    return grid


def current_weights(weights: ScoringWeights) -> tuple[float, ...]:
    """Normalize scoring weights to a unit-sum mix in component order."""
    raw = [max(0.0, float(getattr(weights, name))) for name in COMPONENTS]
    subtotal = sum(raw) or 1.0
    return tuple(round(value / subtotal, 4) for value in raw)


def fmt_weights(weights: tuple[float, ...]) -> str:
    """Compact mix rendering, e.g. ``audi=0.30 narr=0.25``."""
    return " ".join(
        f"{name[:4]}={value:.2f}" for name, value in zip(COMPONENTS, weights, strict=True)
    )


def _pnl_to_lamports(value: Any) -> int:
    """Trades-log PnL (SOL float or exact decimal string) to integer lamports (INT-01)."""
    if value is None:
        return 0
    try:
        scaled = Decimal(str(value)) * (10**9)
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ValueError(f"bad pnl {value!r}") from exc
    return int(scaled.to_integral_value(rounding=ROUND_HALF_UP))


def collect_pnl(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Sum closed-trade PnL per mint, in integer lamports."""
    pnl: dict[str, int] = {}
    for record in records:
        if record.get("type") == "close":
            mint = str(record.get("mint", ""))
            pnl[mint] = pnl.get(mint, 0) + _pnl_to_lamports(record.get("pnl_sol"))
    return pnl


def candidate_from_record(
    record: Mapping[str, Any], pnl: Mapping[str, int], seen: set[str]
) -> Candidate | None:
    """One candidate from a scored record. None for closes and scoreless rows."""
    scores = record.get("scores")
    if not scores or record.get("type") == "close":
        return None
    mint = str(record.get("mint", ""))
    if mint in seen:
        return None
    seen.add(mint)
    parts = tuple(float(scores.get(name) or 0.0) for name in COMPONENTS)
    bought = record.get("type") == "buy"
    realized = pnl.get(mint) if bought else None
    return Candidate(mint=mint, parts=parts, bought=bought, pnl_lamports=realized)


def load_candidates(records: Iterable[Mapping[str, Any]]) -> list[Candidate]:
    """First scored sighting per mint, with close PnL attached to buys."""
    materialized = list(records)
    pnl = collect_pnl(materialized)
    seen: set[str] = set()
    candidates: list[Candidate] = []
    for record in materialized:
        candidate = candidate_from_record(record, pnl, seen)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def load_candidates_from_path(path: Path) -> list[Candidate]:
    """Parse a JSONL trades log. Blank lines are skipped; anything else strict."""
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number}: not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{path}:{number}: line is not a JSON object")
        records.append(parsed)
    return load_candidates(records)


def header_lines(
    log: str,
    candidates: Sequence[Candidate],
    closed: Sequence[Candidate],
    weights: tuple[float, ...],
) -> list[str]:
    """Report banner: what was read and which weights are current."""
    return [
        "",
        "=" * 68,
        f"  WEIGHT TUNING  {log}",
        f"  scored candidates: {len(candidates)}   closed trades: {len(closed)}",
        f"  current weights: {fmt_weights(weights)}",
        "=" * 68,
    ]


def caution_lines(closed: Sequence[Candidate]) -> list[str]:
    """Small-sample warning, or nothing when the sample is meaningful."""
    if len(closed) >= MEANINGFUL_SAMPLE:
        return []
    return [
        "",
        f"  CAUTION: {len(closed)} closed trades is below {MEANINGFUL_SAMPLE}.",
        "  Any ranking on this little data is noise, not signal: read the",
        "  table as what already happened, nothing more.",
    ]


def threshold_lines(candidates: Sequence[Candidate], weights: tuple[float, ...]) -> list[str]:
    """One row per threshold at the current weights."""
    lines = [
        "",
        "Threshold sweep at current weights",
        f"  {'cutoff':>6}  {'passed':>10}  {'kept':>7}  {'kept PnL':>10}  "
        f"{'missed':>8}  {'missed PnL':>10}",
    ]
    for threshold in THRESHOLDS:
        outcome = evaluate(candidates, weights, threshold)
        lines.append(
            f"  {threshold:>6.2f}  {outcome.passed:>10}  {outcome.kept_trades:>7}  "
            f"{outcome.kept_pnl:>+10.4f}  {outcome.lost_trades:>8}  "
            f"{outcome.lost_pnl:>+10.4f}"
        )
    lines += [
        "",
        "  'missed' are trades this cutoff would NOT have taken;",
        "  negative missed PnL means the cutoff would have saved that money.",
    ]
    return lines


def grid_lines(
    candidates: Sequence[Candidate], weights: tuple[float, ...], step: float, top: int
) -> list[str]:
    """Best threshold per weight mix, ranked, top N shown."""
    grid = simplex(step)
    lines = [f"\nWeight search: {len(grid)} mixes x {len(THRESHOLDS)} cutoffs"]
    best_by_weights: dict[tuple[float, ...], tuple[Outcome, tuple[float, ...], float]] = {}
    for candidate_weights in grid:
        for threshold in THRESHOLDS:
            outcome = evaluate(candidates, candidate_weights, threshold)
            if outcome.kept_trades == 0:
                continue
            row = (outcome, candidate_weights, threshold)
            current = best_by_weights.get(candidate_weights)
            if current is None or rank(row) > rank(current):
                best_by_weights[candidate_weights] = row
    results = sorted(best_by_weights.values(), key=rank, reverse=True)
    base = evaluate(candidates, weights, 0.65)
    lines.append("\nBest mixes by kept profit minus missed profit")
    lines.append(f"  {'#':>2}  {'weights':<38} {'cutoff':>5}  {'kept':>6}  {'PnL':>10}")
    for index, (outcome, candidate_weights, threshold) in enumerate(results[:top], 1):
        lines.append(
            f"  {index:>2}  {fmt_weights(candidate_weights):<38} {threshold:>5.2f}  "
            f"{outcome.kept_trades:>6}  {outcome.kept_pnl:>+10.4f}"
        )
    lines += [
        "",
        f"  for reference, current weights at 0.65: "
        f"{base.kept_trades} trades, PnL {base.kept_pnl:+.4f}",
        "",
        "  Missed tokens never report back. This table is about what",
        "  already happened, not about future income.",
        "",
    ]
    return lines


def run_report(log: str, step: float, top: int, weights: ScoringWeights) -> tuple[list[str], int]:
    """Build every output line plus the exit code."""
    candidates = load_candidates_from_path(Path(log))
    if not candidates:
        return [f"No scored records in {log}; nothing to tune."], 1
    closed = [candidate for candidate in candidates if candidate.pnl_lamports is not None]
    mix = current_weights(weights)
    lines = header_lines(log, candidates, closed, mix)
    lines += caution_lines(closed)
    lines += threshold_lines(candidates, mix)
    if not closed:
        lines.append("")
        lines.append("No closed trades; nothing to compare weight mixes on.")
        return lines, 0
    lines += grid_lines(candidates, mix, step, top)
    return lines, 0


def build_parser() -> argparse.ArgumentParser:
    """CLI surface: log path plus grid density and row count."""
    parser = argparse.ArgumentParser(description="Tune scoring weights and cutoff")
    parser.add_argument("log", nargs="?", default="logs/trades.jsonl")
    parser.add_argument("--fine", action="store_true", help="0.05 grid step instead of 0.10")
    parser.add_argument("--top", type=int, default=10, help="how many mixes to show")
    return parser


def _current_weights() -> ScoringWeights:
    """Operator-configured weights, or factory defaults when unset/unreadable."""
    try:
        return load_settings().scoring.weights
    except ConfigError:
        return ScoringWeights()


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Writes the report to stdout, returns the exit code."""
    args = build_parser().parse_args(argv)
    lines, code = run_report(args.log, 0.05 if args.fine else 0.10, args.top, _current_weights())
    for line in lines:
        sys.stdout.write(line + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
