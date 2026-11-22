# Phase 19 Plan 06: Hosted Runtime Edge Summary

**Phase:** 19-observability · **Plan:** 06
**Status:** complete
**Date:** 2026-11-22

## What was built

- Gateway bind/tokens (HOST-09/10): `services/desk-gateway/src/desk_gateway/config.py` gains `validate_gateway_bind` (refuses non-loopback without `DESK_GATEWAY_TLS`/`DESK_GATEWAY_REVERSE_PROXY`) and `validate_tokens` (32-byte floor, equal-token refusal); `__main__.py` validates before serving, exiting non-zero.
- Health bind/timeout (HOST-11/12): `health_server.py` defaults to loopback, `/metrics` is 401 without a token beyond loopback, and incomplete requests close within the read timeout (default 5 s).
- Replay label (HOST-15): every `/livez`, `/readyz`, `/metrics` body carries server-set `replay_demo: true`, `ledger_source: replay`; no override knob exists.
- Live root (HOST-16): `run --live-paper` builds the Phase 15 live-data paper composition root (paper only, gated on `PUMPGROK_OD04_PROBE_REVIEW=approved`); compose default runs it; the fixture command lives only in the `replay` profile (`pumpgrok-replay` service).
- Secrets/pins (HOST-13/14): compose uses Docker secrets (`secrets: [pumpgrok_env]`, `/run/secrets`), no `env_file`, no secret-valued env; Dockerfile bases pinned by real sha256 digests (verified via `docker buildx imagetools inspect`).

## Gates

`uv run pytest tests/hosted ci/tests/test_compose_docker_secrets.py ci/tests/test_image_digest_pins.py` → 51 passed.

## Deviations

- HOST-14 compose `image: pumpgrok:local` entries are locally built from the digest-pinned Dockerfile (pinned transitively); the pin test asserts digest pinning for registry refs and accepts local builds. Building and pinning the built image by digest would freeze CI rebuilds.
- `services/desk-gateway/src/gateway.py` (plan path) does not exist; the guards live in the actual `desk_gateway/config.py` + `__main__.py`.

## Requirements

HOST-09 through HOST-16.
