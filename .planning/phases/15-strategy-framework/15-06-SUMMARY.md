# Phase 15 Plan 06: Live-data paper root + Intent router — Summary

**Status: complete.** Commits `f330180` (15-06) and `4743c56` (gate lint/typecheck fixes).
SC 10 and SC 11 hold; the router suite reports zero skipped.

## What shipped

- `src/pumpgrok/supervisor/live_paper.py` — the read-only live-data paper
  composition root (MKT-09, D-06). `build_live_paper` refuses to build
  unless the execution mode is paper (`LivePaperError` otherwise, checked
  before any component is constructed). It wires the Phase 13 datafeed
  (`LivePriceSource`, `MintBook` + `MarksLoop`), the 15-03 strategy runtime
  under slice allocation, and the Intent router. Feed access goes through
  `LivePaperDesk.feed_call`, which checks the read-only allowlist before
  touching the transport — only the five allowlisted methods are reachable.
  `strategy_factory` guards the registry's `resolve_factory`: a returned
  module object (its fallback when the named class is absent, e.g. legacy
  screening has no instantiable class) is refused instead of being called.
  Unknown strategy ids are refused.
- `src/pumpgrok/supervisor/intent_router.py` — the single path from a
  strategy `Intent` to `exec.place` (RT-02, D-06). The router validates the
  strategy id against the four registered ids and the side against
  {buy, sell}. Below `autonomous-paper` (or the ledger default
  `manual-ticket`) it appends a `JournalNote` refusal row and places
  nothing — no ticket, no approval, no `place` call. At autonomy it
  allocates the `SOL-YYYYMMDD-NNN` ticket, mints the `apr-<ULID>` approval,
  records the ticket attribution ref (legacy writes none, per 15-02), and
  places exactly one `OrderRequest` through the injected `place`.
- `src/pumpgrok/supervisor/exit_rules.py` — ticket filter. `LedgerExitBook`
  carries a sold-ticket claim set; `claim_ticket` is first-wins per ticket,
  so two strategies racing one ticket-attributed position (and a later
  rule pass for the same ticket) produce exactly one sell. Both the rule
  sell path and the graduation-close path claim the ticket before acting.
  A re-entry opens a new ticket and is unaffected.
- `src/pumpgrok/strategies/registry.py` — type-only fix: `resolve_factory`
  return is cast to `Callable[..., Any]` (mypy strict was failing on the
  `Module | Any` fallback), and the function-level `import importlib` moved
  to module level. Runtime behavior unchanged; the consumer-side guard
  lives in `live_paper.strategy_factory`.

## Tests

- `tests/desk/test_live_paper_root.py` — refusal unless paper (live string,
  `ExecutionMode.LIVE`, `paper-event`, `manual`); builds under paper (enum
  and string); registry module-fallback guard; unknown-id refusal; AST
  scan over the six composed modules for signing/send symbols.
- `tests/desk/test_exit_rules_filter.py` — first-wins claim; two
  strategies sharing a ticket produce exactly one `place_sell`; a fresh
  ticket sells again.
- `tests/desk/test_intent_router.py` — below-autonomy refusal journaled
  with zero `place` calls; ledger default refuses; at autonomy places once
  with the router-allocated ticket/approval; unknown id refused + journaled;
  static proof that no strategy module names `.place` or imports execution
  machinery. Zero skipped tests.
- `tests/desk/test_ticket_approval_allocation.py` — ticket/approval formats,
  sequential ticket numbers, attribution ref written for new strategies,
  none for legacy, refusal allocates nothing.
- `tests/datafeed/test_readonly.py` (extended) — parameterized write-method
  refusals, all five allowlisted methods pass, and the root's `feed_call`
  reaches only the allowlist (a `sendTransaction` attempt is refused
  before the transport ran).

## Gate results (SC 10 / SC 11 verbatim)

- `uv run pytest -q tests/desk/test_live_paper_root.py tests/desk/test_exit_rules_filter.py tests/datafeed/test_readonly.py` → exit 0
- `uv run pytest -q tests/desk/test_intent_router.py tests/desk/test_ticket_approval_allocation.py` → exit 0
- `uv run pytest tests/desk/test_intent_router.py -rs` → 6 passed, no SKIPPED line

## Deviations

- Rule 1/2: `resolve_factory` fallback returned the module object, causing a
  mypy `--strict` failure and a latent runtime trap. Fixed the typing with
  a cast (registry) and guarded the consumer (`live_paper.strategy_factory`
  refuses non-class factories). Committed with the gate-fix commit `4743c56`.
- Rule 3: `make lint` / `make typecheck` were red at HEAD from 37 pre-existing
  lint findings in Phase 15 files (15-01…15-05) and the registry mypy error.
  Fixed mechanically (ruff autofixes plus manual E501/SIM/PLC0415 wraps;
  one tautological `or True` assertion in `test_no_llm.py` dropped and noted
  in its comment — the `hasattr` and `find_spec` asserts still carry that
  test). Commit `4743c56`. `make lint` and `make typecheck` now exit 0.
- Stubs: none. No package installed. No signing/send/key material anywhere
  in the new modules (AST-scanned by the new test).

## Threat flags

None new beyond the plan's register: T-15-13 (root AST scan), T-15-14
(refusal journal rows), T-15-15 (router-only routing) are all mitigated and
covered by the new tests. `src/pumpgrok/supervisor/live_paper.py` and
`src/pumpgrok/supervisor/intent_router.py` are the only new modules.

## Files

Created: `src/pumpgrok/supervisor/live_paper.py`,
`src/pumpgrok/supervisor/intent_router.py`,
`tests/desk/test_live_paper_root.py`,
`tests/desk/test_exit_rules_filter.py`,
`tests/desk/test_intent_router.py`,
`tests/desk/test_ticket_approval_allocation.py`.
Modified: `src/pumpgrok/supervisor/exit_rules.py` (ticket-claim filter),
`tests/datafeed/test_readonly.py` (extended), plus the `4743c56` gate-fix set.
