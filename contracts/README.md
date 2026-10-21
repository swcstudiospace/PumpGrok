# contracts/

The only shared surface between seats. Owned by RISK (`bot-02-risk`, `ownership.yaml`). Every
other path resolves to exactly one owner (G-1), so a seat changes the interface it consumes only
through a change document (G-4).

```
contracts/
├── events/         One JSON Schema per ledger event type (R32). GENERATED. Do not edit.
├── tool-rosters/   The MCP tool surface each seat sees on the Desk Gateway.
└── changes/        One change document per proposed contract change. The G-4 input.
```

Consumers of each surface are listed in `ownership.yaml` under `contract_consumers`. That list is
machine-read by the gates; this file does not repeat it.

## Events — `events/`

`events/<snake>.schema.json` is the JSON Schema of one pydantic model in
`src/pumpgrok/ledger/events.py`. There are 18 files, one per `EventType`, and no other event
vocabulary exists: `journal.append` and `desk.event_emit` take `kind` as the snake_case form of
the type.

The files are generated, never hand-written. After changing a model:

```bash
uv run python scripts/generate-event-schemas.py          # regenerate
uv run python scripts/generate-event-schemas.py --check  # exit 1 on drift or a stale file
```

Money is integer base units (`*_lamports`, `*_units`). Prices and fractions are Decimal strings.
Every model forbids extra fields, so the schemas set `additionalProperties: false` throughout.

## Tool rosters — `tool-rosters/`

`_core.yaml` holds the desk `desk.*` core eight, which every seat receives. Each seat file holds
only that seat's own tools and sets `core: true`. The effective roster a seat sees on
`/mcp/<short>` is the core eight plus the seat's `tools`.

| File | Seat | Own tools | Effective |
|---|---|---|---|
| `_core.yaml` | every seat | 8 (`desk.*`) | - |
| `bot-00-chief.yaml` | CHIEF | 7 | 15 |
| `bot-01-scout.yaml` | SCOUT | 7 | 15 |
| `bot-02-risk.yaml` | RISK | 7 | 15 |
| `bot-03-whale.yaml` | WHALE | 6 | 14 |
| `bot-04-sniper.yaml` | SNIPER | 7 | 15 |
| `bot-05-rug.yaml` | RUG | 7 | 15 |
| `bot-06-exit.yaml` | EXIT | 7 | 15 |
| `bot-07-shill.yaml` | SHILL | 3 | 11 |
| `bot-08-signal.yaml` | SIGNAL | 6 | 14 |
| `bot-09-journal.yaml` | JOURNAL | 7 | 15 |

Sizes and grants follow `docs/ROSTER.md` section 6 and the matrix in `docs/TOOL_CATALOG.md`.
Tool names are the dotted catalog ids. Each seat's `consumers` lists only that seat.

Per-tool fields:

- `name`: dotted `<namespace>.<verb>` (G-7 `TOOL_NAME_RE`). The transport name is derived at
  exposure time and is never stored here.
- `kind`: `read` never mutates a system of record and fails open. `write` mutates and fails closed.
- `side_effect`: `read` or `paper-write`. `live-write` is never permitted in a roster.
- `gates`: `g6` on every write tool. The tool's `input.required` must include `approval_id`.
- `rollback_plan`: required in `input.required` of every write tool (G-7 `WRITE_REQUIRED_FIELDS`).
- `backend`: the registry capability that implements the tool.
- `input`: JSON Schema, `type: object`, `additionalProperties: false`.

G-7 (`ci/gates/check_desk_integrity.py`) fails the build when:

- an effective roster has fewer than 8 or more than 15 tools;
- a tool name is duplicated, or does not match the dotted pattern;
- a tool has no input schema, or a g5/g6 tool's schema does not require its gate's fields;
- a write tool is not tagged `g6`;
- any tool name starts with `exec.live`. No seat may resolve a live-write tool.

The seat's `endpoint` must equal `/mcp/<short>`.

Check the rosters with:

```bash
python3 ci/gates/check_desk_integrity.py --repo .
```

## Changes — `changes/`

Every change to a file under a `contract_surface` is proposed in a change document in
`changes/<change-id>.yaml`. G-4 (`ci/gates/check_contracts.py`) reads that document; see
`changes/README.md` for the fields it requires.

Required fields: `change_id`, `proposed_by`, `surface`, `breaking`, `version`, `summary`.
A breaking change also needs a major version bump, a `migration_note`, and an acknowledgement
from every consumer listed for the surface in `ownership.yaml`. Contract changes merge before any
implementation that depends on them.

```bash
python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/<change-id>.yaml
```
