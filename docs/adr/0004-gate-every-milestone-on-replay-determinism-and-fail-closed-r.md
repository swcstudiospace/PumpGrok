# ADR-0004. Gate every milestone on replay determinism and fail-closed refusal

- **Status:** accepted
- **Date:** 2026-11-20
- **Deciders:** A03
- **Task:** T1482-arch

## Context and Problem Statement

US-017 to US-021, US-024 and AC-017 to AC-021, AC-024, AC-027 to AC-029 define the canonical gate suite and merge discipline

## Decision Drivers

Enterprise quality bar; deterministic replay; no merge on red CI

## Considered Options

- Advisory gates
- Mandatory-only-on-main

## Decision Outcome

Chosen option: "Every milestone closes only when make lint typecheck test audit exit 0, replay smoke exits 0 with identical hash, live refusal exits 3, gateway pytest exits 0 and per-PR CI is 100 percent green".

### Positive Consequences

- Main always holds a green baseline; replay smoke and live refusal give a single-command morning check.

### Negative Consequences

- Milestones cannot close on partial evidence; receipts (US-025) must name every command and exit code.

## Consequences

Draft PRs merge only on green CI; receipts name every command and exit code (US-025)
