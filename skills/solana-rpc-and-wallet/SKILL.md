---
name: solana-rpc-and-wallet
description: Safe patterns for reading balances, token accounts, metadata, Token-2022 extensions, and managing the throwaway wallet connection without ever handling private keys.
bots:
  - bot-04-sniper
  - bot-06-exit
gates:
  - G-3
required_tools:
  - onchain.priority_fee
required_data:
  - solana_rpc
permissions:
  max_side_effect: read
  network: true
  filesystem: none
---

# Solana RPC and Wallet

## L1 - Summary
Safe read patterns for balances, token accounts, metadata, and Token-2022 extensions, plus the throwaway-wallet connection rules. Reads chain state; never handles private keys.

## L2 - Method
1. Wallet rules (non-negotiable):
   - Only a dedicated throwaway wallet (at most $200 USDC plus SOL for fees).
   - Private keys and seed phrases never enter chat, files, or memory.
   - Connection is performed by the human via screen hand-off only.
   - The public address is recorded in `desk.md` after successful connection.
2. Priority fees and compute: prefer the output of `onchain.priority_fee` (RPC failover plus rate limits in `src/pumpgrok/tools/onchain/rpc.py`). Cap the maximum fee so a spike cannot drain the wallet.

## Failure modes
- Key material requested, offered, or pasted: abort the flow and escalate.
- Wallet connection outside human hand-off: refuse; no seat connects a wallet itself.
- Unbounded fee: any send path without a fee cap is refused.

## References
- Tools: `onchain.priority_fee`; cross-link: `key-custody` (secret handling)
- Gate: G-3; constitution: `prompts/_shared/core-directives.xml`
