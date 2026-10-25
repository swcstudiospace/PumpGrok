# Phase 7 Verification: Documentation upgrade

Status: passed. All nine roadmap success criteria verified against the tree at
HEAD 8e32f14 or against orchestrator gate logs read, not rerun.

Scope: Phase 7 goal is that CLAUDE.md, AGENTS.md, README, ARCHITECTURE, SETUP,
the replay skill, the plugin version statements and the vendor pin describe the
code as fixed by Phase 6, and historical design records say so in a banner.
Requirements DOC-01 to DOC-04. PRC-01 is covered by criterion 1.

Method: read-only. No gate rerun per brief. Evidence is grep output, file reads,
and the orchestrator logs at paths TMP_F7_LINT, TMP_F7_TYPE, TMP_F7_TEST,
TMP_F7_CHECK, TMP_F7_VDC, TMP_F7_SMOKE and TMP_F7_LIVE under /tmp.

## Criteria table

| Num | Criterion summary | Verdict | Evidence |
|-----|-------------------|---------|----------|
| 1 | lint, typecheck, test, check.sh each exit 0; one-shot paper replay exits 0 | PASS | /tmp/f7_lint.log shows ruff check All checks passed plus format clean on 665 files. /tmp/f7_type.log shows mypy Success no issues in 159 source files. /tmp/f7_test.log shows full pytest run to 100 percent with dots and 2 skips, no failure marks, exit 0 per orchestrator. /tmp/f7_check.log shows ok 35 skills, 10 agents, 259 markdown files checked, repository healthy. /tmp/f7_vdc.log shows PASS for one-shot run with paper once replay on smoke fixture, exit 0. |
| 2 | CLAUDE.md carries at least 9 of the named section headings | PASS | grep count of the nine heading alternatives in /root/src/repos/pumpgrok/CLAUDE.md returns 9. File is 107 lines. |
| 3 | Every CLAUDE.md bullet cites a backticked path | PASS | Pipeline listing bullet lines of /root/src/repos/pumpgrok/CLAUDE.md and filtering for lines without a backtick returns no output. |
| 4 | AGENTS.md shorter than origin/main, links CLAUDE.md, no placeholder | PASS | /root/src/repos/pumpgrok/AGENTS.md is 133 lines versus 423 lines for origin/main AGENTS.md. It contains one CLAUDE.md pointer. Case-insensitive placeholder count is 0. GSD marker blocks project-start, project-end, workflow-start, workflow-end are kept verbatim. |
| 5 | verify_doc_commands.sh exits 0 | PASS with noted narrowing, see deviations | /tmp/f7_vdc.log tail shows pass equal 2, skip equal 9, fail equal 0. The two PASS lines are the one-shot paper replay and doctor. /root/src/repos/pumpgrok/scripts/verify_doc_commands.sh at lines 149 to 159 matches any serve command and records SKIP with a help-flags check, never executing it. Make targets, check.sh, uv sync and docker entries are likewise listed but skipped with a stated reason. |
| 6 | tests/docs green: versions, VENDOR_PIN, CLI verbs, contradictions | PASS | Full suite exit 0 in /tmp/f7_test.log covers /root/src/repos/pumpgrok/tests/docs. Test file /root/src/repos/pumpgrok/tests/docs/test_doc_consistency.py defines four tests: manifest versions match pyproject, vendor pin plus retirement wording, documented verbs exist in CLI help, no contradiction strings. All four plugin manifests carry version 0.1.0 matching pyproject.toml version 0.1.0, confirmed by grep. docs/VENDOR_PIN.md contains pin 409e74c905faa0e9de42e918efe2c604f206856e exactly once. |
| 7 | Historical banner test green; records begin with the banner | PASS | /root/src/repos/pumpgrok/tests/docs/test_historical_banners.py fixes a five-file set and requires first line Historical design record. First lines confirmed: /root/src/repos/pumpgrok/docs/DISCOVERY.md, /root/src/repos/pumpgrok/docs/MIGRATION_MAP.md, /root/src/repos/pumpgrok/docs/upgrade-plan-desk-v2.md, /root/src/repos/pumpgrok/docs/design/interfaces.md, /root/src/repos/pumpgrok/docs/design/paper-engine.md all begin with Historical design record. Full suite exit 0 implies the banner test passes now that 07-06 bannered the two design files. |
| 8 | CHANGELOG carries at least 4 DOC-01 to DOC-04 tags | PASS | grep count of DOC-01 through DOC-04 in /root/src/repos/pumpgrok/CHANGELOG.md returns 4. The Phase 7 section sits above the Phase 6 section. |
| 9 | Replay hash unchanged; Phase 7 hash line with the same value | PASS | /root/src/repos/pumpgrok/CHANGELOG.md line 16 records Phase 7 smoke-10m events.hash after b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d. Lines 34 to 35 record Phase 6 before and after with the identical value. Orchestrator brief states both verify runs at HEAD produced that hash, identical to the Phase 6 after-hash. /tmp/f7_smoke.log itself carries the one-shot run output, not the verify hash, so hash equality rests on the orchestrator statement plus the CHANGELOG lines. |

## Spot checks: five plus additional factual claims

Each claim below was checked with grep or read against the source. Tests would not
catch most of these because they are prose claims, not machine-checked strings.

1. Ten seats, ten role files. CLAUDE.md, README.md line 5, ARCHITECTURE.md line 7
   and SETUP.md claim ten seats. PASS: /root/src/repos/pumpgrok/agents holds
   chief, exit, journal, risk, rug, scout, shill, signal, sniper, whale plus
   README, that is ten seat files. SETUP.md section 5 names SIGNAL and JOURNAL.
2. Thirty-five skills. README.md line 5 and line 12 claim 35 skills. PASS:
   directory count under /root/src/repos/pumpgrok/skills is 35. The phantom
   twenty-three-skills claim named in early notes was correctly not invented as
   a correction; grep finds no twenty-three in README.
3. No RPC flag; env form is PUMPGROK_RPC__ENDPOINTS. ARCHITECTURE.md lines 28,
   29, 204 and SETUP.md line 139 use the env name. PASS: grep for the double
   quoted rpc flag under /root/src/repos/pumpgrok/src and
   /root/src/repos/pumpgrok/scripts returns 0 matches; settings module
   /root/src/repos/pumpgrok/src/pumpgrok/config/settings.py uses the PUMPGROK
   prefix with nested delimiter.
4. market.price is bonding-curve getAccountInfo, no Jupiter path in module.
   PASS: /root/src/repos/pumpgrok/src/pumpgrok/tools/market/price.py lines 1
   to 8 state exactly that; the single case-insensitive jupiter match in that
   file is the denial sentence itself. Jupiter QUOTE_URL lives only in
   /root/src/repos/pumpgrok/src/pumpgrok/tools/market/jupiter.py as the
   informational quote.
5. Serve needs replay without once; one-shot needs once plus replay. PASS:
   /root/src/repos/pumpgrok/src/pumpgrok/cli.py lines 581 to 596 implement both
   branches with not-implemented messages. SKILL.md lines 23, 33 and 49 use the
   once form and note the serve variant, matching the code.
6. SETUP and ARCHITECTURE RPC wording. PASS: PUMPGROK_RPC__ENDPOINTS appears in
   SETUP.md once and ARCHITECTURE.md twice, per S8 output above.
7. Banned contradiction strings absent from the four docs. PASS: case
   insensitive sweep for eight-role, no server queue or daemon sentence,
   Nothing in this repo is started as a service, the rpc flag, same code path
   as live paper, identical path, identical fill across README.md,
   ARCHITECTURE.md, SETUP.md and SKILL.md returns no output.
8. Plugin manifests version 0.1.0. PASS: all four manifests under
   /root/src/repos/pumpgrok/plugin.json, /root/src/repos/pumpgrok/.claude-plugin/plugin.json,
   /root/src/repos/pumpgrok/.cursor-plugin/plugin.json,
   /root/src/repos/pumpgrok/.grok-plugin/plugin.json carry version 0.1.0,
   matching /root/src/repos/pumpgrok/pyproject.toml version 0.1.0.
9. Banner lines. PASS: all five files named in the criterion 7 row begin with
   exactly Historical design record, verified by head.

No stale or wrong claim was found in the sampled statements. One wording note:
CLAUDE.md line 12 area and line 38, 63, 96 were already corrected in commit
5c068e3 per the 07-01 summary; the current tree carries the corrected wording.

## Deviation judgements: OVERRIDE-A through OVERRIDE-D

1. OVERRIDE-A: manifests set to 0.1.0, schema URL untouched. JUSTIFIED. The
   schema URL ending in 1.0.0 names the plugin schema version, a different
   namespace from the package version. Criterion 6 requires manifest versions
   to match pyproject.toml, which they now do in all four files.
2. OVERRIDE-B: no vendored snapshot searched; pin line kept, present-tense
   vendored statements corrected to past tense with Phase 4 STRUCT-006
   retirement. JUSTIFIED. Directory /root/src/repos/pumpgrok/vendor is absent
   from the tree, so a snapshot comparison is impossible; keeping the pin as a
   historical provenance record is the honest alternative, and the pin line is
   byte-identical.
3. OVERRIDE-C: eight-role to ten-seat in manifest descriptions; the
   agent-name parenthetical in .claude-plugin left as-is. JUSTIFIED. The core
   contradiction is fixed in all four manifests; the parenthetical names agent
   host products and is outside the override scope. No criterion depends on it.
4. OVERRIDE-D: consistency test asserts pin plus retirement wording instead of
   snapshot match, and references no vendor directory path. JUSTIFIED for the
   same reason as OVERRIDE-B. Requirement DOC-03 wording still holds because
   the vendor pin record now matches reality: retired tree, preserved pin.

## Criterion 5 wording judgement

Roadmap text says the script runs each command in the Commands sections and
checks its documented exit code. The script as built RUNS only finite offline
commands, doctor and the one-shot paper replay, and LISTs without executing
make targets, check.sh, uv sync, docker and any serve loop. This is a NARROWING
of the letter of the wording, forced by two higher constraints: Phase 7 hard
constraint 1 forbids running the whole-repo suite from a task, and the serve
loop is long-lived by design. The acceptance predicate, script exits 0, is met
with fail equal 0, and every skip is labeled with its reason in the log. The
narrowing is documented, not hidden. Verdict on criterion 5 remains PASS.

## Verify script safety check

/root/src/repos/pumpgrok/scripts/verify_doc_commands.sh never executes run
with serve. The serve pattern at line 149 routes to a skip path that only runs
pumpgrok run help to confirm the flags exist. No eval of extracted commands
reaches a serve invocation. Confirmed by read of lines 140 to 165.

## AGENTS.md check

/root/src/repos/pumpgrok/AGENTS.md is shorter than origin/main AGENTS.md, 133
versus 423 lines, links /root/src/repos/pumpgrok/CLAUDE.md, contains no
placeholder in any case, and keeps the GSD marker blocks project-start,
project-end, workflow-start and workflow-end verbatim.

## Not verified / context only

1. Replay hash equality across the two verify runs was not independently
   reproducible under the brief rules; it is accepted from the orchestrator
   statement plus the matching CHANGELOG lines. No contrary evidence was found.
2. Live refusal exit 3 in /tmp/f7_live.log is context, not a Phase 7 criterion:
   the log shows the nine-precondition refusal text. Phase 7 keeps live
   disabled by doing nothing to live paths.
3. Phase 6 receipt and gate state, G-1 and G-2 failures, are owned by the
   orchestrator and are not Phase 7 criteria. They do not affect this verdict.
4. Visual rendering of banners and docs needs no human check beyond the
   first-line greps; no human verification items are raised.

## Gaps

None. No gaps_found list. Status passed.
