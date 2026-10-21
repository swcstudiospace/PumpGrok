# No secrets in the image. Every PUMPGROK_* value arrives at run time (compose env_file or -e);
# nothing from .env is copied in (see .dockerignore). Pinned bases: python:3.12-slim, uv 0.13.4.

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PUMPGROK_PROFILE=paper
RUN useradd --system --create-home --home-dir /home/pumpgrok pumpgrok \
 && mkdir -p /app/var \
 && chown pumpgrok:pumpgrok /app/var
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
# Read-only replay input for the default CMD (research Pitfall 5). Only this fixture is copied.
COPY tests/fixtures/replay/smoke /app/tests/fixtures/replay/smoke
USER pumpgrok
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["pumpgrok", "doctor"]
STOPSIGNAL SIGTERM
ENTRYPOINT ["pumpgrok"]
# One skip-only replay cycle, then exit 0 (R50). Ledger output goes to /app/var, the only
# writable path in the image.
CMD ["run", "--mode", "paper", "--once", "--replay", "tests/fixtures/replay/smoke"]
