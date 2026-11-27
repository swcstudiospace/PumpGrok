"""Entry checks reject unsafe mints and fail closed on missing data (RSK-05, S-E1)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, cast

import pytest

from pumpgrok.config.settings import SafetyThresholds
from pumpgrok.risk.entry_checks import (
    EntryEvidence,
    MintLists,
    default_mint_lists_path,
    evaluate_entry,
    load_mint_lists,
)
from pumpgrok.tools.safety.checks import REQUIRED_IDS, CheckId, CheckResult

MINT = "Mint1111111111111111111111111111111111111"
THRESHOLDS = SafetyThresholds()
EMPTY_LISTS = MintLists(deny=frozenset(), warn=frozenset())


def _row(check_id: str, status: str = "pass") -> CheckResult:
    return CheckResult(
        id=cast(CheckId, check_id),
        status=cast(Any, status),
        reason=f"{check_id} {status}",
    )


def _clean_checks() -> list[CheckResult]:
    return [_row(check_id) for check_id in sorted(REQUIRED_IDS)]


def _evidence(**overrides: Any) -> EntryEvidence:
    fields: dict[str, Any] = {
        "mint": MINT,
        "authorities": {"has_mint_authority": False, "has_freeze_authority": False},
        "extensions": [],
        "top10_share": 0.10,
        "checks": _clean_checks(),
    }
    fields.update(overrides)
    return EntryEvidence(**fields)


def _verdict(
    evidence: EntryEvidence,
    lists: MintLists = EMPTY_LISTS,
    *,
    holder_blind_advisory: bool = False,
) -> Any:
    return evaluate_entry(evidence, lists, THRESHOLDS, holder_blind_advisory=holder_blind_advisory)


def test_clean_mint_passes_without_warnings() -> None:
    verdict = _verdict(_evidence())
    assert verdict.ok
    assert verdict.reasons == ()
    assert verdict.warnings == ()


def test_live_mint_authority_is_rejected() -> None:
    verdict = _verdict(
        _evidence(authorities={"has_mint_authority": True, "has_freeze_authority": False})
    )
    assert not verdict.ok
    assert any("mint authority is live" in reason for reason in verdict.reasons)


def test_live_freeze_authority_is_rejected() -> None:
    verdict = _verdict(
        _evidence(authorities={"has_mint_authority": False, "has_freeze_authority": True})
    )
    assert not verdict.ok
    assert any("freeze authority is live" in reason for reason in verdict.reasons)


@pytest.mark.parametrize("missing", ["has_mint_authority", "has_freeze_authority"])
def test_missing_authority_field_is_rejected(missing: str) -> None:
    """S-E1: an absent authority field rejects instead of passing as revoked."""
    authorities = {"has_mint_authority": False, "has_freeze_authority": False}
    del authorities[missing]
    verdict = _verdict(_evidence(authorities=authorities))
    assert not verdict.ok
    assert any(f"{missing} missing" in reason for reason in verdict.reasons)


def test_missing_authority_metadata_is_rejected() -> None:
    verdict = _verdict(_evidence(authorities=None))
    assert not verdict.ok
    assert "authority metadata missing" in verdict.reasons


@pytest.mark.parametrize(
    "entry",
    [
        "PermanentDelegate",
        "transferHook",
        "nonTransferable",
        "permanent-delegate",
        "{'extension': 'transferHook', 'state': {}}",
    ],
)
def test_rejected_token2022_extension_is_rejected(entry: str) -> None:
    verdict = _verdict(_evidence(extensions=[entry]))
    assert not verdict.ok
    assert any("is rejected" in reason for reason in verdict.reasons)


def test_other_token2022_extension_only_warns() -> None:
    verdict = _verdict(_evidence(extensions=["metadataPointer"]))
    assert verdict.ok
    assert len(verdict.warnings) == 1
    assert "metadataPointer" in verdict.warnings[0]


def test_top10_at_fail_threshold_is_rejected() -> None:
    verdict = _verdict(_evidence(top10_share=0.25))
    assert not verdict.ok
    assert any("top-10 holders own 25.00%" in reason for reason in verdict.reasons)


def test_top10_just_below_fail_threshold_warns_only() -> None:
    verdict = _verdict(_evidence(top10_share=0.2499))
    assert verdict.ok
    assert len(verdict.warnings) == 1


def test_top10_at_warn_threshold_warns_without_rejecting() -> None:
    verdict = _verdict(_evidence(top10_share=0.20))
    assert verdict.ok
    assert any("top-10 holders own 20.00%" in warning for warning in verdict.warnings)


def test_top10_below_warn_threshold_is_silent() -> None:
    verdict = _verdict(_evidence(top10_share=0.199))
    assert verdict.ok
    assert verdict.warnings == ()


def test_blind_required_check_is_rejected() -> None:
    checks = [row for row in _clean_checks() if row.id != "lp_status"]
    checks.append(_row("lp_status", "blind"))
    verdict = _verdict(_evidence(checks=checks))
    assert not verdict.ok
    assert "required check lp_status is blind" in verdict.reasons


def test_blind_advisory_check_does_not_reject() -> None:
    """Advisory ids are blind by construction and never reject on their own."""
    verdict = _verdict(_evidence(checks=[*_clean_checks(), _row("transfer_tax", "blind")]))
    assert verdict.ok


@pytest.mark.parametrize("holder", ["top10_concentration", "deployer_history"])
def test_blind_holder_pair_warns_while_no_paid_rpc_recorded(holder: str) -> None:
    """Amendment 2026-10-25: a BLIND SAFE-4/SAFE-8 row warns and does not reject."""
    checks = [row for row in _clean_checks() if row.id != holder]
    checks.append(_row(holder, "blind"))
    verdict = _verdict(_evidence(checks=checks), holder_blind_advisory=True)
    assert verdict.ok
    assert any(f"required check {holder} is blind" in warning for warning in verdict.warnings)


@pytest.mark.parametrize("holder", ["top10_concentration", "deployer_history"])
def test_blind_holder_pair_rejects_once_paid_rpc_recorded(holder: str) -> None:
    checks = [row for row in _clean_checks() if row.id != holder]
    checks.append(_row(holder, "blind"))
    verdict = _verdict(_evidence(checks=checks), holder_blind_advisory=False)
    assert not verdict.ok
    assert f"required check {holder} is blind" in verdict.reasons


def test_absent_holder_row_rejects_even_while_advisory() -> None:
    """Advisory only covers a BLIND row; a missing required row still rejects."""
    checks = [row for row in _clean_checks() if row.id != "top10_concentration"]
    verdict = _verdict(_evidence(checks=checks), holder_blind_advisory=True)
    assert not verdict.ok
    assert "required check top10_concentration has no result" in verdict.reasons


def test_blind_non_holder_required_check_rejects_while_advisory() -> None:
    """The advisory carve-out is the holder pair only; other required blinds reject."""
    checks = [row for row in _clean_checks() if row.id != "lp_status"]
    checks.append(_row("lp_status", "blind"))
    verdict = _verdict(_evidence(checks=checks), holder_blind_advisory=True)
    assert not verdict.ok
    assert "required check lp_status is blind" in verdict.reasons


@pytest.mark.parametrize("missing", sorted(REQUIRED_IDS))
def test_missing_required_result_is_rejected(missing: str) -> None:
    """S-E1: a REQUIRED_IDS id with no result rejects the mint."""
    checks = [row for row in _clean_checks() if row.id != missing]
    verdict = _verdict(_evidence(checks=checks))
    assert not verdict.ok
    assert f"required check {missing} has no result" in verdict.reasons


def test_missing_safety_report_is_rejected() -> None:
    verdict = _verdict(_evidence(checks=None))
    assert not verdict.ok
    assert "safety report missing" in verdict.reasons


def test_duplicate_required_result_is_rejected() -> None:
    checks = [*_clean_checks(), _row("lp_status")]
    verdict = _verdict(_evidence(checks=checks))
    assert not verdict.ok
    assert "duplicate result for check lp_status" in verdict.reasons


def test_missing_extension_data_is_rejected() -> None:
    verdict = _verdict(_evidence(extensions=None))
    assert not verdict.ok
    assert "token-2022 extension data missing" in verdict.reasons


def test_missing_top10_share_is_rejected() -> None:
    verdict = _verdict(_evidence(top10_share=None))
    assert not verdict.ok
    assert "top-10 concentration missing" in verdict.reasons


def test_non_numeric_top10_share_is_rejected() -> None:
    verdict = _verdict(_evidence(top10_share=cast(Any, "not-a-number")))
    assert not verdict.ok
    assert "top-10 concentration is not a number" in verdict.reasons


def test_negative_top10_share_is_rejected() -> None:
    verdict = _verdict(_evidence(top10_share=-0.1))
    assert not verdict.ok
    assert "top-10 concentration is not a valid share" in verdict.reasons


def test_deny_listed_mint_is_rejected() -> None:
    lists = MintLists(deny=frozenset({MINT}), warn=frozenset())
    verdict = _verdict(_evidence(), lists)
    assert not verdict.ok
    assert "mint is on the deny list" in verdict.reasons


def test_warn_listed_mint_warns_without_rejecting() -> None:
    lists = MintLists(deny=frozenset(), warn=frozenset({MINT}))
    verdict = _verdict(_evidence(), lists)
    assert verdict.ok
    assert "mint is on the warn list" in verdict.warnings


def test_shipped_mint_lists_parse_with_tomllib_and_are_empty() -> None:
    with open(default_mint_lists_path(), "rb") as handle:
        raw = tomllib.load(handle)
    assert raw == {"deny": [], "warn": []}
    assert load_mint_lists() == EMPTY_LISTS


def test_missing_mint_lists_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_mint_lists(tmp_path / "absent.toml")


def test_mint_lists_with_unknown_key_raises(tmp_path: Path) -> None:
    path = tmp_path / "mint_lists.toml"
    path.write_text("deny = []\nwarn = []\nreject = []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected exactly the keys"):
        load_mint_lists(path)


def test_mint_lists_with_non_string_entry_raises(tmp_path: Path) -> None:
    path = tmp_path / "mint_lists.toml"
    path.write_text("deny = [1]\nwarn = []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty mint strings"):
        load_mint_lists(path)


def test_holder_blind_advisory_leaves_verdict_unchanged() -> None:
    """T3: the advisory flag changes no verdict that has no BLIND holder row."""
    live_mint = _evidence(authorities={"has_mint_authority": True, "has_freeze_authority": False})
    for evidence in (_evidence(), live_mint):
        advisory = _verdict(evidence, holder_blind_advisory=True)
        strict = _verdict(evidence, holder_blind_advisory=False)
        assert advisory == strict


def test_omitting_holder_blind_advisory_raises_type_error() -> None:
    with pytest.raises(TypeError):
        evaluate_entry(_evidence(), EMPTY_LISTS, THRESHOLDS)  # type: ignore[call-arg]
