# Phase 15 Plan Check: PASS with warnings

Verdict: PASS. All 8 ROADMAP requirements are covered, waves and deps are acyclic,
seats resolve clean, honesty rules hold, hashes and owner decisions are honored.
4 warnings and 2 advisories below. No blocker.

## Warnings

1. Fee v2 default may not reach the pin-generating path. Plan 15-01 files list the new
   paper fees section plus cli backtest, but not fees.py, settings.py, or the paper
   adapter. If the flip lives only in the CLI, PaperAdapter keeps building v1 and the
   trading-smoke re-pin is a no-op. Fix: name the runtime default file in 15-01 files,
   or prove the parity test drives the real paper path default.
2. Trading-smoke move is never proved distinct. Plan 15-07 greps before as any 64-hex
   and after equal to the pin file, so an equal pair passes. Fix: assert before differs
   from after, and pin the exact git command that recovers the pre-15-01 OLD value,
   since summaries under tmp do not cross branches.
3. Canonical no-send gates are not run. Plan 15-06 runs a bespoke AST scan but never
   the repo safety suites for import graph and no signing. Fix: add those two suites
   to the 15-06 acceptance block.
4. ROADMAP success criterion make test has no covering command. Plans run targeted
   pytest plus lint and typecheck only. Fix: add make test to the 15-08 close block.

## Advisories

1. Plan 15-01 creates strategies allocation without strategies init, which lands in
   15-02. Namespace packages make it import, but the order is fragile. Fix: create the
   init in 15-01.
2. Plan 15-06 cites exit reasons from engine exits while the literal lives in core
   adapter. The four reasons exist, only the pointer is off. Fix: correct the pointer.

Coverage: MKT-09 in 15-06, STR-01 in 15-01 and 15-02, STR-03 in 15-01 15-02 15-03 15-06,
STR-04 in 15-03 15-04 15-05, STR-05 in 15-02, STR-06 in 15-01, FEE-01 in 15-01,
RT-02 in 15-06. Smoke-10m pair equal, trading pair moves once. OD-02 OD-06 OD-08 OD-17
honored. Live stays refused. No signing or key code. Registry and bounds edits
serialize across waves 2 3 4 5. PR merge order matches dependencies.
