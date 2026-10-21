---
phase: 03-tools-and-skills
plan: "06"
subsystem: 35-skill-set
tags: [SKILL-001, SKILL-002, SKILL-004, B10, prompts, agents]
requires:
- phase: 03-tools-and-skills plan 04
  provides: [ten seat manifests with R35 sizes, 37-tool registry shape]
provides:
- 12 new skills under skills/ with B10 bots and granted required_tools
- 23 retrofitted skills (required_tools, permissions, B10 bots/gates)
- tests/test_skill_manifests.py SKILL-002 suite (SC1 file 1)
- prompt loader load=always plus tools contract, regenerated prompts-assembled and agents
- 35-skills counts in 4 plugin manifests plus skills and root READMEs
affects: [03-07]
status: complete
actuals:
  tokens: 28000
  tasks: 4
  commits: 6
  plan_head_before: 098f26c
tech-stack:
  added: []
  patterns: [frontmatter-is-manifest, B10 bots rule, load-always skills, tools-contract element]
key-files:
  created: [skills/verification-receipts/SKILL.md, skills/paper-broker/SKILL.md, skills/replay-and-backtest/SKILL.md, skills/live-gate-procedure/SKILL.md, skills/kill-switch/SKILL.md, skills/rpc-hygiene/SKILL.md, skills/key-custody/SKILL.md, skills/safety-scoring/SKILL.md, skills/momentum-signals/SKILL.md, skills/portfolio-ledger/SKILL.md, skills/daily-report/SKILL.md, skills/desk-doctor/SKILL.md, tests/test_skill_manifests.py]
  modified: [skills/*/SKILL.md, scripts/prompt_sources.py, scripts/assemble-prompts.sh, prompts/bot-0*.xml, prompts-assembled/*.xml, agents/*.md, plugin.json, .claude-plugin/plugin.json, .grok-plugin/plugin.json, .grok-plugin/marketplace.json, skills/README.md, README.md]
decisions:
- "B10 applied as listing-AND-grants: bots = seats whose prompt skills list contains the skill AND that hold every required_tools entry; grant violations shrink bots, never roster edits"
- "Prompt skills = roster manifest skills plus four table-fidelity additions (desk-operating-model to 9 seats, grokbot-pipeline to JOURNAL, desk-strategy-lab to EXIT/SIGNAL, replay-and-backtest to EXIT); desk-post-trade-review removed from CHIEF prompt"
- "kill-switch required_tools is risk.halt_status only (CHIEF gets halt_status, never kill_switch); paper-broker required_data uses jupiter, never jupiter_lite"
- "desk-doctor permissions are read even though desk.doctor is a paper-write tool, per plan tracer instruction"
requirements-completed: [SKILL-001, SKILL-002, SKILL-004]
coverage:
- id: D1
  description: "Tracer: desk-doctor parses to SkillManifest with name==dirname, non-LIVE_WRITE permissions, L1/L2/Failure/References body under 350 lines"
  requirement: "SKILL-001"
  verification:
  - kind: unit
    ref: "tests/test_skill_manifests.py (desk_doctor selector, 4 passed with SC1 file 2)"
    status: pass
  human_judgment: false
- id: D2
  description: "SKILL-002 suite: 35 dirs parse, name==dirname, granted-tools under B10 bots, LIVE_WRITE refused, fixtures exist, new-12 present, no forbidden strings, journal grep"
  requirement: "SKILL-002"
  verification:
  - kind: unit
    ref: "tests/test_skill_manifests.py (162 passed with tests/test_bot_manifests.py)"
    status: pass
  human_judgment: false
- id: D3
  description: "SKILL-004: seat prompts list load=always skills plus tools contract, assembled XML carries contract attr, agents regenerated, 35 count everywhere"
  requirement: "SKILL-004"
  verification:
  - kind: unit
    ref: "bash scripts/assemble-prompts.sh --check; python3 scripts/generate-templates.py --check; SC2 literal"
    status: pass
  human_judgment: false
metrics:
  duration: 10min
  completed: 2026-10-21
  tasks: 4
  files_modified: 65
  tests_added: 16
  tests_passing: 162
---

# Phase 3 Plan 06: 35-Skill Set Summary

**Twelve new skills authored, 23 existing retrofitted to the B10 bots rule with granted required_tools and non-LIVE_WRITE permissions, SKILL-002 manifest suite green, prompts and agents regenerated with load=always skills and tools contracts, 35-skills count consistent across plugins and READMEs.**

## Performance

- **Duration:** 10 min (13:53-14:03 UTC, first to last task commit)
- **Started:** 2026-10-21T13:53:58Z
- **Completed:** 2026-10-21
- **Tasks:** 4 (1 tracer, 1 tdd, 2 auto)
- **Files modified:** 65 (12 created skills, 1 created test, 23 retrofits, 10 prompts, 10 assembled, 10 agents, 2 scripts, 4 plugin manifests, 2 READMEs)

## Accomplishments

- `tests/test_skill_manifests.py`: SKILL-002 suite asserting 35 skill dirs parse to `SkillManifest` with `name == dirname`, description and body budgets, L1/L2/Failure/References headings, every `required_tools` entry registered and granted to every listed bot (`all` expanded to the ten seats, `exec.*` expanded against the roster), `max_side_effect != LIVE_WRITE`, fixtures paths exist, new-12 names present, `required_data` from the known source set, no `jupiter_lite`/`lite-api`/`--max-micro` strings, and the SC2 journal-ownership grep.
- 12 new skills per interfaces 3.2, each with L1 Summary plus decision tree, numbered L2 S-steps naming `pumpgrok` verbs or catalog tools, Failure modes table, References, ASCII-only bodies under 100 lines.
- 23 retrofits: `required_tools` from the interfaces 3.1 column plus `permissions` (paper-write iff a required tool writes), bots/gates resolved by B10, stale `tools/*.py` and `/workspace/` references replaced with catalog tools and `pumpgrok` verbs.
- `scripts/prompt_sources.py`: `load_seat` accepts `load="always"` (default) on `<skill>` and requires `<tools contract="contracts/tool-rosters/<seat>.yaml"/>`, validated against the roster file on disk.
- All ten seat prompts list load=always skills and the tools contract; `prompts-assembled/*.xml` carry the `contract` attribute on `<roster>`; `agents/*.md` regenerated; both `--check` modes clean.
- `23 skills` becomes `35 skills` in `plugin.json`, `.claude-plugin/plugin.json`, `.grok-plugin/plugin.json`, `.grok-plugin/marketplace.json`; `skills/README.md` gains the Paper Trading and Safety table with corrected primary users; root `README.md` lines 5 and 12 updated.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Key-custody description colon broke YAML frontmatter**
- **Found during:** Task 2 GREEN run
- **Issue:** Unquoted `description` containing `: ` parsed as a mapping, failing `SkillManifest` validation for one new skill.
- **Fix:** Quoted the description string; restored the `name` line clobbered by the first fix attempt.
- **Files modified:** skills/key-custody/SKILL.md
- **Commit:** de00aae

**2. [Rule 3 - Blocking] Loader edit dropped the body-parts block**
- **Found during:** Task 4 regeneration
- **Issue:** The `<tools contract>` hunk replaced the `<body>` parts parser, so `load_seat` raised `NameError: parts`.
- **Fix:** Re-inserted the parts block between contract validation and `SeatSource` construction.
- **Files modified:** scripts/prompt_sources.py
- **Commit:** 839bc9e

### B10 Resolutions (binding rule, not deviations)

Grant violations shrink bots; prompt listings expand where grants allow:
- `risk-audit` bots `[bot-02-risk]` to `[bot-05-rug]` (RISK holds no `safety.*` or `onchain.*` grants, R35 note).
- `desk-incident-response` `[all]` to `[bot-00-chief, bot-02-risk]`; `desk-monitoring` drops RUG; `desk-post-trade-review` drops CHIEF and EXIT; `browser-ops` drops SCOUT; `solana-market-data` drops RISK; `solana-rpc-and-wallet` drops RISK and adds EXIT; `solana-api-reference` drops RISK; `position-monitoring`, `holder-and-flow-analysis` drop EXIT and RISK; `pumpgrok-setup` and `tool-connections` narrow to CHIEF; `desk-trade-lifecycle` `[all]` to `[chief, scout]`; `desk-risk-limits` gates to `[G-2]`; `desk-incident-response`, `grokbot-pipeline`, `hermes-cron-desk`, `tool-connections`, `desk-operating-model` gates to `[]`.
- `social-sentiment` expands to `[bot-07-shill, bot-01-scout]` (SCOUT lists it AND holds both grants; strict B10 includes it).
- `desk-post-trade-review` removed from the CHIEF prompt (roster never listed it, CHIEF holds no grants); EXIT keeps its listing as a consumer but stays out of bots.
- Prompt-side additions to match the interfaces tables where grants allow: `desk-operating-model` to 9 seats, `grokbot-pipeline` to JOURNAL, `desk-strategy-lab` to EXIT and SIGNAL, `replay-and-backtest` to EXIT. Roster manifests untouched (03-04 artifacts, out of this plan's file list).

Or: "None - plan executed exactly as written" does not apply; the above are the tracked B10 resolutions.

## Verification

- `uv run pytest -q tests/test_skill_manifests.py tests/test_bot_manifests.py` exits 0 (162 passed).
- `test "$(ls -d skills/*/ | wc -l)" -eq 35` exits 0; `grep -q 'bot-09-journal' skills/desk-post-trade-review/SKILL.md` exits 0; `! grep -rn "23 skills" plugin.json .claude-plugin .grok-plugin .cursor-plugin agents` prints nothing.
- `bash scripts/assemble-prompts.sh --check` exits 0; `python3 scripts/generate-templates.py --check` exits 0; `./scripts/check.sh` exits 0 (35 skills, 10 agents).

## Known Stubs

None. Every skill body is complete prose with real tool references; no placeholders, TODOs, or empty sections.

## Threat Flags

None. Skill frontmatter claims are validated, not trusted: the suite asserts every `required_tools` entry is registered and granted to every listed bot (T-03-06-01), `SkillPermissions` plus the suite refuse `LIVE_WRITE` (T-03-06-02), and the SC2 grep pins the count strings (T-03-06-03). No new dependencies; prompt scripts extended, not replaced.

## Self-Check: PASSED

- All 12 created skills and the test file exist on disk.
- All 6 plan commits resolve in `git log` (ff9fa56, c339c0e, 657c94b, de00aae, 61076fc, 839bc9e).
- `git status --short` shows only the SUMMARY file (to be committed next) plus pre-existing untracked planning entries.
