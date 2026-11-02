"""The declared-space identity ignores entry order and repeats, and follows entry content."""

from pumpgrok.cli.promotion import declared_space_identity

FIVE = {"filter": {"min_unique_buyers": 5}}
SEVEN = {"filter": {"min_unique_buyers": 7}}
NINE = {"filter": {"min_unique_buyers": 9}}


def test_reordering_the_entries_keeps_the_identity() -> None:
    assert declared_space_identity([FIVE, SEVEN]) == declared_space_identity([SEVEN, FIVE])


def test_repeating_an_entry_keeps_the_identity() -> None:
    assert declared_space_identity([FIVE, SEVEN]) == declared_space_identity([FIVE, SEVEN, FIVE])


def test_changing_the_second_entry_changes_the_identity() -> None:
    assert declared_space_identity([FIVE, SEVEN]) != declared_space_identity([FIVE, NINE])
