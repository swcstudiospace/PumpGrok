---
phase: 03-tools-and-skills
verified: 2026-10-21T15:09:44Z
status: human_needed
score: 6/6 must-haves verified
criteria_passed: 6/6
criteria_partial: 0
criteria_failed: 0
pending_human_items: 3
gaps: []
accepted_partials:
  - A1 roster additive version bump; G-4 acks pending (human checkpoint)
  - A2 criterion 5 narrowed to tools/core/cli; engine floats exempt until Phase 4
  - A3 TOOL-004 atomicity and TOOL-011 full verb coverage move to Phase 4
  - A4 bonding-curve layout ASSUMED; rpc.api_key setting kept; live probe in Phase 4
---

# Phase 3: Tools and Skills Verification Report

**Phase goal:** Every desk tool is a typed, registered dotted tool that seats
reach only through least-privilege rosters, exposed through the desk gateway,
and the full 35-skill set validates against its manifests.

**Branch:** feat/grokbot-desk-merge
**Method:** goal-backward. Every ROADMAP criterion re-run literally in the
working tree; SUMMARY.md claims treated as pointers, not evidence.

## Criterion results (literal commands, recorded exit codes)

| # | Literal command | Exit | Verdict |
|---|-----------------|------|---------|
| 1 | `uv run pytest -q tests/test_skill_manifests.py tests/test_bot_manifests.py` | 0 | PASS (162 passed, 0 failed) |
| 2a | `test "$(ls -d skills/*/ \| wc -l)" -eq 35` | 0 | PASS (35 dirs) |
| 2b | `grep -q 'bot-09-journal' skills/desk-post-trade-review/SKILL.md` | 0 | PASS |
| 2c | `! grep -rn "23 skills" plugin.json .claude-plugin .grok-plugin .cursor-plugin agents` | 0 | PASS (grep exit 1, no matches, all four paths exist) |
| 3a | `uv run pytest -q -k "least_privilege or gateway"` | 0 | PASS (21 passed, 0 failed) |
| 3b | `uv run pytest -q` in `services/desk-gateway/` | 0 | PASS (21 passed, 0 failed) |
| 4a | `uv run pumpgrok paper buy --help` lists `--ticket --mint --size-sol --slippage-bps --approval-id` | 0 | PASS (all five flags present, plus --seat) |
| 4b | `! grep -rnE "\b(post|put|patch|delete)\b\|method=['\"](POST\|PUT\|PATCH\|DELETE)" src/pumpgrok/tools/social/` | 0 | PASS (grep exit 1, no matches, no errors) |
| 5a | `! grep -rnE "(lamports\|units\|sol)[A-Za-z_]*: *float" src/pumpgrok/tools src/pumpgrok/core src/pumpgrok/cli.py` | 0 | PASS (grep exit 1, no matches, no errors; narrowed scope per A2) |
| 5b | `uv run pytest -q` (full root suite) | 0 | PASS (888 passed, 0 failed) |
| Ckpt | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` | 0 | PASS (one cycle completes, cycle_end event emitted) |
| Gate G-7 | `python3 ci/gates/check_desk_integrity.py` | 0 | PASS (10 rosters, 21 prompt files) |
| Gate G-4 | `python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/phase-3-seat-manifests.yaml` | 0 | PASS (non-breaking, v1.1.0, 0 acks) |
| Gate G-3 | `python3 ci/gates/check_secrets.py` and `--base origin/main` | 0 | PASS (470 files, no secrets) |
| Lint | `ruff check src/` | 0 | PASS |
| Lint | `ruff format --check src/` | 0 | PASS |
| Types | `uv run mypy src/` | 0 | PASS (122 files, no issues) |
| Suite | `uv run pytest -q` services/desk-gateway (criterion 3b repeat) | 0 | PASS |

**Score: 6/6 ROADMAP criteria PASS** (criterion 2 and 4 each have
sub-commands; all sub-commands exit 0).

### Command-run notes (no verdict impact)

- N1 pipe artifact: `uv run pytest ... | tail` intermittently renders as
  "Pytest: No tests collected" with exit 0 in this sandbox (also noted in
  03-07-SUMMARY). Ground truth was taken from output redirected to files:
  162 dots / 0 failures for criterion 1, 21 / 0 for 3a, 21 / 0 for the
  gateway suite, 888 / 0 for the full suite. Exit codes above are the real
  process exits.
- N2 bare `mypy src/` (system env) exits 2: `No module named 'pydantic'`.
  Under the project env (`uv run mypy src/`) it exits 0. Repo issue: none.
- N3 bare `check_contracts.py` (no `--change`) exits 1 by design: it lists
  the 32 touched contract surfaces and asks for a change document. With the
  phase change doc (`--change contracts/changes/phase-3-seat-manifests.yaml`,
  the form `run_all.py` supports) it exits 0 with G-4 PASS. Not a gap.
- N4 `ls -d skills/*/` prints one stderr line (`skills/README.md/` is not a
  directory) but still lists exactly 35 directories; the `test ... -eq 35`
  exits 0.
- N5 criterion 3b was run from `services/desk-gateway/` with its own
  `uv run pytest -q` (own pyproject + committed uv.lock, 25 packages,
  stdlib HTTP only).

## Requirement-to-evidence mapping (all 15 ids)

| Requirement | Plan | Evidence (file / test, all re-run or read) |
|-------------|------|---------------------------------------------|
| TOOL-001 market reads | 03-02 | `src/pumpgrok/tools/market/{price,ohlcv,liquidity,trades,holders_snapshot}.py`; `tests/tools/market/` green inside full suite |
| TOOL-002 RPC discipline | 03-01, 03-02 | `src/pumpgrok/tools/onchain/rpc.py`; `tests/tools/onchain/test_rpc.py` green; B12 naming item pending (see H3) |
| TOOL-003 safety scoring | 03-02 | `src/pumpgrok/tools/safety/score_report.py` + `checks/`; `tests/tools/safety` green; BLIND semantics, no exceptions |
| TOOL-004 exec input contract | 03-03 | `src/pumpgrok/tools/exec/place.py` rejects without approval, unknown approval exits 1 with JSON, zero OrderPlaced rows; atomic consume-and-order + repeat-returns-first-fill deferred to Phase 4 per A3 |
| TOOL-005 portfolio/ledger | 03-03 | `src/pumpgrok/tools/portfolio/` + `src/pumpgrok/ledger/store.py`; task-2 gate green |
| TOOL-006 notify/risk | 03-03 | `src/pumpgrok/tools/notify/`, `src/pumpgrok/tools/risk/`; allowlisted Notifier, kill_switch action enum {set, flatten_request} only |
| TOOL-007 desk core eight | 03-03 | `src/pumpgrok/tools/desk/` (brief, docs_search, memory_retain/recall, ownership_resolve, receipt_check, event_emit, doctor); task-3 gate green |
| TOOL-008 money typing | 03-01 (+02/03/07) | Criterion 5a grep clean; Decimal-only boundary, `*_lamports: int`; engine/ floats exempt per A2 |
| TOOL-009 least privilege | 03-02, 03-04 | Criterion 3a (21 tests: ceiling refusals, R63 cron guard, R35 sizes, kill_switch only risk, ledger_write nowhere); criterion 4b social GET-only |
| TOOL-010 desk gateway | 03-05 | Criterion 3b (21 tests: compare_digest 401/403/503, tools/list == roster+core, tools/call isError envelopes); `src/pumpgrok/contracts/projection.py` facade |
| TOOL-011 operator verbs | 03-07 | Criterion 4a (five flags); `build_operator_registry()` 37-tool composition; absent backends print JSON envelope exit 5 per A3; hidden `tools` verb outside top help |
| SKILL-001 35-skill set | 03-06 | Criterion 2a/2b (35 dirs, journal bot ref); 12 new + 23 retrofitted SKILL.md files on disk |
| SKILL-002 skill manifests | 03-06 | Criterion 1 joint run (162 tests incl. name==dirname, granted-tools, no LIVE_WRITE, no forbidden strings) |
| SKILL-003 bot manifests | 03-04 | Criterion 1 joint run (14 tests: ten manifests load, R35 sizes, R20 keys, chief resolves desk.brief / refused exec.place); roster files at version 1.1.0 with manifest blocks (spot-read bot-00-chief.yaml: 7 own + core eight = 15) |
| SKILL-004 prompt wiring | 03-06 | Criterion 2c (no "23 skills" anywhere); `scripts/assemble-prompts.sh --check` and `generate-templates.py --check` per 03-06 verification; load=always skills + tools contract in prompts |

## Accepted partials (user-approved, NOT gaps)

- **A1 roster contract:** seat rosters carry manifest blocks, version
  1.0.0 to 1.1.0, change doc
  `contracts/changes/phase-3-seat-manifests.yaml`. G-4 acks from the ten
  seat consumers are recorded `pending_acks` (verified on disk). Pending,
  not failed.
- **A2 narrowed criterion 5:** float grep covers `src/pumpgrok/tools`,
  `src/pumpgrok/core`, `src/pumpgrok/cli.py` only; vendor-parity floats in
  `src/pumpgrok/engine/` exempt until Phase 4. Judged against the narrowed
  text: PASS.
- **A3 Phase 4 deferrals:** TOOL-004 atomic consume-and-order transaction
  and repeat-returns-first-fill; TOOL-011 full verb coverage (unbuilt
  backends exit 5 with the JSON envelope, verified in `src/pumpgrok/cli.py`
  `not_yet_implemented` + `EXIT_NOT_IMPLEMENTED` map). Input contract and
  wired-verb path delivered in Phase 3. Accepted partial coverage, not gaps.
- **A4 assumptions:** bonding-curve layout stays ASSUMED (fixture marked
  ASSUMED in `src/pumpgrok/tools/onchain/curve_layout.py`); setting remains
  `rpc.api_key`. Live confirmation via Phase 4 probe (R65). Pending, not
  failed.

## Pending human items (only reason status is not `passed`)

### H1. G-4 acknowledgements from ten seat consumers (A1 checkpoint)

**Test:** Collect ack from each consumer listed under `pending_acks` in
`contracts/changes/phase-3-seat-manifests.yaml` (bot-00-chief and nine
others; list verified on disk starting at line 48).
**Expected:** Change doc records 10 acks; re-run of the G-4 command shows
acknowledged instead of `0 acknowledgement(s)`.
**Why human:** Only the user can collect cross-consumer sign-off; no
programmatic check can substitute.

### H2. Bonding-curve layout live confirmation (A4)

**Test:** Run the Phase 4 live probe against RPC (R65) and confirm the
ASSUMED layout in `curve_layout.py` decodes real `lp_status`/`price`
accounts.
**Expected:** Fixture `ASSUMED` marker cleared or layout corrected; no
entry depends on RPC prices until then.
**Why human:** Requires live network access and user confirmation of the
layout; cannot verify from fixtures.

### H3. TOOL-002 setting-name confirmation (B12)

**Test:** Confirm whether `rpc.api_key` (current, env
`PUMPGROK_RPC__API_KEY`) or the TOOL-002 text `solana.rpc_api_key` is
canonical.
**Expected:** Either a rename or an explicit keep; the other text updated.
**Why human:** Naming decision reserved for the user in 03-CONTEXT.

## Gaps

None. No criterion fails for a reason outside the accepted partials above.

---

_Verified: 2026-10-21T15:09:44Z_
_Verifier: Flow3b.Verify03 (gsd-verifier)_
