# Hermes runtime for PumpGrok

Isolated profiles plus a file-bus cron state machine. Fits a headless VPS
that already runs Hermes Agent. Hermes Desktop is a laptop client pointed
at that VPS over SSH. It does not run on the server.

This path reuses the existing box. It does not require a Desktop-class VPS.

## What this adds

| Path | Purpose |
|------|---------|
| `hermes/profiles.yaml` | Role to skills, cron ownership, isolation flags |
| `hermes/cron/jobs.yaml` | Scheduler spec |
| `hermes/cron/prompts/` | Self-contained cron prompts |
| `scripts/hermes-bootstrap.sh` | Create 8 isolated HERMES_HOME trees |
| `scripts/hermes-install-cron.sh` | Register scout/risk/chief/rug jobs including scout-pipeline |
| `scripts/hermes-verify-isolation.sh` | Isolation and file-bus checks |
| `tools/desk_state.py` | Disk status for the state machine |
| `tools/pipeline_evidence.py` | Vendor JSONL to PIPELINE-EVIDENCE for scout-pipeline |
| `skills/hermes-cron-desk/` | Skill the cron jobs load |

## Isolation model

A Hermes Bot is a profile. Each role is a separate `HERMES_HOME`, not a
cosmetic persona.

```
~/.hermes/                     existing personal assistant (leave it)
~/.hermes/profiles/chief/      inbound Telegram + pickup cron
~/.hermes/profiles/scout/      discovery + pipeline ingest cron + own MEMORY
~/.hermes/profiles/risk/       veto memory that survives restarts
~/.hermes/profiles/whale/      on-demand only
~/.hermes/profiles/sniper/     on-demand only, never cron
~/.hermes/profiles/rug/        paper-position watch cron
~/.hermes/profiles/exit/       on-demand only, never cron
~/.hermes/profiles/shill/      on-demand only
~/trading-desk/                ONLY shared writable state
```

Bootstrap uses `hermes profile create <role> --no-skills` and writes
`.no-bundled-skills`. It never uses `--clone` or `--clone-all`. Those
flags would copy the default agent's memory and Telegram token into
every desk role.

`terminal.home_mode: profile` keeps tool subprocesses out of the OS
user home cookie and ssh pool.

Shared across profiles: this repository (`PUMPGROK_ROOT`) and the file
bus (`PUMPGROK_DESK`). Isolated per profile: SOUL.md, MEMORY.md,
sessions, skills copy, cron store, `.env`, `state.db`.

## File bus

```
$PUMPGROK_DESK/
  desk.md          engagement + Halt
  risk-limits.md   interview notes
  leads/           SCOUT
  briefs/          RISK
  proposals/       CHIEF + ticket_helper.py
  positions/       SNIPER / EXIT / RUG (paper)
  journal/         append-only
  incidents/       RUG
  watch/           RUG
```

Ticket IDs (`SOL-YYYYMMDD-NNN`) are unique across every folder. A brief
and a proposal reuse the lead ID. They do not allocate a second ID.

## State machine

```
scout cron          -> leads/SOL-*.md
scout-pipeline cron -> leads/SOL-*.md from vendor JSONL via pipeline_evidence.py
risk cron   -> briefs/SOL-*.md   CLEAR | CONDITIONAL | KILL | BLIND
chief cron  -> proposals/<same-id>.md + Telegram PENDING_HUMAN
human       -> approve TICKET mint size slippage
sniper      -> paper_sim only, never from cron
rug cron    -> incidents/ if a paper position exists
```

If `desk.md` Halt is true, or engagement is not `research` or `paper`,
cron jobs print `[SILENT]` and stop. Cron never raises engagement and
never sends a live transaction.

## Vendor pipeline ingest

The grokbot-pumpfun vendor engine is a separate operator process. Hermes
cron never starts it, and never starts it in live mode.

The `scout-pipeline` job (every 60m, owner scout, deliver `bot-chat:chief`)
only reads `vendor/grokbot-pumpfun/logs/trades.jsonl` through
`tools/pipeline_evidence.py` and writes leads under `$PUMPGROK_DESK/leads/`.
A missing log is normal before the first vendor dry-run. `tx_hash: dry_run`
is not a fill. SNIPER and EXIT remain the only exchange writers after exact
human approval.

## Install on the existing VPS

```bash
cd /path/to/PumpGrok
chmod +x scripts/hermes-bootstrap.sh scripts/hermes-install-cron.sh \
         scripts/hermes-verify-isolation.sh tools/desk_state.py tools/ticket_helper.py

./scripts/hermes-bootstrap.sh --desk "$HOME/trading-desk" --copy-provider-env
# edit ~/.hermes/profiles/chief/.env with a NEW Telegram token
./scripts/hermes-install-cron.sh --desk "$HOME/trading-desk"
./scripts/hermes-verify-isolation.sh --desk "$HOME/trading-desk"
```

`--copy-provider-env` copies allowlisted model API keys from
`~/.hermes/.env` into each profile. It never copies Telegram tokens or
wallet material.

### Make cron fire on the box you already have

Cron only runs while a Hermes gateway process is ticking. Keep the
existing default gateway. Enable multiplex so that gateway also ticks
the desk profiles without starting sniper or exit adapters:

```yaml
# in ~/.hermes/config.yaml (default profile)
gateway:
  multiplex_profiles: true
  multiplex_profile_allowlist:
    - chief
    - scout
    - risk
    - rug
```

Then restart the existing gateway service. Do not start sniper or exit
gateways. Do not reuse the personal-assistant Telegram token on chief.

```bash
hermes -p chief gateway install   # only if the chief token is new
hermes gateway restart            # or however this box already runs it
```

Smoke:

```bash
PUMPGROK_DESK="$HOME/trading-desk" python3 tools/desk_state.py status
hermes -p scout cron list
hermes -p scout cron run scout-pipeline
```

## Security

- No private keys in any profile `.env`
- No SNIPER or EXIT cron
- Do not reuse the existing completion-bot token on `chief`
- Engagement stays `research` until you edit `desk.md` by hand
- Human approval is still required before any paper or live send
- Files beat memory. Profile MEMORY.md is a seed, not the desk ledger
- Never start the vendor engine from Hermes, live or otherwise
- Pipeline JSONL is evidence only; dry_run is not a fill

## Operator commands

```bash
python3 tools/desk_state.py status
python3 tools/desk_state.py pending-leads
python3 tools/desk_state.py pending-tickets
python3 tools/desk_state.py open-positions
python3 tools/desk_state.py halt --reason "daily loss limit"
python3 tools/ticket_helper.py next
python3 tools/ticket_helper.py create --mint <MINT> --ticket <LEAD-ID> --status PENDING_HUMAN
python3 tools/pipeline_evidence.py --candidates --block --limit 5
```
