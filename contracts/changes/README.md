# contracts/changes/

One change document per proposed change to a contract surface. This directory is the G-4 input:
`ci/gates/check_contracts.py --change contracts/changes/<change-id>.yaml` reads one document and
checks it against the diff.

## Document shape

```yaml
change_id: feat-order-placed-note        # unique, matches the file name
proposed_by: bot-00-chief                 # a seat id from ownership.yaml
surface: contracts/events/order_placed.schema.json   # the contract file this change touches
surfaces: []                              # optional: further contract paths, listed individually
breaking: false                           # true requires the rules below
version: 1.1.0                            # semver
previous_version: 1.0.0                   # required when breaking: the major must increase
summary: One line on what the contract change does.
semantic_changes: []                      # declare meaning changes explicitly, [] if none
migration_note: ""                        # required when breaking
acknowledgements:                         # one entry per consumer listed for the surface
  - bot: bot-01-scout
    ack: true
```

Required fields for G-4: `change_id`, `proposed_by`, `surface`, `breaking`, `version`, `summary`.

## Rules

- The document's `surface` and `surfaces` must cover every contract-surface file in the diff,
  except files under `contracts/changes/`. List each file individually. `contracts/**` does not
  satisfy the check.
- A breaking change needs a major version bump, a `migration_note`, and `ack: true` from every
  consumer listed in `ownership.yaml` (`contract_consumers`).
- A non-breaking change still needs a document. Acknowledgements are informational there, but a
  rejection blocks the change.
- Generated files (`contracts/events/*.schema.json`) change only by regenerating from
  `src/pumpgrok/ledger/events.py`. The change document describes the model change that produced
  them.
- One active document per change. Archive the previous document when its change has merged.
