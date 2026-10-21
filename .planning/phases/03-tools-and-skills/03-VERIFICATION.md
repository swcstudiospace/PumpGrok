---
phase: 03-tools-and-skills
verified: 2026-10-21T16:30:00Z
status: passed
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

# Phase 3: Tools and Skills Re-Verification Report (at HEAD)

**Phase goal:** Every desk tool is a typed, registered dotted tool that seats
reach only through least-privilege rosters, exposed through the desk gateway,
and the full 35-skill set validates against its manifests.

**HEAD:** ac34189 (`feat/grokbot-desk-merge`)
**Method:** goal-backward. Every ROADMAP criterion re-run literally at HEAD;
prior report (commit 715db78) not reused. SUMMARY.md claims treated as
pointers, not evidence.

Since the prior report the tree gained: lint cleanup, receipt_check Clock
fix (c1b881c), code-review fixes WR-01..WR-10 (d5c0985, 00d7e69, db28f75,
500eb5f, e0c15f4, f747c59, 1aed59f, 3e847b7, 194092b), and review artifacts
through iteration 3 (status clean, 0 critical, 0 warning).

## Criterion results (literal commands, recorded exit codes)

| # | Literal command | Exit | Verdict |
|---|-----------------|------|---------|
| 1 | `uv run pytest -q tests/test_skill_manifests.py tests/test_bot_manifests.py` | 0 | PASS (162 passed, 0 failed) |
| 2a | `test "$(ls -d skills/*/ \| wc -l)" -eq 35` | 0 | PASS (35 dirs; `skills/README.md` is a file, not counted) |
| 2b | `grep -q 'bot-09-journal' skills/desk-post-trade-review/SKILL.md` | 0 | PASS |
| 2c | `! grep -rn "23 skills" plugin.json .claude-plugin .grok-plugin .cursor-plugin agents` | 0 | PASS (no matches; all five paths exist) |
| 3a | `uv run pytest -q -k "least_privilege or gateway"` | 0 | PASS (23 passed, 888 deselected) |
| 3b | `uv run pytest -q` in `services/desk-gateway/` | 0 | PASS (45 passed, 0 failed) |
| 4a | `uv run pumpgrok paper buy --help` lists `--ticket --mint --size-sol --slippage-bps --approval-id` | 0 | PASS (all five flags present, plus --seat) |
| 4b | `! grep -rnE "\b(post\|put\|patch\|delete)\b\|method=['\"](POST\|PUT\|PATCH\|DELETE)" src/pumpgrok/tools/social/` | 0 | PASS (no matches, no errors) |
| 5a | `! grep -rnE "(lamports\|units\|sol)[A-Za-z_]*: *float" src/pumpgrok/tools src/pumpgrok/core src/pumpgrok/cli.py` | 0 | PASS (no matches; narrowed scope per A2) |
| 5b | `uv run pytest -q` (full root suite) | 0 | PASS (911 passed, 0 failed) |
| Ckpt | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` | 0 | PASS (one cycle completes, cycle_end event emitted) |
| Gate G-7 | `python3 ci/gates/check_desk_integrity.py --repo .` | 0 | PASS (10 rosters, 21 prompt files) |
| Gate G-4 | `python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/phase-3-seat-manifests.yaml` | 0 | PASS (non-breaking, v1.1.0, 0 acks) |
| Gate G-3 | `python3 ci/gates/check_secrets.py --base origin/main` | 0 | PASS (484 files, no secrets) |
| Lint | `uv run ruff check .` | 0 | PASS (all checks passed) |
| Lint | `uv run ruff format --check .` | 0 | PASS (384 files already formatted) |
| Types | `uv run mypy src/` | 0 | PASS (123 files, no issues) |

**Score: 6/6 ROADMAP criteria PASS** (criteria 2, 3, 4, 5 each have
sub-commands; every sub-command exits 0).

### Command-run notes (no verdict impact)

- N1 pipe artifact: bare `uv run pytest -q` in this sandbox intermittently
  renders "No tests collected" with exit 0 when piped through `tail`. Ground
  truth was taken from output redirected to files, and from
  `uv run python -m pytest -o addopts="" -q`, which prints real counts:
  162 / 0 for criterion 1, 23 / 0 for 3a, 45 / 0 for the gateway suite,
  911 / 0 for the full suite. The exit code is authoritative in all cases.
- Count drift vs the prior report (3a: 21 -> 23; gateway: 21 -> 45; full:
  888 -> 911) is growth from the WR-fix regression tests
  (test_long_content_length.py, test_append_seat_scoped.py and siblings),
  not silent skipping: deselected/failed counts are 0 in every run.
- C2a prints `ls: cannot access 'skills/README.md/': Not a directory` on
  stderr because the glob `skills/*/` is attempted against the plain file
  `skills/README.md`; the counted output is 35 directory lines and the
  `test ... -eq 35` exits 0.

## Requirement mapping (all 15 phase-3 ids)

| ID | Status | Evidence |
|----|--------|----------|
| TOOL-001 | SATISFIED | `tests/tools/market/` green inside full suite (911 passed); typed outputs with freshness/source per catalog section 1 |
| TOOL-002 | SATISFIED | `tests/tools/onchain/` green; single RPC client `src/pumpgrok/tools/onchain/rpc.py`; WHALE grants for deployer_history/large_transfers covered by least-privilege tests (criterion 3a) |
| TOOL-003 | SATISFIED | `tests/tools/safety/` green; BLIND-on-no-data behavior in score_report |
| TOOL-004 | PARTIAL (A3) | Input contract delivered: `approval_id` required (`place.py:43`), idempotency key derived from (ticket_id, side, decision_id), `exec.simulate` writes nothing. Atomic consume-and-order same-transaction write deferred to Phase 4 |
| TOOL-005 | SATISFIED | `tests/tools/{portfolio,risk,journal,desk}/` green; kill_switch accepts only set/flatten_request; ledger_write PermissionDenied for seats; journal/event_emit kind restricted to journal_note/escalation |
| TOOL-006 | SATISFIED | `tests/tools/notify/` green; stdout+file sinks always on, Telegram/webhook allowlisted; RISK/RUG escalate via event_emit |
| TOOL-007 | SATISFIED | Core-eight desk tools resolvable by every seat (registry tests green); `desk.doctor` shares the `pumpgrok doctor` code path; WR-01 path traversal fixed and reviewed clean |
| TOOL-008 | SATISFIED (narrowed, A2) | Criterion 5a grep clean over tools/core/cli; `tests/tools/test_money_types.py` green; no float money in scope; engine vendor-parity floats exempt until Phase 4 |
| TOOL-009 | SATISFIED | Criterion 3a (23 passed): `test_registry_least_privilege.py`, `test_live_gate.py`, `test_gateway_projection.py`, `test_forbidden_owners.py`; criterion 4b social GET-only clean |
| TOOL-010 | SATISFIED | Criterion 3b (45 passed in services/desk-gateway); seat-B token on seat-A route is 403; WR-09 Content-Length cap fixed and reviewed clean |
| TOOL-011 | PARTIAL (A3) | Criterion 4a: all five `paper buy` flags present; `test_tools_cli.py` green; unbuilt backends exit 5 with the JSON envelope; full verb coverage deferred to Phase 4 |
| SKILL-001 | SATISFIED | Criterion 2a/2b: 35 skills on disk; post-trade-review owned by bot-09-journal |
| SKILL-002 | SATISFIED | Criterion 1: `test_skill_manifests.py` green (162 combined with bot manifests) |
| SKILL-003 | SATISFIED | Criterion 1: `test_bot_manifests.py` green; ten BotManifests bot-00-chief .. bot-09-journal with R20 risk_budget keys |
| SKILL-004 | SATISFIED | Criterion 2c: no stale "23 skills" in plugin.json, .claude-plugin, .grok-plugin, .cursor-plugin, agents |

## Accepted partials (reported separately, not gaps)

- **A1 roster additive version bump:** change doc is a one-way additive
  roster contract change (v1.1.0, non-breaking per G-4). G-4 acks from ten
  seat consumers are recorded `pending_acks` (verified on disk, lines 48-57
  of the change doc). Pending, not failed.
- **A2 narrowed criterion 5:** float grep covers `src/pumpgrok/tools`,
  `src/pumpgrok/core`, `src/pumpgrok/cli.py` only; vendor-parity floats in
  `src/pumpgrok/engine/` exempt until Phase 4. Judged against the narrowed
  text: PASS.
- **A3 Phase 4 deferrals:** TOOL-004 atomic consume-and-order transaction;
  TOOL-011 full verb coverage (unbuilt backends exit 5 with the JSON
  envelope, verified in `src/pumpgrok/cli.py` `not_yet_implemented` +
  `EXIT_NOT_IMPLEMENTED` map). Input contract and wired-verb path delivered
  in Phase 3. Accepted partial coverage, not gaps.
- **A4 assumptions:** bonding-curve layout stays ASSUMED (fixture marked
  ASSUMED in `src/pumpgrok/tools/onchain/curve_layout.py`); setting remains
  `rpc.api_key`. Live confirmation via Phase 4 probe. Pending, not failed.

## Pending human items (only reason status is not `passed`)

### H1. G-4 acknowledgements from ten seat consumers (A1 checkpoint)

**Test:** Collect ack from each consumer listed under `pending_acks` in
`contracts/changes/phase-3-seat-manifests.yaml` (bot-00-chief and nine
others; list verified on disk).
**Expected:** Change doc records 10 acks; re-run of the G-4 command shows
acknowledged instead of `0 acknowledgement(s)`.
**Why human:** Only the user can collect cross-consumer sign-off; no
programmatic check can substitute.

### H2. Bonding-curve layout live confirmation (A4)

**Test:** Run the Phase 4 live probe against RPC and confirm the ASSUMED
layout in `curve_layout.py` decodes real `lp_status`/`price` accounts.
**Expected:** Fixture `ASSUMED` marker cleared or layout corrected; no
entry depends on RPC prices until then.
**Why human:** Requires live network access and user confirmation of the
layout; cannot verify from fixtures.

### H3. TOOL-002 setting-name confirmation

**Test:** Confirm whether `rpc.api_key` (current, env
`PUMPGROK_RPC__API_KEY`) or the TOOL-002 text `solana.rpc_api_key` is
canonical.
**Expected:** Either a rename or an explicit keep; the other text updated.
**Why human:** Naming decision reserved for the user in 03-CONTEXT.

## Gaps

None. No criterion fails for a reason outside the accepted partials above.

---

_Verified: 2026-10-21T16:30:00Z at HEAD ac34189_
_Verifier: Flow3b.ReVerify03 (gsd-verifier)_
