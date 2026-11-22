# Datafeed runbook (v4)

Read the datafeed health from the doctor and the health file; never adjust the clock.

```bash
uv run pumpgrok doctor
```

Source states (`live`, `stale`, `resyncing`, `disconnected`) appear as `source <name> status=<state>`. A source that has never framed is not stale; resync holds until the next good frame. Data age is also exposed as the `pumpgrok_data_age_seconds{source}` metric.

```bash
uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
```

Stale-source alerts fire from `docs/observability/alerts.yaml` (`pumpgrok_data_age_seconds > 300`).
