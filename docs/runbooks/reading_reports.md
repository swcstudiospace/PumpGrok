# Reading reports runbook

Emitting and reading desk reports. Reports render from the ledger, so they describe what actually happened, not what the engine hoped would happen.

## Quick start

```bash
pumpgrok report --daily
pumpgrok report --weekly
pumpgrok report --daily --day 2026-10-21
pumpgrok report --daily --out var/report-daily.md
```

The first two commands print the daily and weekly rollups to stdout. `--day` and `--week` pin an explicit period instead of the default. `--out` writes the same markdown to a file as well.

## What reports contain

- Daily rollup: fills, fees, realized and unrealized PnL in SOL, per-seat activity, error and stale-data counts, and the current breaker and kill-switch posture.
- Weekly rollup: the same figures aggregated Monday to Sunday, plus week-over-week deltas.
- Every figure traces to ledger events. A number that cannot be traced is reported as unavailable, never interpolated.

## Rules that apply to reports

- Read reports from the ledger-backed render only. Engine stdout and chat summaries are not the record.
- Pin `--day` or `--week` when comparing across days; the bare default always means today or this week.
- Treat cost lines (RPC usage, model spend) as first-class signals during the unattended paper run. A cost spike is an incident, not bookkeeping.
- Never hand-edit a written report file. Re-render with `--out` after the underlying ledger changes.

## References

- Report rendering: `src/pumpgrok/reporting/`
- Ledger verification: `pumpgrok verify --fixture smoke`
- Engine cycle: `docs/runbooks/engine.md`
