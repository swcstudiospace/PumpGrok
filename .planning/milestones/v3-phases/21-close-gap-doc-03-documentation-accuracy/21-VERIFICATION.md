---
status: passed
phase: 21-close-gap-doc-03-documentation-accuracy
requirements:
  - DOC-03
verified_at_commit: da51664
method_notes: >
  Independent verification by a separate agent against worktree
  /root/src/repos/pumpgrok-wt/v3-closeout (branch bot-00-chief/v3-closeout, HEAD da51664).
  Test counts were read from junit XML (/tmp/p21b-red.xml, /tmp/p21b-docs.xml);
  console pytest summaries were not used. Red state was reproduced from the
  commit 1128f0a tree (test commit, documents still at e58920b state) in a scratch
  copy under /tmp/p21b-red, which was removed afterwards. The red run covered the whole
  tests/docs directory (44 tests); both failures are in tests/docs/test_doc_consistency.py.
  make test and the full suite were not run. Product code diff since 9cb6e66 over
  src tests Makefile pyproject.toml uv.lock ci scripts is empty. The residual scan was
  run with grep over the five named documents; each hit was classified against the code.
  Every gate command was run from the worktree. Changes to the worktree: none
  (git status shows only the pre-existing .planning modifications and this file).
---

# Phase 21 verification: DOC-03 documentation accuracy

## Status

**passed.** Checks 1 to 6 pass. Check 4 has no unresolved contradiction in the
named documents (README.md, ARCHITECTURE.md, SETUP.md, skills/replay-and-backtest/SKILL.md,
docs/VENDOR_PIN.md). The two earlier gaps recorded in the gaps_found version of this file
(the "read-only" statements, fixed in fd8a707) are closed and re-checked below.

Two points are recorded for the orchestrator and are not failures under the stated acceptance
rule (see "Residual notes"):

- The CHANGELOG entry records corrections by document. DOC-03 says "each change appears in
  CHANGELOG.md". The row-level list (47 rows) lives in 21-01-SUMMARY section 3, not in CHANGELOG.md.
- docs/VENDOR_PIN.md:9 names the absent `vendor/grokbot-pumpfun/LICENSE` path. It is judged
  correct historical provenance, not a contradiction.

No document or product file was edited by this verification.

## Criteria

| # | Command | Exit | Result | Verdict |
|---|---------|------|--------|---------|
| 1 | `git archive 1128f0a \| tar -x -C /tmp/p21b-red`; `cd /tmp/p21b-red && uv run --project /root/src/repos/pumpgrok-wt/v3-closeout python -m pytest tests/docs -q --junitxml=/tmp/p21b-red.xml` | 1 | junit suite pytest: tests=44 failures=2 errors=0 skipped=0. Failing: `test_plugin_manifest_versions_match_pyproject` (`.claude-plugin/marketplace.json` version `'1.0.0' != '0.1.0'`) and `test_plugin_manifest_descriptions_avoid_eight_role` (`.claude-plugin/marketplace.json` description begins "Eight-role Solana memecoin trading desk"). Each test stops at its first failing manifest; `.grok-plugin/marketplace.json` also carried version 1.0.0 and "Eight-role" at 1128f0a. Scratch directory /tmp/p21b-red removed (verified). | PASS |
| 2 | `uv run python -m pytest tests/docs -q --junitxml=/tmp/p21b-docs.xml` | 0 | junit tests=44 failures=0 errors=0 skipped=0 | PASS |
| 3 | Manifest versions and descriptions: `pyproject.toml:3` version; each plugin entry parsed as JSON in `plugin.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, `.grok-plugin/plugin.json`, `.grok-plugin/marketplace.json`; `grep -n -i eight` over the six files | 1 (grep, no hits) | pyproject `version = "0.1.0"`. All six manifests carry `0.1.0` on every plugin entry (root `plugin.json` and the three non-marketplace plugin manifests at top level; each marketplace file has one plugin entry, and its top level has no version key). Descriptions: all say "Ten-seat"; no "eight" text in any of the six files. | PASS |
| 4 | `grep -n -i -E 'eight\|ticket_helper\|paper_sim\|/workspace/trading-desk\|vendor/grokbot-pumpfun\|--rpc\|ticket next\|config\.example\.yaml\|read[- ]only\|no server, queue\|started as a service\|market\.price' README.md ARCHITECTURE.md SETUP.md skills/replay-and-backtest/SKILL.md docs/VENDOR_PIN.md`, plus `grep -n -o trading-desk` for the `$HOME` form | 0 (hits present, all classified) | Zero hits for `eight`/`Eight`, `ticket_helper`, `paper_sim`, `/workspace/trading-desk`, `--rpc`, `started as a service`, `no server, queue` in the five documents. `read-only` hits are classified below as correct. No unresolved contradiction. See the classification table. | PASS |
| 5 | ARCHITECTURE.md mermaid check: fence count, and grep for Vendor, Jsonl, Bridge, vendor, jsonl, bridge inside each mermaid block | 0 | Fences: 8 in ARCHITECTURE.md (even). Mermaid blocks at lines 35-51 and 151-164, both closed. The first block has nodes Human, Host, Pack, Desk, Jup, Rpc, Web and edges Human to Host, Host to Pack, Host to Desk, Host to Web, Pack to Jup, Pack to Rpc. No Vendor, Jsonl or Bridge node or edge in either mermaid block. The only match is line 77, inside the plain-text module-map fence (lines 71-79, no language tag): "`pumpgrok scout pipeline` --> not implemented (exit 5); no vendor import", which is not a mermaid node. Fences in other named documents: README.md 4, SETUP.md 14, skills/replay-and-backtest/SKILL.md 2, docs/VENDOR_PIN.md 0 (all even). | PASS |
| 6a | `./scripts/verify_doc_commands.sh` | 0 | `pass=2 skip=9 fail=0` | PASS |
| 6b | `./scripts/check.sh` | 0 | `ok: 35 skills, 10 agents, 321 markdown files checked`; `PumpGrok repository structure looks healthy.` | PASS |
| 6c | `make lint` | 0 | `ruff check .`: All checks passed. `ruff format --check .`: 819 files already formatted. | PASS |
| 6d | `uv run pumpgrok verify --fixture smoke-10m` | 0 | `events.hash=b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`; `verify=CONSISTENT seq=2 events=41`. The hash matches the required value (grep count 1). | PASS |

Additional checks run for this verification (not in the 1-6 list):

| Check | Command | Exit | Result |
|-------|---------|------|--------|
| Product diff since 9cb6e66 | `git diff --stat 9cb6e66 HEAD -- src tests Makefile pyproject.toml uv.lock ci scripts` | 0 | Empty. |
| Scout verb exit | `uv run pumpgrok scout pipeline --candidates` | 5 | `not-yet-implemented` (matches ARCHITECTURE and SETUP). |
| Help forms do not write | Row counts of `var/ledger.sqlite` before and after `uv run pumpgrok ticket next --help` | 0 | Unchanged (events 0, snapshots 0, meta 1). |
| market.price help | `uv run pumpgrok tools market.price --help` | 0 | OK. |
| Added non-ASCII in phase 21 | `git diff -U0 e58920b HEAD` over named docs, CHANGELOG, manifests, tests/docs, CLAUDE.md, filtered to added lines with non-ASCII bytes | n/a | No added non-ASCII lines. |

## Check 4 hit classification

Pattern set as listed in check 4, plus `trading-desk` for the `$HOME` form. Line numbers are HEAD numbers.

| File:line | Hit (abridged) | Verdict | Evidence |
|-----------|----------------|---------|----------|
| README.md:14 | Operator CLI "never signs or sends"; `ticket next` and `create` append a row to `var/ledger.sqlite`; paper-trade commands refuse without writing | Correct | `src/pumpgrok/cli/verbs_state.py:383-384` (`next` calls `allocate_ticket`), `:394-422` (`create` calls `allocate_ticket`); `src/pumpgrok/ledger/tickets.py:22` (`MAX_ATTEMPTS`), `:73` (retry loop); `src/pumpgrok/ledger/paths.py:22` |
| README.md:43 | `uv run pumpgrok tools market.price --help` | Correct | `src/pumpgrok/tools/market/price.py` exists; command exit 0 (this round) |
| README.md:46 | `uv run pumpgrok ticket next --help` | Correct (help form) | Exit 0; ledger row counts unchanged (this round) |
| README.md:52 | Allocate and list tickets with `pumpgrok ticket next`, `create`, `list` | Correct | `verbs_state.py:383-422` |
| README.md:65 | "Formerly the vendored `vendor/grokbot-pumpfun/` tree, retired in Phase 4" | Correct (past tense) | `src/pumpgrok/engine/__init__.py` exists; `vendor/` absent (this round); `docs/VENDOR_PIN.md:3-5` |
| ARCHITECTURE.md:15 | Screening engine: replay-only port; `vendor/grokbot-pumpfun/` absent, formerly vendored | Correct | `vendor/` absent; `src/pumpgrok/engine/__init__.py`; `docs/VENDOR_PIN.md:3-5` |
| ARCHITECTURE.md:18, :55, :217 | "read-only `/healthz` and `/metrics`" | Correct: describes served endpoints, not the CLI | `src/pumpgrok/doctor.py:5` (`GET /healthz`, `GET /metrics` on 127.0.0.1) |
| ARCHITECTURE.md:27, :118 | `market.price` spot read via `getAccountInfo` on the curve account (ASSUMED layout); paper marks through the curve port | Correct | `src/pumpgrok/tools/market/price.py`; `src/pumpgrok/execution/paper_adapter/adapter.py:152` (`_read_curve`); `marks.py:9` imports `curve_math` |
| ARCHITECTURE.md:40, :179, :192, :201, :203, :204 | `$HOME/trading-desk` as the operator host folder | Correct (D-04(c) deviation, accepted in 21-01) | `scripts/hermes-bootstrap.sh:8` `DESK="${PUMPGROK_DESK:-${HOME}/trading-desk}"` (same default in `hermes-install-cron.sh:7`, `hermes-verify-isolation.sh:7`). No `/workspace/trading-desk` string remains in the named documents |
| ARCHITECTURE.md:77 | Module map: `pumpgrok scout pipeline` --> not implemented (exit 5); no vendor import | Correct | Exit 5 (this round) |
| ARCHITECTURE.md:78 | `scripts/check.sh` (read-only validation) | Correct | `scripts/check.sh` opens files only in read mode (lines 14, 87, 104, 149, 168); no `mkdir`, `touch`, `rm`, `mv`, `cp` or shell redirect |
| ARCHITECTURE.md:81 | Retired vendor components; absent; `scout pipeline --candidates` exits 5 | Correct | `vendor/` absent; exit 5 (this round) |
| ARCHITECTURE.md:144, :168, :180, :192 | Ticket IDs from `pumpgrok ticket next` | Correct | `ledger/tickets.py:22, :73`; `verbs_state.py:383-384` |
| ARCHITECTURE.md:201 | `PUMPGROK_DESK` row | Correct | `scripts/hermes-*.sh` `DESK` default (above) |
| ARCHITECTURE.md (rows near :200) | `PUMPGROK_RPC__ENDPOINTS` tools | Correct | `src/pumpgrok/tools/onchain/authorities.py`, `priority_fee.py`, `top_holders.py` exist (this round) |
| ARCHITECTURE.md:244 | "ten seats" (eight wording removed) | Correct | `agents/` holds 10 role files plus README.md |
| SETUP.md:6 | "Setup writes only local folders and files ... `~/trading-desk`" | Correct | Lines 47, 50, 55-56, 168, 184 write under `$HOME` |
| SETUP.md:47, :50, :55, :56, :168, :184 | `~/trading-desk` mkdir, touch, and create steps | Correct | `scripts/hermes-bootstrap.sh:8, :217` (folder list matches line 50) |
| SETUP.md:136, :203 | `uv run pumpgrok ticket next --help` / `pumpgrok ticket next --help` | Correct (help form) | Exit 0; no row written (this round) |
| SETUP.md:147 | Screening engine not vendored; `vendor/grokbot-pumpfun/` absent, formerly vendored | Correct | `vendor/` absent; `docs/VENDOR_PIN.md:3-5` |
| skills/replay-and-backtest/SKILL.md:3, :23, :33 (S2) | `--once --replay` drives supervisor, rule and paper adapter on a fixture clock; the `run_replay` checkpoint writes its verdict row first and does not run the paper adapter | Correct; the D-07 overclaim is not present | `verbs_state.py:104-117` routes `--once --replay` to `_skip_cycle` (`:156-173`), which calls `run_once_replay`; `supervisor/scheduler/serve.py:47-80` (`run_replay` writes the checkpoint row first, per the docstring at `:62`), then `serve_fixture_timeline` (`:145`), where seats place orders through `exec.place` and PaperAdapter (`:66-67`). File last changed at e58920b (no edit needed) |
| docs/VENDOR_PIN.md:3 | "The screening engine formerly under `vendor/grokbot-pumpfun/` ..." | Correct (historical) | Header lines 3-5 |
| docs/VENDOR_PIN.md:9 | "License: MIT (`vendor/grokbot-pumpfun/LICENSE`)" | Correct as historical provenance (judgment; see Residual notes) | Path absent. The MIT text is retained at `src/pumpgrok/engine/LICENSE-grokbot-pumpfun` ("MIT License, Copyright (c) 2026 zostaff"). The pin record is declared historical at lines 3-5 and 10-11 |
| docs/VENDOR_PIN.md:10 | "Moved from: `vendor/grokbot-pumpfun/PUMPGROK.md` ... retired in Phase 4" | Correct (explicit "Moved from") | Same retirement record |
| docs/VENDOR_PIN.md:25 | `config.example.yaml` belonged to the vendored tree and is not in this checkout | Correct | `config.example.yaml` absent (this round) |

Zero hits remain for `ticket_helper`, `paper_sim`, `/workspace/trading-desk`, `--rpc`, `eight`/`Eight`,
`no server, queue` and `started as a service` in the five named documents. The `read-only` wording
removed in fd8a707 (README.md:5, :14, :30; ARCHITECTURE.md:3; SETUP.md:6) is not present; the
remaining `read-only` uses are the served endpoints (ARCHITECTURE.md:18, :55, :217) and check.sh
(ARCHITECTURE.md:78).

## Requirements

| ID | Requirement text (REQUIREMENTS.md:27) | Status | Evidence |
|----|----------------------------------------|--------|----------|
| DOC-03 | README, ARCHITECTURE, SETUP, skills/replay-and-backtest/SKILL.md, plugin version statements and docs/VENDOR_PIN.md match the code. Every contradiction from the 2026-10-25 docs audit is corrected, and each change appears in CHANGELOG.md. | satisfied under the stated acceptance rule; CHANGELOG granularity noted | Plugin versions and descriptions: checks 1-3 (`pyproject.toml:3`; six manifests at 0.1.0; no "eight" text). Named documents: check 4 classification (no unresolved contradiction); check 5 (mermaid). Audit items: `ticket_helper.py` and `paper_sim.py` absent from README, ARCHITECTURE and SETUP (check 4 zero hits); vendor described as absent and formerly vendored (ARCHITECTURE.md:15, :81; SETUP.md:147; README.md:65); "eight persistent Bots" now "ten seats" (ARCHITECTURE.md:244; `agents/` 10 role files); `/workspace/trading-desk` replaced by `$HOME/trading-desk` (`scripts/hermes-bootstrap.sh:8`). CHANGELOG: Phase 21 entry at CHANGELOG.md lines 5-12 lists the manifest fix and corrections for ARCHITECTURE, SETUP, README, VENDOR_PIN, ticket next, and the round 2 read-only and CLAUDE.md fixes, one bullet per document. The replay hash line remains in the Phase 20 entry (check 6d). |

## Residual notes

1. CHANGELOG granularity (orchestrator decision). The Phase 21 entry has one bullet per document,
   not one per correction. Row-level corrections such as ARCHITECTURE "Observability" (run --serve
   /healthz), "PUMPGROK_RPC__ENDPOINTS" tool paths, "jupiter_quote.py" to `tools/market/jupiter.py`,
   the "AGPL-3.0" and organisation URL scoping, and the "No database" sentence are recorded only in
   21-01-SUMMARY section 3, not in CHANGELOG.md. If "each change appears in CHANGELOG.md" is read
   literally, this is a gap, and a follow-up edit to CHANGELOG.md would close it. It does not change
   checks 1-6.
2. docs/VENDOR_PIN.md:9 (judgment). The license line names an absent path. It is judged historical
   provenance: the document header and lines 10-11 declare the tree retired and the file the pin
   record. A one-line repoint to `src/pumpgrok/engine/LICENSE-grokbot-pumpfun` would remove the
   dangling path. Not counted as a contradiction.
3. D-04(c) deviation (accepted, as in 21-01 deviation 2). No repository skill or script uses
   `/workspace/trading-desk`. The `$HOME/trading-desk` form is the default in `scripts/hermes-bootstrap.sh:8`.
4. Claims in ARCHITECTURE.md not checked by this round (listed in 21-01 section 9): "HTTP/RPC
   exceptions become {"ok": false} and the process exits 1", "Tools do not read environment
   variables", and the "no os.environ / .env readers" statement. The buy and sell split at
   ARCHITECTURE.md:18 is consistent with agents/sniper.md (`writes_to_exchange: true`, buys only) and
   agents/exit.md (`writes_to_exchange: true`, sells only); the sell side was read from sniper.md:85.
5. Replay observation (not a doc contradiction). `pumpgrok verify --fixture smoke-10m` reports the
   checkpoint decision as `skip` with `engine_reason: no_metadata` on the fixture. The hash and
   CONSISTENT result are unaffected.
6. Test hardening (not a failure). `test_plugin_manifest_descriptions_avoid_eight_role` matches only
   the hyphenated substring "eight-role". `BANNED_FRAGMENTS` in `test_no_contradiction_strings_in_docs`
   matches "eight-role" and "Eight specialist" only; "Eight roles" and "Eight role" would pass.
7. Count drift. check.sh reports 321 markdown files now; 320 at 9cb6e66 (prior verification) and 319
   in 21-01-SUMMARY. Not a failure.

## Tech debt (outside the named DOC-03 documents; recorded, not failures)

- `agents/README.md:3` "Eight specialist Bots"; `:16` "All eight roles" (ten seats).
- `skills/desk-operating-model/SKILL.md:18` "eight roles" (21-01 also cited :3; the current file shows only :18).
- `skills/pumpgrok-setup/SKILL.md:20` "fully operational eight-role desk" (new in this round).
- `scripts/hermes-bootstrap.sh:2`, `:214` "eight PumpGrok roles", "eight children". The script's
  `ROLES` array (line 14) has 8 entries (chief scout risk whale sniper rug exit shill): SIGNAL and
  JOURNAL are not provisioned. Named documents do not state a Hermes profile count (checked).
- `scripts/README.md:8` "Create eight isolated Hermes profiles".
- `skills/holder-and-flow-analysis/SKILL.md:27` `python /workspace/pumpgrok/tools/holder_check.py`
  (the file is absent; the in-tree holder tool is `src/pumpgrok/tools/onchain/top_holders.py`).
- `skills/grokbot-pipeline/SKILL.md`: body not reviewed in this round (its description at line 3 names
  `src/pumpgrok/engine`, which matches the tree).
- Design and history documents, out of DOC-03 scope (D-10): `docs/ROSTER.md` (16 "eight" hits),
  `docs/upgrade-plan-desk-v2.md` (14), `docs/FOUNDATION_STACK.md`, `docs/DISCOVERY.md` (`tools/paper_sim.py`
  and `tools/ticket_helper.py` rows at :309 and :381; `/workspace/trading-desk` at :309, :381, :594, :662),
  `docs/MIGRATION_MAP.md` (`/workspace/trading-desk` at :77, :503), `docs/design/paper-engine.md:419`,
  `docs/design/interfaces.md:1177`. Their self-described status is recorded, not changed.
- `skills/verification-receipts/SKILL.md:50`, `contracts/tool-rosters/*.yaml`, `scripts/prompt_sources.py`,
  `ci/gates/check_desk_integrity.py`: "core eight" refers to the eight `desk.*` core tools, not roles.
  Correct; no action.
- Placeholder organisation `your-org` in `SETUP.md:16-17`, `.claude-plugin/marketplace.json:13,15`,
  `.grok-plugin/marketplace.json:13,15`, and `scripts/check.sh` (allowlist). The real organisation name is
  unknown (docs/MIGRATION_MAP.md section 8).
- `docs/VENDOR_PIN.md:9` license pointer (see Residual notes 2).
- Test hardening (see Residual notes 6).
- Non-ASCII punctuation in pre-existing text: README.md (3 lines), ARCHITECTURE.md (11), SETUP.md (12).
  None were added by phase 21.
- Console pytest summary is unreliable in this environment; counts above come from junit XML.

## Evidence index

- Red: /tmp/p21b-red.xml (scratch tree /tmp/p21b-red removed)
- Green: /tmp/p21b-docs.xml, /tmp/p21b-docs.log
- Gates: /tmp/p21b-vdc.log (verify_doc_commands), /tmp/p21b-check.log (check.sh), /tmp/p21b-lint.log (make lint), /tmp/p21b-verify.log (replay verify)
- Scout exit: /tmp/p21b-scout.out
