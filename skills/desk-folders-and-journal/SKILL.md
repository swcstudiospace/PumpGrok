---
name: desk-folders-and-journal
description: Standard directory layout and append-only journal conventions for PumpGrok. Ensures every Bot writes to the same predictable locations.
bots:
  - bot-00-chief
  - bot-09-journal
gates:
  - G-2
required_tools:
  - journal.append
required_data: []
permissions:
  max_side_effect: paper-write
  network: true
  filesystem: var
---

# Desk Folders and Journal

## L1 - Summary
One predictable layout for tickets, evidence, and the append-only journal. Every seat writes to the same locations so CHIEF and JOURNAL can reconstruct any ticket path from the ledger and the file views.

## L2 - Method
1. Use the standard layout: the append-only ledger plus derived views.
```
var/
  ledger.sqlite        append-only event chain (single truth)
  replay/<dataset>/   replay ledgers, source=replay, never live metrics
  exports/             JSONL snapshots and report views
  KILLSWITCH           halt file when present
```
Ticket folders (`proposals/`, `briefs/`, `leads/`, `journal/` views) are
derived from the ledger, never read back as state.
2. Journal rules: append only, never delete or overwrite. Every entry carries the ticket ID and a UTC timestamp.
3. `desk.md` always records the engagement level, the wallet address once connected, and the daily loss limit.
4. Ledger-backed views (`pumpgrok ticket list`, `pumpgrok journal rollup`) are derived from the event ledger; the folders are views, never read back as state.

## Failure modes
- Missing ticket ID or timestamp on an entry: the entry is inadmissible; re-log with both.
- Conflicting folder state vs ledger: the ledger wins; re-derive the view.
- Attempted overwrite or delete of journal history: refuse; append a correction instead.

## References
- Ledger: `src/pumpgrok/ledger/` (events, tickets, snapshots)
- CLI: `pumpgrok ticket list`, `pumpgrok journal rollup`, `pumpgrok state status`
- Companion skill: `desk-post-trade-review` (review schema)
