# Design A decisions (record)

Status: OWNER-DECIDED (human:SomeRandmGuyy, 2026-11-13). RISK review: NOT RECORDED. Plan 14-01 requires an owner and RISK review before implementation; this record does not claim the RISK review.

Source of values: the proposal in 14-DESIGN-A-PROPOSAL.md (commit 9d90eb8), with the owner choices below. Where the proposal says UNKNOWN and the owner delegated "use the recommended values per a professional trading standard", the value is marked RECOMMENDED with its reason. Values sourced from the repo are marked REPO with file:line.

## Owner choices

| Item | Decision | Basis |
|---|---|---|
| Policy source of record | Design A with the N6 corrections | owner |
| Daily budget | 400 (minute 6, hour 60) | owner; legacy 2000 rejected |
| Breaker | 3 failures in 60 s, one half-open probe | owner; legacy 8/120 s rejected |
| Bus constants | Repo values (BACKOFF_MAX_S 16) | owner |
| Hermes journal rollup (OD-13) | Disable all six superseded jobs | owner |
| Cache TTLs | 24h, 300s, 900s, 60s, 30s negative; LRU 5000 | owner |
| Reserve share | 20%, checker only | owner |

## Prefilter and in-flight values

| Item | Value | Provenance |
|---|---|---|
| Minimum age before a candidate is considered | 120 s | REPO: src/pumpgrok/config/sections/engine.py:21 (`min_age_seconds`) |
| Minimum unique buyers | 5 | REPO: src/pumpgrok/config/sections/engine.py:18 (`min_unique_buyers`) |
| Age upper bound | 3600 s (1 hour) | RECOMMENDED: candidates older than an hour are outside the launch window the desk is built for |
| Market window | Rolling 3600 s from first trade | RECOMMENDED: matches the age bound, so each candidate is judged in one window |
| Mint cooldown after a decision | 300 s | RECOMMENDED: prevents repeated Grok spend on one mint within five minutes |
| grok.min_prerank | 0.5 on a normalised 0 to 1 prerank | RECOMMENDED: midpoint gate; no repo source exists, so RISK should confirm the scale |
| In-flight bound | 4 concurrent Grok calls | RECOMMENDED: bounds parallel spend and matches the budget minute cap of 6 |

## Open items

1. RISK review of this record, and of the RECOMMENDED values above. Not recorded.
2. The min_prerank scale (its normalisation) has no repo source; RISK must confirm it before use.
3. Plan 14-01 baseline capture on the exact clean Phase 14 starting tree (its precondition); not recorded here.
