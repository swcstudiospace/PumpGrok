#!/usr/bin/env python3
"""Generate REQUIREMENTS.md for v4 (ASCII only) from the draft, plans.json and changes-applied.md."""
import re
import sys

sys.path.insert(0, "/tmp/v4/final/gsd")
import _gen_roadmap as g

OUT = g.OUT
H = g.H
DRAFT = open("/tmp/v4/planning/REQUIREMENTS-v4.md").read()

DROPPED = {"EVT-11", "STR-02", "RSK-07"}  # merged into PRC-03, not carried by any plan

FAMILIES = [
    ("EVT", "Event runtime (EVT)"),
    ("GRK", "Grok gateway (GRK)"),
    ("MKT", "Curve truth and live market data (MKT)"),
    ("REC", "Recorder (REC)"),
    ("STR", "Strategy framework (STR)"),
    ("BT", "Backtest v2 (BT)"),
    ("RSK", "Risk hardening (RSK)"),
    ("PRM", "Promotion lifecycle (PRM)"),
    ("LIV", "Dormant live path (LIV)"),
    ("QLT", "Engineering quality (QLT)"),
    ("PRC", "Process (PRC)"),
    ("OBS", "Observability and documentation (OBS)"),
    ("FEE", "Paper fee model (FEE)"),
    ("RT", "Event desk runtime (RT)"),
]

# parse the draft
REQ = {}
for m in re.finditer(r"^- \[ \] ([A-Z]+-\d+): (.*?) Check: `(.*)`\s*$", DRAFT, re.M):
    REQ[m.group(1)] = [m.group(2), m.group(3)]

assert len(REQ) == 98, len(REQ)

# overrides of draft text or check (reconciled against changes-applied.md section C and plans.json)
OVR = {
    "EVT-08": ["Deterministic drain gives a byte-identical ledger across two runs, holds a trading-smoke parity, and equals the legacy smoke-10m hash under fixture_compat with zero skipped tests.",
               "uv run pytest -q tests/replay/test_event_drain_parity.py && ! uv run pytest tests/replay/test_event_drain_parity.py -rs | grep -q SKIPPED"],
    "EVT-10": [None, "uv run pytest -q tests/desk/test_event_wake.py tests/supervisor/test_scheduler.py"],
    "EVT-13": [None, "uv run pytest -q tests/desk/test_hermes_jobs_superseded.py tests/test_doctor_event_mode.py tests/cli/test_wake_mode.py"],
    "GRK-10": [None, "uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_metrics_events.py"],
    "GRK-11": ["The measurement script reports before and after JSON on a fixture with at least 50 admitted candidates, and calls_after is at most 20 percent of calls_before on evidence-50 and soak-3d.",
               "uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/evidence-50 --min-candidates 50 --max-ratio 0.2 && uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/soak-3d --max-ratio 0.2"],
    "LIV-04": ["The arm record is verified and bound to the configuration hash and an expiry; its settings fields exist in the config skeleton.",
               "uv run pytest -q tests/live/test_arm_record.py tests/config/test_live_settings_caps.py"],
    "LIV-07": [None, "{ uv run pumpgrok run --mode live --once; test $? -eq 3; } && uv run pytest -q tests/safety/test_live_refusal_lists_nine.py"],
    "LIV-08": [None, "cd services/desk-signer && uv run pytest -q && cd ../.. && uv run pytest -q tests/safety/test_signer_isolation.py"],
    "QLT-01": ["The default test path excludes the 49 minute soak test; soak runs through make test-soak and nightly CI.",
               "uv run pytest -q tests/quality/test_fast_split.py && make -n test | grep -q 'not slow' && make -n test-soak | grep -q 'm slow'"],
    "QLT-02": [None, "make cov && grep -n 'fail_under' pyproject.toml"],
    "QLT-05": [None, "uv run pytest -q tests/characterization tests/config/test_settings_surface_characterization.py tests/cli/test_backtest_verb_characterization.py tests/supervisor/test_seat_task_characterization.py"],
    "QLT-06": [None, "uv run pytest -q tests/quality/test_no_plain_swallow.py tests/core/test_manifests_errors.py tests/test_doctor_errors.py tests/tools/onchain/test_onchain_errors.py tests/tools/market/test_jupiter_errors.py"],
    "QLT-08": [None, "make mutation-smoke && test -f docs/mutation-testing.md"],
    "QLT-09": [None, "uv run pytest -q ci/tests/test_sbom_step.py"],
    "PRC-03": ["smoke-10m events.hash stays " + H + " at every phase close, and the trading smoke ledger hash is pinned and checked in a clean cwd; each phase records a CHANGELOG before and after pair for both (equal pairs are recorded, not skipped; the trading-smoke pair moves once, in Phase 15, with the paper fee model v2 default flip). The ids EVT-11, STR-02 and RSK-07 of the three designs state this same invariant and are enforced here.",
               "uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py && uv run pumpgrok verify --fixture smoke-10m | grep -q " + H],
    "PRC-04": [None, "! grep -nE 'pull_request\\.number' .github/workflows/gates.yml && uv run pytest -q ci/tests/test_no_pr_waivers.py"],
    "PRC-06": [None, "for p in 11 12 13 14 15 16 17 18 19; do grep -qF \"Phase $p: smoke-10m events.hash after: " + H + "\" CHANGELOG.md || exit 1; grep -qE \"Phase $p: trading-smoke events.hash after: [0-9a-f]{64}\" CHANGELOG.md || exit 1; done"],
    "PRC-07": ["The constitution amendment is applied only by a human-approved pull request (the owner applies and merges) with one step-scoped G-1 waiver and the exact approved text.",
               None],
    "OBS-02": [None, "uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_health_event_sections.py tests/desk/test_metrics_strategy.py"],
    "OBS-05": [None, "test -f .planning/milestones/v4-MILESTONE-AUDIT.md && { uv run pumpgrok run --mode live --once; test $? -eq 3; }"],
    "STR-01": [None, "uv run pytest -q tests/strategies/test_base.py tests/strategies/test_registry.py tests/config/test_paper_event_overlay.py"],
    "EVT-12": [None, None],
    "PRM-05": [None, "uv run pytest -q tests/promotion/test_no_timers.py tests/desk/test_live_paper_risk_wiring.py"],
}

# requirements added by the plan set (changes-applied.md section R); text from that table, checks from plans.json
NEW = {
    "PRC-09": ["The trading `smoke` ledger hash and full row dump are pinned and checked in a clean cwd by every code plan.",
               "uv run pytest -q tests/replay/test_trading_smoke_pin.py"],
    "PRC-10": ["CI lint, typecheck and audit cover services/ when present; the idle-Grok gate runs in CI.",
               "uv run pytest -q ci/tests/test_ci_covers_services.py ci/tests/test_idle_grok_gate.py"],
    "PRC-11": ["Every v4 settings section exists once in the settings skeleton, config-gated off.",
               "uv run pytest -q tests/config/test_v4_settings_skeleton.py"],
    "EVT-14": ["One event catalog and one source and staleness owner.",
               "uv run pytest -q tests/events/test_models_v4_kinds.py tests/events/test_sources.py"],
    "STR-06": ["Parameter identity covers strategy parameters (ParamSet, CandidateParams, load_bounds and harness trial identity use `[strategy.ID.PARAM]`); legacy content hashes are unchanged and pinned by a golden test.",
               "uv run pytest -q tests/upgrade/test_paramset_hash_stable.py tests/upgrade/test_paramset_strategy.py"],
    "FEE-01": ["Paper fee model v2 (venue 100 bps plus the PumpPortal fee when that builder is used, ATA rent on the first buy of a mint, signer priority-fee cap) is selectable, and the default flip records a before and after trading-smoke pair.",
               "uv run pytest -q tests/execution/test_fee_model_v2.py tests/config/test_paper_fees_default.py"],
    "MKT-10": ["EVENT_DECODE_STATUS is VERIFIED only through a human-set reviewed_by; otherwise it stays ASSUMED.",
               "uv run pytest -q tests/tools/onchain/test_event_decode_status.py"],
    "RT-01": ["Event-mode seat cycle bodies exist for all ten seats and run on wakes.",
              "uv run pytest -q tests/desk/test_event_cycles.py tests/desk/test_event_cycles_aux.py"],
    "RT-02": ["Strategy Intents reach exec.place only through the router with ticket and approval allocation.",
              "uv run pytest -q tests/desk/test_intent_router.py tests/desk/test_ticket_approval_allocation.py"],
    "RT-03": ["The event desk composition root wires bus, sources, runtime, gateway, router and promotion edges and refuses to build unless paper.",
              "uv run pytest -q tests/desk/test_event_desk_e2e.py tests/desk/test_event_desk_idle.py"],
    "RT-04": ["Restart recovery re-arms deadlines and restores tapes, peaks, probation and the watch set.",
              "uv run pytest -q tests/strategies/test_recovery.py tests/desk/test_restart_recovery.py tests/desk/test_restart_exit_deadlines.py"],
    "RSK-09": ["Exit sells check only the live gate rows that make sense (rows 1, 2, 5, 6, 8) and are minted autonomous_live while any live position is open, even with a halt, kill, breaker or expired arm.",
               "uv run pytest -q tests/live/test_gate_exit_rows.py tests/live/test_exit_sells_autonomous_live.py"],
    "LIV-17": ["The arm record binds (strategy id, parameter-set hash) pairs with a stated maximum expiry (default 72 hours, hard ceiling 168); any hash change needs a new arm record.",
               "uv run pytest -q tests/live/test_arm_scope.py tests/live/test_arm_expiry_ceiling.py"],
    "LIV-18": ["The signer enforces an instruction-level transaction allowlist with a signer-owned blockhash and verifies the final signed bytes.",
               "cd services/desk-signer && uv run pytest -q tests/test_txpolicy_allowlist.py tests/test_blockhash_signer_owned.py tests/test_final_bytes_verify.py"],
    "LIV-19": ["Stage, kill and halt are mirrored idempotently into the live ledger; signer persistence and drift checks cover SOL and token balances; a failed on-chain send latches a human-clear halt.",
               "uv run pytest -q tests/live/test_stage_mirror.py tests/live/test_reconcile.py tests/live/test_tx_failed_onchain_latch.py"],
    "LIV-20": ["The literal sites of the event source are explicit: nine sites, three risk-owned widened, six sniper and journal sites pinned narrow by an AST test.",
               "uv run pytest -q tests/ledger/test_event_source_literal_sites.py"],
}


def final_reqs():
    out = {}
    for rid, (text, chk) in REQ.items():
        if rid in DROPPED:
            continue
        if rid in OVR:
            t2, c2 = OVR[rid]
            text = t2 if t2 is not None else text
            chk = c2 if c2 is not None else chk
        out[rid] = [text, chk]
    for rid, v in NEW.items():
        assert rid not in out
        out[rid] = list(v)
    return out


def build():
    reqs = final_reqs()
    L = []
    L.append("# Requirements: PumpGrok Desk v4\n")
    L.append("**Defined:** 2026-10-28")
    L.append("**Core Value:** The desk reacts to events instead of polling, runs several bounded strategies in paper against live-recorded data, promotes and demotes them on recorded evidence, and carries a fully built but DORMANT live path that only a human can arm; no agent and no desk process can move real funds.\n")
    L.append("Source: owner decisions of 2026-10-28 (live is armed once by a human and then autonomous inside caps; live limits stay inside the current rules, notional cap at most 1.0 SOL and the D6 fractions; custody is a segregated signer process; constitution amendments are drafted for the owner and applied only by a human-approved pull request; draft PRs 17 to 20 merge first, in the order 18, 19, 20, 17; receipts are approved as human:SomeRandmGuyy in batches at the ship checkpoints after phases 12, 14, 17 and 19), the three v4 designs (A events and Grok gateway, B strategies backtest and data, C risk promotion and live), the N6 critique as applied in `changes-applied.md`, and `plans.json` (74 plans, nine phases). Requirement ids continue the v3 numbering where a family already exists (BT-08 onward, LIV-03 onward, PRC-03 onward). Command forms use `uv run` and exit 0 unless stated.\n")
    L.append("## v4 Requirements\n")
    for fam, title in FAMILIES:
        ids = sorted([r for r in reqs if r.split("-")[0] == fam], key=lambda r: int(r.split("-")[1]))
        if not ids:
            continue
        L.append("### %s\n" % title)
        for r in ids:
            t, c = reqs[r]
            L.append("- [ ] %s: %s Check: `%s`" % (r, t, c))
        L.append("")
    L.append("## Standing process rules from v3\n")
    L.append("PRC-01 (each phase closes with `make lint`, `make typecheck`, `make test`, `./scripts/check.sh`, the replay smoke command and a `.receipts/<seat>/<task>.json` receipt per completion claim) and PRC-02 (branch naming `bot-0N-<seat>/v4-pPHASE-slug`; merge through ultrathink-ship after green CI and the Greptile bar, per PROJECT V3-5) are closed v3 requirements that continue to apply to every v4 phase. They are cited in success criteria as (PRC-01) and are not recounted here.\n")
    L.append("## Merged requirement ids\n")
    L.append("Design A (EVT-11), design B (STR-02) and design C (RSK-07) each stated the same invariant, the unchanged smoke-10m `events.hash`. No plan carries them separately, so they are not requirements of this milestone; the invariant is enforced once, by PRC-03, at every phase close. The pin test lands in Phase 11 so the Phase 11 refactors have the safety net before they start. The gaps in the EVT, STR and RSK numbering are intentional.\n")
    L.append("## Out of Scope\n")
    L.append("| Feature | Reason |")
    L.append("|---------|--------|")
    rows = [
        ("Arming live trading, moving real funds, or any agent-run live action", "Live stays DORMANT in v4. The path is built and tested but only a human arms it once, by the runbook, after the amendment is merged; no agent arms, extends or widens an arm record. Which strategy and parameter hash to arm first, and when, is a human decision outside v4."),
        ("Key material or signing code inside the desk package", "The key lives only in the separate desk-signer process on a host the human provisions; the desk package keeps zero signing symbols (INV-S-01 tightened)."),
        ("Applying the constitution amendment by an agent", "Drafted for owner approval with errata E1 to E5 (OD-01); applied only by a human-approved pull request that the owner applies and merges (PRC-07)."),
        ("External historical data or new data vendors", "Data policy: self-recorded only (D8, AF-10). The recorder and importer never fabricate or back-fill evidence."),
        ("Paid RPC procurement or spend by an agent", "A human may choose and record a provider (OD-05); no v4 code assumes one. Defaults use the public endpoint with a reduced watch set."),
        ("PumpPortal paid trade-stream key, subscribeTokenTrade, subscribeAccountTrade", "Default no (R45); the live feed uses the one free keyless connection plus logsSubscribe on RPC."),
        ("New chains, new venues, or non-pump.fun markets; PumpSwap sells after curve completion", "Solana pump.fun only. Live-eligible strategies exit before the curve completes (OD-08); the venue and fee builder is an interface (TxBuilder), not a second venue; direct pump instruction building is a later option behind that interface."),
        ("New LLM vendors or a second model provider", "Grok through the single gateway only; no hosted evaluation service."),
        ("Strategies beyond legacy_screening, momentum_breakout, new_launch_sniper and mean_reversion", "The four baseline strategies and bounded parameter promotion are in scope; further alpha research is a later milestone."),
        ("Flipping the default wake mode to event", "wake_mode stays cadence through v4; the flip is decided in the next milestone after a week of live-paper evidence (OD-20)."),
        ("Jito bundles or tips enabled by default", "Signer fee policy is priority fee only; tips are an opt-in off by default."),
        ("Telegram live verification, G-4 consumer acknowledgements beyond the one additive contract, bot-06 exit roster change", "Human actions outside the code."),
        ("Manual-ticket exit approval path (PAPER-007)", "Deferred by owner decision 2026-10-23."),
        ("Web UI, multi-tenant, billing", "Spec non-goals."),
    ]
    for a, b in rows:
        L.append("| %s | %s |" % (a, b))
    L.append("")
    L.append("## Traceability\n")
    L.append("Which phases cover which requirements. Populated from `plans.json`; each requirement maps to exactly one phase, the phase that proves it, although a plan of an earlier phase may land part of it (for example the RSK-08 pin lands in Phase 11 and is re-run in Phase 17).\n")
    L.append("| Requirement | Phase | Status |")
    L.append("|-------------|-------|--------|")
    for fam, _ in FAMILIES:
        ids = sorted([r for r in reqs if r.split("-")[0] == fam], key=lambda r: int(r.split("-")[1]))
        for r in ids:
            ph = g.RPM[r]
            L.append("| %s | Phase %d %s | Pending |" % (r, ph, g.PHASE_SLUG[ph]))
    L.append("")
    cnt = {ph: len(g.reqs_of_phase(ph)) for ph in range(11, 20)}
    L.append("**Coverage: v4 requirements: %d total, %d mapped, 0 unmapped**\n" % (len(reqs), len(g.RPM)))
    L.append("| Phase | Requirements |")
    L.append("|-------|--------------|")
    for ph in range(11, 20):
        L.append("| %d %s | %d |" % (ph, g.PHASE_SLUG[ph], cnt[ph]))
    L.append("")
    return "\n".join(L), reqs


if __name__ == "__main__":
    txt, reqs = build()
    open(OUT + "/REQUIREMENTS.md", "w").write(txt)
    print(len(txt), "bytes", len(reqs), "requirements")
