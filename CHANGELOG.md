# Changelog

All notable changes to PumpGrok are recorded here. The format follows Keep a Changelog.

## [Unreleased] - Phase 1: Foundation (2026-10-21)

### Added

- `uv_build` src-layout package `pumpgrok` (Python 3.12) with a committed `uv.lock`; `uv sync --frozen`
  is the install path.
- Layered settings with startup guards: profile overlays (`dev`, `paper`, `live`), an operator
  overlay via `PUMPGROK_CONFIG`, refusal of unknown `PUMPGROK_*` names, forbidden key-like names
  and key-bearing values, and mode resolution `--mode` > `PUMPGROK_MODE` > TOML.
- Hash-chained append-only ledger with a verify step, and a deterministic replay clock, seeded RNG
  and fixture loader that checks every listed digest before any ledger file exists.
- Skip-only replay cycle: `pumpgrok run --mode paper --once --replay <dir>` reads one recorded
  fixture, appends one `JournalNote`, verifies the chain and exits 0. No engine runs.
- `pumpgrok doctor`: subsystem health report. Exit 0 whenever settings are valid.
- Redacted JSON logs with correlation IDs carried in context variables.
- Tool and registry core (`core/`), including the `ToolRegistry` invariants and the live-write refusal.
- Gates G-1..G-7 under `ci/gates/` with self-tests, `ci/gates/run_all.py`, the gate workflows and
  pre-commit hook.
- Ownership manifest `ownership.yaml`, ten seat roster and tool rosters, and the generated event
  schemas under `contracts/events/`.
- Multi-stage container image: `python:3.12-slim` build and runtime stages, `uv` 0.13.4, non-root
  user, `PUMPGROK_PROFILE=paper`, the smoke replay fixture, a `pumpgrok doctor` healthcheck,
  `SIGTERM` stop signal, and the replay as its default command.
- `docker-compose.yml`: a one-shot `pumpgrok` service with no restart policy, optional `.env`
  injection, loopback port binding, json-file logging and a 512M memory limit.
- Documentation in programming-desk shape: `AGENTS.md`, `SECURITY.md`, `docs/quality-gates.md`,
  `docs/desk-operating-model.md`, `docs/cross-bot-protocol.md`, `docs/VENDOR_PIN.md`.

### Changed

- `scripts/check.sh` no longer checks vendor paths. The vendor pin is checked through
  `docs/VENDOR_PIN.md`, the emoji scan covers `.planning/**`, and a placeholder-organisation check
  allows the organisation placeholder only in the five manifest and setup files that still carry it
  until STRUCT-007.
- Planning reports use ASCII status words in place of symbol glyphs.

### Removed

- Six tracked `*.pyc` build artifacts under `tests/` and `tools/` are untracked.
- `issues/tissue.json`, a legacy file with no inbound references.
