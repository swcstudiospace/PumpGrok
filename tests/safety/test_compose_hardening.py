"""Compose hardening: every service runs with a read-only root filesystem, a tmpfs /tmp, all
capabilities dropped and no-new-privileges, and no service is privileged.

The test parses docker-compose.yml only; no container is started. The service topology is pinned
so hardening cannot quietly add or remove a service.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"
EXPECTED_SERVICES = ("desk-gateway", "pumpgrok")


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text())["services"]


def test_service_topology_is_pinned():
    assert tuple(sorted(_services())) == EXPECTED_SERVICES


@pytest.mark.parametrize("name", EXPECTED_SERVICES)
def test_root_filesystem_is_read_only(name):
    assert _services()[name].get("read_only") is True, name


@pytest.mark.parametrize("name", EXPECTED_SERVICES)
def test_tmpfs_provides_a_writable_tmp(name):
    mounts = _services()[name].get("tmpfs") or []
    assert any(str(mount).split(":", 1)[0] == "/tmp" for mount in mounts), name


@pytest.mark.parametrize("name", EXPECTED_SERVICES)
def test_every_capability_is_dropped(name):
    assert _services()[name].get("cap_drop") == ["ALL"], name


@pytest.mark.parametrize("name", EXPECTED_SERVICES)
def test_no_new_privileges_is_set(name):
    assert "no-new-privileges:true" in (_services()[name].get("security_opt") or []), name


@pytest.mark.parametrize("name", EXPECTED_SERVICES)
def test_service_is_not_privileged(name):
    assert _services()[name].get("privileged") is not True, name
