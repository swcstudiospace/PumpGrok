# PumpGrok - codebase map

## Purpose

PumpGrok is a ten-seat paper-first Solana memecoin trading desk in `src/pumpgrok/`.
Live trading is fail-closed: this release runs paper only, and every order is
approved or vetoed by risk before it reaches the paper fill path in
`src/pumpgrok/execution/paper_adapter.py`.

- Ten supervised seats (`bot-00-chief` through `bot-09-journal`) are defined in `ownership.yaml` and rostered in `src/pumpgrok/supervisor/scheduler.py`.
- Seat prompts live in `agents/*.md` (ten seat files plus `agents/README.md`).
- The 35 tool skills live in `skills/*/` (35 directories, e.g. `skills/momentum-signals/SKILL.md`).
- Package version is `0.1.0` per `pyproject.toml` (`version = "0.1.0"`).

## Stack

Python 3.12 with `uv`-managed locked deps; lint, types, and tests are pinned in
`pyproject.toml` and wired as targets in `Makefile`.

- Runtime `3.12` is pinned by `pyproject.toml` (`requires-python`, `python_version = "3.12"`).
- Deps install via `make sync`, which runs `uv sync --frozen --group dev` from `Makefile`.
- Lint via `make lint`, which runs `ruff check .` and `ruff format --check .` from `Makefile`.
- Types via `make typecheck`, which runs `mypy src/` under `--strict` per `pyproject.toml`.
- Tests via `make test`, which runs `pytest -q` per `Makefile`.

## Layout

Product code lives in `src/pumpgrok/`; seat prompts, skills, rules, contracts,
fixtures, and operator scripts sit alongside it at the repo root.

- Supervised loop and replay entry points in `src/pumpgrok/supervisor/scheduler.py`.
- CLI verbs and flags in `src/pumpgrok/cli.py` (no `--rpc` flag exists there).
- Settings and `PUMPGROK_*` env binding in `src/pumpgrok/config/settings.py`.
- Market tools in `src/pumpgrok/tools/market/` (e.g. `src/pumpgrok/tools/market/price.py`).
- Execution and paper fills in `src/pumpgrok/execution/` (e.g. `src/pumpgrok/execution/paper_adapter.py`).
- Risk engines and gates in `src/pumpgrok/risk/` (e.g. `src/pumpgrok/risk/engine.py`).
- Replay clock, fixtures, and runner in `src/pumpgrok/replay/` (e.g. `src/pumpgrok/replay/runner.py`).
- Seat prompts in `agents/` (ten role files such as `agents/risk.md` plus `agents/README.md`).
- Tool skills in `skills/*/` (35 directories, each with `skills/<name>/SKILL.md`).
- Generation rules in `rules/` (e.g. `rules/pumpgrok-team.mdc`).
- Event and tool contracts in `contracts/` (`contracts/events/`, `contracts/tool-rosters/`).
- Tests and replay fixtures in `tests/` (e.g. `tests/fixtures/replay/smoke`).
- Operator scripts in `scripts/` (e.g. `scripts/check.sh`).

## Commands

Only commands verified against `Makefile` and `src/pumpgrok/cli.py` are listed
here. Full gate bundle is `make check` (see `Makefile`).

- `make lint` lints and format-checks via `ruff` as defined in `Makefile`.
- `make typecheck` runs `mypy src/` under `--strict` as defined in `Makefile`.
- `make test` runs the suite via `pytest -q` as defined in `Makefile`.
- `./scripts/check.sh` runs the repo consistency checks referenced by `Makefile`.
- `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` runs one offline paper cycle over `tests/fixtures/replay/smoke` (see `src/pumpgrok/cli.py`).
- `uv run pumpgrok run --mode paper --serve --replay tests/fixtures/replay/smoke` serves `/healthz` and `/metrics` in a replay loop; `src/pumpgrok/cli.py` requires `--replay <dir>` without `--once` for `run --serve`.
- `uv run pumpgrok doctor` prints effective config and killswitch state via `src/pumpgrok/cli.py`.

## Architecture

One supervisor tick drives ten seats in roster order; risk approves every order
and paper fills settle against the curve account.

- Ten-seat tick loop lives in `src/pumpgrok/supervisor/scheduler.py`; due seats start in roster order each tick (`TICK_S = 1.0`, `src/pumpgrok/supervisor/scheduler.py:89-90`).
- One-shot replay builds a `PaperAdapter` in `src/pumpgrok/supervisor/scheduler.py` (`run_once_replay`).
- Pre-graduation fills come from bonding-curve reserves via `src/pumpgrok/execution/paper_adapter.py`, never from a quote.
- `src/pumpgrok/tools/market/price.py` reads the curve account with `getAccountInfo` and decodes it with `src/pumpgrok/tools/onchain/curve_layout.py`; it has no Jupiter path.
- `src/pumpgrok/tools/exec/quote.py` routes through the `ExecutionAdapter` from `src/pumpgrok/core/adapter.py` and is informational only, never the fill price.
- `src/pumpgrok/tools/market/jupiter.py` holds only the informational Jupiter Swap V2 order URL in `QUOTE_URL`; it never calls `/execute`.
- Serve mode is the replay loop with `/healthz` and `/metrics` in `src/pumpgrok/cli.py` (`_serve_replay_loop`); it is paper-only with no live path.

## Conventions

Units, ratios, time, and config follow the rules below; grep the cited file
before inventing a second convention.

- Money is integer lamports (`int`) converted once at load via `src/pumpgrok/core/units.py` (see `src/pumpgrok/core/risk_budget.py`).
- Ratios and prices are `Decimal` only, never `float` (e.g. `price: Decimal` in `src/pumpgrok/tools/market/price.py`).
- Time comes from the injected `Clock` in `src/pumpgrok/replay/clock.py`, re-exported by `src/pumpgrok/core/ids.py`; `WallClock` is production, `FixtureClock` is replay.
- Config arrives via `PUMPGROK_*` env vars bound in `src/pumpgrok/config/settings.py` (nested delimiter `__`, e.g. `PUMPGROK_RPC__ENDPOINTS`).
- RPC endpoints are keyless URLs in `src/pumpgrok/config/settings.py` (`RpcSettings.endpoints`, default `https://api.mainnet-beta.solana.com`); there is no `--rpc` flag in `src/pumpgrok/cli.py`.
- Every file resolves to exactly one owning seat via `ownership.yaml` (last match wins; validate with `ci/gates/check_ownership.py`).

## GSD artifact

Planning state and per-task evidence live outside the product tree.

- Phase plans, context, and summaries live in `.planning/phases/07-documentation-upgrade/` (e.g. `.planning/phases/07-documentation-upgrade/07-CONTEXT.md`).
- Per-task machine receipts live in `.receipts/<bot>/<task>.json` (see the `gates` target in `Makefile`).
- Prompt sources and generated agent templates are checked by `scripts/assemble-prompts.sh` and `scripts/generate-templates.py`.

## Safety

Paper-only by default; live mode refuses to start unless every precondition in
`src/pumpgrok/cli.py` is met.

- `run` accepts `--mode paper --once --replay <dir>` (one cycle) and `--serve --replay <dir>` (loop); `--record`, `--duration` and other combinations exit not-implemented (`src/pumpgrok/cli.py`, `_run`, lines 581-596).
- `run --mode live` evaluates `LiveGate` in `src/pumpgrok/cli.py` and refuses with exit code `3` (`EXIT_LIVE` in `src/pumpgrok/cli.py`) when any precondition is unmet.
- Secrets arrive only as `PUMPGROK_*` env vars per `src/pumpgrok/config/settings.py`; key-bearing endpoint values are refused at startup (see `RpcSettings` in `src/pumpgrok/config/settings.py`).
- Paid-provider keys travel in `api_key` and are sent as a header, never embedded in endpoint URLs (see `src/pumpgrok/config/settings.py`).

## Known gaps

Assumptions and path differences the reader must not mistake for verified fact.

- Curve decoding uses the `[ASSUMED]` layout in `src/pumpgrok/tools/onchain/curve_layout.py` until a live probe confirms it (see `scripts/probe_curve_layout.py`).
- `run --once --replay` exercises the `PaperAdapter` path via `run_once_replay` in `src/pumpgrok/supervisor/scheduler.py`, while `run_replay` in `src/pumpgrok/supervisor/scheduler.py` writes the checkpoint verdict row first and does not run the paper adapter.
- `run --record` is not implemented and exits `EXIT_NOT_IMPLEMENTED` from `src/pumpgrok/cli.py`.
