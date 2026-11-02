# Phase 18 CONTEXT: Dormant live path, amendment-gated

Milestone v4, Phase 18. Goal per ROADMAP: the five hardcoded-unmet live gate rows become real checks; a segregated desk-signer process (single-send persistence, signer-side policy, chain reconciliation, shadow mode) exists; the desk holds no key and no signing symbol; the amendment is applied by a HUMAN in one pull request. Live STAYS REFUSED: with the overlay disabled, no env flag and no arm record, `run --mode live` exits 3; arming is a human-only runbook step no plan performs.

Depends on: Phase 17 (stage rows, kill, promotion) and Phases 12, 13, 15. Plans 18-01 and 18-07 have no code dependency and may start early (contract acknowledgements take a round trip). amendment_wait plans (18-03 to 18-06, 18-08, 18-09) merge only after the owner approves the exact amendment text (OD-01: draft plus errata E1 to E5) and PR-34 merges.

## Locked decisions (NON-NEGOTIABLE)

- D-01: Money integer lamports; Decimal only for ratios.
- D-02: Clock-only time in the desk.
- D-03: Live stays refused; no overlay ships enabled=true (test_live_disabled_overlays); no plan arms, funds or sends.
- D-04: hashes are identity only, never a score.
- D-05: mypy --strict, ruff, no dead code, no swallowed errors, no placeholders, ASCII-only docs.
- D-06: Owner answers: live is armed ONCE by a human, then autonomous inside caps (notional cap at most 1.0 SOL, D6 fractions); custody is a segregated signer; the amendment lands only by a human-approved PR.
- D-07 (blocker fix 1): LiveGate splits into `check_entry` (all nine rows) and `check_exit` (rows 1, 2, 5, 6, 8: mode, enabled, wallet allowlist, notional cap, adapter registered). The engine calls check_exit for sells and mints `autonomous_live` for exit-rule and flatten sells while ANY live position is open, even with a halt, kill, open breaker, expired arm or demotion; only entries are suspended. Tests prove both directions in those states.
- D-08 (blocker fix 2): the arm record lists (strategy id, param_set_hash) PAIRS (`live confirm --strategy id:hash`, repeatable); a param hash change needs a new arm; expiry at most live.arm_max_expiry_hours (default 72, hard ceiling 168, OD-07), longer records fail to load; the record binds the config hash AND ledger-held param hashes; the place frame carries param_set_hash and the signer re-derives it from stage rows.
- D-09 (blocker fix 3): plan 18-04 applies an INSTRUCTION-level allowlist to the decoded transaction, fail closed: System Transfer ONLY to the pinned fee recipient; Token and Token-2022 deny Transfer, Approve, SetAuthority, Burn, Freeze and non-wallet CloseAccount; ATA create only for wallet and intent mint; pump program discriminator allowlist with curve PDAs derived from the intent mint; ComputeBudget within signer.fee_cap_lamports; v0 lookup tables refused. The signer owns the blockhash and verifies the FINAL signed bytes. PumpPortal trade-local sits behind a TxBuilder interface (OD-14).
- D-10: Single send (18-03): RECEIVED, BUILT, SIMULATED, SIGNED, SUBMITTED, then CONFIRMED_OK, CONFIRMED_FAILED, DROPPED or UNKNOWN. The SIGNED row (signature, tx bytes, lastValidBlockHeight) is fsynced (file AND directory) before sendTransaction; maxRetries 0; no rebroadcast; DROPPED only after a finalized check; confirmation uses a SECOND RPC; UNKNOWN is never retried and blocks all but its own reconcile; restart reconciles, never re-signs.
- D-11: IPC: Unix socket var/signer/signer.sock mode 0660 plus group signer.socket_group (OD-11: desk-signer-clients), length-prefixed canonical_json frames (hello, quote, simulate, place, status, reconcile, balances, attest, identity), nonce plus signer-clock timestamp, persisted nonce window; attestation and identity travel over the socket, never shared-var files. SO_PEERCRED across containers authenticates nothing beyond signer policy; the doc says so.
- D-12: The desk holds no key and no signing symbol: INV-S-01 is tightened (EXEMPT_PREFIX removed): no sign, sendTransaction, Keypair, solders or solana under src/pumpgrok, execution/live included. The signer lives in services/desk-signer with its own pyproject, lock, lint, mypy, pip-audit and CI job; its tests live ONLY under services/desk-signer/tests (root suite: just tests/safety/test_signer_isolation.py). Key file at DESK_SIGNER_CREDENTIAL_PATH (0400, signer uid), placed by the human.
- D-13: C-17 mirror: stage, kill and halt rows live in the PAPER ledger; the signer folds the LIVE ledger (var/live/ledger.sqlite, source=live). mirror.py appends idempotent copies at promotion, kill and halt edges and at arm time, called from the composition root, never a timer. The doc states this is CONSISTENCY, not independence.
- D-14: C-07 adds `live` to EventSource additively (non-breaking) across ALL nine literal sites. Changed (risk): ledger/events.py:31, ledger/store.py:31, risk/engine/steps.py:222 and 18 schemas. Deliberately NARROW and pinned by tests/ledger/test_event_source_literal_sites.py: sniper paper_adapter adapter.py:57, buy.py:36, marks.py:32, execution/__init__.py:28; journal ledger_read.py:30, ledger_write.py:38. G-4: breaking false, semantic_changes empty, each regenerated schema listed, `generate-event-schemas.py --check`.
- D-15: tx_failed_onchain latches a HaltSet only a human clears (errata E2; the exec_errors breaker auto-resets after 900 s); any UNKNOWN sets HaltSet(live_unknown); reconcile compares SOL and token balances within live.drift_tolerance_lamports (OD-03).
- D-16 (blocker fix 6, plan 18-07): the amendment is ONE owner-applied PR (PR-34, branch bot-00-chief/v4-p18-amendment), the only non-seat-pure PR in v4, with ONE step-scoped G-1 waiver (gates.yml step "G-1 - Path ownership" for that PR number; test_no_pr_waivers pinned to (N,)). Text = the draft plus errata E1 to E5 and every missed copy (see the plan's files); new oracle tests/safety/amendment_2026_10_28_frozen.txt and test_amendment_copies_complete.py. Agents never apply, paraphrase or merge it.
- D-17: build_adapter dispatches to execution/live_factory.py ONLY when mode is live and the gate is open; that factory imports the registered class by dotted path and nothing else does, so no supervisor, cli, backtest, upgrade or paper_adapter import closure reaches the signer client.

## Grey-area defaults

- G-01: The arm runbook uses an operator-local file named by PUMPGROK_CONFIG outside git, never a committed overlay with enabled=true (E3); cap_sol = min(1.0, 200 USD / SOL price minus fees) at arm time (OD-12, E4).

## Phase boundary

In scope: event source contract, signer protocol, stop_state, execution/live/*, services/desk-signer/**, compose service, doctor checks, live verbs, amendment PR, runbooks, dormant wiring. Out of scope: arming, funding, key placement, mainnet transactions, PumpSwap.

## Canonical references

execution/live/{live_gate,live_adapter}.py, risk/engine/{steps,constants}.py, ledger/{events,store}.py, contracts/events/, ownership.yaml, rules/pumpgrok-team.mdc, docs/RISK_POLICY.md, research/C-risk-promotion-live.md sections 3 to 8, research/C-AMENDMENT-DRAFT.md, research/amendment-errata.md.

## Existing code insights

- `live confirm` writes an HMAC record (var/live_confirmation.json, cap at most 1.0 SOL) hashing `[]` for the allowlist, with no verifier; LiveGate rows 5, 6, 8, 9 are hardcoded unmet.
- Fill.venue_tx_ref is pattern-locked to dry_run:ULID; it becomes `^(dry_run:[ULID]|[1-9A-HJ-NP-Za-km-z]{64,88})$`; paper never emits a signature form and live never emits dry_run.

## Specifics

- Place frame: OrderRequest JSON unchanged, dedupe key exec_place_key(ticket, side, decision_id), approval kind (human_buy, autonomous_live), strategy_id, param_set_hash; a duplicate key returns the stored response.
- Hash rule: both pairs EQUAL (18-10).

## Deferred ideas

Direct pump instruction building; Jito tips; pump-amm sells.

## Ownership, receipt and hash rules (every plan of this phase)

- Branch `bot-0N-seat/v4-pPHASE-slug`, one PR per (phase, seat) (PR table below). Receipt `.receipts/bot-0N-seat/v4-pPHASE-slug.json` (task_id = slug, branch = the branch), tracked through the glob `!.receipts/bot-0*/v4-p*.json` from plan 11-01; no other seat edits .gitignore.
- `approved_by` is NEVER self-written and a seat never approves its own work. An agent reviewer (chief for risk-authored work, risk for other seats) reads the diff; human-gated receipts are committed WITHOUT approved_by and the owner adds `human:SomeRandmGuyy` in a batch at the ship checkpoint (after phases 12, 14, 17, 19).
- Seat purity: every path resolves to the plan seat via `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; tests/** is risk except tests/desk/** (chief) and tests/engine/** (signal); execution/** sniper; cli/** risk; supervisor/** chief. A foreign-test failure gets a one-file companion plan by the owning seat, merged first.
- Replay hashes: smoke-10m `events.hash` is `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (seq=2 events=41, verdict and rollover rows only). Trading `smoke` (5 events, seq 11) gave `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54` at HEAD 641927c; plan 11-01 pins it at v4-base; it moves only in plan 15-01. Run receipts in a fresh worktree without var/ledger.sqlite.
- Live stays refused: `uv run pumpgrok run --mode live --once; test $? -eq 3`; nothing arms it.
- Acceptance lines are real commands; exit 0 means success. The G-2 bypass family (collect-only, `--co`, `|| true`, stderr to /dev/null, `--force`, `--dry-run`, inline PUMPGROK_LIVE_ENABLE) never appears; `! cmd -rs | grep -q SKIPPED` proves no skips. Plans touching src also run make lint and make typecheck.


## Plans (11 planned; research/plans.json is the source)

Pull requests in merge order (numbers from research/pr-plan.md):

| PR | Branch | Plans | Approver | Checkpoint |
|----|--------|-------|----------|------------|
| PR-35 | `bot-02-risk/v4-p18-dormant-live-path` | 18-01, 18-02, 18-03, 18-04, 18-05, 18-06 | human:SomeRandmGuyy (batch); agent review first | CP19 |
| PR-34 | `bot-00-chief/v4-p18-amendment` | 18-07 | human (owner applies and merges) | CP19 |
| PR-36 | `bot-04-sniper/v4-p18-live-dispatch` | 18-08 | human:SomeRandmGuyy (batch); agent review first | CP19 |
| PR-37 | `bot-00-chief/v4-p18-runbooks-live-wiring` | 18-09 | human:SomeRandmGuyy (batch); agent review first | CP19 |
| PR-38 | `bot-09-journal/v4-p18-changelog` | 18-10 | bot-02-risk (agent) | CP19 |
| PR-39 | `bot-00-chief/v4-p18-close` | 18-11 | bot-02-risk (agent) | CP19 |

### 18-01: Stop-state reader, live event source contract (additive) and signer protocol schema

- seat bot-02-risk; wave 1; PR-35; depends_on: none; order_after 17-02; requirements: LIV-05, LIV-14, LIV-20, LIV-09; owner decisions: OD-11.
- files: src/pumpgrok/ledger/stop_state.py, tests/ledger/test_stop_state.py, src/pumpgrok/ledger/events.py, src/pumpgrok/ledger/store.py, src/pumpgrok/ledger/paths.py, contracts/events/*.schema.json, contracts/changes/v4-live-source.yaml, tests/ledger/test_live_source.py, tests/contracts/test_live_source_contract.py, src/pumpgrok/risk/engine/steps.py, tests/ledger/test_event_source_literal_sites.py, src/pumpgrok/core/signer_protocol.py, tests/core/test_signer_protocol.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/ledger/test_stop_state.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/v4-live-source.yaml
python3 scripts/generate-event-schemas.py --check
uv run pytest -q tests/ledger tests/contracts
uv run pytest -q tests/core/test_signer_protocol.py
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 18-02: Gate rows split for entries and exits, arm scope by strategy and param hash with maximum expiry, live status, confirm and disarm verbs

- seat bot-02-risk; wave 2; PR-35; depends_on: 11-04, 12-01, 17-03, 18-01; requirements: LIV-03, LIV-04, LIV-07, LIV-11, RSK-09, LIV-17; owner decisions: OD-07, OD-03.
- files: src/pumpgrok/execution/live/live_gate.py, src/pumpgrok/execution/live/arm.py, src/pumpgrok/cli/parsing.py, src/pumpgrok/cli/dispatch.py, src/pumpgrok/cli/verbs_ops.py, src/pumpgrok/doctor.py, tests/live/test_gate_rows56.py, tests/live/test_arm_record.py, tests/safety/test_live_refusal_lists_nine.py, tests/test_live_gate.py, tests/live/test_gate_exit_rows.py, tests/live/test_arm_scope.py, tests/live/test_arm_expiry_ceiling.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/live tests/safety tests/test_live_gate.py tests/test_doctor_probes.py
uv run pumpgrok run --mode live --once; test $? -eq 3
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 18-03: desk-signer core: IPC, nonce window, attestation over the socket, single send, reconcile

- seat bot-02-risk; wave 2; PR-35; depends_on: 11-03, 12-01, 15-01, 18-01, 18-07; requirements: LIV-08, LIV-09, LIV-11, LIV-19; amendment_wait; owner decisions: OD-11.
- files: services/desk-signer/pyproject.toml, services/desk-signer/Dockerfile, services/desk-signer/src/desk_signer/__init__.py, services/desk-signer/src/desk_signer/server.py, services/desk-signer/src/desk_signer/store.py, services/desk-signer/src/desk_signer/reconcile.py, services/desk-signer/src/desk_signer/attest.py, services/desk-signer/src/desk_signer/timesync.py, services/desk-signer/src/desk_signer/redact.py, services/desk-signer/tests/test_server_ipc.py, services/desk-signer/tests/test_nonce_window.py, services/desk-signer/tests/test_single_send.py, services/desk-signer/tests/test_reconcile.py, services/desk-signer/tests/test_import_allowlist.py, services/desk-signer/tests/test_attest_over_socket.py, docker-compose.yml, tests/safety/test_signer_isolation.py.
- acceptance (run from the repo root, each exits 0):

```sh
cd services/desk-signer && uv run pytest -q
uv run pytest -q tests/safety/test_signer_isolation.py
uv run ruff check services
uv run mypy services/desk-signer/src
make audit
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
python3 ci/gates/check_ownership.py --validate-manifest
```

### 18-04: desk-signer transaction policy: instruction-level allowlist, signer-owned blockhash, final-bytes verification

- seat bot-02-risk; wave 3; PR-35; depends_on: 18-03; requirements: LIV-18, LIV-08; amendment_wait; owner decisions: OD-14.
- files: services/desk-signer/src/desk_signer/txbuilder.py, services/desk-signer/src/desk_signer/txpolicy.py, services/desk-signer/src/desk_signer/signing.py, services/desk-signer/src/desk_signer/fees.py, services/desk-signer/src/desk_signer/policy.py, services/desk-signer/tests/test_txpolicy_allowlist.py, services/desk-signer/tests/test_blockhash_signer_owned.py, services/desk-signer/tests/test_final_bytes_verify.py, services/desk-signer/tests/test_alt_refused.py, services/desk-signer/tests/test_token2022_wallet_ata.py, services/desk-signer/tests/test_policy_order.py.
- acceptance (run from the repo root, each exits 0):

```sh
cd services/desk-signer && uv run pytest -q tests/test_txpolicy_allowlist.py tests/test_blockhash_signer_owned.py tests/test_final_bytes_verify.py tests/test_alt_refused.py tests/test_token2022_wallet_ata.py tests/test_policy_order.py
uv run ruff check services
uv run mypy services/desk-signer/src
uv run pumpgrok run --mode live --once; test $? -eq 3
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 18-05: Live adapter client, registry, autonomous_live for entries and exit sells, reconcile verb, tightened guards

- seat bot-02-risk; wave 3; PR-35; depends_on: 12-01, 12-02, 17-02, 18-01, 18-02, 18-07; requirements: LIV-06, LIV-10, LIV-13, LIV-15, RSK-06, RSK-09, LIV-19; amendment_wait; owner decisions: OD-03.
- files: src/pumpgrok/execution/live/signer_client.py, src/pumpgrok/execution/live/registry.py, src/pumpgrok/execution/live/reconcile.py, src/pumpgrok/core/adapter.py, src/pumpgrok/core/approvals.py, src/pumpgrok/risk/engine/steps.py, src/pumpgrok/cli/parsing.py, src/pumpgrok/cli/dispatch.py, src/pumpgrok/cli/verbs_ops.py, tests/harness/faults.py, tests/live/test_registry.py, tests/live/test_reconcile.py, tests/live/test_autonomous_live.py, tests/live/test_single_send.py, tests/safety/test_risk_choke_point.py, tests/safety/test_signer_only_bypass.py, tests/safety/test_no_signing_outside_live_stub.py, tests/safety/test_import_graph_no_live.py, tests/safety/test_no_live_adapter_registered.py, tests/safety/test_live_adapter_raises.py, tests/safety/test_no_backtest_to_live_path.py, src/pumpgrok/risk/breakers.py, tests/live/test_exit_sells_autonomous_live.py, tests/live/test_tx_failed_onchain_latch.py, tests/live/test_reconcile_drift_tokens.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/live tests/safety tests/core
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
python3 ci/gates/check_ownership.py --validate-manifest
```

### 18-06: Shadow-live adapter and the stage, kill and halt mirror into the live ledger

- seat bot-02-risk; wave 4; PR-35; depends_on: 13-03, 17-03, 18-01, 18-03, 18-04, 18-05, 18-07; requirements: LIV-12, LIV-19; amendment_wait.
- files: src/pumpgrok/execution/live/shadow.py, tests/live/test_shadow.py, src/pumpgrok/execution/live/mirror.py, tests/live/test_stage_mirror.py, docs/design/live-ledgers.md.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/live/test_shadow.py tests/safety
uv run pytest -q tests/live/test_stage_mirror.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
python3 ci/gates/check_ownership.py --validate-manifest
```

### 18-07: Constitution amendment: one owner-applied pull request with every copy, the frozen oracle and one step-scoped G-1 waiver

- seat owner-applied:multi-seat; wave 1; PR-34; depends_on: 11-01, 11-09; order_after 11-01; requirements: LIV-16, PRC-07; HUMAN-GATED; owner decisions: OD-01.
- files: rules/pumpgrok-team.mdc, prompts/_shared/core-directives.xml, docs/RISK_POLICY.md, SECURITY.md, docs/LIVE_READINESS.md, docs/SAFETY_INVARIANTS.md, tests/safety/amendment_2026_10_28_frozen.txt, tests/safety/test_constitution_amendment_2026_10_28.py, tests/safety/test_constitution_amendment.py, .github/workflows/gates.yml, ci/tests/test_no_pr_waivers.py, AGENTS.md, ARCHITECTURE.md, docs/ROSTER.md, skills/key-custody/SKILL.md, tests/safety/test_amendment_copies_complete.py, agents/*.md, prompts-assembled/*.xml, skills/desk-operating-model/SKILL.md, .planning/PROJECT.md, README.md, prompts/bot-00-chief.xml, SETUP.md, docs/runbooks/setup.md, prompts/bot-04-sniper.xml.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/safety/test_constitution_amendment_2026_10_28.py tests/safety/test_constitution_amendment.py
python3 scripts/generate-templates.py --check
make prompts
make check
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 18-08: build_adapter dispatches to the live factory only when the gate is open

- seat bot-04-sniper; wave 4; PR-36; depends_on: 11-01, 11-06, 18-05, 18-07; requirements: LIV-06, LIV-07; amendment_wait.
- files: src/pumpgrok/execution/__init__.py, tests/execution/test_build_adapter_registry.py, src/pumpgrok/execution/live_factory.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/execution
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
python3 ci/gates/check_ownership.py --validate-manifest
```

### 18-09: Arm, signer and rollback runbooks; dormant live wiring in the composition root

- seat bot-00-chief; wave 5; PR-37; depends_on: 11-01, 17-04, 18-03, 18-04, 18-05, 18-06, 18-07, 18-08; requirements: LIV-16, LIV-10, LIV-07; amendment_wait; owner decisions: OD-12, OD-11.
- files: docs/runbooks/go_live.md, docs/runbooks/signer.md, docs/runbooks/live_rollback.md, src/pumpgrok/supervisor/live_paper.py, src/pumpgrok/supervisor/scheduler/wake.py, tests/desk/test_live_wiring_dormant.py.
- acceptance (run from the repo root, each exits 0):

```sh
./scripts/check.sh
./scripts/verify_doc_commands.sh
uv run pytest -q tests/desk/test_live_wiring_dormant.py
uv run pumpgrok run --mode live --once; test $? -eq 3
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 18-10: CHANGELOG entry for Phase 18 with both hash pairs

- seat bot-09-journal; wave 6; PR-38; depends_on: 18-01, 18-02, 18-03, 18-04, 18-05, 18-06, 18-07, 18-08, 18-09; order_after 17-06; requirements: PRC-03, PRC-06.
- files: CHANGELOG.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -qF 'Phase 18: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
grep -qF 'Phase 18: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 18: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 18: trading-smoke events.hash after: $p" CHANGELOG.md
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 18-11: Phase 18 close: STATE, verification record, arm-readiness checklist

- seat bot-00-chief; wave 7; PR-39; depends_on: 18-01, 18-02, 18-03, 18-04, 18-05, 18-06, 18-07, 18-08, 18-09, 18-10; order_after 17-07; requirements: PRC-06.
- files: .planning/STATE.md, .planning/ROADMAP.md, .planning/phases/18-dormant-live-path-amendment-gated/18-VERIFICATION.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -q 'Phase 18' .planning/STATE.md
./scripts/check.sh
test -f .planning/phases/18-dormant-live-path-amendment-gated/18-VERIFICATION.md
python3 ci/gates/check_ownership.py --validate-manifest
```
