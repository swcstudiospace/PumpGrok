# Ed25519 point-validation primitive: review record

Plan: 14-06 (checkpoint:decision), requirement ONB-06.
Owner: bot-02-risk (RISK). Governing files: `ownership.yaml` (`pyproject.toml`, `uv.lock` owned by bot-02-risk).
Scope of this record: the choice of primitive for the ONB-06 curve-point check. It does not touch wallet or settings code.

## Verdict

NOT APPROVED for dependency addition as the ONB-06 primitive. `cryptography` is not locked, and its public-key decode does not perform the curve-membership or canonical-encoding check that ONB-06 requires. The owner must decide before any dependency change. See "Options for the owner".

Review type: RISK agent self-review (bot-02-risk). This is NOT an external, independent, or third-party audit.

## 1. Package

| Field | Value | Source |
|---|---|---|
| Name | cryptography (PyCA) | wheel `METADATA` |
| Source | https://github.com/pyca/cryptography | wheel `METADATA` Project-URL |
| License | Apache-2.0 OR BSD-3-Clause | wheel `METADATA` License-Expression |
| Version examined | 50.0.2 | wheel `METADATA` / `WHEEL` |
| Wheel tag | cp311-abi3-manylinux_2_34_x86_64 (built with maturin 1.14.1) | wheel `WHEEL` |
| Artifact provenance | Local uv cache entry only (no network). Wheel SHA-256 not checked against the package index. | - |

Also present in the uv cache: cryptography 50.0.1. Not examined.

## 2. Locked status (uv.lock)

- `uv.lock` (revision 5, `requires-python = "==3.12.*"`) has no `[[package]]` entry for `cryptography`, directly or transitively.
- `grep -i` for `cryptography`, `ed25519`, `nacl`, `cffi` in `uv.lock` and `pyproject.toml`: no matches.
- `pyproject.toml` direct dependencies (8): pydantic, pydantic-settings, httpx, websockets, pyyaml, tenacity, prometheus-client, defusedxml. None pulls cryptography.
- Status: NOT LOCKED. The addition would also bring `cffi` (declared `cffi>=2.0.0` for non-PyPy) and its transitive dependencies.
- The worktree `.venv` has no installed packages (`.venv/lib/python3.12/site-packages/` is empty), so the "installed package" was read from the uv cache copy, copied to a scratch directory and imported with `PYTHONPATH`. Nothing was installed.

## 3. Semantics verified

### 3a. Source read (primary evidence)

- Python wrapper (in wheel): `cryptography/hazmat/primitives/asymmetric/ed25519.py`. `Ed25519PublicKey.from_public_bytes(data)` returns `rust_openssl.ed25519.from_public_bytes(data)`.
- Rust backend (tag 50.0.2): `src/rust/src/backend/ed25519.rs`, function `from_public_bytes`. It calls `openssl::pkey::PKey::public_key_from_raw_bytes(data, Id::ED25519)` and maps any failure to `ValueError("An Ed25519 public key is 32 bytes long")`. The Rust code has no curve-membership check and no canonical-encoding check of its own. Whatever OpenSSL's raw import does is the only validation.
- Rendered docs read: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/. The fetch truncated the `from_public_bytes` section, so this record relies on the Rust source for decode behaviour, not on the docs text.
- Type stub (in wheel): `hazmat/bindings/_rust/openssl/ed25519.pyi` declares `from_public_bytes(data: bytes)` with no documented validation.

### 3b. Behaviour probe (executed, Python 3.12.3, wheel 50.0.2 via PYTHONPATH, no install)

Reference check: an independent RFC 8032 section 5.1.3 decode in pure Python. A value is on-curve when `y < p` (p = 2^255 - 19) and `x^2 = (y^2 - 1) / (d*y^2 + 1)` has a square root mod p.

| Input (32 bytes unless noted) | RFC 8032 decode | cryptography 50.0.2 |
|---|---|---|
| identity `01 00..00` | on-curve | ACCEPT |
| y = 0 | on-curve | ACCEPT |
| base point B (y = 4/5) | on-curve | ACCEPT |
| `ff..ff` (y >= p, non-canonical) | rejected | ACCEPT |
| y = p (non-canonical zero) | rejected | ACCEPT |
| 31 bytes / 33 bytes | n/a | ValueError (length) |
| 4000 random 32-byte strings | 2019 on-curve, 1981 off-curve | ACCEPT 4000 of 4000 |

Result: 1981 of 4000 random 32-byte strings that are NOT points were accepted. 0 on-curve strings were rejected. About half of random strings are off-curve, which matches the note in ONB-06 (REQUIREMENTS.md:47).

Round trip of a generated key (`public_bytes_raw` -> `from_public_bytes`): identical bytes.

`verify()` with an off-curve key raises `InvalidSignature`. That is the signature path, not a decode check, so it does not reject off-curve public keys at load time.

### 3c. Conclusion on semantics

`Ed25519PublicKey.from_public_bytes` is a length check plus OpenSSL raw import. It does NOT:

- reject off-curve encodings,
- reject non-canonical encodings (y >= p),
- check the sign bit for x = 0 (not probed; RFC 8032 requires rejection; any decoder must do it).

Therefore cryptography cannot satisfy ONB-06 "passes an Ed25519 curve-point check" by itself. The check would still need a separately reviewed decoder. A verify-based or load-based trick is not a substitute.

## 4. Reason for the candidate (owner decision, recorded as given)

The owner chose `cryptography` as the Ed25519 point-validation primitive, to be added only after this review (plan 14-06). Context checked here:

- The standard library has no Ed25519.
- `nacl` / PyNaCl is named in `docs/SAFETY_INVARIANTS.md` INV-S-01 and in `docs/MIGRATION_MAP.md` section 2.4 (G-7 `--forbid-imports` list). It is excluded.
- `solders` / `solana` are excluded (INV-S-01; ROADMAP criterion 14).
- base58 decoding already exists with the standard library: `src/pumpgrok/config/sections/core.py` `_base58_decode` and `_is_public_key_text`. No base58 package is needed.

## 5. Known risks

1. Decode gap (blocking): see 3c. ONB-06 semantics are not met by the candidate alone.
2. Signer-import conflict (blocking, needs owner decision): `docs/SAFETY_INVARIANTS.md` INV-S-01 forbids imports of `ed25519` (among others) outside `src/pumpgrok/execution/live/`. `from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey` contains the module name `ed25519`. The enforcing test `tests/safety/test_no_signing_outside_live_stub.py` only bans `solders`/`solana` imports and the symbols `sign`, `send_transaction`, `sendTransaction`, `Keypair`, `Transaction`, `VersionedTransaction`, `Message`; it would not flag this import. The invariant text and its owning test disagree. Per plan 14-06, this conflict must be escalated, not resolved by weakening either requirement.
3. Referenced gate missing: `docs/MIGRATION_MAP.md` (section 2.4) names `ci/gates/check_desk_integrity.py --forbid-imports solders,solana,base58,nacl` and `tests/desk/test_no_signer_imports.py`. Neither flag nor test file exists in this worktree (`ci/gates/check_desk_integrity.py` has no such option; the test file is absent). Not fixed here; noted for the owner.
4. Native dependency footprint: Rust/OpenSSL wheel plus `cffi`. Adds a lock surface.
5. Hazardous-materials module: cryptography's own docs mark Ed25519 as hazmat. The ONB-06 use is public-key only; no private key may enter the desk (rules/pumpgrok-team.mdc clause 1).
6. Artifact integrity: wheel hash not verified against the index; version 50.0.2 is the newest cached, not confirmed as the newest published.
7. Error text is misleading: any failure reads "An Ed25519 public key is 32 bytes long". Callers must not rely on the message.
8. Scope of this review: one wheel, one version, one platform (x86_64 manylinux). No review of the sdist, the OpenSSL build inside the wheel, or the upstream release signing.

## 6. Options for the owner (no choice made here)

A. Keep cryptography out of the lock. Implement the ONB-06 curve-point check as a stdlib decoder (RFC 8032 section 5.1.3, integer arithmetic only) next to `_base58_decode`, with RFC 8032 test vectors and the malformed, non-canonical and off-curve negative vectors. This needs its own independent review as crypto code. It adds no dependency and does not hit INV-S-01.

B. Add cryptography anyway, only if the owner accepts that it does not perform the ONB-06 check. The decoder from option A would still be needed. Cryptography would then only add an unneeded native dependency. Not recommended.

C. Choose another vetted package. It must pass its own legitimacy review and the INV-S-01 / G-7 forbid list. Not identified here.

RISK recommendation: option A. The decision is the owner's.

## 7. Exact command (NOT run; for use only after the owner approves a candidate)

Run only with network access, from the worktree root, after the decision in section 6:

    uv add "cryptography>=50.0.2,<51"

Then `uv lock --check` must show the lock updated with `cryptography` and `cffi`. Nothing has been added to `pyproject.toml` or `uv.lock` by this review.

## 8. Independent-review statement

Self-review by RISK (bot-02-risk), not an external or independent audit: cryptography 50.0.2 is NOT approved as the ONB-06 curve-point primitive because its public-key decode performs no curve-membership or canonical-encoding check, and the INV-S-01 `ed25519` import conflict is unresolved.
