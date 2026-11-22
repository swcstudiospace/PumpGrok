"""HOST-13: secrets as Docker secrets under /run/secrets; no env_file, no secret env."""

from __future__ import annotations

from pathlib import Path

import yaml


def _compose() -> dict:
    return yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))


def test_no_env_file_entry() -> None:
    for name, svc in _compose()["services"].items():
        assert "env_file" not in svc, name


def test_secrets_mounted_under_run_secrets() -> None:
    data = _compose()
    assert "secrets" in data
    for name, svc in data["services"].items():
        assert "secrets" in svc, name


def test_no_secret_valued_environment_entry() -> None:
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "token" not in lowered or "desK_GATEWAY_TOKEN" not in text
    for name, svc in _compose()["services"].items():
        for key in svc.get("environment", {}):
            assert "token" not in str(key).lower(), (name, key)
            assert "secret" not in str(key).lower(), (name, key)
