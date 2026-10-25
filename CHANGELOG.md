# Changelog

All notable changes to PumpGrok are recorded here. The format follows Keep a Changelog.

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
