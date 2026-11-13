# 14-01 baseline and rulings

## Baseline (precondition)

Captured by CHIEF on the clean Phase 14 start tree 53c9ccc, before any product edit:
- `pumpgrok verify --fixture smoke-10m`, run twice: both `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`, equal to the pin.
- `tests/replay/test_replay_hash_pin.py` and `tests/replay/test_trading_smoke_pin.py`: 8 passed.
- Attribution: CHIEF. Independent JOURNAL attestation is NOT recorded; this is an open item for the owner.

## Rulings

1. Breaker: REPO source, 14-CONTEXT.md G-03. Three consecutive failures set llm_available false; a 60 s Clock cooldown; one half-open probe. This supersedes the "3 failures in 60 s" wording in the decisions record. Recorded as the owner-consistent form.
2. Cache key input fields and SANITIZER_VERSION: RECOMMENDED. Use the field set of `canonical_request_hash` in src/pumpgrok/replay/recorder.py (repo source) so the live key matches the replay key. SANITIZER_VERSION = "1", bumped on any change to the sanitizer.
3. Test file list: widen the RISK test list to include tests/grok/test_cache_key_payload.py, tests/grok/test_coalesce.py and tests/grok/test_budget.py (the plan names them; GRK-03 and GRK-04 need them).
4. min_prerank scale: unchanged; still needs RISK confirmation before use.
