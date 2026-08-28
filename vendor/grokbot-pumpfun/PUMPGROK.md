# PumpGrok vendor pin

This directory is the grokbot-pumpfun screening engine, vendored as regular
files (not a git submodule) so a clone of PumpGrok actually contains the
source.

- Upstream: https://github.com/zostaff/grokbot-pumpfun
- Pin: `409e74c905faa0e9de42e918efe2c604f206856e` (`docs/english-markdown`)
- License: MIT (`LICENSE` in this directory)
- Desk procedure: `skills/grokbot-pipeline/SKILL.md` in the PumpGrok root
- Desk bridge: `tools/pipeline_evidence.py` in the PumpGrok root

Desk rules that override upstream docs:

1. Run `mode: dry-run` only. Do not set `mode: live`. Do not fill
   `solana.wallet_private_key`. Upstream live execution is a stub on
   purpose: a real send would bypass PumpGrok ticket approval.
2. `GROKBOT_*` secrets stay in the operator environment. Never write them
   into the journal, briefs, proposals, `desk.md`, or any git file.
3. Pipeline verdicts are evidence for SCOUT / RISK / WHALE / SHILL / RUG /
   EXIT. They are not RISK clearance and not human approval.
4. `tx_hash: "dry_run"` is not a fill. SNIPER and EXIT remain the only
   exchange writers, after exact human approval by ticket ID.

Runtime artefacts (`config.yaml`, `.venv/`, `logs/`, `state/`, `.env`) are
gitignored here. Copy `config.example.yaml` to `config.yaml` locally.
