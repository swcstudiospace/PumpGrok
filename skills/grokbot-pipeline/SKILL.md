---
name: grokbot-pipeline
description: Operator-run pump.fun screening pipeline ported to src/pumpgrok/engine (retired oracle pin in docs/VENDOR_PIN.md). Produces dry-run trade evidence (nine-stage pipeline, four Grok agents, JSONL log, replay tooling) that feeds all eight desk roles via tools/pipeline_evidence.py (JSON plus PIPELINE-EVIDENCE). Never enables live trading.
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
The pump.fun screening pipeline that turns a firehose of new launches into pre-screened, scored, evidence-backed candidates. It runs dry-run only with real market prices; its verdicts enter the ticket flow as evidence, never as authorization. The oracle tree is retired: the ported engine lives at `src/pumpgrok/engine/` (provenance in `docs/VENDOR_PIN.md`, license at `src/pumpgrok/engine/LICENSE-grokbot-pumpfun`).

## L2 - Method
1. Component location and provenance: the ported engine lives at `src/pumpgrok/engine/` (monitor, analyzer, scoring, reputation, exits, watcher, agents, pipeline, tune). The desk reaches it through `pumpgrok scout pipeline` and `tools/pipeline_evidence.py`; nothing imports the retired oracle.
2. Execution is paper only: the desk runs in `paper` mode and the live path refuses with exit 3. The retired `mode: live` stub raised `NotImplementedError`; the desk never used it and never will.
3. One-time setup (host or operator): `uv sync` at the repository root. No separate virtualenv, no `requirements.txt`, no `config.yaml` copy: the ported engine reads `src/pumpgrok/config/overlays/` plus `PUMPGROK_*` env. Secrets boundary: `GROKBOT_*` and `PUMPGROK_*` secrets stay in the operator environment and are never written into the journal, briefs, proposals, `desk.md`, or any repository file.
4. Run the screen (paper only):
```bash
pumpgrok scout pipeline --candidates --limit 5
pumpgrok report --daily
```
Candidate evidence enters the ticket flow through `tools/pipeline_evidence.py` (JSON plus PIPELINE-EVIDENCE). Scores are prior only, never clearance.
5. Desk bridge (from the repository root, stdlib only):
```bash
python tools/pipeline_evidence.py --candidates --block --limit 5
python tools/pipeline_evidence.py --log <archived-trades.jsonl> --mint <MINT> --block
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
- Pin note and provenance: `docs/VENDOR_PIN.md`; oracle license: `src/pumpgrok/engine/LICENSE-grokbot-pumpfun`
