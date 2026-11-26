# ADR-0001. Keep paper-only structural invariant with no live adapter

- **Status:** accepted
- **Date:** 2026-11-20
- **Deciders:** A03
- **Task:** T1482-arch

## Context and Problem Statement

NFR-C1 and US-022 require zero fund-moving paths; AC-019, AC-022, AC-030 verify refusal, adapter scan and secret scan

## Decision Drivers

Compliance NFR-C1 is non-negotiable; fail-closed on uncertain state; no keys in repo

## Considered Options

- Convention-only paper mode
- Separate live package

## Decision Outcome

Chosen option: "Paper-only is structural: adapter registry registers 0 live adapters, live mode exits 3, 0 key material resolves outside the live stub".

### Positive Consequences

- Paper-only holds structurally: adapter-scan (AC-022) and secret-scan (AC-030) stay green with 0 changes to the invariant.

### Negative Consequences

- Live trading cannot be enabled without a new L3 ADR, migration plan and A10 co-sign; no live adapter code is shipped to remove.

## Consequences

Live execution stays impossible in this release; any future live enablement needs a new L3 ADR and A10 co-sign
