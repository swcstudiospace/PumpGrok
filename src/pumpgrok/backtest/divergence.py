"""Paper divergence check on the D7 defaults (PAP-02; CONTEXT D-12).

Compares the backtest window and the paper window over the same window and
reports whether the pair blocks promotion. Authority for the defaults is
`.planning/PROJECT.md` V3-4 (owner approval 2026-10-25): a 2 percentage
point absolute return gap or a 0.5 Sharpe gap alerts and blocks.

Both inputs are `MetricsReport` summaries of one window. The caller passes
summaries of the same window; fill-level window equality is enforced by
`SharedResult.compare` before summarizing. Money stays integer base units
upstream; the gaps here are ratios, never money. No wall clock, no network,
no forward-looking language.
"""

from __future__ import annotations

from dataclasses import dataclass

from pumpgrok.backtest.metrics import MetricsReport

__all__ = [
    "ABSOLUTE_RETURN_GAP_PP",
    "SHARPE_GAP",
    "DivergenceVerdict",
    "breach_line",
    "check",
    "enforce",
]

#: Absolute return gap that alerts and blocks, in percentage points.
#: Authority: `.planning/PROJECT.md` V3-4 (D7 divergence defaults).
ABSOLUTE_RETURN_GAP_PP = 2.0
#: Sharpe-style ratio gap that alerts and blocks. Authority: PROJECT.md V3-4.
SHARPE_GAP = 0.5


@dataclass(frozen=True)
class DivergenceVerdict:
    """Outcome of one backtest-versus-paper window comparison.

    blocks_promotion is true when either D7 default trips. return_gap_pp
    is the absolute total-return gap in percentage points. sharpe_gap is
    the absolute Sharpe-style ratio gap. reasons names every tripped
    threshold, oldest first; empty when clean.
    """

    blocks_promotion: bool
    return_gap_pp: float
    sharpe_gap: float
    reasons: tuple[str, ...] = ()


def check(backtest: MetricsReport, paper: MetricsReport) -> DivergenceVerdict:
    """Compare same-window backtest and paper summaries (PAP-02).

    Gaps at or past a D7 default alert and block promotion. Both inputs
    must summarize the same window; this function trusts the caller on
    window identity the way `summarize` trusts its context curve.
    """
    return_gap_pp = abs(float(backtest.total_return - paper.total_return)) * 100.0
    sharpe_gap = abs(float(backtest.sharpe_ratio - paper.sharpe_ratio))
    reasons: list[str] = []
    if return_gap_pp >= ABSOLUTE_RETURN_GAP_PP:
        reasons.append(
            f"return_gap_pp={return_gap_pp:.4f} at-or-past {ABSOLUTE_RETURN_GAP_PP:.1f}pp"
        )
    if sharpe_gap >= SHARPE_GAP:
        reasons.append(f"sharpe_gap={sharpe_gap:.4f} at-or-past {SHARPE_GAP:.1f}")
    return DivergenceVerdict(
        blocks_promotion=bool(reasons),
        return_gap_pp=return_gap_pp,
        sharpe_gap=sharpe_gap,
        reasons=tuple(reasons),
    )


def breach_line(verdict: DivergenceVerdict) -> str | None:
    """G-08 stderr text for a blocking verdict, else None.

    The line starts with DIVERGENCE BREACH and carries fixed four-decimal
    gaps plus the tripped reasons, so identical verdicts print identically.
    """
    if not verdict.blocks_promotion:
        return None
    return (
        f"DIVERGENCE BREACH return_gap_pp={verdict.return_gap_pp:.4f} "
        f"sharpe_gap={verdict.sharpe_gap:.4f} "
        f"reasons={'|'.join(verdict.reasons)}"
    )


def enforce(verdict: DivergenceVerdict) -> int:
    """G-08 exit code for a verdict: 1 when blocked, else 0.

    The promotion-gate caller prints `breach_line` to stderr when this
    returns 1 and records the report with promotion ineligible. Exit 1 is
    the existing generic failure code; no new exit code is approved.
    """
    return 1 if verdict.blocks_promotion else 0
