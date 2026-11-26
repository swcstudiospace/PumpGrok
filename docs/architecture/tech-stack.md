# Tech stack selection - PumpGrok outstanding milestones (T1482-arch)

Owner: A03. Catalog: the frozen `uv.lock` golden path already in
`pyproject.toml`; no catalog miss, no new first-party dependency,
no new infrastructure (L2). Level: L2.

| Concern | Choice | Golden path / ADR |
|---|---|---|
| Runtime | Python 3.12 (>=3.12,<3.13) | pyproject.toml requires-python |
| Validation | pydantic v2 (+ pydantic-settings, pydantic.mypy strict) | Locked range >=2.14.1,<3 |
| HTTP clients | httpx, websockets | Locked ranges |
| Retry | tenacity | Locked range |
| Metrics | prometheus-client (/metrics) | Locked range |
| XML safety | defusedxml | Locked range |
| Gateway transport | Python stdlib http.server only | services/desk-gateway README |
| Persistence | stdlib sqlite3 ledger (var/) | src/pumpgrok/ledger/store.py |
| Lint/format | ruff 0.17.x | dev group, `make lint` |
| Types | mypy --strict | dev group, `make typecheck` |
| Tests | pytest + pytest-asyncio | dev group, `make test` |
| Audit | pip-audit --strict | dev group, `make audit` |

Supply-chain rows (evidence obtained from pyproject.toml and
Makefile): SBOM required via `uv export --frozen` in `make audit`;
dependency allowlist is the pinned pyproject ranges plus frozen
uv.lock; licence is AGPL-3.0-only with vendored grokbot-pumpfun
pinned at commit 409e74c9 and never imported as Python code; risk
feed is pip-audit --strict reporting 0 known vulnerabilities
(AC-014). Licence or allowlist conflict would route to A10; none
found in this design.

Environment proposals for A11: none. CI already runs on the Omega
self-hosted pool with uv 0.13.4 pinned; A03 changes no environment.
