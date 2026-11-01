# Phase 20 Context: Close gap LIV-01 (live adapter import path)

## Gap

LIV-01 (Phase 10) claims that the import graph has no path from the backtest, paper, or upgrade modules to a live adapter. The v3 milestone audit (`.planning/v3-MILESTONE-AUDIT.md`, status gaps_found, commit 9bfb0f6) found the claim false at runtime:

- `pumpgrok.cli.backtest` loads `pumpgrok/cli/__init__.py`, which imports `pumpgrok.cli.dispatch`, which reaches `src/pumpgrok/cli/verbs_state.py:44` (`from pumpgrok.execution.live.live_gate import LiveGate, refusal_lines`).
- Importing `pumpgrok.execution.live.live_gate` first executes the package `src/pumpgrok/execution/live/__init__.py`, whose line 3 imports `LiveAdapterStub` from `pumpgrok.execution.live.live_adapter`.
- The guard test `tests/safety/test_import_graph_no_live.py` follows named module edges only. It never executes the parent package `__init__`, so the path is invisible to it and the test passes.
- No live write path exists: the stub is not registered and `run --mode live` exits 3.

## Decisions

- **D-01:** Red first (TDD is on). Before any fix, add two failing regression tests:
  (a) guard fidelity: the guard's edge and closure model follows the parent package `__init__` of every imported module (importing `a.b.c` executes `a/__init__.py` and `a/b/__init__.py`), so the existing guard reports the CLI path as a violation;
  (b) runtime: a fresh interpreter that imports `pumpgrok.cli`, `pumpgrok.cli.backtest`, and `pumpgrok.cli.promotion` leaves `pumpgrok.execution.live.live_adapter` absent from `sys.modules`.
- **D-02:** Fix by removing the adapter re-export from `src/pumpgrok/execution/live/__init__.py`: the import on line 3 and the `"LiveAdapterStub"` entry in `__all__`. The package keeps the gate exports (`PRECONDITION_IDS`, `LiveGate`, `Precondition`, `refusal_lines`). The adapter stays importable from its own module, `pumpgrok.execution.live.live_adapter`.
- **D-03:** Clean cutover. Migrate every caller of the package-level `LiveAdapterStub` import to the submodule path. Known caller: `tests/test_live_gate.py:14`. Grep `src`, `tests`, `docs`, `scripts`, `ci`, and `skills` for any other package-level use. No compatibility alias or re-export.
- **D-04:** No behavior change. `pumpgrok run --mode live --once` still exits 3 and lists the nine preconditions. The adapter stays unregistered. The gate module stays reachable from the CLI, as the G-02 test requires. Update the package docstring so it no longer says the package holds the adapter stub.
- **D-05:** Do not weaken any existing guard assertion. Existing symbol scans, network-root scans, and the `GATE_MODULE` reachability assertion stay as they are. The fidelity change only adds edges.
- **D-06:** Verification. Targeted pytest for `tests/safety` and `tests/test_live_gate.py`, then the canonical `make lint typecheck test audit` and `./scripts/check.sh`. Smoke: `uv run pumpgrok run --mode live --once` exits 3; `uv run pumpgrok verify --fixture smoke-10m` reports CONSISTENT with replay hash `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`. The replay hash must not change.
- **D-07:** Scope is the import structure, the guard test, the single caller migration, and any doc line that names the package-level export. Nothing else changes.
- **D-08:** Work on branch `bot-00-chief/v3-closeout` in `/root/src/repos/pumpgrok-wt/v3-closeout` only. Commit with explicit `git add` paths. Do not push, merge, or touch the phase-6 checkout at `/root/src/repos/pumpgrok`.
- **D-09:** Exception to D-07. Add one `CHANGELOG.md` entry under the v3 section for the LIV-01 closure, because the closeout contract requires a changelog entry for each permanent fix. No other file outside the import structure, guard, and caller migration changes.
