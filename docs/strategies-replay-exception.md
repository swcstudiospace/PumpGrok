# REPLAY-ONLY EXCEPTION: legacy placement

Scope: the legacy_screening replay path only (Phase 15, plan 15-06, RT-02).

## Decision

The IntentRouter (`src/pumpgrok/supervisor/intent_router.py`) is the only path from strategy
Intents to `exec.place`. One exception exists. `src/pumpgrok/strategies/legacy.py` calls the
sniper's granted `exec.place` directly, from `_placement_sink` and `_place_buy`. It does this in
the order the replay has always used: marks, then the buys of each stamp, then the rule sells of
each stamp. Legacy replay fills therefore do not pass through the router.

The owner accepted this exception as a documented replay-only exception. It is not permission
for production code to place orders this way.

## Containment rules

1. Legacy placement stays in `strategies/legacy.py`. No other module under `src/pumpgrok` may
   import or reference the placement names it defines: `_place_buy`, `_placement_sink`,
   `_replay`, `run_legacy_replay`. The only exception is a replay runner on the allowlist below.
2. No other strategy module may reach `exec.place`. That means the tool name, its builder, or a
   `.place(...)` call from `src/pumpgrok/strategies`. Strategy Intents reach `exec.place` only
   through the IntentRouter.

Both rules are checked by `tests/strategies/test_legacy_exception.py`.

## Replay runner allowlist

Modules under `src/pumpgrok` permitted to import legacy placement names. Currently empty:
only `legacy.py` and its parity tests drive the legacy replay.

Adding an entry needs an owner decision recorded in this file, a reason next to the entry, and
an update to the test in the same commit. The test fails if an entry names a missing file.

## Enforcement and limits

The guard is import-based. It follows `from ... import` (including relative imports), module
aliases, and attribute access. It does not follow `getattr`, `importlib`, or names built from
strings. It scans `src/pumpgrok` only; the parity tests in `tests/` are outside its scope.

## Not covered

- Any new strategy that needs `exec.place`. It goes through the IntentRouter. Adding a second
  exception needs a decision recorded here and a test change.
- Changes to placement behavior. This note records the exception and adds no code path.
