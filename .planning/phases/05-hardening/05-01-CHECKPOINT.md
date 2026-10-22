# Checkpoint Record: 05-01 Task 1

checkpoint: `checkpoint:human-verify` (gate=blocking-human)
name: Approve prometheus-client legitimacy and install uv 0.13.4
plan: 05-01-PLAN.md, task 1 (before `uv add`)
status: approved
approved_by: user (ask: prom, Approve both)
user_response: "Approve both (Recommended)"
scope: add prometheus-client 0.26.0 to pyproject.toml and uv.lock with hashes; upgrade host uv from 0.11.26 to 0.13.4 (R49 V-2, matching Dockerfile and CI pins)

## Approved items

| # | Item | Version | Source |
|---|------|---------|--------|
| 1 | prometheus-client | 0.26.0 (pin `>=0.26,<0.27`) | https://github.com/prometheus/client_python (PyPI published 2026-07-24, requires_python >=3.9) |
| 2 | uv (host tooling) | 0.13.4 | https://github.com/astral-sh/uv |

Verdict basis: seam returned SUS for prometheus-client only for `unknown-downloads` (downloads field null); repository URL confirmed as the official Prometheus client.

No other blocking-human checkpoint is approved by this record.
