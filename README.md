# PumpGrok

![PumpGrok banner](banner.jpg)

[![AGPL-3.0](https://img.shields.io/github/license/swcstudiospace/PumpGrok)](LICENSE)
![Python 3](https://img.shields.io/badge/python-3-3776AB)
![Version 1.0.0](https://img.shields.io/badge/version-1.0.0-0A66C2)

Eight-role Solana memecoin **research desk** for Grok Bot, Cursor, Claude Code, and Grok Build. **Not a trading bot.** No keys. Human-approved tickets only.

PumpGrok is an instruction pack: eight role files, 23 skills, a hard security constitution, and read-only Python helpers. The host runtime loads `agents/`, `skills/`, and `rules/`. PumpGrok files never sign, send, or hold a wallet. Version 1.0.0 (`plugin.json`). License: GNU AGPL v3.0.

## 60-second quick start

```bash
git clone --depth 1 https://github.com/swcstudiospace/PumpGrok.git
cd PumpGrok
./scripts/check.sh
```

Exit 0 means the instruction tree (frontmatter, constitution phrases, `rules/pumpgrok-team.mdc`) looks healthy. No network. No keys.

Full Grok Bot bootstrap (folders, skills, eight Bots, Trading Floor) is in [SETUP.md](SETUP.md). That flow is read-only.

## Safety guarantees

These are instruction-pack rules, not a runtime enforcer:

- Private keys are never requested, accepted, or stored. Signing stays on a human-held throwaway wallet outside this repo.
- Every spend requires a human message with the exact ticket ID, mint, size, and max slippage. Analysis is not approval.
- RISK has an absolute veto (`CLEAR` / `CONDITIONAL` / `KILL`). A KILL closes the ticket for the session.
- Only SNIPER may request a buy send. Only EXIT may request a sell send. Both are single-send; unknown or timeout is not an auto-retry.
- `tools/*.py` print JSON and never sign or send. Jupiter and Solana RPC calls are reads (quotes, account info, fees, holders).
- The desk ships no strategies and makes no return claims.

Default engagement is **research**. **paper** logs simulated fills with `tools/paper_sim.py`. **micro-live** is only after a risk-limits interview and explicit user confirmation.

## Eight-role workflow

| Role | File | Job | May request a send |
|------|------|-----|--------------------|
| CHIEF | `agents/chief.md` | Orchestrator | No |
| SCOUT | `agents/scout.md` | Discovery / LEAD | No |
| RISK | `agents/risk.md` | Safety gate | No |
| WHALE | `agents/whale.md` | Holder / flow context | No |
| SHILL | `agents/shill.md` | Social velocity | No |
| SNIPER | `agents/sniper.md` | Single buy request | Yes (buy) |
| RUG | `agents/rug.md` | Post-entry monitor | No |
| EXIT | `agents/exit.md` | Single sell request | Yes (sell) |

Ticket ID format: `SOL-YYYYMMDD-NNN`. Strict order (see [ARCHITECTURE.md](ARCHITECTURE.md)):

1. SCOUT posts a LEAD (mint, source, UTC).
2. RISK runs the fail-closed audit.
3. Optional WHALE / SHILL context.
4. CHIEF opens a ticket (`tools/ticket_helper.py`).
5. Human approves by exact ticket ID.
6. SNIPER may request one buy. RUG monitors. EXIT may request one sell. CHIEF journals.

## Supported hosts

| Host | How the pack is loaded |
|------|------------------------|
| Grok Bot | `plugin.json` plus [SETUP.md](SETUP.md) |
| Cursor | `.cursor-plugin/plugin.json` (`skills`, `agents`, `rules`) |
| Claude Code | `.claude-plugin/plugin.json` |
| Grok Build | `.grok-plugin/plugin.json` |

Hosts without persistent Bots should use subagents or role-labelled passes (`rules/pumpgrok-team.mdc`). Do not invent a Bot-creation API.

## Project status and limitations

- Instruction pack, not a server, queue, or daemon. Nothing in this tree is started as a service.
- No lockfile or version pin for `requests` (needed only by most `tools/*.py`).
- No API keys are required for the public endpoints those tools call. Optional `--rpc` overrides the default public Solana RPC.
- `vendor/grokbot-pumpfun/` is an in-tree screening engine (dry-run default; pin `409e74c905faa0e9de42e918efe2c604f206856e`). Upstream `mode: live` is an unimplemented stub. Pipeline verdicts are not RISK clearance and not human approval. The vendored engine expects Python 3.11+.
- Working desk files belong outside git, conventionally `/workspace/trading-desk/`.
- GitHub About and topics are operator metadata; this file is the product claim.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — layers, ticket flow, persistence
- [SETUP.md](SETUP.md) — Grok Bot bootstrap
- [LICENSE](LICENSE) — GNU Affero General Public License v3.0
- [scripts/check.sh](scripts/check.sh) — offline instruction-tree linter

## License

Copyright (c) 2026 Spectrum Web Co LLC.

PumpGrok is licensed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE).
