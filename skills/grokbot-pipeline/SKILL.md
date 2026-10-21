---
name: grokbot-pipeline
description: Operator-run pump.fun screening engine vendored as in-tree files from zostaff/grokbot-pumpfun (pin 409e74c). Produces dry-run trade evidence (nine-stage pipeline, four Grok agents, JSONL log, replay tooling) that feeds all eight desk roles via tools/pipeline_evidence.py (JSON plus PIPELINE-EVIDENCE). Never enables live trading.
bots:
  - all
gates: []
required_tools: []
required_data: []
permissions:
  max_side_effect: read
  network: true
  filesystem: none
---

# GrokBot Pipeline

## L1 - Summary
The vendored pump.fun screening engine that turns a firehose of new launches into pre-screened, scored, evidence-backed candidates. It runs dry-run only with real market prices; its verdicts enter the ticket flow as evidence, never as authorization.

## L2 - Method
1. Component location and provenance: the engine lives at `vendor/grokbot-pumpfun/` as in-tree regular files, pinned at commit `409e74c905faa0e9de42e918efe2c604e6589e`. The desk never imports vendor Python; it reaches the engine only through the CLI steps below and `tools/pipeline_evidence.py`.
2. Execution is intentionally a stub upstream: `mode: dry-run` works end to end with real market prices; `mode: live` raises `NotImplementedError`. The desk uses dry-run exclusively.
3. One-time setup (host or operator):
```bash
cd ./vendor/grokbot-pumpfun
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp config.example.yaml config.yaml
```
Edit `config.yaml`: keep `mode: dry-run`; leave `solana.wallet_private_key` empty; never fill it. Secrets boundary: `GROKBOT_*` environment variables belong to this vendored component and are never written into the journal, briefs, proposals, `desk.md`, or any repository file.
4. Run the screen:
```bash
cd ./vendor/grokbot-pumpfun
.venv/bin/python -m src.pipeline --config config.yaml
python3 scripts/dashboard.py logs/trades.jsonl --watch 5
python3 scripts/replay.py logs/trades.jsonl
python3 scripts/tune.py logs/trades.jsonl
.venv/bin/python -m pytest -v
```
The run appends `buy` / `skip` / `close` records to `logs/trades.jsonl` with `tx_hash: dry_run`, which is not a fill.
5. Desk bridge (from the repository root, stdlib only):
```bash
python tools/pipeline_evidence.py --candidates --block --limit 5
python tools/pipeline_evidence.py --log vendor/grokbot-pumpfun/logs/trades.jsonl --mint <MINT> --block
```
Missing nested objects become `unavailable`; never invent scores. A missing log fails closed.
6. Stage-to-role mapping: SCOUT prefers `buy` records as the candidate pool (score is not clearance); RISK treats analyzer, audit, and checker output as additional evidence for its live checks (checker `approve: false` is counter-evidence, not a KILL substitute); WHALE uses metrics as prior with live holder checks still required; SHILL uses narrative output as prior; CHIEF uses timing and total score for queue priority but ingest never creates tickets; RUG uses `close.reason` as watch context; EXIT studies `close.reason` distributions; SNIPER ignores pipeline `tx_hash` and sends only after RISK plus exact human approval.

## Failure modes
- Engine cannot start: report the concrete failure and continue manual scouting with `BLIND` evidence standards.
- Failed or empty run: report unavailable data, never a token endorsement.
- High score or `approve: true`: not authorization and not CLEAR; the full RISK pass, CHIEF ticket, and human approval string are still required.
- `tx_hash: dry_run` mistaken for a fill: it is dry-run evidence only.

## References
- Bridge: `tools/pipeline_evidence.py` (JSON plus PIPELINE-EVIDENCE block)
- Desk report schema: PIPELINE-EVIDENCE block (token, log window, record type, analyzer, audit flags, narrative, checker, total score, desk action, sources)
- Pin note and overrides: `vendor/grokbot-pumpfun/PUMPGROK.md`
