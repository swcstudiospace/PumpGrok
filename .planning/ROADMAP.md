# Roadmap: PumpGrok Desk v3

## Overview

PumpGrok Desk v3 makes the paper desk autonomous and evaluable, closes the integrity gaps the v2 audits found, and documents the codebase for agents. Live trading stays disabled throughout. Five phases follow the owner's sequence. Phase 6 closes the audited invariant violations and the feature-lineage gaps first, so every later phase builds on integer money and fail-closed state. Phase 7 rewrites the docs against that fixed code. Phase 8 adds the holdout-aware backtest, the shared result schema and the paper divergence check. Phase 9 adds bounded, reversible paper parameter promotion and applies the approved constitution amendment together with the code it describes. Phase 10 records live readiness and keeps live refused.

Coverage: all 34 v3 requirements map to exactly one phase (see Traceability in `.planning/REQUIREMENTS.md`).

## Shipped

- [x] **v2: PumpGrok Desk v2** - shipped 2026-10-23, 5 phases, 44 plans. Archived: [roadmap](milestones/v2-ROADMAP.md), [requirements](milestones/v2-REQUIREMENTS.md), [audit](milestones/v2-MILESTONE-AUDIT.md).

## Phases

- [ ] **Phase 6: Integrity closure** - Audited invariant violations closed or proven present, feature-lineage fixes re-applied, replay hash before and after recorded (12 requirements)
- [x] **Phase 7: Documentation upgrade** - CLAUDE.md codebase map, trimmed AGENTS.md, contradictions corrected, historical design banners (4 requirements)
- [x] **Phase 8: Backtest and paper evaluation** - Run manifests, holdout and trial accounting, `pumpgrok backtest` verb, shared result schema and divergence check (10 requirements)
- [x] **Phase 9: Bounded paper self-upgrade** - Content-hashed bounded parameter promotion with exact rollback, BLIND advisory rule and the approved constitution amendment (6 requirements)
- [x] **Phase 10: Live readiness, kept disabled** - Live refused with exit 3, no live adapter, import-graph proof and a deferred live-readiness record (2 requirements)

## Phase Details

### Phase 6: Integrity closure

**Goal**: Every audited invariant violation on main is closed or proven present, the two feature-lineage fixes are applied with regression tests, and replay output is unchanged or its change is recorded in CHANGELOG.md by before and after hash.
**Depends on**: Nothing (first v3 phase; branch `bot-00-chief/phase-6-integrity` from origin/main f3887bb)
**Requirements**: INT-01, INT-02, INT-03, INT-04, INT-05, INT-06, INT-07, INT-08, INT-09, INT-10, PRC-01, PRC-02
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test` and `./scripts/check.sh` each exit 0 (PRC-01)
  2. `uv run pytest -q tests/integrity/test_money_types.py` exits 0 and `! grep -rnE "\b[a-z_]*(lamport|equity|fee|pnl|cost|price|size|balance)[a-z_]*\s*:\s*float\b" src/pumpgrok --include=*.py` exits 0 (INT-01)
  3. `uv run pytest -q tests/integrity/test_fail_closed_state.py` exits 0; the test corrupts the ledger peak state, the seat initial equity and the genesis equity, and expects a typed error from each (INT-02)
  4. `uv run pytest -q tests/integrity/test_daily_loss_integer.py` exits 0; a non-positive day-start equity fails the check and is never treated as zero loss (INT-03)
  5. `uv run pytest -q tests/integrity/test_single_sol_conversion.py` exits 0 and `! grep -rn "1_000_000_000" src/pumpgrok --include=*.py | grep -v "src/pumpgrok/core/"` exits 0 (INT-04)
  6. `uv run pytest -q tests/integrity/test_rng_roots.py` exits 0, `! grep -rn "os.urandom" src/pumpgrok --include=*.py | grep -v -E "src/pumpgrok/core/(ids|binding_key)\.py"` exits 0, and `! grep -rn "DEFAULT_SEED" src/pumpgrok --include=*.py | grep -v "src/pumpgrok/replay/"` exits 0 (INT-05)
  7. `uv run pytest -q tests/integrity/test_live_gate_clock.py` exits 0 (gate output byte-identical under a fixture clock) and `! grep -nE "time\.time|datetime\.(now|utcnow)" src/pumpgrok/execution/live/live_gate.py` exits 0 (INT-06)
  8. `uv run pytest -q tests/integrity/test_wr07_replay_ledger_removed.py tests/integrity/test_ledger_mark_fee_partial_sell.py` exits 0, and each of the two tests fails on its pre-fix parent: `git worktree add --detach /tmp/int07-pre 4c19fd9^ && cp -r tests/integrity /tmp/int07-pre/tests/ && (cd /tmp/int07-pre && uv run pytest -q tests/integrity/test_wr07_replay_ledger_removed.py)` exits 1, then the same with `76975bb^` and `test_ledger_mark_fee_partial_sell.py` exits 1, then `git worktree remove --force /tmp/int07-pre` exits 0 (INT-07)
  9. `uv run pytest -q tests/integrity/test_function_length.py` exits 0; it asserts that `_place_buy`, `_place_order` and `_replay_cycles` are each at most 60 lines after the stage split (INT-08)
  10. `uv run pytest -q tests/integrity/test_peaks_survive_restart.py` exits 0; trailing-stop peaks are restored from the ledger after a simulated serve restart (INT-09)
  11. `uv run python scripts/probe_curve_layout.py` exits 0 and writes `docs/CURVE_LAYOUT_PROBE.md` with one line `Status: VERIFIED` or `Status: ASSUMED`; when it reads ASSUMED, `grep -E "^Error: .+" docs/CURVE_LAYOUT_PROBE.md` exits 0 and carries the exact probe error, which satisfies INT-10 and is not a blocker; `! grep -nE "sendTransaction|send_transaction|requestAirdrop|signTransaction" scripts/probe_curve_layout.py` exits 0; `grep -rqE 'LAYOUT_STATUS[^=]*=\s*"ASSUMED"' src/pumpgrok` exits 0 or `grep -rqE 'LAYOUT_STATUS[^=]*=\s*"VERIFIED"' src/pumpgrok` exits 0 to match the recorded status (INT-10). The pattern allows the annotated assignment `LAYOUT_STATUS: Final[str] = "ASSUMED"`; the unannotated `\s*=\s*` form cannot match it (corrected 2026-10-25).
  12. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0 (live stays refused)
  13. `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0
  14. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b"` exits 0, and `grep -qE "Phase 6: smoke-10m events.hash before: [0-9a-f]{64}" CHANGELOG.md && grep -qF "Phase 6: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0; the before value is the events.hash printed on the phase branch before its first edit, and the after value is the hash this phase produces (INT-08 and the replay rule)
  15. `grep -qE "5b5d6a1" CHANGELOG.md && grep -qE "9772655" CHANGELOG.md` exits 0 (review of the Omega CI runner migration recorded, the v2 deferred item)
  16. `test "$(git branch --show-current | grep -cE '^bot-0[0-9]-[a-z-]+/phase-6-[a-z-]+$')" -eq 1` exits 0 and `gh pr list --head "$(git branch --show-current)" --json isDraft,mergedAt --jq 'all(.isDraft and .mergedAt == null)'` prints `true` (PRC-02)
  17. `python3 ci/gates/run_all.py --bot bot-00-chief --receipt .receipts/bot-00-chief/phase-6.json` exits 0 for each completion claim in this phase (PRC-01)

**Checkpoint**: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` completes one cycle, `uv run pumpgrok verify --fixture smoke-10m` prints the same events.hash on two runs, live stays refused with exit 3, and the canonical gate set is green.

**Deliverables**:

- [ ] `src/pumpgrok/ledger/export.py`, `src/pumpgrok/engine/models.py`, `src/pumpgrok/engine/analyzer.py`, `src/pumpgrok/engine/exits.py`, `src/pumpgrok/engine/reputation.py`, `src/pumpgrok/engine/tune.py`: integer money, Decimal for ratios only, and the static guard `tests/integrity/test_money_types.py` (INT-01)
- [ ] `src/pumpgrok/ledger/reducer.py`, `src/pumpgrok/supervisor/seat_task.py`, `src/pumpgrok/supervisor/lifecycle.py`: typed fail-closed errors in place of silent defaults, with regression tests (INT-02)
- [ ] Daily-loss halt in `src/pumpgrok/risk/`: integer arithmetic and a failed check for non-positive day-start equity (INT-03)
- [ ] One SOL-to-lamports conversion in `src/pumpgrok/core/`, used by `src/pumpgrok/core/risk_budget.py`, the CLI and `src/pumpgrok/core/approvals.py`; the copy in `src/pumpgrok/reporting/render.py` removed (INT-04)
- [ ] `src/pumpgrok/core/ids.py` and `src/pumpgrok/core/binding_key.py` as the only `os.urandom` roots; `DEFAULT_SEED` in `src/pumpgrok/replay/rng.py` confined to replay; guard in `tests/integrity/test_rng_roots.py` (INT-05)
- [ ] `src/pumpgrok/execution/live/live_gate.py` reads time only through the injected clock (INT-06)
- [ ] WR-07 (commit 4c19fd9, replay ledger removed on failed append or verify) and the ledger-mark venue-fee fix (commit 76975bb) re-applied on the phase branch. Neither is an ancestor of origin/main (checked 2026-10-25; both sit on `feat/grokbot-desk-merge`, which stays untouched per V3-3). Regression tests in `tests/integrity/` (INT-07)
- [ ] `src/pumpgrok/execution/paper_adapter.py` (`_place_buy`, `_place_order`) and `src/pumpgrok/supervisor/scheduler.py` (`_replay_cycles`) split into stage functions with unchanged behaviour (INT-08)
- [ ] Trailing-stop peak persistence and restore in `src/pumpgrok/engine/exits.py` and `src/pumpgrok/risk/engine.py` (INT-09)
- [ ] `scripts/probe_curve_layout.py` (read-only) and `docs/CURVE_LAYOUT_PROBE.md`; `LAYOUT_STATUS` in `src/pumpgrok` set to match the probe result; entries fail closed while ASSUMED (INT-10)
- [ ] `CHANGELOG.md` entries: the Phase 6 before and after replay hash lines, and the review of Omega CI runner migration commits 5b5d6a1 and 9772655 (PRC-01)
- [ ] Phase branch and draft PR per AGENTS.md; no merge to main (PRC-02)

**Plans**: 9 planned (06-01 to 06-09) plus fix-up 06-01b; all have SUMMARY files. Phase blocked on owner decisions (see .planning/STATE.md).

### Phase 7: Documentation upgrade

**Goal**: CLAUDE.md, AGENTS.md, README, ARCHITECTURE, SETUP, the replay skill, the plugin version statements and the vendor pin describe the code as fixed by Phase 6, and historical design records say so in a banner.
**Depends on**: Phase 6
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-04
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `test "$(grep -cE '^## (Purpose|Stack|Layout|Commands|Architecture|Conventions|GSD artifact|Safety|Known gaps)' CLAUDE.md)" -ge 9` exits 0 (DOC-01)
  3. `! grep -nE '^\s*[-*] ' CLAUDE.md | grep -v '`'` exits 0; every bullet in CLAUDE.md cites a backticked repository path (a grep proxy for "every statement cites a file"; the phase review checks prose statements) (DOC-01)
  4. `test "$(wc -l < AGENTS.md)" -lt "$(git show origin/main:AGENTS.md | wc -l)"` exits 0, `grep -q "CLAUDE.md" AGENTS.md` exits 0, and `! grep -niE "placeholder" AGENTS.md` exits 0 (DOC-02)
  5. `./scripts/verify_doc_commands.sh` exits 0; it runs each command in the Commands sections of AGENTS.md and CLAUDE.md and checks its documented exit code (DOC-02)
  6. `uv run pytest -q tests/docs/` exits 0; it asserts that plugin version statements match `pyproject.toml`, that `docs/VENDOR_PIN.md` matches the vendored snapshot, that every command named in README, ARCHITECTURE, SETUP and `skills/replay-and-backtest/SKILL.md` exists in the CLI help, and that no contradiction from the 2026-10-25 docs audit remains (DOC-03)
  7. `uv run pytest -q tests/docs/test_historical_banners.py` exits 0; every historical design record it lists begins with the banner "Historical design record" (DOC-04)
  8. `test "$(grep -cE 'DOC-0[1-4]' CHANGELOG.md)" -ge 4` exits 0 (DOC-03)
  9. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && grep -qF "Phase 6: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0; the replay output is unchanged by this phase, and CHANGELOG.md records `Phase 7: smoke-10m events.hash after: $a` with the same value

**Checkpoint**: every command, version and path in the docs resolves against the code, `./scripts/verify_doc_commands.sh` is green, and the replay hash is unchanged from Phase 6.

**Deliverables**:

- [x] `CLAUDE.md` at the repository root: purpose, stack, layout, commands, architecture and data flow, conventions, GSD artifact locations, safety rules and known gaps, each bullet citing a file (DOC-01)
- [x] `AGENTS.md` trimmed: stale GSD research dump and placeholder blocks removed, rules index kept, commands verified, links `CLAUDE.md` instead of duplicating it (DOC-02)
- [x] `scripts/verify_doc_commands.sh`: runs the documented commands with their expected exit codes (DOC-02)
- [x] `README.md`, `ARCHITECTURE.md`, `SETUP.md`, `skills/replay-and-backtest/SKILL.md`, plugin version statements and `docs/VENDOR_PIN.md` corrected for every contradiction in the 2026-10-25 docs audit (DOC-03)
- [x] `tests/docs/` consistency tests and `tests/docs/test_historical_banners.py` (DOC-03, DOC-04)
- [x] Banner "Historical design record" on the design records under `docs/` (`docs/design/`, `docs/DISCOVERY.md`, `docs/MIGRATION_MAP.md`, `docs/upgrade-plan-desk-v2.md`); the set is fixed in `tests/docs/test_historical_banners.py` (DOC-04)
- [x] `CHANGELOG.md` entry for each documentation change, tagged with its DOC id, and the Phase 7 replay hash line (DOC-03)

**Plans**: 6 complete (07-01 to 07-06). Verification: `.planning/phases/07-documentation-upgrade/07-VERIFICATION.md` (passed, 9 of 9 criteria). Criterion 6 checks the vendor pin and a retirement statement, not a snapshot (OVERRIDE-D; the snapshot was deleted in Phase 4). Criterion 5 runs the offline subset; make targets, `run --serve` and `check.sh` are name-checked, not executed. Overrides A to D are recorded in the plan SUMMARY files.

### Phase 8: Backtest and paper evaluation

**Goal**: A `pumpgrok backtest` verb runs a parameter set over a recorded dataset with a holdout and trial accounting and writes byte-identical reports; the holdout-aware harness replaces the in-sample grid search; backtest results and paper ledger trades share one schema and a divergence check on the D7 defaults blocks promotion on breach.
**Depends on**: Phase 6 (integer money and the new result schema)
**Requirements**: BT-01, BT-02, BT-03, BT-04, BT-05, BT-06, BT-07, PAP-01, PAP-02, PAP-03
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/backtest/test_run_manifest.py` exits 0; the manifest holds the whole-dataset digest over every file in the dataset directory, the seed, the FilterSettings hash, the parameter-set hash and the code version, and changing one byte of a dataset file changes the run id (BT-01)
  3. `uv run pytest -q tests/backtest/test_replay_result_fields.py` exits 0; each fill carries price, venue fee, network cost, latency, filled fraction and outcome (BT-02)
  4. `uv run pytest -q tests/backtest/test_holdout_split.py` exits 0; the holdout is the final 20 percent of the time window, no tuning step reads it, and the report names the split identifiers (BT-03)
  5. `uv run pytest -q tests/backtest/test_trial_limits.py` exits 0; a search above 20 trials is flagged ineligible for promotion, and a search above 50 trials is rejected with a typed error (BT-04)
  6. `uv run pytest -q tests/backtest/test_metrics.py` exits 0; `grep -rnE "annualiz" src/pumpgrok/backtest --include=*.py` exits 0 with the annualization stated in code; `! grep -rniE "expected (return|profit|pnl)|will earn" src/pumpgrok/backtest src/pumpgrok/reporting --include=*.py` exits 0 (BT-05)
  7. `uv run pumpgrok backtest --fixture smoke-10m > /tmp/bt-a.md && uv run pumpgrok backtest --fixture smoke-10m > /tmp/bt-b.md && cmp /tmp/bt-a.md /tmp/bt-b.md` exits 0, and `grep -qi "holdout" /tmp/bt-a.md && grep -qi "trial" /tmp/bt-a.md && grep -qi "slippage" /tmp/bt-a.md && grep -qi "fees" /tmp/bt-a.md` exits 0 (BT-06)
  8. `! grep -rnE "grid|itertools\.product" src/pumpgrok/engine src/pumpgrok/backtest --include=*.py` exits 0 and `uv run pytest -q tests/backtest/test_single_search_engine.py` exits 0; the harness is the only search entry point (BT-07)
  9. `uv run pytest -q tests/backtest/test_shared_result_schema.py` exits 0; backtest results and paper ledger trades are built from one result model and compare over the same window (PAP-01)
  10. `uv run pytest -q tests/backtest/test_divergence.py` exits 0; a 2 percentage point absolute return gap and a 0.5 Sharpe gap each raise an alert and block promotion, using the D7 defaults as the configured values (PAP-02)
  11. `uv run pytest -q tests/e2e/test_autonomous_paper_recorded.py tests/safety/test_manual_ticket_no_upgrade.py` exits 0; autonomous paper runs end to end on the recorded `smoke` and `smoke-10m` datasets at the human-set autonomous-paper level, and manual-ticket never runs an upgrade (PAP-03)
  12. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && grep -qE "Phase 8: smoke-10m events.hash before: [0-9a-f]{64}" CHANGELOG.md && grep -qF "Phase 8: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0; the result schema changes replay output, so the before and after hash are both recorded
  13. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0

**Checkpoint**: `pumpgrok backtest` writes byte-identical reports for identical inputs, the divergence check blocks promotion on breach, and the replay smoke command completes one cycle.

**Deliverables**:

- [x] `src/pumpgrok/backtest/` new package: run manifest, holdout and walk-forward split, bounded metrics, and the holdout-aware harness that replaces the grid search (BT-01, BT-03, BT-05, BT-07)
- [x] Trial ledger with the 20-trial flag and 50-trial rejection in `src/pumpgrok/backtest/` (BT-04)
- [x] Per-fill result fields in `src/pumpgrok/replay/` (BT-02)
- [x] `backtest` verb in `src/pumpgrok/cli.py` with deterministic report output (BT-06)
- [x] `src/pumpgrok/engine/tune.py`: in-sample grid search removed; no second search engine remains (BT-07)
- [x] One shared result model for backtest and paper ledger trades (PAP-01)
- [x] Divergence check on the D7 defaults in `src/pumpgrok/backtest/` (PAP-02)
- [x] `tests/backtest/`, `tests/e2e/test_autonomous_paper_recorded.py` and the autonomous-paper verification on recorded datasets (PAP-03)
- [x] `CHANGELOG.md` before and after replay hash lines for Phase 8

**Plans**: 10 complete. 08-01 to 08-07 delivered the phase; 08-08 to 08-10 are a correction set that replaced the digest-scored evaluator (see 08-CORRECTION.md). Verification: `.planning/phases/08-backtest-and-paper-evaluation/08-VERIFICATION.md` (passed, 13 of 13 criteria).

### Phase 9: Bounded paper self-upgrade

**Goal**: Paper parameter sets are content-hashed and held within version-controlled bounds; a candidate is promoted only through the gate; every promotion records its evidence and one operation rolls back to the exact prior version; SAFE-4 and SAFE-8 BLIND results are advisory while no paid RPC provider is recorded; the approved constitution amendment lands with the code it describes.
**Depends on**: Phase 8
**Requirements**: UPG-01, UPG-02, UPG-03, UPG-04, UPG-05, UPG-06
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/upgrade/test_param_set_hash.py tests/upgrade/test_active_set_ledger.py` exits 0 (parameter sets are content-hashed; the active set is written to the ledger) and `uv run python -c "import tomllib; tomllib.load(open('src/pumpgrok/config/upgrade_bounds.toml','rb'))"` exits 0 (UPG-01)
  3. `uv run pytest -q tests/upgrade/test_promotion_gate.py` exits 0; an out-of-bounds candidate, a failed holdout, a divergence breach, a search above 20 trials, and a run below the autonomous-paper level each block promotion (UPG-02)
  4. `uv run pytest -q tests/upgrade/test_promotion_evidence.py` exits 0; each promotion records the candidate hash, backtest run id, holdout id, divergence result, trial count and bounds (UPG-03)
  5. `uv run pytest -q tests/upgrade/test_rollback_exact.py` exits 0; promote then roll back restores the exact prior version, verified by content hash and by the active-set ledger record (UPG-03)
  6. `uv run pytest -q tests/upgrade/test_escalation.py` exits 0; an out-of-bounds or ineligible candidate is not promoted and produces a decision request and a journal note (UPG-04)
  7. `uv run pytest -q tests/safety/test_blind_advisory.py` exits 0; SAFE-4 and SAFE-8 report BLIND as advisory with the blind reason written into the verdict while no paid RPC provider is recorded, every other BLIND result stays KILL, and the rule reverts to required when a provider is recorded (UPG-05)
  8. `python3 scripts/generate-templates.py --check` exits 0 and `uv run pytest -q tests/safety/test_constitution_amendment.py` exits 0; the test compares the amended text of `rules/pumpgrok-team.mdc` (clauses 2 and 8, ten-role correction), `agents/risk.md` clause 10, `docs/RISK_POLICY.md` (row 8 and section 2.4) and `.planning/PROJECT.md` (BLIND constraint) with the frozen approved text (UPG-06)
  9. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && grep -qE "Phase 9: smoke-10m events.hash before: [0-9a-f]{64}" CHANGELOG.md && grep -qF "Phase 9: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0; the active-set record may change replay output, so both values are recorded (equal if unchanged)
  10. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0 with the upgrade modules present

**Checkpoint**: a candidate is promoted and rolled back exactly under test, ineligible candidates escalate, the amendment text passes `generate-templates --check`, and live stays refused.

**Deliverables**:

- [x] `src/pumpgrok/config/upgrade_bounds.toml`: declared bounds in version-controlled config (UPG-01)
- [x] `src/pumpgrok/upgrade/` new package: content-hashed parameter sets, the promotion gate, the evidence record, exact rollback and escalation (UPG-01 to UPG-04)
- [x] Ledger event for the active parameter set in `src/pumpgrok/ledger/` (UPG-01, UPG-03)
- [x] SAFE-4 and SAFE-8 advisory BLIND handling with the blind reason in the verdict, in `src/pumpgrok/tools/safety/` (UPG-05)
- [x] Constitution amendment applied exactly as approved on 2026-10-25: `rules/pumpgrok-team.mdc`, `agents/risk.md`, regenerated prompts and agent files via `scripts/generate-templates.py`, `docs/RISK_POLICY.md`, `.planning/PROJECT.md` (UPG-06)
- [x] Frozen copy of the approved amendment text, used as the test oracle in `tests/safety/test_constitution_amendment.py` (UPG-06)
- [x] `tests/upgrade/` and `tests/safety/test_blind_advisory.py`
- [x] `CHANGELOG.md` before and after replay hash lines for Phase 9

**Plans**: 7 complete (09-01 to 09-07; 09-06 carries the risk-only clause 3 override and the content-based locators). Verification: `.planning/phases/09-bounded-paper-self-upgrade/09-VERIFICATION.md` (passed, 10 of 10 criteria).

### Phase 10: Live readiness, kept disabled

**Goal**: Live stays refused end to end: `run --mode live` exits 3 and lists the nine preconditions, no live adapter is registered, the import graph has no path from backtest, paper or upgrade modules to a live adapter, and a deferred live-readiness record states what a future decision requires.
**Depends on**: Phase 9
**Requirements**: LIV-01, LIV-02
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0 and `uv run pytest -q tests/execution/test_live_gate_fails_fast.py tests/safety/test_live_refusal_lists_nine.py` exits 0; stderr names all nine preconditions (LIV-01)
  3. `uv run pytest -q tests/safety/test_no_live_adapter_registered.py` exits 0 (LIV-01)
  4. `uv run pytest -q tests/safety/test_import_graph_no_live.py` exits 0; no import path exists from the backtest, paper or upgrade modules to a live adapter (LIV-01)
  5. `for f in src/pumpgrok/config/overlays/*.toml; do uv run python -c "import tomllib,sys; d=tomllib.load(open('$f','rb')); assert d.get('live',{}).get('enabled') is False, '$f'" || exit 1; done` exits 0 (live disabled in every overlay)
  6. `uv run pytest -q tests/safety` exits 0; the signing and custody AST guard passes and no signing or custody code was added (LIV-02)
  7. `test -f docs/LIVE_READINESS.md && grep -qi "status: deferred" docs/LIVE_READINESS.md && grep -qi "custody" docs/LIVE_READINESS.md && grep -qi "venue" docs/LIVE_READINESS.md && grep -qi "legal" docs/LIVE_READINESS.md && grep -qi "nine" docs/LIVE_READINESS.md` exits 0; the record lists the custody model, venue, legal review and nine-precondition evidence as requirements of a future decision (LIV-02)
  8. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && grep -qF "Phase 10: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0; the replay output is unchanged from Phase 9

**Checkpoint**: on a fresh checkout, `run --mode live` exits 3, the live-readiness record is present and deferred, and the canonical gate set is green.

**Deliverables**:

- [x] `src/pumpgrok/execution/live/live_gate.py`: refusal output lists the nine preconditions (LIV-01)
- [x] `tests/safety/test_no_live_adapter_registered.py`, `tests/safety/test_import_graph_no_live.py`, `tests/safety/test_live_refusal_lists_nine.py` (LIV-01)
- [x] `docs/LIVE_READINESS.md`: deferred record of custody model, venue, legal review and nine-precondition evidence (LIV-02)
- [x] `CHANGELOG.md` v3 closeout entry and the Phase 10 replay hash line

**Plans**: 3 complete (10-01 to 10-03). Verification: `.planning/phases/10-live-readiness-kept-disabled/10-VERIFICATION.md` (passed, 8 of 8 criteria). Live stays refused: exit 3, no live adapter registered, no live import reachable from the guarded roots.

## Progress

**Execution Order:**
Phases execute in numeric order: 6 -> 7 -> 8 -> 9 -> 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 6. Integrity closure | 9/9 (+ fix-up 06-01b) | Blocked: owner decisions (G-1, G-2, approved_by) | - |
| 7. Documentation upgrade | 6/6 | Complete: verified 9/9 (07-VERIFICATION.md) | 2026-10-25 |
| 8. Backtest and paper evaluation | 10/10 | Complete: verified 13/13 (08-VERIFICATION.md) | 2026-10-25 |
| 9. Bounded paper self-upgrade | 7/7 | Complete: verified 10/10 (09-VERIFICATION.md) | 2026-10-25 |
| 10. Live readiness, kept disabled | 3/3 | Complete: verified 8/8 (10-VERIFICATION.md) | 2026-10-25 |
