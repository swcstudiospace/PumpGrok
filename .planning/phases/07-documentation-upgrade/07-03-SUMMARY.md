# Phase 07 Plan 03: DOC-03 Contradiction Corrections (README + ARCHITECTURE + SETUP + replay skill) — Summary

## One-liner

Corrected every 2026-10-25 audit contradiction in README, ARCHITECTURE, SETUP and
the replay-and-backtest skill against the Phase 6 code, verified by grep.

## Status

- Task 1 (README contradictions): complete in commit `3b37550` (pre-existing, untouched by this run).
- Task 2 (ARCHITECTURE, SETUP, replay skill): complete in commit `02fb039`.

## Commits

- `3b37550` — `docs(07-03): [DOC-03] correct README contradictions against Phase 6 code`
  (README.md only: eight-role → ten-seat, version → package `0.1.0`, `--rpc` →
  `PUMPGROK_RPC__ENDPOINTS`, desk-record path fixes. Done before this run; not modified here.)
- `02fb039` — `docs(07-03): [DOC-03] correct ARCHITECTURE, SETUP and replay skill contradictions`
  (this run: ARCHITECTURE.md, SETUP.md, skills/replay-and-backtest/SKILL.md)

## Changes (commit 02fb039)

ARCHITECTURE.md:
- Line 7: `eight-role` → `ten-seat` (matches the ten role files in `agents/` and the
  `ten-seat autonomous paper loop` in `src/pumpgrok/supervisor/__init__.py`).
- Line 18: the `no PumpGrok server, queue, or daemon` sentence contradicted the
  `run --serve` replay loop and the compose `pumpgrok` service, so it now says the
  tree runs no always-on services behind the desk and names the one long-running
  form (`run --mode paper --serve --replay <dataset>`, read-only `/healthz` +
  `/metrics`, paper-only).
- Lines 26–29: the Jupiter row no longer attributes `market.price` to Jupiter.
  `market.price` reads the bonding-curve account with `getAccountInfo` (ASSUMED
  layout; `src/pumpgrok/tools/market/price.py`, no Jupiter path in the module);
  Jupiter appears only as the informational exec-side quote
  (`src/pumpgrok/tools/market/jupiter.py` `QUOTE_URL`, never `/execute`).
- Line 28 and line 203: `--rpc` rows → `PUMPGROK_RPC__ENDPOINTS` (no `--rpc` flag
  exists in `src/`; the env name derives from `Settings.rpc.endpoints` via the
  `PUMPGROK_` prefix + `__` nested delimiter in `src/pumpgrok/config/settings.py`).
- Line 61: `Nothing in this repo is started as a service` → fail-closed serve-mode
  wording (only the opt-in `--serve` replay loop runs as a service; the `--once`
  form runs a single cycle and exits).
- Line 121 (tools table): `market.price` → RPC `getAccountInfo` on the
  bonding-curve account, no Jupiter path in the module.
- Line 242: `priority_fee --rpc/--percentile/--multiplier` → `priority_fee`
  percentile/multiplier inputs (default multiplier 1.2); `--rpc` is not a CLI flag.

SETUP.md:
- Line 4: `eight specialist Bots` → `ten seats`.
- Section 5: heading → `Create the ten seats`; table gains the verified
  `SIGNAL` (Momentum Scorer) and `JOURNAL` (Post-Trade Ledger) rows from
  `agents/signal.md` / `agents/journal.md` frontmatter.
- Line 137: `passed with --rpc` → `set with PUMPGROK_RPC__ENDPOINTS`.

skills/replay-and-backtest/SKILL.md:
- Line 3 (description), line 23 (L1), line 33 (S2): `same code path as (live)
  paper` / `identical path` replaced with the accurate statement — the
  `run --once --replay` path runs the supervisor, the rule, and the PaperAdapter
  on a fixture clock, while the lighter `run_replay` checkpoint
  (`src/pumpgrok/replay/runner.py`, pure engine stage, verdict `JournalNote` row)
  does not run the paper adapter (`src/pumpgrok/supervisor/scheduler.py`
  `open_replay_runtime` / `run_once_replay`).
- Every `pumpgrok run --mode paper --replay <dataset>` command (lines 23, 33,
  references) → `run --mode paper --once --replay <dataset>`, since the bare form
  exits not-implemented (`src/pumpgrok/cli.py` `_run`, lines 591–596). The
  references entry notes `--serve` instead of `--once` for the long-running loop.

## Incident

The first executor wrote its README edits into the main checkout
(`/root/src/repos/pumpgrok`) instead of this worktree and was cancelled. The
README edits were recommitted from the worktree as `3b37550`, and the main
checkout was restored. Verified at handoff: `git -C /root/src/repos/pumpgrok
status --short` output is empty (see below).

## Verification (acceptance commands)

Banned-phrase sweep returns no matches:
`grep -nE 'eight-role|no server, queue, or daemon|Nothing in this repo is started as a service|--rpc|same code path as (live )?paper|identical path|identical fill' ARCHITECTURE.md SETUP.md skills/replay-and-backtest/SKILL.md` → no output (exit 1).
Positive checks pass: `PUMPGROK_RPC__ENDPOINTS` in ARCHITECTURE.md (2×) and
SETUP.md (1×); `ten-seat|ten seats` in both. All three `pumpgrok run` commands in
the skill use `--once` (references entry documents the `--serve` variant).

## Deviations

None. No files outside ARCHITECTURE.md, SETUP.md, and
skills/replay-and-backtest/SKILL.md were edited; no behavior or `src/` changes;
no tests, gates, or network commands were run (orchestrator runs gates).
