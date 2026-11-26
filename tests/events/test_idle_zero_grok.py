"""24 virtual hours with zero source events make zero Grok calls."""

from pumpgrok.events.idle import HOURS, run_idle_grok_calls


def test_idle_desk_is_silent() -> None:
    assert HOURS == 24
    assert run_idle_grok_calls() == 0


def test_idle_calls_are_zero_across_reruns() -> None:
    assert run_idle_grok_calls() == 0
    assert run_idle_grok_calls() == 0
