# ADR-0003. Publish gateway OpenAPI contract before implementation

- **Status:** accepted
- **Date:** 2026-11-20
- **Deciders:** A03
- **Task:** T1482-arch

## Context and Problem Statement

US-010 and AC-010 require 37 tools to reject unknown fields; gateway is the seat-facing boundary (POST /mcp/<short>)

## Decision Drivers

Contract-first rule; unknown-field rejection at the boundary; N-1 compatibility window

## Considered Options

- YAML rosters only (existing)
- GraphQL

## Decision Outcome

Chosen option: "Publish docs/architecture/contracts/pumpgrok-gateway.yaml v1.0.0 (OpenAPI 3.1) before any consumer task is claimed; pin consumers to its digest".

### Positive Consequences

- Consumers (A05, A06, A07, A08) code against a versioned digest-pinned contract; unknown-field rejection (AC-010) is testable from it.

### Negative Consequences

- Contract changes need a version bump and, when breaking, L3 human approval before implementation tasks open.

## Consequences

Additive-only changes bump minor; breaking changes are L3 with migration plan and consumer acks
