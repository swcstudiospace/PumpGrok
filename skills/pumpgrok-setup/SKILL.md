---
name: pumpgrok-setup
description: Bootstrap the entire PumpGrok Solana memecoin trading desk from zero. Clone or unpack the repository, create folders, install skills, create the 8 specialist Bots, set up the Trading Floor, and produce a clean desk record. This is the first skill a Bot must run when it receives the SETUP.md.
bots:
  - all
gates:
  - G-7
---

# PumpGrok Setup

## L1 - Summary
First-run bootstrap that turns a fresh machine into a fully operational eight-role desk. Runs once per desk; never used for day-to-day trading. Leaves the desk in `research` with no wallet connected.

## L2 - Method
1. Follow `/workspace/pumpgrok/SETUP.md` top to bottom exactly. Key stages:
   - Ingest the repository.
   - Read the constitution (`rules/pumpgrok-team.mdc` plus `desk-operating-model`).
   - Create working directories under `/workspace/trading-desk/`.
   - Install all skills.
   - Create the 8 Bots from `agents/`.
   - Create the Trading Floor group chat.
   - Note the tools layer.
   - Write `desk.md` and starter `risk-limits.md`.
   - Run smoke tests.
   - Return the receipt.
2. Output schema:
```
PUMPGROK SETUP COMPLETE
Bots: [list]
Skills: [list]
Trading Floor: created
Engagement: research
Wallet: not yet connected
Status: ready for tool connections and risk-limits interview
```

## Failure modes
- Skipped constitution read: setup is void; re-run from the constitution step.
- Bots created without full standing instructions: recreate; partial instructions are not instructions.
- Engagement above `research` during setup: refuse. Setup never raises engagement.
- Seed phrase or private key requested, accepted, or stored: abort setup and escalate.

## References
- Guide: `SETUP.md`; runbook: `docs/runbooks/setup.md`
- Constitution: `rules/pumpgrok-team.mdc`; roles: `desk-operating-model`
- Next: `tool-connections`, then the `desk-risk-limits` interview
