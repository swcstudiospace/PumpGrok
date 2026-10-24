"""Serve the desk gateway: ``python -m desk_gateway`` (TOOL-010, FOUND-003, G4).

Settings come from the same load path as the CLI (``PUMPGROK_PROFILE`` overlay,
``PUMPGROK_CONFIG`` operator TOML, ``PUMPGROK_*`` environment), so the registry is built from
the operator's configuration. Process settings come from the environment:

- ``DESK_GATEWAY_HOST`` (default ``127.0.0.1``; the container sets ``0.0.0.0``)
- ``DESK_GATEWAY_PORT`` (default ``8787``)
- ``DESK_GATEWAY_DATA_DIR`` (default ``var/desk``, the desk's operational directory that holds
  the kill latch and the ledger)
- ``DESK_GATEWAY_REPO_ROOT`` (default: the checkout this module lives in)

Per-seat bearer tokens come from ``DESK_GATEWAY_TOKEN_<SHORT>``. Exit codes: 0 after a clean
stop, 1 for bad configuration, 3 when live mode is requested (the CLI's live exit code).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from desk_gateway.config import GatewayConfig, load_tokens
from desk_gateway.server import GatewayRefusedError, close_server, create_server
from pumpgrok.config.settings import ConfigError, current_profile, load_settings
from pumpgrok.contracts.projection import default_contracts_dir, short_to_seat
from pumpgrok.ledger.paths import DESK_DATA_DIR, PAPER_LEDGER_PATH
from pumpgrok.logging.json import setup_logging
from pumpgrok.tools.notify.telegram import read_telegram_token

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_LIVE = 3

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
MAX_PORT = 65535
DEFAULT_DATA_DIR = DESK_DATA_DIR

log = logging.getLogger("desk_gateway")


def _say(message: str) -> None:
    sys.stderr.write(f"desk-gateway: {message}\n")
    sys.stderr.flush()


def _port(raw: str | None) -> int:
    text = (raw or "").strip() or str(DEFAULT_PORT)
    try:
        port = int(text)
    except ValueError:
        raise ValueError(
            f"DESK_GATEWAY_PORT must be an integer 1-{MAX_PORT}, got {text!r}"
        ) from None
    if not 1 <= port <= MAX_PORT:
        raise ValueError(f"DESK_GATEWAY_PORT must be an integer 1-{MAX_PORT}, got {port}")
    return port


def main() -> int:
    """Load settings, build the registry from them, and serve until interrupted."""
    try:
        settings = load_settings()
    except ConfigError as exc:
        _say(str(exc))
        return EXIT_CONFIG
    setup_logging(mode=settings.effective_mode, profile=current_profile())
    try:
        port = _port(os.environ.get("DESK_GATEWAY_PORT"))
    except ValueError as exc:
        _say(str(exc))
        return EXIT_CONFIG
    host = os.environ.get("DESK_GATEWAY_HOST", "").strip() or DEFAULT_HOST
    # Anchored to the working directory the target runs from (the repo root), so the gateway
    # reads and writes the same var/ as the CLI, the reports and the kill latch.
    desk_root = Path.cwd()
    data_dir = desk_root / (os.environ.get("DESK_GATEWAY_DATA_DIR", "").strip() or DEFAULT_DATA_DIR)
    default_root = Path(__file__).resolve().parents[4]
    repo_root = Path(os.environ.get("DESK_GATEWAY_REPO_ROOT", "").strip() or default_root)
    contracts_dir = default_contracts_dir()
    shorts = sorted(short_to_seat(contracts_dir).keys())
    tokens = load_tokens(shorts)
    if not tokens:
        log.warning("no DESK_GATEWAY_TOKEN_<SHORT> configured: every seat answers 503")
    config = GatewayConfig(
        host=host,
        port=port,
        contracts_dir=contracts_dir,
        data_dir=data_dir,
        repo_root=repo_root,
        tokens=tokens,
        ledger_path=desk_root / PAPER_LEDGER_PATH,
        telegram_token=read_telegram_token(),
    )
    try:
        server = create_server(config, settings=settings)
    except GatewayRefusedError as exc:
        _say(str(exc))
        return EXIT_LIVE
    except OSError as exc:
        _say(f"cannot bind {host}:{port}: {exc.strerror or exc}")
        return EXIT_CONFIG
    _say(f"serving on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        close_server(server)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
