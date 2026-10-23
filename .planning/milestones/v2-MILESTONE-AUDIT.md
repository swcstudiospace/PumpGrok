---
milestone: v2
audited: 2026-10-23
status: passed
scores:
  requirements: 71/71
  phases: 5/5
  integration: 7/7
  flows: 6/6
gaps:
  requirements: []
  integration: []
  flows: []
tech_debt:
  - phase: 4
    items:
      - "Trailing-stop peaks are held in memory. A serve restart re-learns them; the vendor persisted them."
      - "Replay and serve hold the last curve tick after the recording ends (fixture semantics)."
      - "A recorded tick inside an order's latency window is skipped by the timeline, and the confirmation read sees the latest tick. The smoke fixture has no such tick."
      - "PaperAdapter.mark_to_market (per mint) keeps its original stamping. Replay uses the combined mark; any live caller would still mix marks."
      - "A held mint that stops ticking blocks buys after the staleness limit (60 s), by design (data_stale)."
      - "Ledger-mark fallback closes before this change reported venue fee 0; marks written after it carry the venue fee."
      - "bot-06-exit roster exec.place input does not list exit_reason. The gateway refuses rule sells over HTTP. The roster is human-owned and needs a decision."
  - phase: 5
    items:
      - "Kill channel: a pending KILL and the request offset live in memory until commit. A restart relies on Telegram retaining the update (about 24 h)."
      - "Telegram getUpdates behaviour (webhook 409, group chats, bot privacy mode) is not verified without a live bot."
      - "The gateway kill poll can block its owner loop for up to 2 s every 5 s during a Telegram outage. The interval is fixed."
      - "Flatten barrier is in-process only; a cross-process flatten does not wait."
      - "killswitch flatten prints flatten_status incomplete and exits 6 when a position is left open. Exit 4 is also a corrupt replay fixture, and exit 5 is not implemented."
      - "Container: DESK_GATEWAY_REPO_ROOT is set by the image. Overriding it to /app brings back the missing desk-tool files."
      - "Two roots under ./var by decision: the paper ledger is var/ledger.sqlite, and the kill latch is var/desk/KILLSWITCH."
  - phase: process
    items:
      - "PR 9 (gate-only bootstrap) shipped with --ignore-gsd, by owner decision. Recorded in its PR body."
      - "One-time gate waivers exist for PR 6 (merged), PR 8 (merged), PR 9 (merged) and PR 11. Each is bound to its PR number. Remove PR 11's waiver after its merge."
      - "The Omega CI runner migration (main 5b5d6a1, 9772655) was merged by another seat with its own receipt. It was not reviewed in this audit."
      - "Planning on main was stale until this closeout merges. The completed phase verifications were committed on gap/v2-closure (PR 8)."
---

# Milestone v2 audit: PumpGrok Desk v2

Verdict: passed. PAPER-007 was narrowed by owner decision on 2026-10-23 to the shipped autonomous-paper exit path; the manual-ticket exit approval path is a deferred follow-up, not part of v2.

## Phases

| Phase | Name | Plans | Verification | Evidence |
|---|---|---|---|---|
| 1 | Foundation | 14/14 | passed | .planning/phases/01-foundation/01-VERIFICATION.md |
| 2 | Restructure | 5/5 | passed (re-verified 2026-10-23 at origin/main) | 02-VERIFICATION.md; CR-03 re-verified resolved |
| 3 | Tools and Skills | 7/7 | passed | 03-VERIFICATION.md |
| 4 | Paper Trading and Autonomy | 10/10 | passed; PAPER-007 narrowed by owner decision | 04-VERIFICATION.md |
| 5 | Hardening | 8/8 | passed (re-verified 2026-10-23; SC5 met by security-pr run 39882086579) | 05-VERIFICATION.md |

## Requirements coverage

Sources cross-referenced: the REQUIREMENTS.md checkboxes and traceability table, and the five VERIFICATION.md status fields. The SUMMARY frontmatter cross-check (requirements-completed) was not run in this audit.

- 71 requirements in REQUIREMENTS.md. 71 are complete. PAPER-007 is complete as narrowed.
- Traceability rows: 71, mapped to phases 1 to 5. Unmapped: 0.
- TOOL-011 and PAPER-007 are narrowed by owner decisions (see Decisions). Both are complete with the narrowing stated.

## Integration (end-to-end)

Checked on merged main at 98848e3 with a pristine export, then the closeout fix on gap/v2-closeout.

| Gap | Finding (origin/main ef2f2f6) | Status |
|---|---|---|
| G1 | Fixture cycle never traded | Closed (smoke: buy filled, rule sell filled) |
| G2 | Paper buy and sell verbs refused for every seat | Narrowed by owner decision; documented |
| G3 | Gateway ignored operator settings | Closed (overlay reaches the gateway risk budget) |
| G4 | Gateway had no entrypoint | Closed (python -m desk_gateway; compose service; /healthz) |
| G5 | Kill latch path mismatch; alert source not polled | Closed (one latch path; channel polled per cycle) |
| G6 | Rejected order reported success | Closed (isError true, code approval_missing) |
| G7 | Flatten with no mark exited 0 and left the position open | Closed by the closeout change: exit 6, status incomplete, ERROR log |
| G8 | RISK-004 named the old latch path | Closed by the closeout change |

Flows (from merged main 98848e3):

| Flow | Command | Exit | Result |
|---|---|---|---|
| (a) paper cycle on fixtures | run --mode paper --once --replay tests/fixtures/replay/smoke | 0 | buy rejected post_graduation at 2.5 s; buy filled at 3.0 s; sell filled rule=take_profit |
| (b) live refused | run --mode live --once --replay smoke | 3 | nine preconditions unmet; nothing written |
| (c) kill-switch flatten closes a marked position | seeded mark; killswitch set; killswitch flatten | 0 | PositionClosed reason kill_flatten |
| (d) gateway quote and place | JSON-RPC on /mcp/<seat> | n/a | rejected place returns isError true |
| (e) deterministic replay | verify --fixture smoke, twice | 0, 0 | identical events.hash bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54 |
| (f) daily report render | report --daily | 0 | all sections render |

Closeout run on gap/v2-closeout: full pytest exit 0; ci/tests 407 passed, exit 0; desk gateway 56 passed, exit 0; secrets, check.sh, assemble-prompts, generate-templates, generate-event-schemas, G-1 manifest and G-7 desk integrity all exit 0; smoke run exit 0; verify exit 0 with the same hash; live refused exit 3.

## Decisions recorded (owner)

- The CLI refuses pumpgrok paper buy and sell for every seat (exit 1, no write). Paper orders go through the gateway seats that hold exec grants (sniper, exit). TOOL-011 is narrowed.
- The replay sandbox runs autonomous-paper. The production default stays manual-ticket.
- Exit rule sells are recorded as ApprovalRecorded kind autonomous_paper, approved_by risk_engine, with exit_rule_id. This matches the design, and INV-R-10 is unchanged.
- One canonical paper ledger, var/ledger.sqlite, shared by CLI, replay and gateway through PAPER_LEDGER_PATH.
- The kill latch is var/desk/KILLSWITCH, the operational data directory the CLI already used.
- Kill channel: Telegram inbound commands are polled every risk cycle, allowlisted by chat id, with an offset persisted in the data directory.
- The one-time gate waivers for PR 6, PR 8, PR 9 and PR 11 are owner decisions, each bound to its PR number.
- PR 9 shipped with --ignore-gsd (owner decision bootgsd).
- PAPER-007 narrowed by owner decision (2026-10-23): a standing human exit_rule approval under manual-ticket is a deferred follow-up. The requirement text states it.

## Completion

The archive ships in the same planning PR as the PAPER-007 narrowing, as approved by the owner on 2026-10-23 ("narrow PAPER-007, then archive v2"). The git tag v2 is created on the merge commit after that PR merges.
