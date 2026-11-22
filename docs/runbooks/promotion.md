# Promotion runbook (v4)

Strategy stages come from the promotion surface and are reported read-only by the doctor.

```bash
uv run pumpgrok doctor
```

Stages (`BACKTEST`, `PAPER`, `LIVE_ELIGIBLE`) appear as `stage <strategy> stage=<stage>`. Demote a strategy one stage with the promotion verb.

```bash
uv run pumpgrok promotion demote --strategy momentum_breakout --by human:operator
```

`LIVE` is derived from `LIVE_ELIGIBLE` plus the arm record and is never stored. Non-writer callers raise instead of writing.
