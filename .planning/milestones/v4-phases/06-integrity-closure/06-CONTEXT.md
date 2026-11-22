# Phase 6 Context: Integrity closure

**Milestone:** v3 | **Requirements:** INT-01 to INT-10, PRC-01, PRC-02
**Branch:** bot-00-chief/phase-6-integrity, from origin/main f3887bb plus the planning commit 87e664d

## Baseline (main f3887bb, run 2026-10-25)

- make lint: pass. make typecheck: pass (158 source files). make test: pass, 294 s, 2 skips.
- ./scripts/check.sh: pass. Replay smoke completes; engine decision is skip with data_unavailable, which is expected while the bonding-curve layout is ASSUMED.

## Evidence (re-verified on main 2026-10-25)

- Float money still present: ledger/export.py:105 and :140; engine/models.py:85-86 and :262-265; engine/analyzer.py:161-207; engine/exits.py:41-113; engine/reputation.py:62; engine/tune.py:40-123.
- Silent fallbacks: ledger/reducer.py:312-314; supervisor/seat_task.py:496-501 (_initial_equity returns 0); supervisor/lifecycle.py:123 and :127 (int(... or 0)).
- Daily loss: risk/engine.py:527-532. The drawdown halt still fires at equity 0, so the daily-loss check is not the only backstop.
- SOL to lamports: core/risk_budget.py:57-62, cli.py:165 and :1094, core/approvals.py:154, all ROUND_HALF_UP. Four copies.
- Ambient randomness: cli.py:652 (approval id) and core/binding_key.py:50 (os.urandom). tests/safety/test_static_guards.py:42-45 bans only random.* and uuid/secrets.
- Constant seed fallback: replay/rng.py:12-15; core/registry.py:101; tools/onchain/rpc.py:105; tools/__init__.py:307-351; cli.py:269 and :719; config/settings.py:282.
- Live gate clock: execution/live/live_gate.py:161 reads WallClock().now().
- Long functions: execution/paper_adapter.py _place_order (about lines 429-523, about 95 lines), _place_buy (about 657-880, about 224 lines); supervisor/scheduler.py _replay_cycles (about 598-709, about 112 lines).
- Trailing-stop peaks: held in memory (v2 audit tech debt, phase 4).
- Feature lineage (not ancestors of origin/main): commit 4c19fd9 (WR-07, remove replay ledger when append or verify fails) and commit 76975bb (scale stored venue fee with remaining units on a partial sell). Earlier fix e83801f (persist venue fee on the mark) is present on main as the field; the scaling logic is not verified there.
- Already on main, no action needed: WR-02 gateway seat binding, WR-08 (no image HEALTHCHECK, by design), kill-switch window reads (unbounded), health and metrics fixes, approval and sell matching fixes.

## Decisions (smart-discuss defaults, applied under the approved requirement text)

1. Money (INT-01): integer lamports or base units everywhere. Decimal only for ratios such as price impact, PnL percentage and slippage. The persisted reputation book switches to integer lamports; the existing rebuild-from-ledger path replaces old float books. No dual-read shim.
2. Export (INT-01): ledger/export.py writes prices as exact decimal strings computed from integer scaled values. No float division.
3. Errors (INT-02): raise an existing typed error from core/errors.py where one fits. Add a new typed error only if none fits. No broad exception handler may swallow a ledger, equity or peak read.
4. Daily loss (INT-03): integer cross-multiplied comparison. A start equity of zero or less raises a typed error that the seat reports. The drawdown halt is unchanged.
5. SOL to lamports (INT-04): one implementation in core/, ROUND_HALF_UP. risk_budget, cli and approvals import it. The other three copies are removed.
6. Randomness (INT-05): os.urandom is allowed only at the approval-id point in cli and the binding-key point in core/binding_key.py. The static guard lists this allowlist and rejects any other os.urandom, secrets or uuid use under src/pumpgrok. DEFAULT_SEED stays only in replay code. Production factories receive an explicit seed from the composition root.
7. Live gate clock (INT-06): the gate receives now from its caller. The caller reads the injected Clock. No WallClock inside the gate.
8. Feature-lineage fixes (INT-07): inspect `git show 4c19fd9` and `git show 76975bb` on feat/grokbot-desk-merge, then re-implement on main's code. Each regression test must fail on the pre-fix code.
9. Function splits (INT-08): extract stage functions. Public signatures do not change. No behavior change. Replay hashes are unchanged.
10. Trailing-stop peaks (INT-09): persist peaks through an existing ledger event type. R32 fixes the vocabulary at eighteen event types, so no new type is added. Restore the peak before the first exit check on restart. A serve-restart test proves the restore.
11. Curve probe (INT-10): scripts/probe_curve_layout.py does a read-only getAccountInfo against the configured public RPC for a known bonding-curve account. No keys. It writes a decoded fixture under tests/fixtures/rpc/bonding_curve/. If the network is unreachable, LAYOUT_STATUS stays ASSUMED and the exact error text is recorded verbatim. That satisfies the criterion.
12. Gates (PRC-01): each plan ends with make lint, make typecheck and make test. The phase closes with ./scripts/check.sh, the replay smoke, verify run twice with equal hashes, and live exit 3. Each completion claim gets a receipt under .receipts/bot-00-chief/.
13. Replay hash (INT-01, INT-08, INT-09): unchanged unless the change is required. Any change is recorded in CHANGELOG.md with before and after hashes.

## Open (non-blocking, decided during planning)

- Module name for the units helper, within core/.
- Confirm the inferred locations: risk/engine.py for the daily-loss check; core/ids.py and core/binding_key.py for os.urandom roots.

## Out of scope for this phase

- New ledger event types. Live enablement. Paid RPC. Backtest or upgrade code (Phases 8 and 9). Documentation (Phase 7), except docs/CURVE_LAYOUT_PROBE.md, the one and only docs/ file this phase writes (INT-10 criterion 11).
