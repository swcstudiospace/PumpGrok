# Requirements: PumpGrok Desk v3

**Defined:** 2026-10-25
**Core Value:** The desk runs autonomously in paper mode for 2-4 weeks and produces honest, replayable reports; no code path can move real funds.

Source: owner decisions of 2026-10-25 (see PROJECT.md Key Decisions V3-1..V3-4), the repo-grounded audits of 2026-10-25, and the deferred items of `.planning/milestones/v2-MILESTONE-AUDIT.md`.

## v3 Requirements

### Integrity (INT)

- [x] INT-01: Money crosses every module boundary as integer lamports or base units; Decimal appears only for ratios. The float money fields in ledger/export.py, engine/models.py, engine/analyzer.py, engine/exits.py, engine/reputation.py and engine/tune.py are converted, and a static test rejects float money fields under src/pumpgrok.
- [x] INT-02: Corrupt or missing state fails closed with a typed error, never a silent default: the ledger peak skip in ledger/reducer.py, _initial_equity returning 0 in supervisor/seat_task.py, and genesis equity 'or 0' in supervisor/lifecycle.py each raise and have a regression test.
- [x] INT-03: The daily-loss halt uses integer arithmetic, and a non-positive day-start equity is a failed check, not zero loss.
- [x] INT-04: The SOL-to-lamports conversion has one implementation in core/ used by risk_budget, cli and approvals; the other copies are removed.
- [x] INT-05: os.urandom is allowed only at the approval-id and binding-key composition roots, enforced by the static guard; production id and RNG factories never fall back to the replay seed DEFAULT_SEED.
- [x] INT-06: The live gate reads time only through the injected clock (R27); gate evaluation is byte-identical under a fixture clock.
- [x] INT-07: Two feature-lineage review fixes are closed or proven present: a failed replay append or verify removes the replay ledger (WR-07, commit 4c19fd9), and the stored venue fee on the ledger-mark fallback scales with remaining units after a partial sell (commit 76975bb). Each has a regression test that fails before the fix.
- [x] INT-08: The longest functions are split into stage functions with unchanged behavior: paper_adapter _place_buy (about 224 lines), _place_order (about 95) and scheduler _replay_cycles (about 112). Replay ledger hashes are unchanged, or any intentional change is recorded in CHANGELOG with before and after hashes.
- [x] INT-09: Trailing-stop peaks survive a serve restart (v2 tech debt: peaks are held in memory).
- [x] INT-10: The bonding-curve layout is probed read-only against live mainnet accounts (R65). The result is recorded as VERIFIED with decoded fixtures, or as ASSUMED with the exact probe error. While ASSUMED, entries stay fail-closed.

### Documentation (DOC)

- [x] DOC-01: CLAUDE.md at the repository root maps the codebase: purpose, stack, layout, commands, architecture and data flow, conventions, GSD artifact locations, safety rules and known gaps. Every statement cites a file.
- [x] DOC-02: AGENTS.md drops the stale GSD research dump and placeholder blocks, keeps the rules index, verifies every command, and links CLAUDE.md instead of duplicating it.
- [x] DOC-03: README, ARCHITECTURE, SETUP, skills/replay-and-backtest/SKILL.md, plugin version statements and docs/VENDOR_PIN.md match the code. Every contradiction from the 2026-10-25 docs audit is corrected, and each change appears in CHANGELOG.md.
- [x] DOC-04: Historical design records under docs/ carry a banner stating they describe the design at the time, not current behavior.

### Backtesting (BT)

- [x] BT-01: Each replay or backtest run writes a run manifest containing the whole-dataset digest (every file in the dataset directory), the seed, the FilterSettings hash, the parameter-set hash and the code version. The run id derives from that manifest.
- [x] BT-02: Replay results expose per-fill price, venue fee, network cost, latency, filled fraction and outcome, not only the outcome.
- [x] BT-03: A holdout reserves the final 20 percent of a dataset's time window and is never used for tuning; walk-forward folds are used for tuning; each report names the split identifiers.
- [x] BT-04: Every parameter trial in a search is recorded. A search above 20 trials is flagged and ineligible for promotion; a search above 50 trials is rejected.
- [x] BT-05: Metrics are return, maximum drawdown from a running peak, a Sharpe-style ratio whose annualization is stated in code, win rate, trade count, exposure and turnover. Each metric states its inputs and assumptions, and no output uses expected-return language.
- [x] BT-06: A 'pumpgrok backtest' verb runs a parameter set over a recorded dataset with the holdout and writes a report containing fees, slippage, data window, trial count and holdout id. Two runs with identical inputs are byte-identical.
- [x] BT-07: The in-sample grid search in engine/tune.py is replaced by the holdout-aware harness; no second search engine remains.

### Paper evaluation (PAP)

- [x] PAP-01: Backtest results and paper ledger trades share one result schema, so they compare over the same window.
- [x] PAP-02: A divergence check uses the D7 defaults (2 percentage points absolute return gap, or 0.5 Sharpe gap) over the same window. A breach raises an alert and blocks promotion.
- [x] PAP-03: Autonomous paper operation is verified end to end on recorded datasets under the human-set autonomous-paper level, and manual-ticket never runs upgrades.

### Bounded upgrade (UPG)

- [x] UPG-01: Parameter sets are versioned by content hash. Declared bounds (ranges) live in version-controlled config, and the active set is recorded in the ledger.
- [x] UPG-02: A candidate is promoted only if it is within bounds, passes the holdout, keeps divergence within threshold, comes from a search of at most 20 trials, and runs under the human-set autonomous-paper level.
- [x] UPG-03: Each promotion records its evidence (candidate hash, backtest run id, holdout id, divergence result, trial count, bounds). One operation rolls back to the exact prior version, verified by a test.
- [x] UPG-04: An out-of-bounds or ineligible candidate is not promoted and produces a decision request for a human (escalation and journal note).
- [x] UPG-05: SAFE-4 and SAFE-8 report BLIND as advisory while no paid RPC provider is recorded, with the blind reason written into the verdict. All other BLIND results remain KILL. The rule reverts to required when a provider is recorded.
- [x] UPG-06: The constitution amendment approved on 2026-10-25 is applied exactly as approved: rules/pumpgrok-team.mdc (clauses 2 and 8, and the ten-role correction), agents/risk.md clause 10, regenerated prompts and agent files, docs/RISK_POLICY.md (row 8 and section 2.4), and .planning/PROJECT.md (BLIND constraint and strategy out-of-scope). generate-templates --check passes.

### Live readiness (LIV)

- [x] LIV-01: Live stays refused. 'run --mode live' exits 3 listing the nine preconditions, no live adapter is registered, and an import-graph test shows no path from backtest, paper or upgrade modules to a live adapter.
- [x] LIV-02: A live-readiness record lists what a future decision requires (custody model, venue, legal review, nine-precondition evidence) and is recorded as deferred. No signing or custody code is added.

### Process (PRC)

- [x] PRC-01: Each phase closes with make lint, make typecheck, make test, ./scripts/check.sh, the replay smoke command, and a .receipts/<seat>/<task>.json receipt for each completion claim.
- [x] PRC-02: Phase branches follow AGENTS.md (bot-0N-<seat>/phase-<n>-<unit>), PRs are draft only, and nothing merges to main without approval. Closed 2026-10-26 with owner-approved deviations: ready PR and squash merge after green CI and Greptile 5/5 (PROJECT V3-5).

## Out of Scope

| Feature | Reason |
|---------|--------|
| Live order placement, signing, custody, or any live adapter | Needs custody model, venue and legal decisions; constitution clause 1 and PROJECT D4 |
| External historical data or new data vendors | Data policy: self-recorded only (D8, AF-10) |
| Paid RPC procurement or spend | No provider approved; user decision |
| PumpPortal trade-stream key | Default no (R45); user decision |
| New signal families or alpha research | Only bounded parameter promotion is in scope |
| Telegram live verification, G-4 consumer acknowledgements, bot-06 exit roster change | Human actions outside the code |
| Manual-ticket exit approval path (PAPER-007) | Deferred by owner decision 2026-10-23 |
| Web UI, multi-tenant, billing | Spec non-goals |

## Traceability

Which phases cover which requirements. Populated during roadmap creation (`.planning/ROADMAP.md`); each requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INT-01 | Phase 6 Integrity closure | Complete |
| INT-02 | Phase 6 Integrity closure | Complete |
| INT-03 | Phase 6 Integrity closure | Complete |
| INT-04 | Phase 6 Integrity closure | Complete |
| INT-05 | Phase 6 Integrity closure | Complete |
| INT-06 | Phase 6 Integrity closure | Complete |
| INT-07 | Phase 6 Integrity closure | Complete |
| INT-08 | Phase 6 Integrity closure | Complete |
| INT-09 | Phase 6 Integrity closure | Complete |
| INT-10 | Phase 6 Integrity closure | Complete |
| PRC-01 | Phase 6 Integrity closure | Complete |
| PRC-02 | Phase 6 Integrity closure | Complete |
| DOC-01 | Phase 7 Documentation upgrade | Complete |
| DOC-02 | Phase 7 Documentation upgrade | Complete |
| DOC-03 | Phase 7 Documentation upgrade | Complete |
| DOC-04 | Phase 7 Documentation upgrade | Complete |
| BT-01 | Phase 8 Backtest and paper evaluation | Complete |
| BT-02 | Phase 8 Backtest and paper evaluation | Complete |
| BT-03 | Phase 8 Backtest and paper evaluation | Complete |
| BT-04 | Phase 8 Backtest and paper evaluation | Complete |
| BT-05 | Phase 8 Backtest and paper evaluation | Complete |
| BT-06 | Phase 8 Backtest and paper evaluation | Complete |
| BT-07 | Phase 8 Backtest and paper evaluation | Complete |
| PAP-01 | Phase 8 Backtest and paper evaluation | Complete |
| PAP-02 | Phase 8 Backtest and paper evaluation | Complete |
| PAP-03 | Phase 8 Backtest and paper evaluation | Complete |
| UPG-01 | Phase 9 Bounded paper self-upgrade | Complete |
| UPG-02 | Phase 9 Bounded paper self-upgrade | Complete |
| UPG-03 | Phase 9 Bounded paper self-upgrade | Complete |
| UPG-04 | Phase 9 Bounded paper self-upgrade | Complete |
| UPG-05 | Phase 9 Bounded paper self-upgrade | Complete |
| UPG-06 | Phase 9 Bounded paper self-upgrade | Complete |
| LIV-01 | Phase 10 Live readiness, kept disabled | Complete |
| LIV-02 | Phase 10 Live readiness, kept disabled | Complete |

**Coverage:** v3 requirements: 34 total, 34 mapped, 0 unmapped
