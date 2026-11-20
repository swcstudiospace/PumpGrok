"""Seat manifest loading raises typed errors and never swallows a catch-all (QLT-06, 11-04).

A malformed roster entry is reported as ValueError naming the file, with the underlying
key or pydantic error chained as its cause. Any other failure propagates unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import pumpgrok.core.manifests as manifests
from pumpgrok.core.manifests import load_bot_manifests

CORE_ROSTER = "tools:\n  - name: state.read\n    side_effect: read\n"


def _contracts(tmp_path: Path, bot_doc: str) -> Path:
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "_core.yaml").write_text(CORE_ROSTER, encoding="utf-8")
    (contracts / "bot-01-test.yaml").write_text(bot_doc, encoding="utf-8")
    return contracts


def test_unknown_side_effect_is_a_value_error_with_the_pydantic_cause(tmp_path: Path) -> None:
    contracts = _contracts(
        tmp_path,
        "seat: bot-01-test\n"
        "manifest:\n  id: bot-01-test\n"
        "tools:\n  - name: exec.place\n    side_effect: not-a-class\n",
    )
    with pytest.raises(ValueError, match="needs a valid side_effect") as info:
        load_bot_manifests(contracts)
    assert info.value.__cause__ is not None


def test_missing_side_effect_is_a_value_error_with_the_key_cause(tmp_path: Path) -> None:
    contracts = _contracts(
        tmp_path,
        "seat: bot-01-test\nmanifest:\n  id: bot-01-test\ntools:\n  - name: exec.place\n",
    )
    with pytest.raises(ValueError, match="needs a valid side_effect") as info:
        load_bot_manifests(contracts)
    assert isinstance(info.value.__cause__, KeyError)


def test_manifest_block_that_does_not_validate_names_the_file(tmp_path: Path) -> None:
    contracts = _contracts(
        tmp_path,
        "seat: bot-01-test\nmanifest:\n  id: bot-01-test\n"
        "tools:\n  - name: exec.place\n    side_effect: read\n",
    )
    with pytest.raises(ValueError, match=r"bot-01-test\.yaml: manifest does not validate"):
        load_bot_manifests(contracts)


def test_grant_failure_outside_the_typed_errors_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contracts = _contracts(
        tmp_path,
        "seat: bot-01-test\nmanifest:\n  id: bot-01-test\n"
        "tools:\n  - name: exec.place\n    side_effect: read\n",
    )

    def broken_grant(**_: object) -> None:
        raise RuntimeError("grant backend unavailable")

    monkeypatch.setattr(manifests, "ToolGrant", broken_grant)
    with pytest.raises(RuntimeError, match="grant backend unavailable"):
        load_bot_manifests(contracts)


def test_manifest_failure_outside_the_typed_errors_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contracts = _contracts(
        tmp_path,
        "seat: bot-01-test\nmanifest:\n  id: bot-01-test\n"
        "tools:\n  - name: exec.place\n    side_effect: read\n",
    )

    def broken_validate(_: object, _data: object) -> None:
        raise RuntimeError("validator crashed")

    monkeypatch.setattr(manifests.BotManifest, "model_validate", classmethod(broken_validate))
    with pytest.raises(RuntimeError, match="validator crashed"):
        load_bot_manifests(contracts)
