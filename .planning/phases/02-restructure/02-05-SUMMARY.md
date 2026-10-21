---
phase: 02-restructure
plan: "05"
subsystem: skills-instruction-pack
tags: [struct-007, sec-003, skills, signing-guard, docs]
requires: [02-03]
provides: [skill-bots-gates-pack, signing-ast-guard, setup-runbook]
affects: [phase-3-tool-verbs, phase-4-execution]
tech-stack:
  added: []
  patterns: ["SkillManifest frontmatter (bots/gates) parsed by pydantic", "exact-equality AST walk for signing symbols"]
key-files:
  created:
    - tests/safety/test_no_signing_outside_live_stub.py
    - docs/runbooks/setup.md
  modified:
    - skills/jupiter-routing/SKILL.md
    - skills/desk-execution-protocol/SKILL.md
    - skills/desk-folders-and-journal/SKILL.md
    - skills/desk-incident-response/SKILL.md
    - skills/desk-monitoring/SKILL.md
    - skills/desk-operating-model/SKILL.md
    - skills/desk-post-trade-review/SKILL.md
    - skills/desk-risk-limits/SKILL.md
    - skills/desk-strategy-lab/SKILL.md
    - skills/desk-trade-lifecycle/SKILL.md
    - skills/discovery-tools/SKILL.md
    - skills/grokbot-pipeline/SKILL.md
    - skills/hermes-cron-desk/SKILL.md
    - skills/holder-and-flow-analysis/SKILL.md
    - skills/position-monitoring/SKILL.md
    - skills/pumpgrok-setup/SKILL.md
    - skills/risk-audit/SKILL.md
    - skills/social-sentiment/SKILL.md
    - skills/solana-api-reference/SKILL.md
    - skills/solana-market-data/SKILL.md
    - skills/solana-rpc-and-wallet/SKILL.md
    - skills/tool-connections/SKILL.md
    - tools/README.md
    - ARCHITECTURE.md
    - AGENTS.md
    - README.md
    - SETUP.md
    - rules/pumpgrok-team.mdc
    - plugin.json
    - .claude-plugin/plugin.json
    - .grok-plugin/plugin.json
    - .cursor-plugin/plugin.json
    - scripts/check.sh
decisions:
  - Winning bots/gates table is MIGRATION_MAP sec 4.2, confirmed consistent with ROSTER seat skill lists; no conflict found
  - required_tools left empty on all skills; no roster coupling to break
  - Prompts and agents templates regenerated as a no-op (no Russian vendor text in prompts)
metrics:
  duration: 1 working session
  completed: 2026-10-21
  tasks: 3
  commits: 3
  plan_head_before: 588166d
status: complete
actuals:
  tokens: 26178
  tasks: 3
  commits: 3
  plan_head_before: 588166d
---

# Phase 02 Plan 05: Skills Rewrite and Signing Guard Summary

All 23 skills carry `bots`/`gates` frontmatter with L1/L2 bodies and parse as SkillManifest. The Jupiter skill describes the quote-only `api.jup.ag/swap/v2/order` path feeding `exec.quote`/`exec.place`; `lite-api`, `--max-micro`, and `micro-live` are gone from skills, rules, and top-level docs. The SEC-003 AST guard fails on any `sign`, `send_transaction`, `sendTransaction`, or `Keypair` symbol outside `execution/live/`. SC3 and SC5 green.

## Tasks Completed

| # | Task | Commit | Verify |
|---|------|--------|--------|
| 1 | Tracer: jupiter-routing skill rewritten end-to-end | 4fd71b4 | SkillManifest parse OK (bots sniper/exit, gates G-6) |
| 2 | Remaining 22 skills, prompts, manifests, and docs | 51f860e | SC3 exit 0; check.sh exit 0; oracle 11 passed |
| 3 | SEC-003 signing AST guard | 560081f | guard test 14 passed; full suite 328 passed |

## Verification Evidence

- SC3 (plan literal): `test "$(grep -l '^bots:' skills/*/SKILL.md | wc -l)" -eq 23 && test "$(grep -l '^gates:' skills/*/SKILL.md | wc -l)" -eq 23 && ! /usr/bin/grep -rn -e lite-api -e '--max-micro' skills/` -> exit 0 (`skills/README.md` is a file, so grep prints two stderr noise lines and still exits 0).
- All 23 skills parse as SkillManifest (name equals directory, description within 1024, body within 350 lines, sections L1/L2/Failure modes/References present) -> 23 OK.
- No `micro-live` in skills, rules, README, ARCHITECTURE, AGENTS, SETUP, tools/README, runbook -> exit 0.
- `./scripts/check.sh` -> exit 0 (`ok: 23 skills, 10 agents, 129 markdown files checked`).
- Root oracle `tests/test_tools_cli.py` -> 11 passed, including both TicketHelperDocs assertions (skill keeps `ticket_helper.py next`/`create`, README keeps `next`).
- `python3 scripts/generate-templates.py --check` and `./scripts/assemble-prompts.sh --check` -> both clean, no drift.
- SC5: `tests/safety/test_no_signing_outside_live_stub.py` -> 14 passed (tree scan, stub import/name assertions, 11 probes, scratch-copy test).
- Regression: full `tests/` suite -> 328 passed (314 prior plus 14 new).
- Note on invocation: bare `uv run pytest -q <file>` collects nothing in this shell (a `-q` collection quirk, exit 0, false green). All pytest evidence above uses `-o addopts="--strict-markers"` without `-q`, which collects correctly. The SC5/SC3 shell commands themselves are unaffected (SC3 is grep-based).
- Note: plan verify names `tests/test_skill_manifests.py`, which does not exist in the repo. Used the equivalent check instead: every SKILL.md parsed through `SkillManifest(**yaml.safe_load(frontmatter))`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Freed 456 MB by deleting the regenerable pip cache (`~/.cache/pip`).**
- Found during: task 2 verification (oracle test run).
- Issue: disk 100% full (`/dev/sda1` 0 avail, `/tmp` 17 GB); Python `tempfile` failed with a misleading `FileNotFoundError: No usable temporary directory` (real cause ENOSPC on write), so no pytest run could start.
- Fix: `rm -rf ~/.cache/pip` (pure cache, regenerable). `/tmp` contents and sibling repos left untouched.
- Recorded here so the disk pressure is visible to the orchestrator.

**2. [Rule 3 - Blocking] Fixed pre-existing emoji failures blocking the plan's own `check.sh` gate.**
- Found during: task 2 verification (`./scripts/check.sh` exited 1 at baseline).
- Issue: `check.sh` fails on checkmark/cross characters in tracked `.planning/PROJECT.md:24` and 19 lines of `02-RESEARCH.md` (Environment and criteria tables), all predating this plan.
- Fix: replaced with ASCII `yes`/`no`/`[x]` wording, no meaning changed. No STATE.md or ROADMAP.md touched.

**3. [Rule 3 - Blocking] Shrunk the `your-org` allowlist in `scripts/check.sh`.**
- Found during: task 2 manifest edits.
- Issue: `check.sh` errors when an allowlisted file no longer contains the placeholder; updating `plugin.json` and `ARCHITECTURE.md` to `swcstudiospace` would have failed the plan's own regression gate.
- Fix: removed those two entries; marketplace JSONs and SETUP.md keep the placeholder and stay listed.

**4. [Rule 2 - Missing critical] Created `docs/runbooks/setup.md`.**
- Found during: task 2.
- Issue: plan lists it as a produced artifact but the file did not exist; STRUCT-007 expects the setup runbook to describe `src/pumpgrok/`.
- Fix: wrote a concise runbook (quick start, setup outputs, engagement rules, references). No new scope beyond the plan file.

### Structural notes (not deviations from intent)

- Prompts (`prompts/bot-*.xml`, `_shared/core-directives.xml`) and `agents/*.md` needed no content change: no Russian vendor text exists in prompts (verified by grep), and regenerate scripts confirm zero drift. `agents/chief.md` is therefore unchanged.
- `required_tools` left empty on all 23 skills (Schema default). The plan's key link (tools granted to every listed bot) holds vacuously; no roster coupling introduced.
- `docs/runbooks/` is new; only `setup.md` was created per the plan file list.

## Key Decisions

- Winning bots/gates table: MIGRATION_MAP sec 4.2 verbatim (jupiter-routing: sniper/exit, G-6; desk-incident-response: all, G-2/G-5; full table in the plan). Cross-checked against `docs/ROSTER.md` seat skill lists and `contracts/tool-rosters/*.yaml` tool names; ROSTER documents seat-to-skill ownership consistently with 4.2, so no conflict resolution was needed.
- Jupiter: R44 removes the v1 path rather than flagging it. AGENTS.md historical probe lines reframed as retired dated records; prescriptive lines now name only `api.jup.ag/swap/v2/order` with `x-api-key`.
- Oracle wording: `desk-trade-lifecycle` keeps `ticket_helper.py next`/`create` and `tools/README.md` keeps `next` plus a note documenting that the root oracle pins that wording while new automation prefers `pumpgrok ticket` verbs (Open Q10).
- Manifest org: `swcstudiospace` with `https://github.com/swcstudiospace/PumpGrok` matching the git remote and `pyproject.toml` Homepage; license `AGPL-3.0` matching root LICENSE (Open Q17). Marketplace JSONs and SETUP.md keep `your-org` (out of plan scope) and remain on the check.sh allowlist.
- Engagement vocabulary is now `research`/`paper` only; `micro-live` removed everywhere including `rules/pumpgrok-team.mdc:46` and SETUP.md (R42, Open Q19).

## Known Stubs

None. No TODO/FIXME/placeholder text in created or modified files; every skill body wires real tools, gates, and handoffs. `docs/runbooks/setup.md` points at existing `SETUP.md` and real CLI verbs.

## Threat Flags

None beyond the plan threat model (T-02-13/14/15, T-02-SC): no new network endpoints, no key material in prompt or skill text (Jupiter key referenced only as the `JUPITER_API_KEY` SecretStr setting name), no transaction-building code, no new packages. The guard itself is a test file scanning `src/pumpgrok` only.

## Self-Check: PASSED

- All 23 rewritten skills plus `tools/README.md`, `docs/runbooks/setup.md`, and the guard test exist on disk.
- Commits 4fd71b4, 51f860e, 560081f present in `git log`.
- SC3 command exit 0; guard test 14 passed; full suite 328 passed; `check.sh` exit 0.
