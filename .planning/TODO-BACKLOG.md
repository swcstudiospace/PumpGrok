# TODO / FIXME / HACK backlog (v3 milestone audit)

Sweep: `rg -n -e TODO -e FIXME -e HACK` over the repository, excluding `node_modules`, `vendor`, `dist`, `build`, `.git` and `.venv`. Run on HEAD (commit of this file's parent). Result: 9 hits, all in documentation.

No marker is in source, tests, CI, scripts, services or `.planning/`. The earlier count of 172 was vendored `.venv` site-packages noise and is excluded.

| # | File:line | Marker context | Disposition | Reason |
|---|---|---|---|---|
| 1 | docs/DISCOVERY.md:371 | "both bodies are a TODO comment followed by" (LiveExecutor.buy/sell) | DEFERRED | Quotes a stub in the v2 design discovery record. Historical design record; banner required by DOC-04. Live execution stays refused (Phase 10). |
| 2 | docs/DISCOVERY.md:431 | `# TODO(live): ... Load Keypair from config.solana.wallet_private_key` | DEFERRED | Quoted pseudo-code in a historical design record. No private key enters the system (D4); the setting was removed (R3). |
| 3 | docs/FOUNDATION_STACK.md:746 | M-10 row: JitoConfig and wallet_private_key removed (R3); "TODO" text in the table | DEFERRED | Migration-map row describing a removed vendor setting. Historical record. |
| 4 | docs/MIGRATION_MAP.md:198 | row 107, vendor executor split, mentions TODO | DEFERRED | Migration map for vendored code retired in Phase 4 (STRUCT-006). Historical record. |
| 5 | docs/MIGRATION_MAP.md:272 | JitoConfig / wallet_private_key rows | DEFERRED | Same as #3. Historical record. |
| 6 | docs/MIGRATION_MAP.md:274 | LiveExecutor TODO lines `:150`, `:156-158` in vendored source | DEFERRED | Refers to vendored source removed in Phase 4. Historical record. |
| 7 | docs/design/paper-engine.md:50 | Live executor row: "six-step TODO" | DEFERRED | Design record for the paper engine. Live executor is not registered (Phase 10); no adapter enablement in this milestone. |
| 8 | docs/design/paper-engine.md:162 | "...the order is rejected..." (matched on TODO text in a sentence) | DEFERRED | Design prose; not a marker for work. Historical design record. |
| 9 | docs/design/paper-engine.md:843 | `_audit` line matching the marker text in prose | DEFERRED | Design prose describing live-write refusal. Not a marker for work. |

## Dispositions

- Resolved in this milestone: 0.
- Mapped to an open or in-progress phase: 0 (no open phase in v3).
- Deferred (historical design records, banner present per DOC-04): 9.
- Out of scope: 0.
- Unmapped backlog: 0 code items. Any future marker must carry a tracking reference (CODE_QUALITY_BAR).

## Verification

Re-run the sweep at the commit that closes this milestone. The expected result is the same 9 documentation hits, all still DEFERRED.
