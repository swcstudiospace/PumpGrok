# Recorder runbook (v4)

Seal a recorded dataset from a replay source.

```bash
uv run pumpgrok run --mode paper --record my-dataset --replay tests/fixtures/replay/smoke
```

The sealed output passes `load_dataset` unchanged. `--record` is implemented; `--duration` is not and exits `EXIT_NOT_IMPLEMENTED`.

```bash
uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
```
