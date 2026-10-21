# Cross-bot protocol

A feature that crosses seats has to be coordinated. Two seats that edit the same file, or that
change a shared interface without telling each other, produce silent breakage on a trading desk.
This protocol keeps seat boundaries enforceable by the gates, not by good intentions.

## Seats and levels

The ten seats are `bot-00-chief` (CHIEF), `bot-01-scout` (SCOUT), `bot-02-risk` (RISK),
`bot-03-whale` (WHALE), `bot-04-sniper` (SNIPER), `bot-05-rug` (RUG), `bot-06-exit` (EXIT),
`bot-07-shill` (SHILL), `bot-08-signal` (SIGNAL) and `bot-09-journal` (JOURNAL). Engagement levels
are `research | paper` only (R16). Every seat's change passes gates G-1 through G-7
(`docs/quality-gates.md`).

## Rules that always apply

1. **One owner per path.** Every tracked path resolves to exactly one seat in `ownership.yaml`.
   The last matching pattern wins. An unowned path fails G-1. Before editing, resolve the path
   against that file.
2. **The contract is the only shared surface.** Seats talk through `contracts/` (events, tool
   rosters, change documents), through the ledger, and through CHIEF. They never reach into
   another seat's files.
3. **A change to a contract goes through a change document.** Any edit under a
   `contract_surface` needs `contracts/changes/<change-id>.yaml` (G-4). The required fields are
   `change_id`, `proposed_by`, `surface`, `breaking`, `version` and `summary`.
4. **A breaking change needs every other consumer's acknowledgement.** A breaking change also needs a
   major version bump and a `migration_note`. Every consumer listed for the surface in
   `ownership.yaml` (`contract_consumers`), except the proposing seat (`proposed_by`), must
   acknowledge it in the document. An acknowledgement written by the proposer is ignored —
   never counted, never rejected. A seat cannot acknowledge for another seat. The gate proves
   an acknowledgement is present, not who wrote it; authorship is evidenced by git history
   and reviewed by QUALITY.
5. **Only the two paper-write seats hold write tools.** SNIPER places buys and EXIT places sells,
   each once per approved ticket. No other seat is granted a write tool.
6. **Off-channel seats speak through CHIEF.** SHILL, SIGNAL, JOURNAL and EXIT work one-to-one
   with CHIEF. CHIEF relays their human-visible output into the Trading Floor.

## The steps

The protocol is for changes that cross seat boundaries. It is not needed for work inside one seat.

### Step 1: nominate the integrating seat

One seat owns the end-to-end result. Usually that is the seat whose tool or event is consumed by
the most others. CHIEF records the nomination. The integrating seat does not have to write every
line, but it owns the acceptance check.

### Step 2: the contract change first

The integrating seat opens the contract change: the schema, the tool roster entry or the event
model, plus `contracts/changes/<change-id>.yaml`. Event schemas are generated from
`src/pumpgrok/ledger/events.py` with `python3 scripts/generate-event-schemas.py`. They are never
hand-edited. The contract change merges before any implementation that depends on it.

Run the gate locally:

```bash
python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/<change-id>.yaml
```

### Step 3: implement in parallel

Each seat implements the parts it owns against the merged contract. Each seat's branch is named
`bot-0N-<seat>/<unit>`, and each seat submits its own receipt (G-2). A seat that needs a change in
another seat's path does not make it. It asks CHIEF to route the request to the owner.

### Step 4: integrate

The integrating seat merges the parts and runs the full gate set on the combined tree. The
integration evidence is a receipt that names every seat's commands and exit codes. A claim that
the feature works end to end needs that receipt.

## Amending a contract mid-flight

A contract that has already merged is changed only by a new change document. Do not edit a merged
schema in place. If a consumer discovers a problem after the change merged, it reports the problem
to the owner of the surface, who opens a new change document. The original document stays as
the record of what was agreed.

## Anti-patterns

- A seat editing another seat's file to unblock itself. Route it through CHIEF.
- A seat writing its own acknowledgement into a change document for another seat.
- Hand-editing a generated event schema, which the drift check then rejects.
- Shipping a breaking change with the consumer acknowledgements missing, or with the version unchanged.
- Treating a SIGNAL score or a SHILL sentiment as clearance. Only RISK clears or kills a path.

## When the protocol is overkill

A change that stays inside one seat's paths, touches no contract surface and adds no event does not
need a change document, a nomination or a relay. The owning seat makes the change, runs the gates and
records a receipt.
