---
name: tool-connections
description: Open, authenticate, and persist browser sessions for every website and tool required by PumpGrok. Includes the safe wallet-connection handoff protocol.
bots:
  - bot-00-chief
gates:
  - G-3
---

# Tool Connections

## L1 - Summary
CHIEF-owned setup for every website and tool session the desk needs: which sites, how sessions persist, and the safe wallet-connection handoff. Runs during setup and whenever a session breaks.

## L2 - Method
1. Required sites: X / Twitter, pump.fun, gmgn.ai, jupiter.ag, photon / axiom, solscan.io, rugcheck.xyz.
2. Wallet connection protocol:
   - The user creates a brand-new throwaway wallet.
   - The user funds it with at most $200 USDC plus SOL for fees.
   - The Bot hands the screen to the human for the connection flow.
   - The Bot confirms the public address and records it in `desk.md`.
   - Never accept, store, or request a seed phrase or private key.
3. Persist sessions per the site's own rules; re-run this skill when a session expires rather than working around the login.

## Failure modes
- Login wall or CAPTCHA: hand to the human per `browser-ops`; never bypass.
- Session loss mid-ticket: pause dependent work and mark affected evidence `BLIND` until the session is restored.
- Any key-material exposure: abort and escalate per the constitution.

## References
- Companion skills: `browser-ops` (handoff rules), `pumpgrok-setup` (first-run order)
- Gate: G-3
