# PumpGrok

![PumpGrok banner](banner.jpg)

PumpGrok is an eight-role Solana memecoin trading desk packaged as agent instructions, 35 skills, a hard security constitution, and read-only Python helpers. It is loaded into a host agent runtime (Grok Bot, Cursor, Claude Code, or Grok Build). It is not a trading bot, exchange client, or signer: private keys never enter the system, and only a human-approved ticket may be sent.

Version 1.0.0.

## Capabilities

- Eight specialist roles: CHIEF, SCOUT, RISK, WHALE, SNIPER, RUG, EXIT, SHILL (`agents/`)
- 35 skills covering desk constitution, ticket lifecycle, risk audit, Jupiter routing, discovery, journal conventions, paper-trading discipline, safety scoring, and a vendored dry-run screening engine (`skills/grokbot-pipeline`)
- Always-on desk rule `rules/pumpgrok-team.mdc` (RISK veto, human approval by ticket ID, single-send, no private keys)
- Read-only operator CLI (`pumpgrok`) for Jupiter quotes, mint/freeze authority, priority fees, ticket IDs, paper fills, holder concentration, and pipeline JSONL evidence
- Repo linter `scripts/check.sh` (frontmatter, constitution phrases, one-writer convention; no network)
- Plugin manifests for Grok Bot (`plugin.json`), Claude Code (`.claude-plugin/`), Cursor (`.cursor-plugin/`), and Grok Build (`.grok-plugin/`)

The desk starts in **research** mode. **paper** logs simulated fills via `pumpgrok paper`. There is no live-capital level on this desk: entries beyond paper require an explicit user decision outside these instructions. The desk ships no strategies and makes no return claims.

## Requirements

- A host that can load `agents/`, `skills/`, and `rules/` (Grok Bot, Cursor, Claude Code, or Grok Build)
- Python 3.12 via `uv` (`uv sync` installs the locked deps; `scripts/check.sh` is stdlib only)
- Optional: a private Solana RPC URL passed as `--rpc` (reads default to `https://api.mainnet-beta.solana.com`)

A committed `uv.lock` pins every dependency. No API keys are required for the public endpoints the reads call.

## Setup and usage

Full Grok Bot bootstrap (clone, folders, skills, eight Bots, Trading Floor, desk record) is in [SETUP.md](SETUP.md). That flow is read-only: no keys, no real trades.

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
uv run pumpgrok ticket next
uv run pumpgrok tools market.holders_snapshot --help
uv run pumpgrok paper buy --help
uv run pumpgrok scout pipeline --candidates --help
```

Working files for a live desk belong under `/workspace/trading-desk/` (created by setup), not inside this repo. Allocate and list tickets with `pumpgrok ticket next|create|list`, never loose files.

Cursor / Claude Code / Grok Build load `skills/`, `agents/`, and `rules/` from the plugin manifests. On runtimes without persistent Bots, `rules/pumpgrok-team.mdc` says to use subagents or role-labelled passes.

## Project layout

| Path | Role |
|------|------|
| `agents/` | Eight specialist Bot definitions plus standing instructions |
| `skills/` | Twenty-three `SKILL.md` procedures |
| `rules/` | Always-applied desk constitution (`pumpgrok-team.mdc`) |
| `src/pumpgrok/` | Operator CLI and tool registry (JSON on stdout; never sign or send) |
| `scripts/` | `check.sh` repository linter |
| `vendor/grokbot-pumpfun/` | In-tree vendored screening pipeline (regular files, not a git submodule or gitlink; pin `409e74c905faa0e9de42e918efe2c604f206856e`); notes in `vendor/grokbot-pumpfun/PUMPGROK.md`; desk-facing procedure in `skills/grokbot-pipeline` |
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
