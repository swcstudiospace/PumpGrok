# v3 closeout: PumpGrok Desk v3

Result: archived with recorded tech debt. Owner decision, 2026-11-01: archive v3 now with the audit debt recorded, rather than plan a cleanup phase first.

## Scope

Active milestones only (clarification q1). v3 is the only milestone with remaining work, and ROADMAP.md lists no next milestone. The owner's archive decision names v3.

Phases closed: 6 integrity closure, 7 documentation upgrade, 8 backtest and paper evaluation, 9 bounded paper self-upgrade, 10 live readiness kept disabled, 20 close gap LIV-01, 21 close gap DOC-03. Plans: 36. Tasks: 10.

Archive: .planning/milestones/v3-ROADMAP.md, v3-REQUIREMENTS.md, v3-MILESTONE-AUDIT.md and v3-phases/. The original .planning/REQUIREMENTS.md was removed after archiving.

## Audit

Status: tech_debt (.planning/milestones/v3-MILESTONE-AUDIT.md). All 34 v3 requirements are verified by a passing phase verification. None is unsatisfied and none is orphaned. 31 requirements lack SUMMARY frontmatter metadata and rest on their phase verification alone.

Gaps closed during this closeout:

- LIV-01: the CLI import path loaded the live adapter. Phase 20 closed it: the import guard follows parent package edges, and a fresh-interpreter probe shows the adapter absent after importing pumpgrok.cli, backtest and promotion.
- DOC-03: documents contradicted the code. Phase 21 closed it: a red-first test covers all six plugin manifests, the ARCHITECTURE diagram and read-only wording match the code, ticket next and VENDOR_PIN are corrected, and CLAUDE.md line anchors resolve.
- Phase 7 criterion 4 compared against origin/main, which already holds the trimmed AGENTS.md, so it could never pass. It is re-baselined to f3887bb, the phase start point (423 lines against 133).

## Ship path

- G-1 (path ownership) failed for this branch as built: ten files owned by bot-02-risk (8), bot-04-sniper (1) and bot-09-journal (1). The cross-bot protocol documents no waiver for cross-seat work.
- Owner decision: owner waiver, then merge, with merge method merge.
- PR 28 (bot-02-risk/gate-waiver-pr-27), owner-authorized, merged as 9588bc0. It adds PR 27 to the G-1 waiver list at both if: lines in .github/workflows/gates.yml and allowlists the two PR 27 receipts in .gitignore. Its G-2 receipt names human:SomeRandmGuyy as approver.
- PR 27 (bot-00-chief/v3-closeout) is this closeout. Its G-2 receipt, .receipts/bot-00-chief/v3-closeout.json, is added in the final closeout commit and approved by human:SomeRandmGuyy.
- Re-home follow-up, as with PR 22: the ten files from bot-02-risk, bot-04-sniper and bot-09-journal move to their owners in a follow-up change, and PR 27 is then removed from the waiver list.
- Merge method: the ultrathink ship mergeMethod was set to merge in the global ultrathink config. That setting applies to every repository that uses this config.
- Branch commits stay reachable from main after the merge, so the commit SHAs cited in phase records and the audit remain valid.

## Tag

v3: annotated tag on the final closeout commit. Local only; not pushed.

## Tracking

The Notion Task row (Graph ID ut-8a40d0d875-bac7f745) records PR 27, branch bot-00-chief/v3-closeout, PR State Draft. Linear was never created for this graph (free issue limit), so no Linear state exists.

## Debt carried forward (not blocking the archive)

- INT-10 live probe not run. scripts/probe_curve_layout.py exists, but no bonding-curve account is configured in this checkout, so it makes no RPC call and records Status ASSUMED (docs/CURVE_LAYOUT_PROBE.md). The layout stays ASSUMED (src/pumpgrok/tools/onchain/curve_layout.py:33) and RPC-derived curve entries fail closed. INT-10's live-mainnet clause is not met; phase 6 verification row 11a passed on the recorded ASSUMED result. The correction is in .planning/milestones/v3-MILESTONE-AUDIT.md.
- No operator rollback command: restore_active_set has tests only. UPG-03 is met by its own definition and Phase 9 criterion 5; the owner accepted it.
- SUMMARY requirement metadata is missing for 31 requirements.
- Nyquist validation files are absent for every v3 phase (discovery only).
- Design and history documents outside the DOC-04 set keep retired wording: docs/ROSTER.md, docs/FOUNDATION_STACK.md, docs/upgrade-plan-desk-v2.md, docs/DISCOVERY.md, docs/MIGRATION_MAP.md and docs/design/.
- Documents outside the DOC-03 set still use the eight-role wording: agents/README.md, skills/desk-operating-model/SKILL.md, skills/pumpgrok-setup/SKILL.md, scripts/hermes-bootstrap.sh and scripts/README.md. skills/holder-and-flow-analysis/SKILL.md names an absent helper.
- Reviewer finding F-01 (minor): the import guard reads AST imports only, so dynamic imports (pkgutil, importlib) are not modelled. No present path is missed.
- The phase 6 owner waiver of criterion 17 stands (see the phase 6 verification).
- PR-number waivers in gates.yml (16, 17, 18, 19, 20, 22 and 27) are removed in the cleanup change after the last of these merges, as the workflow's own comment requires.

## Not part of v3

Tracker items blocked on owners stay open and are not v3 work: receipt allowlist lines for PRs 23 to 25, PR 26 G-7 and gitleaks allowlist entries, the PR 23 operator ledger path, the claude-ultrathink push, the agent-swarm approvals, and operator readiness visibility (parked by owner decision).
