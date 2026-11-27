# ADR-0002. Use Clock-only time and integer base-unit money

- **Status:** accepted
- **Date:** 2026-11-20
- **Deciders:** A03
- **Task:** T1482-arch

## Context and Problem Statement

Sweeps B02 and B03 (US-008, US-009) and AC-008, AC-009 require 0 float money fields and 0 wall-clock reads outside the clock module

## Decision Drivers

Replay hash equality AC-012; ledger reconciliation to the lamport; deterministic replay

## Considered Options

- Float money with rounding
- Direct datetime.now calls

## Decision Outcome

Chosen option: "All timestamps come from injected Clock (replay/clock.py is the only wall-clock reader) and all money is integer base units with Decimal ratios separate".

### Positive Consequences

- Replay determinism (AC-012, AC-028) and ledger reconciliation hold; money and clock AST scans are cheap CI gates.

### Negative Consequences

- Every new timestamp call site needs a Clock parameter; float-money shortcuts are rejected at review.

## Consequences

Call sites pass Clock explicitly; money AST scan and clock AST scan must stay green; Decimal strings in contracts
