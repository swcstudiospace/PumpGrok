"""Уведомления: выключены по умолчанию, торговле не мешают, не спамят."""

import asyncio

import httpx

from src.alerts import KNOWN_EVENTS, Notifier
from src.models import AlertsConfig, Config


def collector() -> tuple[list[dict], httpx.AsyncClient]:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen.append({"url": str(request.url), **json.loads(request.content)})
        return httpx.Response(204)

    return seen, httpx.AsyncClient(transport=httpx.MockTransport(handler))


def config(**overrides) -> AlertsConfig:
    base = {"webhook_url": "https://hooks.example/секретный-токен", "max_per_minute": 20}
    base.update(overrides)
    return AlertsConfig(**base)


# --- выключено по умолчанию ----------------------------------------------


def test_disabled_without_url():
    notifier = Notifier(AlertsConfig())
    assert not notifier.enabled
    assert notifier.notify("buy", "куплено") is None


def test_blank_url_counts_as_disabled():
    assert not Notifier(AlertsConfig(webhook_url="   ")).enabled


def test_default_config_is_silent():
    assert not Notifier(Config().alerts).enabled


# --- отправка -------------------------------------------------------------


async def test_sends_configured_event():
    seen, client = collector()
    notifier = Notifier(config(events=["buy"]), client)
    task = notifier.notify("buy", "куплен CAT на 0.4 SOL", mint="M1", score=0.8)
    assert task is not None
    await task

    assert len(seen) == 1
    assert seen[0]["event"] == "buy"
    assert "куплен CAT" in seen[0]["text"]
    assert seen[0]["content"] == seen[0]["text"]     # Discord читает content
    assert seen[0]["fields"]["mint"] == "M1"
    assert notifier.sent == 1


async def test_event_not_in_list_is_skipped():
    seen, client = collector()
    notifier = Notifier(config(events=["buy"]), client)
    assert notifier.notify("close", "закрыто") is None
    await notifier.aclose()
    assert seen == []


async def test_every_known_event_can_be_configured():
    seen, client = collector()
    notifier = Notifier(config(events=list(KNOWN_EVENTS), max_per_minute=100), client)
    for event in KNOWN_EVENTS:
        notifier.notify(event, f"событие {event}")
    await notifier.aclose()
    assert {r["event"] for r in seen} == set(KNOWN_EVENTS)


# --- не мешает торговле ---------------------------------------------------


async def test_network_failure_is_swallowed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("сети нет")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = Notifier(config(events=["buy"]), client)
    await notifier.notify("buy", "куплено")          # исключение наружу не идёт
    assert notifier.failed == 1
    assert notifier.sent == 0


async def test_http_error_is_counted_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="упало")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = Notifier(config(events=["buy"]), client)
    await notifier.notify("buy", "куплено")
    assert notifier.failed == 1


async def test_notify_does_not_block_caller():
    """Отправка уходит в фон: вызывающий не ждёт сеть."""
    started = asyncio.Event()

    async def slow(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(0.05)
        return httpx.Response(204)

    client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    notifier = Notifier(config(events=["buy"]), client)
    task = notifier.notify("buy", "куплено")
    assert not started.is_set()                      # вернулись до похода в сеть
    await task
    assert notifier.sent == 1


# --- не спамит ------------------------------------------------------------


async def test_rate_limit_drops_the_excess():
    seen, client = collector()
    notifier = Notifier(config(events=["buy"], max_per_minute=3), client)
    for index in range(10):
        notifier.notify("buy", f"токен {index}")
    await notifier.aclose()

    assert len(seen) == 3
    assert notifier.dropped == 7


async def test_window_is_sliding(monkeypatch):
    import src.alerts as alerts_module

    clock = {"now": 1000.0}
    monkeypatch.setattr(alerts_module.time, "monotonic", lambda: clock["now"])

    seen, client = collector()
    notifier = Notifier(config(events=["buy"], max_per_minute=2), client)
    notifier.notify("buy", "1")
    notifier.notify("buy", "2")
    assert notifier.notify("buy", "3") is None

    clock["now"] += 61.0                             # минута прошла
    assert notifier.notify("buy", "4") is not None
    await notifier.aclose()
    assert len(seen) == 3


# --- секреты --------------------------------------------------------------


async def test_url_never_appears_in_logs(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = Notifier(config(events=["buy"]), client)
    with caplog.at_level("WARNING"):
        await notifier.notify("buy", "куплено")
    assert "секретный-токен" not in caplog.text
    assert "403" in caplog.text


def test_url_not_in_repr():
    assert "секретный-токен" not in repr(config())


# --- завершение -----------------------------------------------------------


async def test_aclose_waits_for_pending():
    seen, client = collector()
    notifier = Notifier(config(events=["buy"]), client)
    notifier.notify("buy", "последнее перед остановкой")
    await notifier.aclose()
    assert len(seen) == 1


async def test_aclose_does_not_hang_on_stuck_send():
    async def stuck(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(3600)
        raise AssertionError("недостижимо")

    client = httpx.AsyncClient(transport=httpx.MockTransport(stuck))
    notifier = Notifier(config(events=["buy"]), client)
    notifier.notify("buy", "зависшее")
    await asyncio.wait_for(notifier.aclose(grace=0.05), timeout=2)


async def test_snapshot_reports_counters():
    _, client = collector()
    notifier = Notifier(config(events=["buy"], max_per_minute=1), client)
    notifier.notify("buy", "первое")
    notifier.notify("buy", "второе")
    await notifier.aclose()
    assert notifier.snapshot() == {"sent": 1, "dropped": 1, "failed": 0}


# --- конфиг ---------------------------------------------------------------


def test_unknown_event_rejected_before_start():
    cfg = Config.from_raw(
        {"grok": {"api_key": "xai-1234567890abcdef"},
         "alerts": {"webhook_url": "https://hooks.example/x", "events": ["buy", "выдумка"]}},
        env={},
    )
    errors, _ = cfg.problems()
    assert any("выдумка" in e for e in errors)


def test_webhook_can_come_from_environment():
    cfg = Config.from_raw({"grok": {"api_key": "xai-1234567890abcdef"}},
                          env={"GROKBOT_ALERT_WEBHOOK": "https://hooks.example/из-окружения"})
    assert cfg.alerts.webhook_url.get_secret_value() == "https://hooks.example/из-окружения"


def test_redacted_masks_webhook():
    cfg = Config.from_raw(
        {"grok": {"api_key": "xai-1234567890abcdef"},
         "alerts": {"webhook_url": "https://hooks.example/секретный-токен"}}, env={})
    assert "секретный-токен" not in str(cfg.redacted())
