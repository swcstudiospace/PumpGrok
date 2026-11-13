# 13-03 SNIPER receipt (paper factory, Task 3 SNIPER half)

Seat: bot-04-sniper (SNIPER).
Branch: bot-04-sniper/phase-13-entry-gate (worktree /root/src/repos/pumpgrok-wt/phase-13-entry-gate).
Plan: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-03-PLAN.md.

## Commits

- 9ddf64c test(13-03): RED entry policy slot is ignored by BUY (Task 2 RED)
- 13c1fd2 test(13-03): RED forged source and factory injected fixture fill
- 3675e6b feat(13-03): bind BUY entry reads to an injected entry policy (Task 2 GREEN)
- f56e51d feat(13-03): make paper factory the replay-bound construction boundary (this receipt's code)

## Changes (f56e51d)

- `src/pumpgrok/execution/paper_factory.py` (new): `VerifiedReplay`, `verify_replay`, `build_paper_adapter`, and a private deny-all entry policy `_NoReplayEntries`.
- `src/pumpgrok/execution/__init__.py`: `build_adapter` delegates to `build_paper_adapter`, gains a `replay` keyword, and re-exports the factory names.
- Not touched: the RED tests (unchanged), `replay_runtime.py` (CHIEF), `tools/__init__.py` (RISK), `entry_hook.py`, `paper_adapter/*`.

## Published factory signature

```
verify_replay(dataset_dir: str | Path, clock: Clock) -> VerifiedReplay
    # load_dataset(Path(dataset_dir)) -> FixtureCurveSource(dataset, clock)
VerifiedReplay.dataset -> FixtureDataset        (read-only)
VerifiedReplay.curves  -> FixtureCurveSource    (read-only; the one bound source)
    # minted only by verify_replay (module-private token)

build_paper_adapter(
    settings: object, *, store: LedgerStore, risk: RiskEngine, ids: IdFactory,
    clock: Clock, rng: random.Random, price_source: PriceSource | None = None,
    replay: VerifiedReplay | None = None,
    source: Literal["paper", "replay", "manual"] = "paper", p_drop: float = P_DROP,
) -> PaperAdapter

build_adapter(...same keywords...) -> PaperAdapter    # delegate
```

Contract:
- With `replay`: `source` must be `"replay"`; `price_source` must be None or `replay.curves`; BUY entries admit only `replay.curves` (exact type `FixtureCurveSource`, identity checked at both BUY reads). Otherwise `ValueError`.
- Without `replay`: every BUY is refused at ACCEPTED with `data_unavailable` before any read. Sells and exits still read `price_source`.
- Live composition is not admitted (13-04).

## Commands and results

1. RED, before production edits (tip 3675e6b, RED tests 13c1fd2):
   `uv run pytest -q tests/execution/test_paper_factory.py tests/execution/test_curve_source_gate.py tests/execution/test_entry_gate_hook.py 2>&1 | tail -60`
   - Exit code: not captured literally (pipe to `tail`); pytest reported 2 failed, so the pytest exit was nonzero.
   - test_factory_injected_fixture_buy_is_not_filled: `assert 'FillRecorded' not in ['OrderPlaced', 'FillRecorded', 'PositionOpened']` (actual fill, semantic RED).
   - test_injected_source_cannot_forge_fixture_entry: `DID NOT RAISE any of (ValueError, OrderRejectedError)` (actual fill, semantic RED).
   - test_entry_gate_hook: all passing.
2. Import-order smoke (interpreter check, not pytest):
   `uv run python -c "import pumpgrok.replay.sources as s; import pumpgrok.execution as e; ..."` and the reverse order: exit 0 both; `pumpgrok.execution.live` not loaded (False).
3. ASCII check: `grep -nP '[^\x00-\x7F]'` over `paper_factory.py` and `execution/__init__.py`: no matches (grep exit 1).
4. Single targeted run (GREEN and regression evidence):
   `timeout 900 uv run pytest -q -p no:cacheprovider --junitxml=.receipts/bot-04-sniper/13-03-task3-green.xml tests/execution tests/replay tests/test_operator_budget_wiring.py tests/test_tools_cli.py tests/safety/test_no_live_adapter_registered.py tests/safety/test_import_graph_no_live.py tests/characterization/execution tests/tools/test_verb_coverage.py`
   - Exit code 1 (`PIPESTATUS[0]`). JUnit totals: 369 run, 6 failed, 0 errors, 0 skipped.
   - tests/execution: 129 run, 0 failed. Both RED targets pass: test_paper_factory 1/1, test_curve_source_gate 5/5. test_entry_gate_hook passes.
   - Other suites: tests/characterization/execution 45/0 failed; tests/safety 20/0; tests/test_tools_cli.py 69/0; tests/replay 91 run, 2 failed.
   - Failures and attribution:
     - tests/test_operator_budget_wiring.py: `test_build_adapter_without_settings_uses_default_limit` and `test_operator_slippage_limit_clamps_request_in_ledger`. Caused by this change. They BUY through `build_adapter` with scripted `fixture` curves, the same construction as the RED tests, so they cannot both pass. RISK's receipt lists this file for 13-05 migration. Not edited here.
     - tests/tools/test_verb_coverage.py `TestExecBackendCoverage::test_place_buy_fills_and_consumes_approval` and `::test_cancel_unknown_and_positions_after_buy`. Caused by this change, same mechanism (BUY through `build_operator_registry` with scripted curves). RISK's receipt lists this file for 13-05. Not edited here.
     - tests/replay/test_greptile_r2.py `test_later_candidate_is_not_refused_data_stale_after_a_buy` and tests/replay/test_greptile_r3.py `test_two_mints_moving_opposite_are_marked_once_per_instant`. Not attributed to this change: the replay path (`replay_runtime.py`) constructs `PaperAdapter` directly with no entry policy, and these failures are in the data_stale / MarkToMarket path. No pre-change baseline was run in this seat (single-run limit), so this is unverified against HEAD. Owner to confirm.

## Incident: misdirected writes (corrected)

The file-write tool resolved relative paths against the main checkout `/root/src/repos/pumpgrok` (branch `bot-00-chief/phase-6-integrity`), not this worktree. Two files were written there:
- `src/pumpgrok/execution/paper_factory.py`: new untracked file, moved to this worktree and removed from the main checkout.
- `src/pumpgrok/execution/__init__.py`: tracked file, overwritten. Restored in the main checkout with `git checkout -- src/pumpgrok/execution/__init__.py`, which returns it to HEAD blob e39a207. That blob equals this branch's original `__init__.py`. The main checkout's only tracked modification was this file.
- Residual risk: the main file's pre-write state was not snapshotted separately. It was inferred clean from `git status` before the restore. Other untracked items in the main checkout (`.claude/`, `docs/gsd/`, `.receipts/bot-00-chief/*`) were not touched.

## Not done in this seat

- `replay_runtime.py` (CHIEF) still constructs `PaperAdapter` directly. The replay migration to `build_paper_adapter(..., replay=verify_replay(dataset_dir, clock), source="replay")` is CHIEF's.
- `tools/__init__.py` (RISK) is unchanged. It still calls `build_adapter` without `replay`, so its BUYs are refused by design until RISK migrates.
- Plan Task 3 source-tree AST invariant is not added. It depends on the CHIEF and RISK call-site migrations.
- `test_operator_budget_wiring.py` and `test_verb_coverage.py` are not migrated (13-05, owned by RISK).
- Live composition (13-04): live-paper BUYs are refused.
- Fee model v2: out of scope, untouched.
- No pre-change baseline run in this seat.

## Independent review

Independent review: APPROVED by owner human:SomeRandmGuyy on 2026-11-12 as the independent non-self reviewer for this receipt only. Approval covers the factory commits and the test results listed above; the two intended RED tests now pass.
