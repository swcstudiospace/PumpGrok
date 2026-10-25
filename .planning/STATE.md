---
gsd_state_version: "1.0"
milestone: v3
status: Defining roadmap
last_updated: "2026-10-25"
last_activity: 2026-10-25
last_activity_desc: Milestone v3 started
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
current_phase: none
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-25)

**Core value:** The desk runs autonomously in paper mode for 2-4 weeks and produces honest, replayable reports; no code path can move real funds.
**Current focus:** Milestone v3 roadmap (pending approval)

## Current Position

Phase: none (roadmap pending approval)
Plan: none
Status: Defining roadmap
Last activity: 2026-10-25 - Milestone v3 started

## Performance Metrics

**Velocity:**

- v3 plans completed: 0
- v2 history: 5 phases, 44 plans, archived in .planning/MILESTONES.md

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. Recent decisions affecting v3:

- [V3-1]: Constitution amendment approved 2026-10-25 as drafted; BLIND narrowed to SAFE-4 and SAFE-8; applied in phase 9 with its code
- [V3-2]: Backtest data is self-recorded only
- [V3-3]: Branch bot-00-chief/v2-closeout from origin/main; draft PRs only; no merge without approval
- [V3-4]: Research skipped for v3; defaults D11 (max 50 trials), D12 (flag above 20), D13 (20 percent holdout), D7 divergence (2 pp or 0.5 Sharpe)

### Pending Todos

None yet.

### Blockers/Concerns

Open decisions from the v2 audit (`.planning/milestones/v2-MILESTONE-AUDIT.md`), with resolutions:

- PumpPortal trade key: default applied, no key (R45). Resolved; the desk uses no trade-stream key.
- Paid Solana RPC provider: none approved. Public endpoint only, no spend. Holder checks are advisory under the amendment (UPG-05).
- BLIND holder rule: narrowed to SAFE-4 and SAFE-8 (amendment approved 2026-10-25, applied in phase 9). All other BLIND results remain KILL.

Observed data-source degradation to design around: pump.fun REST returns HTTP 530 / error 1016 on all tested paths (R47).

## Deferred Items

v2 audit tech_debt carried forward at v2 close (`.planning/milestones/v2-MILESTONE-AUDIT.md`). Status `deferred-to-v3` means a v3 requirement covers the item; `deferred-beyond-v3` means no v3 requirement covers it.

| Source | Item | Status | Maps to |
|--------|------|--------|---------|
| phase 4 | Trailing-stop peaks are held in memory; a serve restart re-learns them | deferred-to-v3 | INT-09 |
| phase 4 | Replay and serve hold the last curve tick after the recording ends (fixture semantics) | deferred-beyond-v3 | none |
| phase 4 | A recorded tick inside an order's latency window is skipped by the timeline; the confirmation read sees the latest tick | deferred-beyond-v3 | none |
| phase 4 | PaperAdapter.mark_to_market (per mint) keeps original stamping; replay uses the combined mark, any live caller would mix marks | deferred-beyond-v3 | none (live caller out of scope) |
| phase 4 | A held mint that stops ticking blocks buys after the 60 s staleness limit (by design) | deferred-beyond-v3 | none (by design) |
| phase 4 | Ledger-mark fallback closed before the change reported venue fee 0; marks after it carry the venue fee | deferred-to-v3 | INT-07 |
| phase 4 | bot-06-exit roster exec.place input does not list exit_reason; the gateway refuses rule sells over HTTP | deferred-beyond-v3 | Out of Scope (human-owned roster) |
| phase 5 | Kill channel: a pending KILL and the request offset live in memory until commit | deferred-beyond-v3 | none (v2 next goal) |
| phase 5 | Telegram getUpdates behaviour (webhook 409, group chats, bot privacy mode) is not verified without a live bot | deferred-beyond-v3 | Out of Scope (Telegram live verification) |
| phase 5 | The gateway kill poll can block its owner loop up to 2 s every 5 s during a Telegram outage | deferred-beyond-v3 | none |
| phase 5 | Flatten barrier is in-process only; a cross-process flatten does not wait | deferred-beyond-v3 | none |
| phase 5 | killswitch flatten exits 6 with flatten_status incomplete; exit 5 is not implemented | deferred-beyond-v3 | none |
| phase 5 | Container: DESK_GATEWAY_REPO_ROOT is set by the image; overriding it to /app brings back the missing desk-tool files | deferred-beyond-v3 | none |
| phase 5 | Two roots under ./var by decision (ledger var/ledger.sqlite, kill latch var/desk/KILLSWITCH) | deferred-beyond-v3 | none (owner decision, no action) |
| process | PR 9 shipped with --ignore-gsd by owner decision (recorded in its PR body) | deferred-beyond-v3 | none (recorded) |
| process | One-time gate waivers for PR 6, PR 8, PR 9 (all merged) and PR 11; remove PR 11's waiver after its merge | deferred-beyond-v3 | none (owner action) |
| process | Omega CI runner migration (main 5b5d6a1, 9772655) was merged by another seat and not reviewed in the v2 audit | deferred-beyond-v3 | none (needs a separate review) |
| process | Planning on main was stale until the v2 closeout merged | resolved | v2 archive on main; this branch starts from it |

## Session Continuity

Last session: 2026-10-25
Stopped at: Milestone v3 requirements defined; roadmap pending approval
Resume file: None

## Operator Next Steps

- Approve the v3 roadmap, then run /gsd-autonomous
