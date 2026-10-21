# Phase 1: Foundation - Context
**Gathered:** 2026-10-21
**Status:** Ready for planning
**Mode:** Seeded from design docs (discuss replaced; decisions locked by R16-R49)

<domain>
## Phase Boundary
Runnable, gated, empty desk: foundation subsystems as skeletons plus a skip-only replay cycle, all gates green, no network.

Requirement ids (19, = ROADMAP Phase 1 list): FOUND-001, FOUND-002, FOUND-003, FOUND-004, FOUND-005, FOUND-006, FOUND-007, FOUND-008, FOUND-009, FOUND-010, FOUND-011, FOUND-012, FOUND-013, STRUCT-001, STRUCT-008, OBS-001, OBS-002, SEC-001, SEC-002.
</domain>

<decisions>
## Implementation Decisions

### Locked
- **Toolchain (FOUND-001, 002):** pyproject `requires-python >=3.12,<3.13`, uv_build `module-root = "src"`, script `pumpgrok = "pumpgrok.cli:main"`; commit `.python-version` (3.12) and `uv.lock`; `mypy --strict src/` without prometheus or respx overrides (V-5); pytest `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"` (V-9); audit uses `uv export --no-emit-project` (V-4).
- **Container (FOUND-003):** non-root multi-stage image, uv 0.13.4 (V-2), `PUMPGROK_PROFILE=paper`; HEALTHCHECK runs `pumpgrok doctor`; compose `env_file` with `required: false`.
- **Config (FOUND-004, STRUCT-008, SEC-002):** pydantic-settings, prefix `PUMPGROK_`, `__` nesting. Precedence: CLI > env > `PUMPGROK_CONFIG` file > overlay `src/pumpgrok/config/overlays/{dev,paper,live}.toml` (`PUMPGROK_PROFILE`, default paper) > defaults. Mode: `--mode` > `PUMPGROK_MODE` > TOML `execution.mode` (R30). Every overlay has `[live] enabled = false`. Exit 1, values never printed: unknown key, bad type, unknown profile, forbidden names (PRIVATE_KEY, SECRET_KEY, SEED, MNEMONIC, PHANTOM, WALLET_SECRET, KEYPAIR; `replay.seed` exempt), URLs with `api-key=`, `key=` or `token=`. No Jito or wallet-key field (M-10); no root `config/`.
- **Risk and money (R20, R28):** `RiskBudget` has the nine keys of interfaces.md:728; `daily_loss_halt_fraction` capped at 0.05 (INV-C-06); money is `int`.
- **Live gate (R21):** `LiveGate.check()` returns the nine ids in order. `run` prints each unmet id as `[ ] n id reason` and exits 3 before other work. Ids 3, 4, 7, 9 need ledger or confirmation data not yet present: unmet, fail closed. Id 8 is always unmet. `LiveAdapter` stub raises `LiveGateError` after appending `LiveWriteAttempted` (interfaces.md:611).
- **Ids and logging (R29, OBS-001, OBS-002):** `IdFactory(clock, rng)` emits a hand-rolled Crockford ULID (interfaces.md:157-172). CorrelationId is the plain ULID root; children `<ulid>.<n>`. `uuid` banned. JSON log per FOUNDATION_STACK 5.1 with a RedactionFilter; `PUMPGROK_LOG_JSON=false` only in dev.
- **Core (FOUND-005):** `core/{interfaces,registry,ids,approvals,__init__}.py` per interfaces.md 2.1-2.5 and 923-. `ToolRegistry.find` raises `LiveGateError` for any LIVE_WRITE spec (I3) and audits refusals (I4). `canonical_json` rejects floats; do not copy interfaces.md:253 `default=str`.
- **Ledger (FOUND-013, R26, R28, R32):** `ledger/{store,events}.py` per paper-engine.md 3.2-3.3 (schema and hash rule); `BEGIN IMMEDIATE` appends; genesis prev_hash 64 zeros; 18 CamelCase models; `atomic_write` tmp+fsync+os.replace. Replay ledgers are recreated each run.
- **Replay (FOUND-012, R27):** `replay/clock.py` (WallClock, FixtureClock), `rng.py` (`make_rng`, the only RNG constructor), `fixtures.py` (sha256 manifest check; mismatch exits 4, no ledger; INV-R-30).
- **Skip cycle and doctor (FOUND-013, R37):** `run --mode paper --once --replay tests/fixtures/replay/smoke` runs the gate, reads fixture events, appends one JournalNote (`source=replay`, cycle ULID) and exits 0. `run` without `--once --replay` exits 5. `doctor` marks absent subsystems `not-yet-implemented` (warning, exit 0).
- **Ownership and gates (FOUND-006, 007, 010):** `ownership.yaml` names `bot-00-chief` .. `bot-09-journal`; rules from ROSTER.md:427-840 amended by R36; last match wins; G-1 self-test walks `git ls-files`. Ported `ci/gates/*.py` with FOUNDATION_STACK sec 4 constants: `TOOL_NAME_RE = ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`, `SEAT_RE = ^bot-0[0-9]-[a-z-]+$`, roster 8..15, six G-3 trading patterns. `.receipts/<seat>/.gitkeep` x10; gates.yml, security-pr.yml, ci.yml.
- **Contracts and prompts (FOUND-008, 009):** `contracts/` per ROSTER.md sec 8 (R35 sizes); 18 `events/<snake>.schema.json` generated from `ledger/events.py`; `prompts/` sources with ported scripts; `agents/*.md` keep agents/chief.md:1-17 frontmatter.
- **Desk docs (FOUND-011):** AGENTS.md desk rules index above line 1, GSD marker blocks verbatim; SECURITY.md key-custody line (R40); CHANGELOG.md; docs/quality-gates.md; docs/desk-operating-model.md; docs/cross-bot-protocol.md; levels `research | paper` only.
- **Hygiene, secrets, harness (STRUCT-001, SEC-001, FOUND-012):** `git rm --cached` the six tracked `*.pyc`; delete `issues/tissue.json`; `docs/VENDOR_PIN.md` (409e74c); `.gitignore` per FOUND-007 plus `.planning/research/.cache/`; `scripts/check.sh` rewritten. `.env.example` placeholders only; no PumpPortal key (R45), lite-api URL (R44) or wallet key. `tests/conftest.py` blocks httpx and `websockets.connect`; `tests/harness/faults.py` FaultInjector.

### Claude's Discretion
- **Container command (conflict):** SC4 needs a healthy running container; no supervisor before Phase 4. Default CMD `doctor --hold` (holds until SIGTERM). Orchestrator approves or relaxes SC4.
- **Dependencies:** declare only imports (pydantic, pydantic-settings, httpx, websockets, pyyaml); defer tenacity (Phase 2) and prometheus-client (Phase 5).
- Exit codes: 0 ok, 1 config, 2 ledger inconsistent (reserved), 3 live refused, 4 corrupt fixture, 5 not implemented. `PUMPGROK_EXECUTION__MODE` is a startup error.
- Skip JournalNote: `seat="desk"`, `note_kind="note"`; MIGRATION_MAP's `note_kind: cycle` is not in the enum.
- Open: design hash omits `idempotency_key`; recommend adding before the first ledger write.
- `your-org` remains in plugin.json:8,11 and SETUP.md:16-17; check.sh warns via allowlist until STRUCT-007.
- REQUIREMENTS test paths win over SAFETY_INVARIANTS. `[live] enabled` is a marker, not a precondition. Live stub moves to Phase 1 (INV-C-03).
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `hermes/profiles.yaml:18-24` forbidden keys; `rules/pumpgrok-team.mdc:28,30,34` constitution bytes; `vendor/grokbot-pumpfun/src/state.py:76-89` atomic writer; `vendor/grokbot-pumpfun/src/models.py:286-306,400-416` Jito and wallet fields (delete).
- programming-desk (shape only, never imported): `ci/gates/check_secrets.py:29`, `check_ownership.py` `_match`, `ci/tests/test_gates.py`, `scripts/assemble-prompts.sh`, `scripts/generate-templates.py`, `gates.yml`, `security-pr.yml`.

### Established Patterns
- AGENTS.md is 335 lines, not 644 as briefed; 7 GSD marker blocks (14 marker lines), kept verbatim.
- Absent today: pyproject.toml, .gitignore, .python-version, uv.lock, Makefile, Dockerfile, ci/, contracts/, prompts/, tests/fixtures/.
- `tests/test_tools_cli.py` (unittest) must pass until Phase 2 removes `tools/`.

### Integration Points
- Phase 2 consumes `core/`, `replay/`, `config/`; Phase 4 builds the reducer on `ledger/store.py`.
</code_context>

<specifics>
## Specific Ideas
(a) Verification is automated: every success criterion is a command; no live network; fixtures recorded or hand-authored.
(b) Checkpoint: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`, `make lint typecheck test audit` exits 0, and the sqlite count of `JournalNote` rows with `source='replay'` prints `1`.
(c) Fixture: `tests/fixtures/replay/smoke` only.
</specifics>

<deferred>
## Deferred Ideas
- Phase 2: engine port, read-only tools, RPC client, SEC-003, STRUCT-002..007. Phase 3: tool layer, gateway, skills.
- Phase 4: PaperAdapter, RiskEngine, supervisor, reducer and export, reports, SEC-004, GOLIVE-001/002. Phase 5: /metrics, runbooks, soak, SEC-005, GOLIVE-003.
</deferred>

## Orchestrator resolutions (binding)
- R50 (container, Phase 1): the compose service runs `pumpgrok run --mode paper --once --replay /app/tests/fixtures/replay/smoke` and exits 0. The compose healthcheck runs `pumpgrok doctor` (FOUND-003). No `--hold` mode is built. The healthy long-running container is verified in ROADMAP Phase 5 criterion 3 once the supervisor health endpoint exists. ROADMAP Phase 1 criterion 4 was reworded accordingly.
- R51 (Docker): the docker CLI is installed (29.6.2). Criterion 4 needs a reachable daemon. If the daemon is unreachable, record the exact error as a blocker; do not substitute another check.
- R56 (CR-01, contract governance): a change's required acknowledgers are contract_consumers(surface) minus proposed_by. An acknowledgement from the proposer is ignored, not rejected. G-4 passes when every required acknowledger has an ack in the change file. The gate verifies that an ack is present, not who wrote it. SECURITY.md and docs/cross-bot-protocol.md state that residual limit; authorship is evidenced by git history and reviewed by QUALITY.
- R57 (write-tool gating, G-7 port): approval gating (g6: approval_id and rollback_plan) applies only to tools whose roster entry declares gates: [g6], as docs/TOOL_CATALOG.md declares (exec.place, exec.cancel, and the kill-switch set action where the catalog says so). Paper-write tools with no g6 declaration (journal.append, notify.alert, desk.event_emit, portfolio.ledger_write) need no approval. Live-write tools always require g6 and are never resolvable (invariant I1). Replace the blanket kind-write rule with this declared-gate rule.
- R58 (WR-08 ledger side): ApprovalRecorded gains token_units (int, required for kinds that sell) in ledger/events.py and in its contracts/events schema; regenerate the schemas.
- R59 (lint and types gate): make lint (ruff check and ruff format --check over the repo) and make typecheck (mypy --strict over src) must exit 0. Fix findings. Do not add noqa or type-ignore comments to silence new findings; existing ignores are reviewed, not extended.
- R60 (schema drift): the event schema generator (generate-event-schemas.py, see 01-VERIFICATION.md) runs in write mode, then --check must exit 0.
- R61 (plan 01-06 out-of-scope edits): the gap-closure work reviews the files plan 01-06 changed outside its file list and keeps them when they are correct. It reverts a file only with a stated defect.
