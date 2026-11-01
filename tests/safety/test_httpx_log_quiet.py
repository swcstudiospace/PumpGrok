"""httpx and httpcore INFO request lines never reach the log sink; warnings still do.

The synthetic secret rides in a key parameter that the value-based redactor does not match, so
the sink must stay free of it because the request line is dropped, not because it was masked.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator

import pytest

from pumpgrok.logging import setup_logging

SECRET = "synthetic-key-7f3a9c2e1b8d"  # pragma: allowlist secret: synthetic  # gitleaks:allow
REQUEST_URL = f"https://rpc.example.org/?token={SECRET}"
THIRD_PARTY_LOGGERS = ("httpx", "httpcore")


@pytest.fixture
def restored_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers = list(root.handlers)
    root_level = root.level
    levels = {name: logging.getLogger(name).level for name in THIRD_PARTY_LOGGERS}
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(root_level)
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)


@pytest.mark.parametrize("name", THIRD_PARTY_LOGGERS)
def test_request_info_line_with_secret_url_is_not_written(
    restored_logging: None, name: str
) -> None:
    buffer = io.StringIO()
    setup_logging(mode="paper", profile="paper", environ={}, stream=buffer)
    logging.getLogger(name).info('HTTP Request: GET %s "HTTP/1.1 200 OK"', REQUEST_URL)
    assert SECRET not in buffer.getvalue()


@pytest.mark.parametrize("name", THIRD_PARTY_LOGGERS)
def test_third_party_warning_still_reaches_the_sink(restored_logging: None, name: str) -> None:
    buffer = io.StringIO()
    setup_logging(mode="paper", profile="paper", environ={}, stream=buffer)
    logging.getLogger(name).warning("connection retried")
    assert "connection retried" in buffer.getvalue()
