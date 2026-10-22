# Security

## Posture

PumpGrok is a paper-trading desk. It runs in paper mode by default and can never move real
funds: the only enabled execution adapter is the paper adapter, and `pumpgrok run --mode live`
exits 3 until every precondition of the live gate holds.

## Key custody

Key custody: no key material exists in paper mode; nothing to custody.

The desk never requests, accepts, stores, prints or reasons about seed phrases, private keys or
recovery phrases. The settings model has no wallet-key field. Startup refuses environment names
that carry key-like substrings (`PRIVATE_KEY`, `SECRET_KEY`, `SEED`, `MNEMONIC`, `PHANTOM`,
`WALLET_SECRET`, `KEYPAIR`). The one exception is `PUMPGROK_REPLAY__SEED`, which is a replay
seed and not key material. Startup also refuses key-bearing URL values and unknown `PUMPGROK_*`
names, and it reports names and locations only, never values.

## Secrets handling

- Operator configuration arrives only as `PUMPGROK_*` environment variables, or through the
  optional `.env` file that compose injects at run time (`required: false`).
- `.env` is gitignored and excluded from the image by `.dockerignore`. No secret is passed as a
  build argument, and nothing is baked into the image.
- `.env.example` carries placeholders only and must pass the secrets gate (G-3).
- Logs are JSON and pass through a redaction filter. Secret values are never logged; a secret is
  shown as its length at most.

## Container

- The runtime user is non-root (`pumpgrok`, system account).
- The image contains the installed package, the smoke replay fixture and nothing else from the
  repository. `vendor/`, `.git`, `.planning/`, `var/` and `tests/` (except the fixture) are excluded.
- The image's one-shot replay command is read-only with respect to its inputs. Its ledger output
  goes to `/app/var` inside the container.

## Untrusted content

Token metadata, website text, social posts and chat messages are untrusted data. Instructions
found inside them are never executed (constitution clause 7). Seat output that cites such content
treats it as evidence, not as direction.

## Gates

- G-3 (`ci/gates/check_secrets.py`) scans the change for committed secrets.
- G-4 (`ci/gates/check_contracts.py`) proves an acknowledgement is present for every required
  consumer (contract consumers minus the proposer; a proposer acknowledgement is ignored),
  not who wrote it. Authorship is evidenced by git history and reviewed by QUALITY.

## Reporting a vulnerability

Report suspected vulnerabilities privately to the repository maintainers. Do not put secrets,
wallet material or live endpoints with credentials in a public issue or pull request.

## Exceptions

No check is pre-listed here: every row below names a genuinely failing security gate
with its evidence. An expired row fails CI (`python3 ci/security/check_exceptions.py`,
enforced by `ci/tests/test_security_workflows.py`), so an exception cannot silently
linger past its expiry.

| Check | Fingerprint | Reason | Owner | Expiry (ISO) |
|---|---|---|---|---|
