---
phase: "1"
slug: "foundation"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-21"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: 01-RESEARCH.md `## Validation Architecture`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 (auto mode); stdlib unittest for `tests/test_tools_cli.py` (until Phase 2) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (created in Wave 0) |
| **Quick run command** | `uv run pytest -q tests/<file>::<test>` |
| **Full suite command** | `uv sync --frozen && make lint typecheck test audit` |
| **Estimated runtime** | ~120 seconds |

---

## Sampling Rate

- **After every task commit:** run the task's `<automated>` command.
- **After every plan wave:** run the full suite command.
- **Before `/gsd:verify-work`:** all five ROADMAP Phase 1 success criteria green.
- **Max feedback latency:** 120 seconds (Docker steps may exceed this; run them once per wave, not per task).

---

## Per-Requirement Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists |
|--------|----------|-----------|-------------------|-------------|
| FOUND-001 | `uv sync --frozen` on clean checkout | smoke | `uv sync --frozen --group dev` | ❌ W0 (pyproject, uv.lock) |
| FOUND-002 | canonical make targets | integration | `make lint typecheck test audit` | ❌ W0 (Makefile) |
| FOUND-003 | compose config, image build, replay one-shot | smoke | `docker compose config --quiet && docker compose build pumpgrok && docker compose run --rm pumpgrok` | ❌ W0 |
| FOUND-004 | loader precedence, refusals | unit | `uv run pytest -q tests/config/` | ❌ W0 |
| FOUND-005 | registry I1-I4; LIVE_WRITE refused | unit | `uv run pytest -q tests/core/` | ❌ W0 |
| FOUND-006 | ownership manifest validates | gate | `python3 ci/gates/check_ownership.py --validate-manifest` | ❌ W0 |
| FOUND-007 | gate self-tests | gate | `python3 -m pytest ci/tests/ -q` | ❌ W0 (port) |
| FOUND-008 | contracts and schemas, G-7 | gate | `python3 ci/gates/check_desk_integrity.py --repo .` | ❌ W0 |
| FOUND-009 | prompts assemble, agents regenerate | gate | `bash scripts/assemble-prompts.sh --check && python3 scripts/generate-templates.py --check` | ❌ W0 |
| FOUND-010 | workflows exist and parse | static | `python3 -c "import yaml,glob; [yaml.safe_load(open(p)) for p in glob.glob('.github/workflows/*.yml')]"` | ❌ W0 |
| FOUND-011 | docs present, check.sh passes | gate | `./scripts/check.sh` | partial (rewrite) |
| FOUND-012 | network blocked; replay clock/rng/fixtures; FaultInjector | unit | `uv run pytest -q tests/test_network_block.py tests/replay/` | ❌ W0 |
| FOUND-013 | skip cycle, JournalNote count 1, doctor | e2e | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke && uv run python -c "import sqlite3; print(sqlite3.connect('var/replay/smoke/ledger.sqlite').execute(\"select count(*) from events where type='JournalNote' and source='replay'\").fetchone()[0])"` | ❌ W0 |
| STRUCT-001 | pyc/tissue removed; pin doc | static | `git ls-files \| grep -E '\.pyc$\|tissue'; test -f docs/VENDOR_PIN.md` | ❌ W0 |
| STRUCT-008 | no wallet/Jito field | static | `! grep -rn -e JitoConfig -e wallet_private_key src/pumpgrok` | ❌ W0 |
| OBS-001 | JSON logs, redaction | unit | `uv run pytest -q tests/test_logging.py::test_log_redaction` | ❌ W0 |
| OBS-002 | correlation chain | unit | `uv run pytest -q tests/test_correlation.py` | ❌ W0 |
| SEC-001 | secrets gate on diff | gate | `python3 ci/gates/check_secrets.py --base origin/main` | ❌ W0 |
| SEC-002 | forbidden config keys refused, values not printed | unit | `uv run pytest -q tests/config/test_forbidden_keys.py` | ❌ W0 |

---

## Wave 0 Requirements

- [ ] `pyproject.toml`, `uv.lock`, `.python-version`, `Makefile` — toolchain (FOUND-001, FOUND-002)
- [ ] `tests/conftest.py` — network block for httpx and websockets (FOUND-012)
- [ ] `tests/config/`, `tests/core/`, `tests/replay/`, `tests/test_logging.py`, `tests/test_correlation.py` — stubs for requirement tests
- [ ] `ci/gates/*.py` and `ci/tests/` — ported gate precedent (FOUND-006..008, SEC-001)
- [ ] `tests/fixtures/replay/smoke` — hand-authored fixture (FOUND-012, FOUND-013)

*If none needed for a row: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Packages flagged SUS by legitimacy audit (uv-build, pydantic, pydantic-settings, httpx, websockets, pyyaml, pytest, and others) | FOUND-001 | Automated legitimacy signal is inconclusive (too-new / no download counts) | Human checkpoint before `uv lock`; confirm each source repo |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s (Docker steps excepted)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
