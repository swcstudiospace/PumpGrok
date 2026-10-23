---
phase: 02-restructure
plan: "01"
subsystem: tools-onchain-market
tags: [tenacity, rpc-failover, characterization, struct-002, tracer]
requires: []
provides: [rpc-client, ported-tools, tool-fixtures, tool-ownership]
affects: [02-02-engine, 02-03-cli, phase-3-tools]
tech-stack:
  added: ["tenacity>=9.2.1,<10"]
  patterns: ["injected httpx.MockTransport fixtures", "injected Clock sleep", "seeded Random wait"]
key-files:
  created:
    - src/pumpgrok/tools/__init__.py
    - src/pumpgrok/tools/onchain/__init__.py
    - src/pumpgrok/tools/onchain/rpc.py
    - src/pumpgrok/tools/onchain/authorities.py
    - src/pumpgrok/tools/onchain/holders.py
    - src/pumpgrok/tools/onchain/priority_fee.py
    - src/pumpgrok/tools/market/__init__.py
    - src/pumpgrok/tools/market/jupiter.py
    - tests/characterization/test_authority_check.py
    - tests/characterization/test_holder_check.py
    - tests/characterization/test_priority_fee.py
    - tests/characterization/test_jupiter_quote.py
    - tests/fixtures/http/authority_ok.json
    - tests/fixtures/http/authority_not_found.json
    - tests/fixtures/http/holders.json
    - tests/fixtures/http/priority_fee.json
    - tests/fixtures/http/jupiter_order.json
  modified:
    - pyproject.toml
    - uv.lock
    - .env.example
    - src/pumpgrok/config/settings.py
    - src/pumpgrok/config/overlays/dev.toml
    - src/pumpgrok/config/overlays/paper.toml
    - src/pumpgrok/config/overlays/live.toml
    - src/pumpgrok/core/datasource.py
    - ownership.yaml
    - tests/test_skip_cycle.py
decisions:
  - Tenacity 9.2.1 AsyncRetrying confirmed: sleep keyword plus custom wait callable; seeded _SeededWait used, never wait_random_exponential
  - recommended_lamports_per_cu kept as documented alias (MIGRATION row 77)
  - Jupiter x-api-key header; JUPITER_API_KEY stays non-PUMPGROK composition-root input
  - holders.py module owner settled to bot-05-rug per R35 (transfers stay WHALE)
  - Price mapping Ratio = priceImpact / 100; priceImpactPct never read
metrics:
  duration: 1 working session
  completed: 2026-10-21
  tasks: 3
  commits: 3
status: complete
actuals:
  tokens: 13000
  tasks: 3
  commits: 3
---

# Phase 02 Plan 01: Tools Tracer Summary

Tenacity-backed keyless Solana RPC client with ordered failover plus the four ported read-only root tools (authorities, holders, priority fee, Jupiter v2 quote), pinned by hand-authored fixtures and 13 offline characterization tests reproducing the 6 root unittest cases.

## Tasks Completed

| # | Task | Commit | Verify |
|---|------|--------|--------|
| 1 | Tracer: keyless RPC client plus authority check | aa9f62f | 5 passed |
| 2 | Holders, priority fee, Jupiter quote ports | f0a45bb | 13 passed (4-file SC1) |
| 3 | Ownership rules and static-gate close-out | 92612e9 | manifest OK, 366 paths owned |

## Verification Evidence

- SC1: `uv run python -m pytest tests/characterization/test_authority_check.py tests/characterization/test_holder_check.py tests/characterization/test_jupiter_quote.py tests/characterization/test_priority_fee.py` -> exit 0, 13 passed, no NetworkBlocked.
- Regression: `tests/test_skip_cycle.py` -> exit 0, 8 passed.
- Manifest: `python3 ci/gates/check_ownership.py --validate-manifest` -> exit 0, 366 tracked paths owned.
- Lint/typecheck on new files: `ruff check` exit 0, `ruff format --check` exit 0, `mypy` (strict, 9 files) exit 0.
- Settings: loads with all 8 new sections; key-bearing `PUMPGROK_RPC__ENDPOINTS` value refused at startup.
- Oracle cleanliness: `tools/`, `tests/test_tools_cli.py`, `vendor/` byte-identical (no modifications).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test expectation] Stale doctor assertion in test_skip_cycle.py**
- Found during: task 2 regression run
- Issue: `test_doctor_reports_absent_subsystems_as_warnings` listed `tools` as absent, but task 1's `tools/__init__.py` (plan-mandated, "doctor flips to ok") makes doctor report `ok tools`.
- Fix: assert `ok tools` present; absent list now `engine, gateway, supervisor, reports`. Anticipated by 02-PATTERNS.md row 50.
- Files modified: tests/test_skip_cycle.py
- Commit: f0a45bb

**2. [Rule 1 - Lint] S311 + F401 on new files**
- Found during: task 2 lint pass
- Issue: `random.Random(0)` default tripped S311; unused `SecretStr` import in jupiter test.
- Fix: default RNG via `make_rng()` (single sanctioned constructor path); removed unused import; `ruff format` applied.
- Commit: f0a45bb

### Ownership Settle (plan-authorized)

- `src/pumpgrok/tools/onchain/holders.py` rule changed `bot-03-whale` -> `bot-05-rug` per binding R35 (top_holders is a RUG grant; deployer_history/large_transfers stay WHALE). Flat test rules: authority/holder/priority_fee -> bot-05-rug, jupiter_quote -> bot-01-scout (R36).
- Commit: 92612e9

## Key Decisions

- Tenacity signature ASSUMED A1 confirmed against installed 9.2.1: `AsyncRetrying(sleep=..., stop=..., wait=<callable>, retry=..., reraise=...)`; custom `_SeededWait(retry_state)->float` draws jitter from the injected `random.Random`.
- RPC errors fail over to the next endpoint immediately; transport errors retry per endpoint (max 3) with injected-clock sleeps.
- `recommended_lamports_per_cu` kept as an explicit documented alias, never silently carried or dropped.
- `x-api-key` header name for a paid RPC key is provisional pending provider confirmation (Open Q7); all fixtures and tests are keyless.
- Each characterization module documents its oracle divergence in its docstring (Pitfall 1); non-zero-exit root cases are pinned via their exact `ok: False` predicate since CLI verbs land in a later plan.

## Known Stubs

None. No placeholders, mocks, or unwired paths were introduced.

## Threat Flags

None beyond the plan threat model (T-02-01/02/03, T-02-SC): no new endpoints, auth paths, or secrets. Verified: errors carry method plus endpoint count only; `JUPITER_API_KEY` never logged (keyless state only); `uv.lock` commits tenacity 9.2.1 in the same change as `pyproject.toml`; no respx/solders/solana added.

## Self-Check: PASSED

- All created files exist on disk; all modified files committed.
- Commits aa9f62f, f0a45bb, 92612e9 present in `git log`.
