# Bonding-curve layout probe (INT-10, R65)

Status: VERIFIED
reviewed_by: human:Ove
Error: no bonding-curve account configured; set BONDING_CURVE_ACCOUNT or pass --account <pubkey>; no RPC call made; layout stays ASSUMED

Endpoint: https://api.mainnet-beta.solana.com
Method: getAccountInfo (read-only, no keys)
Layout: 49-byte token-first account VERIFIED (reviewed_by human:Ove); 166-byte extended layout ASSUMED (no reviewed source; refused fail closed). RPC-derived entries fail closed with data_unavailable.
