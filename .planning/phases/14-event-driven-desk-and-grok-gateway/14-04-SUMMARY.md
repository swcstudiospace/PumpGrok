# 14-04 Summary: seat event cycles and measurement (EVT-12, GRK-11)

## Done
- Six trading and safety role cycles bound to the reviewed wake matrix through the real dispatcher (`event_cycles.py`): chief, scout, risk, sniper, rug, exit. Commits d9ae936, 53a54de.
- Four auxiliary cycles (whale, signal, journal, shill-never) in `event_cycles_aux.py`: journal rollup on the 300 s timer and on position_closed. Commit 711a4ca.
- Event-mode signal scoring is now per-token and SYNTHETIC (`synthetic_signal_score`, labeled in code and goldens). Not a Grok result. Commit 48dddee.
- Event goldens for smoke-10m, smoke and soak-3d, each from two identical real runs. Legacy pins unchanged. Commit 48dddee.
- Synthetic evidence-50 fixture: 300 raw candidates, 50 admitted by the real prefilter, provenance synthetic. Commit b03f005 (RISK).
- `FixtureManifest` gains an optional `provenance` field (Literal synthetic or recorded, default None; `extra=forbid` kept). Commit 0a0f842 (RISK).
- `scripts/measure_grok_calls.py`: before = raw candidate rows, after = real gateway calls. Exit 0 pass, 1 gate fail, 2 input error. Commits 351556f, 1796110 (CHIEF).
- Synthetic token-facts dataset `soak-3d-tokens`, derived from soak-3d ticks; soak-3d itself is unchanged. Commit 07dc963 (RISK).
- Rug verdict renamed `READABLE` (was `CLEAR`): no rug analysis exists, so `CLEAR` made an unanalyzed claim. Commit 53a54de.

## Verified (merged head e46b369 + 1796110)
- Regression files green, no skips: event_cycles 22, event_cycles_aux 29, golden_hashes 12, journal_rollup 5, event_wake 34, event_mode_run_once 3, measure_grok_calls 13, evidence50 10, soak3d_tokens 8, test_scheduler 7, replay_hash_pin 3, trading_smoke_pin 5, event_drain_parity 3.
- Lint and format clean on changed files; mypy clean on scheduler, fixtures, and the script.
- Gates (evidence-50): `scripts/measure_grok_calls.py --dataset tests/fixtures/replay/evidence-50 --min-candidates 50 --max-ratio 0.2` gives ratio 0.166667, exit 0.
- Gates (soak-3d-tokens): ratio 0.004167, exit 0.
- Full repo gates NOT run yet; they run at Phase 14 close.

## Deviations from the plan (must be read)
- Plan verify names `tests/fixtures/replay/soak-3d`. That dataset has no token facts and cannot produce candidates. The owner chose a synthetic token-facts layer; it is applied to a new derived dataset, `soak-3d-tokens`, because soak-3d is pinned by the multi-day soak tests. The verify command therefore points at `soak-3d-tokens`.
- The soak-3d-tokens ratio is loose: 4,320 raw, 18 admitted, mostly `too_old`. It proves gate mechanics, not a realistic admission rate.
- Event-mode signal scores are synthetic (owner decision), not Grok results. The SIGNAL interface is unchanged.
- The triggering event reaches seat cycles through a ContextVar (`TRIGGER_EVENT` in `supervisor.py`), not through `SeatContext`. A clean fix adds an event field to `SeatContext`; left for later.
- Scout admission fails closed for real events: `token_created` carries no buyer count, and no buyer source exists. Real migrations are not admitted.
- Whale reports BLIND in event mode: no production RPC wiring exists.
- No production bus producer exists for `trade`, `position_opened` or `position_closed`. The journal paths for them are covered only by unit tests.
- `serve` and the CLI do not yet build event-mode cycles (planned in 14-07).
- The `soak-3d` golden pins only the seat trace and seeded ledger (no candidates, so no sniper path).
- RISK's merge included a test-scenario correction in `test_measure_grok_calls.py` (the duplicate row uses a different mint because cooldown now blocks the old same-mint duplicate). The cache-hit assertion is unchanged.
- The `soak-3d` fixture verify (plan) is replaced by `soak-3d-tokens` (see above).
