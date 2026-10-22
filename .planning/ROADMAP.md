# Roadmap: PumpGrok Desk v2

## Overview

PumpGrok Desk v2 turns the existing pack (seats, skills, read-only tools, vendored dry-run engine) into an autonomous, paper-only Solana memecoin desk packaged as the Python 3.12 package `src/pumpgrok/`. The five phases follow the fixed plan (R37). Foundation builds the package, layered config, ownership, gates, contracts, the network-blocked test harness and a hash-chained ledger with a skip-only replay cycle. Restructure ports the read-only tools and the screening engine into the package while the vendor suite stays the oracle. Tools and Skills adds the typed dotted tool layer, least-privilege rosters, the desk gateway and the 35-skill set. Paper Trading and Autonomy adds the curve-faithful paper engine, risk engine, deterministic replay, supervisor, reports and the live-mode refusal, then retires the vendor tree. Hardening proves soak, fault injection, metrics, runbooks, the go-live gate and security evidence. Every phase checkpoint keeps `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` runnable.

Coverage: all 71 v1 requirements map to exactly one phase (see Traceability in `.planning/REQUIREMENTS.md`).

## Phases

- [x] **Phase 1: Foundation** - Package, layered config, ownership, ported gates, contracts, network-blocked harness and ledger with a skip-only replay cycle (19 requirements) (completed 2026-10-21)
- [x] **Phase 2: Restructure** - Read-only tools and vendor engine ported into `src/pumpgrok` with characterization tests, skills rewritten, CLI verbs exposed (5 requirements) (completed 2026-10-21)
- [x] **Phase 3: Tools and Skills** - Dotted typed tool layer, least-privilege rosters, desk gateway and the 35-skill set (15 requirements) (completed 2026-10-21)
- [x] **Phase 4: Paper Trading and Autonomy** - Curve-faithful paper fills, risk engine, deterministic replay, supervised ten-seat loop, reports, live refusal and vendor retirement (24 requirements) (completed 2026-10-22)
- [ ] **Phase 5: Hardening** - Multi-day soak, fault injection, metrics, runbooks, go-live gate proof and security evidence (8 requirements)

## Phase Details

### Phase 1: Foundation

**Goal**: A clean checkout installs from the lockfile, passes the canonical gates, loads layered settings, and runs one skip-only replay cycle that writes a hash-chained ledger with no network access.
**Depends on**: Nothing (first phase)
**Requirements**: FOUND-001, FOUND-002, FOUND-003, FOUND-004, FOUND-005, FOUND-006, FOUND-007, FOUND-008, FOUND-009, FOUND-010, FOUND-011, FOUND-012, FOUND-013, STRUCT-001, STRUCT-008, OBS-001, OBS-002, SEC-001, SEC-002
**Success Criteria** (what must be TRUE):

  1. `uv sync --frozen && make lint typecheck test audit` exits 0 on a clean checkout (FOUND-001, FOUND-002)
  2. `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0, and `uv run python -c "import sqlite3; print(sqlite3.connect('var/replay/smoke/ledger.sqlite').execute(\"select count(*) from events where type='JournalNote' and source='replay'\").fetchone()[0])"` prints `1` (FOUND-013)
  3. `python3 ci/gates/check_ownership.py --validate-manifest`, `python3 ci/gates/check_desk_integrity.py --repo .`, `python3 ci/gates/check_secrets.py --base origin/main` and `python3 -m pytest ci/tests/ -q` each exit 0 (FOUND-006, FOUND-007, FOUND-008, SEC-001)
  4. `docker compose config --quiet` exits 0, `docker compose build pumpgrok` exits 0, `docker compose run --rm pumpgrok` exits 0 after one skip-only replay cycle, and `./scripts/check.sh` exits 0 (FOUND-003, FOUND-011)
  5. `uv run pytest -q` exits 0 including the static test that rejects direct `asyncio.sleep`, `asyncio.timeout`, `time.time` and `uuid` use in `src/pumpgrok`, and `! grep -rn -e JitoConfig -e wallet_private_key src/pumpgrok` prints nothing; `test ! -d config` succeeds (FOUND-004, FOUND-005, FOUND-012, STRUCT-008)

**Checkpoint**: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` completes one cycle under skip-only semantics (`docs/upgrade-plan-desk-v2.md` section 6.1) and the canonical gates pass.

**Deliverables**:

- [ ] `uv_build` src-layout package, Python 3.12 pin, committed `uv.lock` (FOUND-001)
- [ ] Make targets, multi-stage non-root image, compose healthcheck (FOUND-002, FOUND-003)
- [ ] pydantic-settings loader with R30 precedence, overlays and forbidden-key refusal (FOUND-004, STRUCT-008)
- [ ] `core/` interfaces, registry, ids and approvals with invariants I1-I5 (FOUND-005)
- [ ] `ownership.yaml`, ported G-1..G-7 gates, receipts, pre-commit and workflows (FOUND-006, FOUND-007, FOUND-010)
- [ ] `contracts/` rosters and event schemas, prompt sources, assembly, AGENTS/SECURITY/docs (FOUND-008, FOUND-009, FOUND-011)
- [ ] Network-blocking test harness, replay clock/rng/fixtures, `FaultInjector` (FOUND-012)
- [ ] Ledger store and event models, skip-only replay cycle, `pumpgrok doctor` (FOUND-013)
- [ ] Redacted JSON logging, ULID correlation spans, env-only secrets, tracked-file cleanup (OBS-001, OBS-002, SEC-002, STRUCT-001)

**Plans**: TBD

- [x] 01-01-PLAN.md
- [x] 01-02-PLAN.md
- [x] 01-03-PLAN.md
- [x] 01-04-PLAN.md
- [x] 01-05-PLAN.md
- [x] 01-06-PLAN.md
- [x] 01-07-PLAN.md
- [x] 01-08-PLAN.md
- [x] 01-09-PLAN.md

### Phase 2: Restructure

**Goal**: The read-only tools and the vendor screening engine run from `src/pumpgrok` under characterization tests while the vendor tree stays alive as the oracle; skills, CLI verbs and the signing guard match the target layout.
**Depends on**: Phase 1
**Requirements**: STRUCT-002, STRUCT-003, STRUCT-005, STRUCT-007, SEC-003
**Success Criteria** (what must be TRUE):

  1. `uv run pytest -q tests/characterization/test_authority_check.py tests/characterization/test_holder_check.py tests/characterization/test_jupiter_quote.py tests/characterization/test_priority_fee.py` exits 0, reproducing the 6 root unittest cases that exercise these four ported tools (STRUCT-002)
  2. `cd vendor/grokbot-pumpfun && python3 -m pytest -q` exits 0, `uv run pytest -q tests/characterization/` exits 0, and `! grep -rlP '\p{Cyrillic}' src/pumpgrok/engine/` prints nothing (STRUCT-003)
  3. `test "$(ls -d skills/*/ | wc -l)" -eq "$(grep -l '^bots:' skills/*/SKILL.md | wc -l)" && test "$(grep -l '^bots:' skills/*/SKILL.md | wc -l)" -eq "$(grep -l '^gates:' skills/*/SKILL.md | wc -l)" && ! grep -rn -e lite-api -e '--max-micro' skills/` exits 0 (STRUCT-007). Superseded by Phase 3 SC2a: the count of 23 became 35 when Phase 3 added twelve skills, so the invariant is now every skill directory carrying both bots and gates frontmatter.
  4. `uv run pumpgrok --help` exits 0, and `uv run pumpgrok paper buy --help` lists `--ticket`, `--mint`, `--size-sol`, `--slippage-bps` and `--approval-id` (STRUCT-005)
  5. `uv run pytest -q tests/safety/test_no_signing_outside_live_stub.py` exits 0 (SEC-003)

**Checkpoint**: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` still completes one cycle and the canonical gates pass.

**Deliverables**:

- [ ] Read-only tools re-implemented over the single RPC client with failover (STRUCT-002)
- [ ] Vendor monitor, analyzer, scoring, reputation, agents, tune, exits and watcher ported with translated strings and unchanged reason codes (STRUCT-003)
- [ ] CLI verbs of DISCOVERY plus R12 and R40, `not-yet-implemented` for absent subsystems, cron prompts wrap `pumpgrok` only (STRUCT-005)
- [ ] 23 skills gain `bots` and `gates` frontmatter and L1/L2 bodies; quote-only Jupiter path (STRUCT-007)
- [ ] AST guard against signing symbols outside the live stub (SEC-003)

**Plans**: TBD

### Phase 3: Tools and Skills

**Goal**: Every desk tool is a typed, registered dotted tool that seats reach only through least-privilege rosters, exposed through the desk gateway, and the full 35-skill set validates against its manifests.
**Depends on**: Phase 2
**Requirements**: TOOL-001, TOOL-002, TOOL-003, TOOL-004, TOOL-005, TOOL-006, TOOL-007, TOOL-008, TOOL-009, TOOL-010, TOOL-011, SKILL-001, SKILL-002, SKILL-003, SKILL-004
**Success Criteria** (what must be TRUE):

  1. `uv run pytest -q tests/test_skill_manifests.py tests/test_bot_manifests.py` exits 0 (SKILL-002, SKILL-003)
  2. `test "$(ls -d skills/*/ | wc -l)" -eq 35` and `grep -q 'bot-09-journal' skills/desk-post-trade-review/SKILL.md` both exit 0, and `! grep -rn "23 skills" plugin.json .claude-plugin .grok-plugin .cursor-plugin agents` prints nothing (SKILL-001, SKILL-004)
  3. `uv run pytest -q -k "least_privilege or gateway"` exits 0, and the desk gateway suite in `services/desk-gateway/` passes under `uv run pytest -q` (TOOL-009, TOOL-010)
  4. `uv run pumpgrok paper buy --help` lists `--ticket`, `--mint`, `--size-sol`, `--slippage-bps` and `--approval-id`, and `! grep -rnE "\b(post|put|patch|delete)\b|method=['\"](POST|PUT|PATCH|DELETE)" src/pumpgrok/tools/social/` prints nothing (TOOL-011, TOOL-009)
  5. `! grep -rnE "(lamports|units|sol)[A-Za-z_]*: *float" src/pumpgrok/tools src/pumpgrok/core src/pumpgrok/cli.py` prints nothing and `uv run pytest -q` exits 0 (TOOL-008). Scope narrowed to the new layers by user approval (ask: float, Narrow criterion 5); vendor-parity float fields in src/pumpgrok/engine/ are exempt until Phase 4 retires the oracle.

**Checkpoint**: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` still completes one cycle and the canonical gates pass.

**Deliverables**:

- [ ] Market, onchain, safety, exec, portfolio, risk, journal, notify and desk core tools with typed models (TOOL-001..008)
- [ ] Ten seat rosters and `_core.yaml` with the R35 sizes; least-privilege suite (TOOL-009)
- [ ] Desk gateway serving `/mcp/<seat>` with per-seat token isolation (TOOL-010)
- [ ] Operator verbs as thin catalog wrappers printing JSON (TOOL-011)
- [ ] Twelve new skills, skill and bot manifest tests, seat prompt skill lists (SKILL-001..004)

**Plans**: TBD

- [x] 03-01-PLAN.md
- [x] 03-02-PLAN.md
- [x] 03-03-PLAN.md
- [x] 03-04-PLAN.md
- [x] 03-05-PLAN.md
- [x] 03-06-PLAN.md
- [x] 03-07-PLAN.md

### Phase 4: Paper Trading and Autonomy

**Goal**: The desk runs autonomously in paper mode on fixture data: curve-faithful fills, a risk engine with halts, breakers and kill switch, deterministic replay under virtual time, a supervised ten-seat loop with health and reports, live mode refused, and the vendor tree retired.
**Depends on**: Phase 3
**Requirements**: STRUCT-004, STRUCT-006, PAPER-001, PAPER-002, PAPER-003, PAPER-004, PAPER-005, PAPER-006, PAPER-007, RISK-001, RISK-002, RISK-003, RISK-004, RISK-005, RISK-006, AUTO-001, AUTO-002, AUTO-003, AUTO-004, AUTO-005, AUTO-006, SEC-004, GOLIVE-001, GOLIVE-002
**Success Criteria** (what must be TRUE):

  1. `uv run pytest --collect-only -q tests/characterization` reports at least 164 tests collected, and `uv run pytest -q` exits 0 (STRUCT-004)
  2. `uv run pumpgrok verify --fixture smoke-10m` exits 0, showing two seeded runs over `tests/fixtures/replay/smoke-10m` produce identical `events.hash`, JSONL bytes and final state (PAPER-004)
  3. `PUMPGROK_KILLSWITCH=1 uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke-10m` exits 0 and `uv run python -c "import sqlite3; print(sqlite3.connect('var/replay/smoke-10m/ledger.sqlite').execute(\"select count(*) from events where type='OrderPlaced'\").fetchone()[0])"` prints `0` (RISK-004, RISK-003)
  4. `uv run pumpgrok run --mode live --once` exits 3 and sends nothing; `uv run pumpgrok report --daily` and `uv run pumpgrok report --weekly` exit 0, and `uv run pumpgrok report --daily | LC_ALL=C grep -c -P '[^\x00-\x7F]'` prints `0` (SEC-004, PAPER-006)
  5. `test ! -e vendor/grokbot-pumpfun`, `test -f src/pumpgrok/engine/LICENSE-grokbot-pumpfun`, and `rg -l -F "vendor/grokbot-pumpfun" src skills agents rules hermes scripts ci contracts prompts` prints nothing (STRUCT-006)

**Checkpoint**: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` completes one full ten-seat cycle with no network access and the canonical gates pass.

**Deliverables**:

- [ ] Vendor executor, risk, ops, state and log ported with adapted characterization tests; daily-loss auto-clear intentionally dropped (STRUCT-004)
- [ ] `PaperAdapter` with curve-based fills, slippage, partial fills and dropped transactions (PAPER-001)
- [ ] Hash-chained WAL ledger with snapshots, reducer, JSONL export and tamper detection (PAPER-002, PAPER-003)
- [ ] Deterministic replay and recorder with canonical request hashes (PAPER-004)
- [ ] Graduation, post-graduation rejection and BLIND flatten rules (PAPER-005)
- [x] Daily and weekly reports, tickets and approvals (PAPER-006, PAPER-007)
- [ ] Risk engine, halts, breakers, kill switch and observe-only degradation (RISK-001..006)
- [ ] Supervisor with heartbeats, restarts, health endpoints and graceful shutdown; degraded-mode matrix (AUTO-001..006)
- [x] Live adapter stub that always refuses with `LiveGateError`, live gate validation and confirmation record (SEC-004, GOLIVE-001, GOLIVE-002)
- [x] Vendor tree deleted after the six retirement checks (STRUCT-006)

**Plans**: TBD
- [x] 04-01-PLAN.md
- [x] 04-02-PLAN.md
- [x] 04-03-PLAN.md
- [x] 04-04-PLAN.md
- [x] 04-05-PLAN.md
- [x] 04-06-PLAN.md
- [x] 04-07-PLAN.md
- [x] 04-08-PLAN.md
- [x] 04-09-PLAN.md

### Phase 5: Hardening

**Goal**: The desk survives multi-day replay, injected faults and restarts; exposes metrics and health; ships runbooks and proven go-live gates with live disabled; and carries security and changelog evidence.
**Depends on**: Phase 4
**Requirements**: RISK-007, AUTO-007, AUTO-008, OBS-003, OBS-004, OBS-005, SEC-005, GOLIVE-003
**Success Criteria** (what must be TRUE):

  1. `uv run pytest -q tests/soak/test_soak_multiday_replay.py tests/degradation/` exits 0, covering the `soak-3d` memory bound, daily rollover and each degraded-mode fault row (AUTO-007, AUTO-008)
  2. `grep -rhoE "pumpgrok_(cycle_seconds|bot_crashes_total|orders_total|equity_sol|drawdown_pct|data_age_seconds|breaker_state|kill_switch|ledger_seq)" src/pumpgrok | sort -u | wc -l` prints `9`, and the metrics tests pass under `uv run pytest -q` (OBS-003)
  3. `for f in setup engine start_stop kill_switch breaker_reset outage rollback reading_reports go_live; do test -f docs/runbooks/$f.md || exit 1; done && ./scripts/check.sh` exits 0, `for p in 1 2 3 4 5; do grep -q "Phase $p" CHANGELOG.md || exit 1; done` exits 0, and `docker compose up -d --build pumpgrok && docker compose ps pumpgrok` reports the service `healthy` via the supervisor `/healthz` probe (OBS-004, OBS-005, FOUND-003)
  4. `uv run pytest -q tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py` exits 0, and `for f in src/pumpgrok/config/overlays/*.toml; do uv run python -c "import tomllib,sys; d=tomllib.load(open('$f','rb')); assert d.get('live',{}).get('enabled') is False, '$f'" || exit 1; done` exits 0 (RISK-007, GOLIVE-003)
  5. `gh run list --workflow security-pr.yml --branch main --limit 1 --json conclusion -q '.[0].conclusion'` prints `success`, or every non-green check is listed in `SECURITY.md` with an expiry date (SEC-005)

**Checkpoint**: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` still completes one cycle and the canonical gates pass.

**Deliverables**:

- [ ] `soak-3d` multi-day replay and fault-injection suite under `tests/degradation/` (AUTO-007, AUTO-008)
- [ ] Prometheus `/metrics` endpoint and span timings (OBS-003)
- [ ] Nine runbooks, CHANGELOG entries for every phase, AGENTS index and milestone report (OBS-004, OBS-005)
- [ ] `docs/RISK_POLICY.md` compliance boundary and manipulation-tool test (RISK-007)
- [ ] Go-live runbook and fail-fast proof for each of the nine preconditions; `live.enabled = false` in every overlay (GOLIVE-003)
- [ ] Security workflow green on `main` or exceptions with expiry in `SECURITY.md` (SEC-005)

**Plans**: 8 plans in 5 waves
- [ ] 05-01-PLAN.md (wave 1, OBS-003)
- [ ] 05-02-PLAN.md (wave 1, OBS-004, OBS-005)
- [ ] 05-03-PLAN.md (wave 2, AUTO-007, AUTO-008)
- [ ] 05-04-PLAN.md (wave 2, RISK-007, GOLIVE-003)
- [ ] 05-05-PLAN.md (wave 3, OBS-005)
- [ ] 05-06-PLAN.md (wave 3, OBS-005)
- [ ] 05-07-PLAN.md (wave 4, SEC-005, OBS-004)
- [ ] 05-08-PLAN.md (wave 5, OBS-005)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 14/14 | Complete    | 2026-10-21 |
| 2. Restructure | 5/5 | Complete    | 2026-10-21 |
| 3. Tools and Skills | 7/7 | Complete    | 2026-10-21 |
| 4. Paper Trading and Autonomy | 10/10 | Complete    | 2026-10-22 |
| 5. Hardening | 0/8 | Planned | - |
