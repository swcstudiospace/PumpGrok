# Checkpoint Record: 01-01 Task 1

checkpoint: `checkpoint:human-verify` (gate=blocking-human)
name: Checkpoint: approve the 12 SUS packages before uv lock
plan: 01-01-PLAN.md, task 1 (before `uv lock`)
status: approved
approved_by: user (ask: pins, approve all 13)
user_response: "Approve all 13 pins (Recommended)"
pin_list_changed: false

## Approved pin list (13 entries)

| # | Package | Version | Source repo |
|---|---------|---------|-------------|
| 1 | uv-build | 0.13.4 | pypi.org/project/uv-build (seam reported pypi.org/project/uv/; canonical repo to be confirmed by the human, see approval) |
| 2 | pydantic | 2.14.1 | github.com/pydantic/pydantic |
| 3 | pydantic-settings | 2.16.1 | github.com/pydantic/pydantic-settings |
| 4 | httpx | 0.28.1 | github.com/encode/httpx |
| 5 | websockets | 17.3 | github.com/python-websockets/websockets |
| 6 | pyyaml | 6.0.3 | pyyaml.org |
| 7 | ruff | 0.17.1 | docs.astral.sh/ruff |
| 8 | mypy | 2.4.0 | mypy-lang.org |
| 9 | pytest | 9.1.1 | github.com/pytest-dev/pytest |
| 10 | pytest-asyncio | 1.4.0 | github.com/pytest-dev/pytest-asyncio |
| 11 | pip-audit | 2.10.1 | github.com/pypa/pip-audit |
| 12 | types-PyYAML | 6.0.12.20260906 | github.com/python/typeshed |
| 13 | requests (dev-only, >=2.32,<3) | 2.34.2 verified | github.com/psf/requests |

Note: the checkpoint title says "12 SUS packages"; the approved list has 13 entries because dev-only `requests` is included. Approval covers all 13 as listed.

Resume: the approval unblocks the single `uv lock` step in plan 01-01 task 2 (tracer). No other blocking-human gate is approved by this record.
