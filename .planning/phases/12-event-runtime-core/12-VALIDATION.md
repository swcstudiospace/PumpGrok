---
phase: "12"
slug: "event-runtime-core"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-08"
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest, asyncio_mode auto, loop scope function |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest -q tests/events tests/config/test_v4_settings_skeleton.py tests/config/test_events_settings.py tests/config/test_live_settings_caps.py tests/cli/test_events_cli.py tests/degradation/test_event_source_faults.py tests/replay/test_event_drain_parity.py tests/safety/test_events_not_wired.py` |
| **Full suite command** | `make test` |
| **Estimated runtime** | 120 seconds |

---

## Sampling Rate

- **After every task commit:** Run the quick command for the files that task added
- **After every plan wave:** Run the quick command above
- **Before `/gsd:verify-work`:** `make test` must be green, plus the phase hash and live-refusal checks
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01 | 01 | 1 | PRC-11 | T-12-01 | New sections default off; cap above 1 SOL refuses; no secret echo | unit | `uv run pytest -q tests/config/test_v4_settings_skeleton.py tests/config/test_events_settings.py tests/config/test_live_settings_caps.py` | no | pending |
| 12-02 | 02 | 2 | EVT-01 | T-12-02 | One EventKind; integer money; derived ids | unit | `uv run pytest -q tests/events/test_models.py tests/events/test_models_v4_kinds.py` | no | pending |
| 12-03 | 03 | 3 | EVT-02 EVT-03 EVT-04 | T-12-03 | P0 never dropped; P1 to sidecar DLQ; no ledger open | unit | `uv run pytest -q tests/events/test_bus_lanes.py tests/events/test_bus_backpressure.py tests/events/test_bus_dedup_coalesce.py` | no | pending |
| 12-04 | 04 | 4 | EVT-05 EVT-06 EVT-07 EVT-09 | T-12-04 | Idempotent delivery; recover once; corrupt cursor starts clean | unit | `uv run pytest -q tests/events/test_bus_retry_dlq.py tests/cli/test_events_cli.py tests/events/test_handler_idempotency.py tests/events/test_bus_shutdown.py tests/events/test_sources.py tests/degradation/test_event_source_faults.py` | no | pending |
| 12-05 | 05 | 5 | EVT-08 EVT-14 | T-12-05 | Drain bytes match; bus not imported by verify; live stays exit 3 | unit | `uv run pytest -q tests/replay/test_event_drain_parity.py tests/safety/test_events_not_wired.py` | no | pending |

---

## Wave 0 Requirements

- [ ] `tests/config/test_v4_settings_skeleton.py` — PRC-11
- [ ] `tests/config/test_events_settings.py` — events section defaults
- [ ] `tests/config/test_live_settings_caps.py` — cap refuse without editing LiveSettings
- [ ] `tests/events/` — bus, models, sources, shutdown
- [ ] `tests/cli/test_events_cli.py` — dlq list, replay, purge
- [ ] `tests/degradation/test_event_source_faults.py` — FaultyEventSource
- [ ] `tests/replay/test_event_drain_parity.py` — determinism and trading-smoke parity, zero skips
- [ ] `tests/safety/test_events_not_wired.py` — no import from supervisor, execution, engine, or replay runner

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
