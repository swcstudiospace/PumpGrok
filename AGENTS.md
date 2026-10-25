# PumpGrok desk: instructions for coding agents

PumpGrok is a ten-seat, paper-first Solana trading desk (`src/pumpgrok/`), packaged in the
programming-desk shape: path ownership, verification receipts, gates G-1..G-7, contracts and prompt
assembly. Engagement levels are `research | paper` only (R16). No code path can move real funds.

New here? Start with [CLAUDE.md](CLAUDE.md), the codebase map (stack, layout, commands,
architecture); this file holds the operating rules.

## Where the rules live

The linked file is the rule. Do not treat a summary as a substitute.

| Topic | File |
|---|---|
| Gates G-1..G-7, how to run them | [docs/quality-gates.md](docs/quality-gates.md) |
| Ten seats, levels, flow of a trade | [docs/desk-operating-model.md](docs/desk-operating-model.md) |
| Features that cross seats | [docs/cross-bot-protocol.md](docs/cross-bot-protocol.md) |
| Key custody, secrets, container posture | [SECURITY.md](SECURITY.md) |
| Security constitution (verbatim in every seat file) | [rules/pumpgrok-team.mdc](rules/pumpgrok-team.mdc) |
| Path to owner | [ownership.yaml](ownership.yaml) |
| Vendored engine pin and desk overrides | [docs/VENDOR_PIN.md](docs/VENDOR_PIN.md) |
| Event and tool contracts | [contracts/README.md](contracts/README.md) |
| Release history | [CHANGELOG.md](CHANGELOG.md) |

## The ten seats

| Seat id | Channel | Writes exchange |
|---|---|---|
| bot-00-chief | Trading Floor | no |
| bot-01-scout | Trading Floor | no |
| bot-02-risk | Trading Floor | no |
| bot-03-whale | Trading Floor | no |
| bot-04-sniper | Trading Floor | paper-write |
| bot-05-rug | Trading Floor | no |
| bot-06-exit | DM / off-channel | paper-write |
| bot-07-shill | DM / off-channel | no |
| bot-08-signal | DM / off-channel | no |
| bot-09-journal | DM / off-channel | no |

## Before the first edit

Every path resolves to exactly one seat in [ownership.yaml](ownership.yaml). The last matching
pattern wins, and an unowned path fails G-1. Resolve the paths you will edit before changing them.
Cross-seat work follows [docs/cross-bot-protocol.md](docs/cross-bot-protocol.md).

Work on a `bot-0N-<seat>/<unit>` branch. The gates workflow derives the acting seat from that
prefix. Open a draft pull request. Do not merge, force-push or delete branches without approval.

## Receipts

No completion claim without a receipt under `.receipts/<seat>/<task-id>.json`. Record the commands
you ran and their exit codes, and list what you did not verify. A seat never approves its own
work. Receipts are gitignored; track one with `git add -f`.

## Secrets

Do not print, commit or echo keys, tokens, seed phrases, or `.env` contents. Reference environment
variables by name only. G-3 is `python3 ci/gates/check_secrets.py`.

## Run the checks

```bash
uv sync --frozen --group dev
make lint typecheck test audit   # canonical suite (CI runs the same)
./scripts/check.sh               # instruction-file lint, no network
docker compose run --rm pumpgrok # one skip-only replay cycle, exits 0
```

Use `uv run` for Python commands. The replay is the only executable path in Phase 1.

---

Generated and maintained sections follow. The GSD marker blocks below are kept verbatim.

<!-- GSD:project-start source:PROJECT.md -->

## Project

**PumpGrok Desk v2**

PumpGrok is a Solana memecoin (pump.fun launch) trading desk: ten LLM-backed seats (chief, scout, risk, whale, sniper, rug, exit, shill, signal, journal) plus a catalog of read-only and paper-write tools and a library of skills, packaged in the shape of programming-desk (`ownership.yaml`, receipts, gates G-1..G-7, contracts, prompt assembly, skill manifests) as a Python 3.12 package `src/pumpgrok/`. It is built for the operator who wants the desk to run autonomously in paper mode for the first 2-4 weeks, under an asyncio supervisor, against live Solana data, recording everything in an append-only ledger and replaying deterministically from fixtures. It can never move real funds: the only enabled execution adapter is a `PaperAdapter`, live adapters are disabled stubs behind a nine-precondition gate, and private keys never enter the system.

**Core Value:** The desk runs autonomously in paper mode for 2-4 weeks and produces honest, replayable reports; no code path can move real funds.

### Constraints

- **Security**: Paper-only hard default; `execution.mode` defaults to `paper`, `PaperAdapter` is the only enabled adapter, live adapters raise `LiveGateError`, and `pumpgrok run --mode live` exits 3 unless all nine R21 preconditions hold (precondition 8, a registered live adapter, never holds in this milestone) - the core value depends on no code path being able to move real funds.
- **Security**: No private keys, seed phrases or keypairs ever enter the system; forbidden config names abort startup, secrets arrive only via env, and an AST test fails on signing symbols outside the live stub - the security constitution (`rules/pumpgrok-team.mdc`) is kept verbatim.
- **Compliance**: Detect and trade on observed public signals only; no coordinated buying, wash trades, volume generation, shilling, social posting or wallet UI automation - D7/R39, enforced by `tests/safety/test_no_manipulation_tools.py` and the `notify.alert` allowlist.
- **Compliance**: Constitution clauses are enforced in code, not prose: ticket format `SOL-YYYYMMDD-NNN`, exact human approval phrase, single-send idempotency, RISK `KILL` non-overridable, 5% daily-loss `FLOOR HALTED` with human-only clear - D9, R5, R22, R23.
- **Compatibility**: Mirror programming-desk conventions exactly in shape and names (`ownership.yaml` with one owner per tracked path, gates G-1..G-7 plus self-test, receipts per PR under `.receipts/<seat>/`, prompt assembly from `prompts/*.xml`, skills with L1/L2/L3 bodies and manifests) - D1/D2, so operators and agents move between the two desks without relearning.
- **Compatibility**: Keep the Solana integrations exactly as today (mainnet JSON-RPC, pump.fun REST, PumpPortal WS, Jupiter Swap V2 order, x.ai Grok); nothing added, nothing dropped; Jito dead config and `wallet_private_key` removed - D8, R3.
- **Tech stack**: Python 3.12 only, `uv`, ruff, mypy --strict, pytest; money as integers in base units (lamports, token units) with `Decimal` only for ratios; ULIDs from `core/ids.py`; all time through the `Clock` (no direct `asyncio.sleep`/`time.time`) - D1, R27, R28, R29 keep replay deterministic and the ledger hash chain stable.
- **Process**: ASCII-only new docs (`scripts/check.sh` fails on emoji); constitutional strings keep their exact bytes (U+2013) in code - R7.
- **Process**: GSD workflow with code review and verification per phase; five phases cut per R37 so every checkpoint is buildable from Phase 1 with no waiver; one PR per batch on `bot-0N-<seat>/phase-<n>-<unit>` branches with a receipt and `python3 ci/gates/run_all.py` green.
- **Process**: Checkpoint rule after every phase: all canonical commands exit 0 (`make lint typecheck test audit`) and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` completes one cycle on fixture data (skip-only in Phase 1, engine decision from Phase 2, full ten-seat cycle from Phase 4) with no network - R37, SPE-18063.
- **Dependencies**: pump.fun frontend REST and PumpPortal WS are unofficial with heuristic field names; upstream payloads parse with `extra="ignore"` models, a malformed payload yields `DataStale`/`BLIND`, and `BLIND` is treated as `KILL` - upgrade plan section 8.1.

<!-- GSD:project-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-fast` for a trivial task inline, with no subagents and no PLAN.md
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

## Rules index

Read these before the first edit. Each linked file is the rule; a summary elsewhere is not a substitute.

| Order | File | Read it for |
|---|---|---|
| 1 | [rules/pumpgrok-team.mdc](rules/pumpgrok-team.mdc) | Security constitution (verbatim in every seat file) |
| 2 | [ownership.yaml](ownership.yaml) | Which seat owns the paths you will touch |
| 3 | [docs/desk-operating-model.md](docs/desk-operating-model.md) | Ten seats, levels, flow of a trade |
| 4 | [docs/cross-bot-protocol.md](docs/cross-bot-protocol.md) | Working across seats |
| 5 | [docs/quality-gates.md](docs/quality-gates.md) | Gates G-1..G-7, how to run them |
| 6 | [SECURITY.md](SECURITY.md) | Key custody, secrets, container posture |
| 7 | [docs/RISK_POLICY.md](docs/RISK_POLICY.md) | Risk defaults, paper-first policy, manipulation boundary |
| 8 | [docs/SAFETY_INVARIANTS.md](docs/SAFETY_INVARIANTS.md) | Non-negotiable invariants and their owning tests |
| 9 | [docs/runbooks/setup.md](docs/runbooks/setup.md) | Operator path: setup, engine, start/stop, kill switch, outage, rollback, reports, go-live |
| 10 | [docs/VENDOR_PIN.md](docs/VENDOR_PIN.md) | Vendored engine pin and desk overrides |
| 11 | [CHANGELOG.md](CHANGELOG.md) | Release history by phase |
