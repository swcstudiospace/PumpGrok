# Start and stop runbook

Starting and stopping the desk under compose. The one-shot replay cycle is the health proof after every start.

## Quick start

```bash
docker compose up --build pumpgrok
docker compose ps
docker compose logs pumpgrok
docker compose run --rm pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
docker compose down
```

`up --build` starts the single `pumpgrok` service. `ps` and `logs` confirm it is up and serving. The one-shot replay proves the running image still completes a cycle. `down` stops it.

## What start and stop do

- `up` builds the multi-stage image and starts one `pumpgrok` service with `PUMPGROK_PROFILE=paper`, the loopback health port, and `./var` bound to `/app/var`.
- The service keeps no restart policy for one-shot runs; a long-running serve form uses `unless-stopped`.
- `down` stops the container. Ledger and logs persist in the host `./var/` bind mount.

## Rules that apply to start and stop

- The container runs as the non-root `pumpgrok` user, while a host bind mount is owned by the host user. On Linux hosts, make the host `./var/` directory writable by the container user before the first `up`; do not paper over this with a compose user mapping, which changes the security posture.
- Keep the image build hermetic: the build copies `.python-version`, `pyproject.toml`, `uv.lock`, and `src/` only. Runtime secrets arrive via `.env`, never via build args.
- After every start or rebuild, run the one-shot replay cycle and `pumpgrok doctor` before calling the desk healthy.
- Probe health with `pumpgrok doctor` and the `/healthz` endpoint. Never probe endpoints with ad-hoc network tools.

## References

- Container build: `Dockerfile`
- Service definition: `docker-compose.yml`
- Subsystem health: `pumpgrok doctor`
- Engine proof cycle: `docs/runbooks/engine.md`
