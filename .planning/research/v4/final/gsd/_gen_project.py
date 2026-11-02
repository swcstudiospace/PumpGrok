#!/usr/bin/env python3
"""Generate the full replacement PROJECT.md for v4 from the current file (ASCII only)."""
import re
import sys

sys.path.insert(0, "/tmp/v4/final/gsd")
import _gen_requirements as gr

CUR = open("/root/src/repos/pumpgrok/.planning/PROJECT.md").read().split("\n")
reqs = gr.final_reqs()


def ranges(fam):
    nums = sorted(int(r.split("-")[1]) for r in reqs if r.split("-")[0] == fam)
    out = []
    s = p = nums[0]
    for n in nums[1:]:
        if n == p + 1:
            p = n
            continue
        out.append((s, p))
        s = p = n
    out.append((s, p))
    return len(nums), ", ".join(("%s-%02d" % (fam, a) if a == b else "%s-%02d..%02d" % (fam, a, b)) for a, b in out)


def line(i):  # 1-based line of the current file
    return CUR[i - 1]


def fam_line(fam, desc):
    n, rg = ranges(fam)
    return "- [ ] %s (%d requirements, %s): %s" % (fam, n, rg, desc)


L = []
A = L.append
A("# PumpGrok Desk v4")
A("")
A("## What This Is")
A("")
A("PumpGrok is a Solana memecoin (pump.fun launch) trading desk: ten LLM-backed seats (chief, scout, risk, whale, sniper, rug, exit, shill, signal, journal) plus a catalog of read-only and paper-write tools and a library of skills, packaged in the shape of programming-desk (`ownership.yaml`, receipts, gates G-1..G-7, contracts, prompt assembly, skill manifests) as a Python 3.12 package `src/pumpgrok/`. It is built for the operator who wants the desk to run autonomously in paper mode, under an asyncio supervisor, recording everything in an append-only ledger and replaying deterministically from fixtures. As of v4 the desk is event-driven and multi-strategy: seats wake on typed events instead of cadence polling (cadence stays the default until a later decision), every Grok call is a consequence of an event and passes one gateway, four bounded baseline strategies (legacy_screening, momentum_breakout, new_launch_sniper, mean_reversion) run in paper against a live-recorded data feed with isolated capital slices, and strategies are promoted and demoted on recorded evidence. v4 also builds a fully tested but DORMANT live path: a segregated desk-signer process holds the only key, the desk package holds no key and no signing symbol, and only a human can arm live once, after which the desk may trade autonomously inside the arm record's caps. Nothing in v4 arms live: the only enabled execution adapter is the `PaperAdapter`, `run --mode live` exits 3 on every default start behind the nine-precondition gate, and no agent or desk process can move real funds.")
A("")
A("## Core Value")
A("")
A("The desk reacts to events instead of polling, runs several bounded strategies in paper against live-recorded data, promotes and demotes them on recorded evidence, and carries a fully built but DORMANT live path that only a human can arm; no agent and no desk process can move real funds.")
A("")
A("## Current State")
A("")
A("v2 shipped 2026-10-23 (paper-only desk, ten seats, risk engine, paper adapter on the bonding-curve model, deterministic replay, supervised serve loop, desk gateway, Telegram kill channel; 71 requirements). v3 shipped (closed 2026-10-26): integer money and fail-closed state, `CLAUDE.md` and a trimmed `AGENTS.md`, the holdout-aware `pumpgrok backtest` verb and divergence check, bounded and reversible paper parameter promotion with the constitution amendment of 2026-10-25, and live kept refused (34 requirements, 35 plans). Archived under `.planning/milestones/`: `v2-ROADMAP.md`, `v2-REQUIREMENTS.md`, `v2-MILESTONE-AUDIT.md`, `v3-ROADMAP.md`, `v3-REQUIREMENTS.md`.")
A("")
A("v4 is in progress. The roadmap (Phases 11 to 19), requirements (111) and plans (74, in 45 pull requests) were written on 2026-10-28 and none has started. The product line is main at the commit tagged `v4-base`, taken after the owner-approved merge of draft PRs 16 to 20 (order 18, 19, 20, 17 for 17 to 20). Live is still refused (exit 3).")
A("")
A("## Current Milestone: v4 Event-Driven Multi-Strategy Desk with a Dormant Live Path")
A("")
A("**Goal:** make the desk event-driven (typed event bus, one Grok gateway, event-mode supervisor wake, idle desk silent), run four bounded strategies in paper on live-recorded data with per-strategy slices, backtest v2 and an evidence-based promotion lifecycle, and build the live path fully but dormant (segregated signer, arm record, instruction-level policy, shadow mode, human-approved constitution amendment). Live trading is never enabled by v4.")
A("")
A("**Status:** planned 2026-10-28 in `.planning/ROADMAP.md` and `.planning/REQUIREMENTS.md` (111 requirements, 14 families, 9 phases, 74 plans); ready to plan Phase 11 (`.planning/STATE.md`). Phase 11 plan 11-09 installs these planning files in the repository.")
A("")
A("**Deferred beyond v4** (see `.planning/STATE.md` Deferred Items and Out of Scope):")
A("- Manual-ticket exit approvals: a standing human `exit_rule` approval that the exit seat consults before a rule sell (PAPER-007 narrowed; see Out of Scope).")
A("- Flipping the default `wake_mode` to event, and removing `stop_loss_poll_seconds` from the bounds: decided in the next milestone after a week of live-paper evidence (OD-20).")
A("- PumpSwap sells (`pool=pump-amm`) and direct pump instruction building in the signer: live-eligible strategies exit before the curve completes in v4 (OD-08, OD-14).")
A("- Telegram inbound verification against a live bot: getUpdates behaviour, webhook 409, group chats.")
A("- Persist the pending kill and its offset across restarts, before commit (in memory today).")
A("- The first arm itself (which strategy and parameter hash, and when): a human-only runbook step.")
A("")
A("## Requirements")
A("")
A("### Validated (v2, shipped 2026-10-23)")
A("")
for i in range(33, 54):
    A(line(i))
A("")
A("### Validated (v3, closed 2026-10-26)")
A("")
A("Full v3 record: `.planning/milestones/v3-REQUIREMENTS.md` (34 of 34 complete) and `.planning/milestones/v3-ROADMAP.md`.")
A("")
A("- [x] INT (10 requirements, INT-01..010): integer money across module boundaries, fail-closed corrupt or missing state, integer daily-loss halt, one SOL-to-lamports conversion, id and RNG composition roots, injected-clock live gate, two feature-lineage review fixes, stage-function splits, persisted trailing-stop peaks, bonding-curve layout probe - Phase 6")
A("- [x] DOC (4 requirements, DOC-01..004): `CLAUDE.md` codebase map, `AGENTS.md` cleanup and command verification, docs contradictions corrected, historical design banners - Phase 7")
A("- [x] BT (7 requirements, BT-01..007): run manifests with whole-dataset digest, per-fill replay detail, holdout and walk-forward split, trial recording with 20 and 50 trial limits, bounded metrics, `pumpgrok backtest` verb, holdout-aware harness - Phase 8")
A("- [x] PAP (3 requirements, PAP-01..03): one result schema for backtest and paper trades, divergence check on the D7 defaults, autonomous paper verified on recorded datasets - Phase 8")
A("- [x] UPG (6 requirements, UPG-01..06): content-hashed parameter sets within bounds, promotion gate, evidence record with exact rollback, escalation, SAFE-4 and SAFE-8 advisory BLIND, constitution amendment of 2026-10-25 applied - Phase 9")
A("- [x] LIV (2 requirements, LIV-01..02): live stays refused (exit 3, no live adapter, import-graph test), live-readiness record deferred - Phase 10")
A("- [x] PRC (2 requirements, PRC-01..02): phase gates and receipts, phase branches and pull requests; closed with owner-approved deviations (V3-5) - Phase 6")
A("")
A("### Active (v4)")
A("")
A("<!-- Current scope. One line per requirement family; the individual ids live in .planning/REQUIREMENTS.md. -->")
A("")
A(fam_line("EVT", "typed frozen events in one catalog, P0 lane that never drops, dedup, coalescing, seeded retry, persisted DLQ, graceful shutdown, deterministic drain, SourceSupervisor, event-mode supervisor wake, idle desk, Hermes cutover (EVT-11 is merged into PRC-03)"))
A(fam_line("GRK", "one Grok gateway: prefilter, sanitizer and strict parse, cache, in-flight coalescing, layered persisted budget, fallback ladder, replay backend, exits and risk never wait on Grok, metrics, measurement script"))
A(fam_line("MKT", "token-first curve layout, pump event decoder, human-reviewed probe record and status flips, allowlist price gate, bounded read-only live feed, fail-closed LivePriceSource, marks, graduation, no-send proof for live-data paper"))
A(fam_line("REC", "self-verifying recorder with gaps, importer, trim and rebuild verbs"))
A(fam_line("STR", "strategy protocol, registry, runtime, attribution, four baseline strategies with bounded parameters, parameter identity over strategy parameters, no LLM in any strategy hook (STR-02 is merged into PRC-03)"))
A(fam_line("BT", "Metrics v2, round trips, look-ahead canary and evidence grading, gap segmentation, strategy-aware replay, autonomous idempotent backtest scheduler (continues the v3 BT family)"))
A(fam_line("RSK", "per-strategy slice and kill on existing rows, lazy idle-quiet feed health, live failure classes, entry checks, choke-point proof, 19 STEP_IDS unchanged, exit-sell gate rows (RSK-07 is merged into PRC-03)"))
A(fam_line("PRM", "stage machine BACKTEST to PAPER to LIVE_ELIGIBLE on ledger rows, floors equal to the LiveGate constants, gate reuse, automatic demotion, event-triggered with no timers, writer discipline"))
A(fam_line("LIV", "dormant live path: real gate rows 5 and 6, arm record bound to the configuration hash and (strategy, parameter hash) pairs, stop-state reader, registry, segregated desk-signer with single send and instruction-level allowlist, reconcile, shadow mode, additive live event source, amendment oracle (continues the v3 LIV family)"))
A(fam_line("QLT", "fast and soak test split, coverage floor, complexity ratchet, six hotspot splits behind characterization tests, narrowed excepts, property tests, mutation smoke, SBOM, compose hardening"))
A(fam_line("PRC", "replay hash pins and CHANGELOG pairs per phase, waiver removal, receipt glob, journal and chief closes per phase, amendment by a human-approved pull request, services in CI, settings skeleton (continues the v3 PRC family)"))
A(fam_line("OBS", "doctor v4, health and metric sections, alert rules, docs, nightly event soak, milestone audit, per-strategy report section"))
A(fam_line("FEE", "paper fee model v2 selectable, default flip with a recorded before and after pair"))
A(fam_line("RT", "event-mode seat cycle bodies, Intent to exec.place router, event desk composition root, restart recovery"))
A("")
A("### Out of Scope")
A("")
A("<!-- Explicit boundaries from docs/upgrade-plan-desk-v2.md section 5.11 and the v4 requirements. -->")
A("")
A("- Live trading enablement: arming live, live order placement and any real transaction stay out of scope until the human-approved constitution amendment is applied (plan 18-07, PRC-07) and the human arm procedure is run (`docs/runbooks/go_live.md`); v4 builds the path dormant, `run --mode live` exits 3, and no agent arms, extends or widens an arm record")
A("- Signing and custody inside the desk package: keys exist only in the separate desk-signer process on a host the human provisions; the desk keeps zero signing symbols (INV-S-01 tightened); wallet funding is a human step")
A("- Applying a constitution amendment by an agent: amendments are drafted for the owner and applied only by a human-approved pull request")
A("- Web dashboard or UI beyond text/markdown reports - spec non-goal; `reporting/dashboard.py` is a text renderer only")
A("- New chains, venues, launchpads, data vendors; post-graduation CPMM modelling and PumpSwap sells - D8 keeps the integrations exactly as today; R8/R38 document graduation as a force-close limitation; live-eligible strategies exit before the curve completes (OD-08)")
A("- External historical data or new data vendors - data policy unchanged: self-recorded only (D8, AF-10); the recorder and importer never fabricate or back-fill evidence")
A("- Paid RPC procurement or spend by an agent - a human may choose and record a provider (OD-05); no v4 code assumes one")
A("- PumpPortal trade-stream key - default no (R45); user decision")
A("- Multi-tenant, billing, SaaS packaging - spec non-goal; single-operator internal tool")
A("- New alpha and new signal families beyond the four baseline strategies (legacy_screening, momentum_breakout, new_launch_sniper, mean_reversion), which are in scope under clause 8 as amended on 2026-10-25; paper parameter evaluation and bounded promotion stay in scope")
A("- Engagement level `micro-live` - retired by R16; levels are `research | paper` only, `live` exists solely behind the disabled gate")
A("- Changing `~/src/repos/programming-desk/` itself - spec non-goal; it is mirrored in shape and names only, never imported or edited")
A("- Social posting, coordinated buying, volume tooling, wallet UI automation - forbidden by D7/R39; detection only, enforced by a static test")
A("- Telegram live verification, G-4 consumer acknowledgements beyond the one additive contract, bot-06 exit roster change - human actions outside the code")
A("- Manual-ticket exit approval path (PAPER-007) - deferred by owner decision 2026-10-23")
A("- Flipping the default `wake_mode` to event - cadence stays the default through v4 (OD-20)")
A("- Coverage threshold beyond the measured Phase 11 baseline, ed25519 confirmation signatures, Greptile as a gate, gateway OAuth - deferred (`docs/FOUNDATION_STACK.md` U-5, `docs/design/paper-engine.md` section 7.3)")
A("")
# Context: keep, update Baseline
for i in range(86, 90):
    if i == 88:
        A("**Baseline**")
        A("- v2 and v3 are closed. Milestone v4 branches from main at the commit tagged `v4-base`, after draft PRs 16 to 20 merge (owner decision V4-5); `feat/grokbot-desk-merge` stays untouched (V3-3).")
        continue
    if i == 89:
        continue
    A(line(i)) if i != 88 else None
# keep the rest of Context (line 90 to 121), adding v4 design records
for i in range(90, 122):
    A(line(i))
A("")
A("**v4 design records** (written by their plans, not yet present)")
A("- `docs/design/events-grok.md` - event runtime, bus lanes, sources and the Grok gateway (plan 12-02).")
A("- `docs/design/live-ledgers.md` - the paper and live ledgers, what the stage, kill and halt mirror is and is not (plan 18-06).")
A("- `docs/runbooks/events.md`, `datafeed.md`, `recorder.md`, `promotion.md`, `go_live.md`, `signer.md`, `live_rollback.md` - operator runbooks (plans 14-04, 18-09, 19-07).")
A("- `docs/CURVE_LAYOUT_PROBE.md` and `docs/mutation-testing.md` - probe record and mutation smoke notes (plans 13-02, 11-05).")
A("")
# Constraints: verbatim
for i in range(123, 136):
    A(line(i))
A("")
# Key decisions: verbatim through V3-5
for i in range(137, 179):
    A(line(i))
V4 = [
    ("V4-1: Live is armed once by a human, then the desk is autonomous inside the arm record's caps; v4 builds that path DORMANT and never arms it",
     "Owner decision 2026-10-28. Requires constitution clause 2 amended (draft with errata E1 to E5, see V4-4). A default live start still exits 3 listing the nine preconditions (LIV-07); arming is a human-only runbook step", "Decided"),
    ("V4-2: Live limits stay inside the current rules: notional cap at most 1.0 SOL (a larger value refuses to load) and the D6 fractions; at arm time cap_sol = min(1.0, 200 USD / SOL price minus fees) and funding never exceeds cap plus fees",
     "Owner decision 2026-10-28; OD-12 default and errata E4; throwaway wallet limit unchanged", "Decided"),
    ("V4-3: Custody is a segregated signer process (`services/desk-signer`): own uid and container, own sqlite, key file readable only by the signer uid and placed by the human; the desk package holds no key and no signing symbol (INV-S-01 tightened); IPC over a Unix socket, mode 0660 with a client group",
     "Owner decision 2026-10-28; a compromised desk can always call the socket, so authority lives in signer-side policy (instruction-level allowlist, signer-owned blockhash, final-bytes verification), not in a shared secret. OD-11 and OD-14 defaults", "Decided"),
    ("V4-4: Constitution amendments are drafted for the owner and applied only by a human-approved pull request: plan 18-07 is one owner-applied PR with every copy, a frozen oracle and one step-scoped G-1 waiver, and plan 19-04 removes the waiver",
     "Owner decision 2026-10-28; the draft changes clauses 1, 2, 3, 8, 9, the SNIPER bullet and the closing paragraph; errata E1 (exit sells never suspended, arm record lists (strategy, parameter hash) pairs with a maximum expiry), E2 (failed on-chain send halts like UNKNOWN), E3 (operator-local config outside git), E4 (USD cap rule), E5 (every missed copy) apply (OD-01). Agents never apply, paraphrase or merge the text", "Pending (phase 18)"),
    ("V4-5: Draft PRs 17 to 20 are approved for merge in the order 18, 19, 20, 17 before v4 starts; the merge commit is tagged `v4-base`",
     "Owner decision 2026-10-28; plan 11-01 preflight proves the symbols the later plans rely on (`backtest/equity.py`, `is_writer`, `verify_stored_content`) and fails until the PRs are merged", "Decided"),
    ("V4-6: Receipts are approved as human:SomeRandmGuyy in batches at four ship checkpoints, after phases 12, 14, 17 and 19; a seat never approves its own work",
     "Owner decision 2026-10-28; human-gated plans commit receipts without approved_by and the owner adds it at the checkpoint; the Greptile score is never written into a receipt", "Decided"),
    ("V4-7: The event runtime keeps one typed catalog (`events/models.py`) with priority a pure function of kind, a P0 lane that never drops, bus state in a sidecar sqlite that never touches the ledger, a deterministic drain for replay, and one owner of source staleness; cadence mode stays the default and byte-identical",
     "Design A as corrected by N6 (changes-applied items 11 and 12); keeps smoke-10m unchanged by construction; flipping the default is deferred (OD-20)", "Decided"),
    ("V4-8: Every Grok call is a consequence of an event and passes one gateway (prefilter, sanitizer, cache from an explicit payload, in-flight coalescing, layered persisted budget, fallback ladder); exits and risk never import or wait on it; an idle desk makes zero calls",
     "Design A as corrected by N6 (item 14); GRK-07 and EVT-12 are enforced by static tests and an idle-Grok gate in CI; Hermes cron jobs that duplicate events are disabled in event mode (OD-13)", "Decided"),
    ("V4-9: Replay hash discipline: smoke-10m events.hash stays b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d at every phase close; the trading smoke hash is pinned in plan 11-01 and moves once, in Phase 15, with the paper fee model v2 default flip (OD-09); each phase records both before and after pairs in CHANGELOG.md; every new behavior is config-gated off",
     "N6 items 9 and 23; no design may move a hash silently", "Decided"),
    ("V4-10: Four baseline strategies (legacy_screening, momentum_breakout, new_launch_sniper, mean_reversion) with bounded, version-controlled parameters under `[strategy.ID.PARAM]`; slice weights 0.20 each with a 0.20 reserve (OD-17); a new paper-event overlay allows 6 open positions and 40 trades per day while the live overlay stays at 3 and 20 (OD-02); parameter identity covers strategy parameters and legacy content hashes stay byte-identical",
     "Designs B and C as corrected by N6 (items 4 and 8, 16); no new strategy beyond the four is in scope", "Decided"),
    ("V4-11: Promotion is BACKTEST to PAPER to LIVE_ELIGIBLE on ledger rows, event-triggered with no timers and no Grok; floors equal the LiveGate constants (14 days, 50 closed trades, profit factor 1.2, drawdown 0.15) and the loader refuses looser values; LIVE is derived, never stored; live-eligible strategies must exit before the curve completes (max_progress at most 0.85, exit_progress at most 0.92), and no PumpSwap sells exist in v4",
     "Design C and OD-08, OD-16; any parameter hash change resets the pair to BACKTEST and needs a new arm", "Decided"),
    ("V4-12: Exits are never suspended by entry-only conditions: the gate splits into check_entry (all rows) and check_exit (rows 1, 2, 5, 6, 8), and exit and flatten sells are minted autonomous_live while any live position is open, even with a halt, kill, breaker or expired arm; a failed on-chain send latches a human-clear halt like UNKNOWN; a send is persisted as SIGNED before the RPC call and UNKNOWN is never retried; arm expiry defaults to 72 hours with a hard ceiling of 168 (OD-07)",
     "N6 blocker items 1 to 3 and errata E1 and E2; REVIEW defaults for holder fraction 0.30, strategy loss 0.25 of slice, 4 consecutive losses and drift tolerance 5_000_000 lamports (OD-03) apply until the owner replies", "Decided"),
    ("V4-13: Data policy is unchanged (self-recorded only); evidence grading lets only recorded, complete, long, gap-light data count toward promotion; no paid RPC provider is recorded, so defaults use the public endpoint with a reduced watch set (OD-05)",
     "Owner decision 2026-10-25 (V3-2) carried forward; B-design recorder and N6 items 15 and 17", "Decided"),
    ("V4-14: Quality first and one plan layer: Phase 11 splits six hotspots behind characterization tests, removes every PR-number waiver and adds a receipt glob; `plans.json` (74 plans, 45 pull requests, one per phase and seat, plus a journal CHANGELOG PR and a chief close PR per phase) is the single source for plans, seats, waves and acceptance commands; the amendment PR is the only pull request that is not seat-pure",
     "pr-plan.md and changes-applied.md; the 21 open owner decisions OD-01 to OD-21 carry recommended defaults that apply when no answer arrives by their needed-by point and are listed as unverified in the receipt (`.planning/STATE.md`)", "Decided"),
]
for d, r, o in V4:
    A("| %s | %s | %s |" % (d, r, o))
A("")
# Evolution: verbatim, plus a v4 note
for i in range(180, 201):
    A(line(i))
A("")
A("**v4 note (2026-10-28):** v4 phase numbering continues from v3, so phase 11 is the first v4 phase. Each v4 phase closes with the PRC-01 gate set, a receipt per completion claim, one journal CHANGELOG pull request with both replay hash pairs and one chief `.planning` close. As each v4 family completes, move its items from Active to Validated with the phase reference. The amendment pull request (plan 18-07) is the only change that edits the Out of Scope live and custody rows and the BLIND constraint text, and only a human applies it.")
A("")
A("---")
A("*Last updated: 2026-10-28 after the v4 roadmap and requirements were written (owner decisions V4-1 to V4-14)*")
A("")

txt = "\n".join(L)
open("/tmp/v4/final/gsd/PROJECT.md", "w").write(txt)
print(len(txt), "bytes", len(L), "lines")
