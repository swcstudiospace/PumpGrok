---
name: hermes-cron-desk
description: File-bus cron state machine and Hermes profile isolation rules for PumpGrok. Use when installing profiles, running desk_state.py, or deciding which cron may fire.
---

# Hermes Cron Desk

## Isolation
Each role is `~/.hermes/profiles/<role>/` (its own HERMES_HOME). Memory, sessions, SOUL, cron, and `.env` do not cross roles. The only shared writable surface is `$PUMPGROK_DESK`.

## File bus
```
$PUMPGROK_DESK/
  desk.md          engagement + Halt
  leads/           SCOUT
  briefs/          RISK
  proposals/       CHIEF + ticket_helper.py
  positions/       SNIPER/EXIT/RUG (paper)
  journal/         append-only
  incidents/       RUG
  watch/           RUG
```

## Commands
```bash
python "$PUMPGROK_ROOT/tools/desk_state.py" status
python "$PUMPGROK_ROOT/tools/desk_state.py" pending-leads
python "$PUMPGROK_ROOT/tools/ticket_helper.py" next
```

## Cron owners
- scout-discover, risk-audit-open-leads, chief-pickup, rug-watch-paper, chief-journal-rollup
- NEVER cron SNIPER or EXIT
- NEVER raise engagement from cron
- If Halt is true or engagement is not research|paper, print [SILENT]

## Telegram
Only the chief profile may hold TELEGRAM_BOT_TOKEN. Other profiles notify via bot-chat:chief or files.
