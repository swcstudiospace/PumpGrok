# Threat model (STRIDE) - PumpGrok (T1482-arch)

Owner: A03. Status: pending A10 co-sign; residual risk acceptance
is A10's decision only. Zones: Desk (trusted), CI (trusted),
External (untrusted: Solana RPC, Jupiter quote API, tracker),
Human operator (trusted).

| Crossing | S | T | R | I | D | E |
|---|---|---|---|---|---|---|
| tool-registry -> Solana RPC (read-only) | n/a, public RPC | Response tampering: validate jsonParsed, fail closed | Ledger records source and UTC | Public data only; no keys sent | RPC timeout -> named refusal, 0 fills | n/a, no privileges granted |
| tool-registry -> Jupiter quote (never /execute) | n/a | Quote tampering: advisory only, human approves exact ticket | Ticket records quote | No key material | Quote absent -> refuse ordering | n/a |
| Network -> desk-gateway | Bearer token spoofing: per-seat tokens, hmac.compare_digest | Body tampering: 1 MiB cap, JSON schema, unknown-field rejection | Gateway logs seat + status only | Token never logged; 503 leaks no detail | ThreadingHTTPServer with body cap; unauthenticated 401 | Cross-seat token 403; unconfigured seat 503 fail-closed |
| CI -> tracker | n/a | Tracker tampering: machine-read export, 16 parents with sub-issues | Receipts name every command and exit code | n/a | n/a | Merge guard refuses red PRs (AC-024) |
| Human -> desk (approval) | Approval must name ticket ID + mint + size + max slippage | n/a | Journal append-only with ticket IDs | n/a | n/a | Only SNIPER buys, only EXIT sells; RISK KILL non-overridable |

Paper-only invariant: 0 live adapters register, live mode exits 3,
0 key material in repo, no `exec.live*` tool name (AC-019, AC-022,
AC-030, NFR-C1). High-risk crossings awaiting A10 co-sign: network
-> desk-gateway (authentication boundary) and human approval
(execution boundary).
