# User stories - PumpGrok outstanding milestones (T1482-req)

Backlog for v4 Phases 11-14, Phase 17, sweeps B00-B09 and L1-P1.
Each story carries its MoSCoW class and a point estimate.
Stories are independent units: INVEST check I passes only with zero
listed dependencies, so sequencing lives in the spec and the tracker.
IDs are stable across revisions and never renumbered.

## US-001 draft assumption

As the chief, I want the phase 11 package in the v4 series to complete with every work unit carrying measurable completion evidence, so that leadership sees one closed phase instead of scattered claims.

MoSCoW: Must. Estimate: 5.

## US-002 draft assumption

As the release owner, I want the phase 12 package in the v4 series to meet its entry criteria while the phase 11 package is already closed, so that sequencing stays legible and regressions surface early.

MoSCoW: Must. Estimate: 5.

## US-003 draft assumption

As the audit owner, I want the phase 13 package in the v4 series to present each quality claim backed by a rerunnable command transcript, so that auditors repeat the proof instead of trusting prose.

MoSCoW: Must. Estimate: 5.

## US-004 draft assumption

As the operator, I want the phase 14 package in the v4 series to close with the desktop checklist refreshed and the changelog entry written, so that day-to-day operation reflects the shipped behavior.

MoSCoW: Must. Estimate: 3.

## US-005 draft assumption

As the chief, I want the phase 17 series to land as numbered deliveries with one owner each and a shared completion ledger, so that parallel tracks never blur into a single ambiguous batch.

MoSCoW: Must. Estimate: 5.

## US-006 draft assumption

As the typecheck owner, I want sweep B00 to leave every package file passing strict static type checking with zero suppressions, so that callers get compile-time guarantees on each exported symbol.

MoSCoW: Must. Estimate: 3.

## US-007 draft assumption

As the style owner, I want sweep B01 to leave the tree passing the linter and formatter checks with zero violations in all 5 gate runs, so that diffs stay reviewable and churn stays low.

MoSCoW: Must. Estimate: 3.

## US-008 draft assumption

As the ledger owner, I want sweep B02 to confirm every monetary quantity in the codebase is an integer count of base units with ratios kept separate, so that reports reconcile to the lamport.

MoSCoW: Must. Estimate: 5.

## US-009 draft assumption

As the replay owner, I want sweep B03 to confirm every timestamp originates from the injected clock with zero wall clock reads outside the clock module, so that replayed runs repeat bit for bit.

MoSCoW: Must. Estimate: 3.

## US-010 draft assumption

As the contract owner, I want sweep B04 to confirm every seat-facing contract validates its inputs and rejects unknown fields, so that malformed requests fail at the boundary with a named error.

MoSCoW: Must. Estimate: 5.

## US-011 draft assumption

As the risk owner, I want sweep B05 to confirm every uncertain state denies ordering actions and raises a named refusal, so that missing data never converts into a silent trade.

MoSCoW: Must. Estimate: 5.

## US-012 draft assumption

As the replay owner, I want sweep B06 to confirm two replays of the smoke dataset produce identical event hashes, so that investigators trace any discrepancy to a code change with confidence.

MoSCoW: Must. Estimate: 3.

## US-013 draft assumption

As the quality owner, I want sweep B07 to confirm the full test collection runs and passes with zero skipped safety cases, so that every invariant keeps a live guard.

MoSCoW: Must. Estimate: 5.

## US-014 draft assumption

As the security owner, I want sweep B08 to confirm the dependency audit reports zero known vulnerabilities in the locked set, so that the release ships without a disclosed exposure window.

MoSCoW: Must. Estimate: 3.

## US-015 draft assumption

As the docs owner, I want sweep B09 to confirm every operator command in the documentation runs verbatim against the current tree, so that new operators follow steps that work on first attempt.

MoSCoW: Should. Estimate: 3.

## US-016 draft assumption

As the chief, I want the L1-P1 fix set to land with each defect traced to a regression test, so that closed issues stay closed across later refactors.

MoSCoW: Must. Estimate: 5.

## US-017 canonical gate suite

As the release owner, I want the canonical gate suite (lint, typecheck, tests, dependency audit) to pass on the merge commit, so that main always holds a green baseline.

MoSCoW: Must. Estimate: 3.

## US-018 replay smoke

As the operator, I want the recorded smoke replay to finish one full ten-seat cycle offline and emit an identical hash on rerun, so that morning checks confirm the desk from a single command.

MoSCoW: Must. Estimate: 3.

## US-019 live refusal

As the operator, I want the live-mode invocation to be refused with exit code 3 and each unmet precondition printed, so that nobody reaches a fund-moving path by accident.

MoSCoW: Must. Estimate: 2.

## US-020 gateway tests

As the gateway owner, I want the desk gateway test collection to pass in its own project runner, so that seat-facing reads keep working after changes to the core package.

MoSCoW: Must. Estimate: 3.

## US-021 per-PR CI

As the release owner, I want every pull request to show all required CI jobs green before review closes, so that merges never land on a red signal.

MoSCoW: Must. Estimate: 3.

## US-022 paper-only invariant

As the compliance owner, I want zero live adapters registered and zero key material reachable from the runtime, so that the paper-only promise is structural rather than conventional.

MoSCoW: Must. Estimate: 3.

## US-023 tracker programming

As the chief, I want each outstanding milestone represented by one tracker issue with numbered sub-issues for its work units, so that progress tracking matches the shipped units exactly.

MoSCoW: Must. Estimate: 5.

## US-024 merge discipline

As the release owner, I want merges restricted to reviewed draft pull requests with green CI, so that the main branch carries only evidence-backed changes.

MoSCoW: Must. Estimate: 2.

## US-025 completion receipts

As the chief, I want every completed unit to carry a receipt naming the commands run and their exit codes, so that reviewers verify claims without re-asking for transcripts.

MoSCoW: Must. Estimate: 2.

## US-026 documentation lint

As the docs owner, I want every new document to pass the ASCII and instruction-file lint, so that documentation checks stay deterministic in CI.

MoSCoW: Must. Estimate: 2.
