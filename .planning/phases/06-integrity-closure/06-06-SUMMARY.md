# Phase 06 Plan 06: Read-only curve layout probe (INT-10) — Summary

- Phase: 06-integrity-closure, Plan 6, Requirement INT-10 (R65)
- Status: complete (offline contract; live run deferred to orchestrator after merge)
- `LAYOUT_STATUS` in `src/pumpgrok/tools/onchain/curve_layout.py` stays `ASSUMED`;
  RPC-derived entries remain fail-closed (`data_unavailable`). No behavior change.

## Completed tasks

1. Read-only curve layout probe script, fixture, and probe doc — commit `c470de1`.
   - `scripts/probe_curve_layout.py` (new): single read-only `getAccountInfo`
     POST via stdlib `urllib` against the configured public RPC
     (default `https://api.mainnet-beta.solana.com`, override `--endpoint` /
     `RPC_ENDPOINT`); account from `--account` / `BONDING_CURVE_ACCOUNT`; no
     keys loaded, no wallet, no signing path. Success writes the decoded layout
     to `tests/fixtures/rpc/bonding_curve/probe.json` and `Status: VERIFIED` to
     `docs/CURVE_LAYOUT_PROBE.md`. Any failure (no account configured,
     transport error, RPC error, unknown account, undecodable bytes) exits 0,
     keeps `ASSUMED`, writes `probe.json` with the exact error verbatim and the
     doc with `Status: ASSUMED` plus `Error: <exact probe error>`.
   - `tests/fixtures/rpc/bonding_curve/probe.json` (new): `ASSUMED` record; the
     probe was NOT run here (live network call deferred to the orchestrator
     after merge, per assignment), so `probe_error` records that verbatim and
     the doc `Error:` line carries the identical string.
   - `docs/CURVE_LAYOUT_PROBE.md` (new): the one Phase 6 `docs/` exception per
     06-CONTEXT.md Out-of-scope; `Status: ASSUMED` + verbatim `Error:` line.
   - `src/pumpgrok/tools/onchain/curve_layout.py`: intentionally unchanged —
     `LAYOUT_STATUS: Final[str] = "ASSUMED"` already fail-closed; see deviation 1.

## Commits

- `c470de1`: feat(integrity): read-only curve layout probe script, fixture,
  probe doc (INT-10)

## Deviations

1. Plan acceptance grep for `LAYOUT_STATUS` does not match the annotated
   assignment: the plan's pattern `LAYOUT_STATUS\s*=\s*"(ASSUMED|VERIFIED)"`
   matches neither `LAYOUT_STATUS: Final[str] = "ASSUMED"` (curve_layout.py:35)
   nor the `==` comparisons in tests. Weakening the annotation to satisfy the
   grep would be cosmetic churn, so the code is untouched and the corrected
   check is `grep -rqE 'LAYOUT_STATUS[^=]*=\s*"(ASSUMED|VERIFIED)"'
   src/pumpgrok` (exits 0; matches the annotated assignment). Value verified
   `ASSUMED`, consistent with `probe.json` and the doc.
2. No bonding-curve account is configured: the repo holds no confirmed
   mainnet curve PDA (the program id in `layout.json` is marked
   ASSUMED/unconfirmed training knowledge), so no pubkey was fabricated. The
   script takes `--account` / `BONDING_CURVE_ACCOUNT`, and the committed
   fixture/doc record the ASSUMED not-run state. The orchestrator's live run
   supplies the known account and overwrites both artifacts.
3. The probe was not executed here (live network call, per assignment); the
   offline contract (files exist, Status/Error lines, no-send grep) is what
   this plan delivers.

## Acceptance commands (for the orchestrator to run after merging)

```bash
test -f tests/fixtures/rpc/bonding_curve/probe.json \
&& test -f docs/CURVE_LAYOUT_PROBE.md \
&& grep -qE '^Status: (VERIFIED|ASSUMED)$' docs/CURVE_LAYOUT_PROBE.md \
&& (grep -qE '^Status: VERIFIED$' docs/CURVE_LAYOUT_PROBE.md \
    || grep -qE '^Error: .+' docs/CURVE_LAYOUT_PROBE.md) \
&& grep -rqE 'LAYOUT_STATUS[^=]*=\s*"(ASSUMED|VERIFIED)"' src/pumpgrok \
&& ! grep -nE "sendTransaction|send_transaction|requestAirdrop|signTransaction" scripts/probe_curve_layout.py
```

Live refresh (orchestrator, after merge — real network call):

```bash
BONDING_CURVE_ACCOUNT=<known-curve-pubkey> uv run python scripts/probe_curve_layout.py
```

then re-run the acceptance block above; on success the doc reads
`Status: VERIFIED` and `LAYOUT_STATUS` may be flipped to `VERIFIED` only after
human review of the decoded fixture.

## Changed files

- `scripts/probe_curve_layout.py` (new)
- `tests/fixtures/rpc/bonding_curve/probe.json` (new)
- `docs/CURVE_LAYOUT_PROBE.md` (new)
- `.planning/phases/06-integrity-closure/06-06-SUMMARY.md` (new, this file)
