"""Inventory lists every operator input and is snapshot-pinned."""

from pumpgrok.onboarding.inventory import INVENTORY, inventory_snapshot_hash


def test_inventory_covers_five_inputs() -> None:
    names = {spec.name for spec in INVENTORY}
    assert names == {
        "xai_api_key",
        "wallet_public_address",
        "rpc_endpoint",
        "seat_tool_access",
        "hmac_confirmation_key",
    }


def test_snapshot_hash_is_stable() -> None:
    assert inventory_snapshot_hash() == inventory_snapshot_hash()
    assert len(inventory_snapshot_hash()) == 64


def test_modes_are_classified() -> None:
    by_name = {spec.name: spec for spec in INVENTORY}
    assert by_name["wallet_public_address"].kind_for("paper") == "not-read"
    assert by_name["wallet_public_address"].kind_for("live") == "required"
    assert by_name["hmac_confirmation_key"].kind_for("live") == "forbidden"
    assert by_name["xai_api_key"].kind_for("paper") == "required"
    assert by_name["rpc_endpoint"].kind_for("paper") == "optional"
