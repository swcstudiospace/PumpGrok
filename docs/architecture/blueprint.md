# Architecture blueprint - PumpGrok outstanding milestones (T1482-arch)

Version 1.0. Status: accepted design. Owner: A03. Contract:
`docs/architecture/contracts/pumpgrok-gateway.yaml` v1.0.0 (ADR-0003).
Requirements: `docs/requirements/spec.md` (26 stories US-001..US-026,
30 criteria AC-001..AC-030, 5 NFRs). Paper-only throughout (ADR-0001).

## 1. C4 context

External actors and systems: Human operator, Host agent runtime
(Grok Bot / Cursor / Claude Code), Solana JSON-RPC, Jupiter quote API,
Browser sites. PumpGrok is an instruction pack plus small read-only
CLIs; the only service form is the paper gateway and the paper replay
runner, both started on operator request.

## 2. C4 containers

| Container | Responsibility | Trust zone |
|---|---|---|
| cli | `pumpgrok` verbs; exit 0/1/2/3/4/5/6 contract | Desk (trusted) |
| desk-gateway | Stdlib HTTP JSON-RPC projection of the tool registry; per-seat bearer tokens | Desk (trusted) |
| tool-registry | 37 registered tools; unknown-field rejection; fail-closed refusals | Desk (trusted) |
| ledger | Append-only SQLite ledger, events, receipts | Desk (trusted) |
| replay-engine | Clock-injected deterministic replay; event-hash output | Desk (trusted) |
| risk-engine | Kill switch, breakers, halt state | Desk (trusted) |
| ci-gates | G-1..G-7 plus `make check` canonical suite | CI (trusted) |
| tracker | Linear issues and sub-issues per milestone (US-023) | External (untrusted) |

Relations: cli -> tool-registry; cli -> ledger; cli -> replay-engine;
desk-gateway -> tool-registry; desk-gateway -> ledger;
tool-registry -> risk-engine; tool-registry -> ledger;
replay-engine -> ledger; ci-gates -> tracker; cli -> desk-gateway.

Layer order (outermost to innermost): cli, gateway, tools, domain,
persistence. Modules: `cli` (cli), `desk_gateway` (gateway),
`tools` (tools), `risk` (domain), `ledger` (persistence),
`replay` (domain). Edges: cli -> tools; cli -> gateway; gateway ->
tools; tools -> risk; tools -> ledger; replay -> ledger; risk ->
ledger. No module depends on a layer above it; the graph is acyclic.

Fan-out budget: 4 distinct containers per container. Largest observed
fan-out is 4 (cli). No container is isolated.

## 3. NFR allocation (100 percent)

| NFR | Binding | Limit |
|---|---|---|
| NFR-P1 performance | component budget replay-smoke | 60 s per ten-seat cycle; suite 900 s |
| NFR-S1 security | component budget secret-scan | 0 secret shapes |
| NFR-A1 accessibility | contract clause x-nfr/NFR-A1 | 0 non-ASCII bytes; 1 single-line ASCII error record |
| NFR-I1 internationalisation | contract clause x-nfr/NFR-I1 | 0 locale-dependent formats; ISO 8601 UTC |
| NFR-C1 compliance | contract clause x-nfr/NFR-C1 | 0 live adapters; live exit 3; 0 keys |

`arch_nfr_allocation` returned coverage_pct 100, fully_allocated true.

## 4. Contracts

- Gateway OpenAPI 3.1 v1.0.0, 2 operations (GET /healthz,
  POST /mcp/{short}), every operation carries operationId and
  responses. Non-breaking initial publication; additive changes bump
  minor, breaking changes are L3 (ADR-0003).
- Ledger events: `contracts/events/*.schema.json` (generated, never
  hand-written; drift check in `make check`). 18 event types.
- Tool rosters: `contracts/tool-rosters/*.yaml`; effective roster
  8 core + seat tools, 11..15 tools, `additionalProperties: false`
  on every input (AC-010: 37 of 37 tools reject unknown fields).

## 5. Tech stack (approved catalog: the frozen lockfile)

Python 3.12, pydantic v2, httpx, websockets, tenacity,
prometheus-client, defusedxml, PyYAML; dev: ruff, mypy --strict,
pytest, pip-audit. Gateway: Python stdlib `http.server` only (no web
framework). Persistence: stdlib sqlite3 ledger. No new first-party
dependency and no new infrastructure in this design (L2).

## 6. Fitness functions (CI)

1. `make lint` - ruff check + format, 0 violations (AC-007).
2. `make typecheck` - mypy --strict on src/, 0 errors, 0 suppressions (AC-006).
3. `make test` - pytest root suite exit 0, 0 failures (AC-013);
   gateway suite exit 0 across 15 files (AC-020).
4. `make audit` - pip-audit --strict, 0 vulnerabilities (AC-014).
5. `make check` - canonical suite plus prompt/template/schema drift
   and `./scripts/check.sh` (AC-017, AC-027, AC-026).
6. Replay smoke exit 0 with identical hash on rerun (AC-018, AC-028);
   smoke-10m hash sha256 b69c2959... (AC-012).
7. Live refusal exit 3 with 9 unmet lines (AC-019).
8. G-1..G-7 via `ci/gates/run_all.py`; per-PR CI 100 percent green
   before merge (AC-021, AC-029); merge guard refuses red PRs (AC-024).
9. AST scans: money-ast-scan 0 float money (AC-008),
   clock-ast-scan 0 wall-clock reads outside replay/clock.py (AC-009),
   adapter-scan 0 live adapters (AC-022), secret-scan 0 shapes (AC-030).
10. Contract check (`arch_contract_check.py`) before any contract
    publication; layer, cycle and fan-out checks per section 2.

## 7. Supply chain

SBOM required: `uv export --frozen` lockfile export in `make audit`.
Dependency allowlist: pyproject.toml pinned ranges only; uv.lock
frozen. Licence matrix: AGPL-3.0-only project; vendored
grokbot-pumpfun pinned at commit 409e74c9 and never imported as code.
Risk feed: pip-audit --strict must report 0 known vulnerabilities.

## 8. Threat model summary (STRIDE, for A10 co-sign)

Trust zones: Desk (trusted), CI (trusted), External RPC/quote APIs and
tracker (untrusted), Human operator (trusted, approves spends).
Boundary crossings: tool-registry -> Solana RPC (read-only),
tool-registry -> Jupiter quote (informational only, never /execute),
desk-gateway -> network (per-seat bearer tokens), ci-gates -> tracker.
Mitigations: fail-closed on every uncertain state (AC-011), unknown-
field rejection (AC-010), hmac.compare_digest token comparison,
1 MiB body cap, 0 key material in repo, live gate exit 3. Residual
risk acceptance is A10's decision; high-risk crossings need A10
co-sign before implementation tasks open.

## 9. Review standards (for A09)

Dependency direction follows section 2 layer order; coupling budget
is fan-out 4 per container; money fields are int base units only;
timestamps take an injected Clock; every tool input forbids extra
fields; every uncertain state returns a named refusal; no live-write
tool name may start with `exec.live`.

## 10. Open questions

- Owner confirms sweep-order assumption A-1 (B00 typing, B01 lint,
  B02 money, B03 time, B04 contracts, B05 fail-closed, B06
  determinism, B07 tests, B08 dependency audit, B09 docs).
- A10 co-signs the STRIDE crossings in section 8.
- A11 owns any CI-runner or environment change; A03 proposes only.
