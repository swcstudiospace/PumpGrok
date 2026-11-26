# Phase 13: Curve truth, live market data and recorder - Research

**Researched:** 2026-11-10  
**Domain:** Read-only Solana market data, deterministic paper pricing and replay recording  
**Confidence:** MEDIUM — repository seams and official provider documentation were inspected; live provider compatibility and on-chain layout verification remain human-gated.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Curve and source truth
- Decode token-first 49- and 166-byte account layouts, validating discriminators and refusing unverified or unknown entry sources.
- Keep layout and event status ASSUMED until a human reviews the probe evidence. Never infer verification from successful decoding.

#### Feed and recovery
- Reuse the event runtime and injected Clock. Bound the watchset, pin held mints, obey provider rate limits, deduplicate signatures and record reconnect gaps.
- Prices fail closed on disconnection or stale data; graduation refuses entry, and held positions follow the specified gap and timeout behavior.

#### Recorder and paper execution
- Seal replay-compatible, digest-verified datasets with monotonic ticks and recorded gaps; recover torn tails without hiding corruption.
- Keep fee model v1 as the default; expose v2 as an explicit selection. Paper factories and entry hooks must not import live execution.
- Preserve both replay pins and document before and after hashes.

#### Safety and process
- Research and paper only; no keys, signing, real-fund movement or automatic live promotion. Live mode remains refused.
- Follow path ownership and cross-seat protocol; use seat-owned branches, independent receipts and TDD RED/GREEN commits with plan-specific subjects.
- Phase 12 PRs 61-63 are merged, but its verification owner reports stale and its TDD review remains unresolved; do not assert Phase 12 verification was refreshed.

### Claude's Discretion
- Choose implementation details using existing patterns and the Phase 13 acceptance criteria; avoid new external providers.

### Deferred Ideas (OUT OF SCOPE)
Phase 14 onboarding, broader asset support, and any real-money trading remain outside Phase 13.
</user_constraints>

<phase_requirements>
## Phase Requirements

Descriptions below are the requirements recorded in `.planning/REQUIREMENTS.md:63-77`; acceptance detail and the extra phase-scoped halves of MKT-09 and FEE-01 come from `.planning/ROADMAP.md:103-138`. [VERIFIED: .planning/REQUIREMENTS.md:63-77] [VERIFIED: .planning/ROADMAP.md:103-138]

| ID | Description | Research support |
|---|---|---|
| MKT-01 | Token-first 49/166-byte curve accounts; reject bad discriminator | Official IDL, existing decoder gap, human-review gate |
| MKT-02 | Five pump events round-trip; ignore trailing bytes; truncated payload errors | Existing typed decoder and targeted characterization |
| MKT-03 | Probe record pending human review; otherwise exact error and assumed status | Probe evidence and explicit human checkpoint |
| MKT-04 | Allowlist prices: refuse unknown/unverified; allow replay | Replace existing negative check; preserve fixture source semantics |
| MKT-05 | Capped watchset, held pins, overflow; bridge to event catalog | Watchset invariants and bus mapping |
| MKT-06 | Timeout reconnect deduplicates signatures, emits gaps, obeys limiter | SourceSupervisor, fake clock, provider documentation |
| MKT-07 | Disconnected price unavailable, completed entry refused, gap holds, timeout zero | State machine and paper adapter interface |
| MKT-08 | Mark held mints within 60 seconds on fake clock; no timer while flat | Clock-driven scheduler |
| MKT-10 | Event decoding status becomes verified only via human reviewer | Independent event status review |
| REC-01 | Sealed, loader-compatible, ticks-only dataset; nondecreasing timestamps | Existing fixture loader and manifest digest requirements |
| REC-02 | Gap file and torn last-line recovery | Separate gap sidecar, integrity and recovery rules |
| MKT-09 (phase slice) | Read-only allowlist and no-send checks | Restrict transports and prove imports/frames; composition root is later |
| FEE-01 (phase slice) | Selectable v2 while v1 remains default, with paper factory and gate hook | Fee seam and fee accounting tests; default flip belongs to Phase 15 |
</phase_requirements>

## Summary

Implement a thin read-only ingestion pipeline around the existing event runtime and paper adapter. The current curve decoder consumes a SOL-first struct and discards its discriminator; its gate rejects only one unverified source rather than allowing known safe sources. The fixture source already supplies integer reserves and a paper price-source protocol. Correct those seams without rewriting the paper engine or changing replay behavior. [VERIFIED: src/pumpgrok/tools/onchain/curve_layout.py:25-87,153-161] [VERIFIED: src/pumpgrok/replay/sources.py:44-87] [VERIFIED: src/pumpgrok/execution/paper_adapter/models.py:18-37]

**Human-gated, not verified:** the checked-in probe says `Status: ASSUMED` and records that no curve account was configured; it is not a successful live probe. An official IDL and a successful decode are useful evidence, but neither authorizes a status flip. The roadmap designates 13-05 human-gated, and Phase 12 historical verification is stale. [VERIFIED: docs/CURVE_LAYOUT_PROBE.md:1-8] [VERIFIED: .planning/ROADMAP.md:127-138] [VERIFIED: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-CONTEXT.md:28-31]

**Primary recommendation:** Plan a fixture-first, seven-plan paper-only cutover with independent human review, and keep all unobserved provider behaviors explicit rather than guessing.

## Architectural Responsibility Map

| Capability | Primary tier | Secondary tier | Rationale |
|---|---|---|---|
| Feed, limits, reconnect and gaps | Backend read-only datafeed | External provider | Owns connection health, controlled subscriptions and provenance |
| Curve decode and trust | Backend on-chain tools | Human reviewer | Parsing and source admission are separate from evidence review |
| Price, graduation and marks | Paper execution backend | Event bus | Reserves price fills; clock controls freshness and mark cadence |
| Sealed replay data | Local storage/replay | Feed | Digest-verified byte stream and explicit gaps support deterministic playback |
| Fee selection and entry hooks | Paper execution backend | Risk | Explicit model selection must not introduce live imports |

## Project Constraints (from CLAUDE.md)

- Python 3.12, uv frozen dependencies, strict typing; use existing lint, typecheck and test conventions. Money is integer lamports, ratios/prices use Decimal, and time comes from injected Clock. [VERIFIED: CLAUDE.md:15-24,71-80]
- Respect last-match seat ownership, cross-seat review, paper-only safety and no secret-bearing URLs; do not introduce live execution or private-key handling. [VERIFIED: CLAUDE.md:81-99] [VERIFIED: rules/pumpgrok-team.mdc:26-48]
- Update applicable documentation and replay pin evidence; preserve replay one-shot behavior. Phase context additionally requires TDD RED/GREEN and independent receipts. [VERIFIED: CLAUDE.md:83-107] [VERIFIED: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-CONTEXT.md:23-31]
- The workspace skill makes market data read-only, requires sources and UTC timestamps, and warns against stale or graduation-confused figures. [VERIFIED: skills/solana-market-data/SKILL.md:12-18,21-43]

## Standard Stack

Use the existing locked project stack; recommend **no new dependency or provider**. The project declares `requires-python = ">=3.12,<3.13"`, `"httpx>=0.28.1,<0.29"`, `"websockets>=17.3,<18"`, `"pydantic>=2.14.1,<3"`, `"pytest>=9.1.1,<10"`, and `"pytest-asyncio>=1.4.0,<2"`. These are declared constraints, not newly checked registry releases. [VERIFIED: pyproject.toml:1-18,35-46]

| Existing component | Purpose | Directive |
|---|---|---|
| Python standard library | Binary parsing, hashing, durable files | Reuse; no new package |
| Existing websockets and httpx | Injected network transport | Only allow read-only endpoints/methods |
| Existing events bus / SourceSupervisor | Dispatch, backoff, cursors | Reuse without changing shared contracts |
| Existing pytest / pytest-asyncio | Deterministic tests | Use fake clock and injected transports |

Package legitimacy audit is not applicable: no external install is recommended. The declared project constraints above do not establish that every transitive locked dependency is available in the execution environment. [ASSUMED]

## Architecture Patterns

### Data flow

```text
PumpPortal creation/migration ----\
                                  -> validate -> bounded mint/watch state -> bus bridge -> event runtime
Solana logs notifications ------/       |                 |                             |
                                        |                 +-> held-mint marks ----------> paper adapter
                                        +-> dedup/resync/gaps -> recorder -> seal manifest -> replay loader
                                                       |
                                              disconnect/stale -> refuse entry
```

- Official PumpPortal documentation labels creation and migration subscriptions free, requests a single websocket connection, and currently illustrates a URL with an API key query parameter. It does not establish that the illustrated connection is compatible with this project's keyless endpoint policy; do not invent unauthenticated availability, configure a wallet, or leak a key into a URL. Human review of permitted configuration and a read-only probe are required before claiming live availability. [CITED: https://pumpportal.fun/data-api/real-time/]
- Solana documents that the logs filter supports exactly one address per `mentions` filter and that notifications include slot, signature, error and logs. Filter failed transaction observations appropriately; use signature dedup without silently assuming one signature implies exactly one useful program event. [CITED: https://solana.com/docs/rpc/websocket/logssubscribe] [ASSUMED]
- PumpPortal's FAQ describes provider websocket limits separately from the phase-specific limiter. Implement the roadmap's stricter acceptance requirement of 30 per 10 seconds; do not describe it as a provider-published limit. Confirm the limiter's target operation and actual RPC provider policy before deployment. [VERIFIED: .planning/ROADMAP.md:117-119] [CITED: https://pumpportal.fun/FAQ]
- Bridge to existing event kinds, not a new external contract. Exact catalog excerpt: `token_created = "token_created"`, `migration = "migration"`, `trade = "trade"`, `curve_tick = "curve_tick"`, `mark = "mark"`; the latter two have priority 2 while the first three have priority 1. [VERIFIED: src/pumpgrok/events/models.py:24-53]
- Persist the recorder upstream of a potentially coalescing bus or otherwise prove it captures all intended ticks and gaps: the runtime documentation explicitly says unsettled priority-2 ticks may be lost on crash. [VERIFIED: docs/design/events-grok.md:108-109]

### Curve and paper seams

The current struct is `struct.Struct("<8sQQQQQB")`; current code unpacks `(_, vsol, vtok, rsol, rtok, supply, complete)` and accepts only the struct's exact length. Existing status is `LAYOUT_STATUS: Final[str] = "ASSUMED"`. These exact excerpts describe the old implementation, not the desired wire order. [VERIFIED: src/pumpgrok/tools/onchain/curve_layout.py:25-33,57-87]

The official Pump IDL exposes a `BondingCurve` type whose first reserve is `virtual_token_reserves`; consult the IDL directly for the full field order and discriminator, then separately test 49 and 166 bytes, invalid lengths, wrong discriminator and malformed flags. The official program documentation states account extension exists; do not claim every extended byte has been validated. [CITED: https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump.json] [CITED: https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/PUMP_PROGRAM_README.md]

The current `rpc_curve_price_allowed` returns `not (curve_source == "rpc" and LAYOUT_STATUS != "VERIFIED")`, so any other source currently passes. Replace this negative check with an explicit allowlist at the actual entry choke point and account for status of all sources; ensure fixture replay is allowed without making unreviewed feed data entry-safe. [VERIFIED: src/pumpgrok/tools/onchain/curve_layout.py:153-161] [VERIFIED: src/pumpgrok/execution/paper_adapter/buy.py:9-15]

The existing fee implementation uses `VENUE_FEE_BPS = 100`, `BASE_FEE_LAMPORTS = 5_000`, `COMPUTE_UNITS = 200_000` and integer flooring; preserve it as v1. V2's 100 bps venue term, builder-specific fee, first-buy ATA rent and capped priority fee are phase requirements, not claims that a particular provider will charge those amounts today. Exact additional fee/rent/cap values and their provenance require a bounded configuration/design decision; never invent them. [VERIFIED: src/pumpgrok/execution/fees.py:1-6,20-49] [VERIFIED: .planning/REQUIREMENTS.md:237-237] [ASSUMED]

### Recorder compatibility

The loader's source-of-truth constants are `MANIFEST_NAME = "manifest.json"` and `EVENTS_NAME = "events.jsonl"`; the manifest fields include `dataset`, `recorded_from_utc`, `recorded_to_utc`, `seed_hint`, `sources`, `sha256`, `notes`. Every `*.jsonl` sidecar must be listed with a matching SHA-256; loader checks timestamps are nondecreasing. It verifies and parses the same bytes. Therefore include the gap sidecar in the digest map and put only tick records in the event file, rather than treating the gap file as an unlisted extra. [VERIFIED: src/pumpgrok/replay/fixtures.py:27-30,39-48,105-129,164-185] [VERIFIED: .planning/REQUIREMENTS.md:76-77]

The recorded fixture excerpt is `"kind":"tick"`, `"S":42100000000`, `"T":764608076000000`, `"complete":false`, `"source":"rest"`; fixture replay converts the decoded snapshot source to `source="fixture"`. Preserve this distinction when admitting replay; do not blindly trust an arbitrary producer's claimed source. [VERIFIED: tests/fixtures/replay/smoke/events.jsonl:1-1] [VERIFIED: src/pumpgrok/replay/sources.py:58-76]

Torn-tail recovery must distinguish a genuinely incomplete final write from malformed complete/interior data; preserve and report corruption rather than rewriting evidence silently. A sealed dataset must not be silently repaired after digest failure. [ASSUMED]

## Don't Hand-Roll

| Problem | Use instead | Reason |
|---|---|---|
| Replay manifest verification | Existing `load_dataset` / `verify_manifest` | Checks digests, ordering, names, symlinks and stray sidecars [VERIFIED: src/pumpgrok/replay/fixtures.py:39-69,105-135,164-185] |
| Clock, timeout, retry | Existing injected Clock and SourceSupervisor | Existing deterministic time boundary [VERIFIED: src/pumpgrok/replay/clock.py:1-6,22-33] [VERIFIED: src/pumpgrok/events/sources.py:1-5,60-61] |
| Pricing and fees | Existing reserve math and paper adapter | Avoid changing replay economics [VERIFIED: CLAUDE.md:60-67] |
| Cryptography and protocol client | Standard hashing and existing transport | No custom signing and no new live path [VERIFIED: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-CONTEXT.md:23-30] |

## Runtime State Inventory

This phase changes decoding semantics; it does not authorize migration of live or historical data. No runtime service inventory was performed in this research. [ASSUMED]

| Category | Finding | Action required |
|---|---|---|
| Stored data | Existing replay fixtures and manifests are source-controlled; external databases were not inspected. [VERIFIED: src/pumpgrok/replay/fixtures.py:105-129] | Preserve both pinned fixtures; inspect actual retained recordings before any migration. |
| Live service config | Not inspected. | Human/operator must identify configured subscriptions and credentials before live-paper deployment. |
| OS-registered state | Not inspected. | Operator must inventory any scheduler/service registration before operational cutover. |
| Secrets/env vars | Project policy forbids key-bearing URLs; actual environment not inspected. [VERIFIED: CLAUDE.md:93-99] | Never print secrets; determine compliant provider access before enabling connection. |
| Build artifacts | Existing installed or deployed artifacts not inspected. | Rebuild/redeploy only with authorized owner; preserve old pins. |

## Common Pitfalls

1. **False verification:** successful decoding is not independent human review. Keep both status records assumed until reviewer identity and probe evidence are recorded. [VERIFIED: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-CONTEXT.md:15-17]
2. **Health is not freshness:** disconnected and stale snapshots must not price entries; test held-position gap and timeout transitions separately. [VERIFIED: .planning/ROADMAP.md:117-120]
3. **Pin overflow:** held mints must stay watched while total cap holds; explicitly handle the case where held mints alone exceed cap without silently dropping one. Resolution requires a safe, tested admission policy. [ASSUMED]
4. **Reconnect duplicates or invisible gaps:** restore subscriptions under the injected clock, deduplicate appropriately and write gap boundaries even when no trade follows. [VERIFIED: .planning/REQUIREMENTS.md:68-69,76-77]
5. **Trusting unlisted sidecars or resealing corruption:** digest every data file; recover only a demonstrably torn final line. [VERIFIED: src/pumpgrok/replay/fixtures.py:105-129] [ASSUMED]
6. **Changing replay economics:** keep v1 default; both hash pairs must match the roadmap, not merely one another. [VERIFIED: .planning/ROADMAP.md:115-115,124-124]
7. **False provider facts:** PumpPortal examples show a key in the URL; free stream labels do not prove keyless access or permission to bypass local secret policies. [CITED: https://pumpportal.fun/data-api/real-time/] [VERIFIED: CLAUDE.md:93-99]

## Code Examples

Existing source interface to satisfy rather than invent a competing API: `async def curve(self, mint: str) -> CurveSnapshot | None: ...` [VERIFIED: src/pumpgrok/execution/paper_adapter/models.py:34-37]. Implementations must use the injected clock and return no entry price when unavailable. [VERIFIED: .planning/ROADMAP.md:117-119]

Existing fixture verification pattern: `manifest, contents = _verify(dataset_dir)` followed by `_parse_jsonl(contents[EVENTS_NAME], EVENTS_NAME)`; this preserves verified-byte identity. [VERIFIED: src/pumpgrok/replay/fixtures.py:164-170]

## Validation Architecture

Nyquist validation and TDD are enabled; these are planner instructions, not tests run by this research assignment. [VERIFIED: .planning/config.json:20-25,48-51]

| Property | Value |
|---|---|
| Framework | `pytest>=9.1.1,<10`, `pytest-asyncio>=1.4.0,<2` [VERIFIED: pyproject.toml:35-40] |
| Configuration | `pyproject.toml`, strict markers, test paths and asynchronous mode [VERIFIED: pyproject.toml:137-147] |
| Focused commands | The exact per-domain commands are in roadmap success criteria; use them as RED then GREEN. [VERIFIED: .planning/ROADMAP.md:110-125] |
| Full gate | `make lint`, `make typecheck`, `make test`, `./scripts/check.sh`, replay smoke and both pin checks. [VERIFIED: .planning/ROADMAP.md:110-110,124-125] |

| Requirement | Verification focus | Existing evidence / Wave 0 |
|---|---|---|
| MKT-01/02/03/04/10 | layout sizes/discriminator, all events, probe review, source gate | Existing event tests; add roadmap-named layout, probe, price-gate and status tests. [VERIFIED: .planning/ROADMAP.md:111-114] |
| MKT-05/06 | bounded pinned watchset, bridge, fault reconnect/dedup/gaps, limiter | Add roadmap-named datafeed tests and transport fixtures. [VERIFIED: .planning/ROADMAP.md:116-117] |
| MKT-07/08 | stale/disconnected, graduation, gap/timeout, 60s marks/flat | Add roadmap-named price, graduation and mark tests with fake Clock. [VERIFIED: .planning/ROADMAP.md:118-119] |
| REC-01/02 | loader-compatible seal, manifest strings, gap, torn tail and corruption | Add roadmap-named recorder tests. [VERIFIED: .planning/ROADMAP.md:120-121] |
| MKT-09/FEE-01 slices | no-send imports, RPC/frame allowlist, selected fee model and hook | Add roadmap-named readonly, fee, factory and entry-hook tests. [VERIFIED: .planning/ROADMAP.md:115-115,122-123] |
| PRC-03/LIV-07 | pinned before/after pairs, no contract diff, live refusal | Existing pin tests plus roadmap commands; do not use historical Phase 12 status as evidence. [VERIFIED: .planning/ROADMAP.md:123-125] |

Per task commit run the relevant focused tests; per integration wave run affected suites; final gate runs roadmap criteria and records real outputs. TDD RED and GREEN commits require plan-specific subjects and seat-owned receipts. [VERIFIED: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-CONTEXT.md:28-31]

## Security Domain

Security enforcement is enabled at configured ASVS level 1. [VERIFIED: .planning/config.json:48-50] Categories below are applicability decisions for this phase, not a completed ASVS audit. [ASSUMED]

| Area | Applies | Control |
|---|---|---|
| Authentication/session | External read endpoints only | No wallet, key or credential in URL/log; provider compatibility unresolved |
| Access control | Yes | Read-only operation allowlists, import-graph and frame tests; live mode remains refused |
| Input validation | Yes | Strict discriminators, lengths, timestamps, schema and source allowlist |
| Cryptography | Integrity only | Standard SHA-256 via existing fixture loader; no signing |
| Availability / tampering | Yes | Bounds, rate limits, reconnection gap evidence, reject stale/corrupt data |

## Environment Availability

| Dependency | Observation | Status |
|---|---|---|
| Python | `Python 3.12.3` | Available; within declared project constraint. [VERIFIED: pyproject.toml:6-6] |
| uv | `uv 0.13.4` | CLI available; frozen environment not exercised. |
| Node | `v24.18.0` | GSD query runtime available. |
| Solana RPC / PumpPortal | No live probe performed. | Access, limits and safe authentication remain unverified; no wallet or key should be supplied. |

No tests, builds, formatters, or live probes were run during this research.

## Assumptions Log

| # | Claim requiring confirmation | Risk |
|---|---|---|
| A1 | Locked dependencies are installed and runnable in execution environment. | Test execution blocked until environment prepared. |
| A2 | Dedup key must allow distinct useful program events within one transaction. | Incorrect key loses events or duplicates ticks; resolve using actual captured fixtures. |
| A3 | Recorder placement and torn-tail discrimination can preserve all intended evidence with chosen crash protocol. | Hidden gaps or corruption if protocol underspecified. |
| A4 | Safe policy exists for held-mint count exceeding watchset capacity. | Held mint silently unwatched unless admission is designed and tested. |
| A5 | Fee v2 configuration values and first-buy rent accounting can be specified from authoritative current evidence without enabling transactions. | Mispriced paper fills; retain v1 and gate v2 values until specified. |
| A6 | Runtime state categories may contain deployed state not inspected in this research. | Operational cutover could leave stale processes or data. |
| A7 | Security applicability table reflects phase scope; not a formal ASVS control verification. | Security gate must validate against actual implemented stack. |

## Open Questions and Human Gates

1. **13-05 human review — RESOLVED (planning disposition only):** 13-05 Tasks 1–3 assign capture of actual account/event evidence identifiers or exact probe errors, an independent human's separate layout and event decisions, and application of those decisions. The reviewer, evidence and decisions remain pending; until a human records `reviewed_by`, both statuses stay assumed, and absent the decision 13-05 cannot complete. [VERIFIED: .planning/ROADMAP.md:111-114,138-138] [VERIFIED: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-07-PLAN.md:103-109]
2. **Provider compatibility — RESOLVED (planning disposition only):** 13-04 Tasks 2–3 and its live-feed verification require an operator-authorized, policy-compliant keyless endpoint, actual create and migration frames, and live ticks verified by the loader; 13-07 Task 1 enforces the closure gate. Actual provider access and compatibility remain unverified; record sanitized provenance or the exact failure, and block phase closure without the required evidence. The documentation example contains an API-key query; no paid stream, wallet, secret-bearing URL, or workaround is authorized. [CITED: https://pumpportal.fun/data-api/real-time/] [VERIFIED: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-07-PLAN.md, Task 1]
3. **Wire evidence and fees — RESOLVED (planning disposition only):** 13-02 Tasks 1–2 cover official IDL field order/discriminator and validated gap/timeout configuration; 13-05 Tasks 1–3 gather public bytes, the reference revision and human review; 13-05 Task 1b requires authoritative operator configuration or existing design provenance for v2 builder fee, rent and priority cap. Actual reviewed evidence, configuration and fee inputs remain pending; missing trust evidence denies unverified entries/marks, missing thresholds fail closed, and missing fee inputs refuse v2 selection. Sample figures are not observed live terms. [ASSUMED] [VERIFIED: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-05-PLAN.md, Task 1b]
4. **Phase 12 gate — RESOLVED (planning disposition only):** 13-01 treats the merged implementation as a dependency; 13-07 Task 1 and phase verification must disclose stale verification and unresolved TDD review. Phase 12 verification has not been refreshed and its review remains unresolved; a contrary claim requires actual independent owner evidence. [VERIFIED: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-CONTEXT.md:28-31] [VERIFIED: .planning/phases/13-curve-truth-live-market-data-and-recorder/13-07-PLAN.md, Task 1]

## Sources and Metadata

- Primary project sources: phase context and roadmap, requirements, project instructions, existing decoder, source supervisor, paper adapter, fee model, fixture loader, ownership manifest and replay fixture; line citations appear beside findings.
- Official external sources: [Pump IDL](https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump.json), [Pump program docs](https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/PUMP_PROGRAM_README.md), [PumpPortal realtime data](https://pumpportal.fun/data-api/real-time/), [PumpPortal FAQ](https://pumpportal.fun/FAQ), [Solana logsSubscribe](https://solana.com/docs/rpc/websocket/logssubscribe). Live claims remain unverified despite official documentation.
- Research-plan seam selected Jina for two questions and web search for one; those providers were not available as exposed tools, so direct official-source reads were used. The confidence seam classified `webfetch` (even with `--verified`) and `websearch` LOW; citations are documentation references, not proof of runtime behavior. No digest was cached as a verified live observation.
- Confidence: existing seams HIGH for inspected code; provider compatibility LOW; architecture and pitfalls MEDIUM pending implementation and evidence. Recheck provider documentation before operational use.
