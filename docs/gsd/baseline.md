# Baseline (Wave 1, HEAD 323abf0, branch bot-00-chief/phase-6-integrity)

| Check | Command | Exit | Result |
|---|---|---|---|
| lint | `make lint` (ruff check . ; ruff format --check .) | 0 | All checks passed; 815 files already formatted |
| typecheck | `make typecheck` (mypy --strict src/) | 0 | Success: no issues found in 208 source files |
| test | `make test` (pytest -q) | 0 | All dots, no failures; `-q` prints no summary count, so the count is not recorded |
| audit | `make audit` (pip-audit --strict) | 0 | No known vulnerabilities found |

Not run: build (Dockerfile and compose; no make target, manual per STATE.md). Coverage: not configured.

Dominant patterns (n3 pattern survey) are deferred to Wave 2: no quality uplift is planned beyond touched code (q4), so a repository-wide pattern census adds no value to a phase yet.
