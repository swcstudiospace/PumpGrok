# PumpGrok

![PumpGrok banner](banner.jpg)

PumpGrok is a ten-seat Solana memecoin trading desk packaged as agent instructions, 35 skills, a hard security constitution, and Python helpers that never sign or send. The helpers write only local files, mainly under `var/`. It is loaded into a host agent runtime (Grok Bot, Cursor, Claude Code, or Grok Build). It is not a trading bot, exchange client, or signer: private keys never enter the system, and only a human-approved ticket may be sent.

Version 0.1.0, the package version (see `pyproject.toml`).

## Capabilities

- Ten specialist seats: CHIEF, SCOUT, RISK, WHALE, SNIPER, RUG, EXIT, SHILL, SIGNAL, JOURNAL (`agents/`)
- 35 skills covering desk constitution, ticket lifecycle, risk audit, Jupiter routing, discovery, journal conventions, paper-trading discipline, safety scoring, and the screening-engine procedure (`skills/grokbot-pipeline`; the vendored tree is retired, see `docs/VENDOR_PIN.md`)
- Always-on desk rule `rules/pumpgrok-team.mdc` (RISK veto, human approval by ticket ID, single-send, no private keys)
- Operator CLI (`pumpgrok`) that never signs or sends. It reads Jupiter quotes, mint/freeze authority, priority fees, and holder concentration; `ticket next` and `create` append a row to the paper ledger `var/ledger.sqlite`. Paper-trade commands place no trades and refuse with code `unavailable` until the curve reader is verified, but first they create the local folders, load or create the binding key, open the ledger and seed its starting equity. `scout pipeline` is registered but not implemented
- Repo linter `scripts/check.sh` (frontmatter, constitution phrases, one-writer convention; no network)
- Plugin manifests for Grok Bot (`plugin.json`), Claude Code (`.claude-plugin/`), Cursor (`.cursor-plugin/`), and Grok Build (`.grok-plugin/`)

The desk starts in **research** mode. **paper** is the simulated-fill level: `pumpgrok run --mode paper --once --replay <dir>` drives the paper adapter on a recorded dataset. The `pumpgrok paper buy|sell` commands refuse with code `unavailable` until the curve reader is verified (Phase 4), so no paper fill runs from those commands. There is no live-capital level on this desk: entries beyond paper require an explicit user decision outside these instructions. The desk ships no strategies and makes no return claims.

## Requirements

- A host that can load `agents/`, `skills/`, and `rules/` (Grok Bot, Cursor, Claude Code, or Grok Build)
- Python 3.12 via `uv` (`uv sync` installs the locked deps; `scripts/check.sh` is stdlib only)
- Optional: a private Solana RPC URL via `PUMPGROK_RPC__ENDPOINTS` (reads default to `https://api.mainnet-beta.solana.com`)

A committed `uv.lock` pins every dependency. No API keys are required for the public endpoints the reads call.

## Setup and usage

Full Grok Bot bootstrap (clone, folders, skills, ten seats, Trading Floor, desk record) is in [SETUP.md](SETUP.md). That flow writes only local folders and files, with no keys and no real trades.

From this repository:

```bash
./scripts/check.sh
```

Exit 0 means the instruction tree looks healthy.

Optional reads (schemas print without keys or spends):

```bash
uv run pumpgrok tools market.price --help
uv run pumpgrok tools onchain.authorities --help
uv run pumpgrok tools onchain.priority_fee --help
uv run pumpgrok ticket next --help
uv run pumpgrok tools market.holders_snapshot --help
uv run pumpgrok paper buy --help
uv run pumpgrok scout pipeline --candidates --help
```

Working files for a desk live under `var/` (append-only ledger `var/ledger.sqlite`, operational dir `var/desk/`), not inside the instruction tree. Allocate and list tickets with `pumpgrok ticket next|create|list`, never loose files.

Cursor / Claude Code / Grok Build load `skills/`, `agents/`, and `rules/` from the plugin manifests. On runtimes without persistent Bots, `rules/pumpgrok-team.mdc` says to use subagents or role-labelled passes.

## Project layout

| Path | Role |
|------|------|
| `agents/` | Ten seat definitions plus standing instructions |
| `skills/` | Thirty-five `SKILL.md` procedures |
| `rules/` | Always-applied desk constitution (`pumpgrok-team.mdc`) |
| `src/pumpgrok/` | Operator CLI and tool registry (JSON on stdout; never sign or send) |
| `scripts/` | `check.sh` repository linter |
| `src/pumpgrok/engine/` | Screening engine. Formerly the vendored `vendor/grokbot-pumpfun/` tree, retired in Phase 4; pin `409e74c905faa0e9de42e918efe2c604f206856e` kept as history in `docs/VENDOR_PIN.md`; desk-facing procedure in `skills/grokbot-pipeline` |
| `plugin.json` | Root agent-plugins manifest |
| `.claude-plugin/`, `.cursor-plugin/`, `.grok-plugin/` | Host-specific plugin metadata |
| `SETUP.md` | Step-by-step Grok Bot desk bootstrap |
| `banner.jpg` | README hero art |

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — module boundaries, ticket flow, persistence
- [SETUP.md](SETUP.md) — bootstrap procedure
- [LICENSE](LICENSE) — GNU Affero General Public License v3.0

Subdirectory READMEs: [agents/README.md](agents/README.md), [skills/README.md](skills/README.md), [rules/README.md](rules/README.md), [scripts/README.md](scripts/README.md).

## Ownership and license

Copyright (c) 2026 Spectrum Web Co LLC. Associated identity: swcstudiospace.

PumpGrok is licensed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE).
