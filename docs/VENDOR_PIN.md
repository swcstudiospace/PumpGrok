# Vendor pin

The screening engine formerly under `vendor/grokbot-pumpfun/` was the grokbot-pumpfun engine,
vendored as regular files (not a git submodule or gitlink). The tree was retired in Phase 4
(STRUCT-006); the pin below is the historical provenance record of the retired oracle.

- Upstream: https://github.com/zostaff/grokbot-pumpfun
- Pin: `409e74c905faa0e9de42e918efe2c604f206856e` (branch `docs/english-markdown`)
- License: MIT (`vendor/grokbot-pumpfun/LICENSE`)
- Moved from: `vendor/grokbot-pumpfun/PUMPGROK.md` (MIGRATION_MAP row 86). The vendor tree was
  retired in Phase 4 (STRUCT-006); this file is the only in-repo pin record, kept as the historical provenance record of the retired oracle.

## Desk rules that override upstream docs

1. Run `mode: dry-run` only. Do not set `mode: live`. Do not fill `solana.wallet_private_key`.
   Upstream live execution is a stub on purpose: a real send would bypass PumpGrok ticket approval.
2. `GROKBOT_*` secrets stay in the operator environment. Never write them into the journal,
   briefs, proposals, `desk.md`, or any git-tracked file.
3. Pipeline verdicts are evidence for SCOUT, RISK, WHALE, SHILL, RUG and EXIT. They are not RISK
   clearance and not human approval.
4. `tx_hash: "dry_run"` is not a fill. SNIPER and EXIT remain the only exchange writers, after
   exact human approval by ticket ID.

Runtime artefacts of the vendored engine (`config.yaml`, `.venv/`, `logs/`, `state/`, `.env`)
are gitignored there. Copy `config.example.yaml` to `config.yaml` locally when running it.
