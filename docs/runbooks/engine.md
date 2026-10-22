# Engine runbook

How the paper engine turns one replay dataset into one auditable decision. Read this before touching engine code or replay fixtures.

## Quick start

```bash
uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
uv run pumpgrok verify --fixture smoke
uv run pumpgrok doctor
```

The first command runs one engine cycle on recorded fixture data and prints the decision line. The second replays the same dataset into its canonical replay ledger and verifies the hash chain. The third confirms every subsystem still reports healthy.

## What the engine does

- Reads one recorded dataset from `tests/fixtures/replay/<name>/` (event log plus fixture manifest with digests).
- Runs a single paper cycle: market snapshot, scoring, and at most one engine decision (`skip` or `buy`).
- Appends one `JournalNote` to the replay ledger and verifies the chain before exiting 0.
- Uses only recorded data. There is no live network on the replay path; missing fixture records fail loudly instead of falling back.

## Rules that apply to the engine

- Replay datasets are read-only inputs. Never edit a fixture to make a run pass; regenerate it from its generator with its recorded seed.
- Effective mode for engine work is `paper`. `run --mode live` is refused by the live gate (exit 3); see `go_live.md`.
- Time comes from the injected `Clock`, never wall time. Engine code must not read wall time or sleep on a real loop.
- Money is integer lamports and token base units. Ratios use `Decimal` only at the boundary and never enter the ledger as floats.

## References

- Replay runner: `src/pumpgrok/replay/`
- Paper adapter: `src/pumpgrok/execution/paper_adapter.py`
- Live gate (why live refuses): `docs/runbooks/go_live.md`
- Fixture loader and digest check: `src/pumpgrok/replay/`
