---
name: tool-connections
description: Open, authenticate, and persist browser sessions for every website and tool required by PumpGrok. Covers the RPC endpoint source and the non-paper wallet connection, which is a separate, typed, explicit human step that paper never runs.
bots:
  - bot-00-chief
gates: []
required_tools: []
required_data: []
permissions:
  max_side_effect: read
  network: true
  filesystem: none
---

# Tool Connections

## L1 - Summary
CHIEF-owned setup for every website and tool session the desk needs: which sites, how sessions persist, which RPC endpoint is in effect, and the non-paper wallet step. Runs during setup and whenever a session breaks. Paper uses website sessions and the RPC endpoint only. Paper never connects a wallet.

## L2 - Method
1. Required sites: X / Twitter, pump.fun, gmgn.ai, jupiter.ag, photon / axiom, solscan.io, rugcheck.xyz.
2. RPC endpoint source:
   - Check the source in effect: `uv run pumpgrok onboarding rpc`. It prints `default`, `explicit` or `unbound`. `default` is the configured endpoint with no operator choice recorded. `default` is not consent.
   - An operator may choose only a configured endpoint: `uv run pumpgrok onboarding rpc --endpoint <url>`. The operator types the `rpc <endpoint>` phrase shown at the prompt. Only scheme, host and port are recorded. Endpoint credentials never go in a command, a file or the chat.
3. Paper never connects a wallet. Paper needs no wallet, and the steps below do not run during a paper setup.
4. Non-paper wallet connection (separate, typed, explicit). This release has no non-paper start; run these steps only when the human moves the desk off paper:
   - The user creates a brand-new throwaway wallet.
   - The user funds it with at most $200 USDC plus SOL for fees.
   - The Bot hands the screen to the human for the connection flow.
   - The human types the public address into a separate confirmation step, explicitly. The Bot compares it with the wallet screen and records only that public address in `desk.md`. No other step records or confirms the address.
   - Never accept, store, or request a seed phrase or private key.
5. Persist sessions per the site's own rules. Re-run this skill when a session expires rather than working around the login.

## Failure modes
- Login wall or CAPTCHA: hand to the human per `browser-ops`; never bypass.
- Session loss mid-ticket: pause dependent work and mark affected evidence `BLIND` until the session is restored.
- RPC source reads `unbound`: no operator choice is in effect. Do not report an endpoint choice; ask the operator to record one or accept `default` explicitly.
- Typed address does not match the wallet screen: record nothing and ask the human to type it again.
- Wallet, key or phrase requested during paper: refuse; paper never asks for or reads one.
- Any key-material exposure: abort and escalate per the constitution.

## References
- Companion skills: `browser-ops` (handoff rules), `pumpgrok-setup` (first-run order and paper start), `desk-doctor` (input checks)
- CLI: `uv run pumpgrok onboarding rpc` (endpoint source)
- Gate: G-3
