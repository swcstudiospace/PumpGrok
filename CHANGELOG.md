# Changelog

All notable changes to PumpGrok are recorded here. The format follows Keep a Changelog.

## [Unreleased] - v3 follow-up: one identity, one valuation, constitution bytes

### Changed

- Parameter-set identity: `param_set_hash` is the normalized CandidateParams content hash, the value the search winner, promotion gate, evidence and active-set ledger carry. Whitespace and key order no longer change it. Every run id changes once, because the identity input changed. `--params` files with keys outside CandidateParams, or float leaves, are refused with a usage error.
- Selection valuation: the search objective uses the report's rule (cash plus open positions at mark, else at cost basis) from `backtest/equity.py`, which the report also calls. A buy-and-hold candidate is no longer scored as a loss in selection, so search scores and winners can change.
- Constitution wording: clause 10 quotes now match the amendment bytes (ASCII double quotes, en dash U+2013 kept) in the prompt core, the generated agent files, RISK_POLICY, ROSTER and the browser-ops skill. The frozen oracle test takes its clause 10 authority from `.planning/AMENDMENT-2026-10-25.md`.

## [Unreleased] - v3 Phase 10: live readiness, kept disabled

### Added

- LIV-01 refusal proof: `pumpgrok run --mode live --once` exits 3 with all nine preconditions in R21 order on stderr (tests/safety/test_live_refusal_lists_nine.py).
- LIV-01 empty-registry proof: build_adapter returns a PaperAdapter only; no live adapter symbol or registry entry is exported (tests/safety/test_no_live_adapter_registered.py).
- LIV-01 import-graph proof: no transitive import path from the backtest, paper-adapter, upgrade, supervisor, or CLI roots reaches the live adapter module (tests/safety/test_import_graph_no_live.py).
- LIV-02 overlay-disabled proof: every overlay under src/pumpgrok/config/overlays ships with live disabled (tests/safety/test_live_disabled_overlays.py).
- LIV-02 deferred record: docs/LIVE_READINESS.md records the custody model, the venue, the legal review, and the nine-precondition evidence, each with owner human and status deferred. The desk stays paper-only and claims no measured readiness.

### Verified

- Phase 10: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
- Phase 10: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
- No task in this phase changed replay bytes: the record and all phase proofs are docs and safety tests only, with no product code change.

## [Unreleased] - v3 Phase 9: bounded paper self-upgrade

### Added

- UPG-01 adds content-hashed parameter sets within version-controlled bounds (src/pumpgrok/config/upgrade_bounds.toml). An out-of-bounds value fails with a typed error and is never clamped.
- UPG-02 adds `evaluate_candidate`, a gate that checks in fixed order: bounds, trial limits, autonomy level, holdout, then the Phase 8 divergence check. The first failure is the typed reason. `record_promotion` does not require `promotion_eligible` or check `blocks_promotion`, so gate enforcement is by convention.
- UPG-03 adds `record_promotion`, which writes an evidence manifest under var/upgrade/promotions/ and refuses different evidence at the same hash without recording anything. `record_active_set` accepts any `by` value, needs no gate verdict and writes a ConfigChanged row with no evidence file. `restore_active_set` writes the prior hash back as a new ConfigChanged row; it does not check the caller and does not verify stored content for that hash.
- UPG-04 escalates an ineligible candidate through the existing Escalation channel with a decision request. `escalate_candidate` is a library function with tests; no production code calls it, so it runs only when a caller invokes it. It never writes an active-set row.
- UPG-05 treats BLIND on SAFE-4 and SAFE-8 as advisory while no paid RPC provider is recorded (PUMPGROK_PAID_RPC_PROVIDER). Setting the provider restores the KILL contract.
- UPG-06 applies the owner-approved constitution amendment of 2026-10-25 to the rules, the desk skill, the agent prompts and the risk policy, with a frozen oracle test. The risk seat alone carries the amended clause 3.

### Verified

- Phase 9: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
- Phase 9: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
- Correction after merge (2026-10-27): the UPG-02 and UPG-03 wording above implied operator-path gating, evidence for active-set changes and a verified restore; promotion, rollback, escalation and active-set record/restore are library-only in this milestone, with no production caller and no operator verb.

## [Unreleased] - v3 Phase 8: backtest and paper evaluation

### Added

- BT-01 adds the backtest run manifest holding the whole-dataset digest, seed, FilterSettings hash, parameter-set hash and code version, with the run id derived from that manifest.
- BT-02 exposes per-fill price, venue fee, network cost, latency, filled fraction and outcome on replay results.
- BT-03 reserves the final 20 percent of a dataset time window as holdout, never used for tuning, with walk-forward folds over the pre-holdout region and named split identifiers.
- BT-04 records every parameter trial; a search above 20 trials is flagged ineligible for promotion and above 50 trials is rejected with a typed error.
- BT-05 bounds metrics to return, maximum drawdown from a running peak, a Sharpe-style ratio with annualization stated in code, win rate, trade count, exposure and turnover, with no expected-return language.
- BT-06 adds the pumpgrok backtest verb running a parameter set over a recorded dataset with the holdout, printing a byte-identical deterministic report.
- BT-07 replaces the engine grid search with the holdout-aware harness as the single search engine.
- PAP-01 shares one result schema between backtest results and paper ledger trades over the same window.
- PAP-02 checks divergence on the 2 percentage point absolute return gap and 0.5 Sharpe gap defaults, alerting and blocking promotion on breach.
- PAP-03 verifies autonomous paper end to end on the recorded smoke and smoke-10m datasets at the human-set autonomous-paper level, with manual-ticket never running an upgrade and no backtest-to-live path.

### Verified

- Phase 8: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
- Phase 8: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
- Phase 8 correction: the first harness scored candidates with a hash digest. It was replaced before the phase closed: candidates now rank by net realized lamports from replayed fills, and the report shows measured fees, slippage and metrics. Per-fill fields are held in memory only, so the replay ledger bytes and the hash are unchanged.

## [Unreleased] - v3 Phase 7: documentation upgrade

### Changed

- DOC-01 adds the CLAUDE.md codebase map at the repository root.
- DOC-02 trims AGENTS.md to its rules, with the offline verify script scripts/verify_doc_commands.sh.
- DOC-03 corrects README, ARCHITECTURE, SETUP, the replay skill and the four plugin manifests (version 0.1.0) to match the code, with docs/VENDOR_PIN.md recording the retired oracle.
- DOC-04 banners historical design records, with consistency and banner tests under tests/docs.

### Verified

- Phase 7: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d

## [Unreleased] - v3 Phase 6: integrity closure

### Changed

- Money crosses module boundaries as integer lamports or base units; Decimal is used only for ratios. Ledger export writes exact decimal strings (INT-01).
- Missing or corrupt state fails closed with CorruptState instead of defaulting to zero, and a seat whose genesis equity is unreadable latches at construction (INT-02).
- The daily-loss halt uses integer arithmetic; a non-positive start equity fails the check instead of reading as zero loss (INT-03).
- One SOL-to-lamports conversion lives in core/units.py. The live gate takes now from its caller and reads no wall clock (INT-04, INT-06).
- Randomness is confined to the approval-id and binding-key roots, enforced by the static guard. Production id and RNG factories take an explicit seed; DEFAULT_SEED stays in replay code (INT-05).
- Long paper-adapter and replay-cycle functions are split into stage functions with unchanged behaviour (INT-08).
- Trailing-stop peaks are restored from the ledger after a serve restart, through existing event types only (INT-09).
- scripts/probe_curve_layout.py is a read-only curve layout probe. LAYOUT_STATUS stays ASSUMED, so entries stay fail-closed (INT-10). The probe ran with no account configured and made no RPC call.

### Verified

- The WR-07 replay ledger cleanup and the partial-sell venue fee scaling (INT-07) were already on main; regression tests were added.
- Phase 6: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
- Phase 6: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d

### Review: Omega CI runner migration (commits 5b5d6a1, 9772655)

- Every job moved from GitHub-hosted runners to the self-hosted pool [self-hosted, linux, x64, omega-ci]. This reverses the earlier stance that self-hosted runners are not used, so it is a policy change and needs owner sign-off.
- Fork pull requests are skipped on every job, so fork code never reaches the pool. Same-repository branches do run on it, so the trust boundary is who can push a branch.
- Trivy moved from the SHA-pinned aquasecurity/trivy-action to the binary baked into the runner image. The binary is not version-pinned in the workflow, and its vulnerability database is fetched on every run.
- Ephemerality of pool runners is not verified in this repository. Job-to-job state on a persistent runner is a risk until it is confirmed.
- ci/tests/test_security_workflows.py no longer forbids self-hosted runners. Its Trivy severity, exit-code and ignore-unfixed assertions remain.

### Owner closure (2026-10-26)

- Phase 6 closes with two owner-approved deviations (PROJECT V3-5; approved_by human:SomeRandmGuyy).
- Criterion 17: G-1 (170 foreign-owned paths) and G-2 are waived in CI for the Phase 6 pull request only, through a PR-number condition in .github/workflows/gates.yml. run_all.py still exits 1 locally on G-1.
- Criterion 16: the phase pull request is ready for review, not draft. It merges to main through ultrathink-ship after CI is green and Greptile reaches 5/5 with no open threads.
- The 2026-10-25 re-own decision is superseded. The paths stay foreign-owned until a follow-up change, and the waiver stays on main until a cleanup change removes it.

### Review fixes (PR 16, Greptile round 1)

- Paper ledger: the genesis equity is written once, when a paper ledger is first opened by a CLI verb or the composition root. A ledger with events but no genesis now fails closed with CorruptState instead of taking the configured budget as its base.
- Active sets: recording stores the overrides under their content hash in the operator ledger. Paper runs and the checkpoint verdict apply the restored filter and exits. The candidate type moved to backtest/candidate.py to break an import cycle; evaluate re-exports it.
- Backtests: a candidate hash equals its ParamSet hash, so the gate accepts real search winners. Net scoring counts each fee once (recorded cash changes minus refused-attempt fees). Folds are cut on distinct timestamps and raise ValueError when there are too few. The holdout is replayed once per backtest. Identical backtests cannot run at once (run-directory lock). Float parameters are a usage error (exit 1).
- Backtest identity: the report identifies the evaluated filter, exits, risk budget and limits. Backtests evaluate the desk-default risk budget and limits, not the operator's configured overlay; that is recorded as a decision.
- Promotion evidence: a second record with different content at the same candidate hash raises PromotionEvidenceConflict. The manifest is created with an exclusive open.
- Startup: PUMPGROK_PAID_RPC_PROVIDER is a registered non-setting name.
- Docs and checks: the CLAUDE.md codebase map names current modules; verify_doc_commands.sh rejects shell operators before execution; the curve probe records VERIFIED only for the expected program owner and account discriminator; the analyzer SOL conversion uses core.units.
- Tests: the import-graph check walks child modules; the autonomy e2e test checks the policy gate directly.
- Round 2: the holdout and the paper window share one end rule (the next float after the last holdout ledger row, including settling orders), so both sides count the same fills. The report's window_end_utc is that last holdout row. An empty holdout ledger is a ConfigError.
- Round 2: promotion evidence is published by a hard link from a complete temporary file in the same directory, so a reader never sees a partial manifest. Manifests are created with owner-only mode (0600).

Follow-ups, not changed in this cycle: default-genesis fallbacks remain in execution/paper_adapter (_fold_state), ledger/reconcile (_genesis) and a supervisor docstring; the replay runtime still fixes autonomy to autonomous-paper; a forced-close fill uses a placeholder decision id until core/adapter.py accepts an empty decision id; the CI waiver is removed by a cleanup change after the merge.

## [Unreleased] - Audit fixes

### Fixed

- Escalation payloads keep the bound seat and source; caller keys cannot override them.
- The key-bearing guard covers api_key, apikey, secret and password; endpoints must use TLS.
- camelCase secret names and full PEM private key blocks are masked in logs.
- A kill-switch re-engagement after a clear writes its own set row; flatten continues past
  per-position failures and logs the cause through the redacted logger.
- A restart-exhausted seat stays latched when the ledger is unreadable.
- RPC curve prices are refused per snapshot source; exposure cost basis follows partial sells.
- Equity uses one SOL-to-lamports rule (ROUND_HALF_UP) across scheduler, engine and read tools.
- A corrupt reputation book leaves a durable degraded marker; the book is loaded at startup.
- NetworkBlocked cannot be swallowed by broad except clauses in tests.
- An exit latch restored from the ledger re-appends its HaltSet before any seat runs; every cycle
  retries it until it lands.
- The RPC entry gate refuses buys only; a stop-loss sell is not refused as ASSUMED-layout data.
- A failed degraded-marker write refuses startup instead of starting with a healthy empty book.
- A kill-switch observation that races a human clear is dropped instead of re-engaging the switch.
- Buys are refused desk-wide while the EXIT seat is latched, even before its HaltSet lands.

## [Unreleased] - Operator surface fixes

### Fixed

- Live confirmation expiry is recorded in UTC; naive, past and out-of-range expiries are refused.
- --day and --week are validated as dates.
- Notify errors never echo webhook URLs; a failed console or alert-file write no longer blocks
  network sinks.
- The gateway logs at the configured level, applies request timeouts, compares bearer tokens as
  bytes, and returns a parse error for deeply nested JSON.
- Hermes scripts: verify-isolation reports failures, bootstrap dry-run writes nothing, and the cron
  installer refuses unreadable or blank prompts before creating any job.
- The go-live quick start computes a future expiry; the live-confirm test pins the CLI clock.

## [Unreleased] - Gate trust hardening

### Fixed

- Gate jobs replace ci/gates and restore ownership.yaml from the base ref; gate scripts run with
  python3 -P. Scanner jobs restore only the settings files, so PR-added ci/security source is scanned.
- Scanner settings come from the base ref; push scans take their base from the event and fall back
  to a broader scan when the base is unreachable.
- check_rollback matches case-insensitively and recognises --mode=live.

## [Unreleased] - Phase 1: Foundation (2026-10-21)

### Added

- `uv_build` src-layout package `pumpgrok` (Python 3.12) with a committed `uv.lock`; `uv sync --frozen`
  is the install path.
- Layered settings with startup guards: profile overlays (`dev`, `paper`, `live`), an operator
  overlay via `PUMPGROK_CONFIG`, refusal of unknown `PUMPGROK_*` names, forbidden key-like names
  and key-bearing values, and mode resolution `--mode` > `PUMPGROK_MODE` > TOML.
- Hash-chained append-only ledger with a verify step, and a deterministic replay clock, seeded RNG
  and fixture loader that checks every listed digest before any ledger file exists.
- Replay paper cycle: `pumpgrok run --mode paper --once --replay <dir>` judges each fixture tick as
  a candidate carrying its recorded evidence, appends the verdict `JournalNote`, lets the sniper seat
  place granted BUYs through `exec.place` (risk and PaperAdapter approve or veto), verifies the chain
  and exits 0. Only seats with an `exec.place` grant trade. Kill-switch flatten closes open replay
  positions through PaperAdapter. Exit rules (stop-loss 30%, take-profit 120%, trailing stop 35%,
  max hold 3600 s; `config/settings.py` `ExitsSettings`) run each replay and serve cycle through the
  ported `PositionWatcher`; a fired rule sells through the exit seat's `exec.place` with
  `exit_reason` set, and only the exit seat may send one.
- `pumpgrok doctor`: subsystem health report. Exit 0 whenever settings are valid.
- Redacted JSON logs with correlation IDs carried in context variables.
- Tool and registry core (`core/`), including the `ToolRegistry` invariants and the live-write refusal.
- Gates G-1..G-7 under `ci/gates/` with self-tests, `ci/gates/run_all.py`, the gate workflows and
  pre-commit hook.
- Ownership manifest `ownership.yaml`, ten seat roster and tool rosters, and the generated event
  schemas under `contracts/events/`.
- Multi-stage container image: `python:3.12-slim` build and runtime stages, `uv` 0.13.4, non-root
  user, `PUMPGROK_PROFILE=paper`, the smoke replay fixture, a `pumpgrok doctor` healthcheck,
  `SIGTERM` stop signal, and the replay as its default command.
- `docker-compose.yml`: a one-shot `pumpgrok` service with no restart policy, optional `.env`
  injection, loopback port binding, json-file logging and a 512M memory limit.
- Documentation in programming-desk shape: `AGENTS.md`, `SECURITY.md`, `docs/quality-gates.md`,
  `docs/desk-operating-model.md`, `docs/cross-bot-protocol.md`, `docs/VENDOR_PIN.md`.

### Changed

- `scripts/check.sh` no longer checks vendor paths. The vendor pin is checked through
  `docs/VENDOR_PIN.md`, the emoji scan covers `.planning/**`, and a placeholder-organisation check
  allows the organisation placeholder only in the five manifest and setup files that still carry it
  until STRUCT-007.
- Planning reports use ASCII status words in place of symbol glyphs.

### Removed

- Six tracked `*.pyc` build artifacts under `tests/` and `tools/` are untracked.
- `issues/tissue.json`, a legacy file with no inbound references.

## Phase 2: Restructure (2026-10-21)

### Added

- Vendor engine ported into `src/pumpgrok/engine/` (analyzer, monitor, pipeline,
  scoring, exits, watcher, reputation, tune, alerts, models) with
  characterization tests pinning vendor behaviour during the move.
- Read-only tool namespaces under `src/pumpgrok/tools/` (agents, desk, exec,
  journal, market, notify, onchain, portfolio, risk, safety, social).
- CLI verbs exposing the ported engine and tool flows through `pumpgrok`.
- Rewritten skills with `bots` and `gates` frontmatter on every skill directory.

### Changed

- Vendor code is consumed through the ported modules; root `tools/` stays as the
  oracle until the census empties at the end of Phase 5.

## Phase 3: Tools and Skills (2026-10-21)

### Added

- Dotted, typed tool layer with least-privilege manifests and tool rosters
  under `contracts/tool-rosters/`.
- Desk gateway projecting tools to seats with side-effect budgets.
- Twelve new skills, bringing the set to 35; every skill carries `bots` and
  `gates` frontmatter (STRUCT-007 invariant).
- Event and tool contracts under `contracts/events/` and `contracts/README.md`.

### Changed

- Money stays integer lamports and base units across the new layers; no `float`
  money fields outside the exempted vendor-parity engine code (TOOL-008).

## Phase 4: Paper Trading and Autonomy (2026-10-22)

### Added

- Curve-faithful paper fills via the paper adapter (`getTokenLargestAccounts`
  holder path, Jupiter Swap V2 order quotes, bonding-curve price derivation).
- Risk engine with limits, breaker set, and kill switch; deterministic replay
  (seeded RNG, fixture digests, read-only seat cycles) and the supervised
  ten-seat loop under `src/pumpgrok/supervisor/`.
- Daily and weekly ledger-backed reports (`pumpgrok report --daily/--weekly`).
- Live refusal: `pumpgrok run --mode live` exits 3 with nine ordered R21
  precondition lines; human-only `pumpgrok live confirm` records the
  HMAC-signed confirmation without changing the effective mode.

### Removed

- `vendor/grokbot-pumpfun/` retired; the ported modules are the implementation
  of record.

## Phase 5: Hardening (in progress)

### Added

- Nine operator runbooks under `docs/runbooks/` (setup, engine, start/stop,
  kill switch, breaker reset, outage, rollback, reading reports, go-live).
- Machine-checked doc contracts: `tests/docs/test_runbook_commands.py`
  (fenced-bash allowlist) and `tests/docs/test_changelog_phases.py`
  (Phase 1-5 heading coverage).
- `AGENTS.md` rules index pointing cloud agents at the normative rule files.

### Changed

- `docs/runbooks/setup.md` rewritten: runtime state under `./var/`, no
  workspace-oracle claims, environment copy described in prose.
