---
name: hermes-cron-desk
description: File-bus cron state machine and Hermes profile isolation rules for PumpGrok. Use when installing profiles, running desk_state.py, or deciding which cron may fire.
bots:
  - bot-00-chief
  - bot-01-scout
  - bot-02-risk
  - bot-05-rug
  - bot-09-journal
gates: []
required_tools:
  - desk.brief
required_data: []
permissions:
  max_side_effect: read
  network: true
  filesystem: none
---

# Hermes Cron Desk

## L1 - Summary
Isolation rules and the file-bus state machine for Hermes cron profiles. Each role runs in its own profile with no shared memory; the only shared writable surface is the desk directory.

## L2 - Method
1. Isolation: each role is `~/.hermes/profiles/<role>/` (its own HERMES_HOME). Memory, sessions, SOUL, cron, and `.env` do not cross roles. Bootstrap uses `hermes profile create <role> --no-skills` and writes `.no-bundled-skills`. Never `--clone` or `--clone-all`.
2. File bus:
```
$PUMPGROK_DESK/
  desk.md          engagement plus Halt
  leads/           SCOUT
  briefs/          RISK
  proposals/       CHIEF tickets
  positions/       SNIPER/EXIT/RUG (paper)
  journal/         append-only
  incidents/       RUG
  watch/           RUG
```
Ticket IDs are unique across every folder. Briefs and proposals reuse the lead ID.
3. Commands (pre-flight first, then the ticket verbs):
```bash
pumpgrok state status --seat <role>
pumpgrok ticket next
pumpgrok ticket create --mint <MINT> --ticket <LEAD-ID> --status PENDING_HUMAN
```
4. Cron owners: scout-discover, risk-audit-open-leads, chief-pickup, rug-watch-paper, chief-journal-rollup. NEVER cron SNIPER or EXIT. NEVER raise engagement from cron. If Halt is true or engagement is not `research` or `paper`, print `[SILENT]`.
5. Telegram: only the chief profile may hold TELEGRAM_BOT_TOKEN. Other profiles notify via bot-chat:chief or files.

## Failure modes
- Halt true or engagement outside `research`/`paper`: the job prints `[SILENT]` and does nothing.
- Cross-profile leakage (shared env or memory): refuse the run; isolation is load-bearing.
- Cron attempting SNIPER/EXIT or an engagement change: refused by the job and by the CLI.

## References
- State tool: `pumpgrok state status --seat <role>` (ledger halt state); `pumpgrok ticket list` (pending tickets)
- CLI pre-flight: `pumpgrok state status`
- Jobs: `hermes/cron/jobs.yaml`; prompts: `hermes/cron/prompts/`
