# Baseline gate results (v3 milestone audit)

Run on the branch `bot-00-chief/phase-6-integrity` at the commit that precedes this file, with no edits in between.

| Command | Exit code | Result |
|---|---|---|
| `make lint` | 0 | `ruff check` and `ruff format --check` clean |
| `make typecheck` | 0 | mypy --strict on `src/` clean (208 source files) |
| `make test` | 0 | full pytest suite passed (coverage gate met) |
| `make audit` | 0 | `pip-audit --strict`: "No known vulnerabilities found" |

Commands are the repository's own targets in `Makefile` (`lint`, `typecheck`, `test`, `audit`). None were added or changed by this milestone audit.

Scope note: `make test` covers the full suite, so it is the HEAD re-check referenced by `v3-MILESTONE-AUDIT.md` for every requirement family. The UPG family was additionally re-run on its own earlier, on the same HEAD lineage, with the same exit 0.
