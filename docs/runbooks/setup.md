# Setup runbook

First-run setup for the PumpGrok desk. The normative steps live in `SETUP.md`; this runbook is the short operator path plus the health checks.

## Quick start

```bash
uv sync
cp .env.example .env
uv run pumpgrok doctor
uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
./scripts/check.sh
```

`pumpgrok doctor` reports every subsystem. `run --mode paper --once --replay` prints one engine decision (`skip` or `buy`) and appends one JournalNote. `check.sh` lints the instruction pack (skill frontmatter, constitution phrases, no network).

## What setup creates

- Working directories under `/workspace/trading-desk/` (`leads/`, `briefs/`, `proposals/`, `positions/`, `watch/`, `incidents/`, `journal/`, `research/`, plus `desk.md` and `risk-limits.md`).
- Eight specialist Bots from `agents/` and the Trading Floor group chat (host-dependent).
- `desk.md` with engagement `research`, no wallet connected, and the daily loss limit.

## Rules that apply during setup

- Follow `SETUP.md` top to bottom exactly (normative). Start with the `pumpgrok-setup` skill, then `tool-connections`, then the `desk-risk-limits` interview.
- Engagement stays at `research` through setup. There is no live-capital level on this desk; `paper` is the highest level these instructions describe.
- Never request, accept, or store seed phrases or private keys. The wallet connects via human screen hand-off only.
- Ported code lives under `src/pumpgrok/` (tools, engine, config, CLI, ledger). Root `tools/*.py` and `vendor/grokbot-pumpfun/` stay byte-identical as oracles.

## References

- Normative setup: `SETUP.md`
- Desk constitution: `rules/pumpgrok-team.mdc`, skill `desk-operating-model`
- Boot order: skills `pumpgrok-setup`, `tool-connections`, `desk-risk-limits`
