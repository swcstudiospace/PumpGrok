"""Integrated unit set: sequencer units.json plus the N6 section 8 changes.

Importing this module yields U (dict id -> unit) with every modification applied.
Seat strings are full ('bot-02-risk'). Deleted units are removed and their
references stripped. Split units map their dependents through REPLACE.
"""

from __future__ import annotations

import copy
import json

H = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d"
SMOKE_CMD = f"uv run pumpgrok verify --fixture smoke-10m | grep -q {H}"
LIVE_CMD = "uv run pumpgrok run --mode live --once; test $? -eq 3"
OWN_CMD = "python3 ci/gates/check_ownership.py --validate-manifest"
TSMOKE_PIN_CMD = "uv run pytest -q tests/replay/test_trading_smoke_pin.py"

U: dict[str, dict] = {x["id"]: copy.deepcopy(x) for x in json.load(open("/tmp/v4/planning/units.json"))}
DELETED = {"T4", "O2t"}
REPLACE = {"C-09": ["C-09a", "C-09b"], "B16": ["B16a", "B16b"]}

RISK, CHIEF, SNIPER, RUG, SCOUT, SIGNAL, JOURNAL = (
    "bot-02-risk", "bot-00-chief", "bot-04-sniper", "bot-05-rug", "bot-01-scout", "bot-08-signal", "bot-09-journal",
)


def new(id, phase, seat, title, files, deps, reqs, acc, notes, human=False, amend=False, oa=None, kind="design"):
    U[id] = {
        "id": id, "phase": phase, "seat": seat, "title": title, "files": list(files), "depends_on": list(deps),
        "order_after": list(oa or []), "wave": 0, "requirement_ids": list(reqs), "acceptance_commands": list(acc),
        "amendment_wait": amend, "human_gate": human, "pr_group": None, "kind": kind, "design": "v4-integration",
        "receipt": None, "notes": notes,
    }


def mod(id, add_files=(), rm_files=(), add_deps=(), rm_deps=(), acc=None, add_acc=(), rm_acc_sub=(), note="", title=None,
        add_reqs=(), human=None, amend=None):
    u = U[id]
    for f in add_files:
        if f not in u["files"]:
            u["files"].append(f)
    u["files"] = [f for f in u["files"] if f not in set(rm_files)]
    for d in add_deps:
        if d not in u["depends_on"]:
            u["depends_on"].append(d)
    u["depends_on"] = [d for d in u["depends_on"] if d not in set(rm_deps)]
    if acc is not None:
        u["acceptance_commands"] = list(acc)
    u["acceptance_commands"] = [c for c in u["acceptance_commands"] if not any(s in c for s in rm_acc_sub)]
    for c in add_acc:
        if c not in u["acceptance_commands"]:
            u["acceptance_commands"].append(c)
    if note:
        u["notes"] = (u["notes"] + " " if u["notes"] else "") + note
    if title:
        u["title"] = title
    for r in add_reqs:
        if r not in u["requirement_ids"]:
            u["requirement_ids"].append(r)
    if human is not None:
        u["human_gate"] = human
    if amend is not None:
        u["amendment_wait"] = amend


# --------------------------------------------------------------------------------------------
# Phase 11 changes
# --------------------------------------------------------------------------------------------
mod("Q01", acc=[
    "uv run python -c \"import tomllib;c=tomllib.load(open('pyproject.toml','rb'));m=str(c['tool']['pytest']['ini_options']['markers']);assert 'slow' in m\"",
    "uv run python -c \"import hypothesis,mutmut,pytest_cov\"",
], note="N6 item 4 of section 4: the original collect-only acceptance matched the G-2 bypass family; replaced by a config assertion and an import check.")
mod("Q02", add_files=["tests/quality/test_fast_split.py"], acc=[
    "uv run pytest -q tests/quality/test_fast_split.py",
    "make -n test | grep -q 'not slow'",
    "make -n test-soak | grep -q 'm slow'",
], note="N6 section 4 and item 10: acceptance no longer uses collect-only; test_fast_split.py asserts the Makefile and pyproject config.")
new("TSMOKE", 11, RISK, "Pin the trading smoke ledger hash and the full row dump before any engine unit",
    ["tests/replay/test_trading_smoke_pin.py", "tests/replay/pin_support.py",
     "tests/fixtures/replay/pins/trading_smoke.json", "tests/fixtures/replay/pins/trading_smoke_rows.json"],
    ["Q05", "EXT:PRS-16-20-MERGED"], ["PRC-09", "PRC-03"],
    [TSMOKE_PIN_CMD,
     "python3 -c \"import json;d=json.load(open('tests/fixtures/replay/pins/trading_smoke.json'));assert d['fixture']=='smoke' and len(d['events_hash'])==64 and d['seq']>1\"",
     "test -f src/pumpgrok/backtest/equity.py", "grep -rq 'def is_writer' src/pumpgrok/ledger", "grep -rq 'verify_stored_content' src/pumpgrok",
     SMOKE_CMD],
    "N6 verdict (PRs 17 to 20 were not on main at HEAD 641927c, so claims about backtest/equity.py, is_writer and verify_stored_content were UNVERIFIED): the three preflight commands in this acceptance list FAIL until PRs 17 to 20 are merged, which is exactly the point; "
    "B15, C-01b and C-05 rely on those symbols. N6 section 3 item 1 and item 9. The smoke-10m hash covers only the verdict note and rollover rows (41 ticks, no admitted trade). The trading `smoke` fixture "
    "(5 events, seq 11, one entry and one take_profit exit) is the only existing fixture that exercises risk, adapter and exit code. Observed at repo HEAD 641927c in a clean cwd: "
    "events.hash bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54, verify=CONSISTENT seq=11 events=5. The unit MUST re-measure at tag v4-base (after PRs 17 to 20) and pin that value "
    "plus every ledger row (seq, ts, type, source, idempotency_key, payload digest) as a JSON dump. The test runs the replay through the library entry used by `pumpgrok verify` with "
    "monkeypatch.chdir(tmp_path) so a persisted var/ledger.sqlite (operator_active_set) can never change the hash (N6 section 3 item 3). pin_support.py holds the regenerate helper "
    "(`python -m tests.replay.pin_support --regen` prints the new pin, never writes); a legitimate re-pin is a deliberate file edit plus a CHANGELOG before and after pair.",
    kind="quality")
new("Q06", 11, RISK, "CI wiring: lint, typecheck and audit also cover services/ and the future signer, with a self-test",
    ["Makefile", ".github/workflows/ci.yml", "ci/tests/test_ci_covers_services.py"],
    ["Q03"], ["PRC-10", "QLT-01"],
    ["uv run pytest -q ci/tests/test_ci_covers_services.py", "make -n typecheck | grep -q services", "make -n lint | grep -q services", "make -n audit | grep -q services"],
    "N6 section 4 (CI) and item 24. ci.yml runs only `make lint typecheck test audit` and `mypy src/` omits services/. Targets are made path-conditional with $(wildcard services/*/src) so they are no-ops while "
    "services/desk-signer does not exist and automatically cover it once C-09a lands; the signer keeps its own lock and its own pytest job (root testpaths = tests, so signer tests never import solders in the root suite). "
    "Chain on Makefile and ci.yml: Q02, Q03, Q06, Q31, A10g, O5.", kind="quality")
mod("Q03", note="Chain Q02 -> Q03 -> Q06 -> Q31 on Makefile and ci.yml.")
mod("Q31", add_deps=["Q06"])
mod("Q09", note="Also ratchets: the new packages (events, grok, datafeed, strategies, promotion, backtest v2, services/desk-signer) are outside the legacy baseline and stay outside it (N6 item 24 and QLT-03).")

# --------------------------------------------------------------------------------------------
# Phase 12 changes: settings skeleton, one event catalog, one source layer
# --------------------------------------------------------------------------------------------
SECTIONS = ["events", "grok_gateway", "datafeed", "recorder", "strategies", "backtest_v2", "risk_strategy", "promotion", "live", "signer", "paper_fees"]
new("SET0", 12, RISK, "Settings skeleton: every v4 config section lands once, config-gated off, before any feature unit",
    ["src/pumpgrok/config/settings.py"] + [f"src/pumpgrok/config/sections/{s}.py" for s in SECTIONS] + [
        "tests/config/test_v4_settings_skeleton.py", "tests/config/test_events_settings.py", "tests/config/test_live_settings_caps.py"],
    ["Q13s", "TSMOKE"], ["EVT-01", "PRC-11", "LIV-04"],
    ["uv run pytest -q tests/config", "uv run ruff check src/pumpgrok/config", "uv run mypy src/pumpgrok/config", SMOKE_CMD, TSMOKE_PIN_CMD],
    "N6 item 21 and section 1 (contention). settings.py was edited by A0, B06, B09, B10, B16, C-02 and C-06 in a strict chain, with unowned keys (watch_max, mtm_refresh_s, gap_haircut_bps, signer keys). "
    "SET0 is the ONLY unit that edits config/settings.py after Q13s: one section module per area (events, grok_gateway, datafeed, recorder, strategies, backtest_v2, risk_strategy, promotion, live, signer, paper_fees), "
    "one import and one field line in Settings each, defaults that leave every behavior off (events.wake_mode cadence, strategies.runtime_enabled false, live.enabled false, execution.fees.version v1). "
    "It also owns the keys the designs forgot: datafeed.watch_max, datafeed.mtm_refresh_s, backtest.gap_haircut_bps, promotion.* thresholds path, live.arm_max_expiry_hours (hard ceiling 168), "
    "live.notional_cap_sol validator 0 < x <= 1.0 (ConfigError above), live.wallet_allowlist base58 shape, live.drift_tolerance_lamports, signer.socket_path, signer.socket_group, signer.fee_cap_lamports, "
    "signer.confirm_timeout_s, signer.nonce_window_s. N6 item 26: no setting name contains the substrings seed, span or an _at suffix (canonical_request_hash drops those keys), so request-shaping fields are renamed (rng_stream, not seed). "
    "Later units add NO field to settings.py and no new section file; they consume. The Q13c characterization test pins pre-v4 sections, so SET0 never edits it. Per-section tests live in tests/config/test_v4_settings_skeleton.py.")
mod("A0", rm_files=["src/pumpgrok/config/settings.py", "src/pumpgrok/config/sections/events.py", "src/pumpgrok/config/sections/grok_gateway.py", "tests/config/test_events_settings.py"],
    add_deps=["SET0"], note="Settings moved to SET0 (N6 item 21); A0 keeps typed errors and the harness fakes FaultyEventSource and FaultyGrokTransport.")
mod("A1", add_files=["tests/events/test_models_v4_kinds.py"], add_reqs=["EVT-14"],
    note="N6 item 11 and section 1 (event vocabulary): events/models.py is the ONE catalog. It contains Design A kinds (TokenLaunched, PriceTick, PositionTick, SourceStatus, Timer, ExitDeadline, Heartbeat, "
         "CandidateReady, StrategySignal, GrokVerdict, OrderOutcome, RiskEdge, PositionChange, Migration, LargeTransfer, HolderShift) AND every Design B and C kind: NewTokenSeen (alias view of TokenLaunched with the creation fields), "
         "CurveTick, FeedGap, FeedResynced, MintEvicted, DatasetSealed, LlmCallCompleted, BacktestCompleted, StrategyVersionRegistered, ParamsProposed. One publisher interface named EventPublisher (B's Publisher is removed). "
         "Priority stays a pure function of kind; a CurveTick for a held mint is emitted by the datafeed bridge as a PositionTick (P0 lane), never promoted inside the bus, and the mapping table is a tested constant. "
         "DeterministicBus ordering is (ts, priority_rank, source_seq); the backtest uses it unchanged (B16 may not order by (ts, line)).")
mod("A2", add_acc=["uv run pytest -q tests/replay/test_event_drain_parity.py -k smoke_trading", "! uv run pytest tests/replay/test_event_drain_parity.py -rs | grep -q SKIPPED"],
    add_deps=["TSMOKE"],
    note="N6 section 3 items 2 and 5: parity runs on the trading `smoke` fixture (smoke-10m has no trades and cannot prove wake ordering) and compares to the pinned trading_smoke rows, not only to smoke-10m. "
         "DeterministicBus.drain yields to the loop until quiescent (in-flight coalescing futures, retry timers, FixtureClock FIFO continuation order) before advancing virtual time; a test pins this.")
mod("A3", add_reqs=["EVT-14"],
    note="N6 item 12 (one staleness owner): SourceSupervisor owns staleness and publishes SourceStatus; it also owns a SourceStateBook (per-source state, last_frame_at on the injected Clock, stable_since). "
         "DegradedState.ws_data_stale (A4 DegradedBridge), FeedHealth (C-04) and LivePriceSource (B08) READ the book or the SourceStatus events; none of them keeps its own timer or last-tick clock, and nobody calls a separate note_tick path.")

# X1: only the bridge remains (catalog moved into A1)
mod("X1", rm_files=["src/pumpgrok/events/models.py", "tests/events/test_models_v4_kinds.py"], title="Datafeed bridge: datafeed events mapped onto the A1 catalog (models live in A1)",
    note="Catalog moved into A1 (N6 item 11). X1 is the bridge only, with the explicit mapping table CurveTick(held) -> PositionTick, CurveTick(other) -> PriceTick, FeedGap -> SourceStatus(stale)+FeedGap, FeedResynced -> SourceStatus(resynced).")
mod("B06", rm_files=["src/pumpgrok/config/settings.py", "src/pumpgrok/config/sections/datafeed.py"], add_deps=["SET0", "A1"])
mod("B07", add_deps=["A1", "A3"], title="Portal and logs transports as SourceSupervisor sources (decode only), resync, REST fallback, test-suite websocket patches",
    note="N6 item 11: reconnect, staleness, resync and cursor logic are A3's. datafeed/* only decodes frames and implements the transport coroutines SourceSupervisor drives. "
         "N6 section 7: the pump.fun REST fallback (frontend-api.pump.fun) may be Cloudflare-blocked or down; the fallback degrades to SourceStatus(blind) and refuses buys, it never assumes availability.")
mod("B08", add_deps=["A3"], note="N6 item 12: LivePriceSource reads SourceStateBook; no private staleness clock.")
mod("B09", rm_files=["src/pumpgrok/config/settings.py", "src/pumpgrok/config/sections/recorder.py"], add_deps=["SET0", "A1"],
    add_files=["tests/replay/test_live_recorder_manifest_strings.py"],
    note="N6 item 17: FixtureManifest.sources is dict[str, str]; machine keys (integer counts, digests) are written as strings, and every recorded jsonl file is listed (unlisted files are rejected at load). A recorded dataset must load back through load_dataset in the same test. N6 row 27: load rejects timestamp regression (fixtures.py:183), so resynced events keep receipt time in ts and the original time in a separate bt field.")

# --------------------------------------------------------------------------------------------
# Phase 13: sniper-seat prerequisites (fee model, paper factory, entry hook) and human review of decode status
# --------------------------------------------------------------------------------------------
mod("B04", rm_deps=["B03"], note="B04 depends only on B02: its tests are written against symbols that exist today (LAYOUT_STATUS, the decode entry points), so they stay green before and after B03. "
    "This order (agnostic tests first, then the layout change, then the human flip) removes the rug -> risk -> rug PR cycle.")
mod("B04s", rm_deps=["B03"], note="Same reasoning as B04: status-agnostic sniper tests merge before the layout rewrite.")
mod("B03", add_deps=["B04", "B04s"], note="N6 section 2 row 22: CURVE_ACCOUNT_SIZE is imported by three other seats' tests (risk tests/safety, scout tests/tools/market, plus rug's own). "
    "B03 keeps the exported name CURVE_ACCOUNT_SIZE with its current value 49 (minimal legacy decode) and adds CURVE_ACCOUNT_SIZE_V2 = 166; no foreign import changes. If a foreign test still fails, a one-file companion plan by the owning seat merges first (contingent, not counted).")
new("B05e", 13, RUG, "Flip EVENT_DECODE_STATUS to VERIFIED only after a human sets reviewed_by on the event decode record",
    ["src/pumpgrok/tools/onchain/pump_events.py", "tests/tools/onchain/test_event_decode_status.py"],
    ["B01", "B04", "B07", "EXT:HUMAN-REVIEWS-EVENT-DECODE"], ["MKT-10", "MKT-02"],
    ["uv run pytest -q tests/tools/onchain/test_event_decode_status.py tests/tools/onchain/test_pump_events.py tests/datafeed/test_price_source.py", SMOKE_CMD],
    "N6 item 22 and section 6 (e): EVENT_DECODE_STATUS is unowned by any unit, and without a human-reviewed VERIFIED value the price gate treats log-derived prices as unverified and refuses buys. "
    "Human-gated, same closure shape as B05: if the reviewer declines, the status stays ASSUMED, live-fed paper buys stay refused (fail closed), and the event desk runs recorded datasets only. Nothing in v4 flips it by default.",
    human=True)
new("FEE1", 13, SNIPER, "Paper fee model v2 (selectable, default v1): protocol, creator and portal fees, ATA rent on first buy",
    ["src/pumpgrok/execution/fees.py", "tests/execution/test_fee_model_v2.py"],
    ["PRC-RECEIPTS"], ["FEE-01"],
    ["uv run pytest -q tests/execution/test_fee_model_v2.py tests/execution", SMOKE_CMD, TSMOKE_PIN_CMD],
    "N6 item 23, section 5 point 6, and C 4 Fees. VENUE_FEE_BPS is 100 (REVIEW) today. Live reality: PumpPortal takes 0.5 percent on Local trades (documented, /tmp/n1/research.md:8, N6 row 40) plus protocol and creator fees, and a first buy pays ATA rent "
    "(about 2_039_280 lamports, roughly 0.002 SOL, 20 percent of the 0.01 SOL minimum trade). FeeModel gains a `version` field and `FeeModel.for_version`; v1 is byte-identical to today so no hash moves in this unit; v2 constants are REVIEW-marked "
    "and listed in the receipt `unverified` list for the human reviewer (OD-09). Integer lamports only.")
new("PF1", 13, SNIPER, "Separate paper adapter factory so the paper composition root never touches build_adapter",
    ["src/pumpgrok/execution/paper_factory.py", "src/pumpgrok/execution/__init__.py", "tests/execution/test_paper_factory.py"],
    ["PRC-RECEIPTS", "Q10s", "Q10b", "Q10f"], ["MKT-09", "LIV-06"],
    ["uv run pytest -q tests/execution/test_paper_factory.py tests/safety/test_import_graph_no_live.py", SMOKE_CMD, TSMOKE_PIN_CMD],
    "N6 item 18 and section 4 (import graph): test_import_graph_no_live takes the transitive closure of supervisor, cli, backtest, upgrade and paper_adapter including function-level imports, so B17's paper root (inside the guarded supervisor prefix) must not import build_adapter. "
    "build_paper_adapter lives in its own module and never imports anything under execution/live. build_adapter keeps its signature and delegates to it for paper and replay. C-12 later adds the live branch by dotted-path import inside a separate live factory.")
U["C-03s"]["depends_on"] = [d for d in U["C-03s"]["depends_on"] if d != "C-03"]
mod("C-03s", add_files=["src/pumpgrok/execution/entry_hook.py"], add_deps=["PF1"],
    title="PaperAdapter calls an EntryRefresh hook before risk.check (Protocol defined here, config-gated, default off)",
    note="Moved from Phase 17 to Phase 13 (saves a sniper PR): the hook is defined against a Protocol (EntryRefresh.refresh(mint)) in execution/entry_hook.py, tested with a fake gate; C-03 (risk) implements EntryGate against that Protocol. "
         "Config-gated by risk.entry.enabled (SET0, default false) so every hash is unchanged.")

# --------------------------------------------------------------------------------------------
# Phase 14 changes: delete T4, tests in tests/desk, GRK fixtures, CI gate wiring, event cycles
# --------------------------------------------------------------------------------------------
new("GRKFX", 14, RISK, "Synthetic evidence dataset with at least 50 admitted candidates for GRK-11 and the idle test",
    ["tests/fixtures/replay/evidence-50/events.jsonl", "tests/fixtures/replay/evidence-50/manifest.json", "tests/fixtures/replay/evidence-50/llm.jsonl",
     "tests/replay/test_evidence50_fixture.py"],
    ["A0"], ["GRK-11"],
    ["uv run pytest -q tests/replay/test_evidence50_fixture.py"],
    "N6 item 15 and section 3 item 8: GRK-11 on soak-3d is vacuous (2 mints, no evidence fields, no candidate passes the filter, so before and after are both 0). "
    "This fixture is hand-authored (coverage=fixture, never promotion evidence) with unique_buyers, name, symbol and creator fields so that passes_filter admits at least 50 candidates; the test asserts the count with the production filter. "
    "Manifest values are strings and every jsonl is listed (N6 row 26).")
mod("A5", add_files=["tests/grok/test_cache_key_payload.py"],
    note="N6 item 14 and section 3 item 6: the cache key payload is explicit and made only of ints and strings: {kind, agent, model, prompt_sha, schema, sanitizer, input} where every Decimal is rendered with str(); canonical_request_hash is NOT fed raw requests (its volatile-key regex drops keys containing _at, seed or span, and _freeze raises TypeError on Decimal). "
         "A test asserts a Decimal-bearing request yields a stable key and that renamed age-like fields do not vanish from the key. Also: GrokOps.precheck message must not read budget.max_per_day (absent on LayeredBudget), N6 row 7. N6 row 5 (claim corrected): the fallback ladder is tied to DegradedState.signal_scoring_mode whose actual values are llm, rule_fallback, observe_only_buys and replay (degraded.py:89-97); there is no degraded.bus_backlog, so the gateway does not read one. "
         "Real budget exhaustion (not a mocked limiter) is exercised end to end to prove the fallback (N6 section 6 d).")
mod("A4", rm_deps=["T4"], add_files=["tests/desk/test_event_wake.py", "tests/desk/test_event_mode_run_once.py"], add_deps=["TSMOKE"],
    add_acc=["uv run pytest -q tests/desk/test_event_wake.py tests/desk/test_event_mode_run_once.py", "! uv run pytest tests/desk/test_event_wake.py -rs | grep -q SKIPPED",
             "uv run pytest -q tests/replay/test_event_drain_parity.py", TSMOKE_PIN_CMD],
    rm_acc_sub=["tests/supervisor/test_event_wake.py", "tests/events/test_idle_zero_grok.py"],
    note="N6 item 9 and 10, section 2 row 12, section 3 item 2. Correction of the design text: A4 DOES touch supervisor/scheduler/serve.py, which hosts run_once_replay (and `verify` calls it, cli/verbs_ops.py:190); "
         "'untouched by construction' is replaced by 'unchanged by test': the trading-smoke row pin (TSMOKE) and smoke-10m hash both stay green and the A2 parity runs on `smoke`. "
         "Tests are chief-owned under tests/desk (EVT-08 is in this unit's acceptance); T4 is deleted. Allowed timers (EVT-10) gain: MTM refresh every datafeed.mtm_refresh_s (45 s) only while positions are open, and reconcile-on-start (N6 item 12 and section 1 Timers).")
mod("A7", rm_deps=["T4"], add_files=["tests/desk/test_metrics_events.py"],
    acc=["uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_metrics_events.py", "! uv run pytest tests/desk/test_metrics_events.py -rs | grep -q SKIPPED"],
    note="N6 item 10 and 27: tests moved to tests/desk (chief). Adds per-strategy P (performance: pnl, round trips, drawdown) and L (live path: arm state, signer attestation, kill) metric families alongside the Grok and event families, registered only in event mode so NINE_FAMILIES stays valid.")
mod("A8", rm_deps=["T4"], add_files=["tests/desk/test_hermes_jobs_superseded.py"],
    acc=["uv run pytest -q tests/desk/test_hermes_jobs_superseded.py", "! uv run pytest tests/desk/test_hermes_jobs_superseded.py -rs | grep -q SKIPPED"],
    note="N6 item 13 and section 2 row 15: `require_activity` does not make idle cost 0 because [SILENT] is printed by the model inside an already running session. Decision: in event mode the Hermes chief-journal-rollup is DISABLED too (superseded_by: events) "
         "and the daily rollup is event-triggered by the supervisor journal cycle on Timer(daily_rollover) (RT1b), so an idle desk starts zero Hermes sessions. rug-watch is likewise disabled (it is gated only inside the session, prompts/rug-watch.md:14). Baseline measured about 12 sessions per hour, 10 of them idle.")
mod("A9", add_deps=["GRKFX"], acc=["uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/evidence-50 --min-candidates 50 --max-ratio 0.2",
                                     "uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/soak-3d --max-ratio 0.2"],
    note="N6 item 15: the ratio gate runs on evidence-50 (at least 50 admitted candidates, non-vacuous) in addition to soak-3d. Report states modeled counts.")
new("RT1a", 14, CHIEF, "Event-mode seat cycle bodies, part 1: scout, signal, risk, sniper, exit on wakes, legacy path through the gateway",
    ["src/pumpgrok/supervisor/scheduler/event_cycles.py", "tests/desk/test_event_cycles.py", "tests/desk/test_event_golden_hashes.py"],
    ["A4", "A5", "A6", "GRKFX", "TSMOKE", "PRC-RECEIPTS"], ["RT-01", "EVT-10"],
    ["uv run pytest -q tests/desk/test_event_cycles.py tests/desk/test_event_golden_hashes.py", "! uv run pytest tests/desk/test_event_cycles.py -rs | grep -q SKIPPED", SMOKE_CMD, TSMOKE_PIN_CMD],
    "N6 item 5 and section 7: every seat cycle body exists only as _replay_* (supervisor/scheduler/replay_cycles.py:27-136); event mode needs real bodies. RT1a covers the entry chain: scout (TokenLaunched/Migration), signal (CandidateReady via the Grok gateway, never GrokAgent.run), "
    "risk (CandidateReady, PositionTick coalesced to 1/s, OrderOutcome, RiskEdge), sniper (BUY verdicts through exec.place) and exit (PositionTick, ExitDeadline) exactly as SEAT_WAKES says. wake_mode stays cadence by default, so cadence, replay and `verify` code paths are not edited. "
    "Golden hashes events-smoke-10m and events-soak-3d are produced here by running the event desk on the recorded datasets (recorded in CHANGELOG by the Phase 14 journal plan); the legacy hash lines stay equal.")
new("RT1b", 14, CHIEF, "Event-mode seat cycle bodies, part 2: whale, rug, shill, journal (event-triggered rollup), chief, heartbeat",
    ["src/pumpgrok/supervisor/scheduler/event_cycles_aux.py", "tests/desk/test_event_cycles_aux.py", "tests/desk/test_journal_rollup_event.py"],
    ["RT1a", "A7", "A8"], ["RT-01", "EVT-13"],
    ["uv run pytest -q tests/desk/test_event_cycles_aux.py tests/desk/test_journal_rollup_event.py", "! uv run pytest tests/desk/test_event_cycles_aux.py -rs | grep -q SKIPPED", SMOKE_CMD],
    "Remaining seats (chief on RiskEdge/SourceStatus/escalation rows, whale on LargeTransfer, rug on held PositionTick/HolderShift/Migration, shill heartbeat only, journal on OrderOutcome/PositionChange/Timer(daily_rollover) with a flush only when dirty). "
    "The journal cycle performs the daily rollup that Hermes no longer does (A8, N6 item 13).")
mod("A12", add_files=["tests/test_doctor_time_sync.py"], add_acc=["uv run pytest -q tests/test_doctor_time_sync.py"],
    note="N6 section 7 (time sync): doctor adds a read-only NTP/clock skew probe (compare against a configured reference, warn above the skew tolerance); event mode and live both refuse to start on failure because assert_no_skew (scheduler/degraded.py:52) refuses ledger appends on backward steps, and arm expiry is evaluated on two clocks. "
         "A12 also carries the missing doctor check named in N6 section 1: doctor refuses event mode while a superseded Hermes job is enabled.")
mod("A10", rm_deps=["T4"], add_files=["tests/events/test_idle_zero_grok.py", "tests/degradation/test_grok_hang_exit.py", "ci/gates/run_all.py", "ci/tests/test_idle_grok_gate.py", ".github/workflows/ci.yml"],
    add_deps=["RT1b", "A9", "Q06"],
    add_acc=["uv run pytest -q tests/events/test_idle_zero_grok.py tests/degradation/test_grok_hang_exit.py ci/tests/test_idle_grok_gate.py", "grep -q check_idle_grok ci/gates/run_all.py", "grep -q idle-grok .github/workflows/ci.yml", "grep -q idle-grok Makefile"],
    note="N6 item 24 and section 4 (CI): ci/gates/ is overlaid from the base ref, so a new gate script is inert in its own PR and absent from run_all.py. The idle-Grok gate is therefore wired three ways at once: run_all.py (edited here, effective from the next PR), a pytest wrapper ci/tests/test_idle_grok_gate.py "
         "(active in `make test` immediately), and a ci.yml step plus the Makefile idle-grok target. test_idle_zero_grok and test_grok_hang_exit were T4 files and now live here, after the code they test exists (no importorskip).")

# --------------------------------------------------------------------------------------------
# Phase 15 changes
# --------------------------------------------------------------------------------------------
new("R0", 15, RISK, "Generalize ParamSet, CandidateParams, load_bounds and the harness trial identity to strategy parameters",
    ["src/pumpgrok/upgrade/params.py", "src/pumpgrok/upgrade/bounds.py", "src/pumpgrok/upgrade/gate.py", "src/pumpgrok/backtest/candidate.py", "src/pumpgrok/backtest/harness.py", "src/pumpgrok/backtest/evaluate.py",
     "tests/upgrade/test_paramset_strategy.py", "tests/upgrade/test_paramset_hash_stable.py", "tests/upgrade/test_bounds_strategy_sections.py", "tests/backtest/test_harness_strategy_identity.py",
     "tests/upgrade/fixtures/bounds_strategy_sample.toml"],
    ["PRC-RECEIPTS", "TSMOKE"], ["STR-06", "STR-01"],
    ["uv run pytest -q tests/upgrade tests/backtest/test_harness_strategy_identity.py", SMOKE_CMD, TSMOKE_PIN_CMD],
    "N6 item 4 and section 1 (param identity). Today ParamSet holds only `filter` and `exits` (upgrade/params.py:31-33), load_bounds reads only those sections (upgrade/bounds.py:86), and evaluate_candidate takes a ParamSet (upgrade/gate.py:84), "
    "so B's [strategy.ID.PARAM] bounds would be silently ignored and C's (strategy id, param hash) binding has no hash to bind. R0 adds an optional `strategy: {id: str, params: dict}` member (default None, extra=forbid kept), "
    "validated through the registered StrategyParams model (resolved lazily by id; unknown id or unknown/out-of-bounds key is a ValidationError, never clamped), makes load_bounds parse `[strategy.ID.PARAM]` sections with the same KeyBound/OutOfBoundsError semantics, "
    "and makes the harness TrialLedger identity include the strategy id and params hash. content_hash for every existing (strategy=None) ParamSet MUST stay byte-identical: tests/upgrade/test_paramset_hash_stable.py pins golden hashes for the legacy shapes, "
    "so PR 17/19 evidence stays valid. No bounds are added to upgrade_bounds.toml here (B12 to B14 do that). Runs before B10 and B12.")
mod("C-01", add_files=["src/pumpgrok/strategies/allocation.py", "tests/strategies/test_allocation.py"], add_reqs=["STR-03"],
    note="N6 item 8: B10 needed strategy_of and allocation.slice_lamports, C-02 needed B10's allocation.py, B10 needed C's ticket refs: a cycle. strategy_of (ledger/strategy_state.py) AND allocation.py (leaf module, integer floor math, no risk imports) now live in C-01; "
         "B10 and C-02 both depend on C-01 and neither depends on the other for these. N6 row 11: replay buys use the constant REPLAY_TICKET (supervisor/scheduler/orders.py:50), so per-strategy attribution does not exist on the replay path B16 reuses; "
         "allocate_ticket(strategy_id, param_set_hash) is the only attribution carrier and the router (RT2) allocates real tickets for strategy intents. "
         "OD-06: day ticket counter refuses allocation at 999 with a typed error (no 4-digit contract change, no silent wrap); tickets are allocated for approved intents only.")
mod("B10", rm_files=["src/pumpgrok/strategies/allocation.py", "src/pumpgrok/config/settings.py", "src/pumpgrok/config/sections/strategies.py"],
    add_files=["src/pumpgrok/config/overlays/paper-event.toml", "tests/config/test_paper_event_overlay.py"], add_deps=["R0", "SET0", "A1"],
    note="Settings come from SET0. The new overlay paper-event.toml carries the multi-strategy paper desk caps (OD-02: recommended max_open_positions 6, max_trades_per_day 40, runtime_enabled true, wake_mode event) and live.enabled=false; "
         "the existing overlays and therefore every replay hash are untouched, and test_live_disabled_overlays still iterates it. Live limits stay inside current rules: the live gate keeps min(2 percent per trade, 5 percent per token, notional_cap_sol <= 1.0 SOL).")
mod("B12", add_deps=["R0", "FEE2"], note="N6 item 22: exit_progress <= 0.92 and max_progress <= 0.85 are bounds so a LIVE_ELIGIBLE position cannot be stranded on a completed curve (no PumpSwap sells in v4). "
    "N6 item 29: stop_loss_poll_seconds is ignored under wake_mode=event; the bounds entry stays (cadence is default) and a test asserts it has no effect in event mode.")
mod("B13", add_deps=["R0", "FEE2"], note="Same progress ceilings as B12.")
mod("B14", add_deps=["R0", "FEE2"], note="Same progress ceilings as B12 (mean_reversion already caps progress at 0.80).")
new("FEE2", 15, RISK, "Flip the paper fee model default to v2 and re-pin the trading smoke hash (before and after pair recorded)",
    ["src/pumpgrok/config/sections/paper_fees.py", "src/pumpgrok/cli/backtest*.py", "tests/fixtures/replay/pins/trading_smoke.json", "tests/fixtures/replay/pins/trading_smoke_rows.json",
     "tests/config/test_paper_fees_default.py", "tests/backtest/test_fee_parity.py"],
    ["FEE1", "SET0", "TSMOKE", "PF1"], ["FEE-01", "PRC-03"],
    ["uv run pytest -q tests/config/test_paper_fees_default.py tests/backtest/test_fee_parity.py", TSMOKE_PIN_CMD, SMOKE_CMD],
    "N6 item 23 (paper fee model with before and after hash lines). The ONLY unit in v4 that deliberately moves the trading smoke hash (fees change cash_delta and venue_fee_lamports in rows). smoke-10m has no trades and stays b69c.... "
    "Same unit makes the backtest CLI build FeeModel from settings (cli/backtest.py:628 hard-codes VENUE_FEE_BPS) so backtest and paper share one fee model. The pin JSON files are re-generated deliberately; the Phase 15 journal plan records "
    "`Phase 15: trading-smoke events.hash before: <old pin>` and `after: <new pin>`. Needs OD-09 review of the v2 constants before merge.")
new("REC", 15, RISK, "Restart-recovery state for strategies: tape snapshot, per-strategy exit peaks, probation state, watch-set seeds",
    ["src/pumpgrok/strategies/recovery.py", "src/pumpgrok/strategies/tape.py", "src/pumpgrok/strategies/runtime.py", "tests/strategies/test_recovery.py"],
    ["B10", "B11", "C-01", "A1"], ["RT-04", "STR-03"],
    ["uv run pytest -q tests/strategies/test_recovery.py tests/strategies", SMOKE_CMD, TSMOKE_PIN_CMD],
    "N6 item 23 and section 7 (restart recovery). Library half: StrategyRuntime.restore(snapshot) rebuilds MintTape rings from the recorder tail or the last N ticks, per-strategy trailing-stop peaks and entry prices from the ledger fold, probation/cooldown state from ledger rows, "
    "and the held-mint watch-set seeds from open positions; ExitDeadline times are recomputed from PositionOpened ts plus max_hold_s. Deterministic: a test kills the runtime mid-run on the strat-* fixtures, restores, and asserts the continued run equals the uninterrupted run (fills and hash). "
    "The chief wiring half is RT4 (Phase 17).")
new("RT2", 15, CHIEF, "Intent to exec.place router: ticket allocation, approval allocation and exit routing for strategy intents",
    ["src/pumpgrok/supervisor/intent_router.py", "tests/desk/test_intent_router.py", "tests/desk/test_ticket_approval_allocation.py"],
    ["B10", "C-01", "R0", "A4", "PRC-RECEIPTS"], ["RT-02", "STR-03"],
    ["uv run pytest -q tests/desk/test_intent_router.py tests/desk/test_ticket_approval_allocation.py", "! uv run pytest tests/desk/test_intent_router.py -rs | grep -q SKIPPED", SMOKE_CMD, TSMOKE_PIN_CMD],
    "N6 item 5 and section 7: the missing hop between a strategy Intent and a sniper exec.place call. Enter intents: allocate_ticket(strategy_id, param_set_hash) (OD-06 guard), size via the allocator, mint the approval the current autonomy level allows "
    "(a paper fill needs the autonomy level a human set with `pumpgrok state autonomy`; below autonomous-paper the router does NOT mint and the intent is journaled as refused, never silently approved), then call exec.place through the same entry the replay path uses "
    "(supervisor/scheduler/orders.py), with one ledger transaction per intent and idempotency key exec_place_key(ticket, side, decision_id). Exit intents use the existing four exit reasons and the global exit book filtered by ticket (B17). "
    "The router has no Grok handle and no live handle. N6 section 6 (e): a human must set autonomous-paper, otherwise approval_missing; this is documented in the runbook and checked by a test.")
mod("B17", add_deps=["PF1"], note="N6 item 18: the paper root builds its adapter with execution.paper_factory.build_paper_adapter, never build_adapter, so the supervisor import closure never reaches execution/live.")

# --------------------------------------------------------------------------------------------
# Phase 16: split B16, bisect, drain order
# --------------------------------------------------------------------------------------------
b16 = U.pop("B16")
b16a = copy.deepcopy(b16)
b16a.update(id="B16a", title="Strategy-aware replay: event source (bisect-indexed curve source), strategy run, gaps, grading",
            files=["src/pumpgrok/backtest/event_source.py", "src/pumpgrok/backtest/strategy_run.py", "src/pumpgrok/backtest/gaps.py", "src/pumpgrok/backtest/grading.py",
                   "tests/backtest/test_strategy_replay.py", "tests/backtest/test_lookahead.py", "tests/backtest/test_grading.py", "tests/backtest/test_gaps.py", "tests/backtest/test_dataset_curve_source_perf.py",
                   "tests/fixtures/replay/strat-gap/events.jsonl", "tests/fixtures/replay/strat-gap/gaps.jsonl", "tests/fixtures/replay/strat-gap/manifest.json"],
            depends_on=["B09", "B10", "B11", "B15", "X1", "A2", "FEE2", "R0"],
            acceptance_commands=["uv run pytest -q tests/backtest/test_strategy_replay.py tests/backtest/test_lookahead.py tests/backtest/test_grading.py tests/backtest/test_gaps.py tests/backtest/test_dataset_curve_source_perf.py", SMOKE_CMD, TSMOKE_PIN_CMD],
            notes="N6 section 3 items 4 and 5 and section 1 (ordering): DatasetCurveSource indexes ticks per mint and answers latest() with bisect (FixtureCurveSource._latest scans all ticks per call, replay/sources.py:58-75, quadratic over multi-day data; a perf-shaped test bounds comparisons). "
                  "Backtest replays through A2's DeterministicBus ordered by (ts, priority_rank, source_seq), the same order as the live desk; it does not use (ts, line). Gap/segment replay reuses the drain-until-quiescent loop. Fixture manifest values are strings (N6 item 17).")
b16b = copy.deepcopy(b16)
b16b.update(id="B16b", title="Backtest scheduler, result store and BacktestEvidenceProvider",
            files=["src/pumpgrok/backtest/scheduler.py", "src/pumpgrok/backtest/store.py", "src/pumpgrok/backtest/evidence.py", "tests/backtest/test_scheduler.py", "tests/backtest/test_evidence_provider.py"],
            depends_on=["B16a", "A1"],
            acceptance_commands=["uv run pytest -q tests/backtest/test_scheduler.py tests/backtest/test_evidence_provider.py", SMOKE_CMD],
            notes="Settings come from SET0 (backtest_v2). Reacts to DatasetSealed, StrategyVersionRegistered and ParamsProposed from the A1 catalog (no B-private events); run key = sha256(strategy_version_id, dataset_digest, params_hash, rng_stream).")
U["B16a"], U["B16b"] = b16a, b16b
mod("B15", add_deps=["FEE2"], note="Annualization below 7 days: annualization_valid=false and annualized_return is None (N6 section 6 f).")
mod("B18", add_deps=["B16b"], note="N6 row 25: `run --record` is an exit-5 stub today (cli/verbs_state.py:88); this unit implements it for real, on the B09 recorder.")
mod("B19", add_deps=["B16b"])

# --------------------------------------------------------------------------------------------
# Phase 17 changes
# --------------------------------------------------------------------------------------------
mod("C-02", rm_files=["src/pumpgrok/config/settings.py", "src/pumpgrok/config/sections/risk_strategy.py"], add_deps=["SET0", "B16b"],
    note="N6 item 1 (blocker, engine side) preparation: the new strategy-slice and kill steps never apply to sells, as for all EXIT_SKIP_STEPS. OD-03: strategy loss fraction default 0.25 of slice, N consecutive losses default 4 (REVIEW).")
mod("C-03", add_deps=["C-03s"], note="N6 item 22 and section 5 point 8: entry checks also require the wallet's own ATA extensions (ImmutableOwner fine; CpiGuard and default-frozen reject) and the check is repeated immediately before send by the signer (C-09b). "
    "EntryGate implements the EntryRefresh Protocol defined by C-03s. OD-03: holder concentration fraction default 0.30 (REVIEW).")
mod("C-04", note="N6 item 12: FeedHealth is fed from SourceStatus events and the A3 SourceStateBook; it owns no timer. Lazy evaluation at check() and on RiskEdge from a transport disconnect.")
mod("C-05", add_deps=["R0", "A3", "B16b"], rm_deps=["B16"],
    note="Thresholds file (human-required) carries OD-08: LIVE_ELIGIBLE needs strategy max_progress <= 0.85 and exit_progress <= 0.92 (live strategies exit before curve completion; PumpSwap sells are out of scope for v4). "
         "Stage rows are ConfigChanged rows in the PAPER ledger (var/ledger.sqlite) written by gate:promotion; the live ledger gets a mirror (C-17, N6 item 20).")
new("RT3", 17, CHIEF, "Event desk composition root: bus, sources, strategy runtime, gateway, router, promotion edges, Timer",
    ["src/pumpgrok/supervisor/event_desk.py", "tests/desk/test_event_desk_e2e.py", "tests/desk/test_event_desk_idle.py"],
    ["A1", "A3", "A4", "A5", "A6", "B07", "B08", "B10", "C-05", "RT1b", "RT2", "B17", "PRC-RECEIPTS"], ["RT-03", "EVT-12"],
    ["uv run pytest -q tests/desk/test_event_desk_e2e.py tests/desk/test_event_desk_idle.py", "! uv run pytest tests/desk/test_event_desk_e2e.py -rs | grep -q SKIPPED", SMOKE_CMD, TSMOKE_PIN_CMD],
    "N6 item 5: the missing E2E runtime unit with the dependency list the critique names (A1, A3, A4, A5, A6, B07, B08, B10, C-05). Wires WallClock-or-FixtureClock, SourceSupervisor with the B07 transports, the datafeed bridge, StrategyRuntime and per-strategy ExitRules, "
    "the GrokGateway, the RT1 seat cycles and the RT2 router, PaperAdapter from the paper factory, RiskEngine with slice weights and FeedHealth, the EntryGate, and the PromotionEvaluator subscribed to PositionChange(closed), RiskEdge, "
    "Timer(daily_rollover) and BacktestCompleted. E2E test: recorded `smoke` and strat-* datasets through the full desk to asserted fills, idle 24 virtual hours with zero Grok calls and zero Timers other than the allowed set. "
    "It still refuses to build unless the effective mode is paper (live stays exit 3).")
new("RT4", 17, CHIEF, "Restart recovery wiring: bus recover, tapes, watch set, ExitDeadline re-arm, probation, exit peaks, reconcile-on-start",
    ["src/pumpgrok/supervisor/recovery.py", "tests/desk/test_restart_recovery.py", "tests/desk/test_restart_exit_deadlines.py"],
    ["RT3", "REC", "A1", "PRC-RECEIPTS"], ["RT-04"],
    ["uv run pytest -q tests/desk/test_restart_recovery.py tests/desk/test_restart_exit_deadlines.py", "! uv run pytest tests/desk/test_restart_recovery.py -rs | grep -q SKIPPED", SMOKE_CMD, TSMOKE_PIN_CMD],
    "N6 item 23 and section 7. On start: EventBus.recover() processes pending events once, the held-mint watch set and tapes are restored through StrategyRuntime.restore (REC), every open position gets its ExitDeadline timer re-armed from PositionOpened ts plus max_hold_s, "
    "per-strategy exit peaks come from the ledger fold, probation state from rows, and a one-time reconcile (store.verify, position/ledger fold) runs as the allowed reconcile-on-start timer. Crash tests: kill mid-run at three points on `smoke` and the strat-* fixtures, restart, and assert ledger rows equal the uninterrupted run and no position loses its exit.")
mod("WIRE-17", add_deps=["RT3"], note="WIRE-17 stays the thin wiring of slice weights, FeedHealth, entry gate and the PromotionEvaluator subscription; RT3 is the full composition. They merge in one plan.")

# --------------------------------------------------------------------------------------------
# Phase 18 changes
# --------------------------------------------------------------------------------------------
mod("C-01b", note="N6 item 20 and section 5 point 3: read_stop_state takes the PAPER ledger path (stage rows, kills, halts as written by the desk) and the LIVE ledger path (orders, fills, UNKNOWN halts) explicitly and reports which ledger each fact came from. "
    "Stated plainly in docs: halts, stage and strategy kills come from a desk-writable ledger, so the signer's re-derivation is a CONSISTENCY check, not an independent control. The independent controls are the HMAC arm record, the wallet allowlist, the caps and the instruction-level tx verification.")
mod("C-07", add_files=["src/pumpgrok/risk/engine/steps.py", "tests/ledger/test_event_source_literal_sites.py"], add_reqs=["LIV-20"],
    title="Contract: live event source (additive), regenerated schemas, change document, and the explicit list of literal sites",
    note="N6 item 7 and section 2 row 28. All nine sites that spell the source literal: RISK-owned and changed here: ledger/events.py:31 (EventSource), ledger/store.py:31 (SOURCES), risk/engine/steps.py:222 (reputation escalation downgrades unknown sources to paper, which would mislabel a live row), plus the 18 schemas under contracts/events. "
         "Deliberately left NARROW (paper or manual only, must never emit live) and pinned by an AST test, tests/ledger/test_event_source_literal_sites.py: sniper tools/execution paper_adapter adapter.py:57, buy.py:36, marks.py:32 and execution/__init__.py:28; journal tools/portfolio/ledger_read.py:30 (filter) and ledger_write.py:38 (agent write tool, must not mint live rows). "
         "The tool roster contract (contracts/tool-rosters/bot-09-journal.yaml:56) therefore does not change. If mypy proves one of the narrow sites must widen, a one-file companion plan by the owning seat merges FIRST (contingent, not counted). "
         "G-4: declare breaking: false, `semantic_changes: []`, version the next minor, list EVERY regenerated schema file individually in `surfaces` (contracts/** does not satisfy G-4), regenerate with scripts/generate-event-schemas.py (checked by make check). "
         "contract_consumers for contracts/events/** is all ten seats; for a non-breaking change acknowledgements are informational but a recorded rejection blocks, so start this unit first in Phase 18 (or earlier).")
mod("C-08", note="N6 items 19 and section 5 point 3: frames carry a nonce and a signer-clock timestamp; the signer persists a nonce window (signer.nonce_window_s) and refuses replays across restarts; `hello` returns signer time and the desk refuses to proceed on skew above tolerance (time-sync check, doctor reads it); "
    "`attest` and `identity` are frames served over the authenticated socket (never files in the shared var/ the desk can write, N6 section 5 point 3). The place frame carries strategy_id AND param_set_hash. Socket mode 0660 with group signer.socket_group (0600 with a separate uid cannot admit the desk). "
    "SO_PEERCRED across containers reads mapped uids and with one shared uid authenticates nothing beyond signer policy: the doc states that.")
mod("C-06", rm_files=["src/pumpgrok/config/settings.py", "src/pumpgrok/config/sections/live.py"], add_deps=["SET0"],
    add_files=["tests/live/test_gate_exit_rows.py", "tests/live/test_arm_scope.py", "tests/live/test_arm_expiry_ceiling.py"], add_reqs=["RSK-09", "LIV-17"],
    note="N6 item 1 (BLOCKER) and item 2 (BLOCKER). Gate split: LiveGate exposes check_entry (all nine rows) and check_exit (rows 1, 2, 5, 6 and 8 only: mode, enabled, wallet allowlist, notional cap, adapter registered). Rows 3, 4, 7 (arm expiry) and 9 (no_active_stop) are NOT evaluated for exit sells, because a halt, kill, breaker or arm expiry is exactly when stop-loss, rug and flatten exits must still go out. "
         "Arm scope: the arm record lists (strategy id, param_set_hash) pairs, not ids; `live confirm` takes `--strategy id:hash` (repeatable); any param hash change (a new stage row for the strategy) invalidates its pair and needs a NEW arm. "
         "Maximum expiry: live.arm_max_expiry_hours (SET0, default 72, hard ceiling 168, OD-07); a record with expiry beyond it fails to load. The arm record binds the configuration hash AND the ledger-held param hashes (the Settings dump alone excludes ledger-held param sets, N6 section 5 point 2). "
         "Doctor additionally checks signer time sync and key custody (no key-like env names).")
new("C-09a", 18, RISK, "desk-signer core: IPC socket, nonce window, attestation over the socket, single-send persistence, chain reconcile, own project",
    ["services/desk-signer/pyproject.toml", "services/desk-signer/Dockerfile", "services/desk-signer/src/desk_signer/__init__.py", "services/desk-signer/src/desk_signer/server.py", "services/desk-signer/src/desk_signer/store.py",
     "services/desk-signer/src/desk_signer/reconcile.py", "services/desk-signer/src/desk_signer/attest.py", "services/desk-signer/src/desk_signer/timesync.py", "services/desk-signer/src/desk_signer/redact.py",
     "services/desk-signer/tests/test_server_ipc.py", "services/desk-signer/tests/test_nonce_window.py", "services/desk-signer/tests/test_single_send.py", "services/desk-signer/tests/test_reconcile.py",
     "services/desk-signer/tests/test_import_allowlist.py", "services/desk-signer/tests/test_attest_over_socket.py", "docker-compose.yml", "tests/safety/test_signer_isolation.py"],
    ["C-08", "C-01", "C-01b", "Q41", "Q06", "C-13", "SET0"], ["LIV-08", "LIV-09", "LIV-11", "LIV-19"],
    ["cd services/desk-signer && uv run pytest -q", "uv run pytest -q tests/safety/test_signer_isolation.py", "uv run ruff check services", "uv run mypy services/desk-signer/src", "make audit", SMOKE_CMD, LIVE_CMD],
    "Replaces the first half of C-09. CI (Q06): the signer gets its own lint, mypy and pip-audit over its own lock (N6 item 24). N6 section 4 (dependencies) and item 19 and 24: signer tests live ONLY under services/desk-signer/tests (root testpaths is `tests`, and pyproject has no solders, base58 or crypto library, so a tests/services/desk_signer directory would import them in the root suite); "
    "the root suite gets only the dependency-free AST test tests/safety/test_signer_isolation.py. The signer has its own pyproject and lock and its own CI job (Q06). Single send: SIGNED row (signature, tx bytes, lastValidBlockHeight) committed with fsync of the file AND the directory before sendTransaction; maxRetries 0; no rebroadcast; "
    "a SIGNED row older than validity is DROPPED only after a finalized-commitment check; confirmation uses a SECOND RPC endpoint (one lying RPC must not fake success). UNKNOWN is never retried and blocks everything but its own reconcile. Logs redact base58 key-length strings, tx bytes and key paths. Compose service reuses Q41 hardening (read_only, cap_drop ALL, no-new-privileges), group-shared socket volume (OD-11). "
    "Merges only after the amendment PR.", amend=True)
new("C-09b", 18, RISK, "desk-signer transaction policy: instruction-level allowlist, signer-owned blockhash, ALT refusal, final-bytes verification",
    ["services/desk-signer/src/desk_signer/txbuilder.py", "services/desk-signer/src/desk_signer/txpolicy.py", "services/desk-signer/src/desk_signer/signing.py", "services/desk-signer/src/desk_signer/fees.py", "services/desk-signer/src/desk_signer/policy.py",
     "services/desk-signer/tests/test_txpolicy_allowlist.py", "services/desk-signer/tests/test_blockhash_signer_owned.py", "services/desk-signer/tests/test_final_bytes_verify.py", "services/desk-signer/tests/test_alt_refused.py",
     "services/desk-signer/tests/test_token2022_wallet_ata.py", "services/desk-signer/tests/test_policy_order.py"],
    ["C-09a"], ["LIV-18", "LIV-08"],
    ["cd services/desk-signer && uv run pytest -q tests/test_txpolicy_allowlist.py tests/test_blockhash_signer_owned.py tests/test_final_bytes_verify.py tests/test_alt_refused.py tests/test_token2022_wallet_ata.py tests/test_policy_order.py",
     "uv run ruff check services", "uv run mypy services/desk-signer/src", LIVE_CMD],
    "N6 item 3 (BLOCKER) and section 5 points 4 and 8, replacing C 4 Transaction build. A program-level allowlist is not enough. Instruction-level rules applied to the decoded transaction, fail closed: "
    "System program: Transfer ONLY, to the pinned fee recipient, amount at most fee_rate times size; reject Assign, Allocate, AdvanceNonce, CreateAccount to other owners. "
    "Token and Token-2022: reject Transfer, TransferChecked, Approve, ApproveChecked, SetAuthority, Burn, Freeze, and CloseAccount unless account owner and destination are the wallet. Associated Token Account program: create only for the wallet owner and the intent mint. "
    "Pump program: discriminator allowlist (buy, sell variants only); bonding curve and associated curve accounts must equal PDAs derived from the intent mint; user account is the wallet. ComputeBudget: limit and price within signer.fee_cap_lamports. "
    "Versioned v0 transactions: resolve address lookup tables from chain and apply the same rules, or refuse (default refuse). The signer owns the recent blockhash: it fetches it, rewrites or rebuilds the message with it, and never trusts the builder's blockhash. "
    "Verification runs on the FINAL signed bytes after compute-limit edits, not on the simulated copy. Mint facts and authorities are re-fetched immediately before send (Token-2022 extensions, authorities, wallet ATA extensions: CpiGuard and default-frozen reject). "
    "Builder is PumpPortal trade-local behind a TxBuilder interface (OD-14); the 0.5 percent portal fee is documented (N6 row 40), only the recipient account is pinned and unverified in docs, so the recipient is a configured allowlist entry. Merges only after the amendment PR.", amend=True)
mod("C-10", add_deps=["SET0"], add_reqs=["RSK-09", "LIV-19"],
    add_files=["src/pumpgrok/risk/breakers.py", "tests/live/test_exit_sells_autonomous_live.py", "tests/live/test_tx_failed_onchain_latch.py", "tests/live/test_reconcile_drift_tokens.py"],
    note="N6 item 1 (BLOCKER, engine side): _step_live_gate runs for sells today (steps.py:239-245; live_gate is not in EXIT_SKIP_STEPS, constants.py:32-47) and approval_missing needs a minted approval for rule exits (steps.py:249). "
         "The engine now calls check_exit for sells, and mints an autonomous_live approval for exit-rule and flatten sells while ANY live position is open, even when the arm has expired or a halt is set (entries are the only thing suspended). Demotion must not strand an open live position: sells keep flowing. "
         "N6 section 5 point 9: live `tx_failed_onchain` latches a HaltSet that only a human clears (the exec_errors breaker auto-resets after 900 s, breakers.py:65, so failed sends could otherwise resume without a human). "
         "N6 section 5 point 6: reconcile compares SOL AND on-chain token balances to ledger positions with ATA rent (about 0.002 SOL) and creator-fee vault effects inside live.drift_tolerance_lamports (OD-03) to avoid false wallet_drift halts. "
         "Registry loads the live class by dotted path only inside a separate live factory module (N6 item 18); test_import_graph_no_live text is updated: supervisor and CLI may reach the registry module but never the client module.")
new("C-17", 18, RISK, "Stage, kill and halt mirror into the live ledger so the signer fold sees them (and the statement of which ledger holds what)",
    ["src/pumpgrok/execution/live/mirror.py", "tests/live/test_stage_mirror.py", "docs/design/live-ledgers.md"],
    ["C-05", "C-10", "C-01b", "C-13"], ["LIV-19"],
    ["uv run pytest -q tests/live/test_stage_mirror.py", SMOKE_CMD, LIVE_CMD],
    "N6 item 20. Statement: strategy_stage:<id>:<hash> rows, strategy_kill rows and halts are written by gate:promotion and the risk engine into the PAPER ledger (var/ledger.sqlite). The signer folds the LIVE ledger (var/live/ledger.sqlite, source=live). "
    "mirror.py appends idempotent copies (key = source row idempotency key plus ledger id) into the live ledger on each promotion edge, kill edge and halt edge and at arm time, called from the composition root (WIRE-18), never by a timer. "
    "A test proves signer and gate see the same stage, kill and halt after a demotion, a kill and a halt. docs/design/live-ledgers.md records that this is consistency, not independence.", amend=True)
mod("C-11", add_deps=["C-17"], note="Shadow gaps (paper expected-out versus simulated-out) feed min_shadow_orders and max_shadow_slippage_gap_bps thresholds in C-05 (read-only here).")
mod("C-12", add_files=["src/pumpgrok/execution/live_factory.py"],
    note="N6 item 18: build_adapter dispatches to execution/live_factory.py only when the effective mode is live and the gate is open; live_factory imports the registered class by dotted path (importlib) and nothing else imports it, so the transitive closure of supervisor, cli, backtest, upgrade and paper_adapter never contains the signer client. The paper side is PF1.")
mod("C-15", note="N6 section 5 point 9 and item 28: step 4 of the arm runbook does NOT commit an overlay with enabled=true (the closing paragraph of the amendment says no overlay enables live); the human uses an operator-local file named by PUMPGROK_CONFIG outside git. "
    "Funding rule: the throwaway limit is 200 USD while the cap is 1.0 SOL; at a SOL price above 200 USD the rule `cap plus fees` breaks clause 1, so the runbook computes cap_sol = min(1.0, 200 USD / SOL price minus fees) at arm time (OD-12). Strand risk (N6 section 5 point 7) and the live exit rules are documented.")
mod("WIRE-18", add_deps=["C-17"], note="Also wires the mirror (C-17) at promotion, kill and halt edges and the arm check at startup; still no timers in the desk.")

# amendment: one owner-applied plan replaces C-13 and C-14 (units kept for file bookkeeping)
mod("C-13", add_files=["AGENTS.md", "ARCHITECTURE.md", "docs/ROSTER.md", "skills/key-custody/SKILL.md", "tests/safety/test_amendment_copies_complete.py"],
    note="N6 item 6 and section 4: HUMAN-APPLIED. The owner (or a human-approved executor working only from the approved text on a branch the owner opens) applies and merges. Copies the draft misses and this unit adds: "
         "prompts/bot-04-sniper.xml:6,27 (sniper-owned), prompts/bot-00-chief.xml:65 and agents/chief.md:72 ('never allow SNIPER without the exact human approval phrase'), AGENTS.md:91, ARCHITECTURE.md:170, SETUP.md:120,203,241, docs/ROSTER.md:116 (and the key-custody rows at 196, 238, 280), "
         "docs/runbooks/setup.md:27, skills/key-custody/SKILL.md:24 ('There is nothing to custody'), and RISK_POLICY 3.3 'R17: no live auto-exit exists' (docs/RISK_POLICY.md:128). test_amendment_copies_complete.py greps every quoting file for the superseded phrases.")
mod("C-14", add_files=["prompts/bot-00-chief.xml", "SETUP.md", "docs/runbooks/setup.md"],
    note="Same PR as C-13 (AMEND). Chief-owned additions from N6 section 4; the sniper-owned prompt is added by the AMEND plan itself.")

# --------------------------------------------------------------------------------------------
# Phase 19 changes
# --------------------------------------------------------------------------------------------
mod("O2", rm_deps=["O2t"], add_files=["tests/desk/test_health_event_sections.py", "tests/desk/test_metrics_strategy.py"],
    acc=["uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_health_event_sections.py tests/desk/test_metrics_strategy.py", "! uv run pytest tests/desk/test_health_event_sections.py -rs | grep -q SKIPPED"],
    note="N6 item 10: O2t (risk, importorskip) is deleted; chief ships its own tests under tests/desk.")
mod("O1", add_deps=["A12"], note="Doctor reports signer attestation by calling the signer over the socket (N6 section 5 point 3), read-only.")
mod("O5", add_deps=["A10", "Q06"], note="Nightly job: schedule trigger in ci.yml; the soak golden hash is recorded in CHANGELOG by PCL-19. Full `pytest -q` including soak is about 50 minutes (N6 section 4), which is why per-plan acceptance uses the fast path.")
mod("PRC-19", note="Restores the empty waiver set after the amendment PR (the pinned waiver tuple recorded the amendment PR number and the human approver).")

# remove deleted units and map split units
for d in DELETED | {"C-09"}:
    U.pop(d, None)
for u in U.values():
    nd: list[str] = []
    for d in u["depends_on"]:
        if d in DELETED:
            continue
        nd.extend(REPLACE.get(d, [d]))
    u["depends_on"] = list(dict.fromkeys(nd))
    na: list[str] = []
    for d in u["order_after"]:
        if d in DELETED:
            continue
        na.extend(REPLACE.get(d, [d]))
    u["order_after"] = list(dict.fromkeys(na))
