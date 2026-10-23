# Milestones

## v2 PumpGrok Desk v2 (Shipped: 2026-10-23)

**Phases completed:** 5 phases, 44 plans, 100 tasks

**Key accomplishments:**
- Locked, installable `pumpgrok` package: uv_build src layout, 13 approved pins in a committed uv.lock (uv 0.13.4), and canonical make targets
- pydantic-settings loader with CLI > env > PUMPGROK_CONFIG > overlay precedence, startup refusal of forbidden/unknown/key-bearing inputs (names only), and live-disabled overlays plus placeholder .env.example
- 15-module core contract: Crockford ULID identity, audited least-privilege tool registry with unconditional LIVE_WRITE refusal, R20 RiskBudget, R33 approvals, float-rejecting canonical_json, and loud atomic writes — all green under TDD.
- Clock, seeded RNG and a sha256-gated smoke fixture ship with an offline-by-default test harness, FaultInjector degraded modes, and an AST guard that bars wall-clock, uuid and ambient randomness from src/pumpgrok
- Ownership manifest with a git ls-files self-test, G-1..G-7 gates ported with pumpgrok constants, and three GitHub workflows on ubuntu-latest, all under test
- 18 generated R32 event schemas, core-eight plus ten seat rosters at R35 sizes passing G-7, and a prompt pipeline that assembles and regenerates every agent with no placeholder left
- Image, compose one-shot and desk docs landed and the replay exits 0 in the container; the phase gate is blocked by lint and typecheck debt that predates this plan.
- 01-foundation · **Plan:** 10 · **Status:** complete
- G-4 now passes exactly when every required acknowledger except the proposer has acked (a proposer ack is ignored, never rejected), and G-7 enforces approval fields only on tools whose roster entry declares gates [g6], with rosters matching the catalog.
- R61 keep-or-revert review of the five plan-01-06 out-of-scope files: all five kept, zero reverts, gates green
- Fail-closed registry composition root with READ-only retry, R23 idempotency keys, Decimal-only money boundary in tools/core/cli, and typed RPC retry/failover — all pinned by 32 passing tests.
- Twelve RPC-backed READ tools with freshness/source, a config-driven safety score_report with BLIND semantics, and a GET-only social client pinned by the non-vacuous SC4 guard — 58 plan tests green, full suite green.
- Fail-closed write tools over a refusing adapter: exec input contracts (B7 scope), ledger-backed portfolio/risk/journal, allowlisted notify, and the desk core eight — 63 plan tests green, full suite (641) green.
- Ten BotManifests load from roster files with least-privilege enforcement, the R63 cron-seat guard holds on both halves, and the gateway projection is unit-pinned in the root suite - 40 new tests green, full suite (681) green, G-4 and G-7 gates green.
- Seat-isolated stdlib-HTTP projection over the in-process registry: per-seat compare_digest tokens (401/403/503), tools/list equals roster plus core with verbatim schemas, tools/call binds the path manifest with isError:true code envelopes, 21 gateway tests green in both runners and 683 root tests green.
- Twelve new skills authored, 23 existing retrofitted to the B10 bots rule with granted required_tools and non-LIVE_WRITE permissions, SKILL-002 manifest suite green, prompts and agents regenerated with load=always skills and tools contracts, 35-skills count consistent across plugins and READMEs.
- Every section-12 operator verb is a thin JSON wrapper over the 37-tool registry: paper buy/sell fail closed on unknown approvals (exit 1), killswitch/state call through where backends exist (exit 0), absent backends print the JSON envelope (exit 5), and the hidden `tools <id> --help` schema verb stays out of top-level help. Full suite green (704 passed).
- Hash-chained WAL ledger with atomic batch appends, pure reducer fold, restart reconcile, resumed JSONL export, atomic desk mirrors, and per-day ticket allocation
- Seeded FixtureClock runner with hash-chained replay ledger, recorded-LLM lookup by canonical request hash, hand-authored smoke-10m fixture, working verify verb, killswitch env fix, and canonical paper ledger path
- Pure integer curve fills with venue/base/priority fees, seeded latency, risk-bound CONFIRMING re-checks, graduation and blind force-closes, and an ASSUMED R65 probe record gating RPC entries to data_unavailable
- 19-step RiskEngine with latching halts, tripping breakers, one-cycle kill switch with flatten, and per-mint KILL blocks
- Corrupt reputation book quarantines to degraded, RiskEngine refuses buys with reputation_degraded plus Escalation while exits run, and the book rebuilds from ledger fills
- Ticket allocation with per-day sequencing, seven approval kinds with manual-ticket versus autonomous-paper semantics, TOOL-004 atomic consume-and-order, UNKNOWN persistence without retry, and TOOL-011 full served-verb coverage with the exit-5 path removed. Suite, lint, format, and types green.
- Roster-order asyncio scheduler with heartbeats, bounded restarts with observe-only latches, graceful shutdown, /healthz + /readyz + atomic health.json, the full AUTO-005 degraded-mode matrix, and an offline ten-seat replay cycle. Suite, lint, format, and types green.
- Daily and weekly ASCII reports from str.format templates, exit-3 live refusal with HMAC-bound confirm record and paper-only metrics, and a vendor-free tree. Suite, lint, format, and types green; ROADMAP criteria 4 and 5 verified command by command.
- Regenerated the smoke-10m fixture with deterministic 44-char base58 mints, closing the SC3 gap with all five ROADMAP criteria plus checkpoint passing literally.
- 05-hardening
- Gate precondition 1 now requires mode live AND [live] enabled, proven by nine isolated exit-3 cases; the manipulation scan spans social, notify, and browser-ops; policy and matrix cite real files and code ids.

---
