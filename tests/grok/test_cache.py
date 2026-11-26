"""Cache stores admitted results; TTL expiry; fallback never stored."""

from pumpgrok.grok.cache import Cache
from pumpgrok.replay.clock import FixtureClock


def test_cache_hit_within_ttl() -> None:
    clock = FixtureClock()
    cache = Cache(clock=clock)
    cache.set("k1", '{"ok": 1}', "scout")
    assert cache.get("k1", "scout") == '{"ok": 1}'


def test_cache_expires_after_agent_ttl() -> None:
    clock = FixtureClock()
    cache = Cache(clock=clock)
    cache.set("k1", '{"ok": 1}', "signal")
    clock.advance_to(120.0)
    assert cache.get("k1", "signal") is None


def test_fallback_results_are_never_cached() -> None:
    clock = FixtureClock()
    cache = Cache(clock=clock)
    cache.set("k1", '{"ok": 1}', "scout", is_fallback=True)
    assert cache.get("k1", "scout") is None
    assert len(cache) == 0


def test_cache_miss_returns_none() -> None:
    cache = Cache(clock=FixtureClock())
    assert cache.get("absent", "scout") is None
