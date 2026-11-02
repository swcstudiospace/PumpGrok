"""The declared-space identity ignores entry order and repeats, and follows entry content."""

from pumpgrok.backtest.manifest import param_set_hash
from pumpgrok.cli.promotion import canonical_space, declared_space_identity
from pumpgrok.core.idempotency import canonical_json

FIVE = {"filter": {"min_unique_buyers": 5}}
SEVEN = {"filter": {"min_unique_buyers": 7}}
NINE = {"filter": {"min_unique_buyers": 9}}


def test_reordering_the_entries_keeps_the_identity() -> None:
    assert declared_space_identity([FIVE, SEVEN]) == declared_space_identity([SEVEN, FIVE])


def test_repeating_an_entry_keeps_the_identity() -> None:
    assert declared_space_identity([FIVE, SEVEN]) == declared_space_identity([FIVE, SEVEN, FIVE])


def test_changing_the_second_entry_changes_the_identity() -> None:
    assert declared_space_identity([FIVE, SEVEN]) != declared_space_identity([FIVE, NINE])


def test_canonical_space_ignores_declaration_order_and_repeats() -> None:
    assert canonical_space([SEVEN, FIVE, SEVEN]) == canonical_space([FIVE, SEVEN])


def test_canonical_space_is_sorted_by_content_hash_with_no_repeats() -> None:
    result = canonical_space([SEVEN, FIVE])
    assert len(result) == 2
    content_hashes = [
        param_set_hash(canonical_json(dict(entry)).encode("utf-8")) for entry in result
    ]
    assert content_hashes == sorted(content_hashes)
