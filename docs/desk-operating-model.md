# Desk operating model: ten-seat paper desk

PumpGrok is a ten-seat desk that trades Solana memecoins launched on pump.fun, in paper mode.
Each seat is an LLM-backed bot with a fixed role, a fixed tool roster and a fixed channel. The
desk is packaged in programming-desk shape: path ownership (`ownership.yaml`), verification
receipts, gates G-1..G-7 (`docs/quality-gates.md`), contracts, and prompt assembly.

It can never move real funds. The only enabled execution adapter is the paper adapter. Engagement
levels are `research` and `paper` only (R16). The security constitution is in
`rules/pumpgrok-team.mdc` and is repeated verbatim in every seat file under `agents/`.

## Seats

| Seat id | Display name | Channel | Writes exchange | Role |
|---|---|---|---|---|
| bot-00-chief | CHIEF, Desk Orchestrator | Trading Floor | no | Schedules cycles, routes work, halts and escalates. Never trades, never sizes. |
| bot-01-scout | SCOUT, Alpha Hunter | Trading Floor | no | Finds new launches and volume anomalies; emits LEADs. |
| bot-02-risk | RISK, Absolute Safety Gate | Trading Floor | no | Portfolio limits, drawdown, breakers and kill switch. Veto is absolute. Owns gates, contracts and `SECURITY.md`. |
| bot-03-whale | WHALE, Smart-Money Analyst | Trading Floor | no | Holder quality and capital flow, after RISK clears or conditions a LEAD. |
| bot-04-sniper | SNIPER, Single-Write Execution | Trading Floor | paper-write | Quotes, simulates and places one paper buy per approved ticket. |
| bot-05-rug | RUG, Safety Monitor | Trading Floor | no | Pre-trade safety due diligence and post-fill rug monitoring. |
| bot-06-exit | EXIT, Position Manager | DM / off-channel | paper-write | Take-profit, stop-loss, trailing and max-hold rules; paper sells. |
| bot-07-shill | SHILL, Sentiment and Velocity | DM / off-channel | no | Social sentiment detection only. Never posts. |
| bot-08-signal | SIGNAL, Momentum Scorer | DM / off-channel | no | Momentum and confidence scoring. Emits scores as evidence. |
| bot-09-journal | JOURNAL, Post-Trade Ledger | DM / off-channel | no | Ledger of record, post-trade review, daily and weekly reports. |

Only `bot-04-sniper` and `bot-06-exit` hold paper-write execution tools. Both are bound by the
single-send rule in the constitution (clause 3).

## Channels

The Trading Floor group is limited to six Bots. The six channel seats are CHIEF, SCOUT, RISK,
WHALE, SNIPER and RUG. The other four seats work one-to-one with CHIEF (DM). CHIEF relays their
human-visible output into the channel. This is the same relay pattern programming-desk uses for
its off-channel reviewer.

## Flow of a trade

A LEAD becomes a paper trade only by passing each seat in order. No seat can skip another.

1. SCOUT emits a LEAD for a new mint with its source and timestamp.
2. RUG runs the pre-trade safety report. RISK applies the checklist and returns CLEAR, CONDITIONAL or KILL.
3. WHALE analyses holders and capital flow, but only for a LEAD that RISK cleared or conditioned.
4. SIGNAL scores momentum and confidence. A score is evidence, never clearance.
5. A human approves a ticket with its exact ID, `SOL-YYYYMMDD-NNN`. Analysis is not approval.
6. SNIPER places one paper buy for that ticket. Any unknown or timed-out result is reported as
   `UNKNOWN RESULT` and reconciled from the ledger. It is never retried blindly.
7. EXIT manages the open position under its rules and places one paper sell when a rule fires.
8. JOURNAL records every event, and produces the daily and weekly reports from the ledger.

CHIEF watches the whole flow. It halts new entries when daily loss reaches the configured limit
and when RISK issues a kill. A RISK KILL ends that token path for the session, and no other seat
can override it.

## Engagement levels

| Level | Meaning |
|---|---|
| `research` | Read-only analysis. No ticket, no paper write. |
| `paper` | Paper-write allowed for approved tickets, against the ledger only. |

Live execution is a configuration mode, not an engagement level. `pumpgrok run --mode live` is
refused by the live gate (exit 3) until all nine R21 preconditions hold, and in this release one of
them, a registered live adapter, never holds.

## What Phase 1 ships

Phase 1 is the foundation. It ships the settings loader, the append-only hash-chained ledger, the
deterministic replay clock and RNG, the redacted JSON logs and correlation IDs, the tool and
registry core, `pumpgrok doctor`, the gates, and the container image.

The one executable path is the skip-only replay cycle:

```bash
uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
docker compose run --rm pumpgrok
```

It reads a recorded fixture, appends one `JournalNote` to the ledger, verifies the chain and exits 0.
No engine runs and no network is used. Seats, the scoring engine, the tool catalogue and the live
pipeline land in later phases. Until then, the seat files describe intended behaviour and are not
evidence that a behaviour exists.

## Verification

Every claim that a change works needs a receipt (`docs/quality-gates.md`, G-2). Run the commands,
record their exit codes, and list what was not verified. A seat never approves its own work.
