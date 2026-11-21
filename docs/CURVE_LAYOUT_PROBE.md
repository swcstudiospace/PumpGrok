# Bonding-curve layout probe (INT-10, R65)

Status: ASSUMED
Error: ValueError: no 49-byte program-owned curve account in recent signatures
Error: no bonding-curve account configured; set BONDING_CURVE_ACCOUNT or pass --account <pubkey>; no RPC call made; layout stays ASSUMED

Endpoint: https://api.mainnet-beta.solana.com
Method: getAccountInfo (read-only, no keys)
Layout: ASSUMED until a live probe decodes under it; RPC-derived entries fail closed with data_unavailable.
Record: decoded_pending_review means decoded but not human-reviewed; VERIFIED needs reviewed_by human:<name> <date>.
