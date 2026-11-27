# TODO / FIXME / HACK / XXX triage (bot-00-chief)

Date: 2026-11-12. Branch: bot-00-chief/phase-6-integrity. Read-only; no product, planning or git state changed.

## Conclusion

A case-insensitive search over src, tests, scripts, docs, .planning and ownership.yaml finds 38 marker-word lines: 0 in src, tests, scripts and ownership.yaml, 9 in docs/, and 29 in .planning/. No hit is a live work marker. Every row is OUT_OF_SCOPE, by category: 9 quote retired vendor or v2 design text in historical design records (rows 1-9); 14 are sweep-record or tracker text (rows 10-23); 10 are negated prose in phase verification or summary records (rows 24-27 and 30-35); 2 are superseded v2 research rows (rows 28-29); 3 are requirement text (rows 36-38). Zero rows are COVERED, because every phase in ROADMAP.md (6 to 10) is Complete and none of their acceptance criteria names a marker. Zero rows are RELEASE_BLOCKER, because no marker sits on a shipped path in src or tests. This agrees with .planning/TODO-BACKLOG.md and .planning/STATE.md. One discrepancy: TODO-BACKLOG.md and MILESTONE-AUDIT.md say "9 hits"; that count covers docs/ only and omits the 29 .planning/ lines listed below.

## Commands run (exit codes)

Pipelines ending in `cut`, `wc` or `sed` report the status of the last command in the pipe.

1. `ls -d src tests scripts docs .planning ownership.yaml` - all six present (exit 0 as printed).
2. `grep -rniE --exclude-dir=node_modules --exclude-dir=vendor --exclude-dir=dist --exclude-dir=build --exclude-dir=.next --exclude-dir=coverage -n '\b(TODO|FIXME|HACK|XXX)\b' src tests scripts docs .planning ownership.yaml` - exit 0; output truncated mid-run, so re-run per tree.
3. `grep -rniE ... -c '\b(TODO|FIXME|HACK|XXX)\b' src tests scripts ownership.yaml`-style per-file counts (`grep -v ':0$'`) - exit 0; per-file counts summed to 38 for docs and .planning.
4. `grep -rniE ... -n ... src tests scripts ownership.yaml | wc -l` - 0 (wc exit 0).
5. `grep -rniE ... docs .planning | wc -l` - 38 (wc exit 0).
6. `grep -rnoiE --exclude-dir=node_modules '.{0,45}\b(TODO|FIXME|HACK|XXX)\b.{0,25}' docs .planning` - exit 0; gave the marker context for every docs/.planning hit.
7. `grep -nE '^#{1,6} '` on each file that contains a hit, plus `sed -n` on specific lines - exit 0; gave the enclosing heading for each hit.
8. `grep -rniE 'LiveExecutor|wallet_private_key|JitoConfig|GROKBOT_WALLET|NotImplementedError' src tests scripts` - exit 0. Matches are only a comment in src/pumpgrok/config/settings.py:297, a comment in src/pumpgrok/execution/fees.py:7, and assertions in tests/config/test_secret_refusal.py:38-43. No LiveExecutor in src or tests.
9. `grep -rniE 'not-yet-implemented' src tests scripts` - exit 0 (see Observations).
10. `head -n 4` of docs/DISCOVERY.md, docs/MIGRATION_MAP.md, docs/design/paper-engine.md, docs/upgrade-plan-desk-v2.md - all start with "Historical design record".
11. `ls vendor` - no such file. `ls src/pumpgrok/execution/live` - __init__.py, live_adapter.py, live_gate.py present.
12. Read: .planning/ROADMAP.md (all phases 6-10 marked [x] Complete), and .planning/TODO-BACKLOG.md, STATE.md, MILESTONE-AUDIT.md at the cited lines.

## Evidence table

Every hit is listed once. Disposition key: OUT_OF_SCOPE (all 38 rows). The "marker" column is the matched text in the line; "heading" is the nearest enclosing heading or table context.

### docs/ (9 hits)

| # | File:line | Enclosing heading | Marker text (matched line) | Disposition | Reason |
|---|---|---|---|---|---|
| 1 | docs/DISCOVERY.md:371 | `### 3.5 Execution / wallet-signing code paths` | "both bodies are a TODO comment followed by" | OUT_OF_SCOPE | Historical design record (banner line 1; DOC-04, Phase 7, complete). Quotes the v2 LiveExecutor stub. Live refused and no live adapter registered: ROADMAP Phase 10, LIV-01. |
| 2 | docs/DISCOVERY.md:431 | `## 4. Real-money risk surface` | "# TODO(live): ... Load Keypair from config.solana.wallet_private_key" | OUT_OF_SCOPE | Historical design record quoting v2 pseudo-code. The setting does not exist: tests/config/test_secret_refusal.py:39 asserts "wallet_private_key" is not a Settings field. No key material: D4, Phase 10 LIV-01. |
| 3 | docs/FOUNDATION_STACK.md:746 | `## 7. MIGRATION_NOTES` (heading at line 733) | "only the `LiveExecutor` TODO comment at `executor.py:156-158` names it" | OUT_OF_SCOPE | Migration note recording the removal of JitoConfig (R3). It describes a completed removal, not future work. FOUNDATION_STACK is not in the DOC-04 banner set. src has no Jito symbol (row 8 grep). |
| 4 | docs/MIGRATION_MAP.md:198 | `### 1.8 Vendor scripts and src (22 rows)` | "a 6-step Russian TODO naming `solders.keypair`" | OUT_OF_SCOPE | Migration map (banner present) for vendor/grokbot-pumpfun. vendor/ is absent on disk (`ls vendor`). ROADMAP Phase 7 notes the snapshot was deleted in Phase 4. |
| 5 | docs/MIGRATION_MAP.md:272 | `### 2.1 Code hits and disposition` | "No code reads `jito` except the `LiveExecutor` TODO comment" | OUT_OF_SCOPE | Migration-map row recording removal of dead Jito config (R3). Banner present; vendor source absent. |
| 6 | docs/MIGRATION_MAP.md:274 | `### 2.1 Code hits and disposition` | "`class LiveExecutor`; TODO lines `:150` ... `:156-158`" | OUT_OF_SCOPE | Row states the vendor TODO recipe is NOT carried over and the replacement raises LiveGateError. Banner present; vendor absent; no LiveExecutor in src. Phase 10 LIV-01. |
| 7 | docs/design/paper-engine.md:50 | `## 1. Existing code: extend vs build (SPE-18025)` | "`LiveExecutor.buy/sell` raise `NotImplementedError` with a six-step TODO" | OUT_OF_SCOPE | Design record (banner present) describing the vendor state being replaced. Live stays refused: ROADMAP Phase 10 goal and LIV-01 criterion 3 (no live adapter registered). |
| 8 | docs/design/paper-engine.md:162 | `### 2.4 Quote source and slippage cap (otherAmountThreshold semantics)` | "(vendor TODO at executor.py:151-156 ...)" | OUT_OF_SCOPE | Design prose citing vendor provenance for the slippage rule. Banner present. No work item. |
| 9 | docs/design/paper-engine.md:843 | `### 7.4 LiveAdapter stub and LiveGateError` | "the six-step vendor TODO (executor.py:151-162) is" | OUT_OF_SCOPE | Design prose describing that a live write is refused and logged. Banner present. Phase 10 LIV-01. |

### .planning/ top-level records (14 hits)

| # | File:line | Enclosing heading | Marker text (matched line) | Disposition | Reason |
|---|---|---|---|---|---|
| 10 | .planning/MILESTONE-AUDIT.md:31 | `## Notes` (N2) | "N2 (TODO scan): 9 hits on HEAD, all in design and migration documentation" | OUT_OF_SCOPE | Audit prose summarising the sweep. Not a marker. The "9" counts docs/ only (see Cross-checks). |
| 11 | .planning/STATE.md:53 | `## Discovery (2026-10-25)` | "Zero TODO, FIXME, HACK or XXX markers in src, tests, ci, scripts ..." | OUT_OF_SCOPE | Negated prose recording the discovery result. |
| 12 | .planning/STATE.md:55 | `## TODO mapping` | "## TODO mapping" (heading) | OUT_OF_SCOPE | Section heading of the session tracker. Not a marker. |
| 13 | .planning/STATE.md:57 | `## TODO mapping` | "| TODO item | Disposition |" (table header) | OUT_OF_SCOPE | Column header. Not a marker. |
| 14 | .planning/STATE.md:102 | `## Decisions` | "q3 defer unmapped TODOs" (gsd-autonomous run defaults) | OUT_OF_SCOPE | Run-default record referring to the session tracker, not to a code marker. |
| 15 | .planning/TODO-BACKLOG.md:1 | H1 title | "# TODO / FIXME / HACK backlog (v3 milestone audit)" | OUT_OF_SCOPE | Title of the sweep record. |
| 16 | .planning/TODO-BACKLOG.md:3 | preamble (before `## Dispositions`, line 19) | "Sweep: `rg -n -e TODO -e FIXME -e HACK` ..." | OUT_OF_SCOPE | Method description. |
| 17 | .planning/TODO-BACKLOG.md:9 | preamble table, row 1 | "both bodies are a TODO comment followed by" | OUT_OF_SCOPE | Backlog row quoting hit 1. |
| 18 | .planning/TODO-BACKLOG.md:10 | preamble table, row 2 | "# TODO(live): ... Load Keypair" | OUT_OF_SCOPE | Backlog row quoting hit 2. |
| 19 | .planning/TODO-BACKLOG.md:11 | preamble table, row 3 | "\"TODO\" text in the table" | OUT_OF_SCOPE | Backlog row quoting hit 3. |
| 20 | .planning/TODO-BACKLOG.md:12 | preamble table, row 4 | "row 107, vendor executor split, mentions TODO" | OUT_OF_SCOPE | Backlog row quoting hit 4. |
| 21 | .planning/TODO-BACKLOG.md:14 | preamble table, row 6 | "LiveExecutor TODO lines `:150`, `:156-158`" | OUT_OF_SCOPE | Backlog row quoting hit 6. |
| 22 | .planning/TODO-BACKLOG.md:15 | preamble table, row 7 | "six-step TODO" | OUT_OF_SCOPE | Backlog row quoting hit 7. |
| 23 | .planning/TODO-BACKLOG.md:16 | preamble table, row 8 | "matched on TODO text in a sentence" | OUT_OF_SCOPE | Backlog row quoting hit 8. |

### .planning/milestones/ and .planning/phases/ records (15 hits)

| # | File:line | Enclosing heading | Marker text (matched line) | Disposition | Reason |
|---|---|---|---|---|---|
| 24 | .planning/milestones/v2-phases/01-foundation/01-VERIFICATION.md:183 | `### Anti-Patterns Found` | "TBD/FIXME/XXX/TODO/HACK ... clean (only hit is the PLACEHOLDER_RE identifier)" | OUT_OF_SCOPE | Verification record of v2 phase 1; result clean. |
| 25 | .planning/milestones/v2-phases/02-restructure/02-05-SUMMARY.md:134 | `## Known Stubs` | "No TODO/FIXME/placeholder text in created or modified files" | OUT_OF_SCOPE | Negated prose. |
| 26 | .planning/milestones/v2-phases/02-restructure/02-VERIFICATION.md:99 | `### Anti-Patterns Found` | "show no TBD/FIXME/XXX debt markers" | OUT_OF_SCOPE | Negated verification finding. |
| 27 | .planning/milestones/v2-phases/04-paper-trading-and-autonomy/04-09-SUMMARY.md:188 | `## Known Stubs` | "finds no TODO, FIXME, placeholder" | OUT_OF_SCOPE | Negated prose. |
| 28 | .planning/milestones/v2-phases/04-paper-trading-and-autonomy/04-RESEARCH.md:235 | `### 4.1 Vendor-to-target map with current state` | "`LiveExecutor` (executor.py:137-172) with 6-step TODO" | OUT_OF_SCOPE | v2 research row. Its own status column says the vendor TODO is not carried and the replacement is LiveAdapterStub. Live refused: Phase 10 LIV-01. |
| 29 | .planning/milestones/v2-phases/04-paper-trading-and-autonomy/04-RESEARCH.md:806 | `## 18. State of the Art (in this repo)` | "Vendor `LiveExecutor` with TODO (executor.py:137-172)" | OUT_OF_SCOPE | Superseded v2 research row (LiveAdapterStub that refuses and records attempts). |
| 30 | .planning/milestones/v2-phases/04-paper-trading-and-autonomy/04-VERIFICATION.md:137 | `### Anti-Patterns Found` | "services/desk-gateway/src/desk_gateway/server.py ... TBD/FIXME/XXX/TODO ... No markers in the fixed file" | OUT_OF_SCOPE | Verification checklist row recording no markers. services/ is outside the search paths and was not re-checked. |
| 31 | .planning/milestones/v2-phases/05-hardening/05-07-SUMMARY.md:184 | `## Known Stubs` | "found no TODO/FIXME/placeholder markers (excluding the intentional `not-yet-implemented` doctor vocabulary)" | OUT_OF_SCOPE | Negated prose. The excluded term is a status string, not a TODO marker (see Observations). |
| 32 | .planning/milestones/v2-phases/05-hardening/05-08-SUMMARY.md:181 | `## Known Stubs` | "No TODO/FIXME/placeholder added" | OUT_OF_SCOPE | Negated prose. |
| 33 | .planning/milestones/v2-phases/05-hardening/05-VERIFICATION.md:133 | `### Anti-Patterns Found` | "No TBD/FIXME/XXX markers introduced by this phase were found" | OUT_OF_SCOPE | Negated verification finding. |
| 34 | .planning/phases/08-backtest-and-paper-evaluation/08-01-SUMMARY.md:45 | `## Design notes` | "No angle brackets, no TODO markers, ASCII only." | OUT_OF_SCOPE | Negated prose. |
| 35 | .planning/phases/08-backtest-and-paper-evaluation/08-02-SUMMARY.md:67 | `## Stub scan` | "No TODO, placeholder, or stub text in new files" | OUT_OF_SCOPE | Negated prose. |
| 36 | .planning/phases/08-backtest-and-paper-evaluation/08-CONTEXT.md:40 | `## Locked decisions (non-negotiable, from the brief)` | "no TODO or placeholder text, ASCII-only new docs" | OUT_OF_SCOPE | Requirement text stating the rule. Not a marker. |
| 37 | .planning/phases/09-bounded-paper-self-upgrade/09-CONTEXT.md:48 | `## Locked decisions (NON-NEGOTIABLE)` | "no TODO or placeholder text, ASCII-only new docs" | OUT_OF_SCOPE | Requirement text stating the rule. Not a marker. |
| 38 | .planning/phases/10-live-readiness-kept-disabled/10-CONTEXT.md:76 | `## Grey areas with defaults and one-line reasons` | "no TODO or placeholder text except the two CHANGELOG hash placeholders" | OUT_OF_SCOPE | Requirement text. The exception names CHANGELOG.md placeholders, which lie outside the search paths and were not inspected. |

## Summary

| Disposition | Count | Rows |
|---|---|---|
| COVERED | 0 | none |
| RELEASE_BLOCKER | 0 | none |
| OUT_OF_SCOPE | 38 | 1-38 |

Total hits: 38 (src 0, tests 0, scripts 0, ownership.yaml 0, docs 9, .planning 29). Rows 17-23 are the seven TODO-BACKLOG.md table lines that quote docs hits; the 29 .planning lines are rows 10-38.

## Cross-checks

- ROADMAP.md: phases 6 to 10 are all "[x] Complete". Phase 6 criterion 17 is waived (G1) and INT-10/G2 is deferred, per MILESTONE-AUDIT.md lines 21-27. None of these items names a TODO, FIXME, HACK or XXX marker.
- Banners (ROADMAP Phase 7, DOC-04): docs/DISCOVERY.md, docs/MIGRATION_MAP.md, docs/design/paper-engine.md and docs/upgrade-plan-desk-v2.md each start with "Historical design record". docs/FOUNDATION_STACK.md has no banner and is not in the DOC-04 set.
- TODO-BACKLOG.md and MILESTONE-AUDIT.md say the sweep gives "9 hits". That is the docs/ count only. A case-insensitive sweep of .planning/ adds 29 lines (rows 10-38, including the seven TODO-BACKLOG table rows 17-23). Those lines do not change any disposition.
- Minor description mismatches in TODO-BACKLOG.md (no disposition change): row 3 says the match is in a table, but the matched text is in prose ("LiveExecutor TODO comment"). Row 8 quotes "the order is rejected", but the matched text is "(vendor TODO at executor.py:151-156 ...)". Row 9 describes an `_audit` line, but the matched text is "six-step vendor TODO (executor.py:151-162)".

## Observations (outside the marker set; not dispositioned)

- The word `not-yet-implemented` is a live status string, not a marker: src/pumpgrok/cli/errors.py:53 (`"status": "not-yet-implemented"`), src/pumpgrok/cli/wiring.py:67 and :188 ("return not-yet-implemented (Phase 4 orchestration). No tool implementation"), and src/pumpgrok/doctor.py:79 and :104. It is emitted by stub or unimplemented verbs and by doctor. Whether any shipped verb depends on it is not verified here. The main agent may want to check it against the release path.

## Not verified

- services/, ci/, skills/, agents/ and contracts/ were not searched (outside this assignment). The STATE.md claim of zero markers there was not re-checked.
- CHANGELOG.md was not inspected, so the "two CHANGELOG hash placeholders" exception (row 38) was not checked.
- Contents of v2 phase files were read only at the hit lines and their headings, not in full.
- The grep included __pycache__ directories in src, tests and scripts. Those are generated; they produced no marker hits, and the matches for "not-yet-implemented" and "NotImplementedError" came from binary bytecode. No .py source hit was missed.
- The contents of src/pumpgrok/execution/live/live_adapter.py were not read in full. Its existence was confirmed. Row 28 relies on the research note's status column, not on a re-read of that file.
