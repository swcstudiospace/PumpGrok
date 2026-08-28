"""Сквозной прогон пайплайна в dry-run на замоканном транспорте.

Проверяет проводку: что ступени идут в нужном порядке, что отказ на любой
из них пишется в лог с указанием ступени, и что в dry-run никакая
транзакция не отправляется.
"""

import asyncio
import json
import time

import httpx
import pytest

from src.log import read_log
from src.models import Config, Token
from src.pipeline import Pipeline, load_and_check, main, parse_args
from src.state import StateStore


def grok_handler(responses: dict[str, str]):
    """Отвечает разным JSON в зависимости от системного промпта агента."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        for marker, content in responses.items():
            if marker in system:
                return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
        raise AssertionError(f"неожиданный промпт: {system[:60]}")

    return handler


GOOD_AUDIT = json.dumps({
    "coordinated_buying": False, "wash_trading": False, "creator_dump_prep": False,
    "bundled_launch": False, "organic_buyer_share": 0.95, "confidence": 0.9,
    "flags": [], "reasoning": "чисто",
})
GOOD_NARRATIVE = json.dumps({
    "trend_fit": 0.9, "virality": 0.9, "community_signals": 0.9,
    "launch_timing": 0.9, "reasoning": "живой мем",
})
GOOD_TIMING = json.dumps({
    "market_sentiment": 0.9, "meme_season": 0.9, "volume_level": 0.9,
    "anomalies": [], "reasoning": "фон хороший",
})
APPROVE = json.dumps({"approve": True, "reason": "ок", "flags": [], "confidence": 0.9})
REJECT = json.dumps({"approve": False, "reason": "органика не бьётся",
                     "flags": ["contradiction"], "confidence": 0.9})


# Резервы кривой в моке — изменяемые: через них тесты роняют цену.
CURVE = {"sol": 30_000_000_000, "tokens": 900_000_000_000_000}


@pytest.fixture(autouse=True)
def _reset_curve():
    CURVE["sol"], CURVE["tokens"] = 30_000_000_000, 900_000_000_000_000
    yield


def crash_price(factor: float) -> None:
    """Обвалить цену в `factor` раз относительно текущей."""
    CURVE["sol"] = int(CURVE["sol"] * factor)


def data_handler(request: httpx.Request) -> httpx.Response:
    """Провайдер данных: холдеры, сделки, карточка токена."""
    path = request.url.path
    if path.endswith("/holders"):
        return httpx.Response(200, json=[
            {"address": f"h{i}", "share": 0.02, "amount": 1000} for i in range(20)
        ])
    if "/trades/all/" in path:
        base = time.time() - 600
        return httpx.Response(200, json=[
            {"user": f"w{i}", "txType": "buy", "solAmount": 0.3 + i * 0.02,
             "timestamp": base + i * 20, "signature": f"s{i}"}
            for i in range(30)
        ])
    return httpx.Response(200, json={
        "description": "милейший кот интернета",
        "twitter": "https://x.com/cat", "telegram": "https://t.me/cat",
        "website": "https://cat.fun",
        "virtual_sol_reserves": CURVE["sol"],
        "virtual_token_reserves": CURVE["tokens"],
    })


@pytest.fixture
def config(tmp_path) -> Config:
    cfg = Config()
    cfg.mode = "dry-run"
    cfg.grok.api_key = "xai-test-key-1234567890"
    cfg.grok.retry_base_delay = 0.0
    cfg.logging.path = str(tmp_path / "trades.jsonl")
    cfg.ops.state_path = str(tmp_path / "state.json")
    cfg.ops.reputation_path = str(tmp_path / "creators.json")
    cfg.filter.min_total_score = 0.65
    return cfg


LIVE_YAML = """
mode: live
grok:
  api_key: xai-настоящий-ключ-1234
solana:
  wallet_private_key: 5xНастоящийКлюч
"""

DRY_YAML = """
mode: dry-run
grok:
  api_key: xai-настоящий-ключ-1234
"""


def wire(pipeline: Pipeline, checker_answer: str) -> None:
    """Подменить весь сетевой транспорт на моки."""
    grok = httpx.AsyncClient(transport=httpx.MockTransport(grok_handler({
        "форензик": GOOD_AUDIT,
        "мем-культуры": GOOD_NARRATIVE,
        "рыночного режима": GOOD_TIMING,
        "риск-офицер": checker_answer,
    })))
    for agent in (pipeline.auditor, pipeline.narrative, pipeline.timing, pipeline.checker):
        agent._client = grok
    data = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(data_handler))
    pipeline.analyzer._client = data
    pipeline.executor._client = data


def fresh_token() -> Token:
    return Token(
        mint="Mint1111", name="Cat", symbol="CAT", image_uri="https://i",
        creator="Creator1", created_timestamp=time.time() - 600,
        unique_buyers=12, curve_progress=0.2, market_cap_sol=30.0,
    )


async def test_dry_run_buys_and_logs_full_context(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    analysis = await pipeline.process(fresh_token())

    assert analysis is not None
    assert analysis.checker.approve
    assert pipeline.risk.open_count == 1

    records = list(read_log(config.logging.path))
    buys = [r for r in records if r["type"] == "buy"]
    assert len(buys) == 1
    buy = buys[0]
    assert buy["tx_hash"] == "dry_run"          # ни одной реальной транзакции
    assert buy["mode"] == "dry-run"
    assert buy["scores"]["total"] >= config.filter.min_total_score
    assert buy["audit"]["organic_buyer_share"] == 0.95
    assert buy["narrative"] and buy["timing"] and buy["checker"]
    assert buy["metrics"]["trade_count"] == 30
    assert buy["entry_price"] > 0


async def test_checker_veto_stops_the_buy(config):
    pipeline = Pipeline(config)
    wire(pipeline, REJECT)
    assert await pipeline.process(fresh_token()) is None
    assert pipeline.risk.open_count == 0

    records = list(read_log(config.logging.path))
    assert [r["type"] for r in records] == ["skip"]
    assert records[0]["stage"] == "checker"
    assert "contradiction" in records[0]["detail"]


async def test_risk_gate_stops_the_buy(config):
    config.risk.max_open_positions = 0
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    assert await pipeline.process(fresh_token()) is None

    records = list(read_log(config.logging.path))
    assert records[-1]["stage"] == "risk"
    assert records[-1]["reason"].startswith("max_open_positions")


async def test_high_threshold_stops_before_checker(config):
    """Скоринговый порог экономит вызов сильной модели: чекер отвечать не должен."""
    config.filter.min_total_score = 0.99
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    pipeline.checker._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: (_ for _ in ()).throw(AssertionError("чекер вызван зря"))
        )
    )
    assert await pipeline.process(fresh_token()) is None
    records = list(read_log(config.logging.path))
    assert records[-1]["stage"] == "scoring"
    assert "слабее всего" in records[-1]["detail"]


async def test_stop_loss_closes_position_and_logs_pnl(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    await pipeline.process(fresh_token())
    position = pipeline.risk.positions["Mint1111"]

    await pipeline._sell(position, price=position.entry_price * 0.5)

    assert pipeline.risk.open_count == 0
    closes = [r for r in read_log(config.logging.path) if r["type"] == "close"]
    assert len(closes) == 1
    assert closes[0]["reason"] == "stop_loss"
    assert closes[0]["tx_hash"] == "dry_run"


# --- рестарт и остановка --------------------------------------------------


async def test_restart_picks_up_open_position(config):
    """Поднятый заново процесс не покупает то же самое второй раз."""
    config.filter.one_position_per_creator = False   # проверяем именно риск-гейт
    first = Pipeline(config)
    wire(first, APPROVE)
    await first.process(fresh_token())
    assert first.risk.open_count == 1

    second = Pipeline(config)
    wire(second, APPROVE)
    second.restore()
    assert second.risk.open_count == 1
    assert await second.process(fresh_token()) is None

    records = list(read_log(config.logging.path))
    assert records[-1]["stage"] == "risk"
    assert records[-1]["reason"] == "already_open"


async def test_restart_continues_grok_budget(config):
    """Иначе петля рестартов выест дневной бюджет вызовов за час."""
    first = Pipeline(config)
    wire(first, APPROVE)
    await first.process(fresh_token())
    spent = first.grok_ops.budget.spent
    assert spent >= 4                      # аудитор, нарратив, тайминг, чекер
    await first.shutdown()

    second = Pipeline(config)
    second.restore()
    assert second.grok_ops.budget.spent == spent


async def test_shutdown_persists_state(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    await pipeline.process(fresh_token())
    await pipeline.shutdown()

    saved = StateStore(config.ops.state_path).load()
    assert saved is not None
    assert "Mint1111" in saved.positions
    assert saved.trades_today == 1


async def test_stop_request_is_idempotent(config):
    pipeline = Pipeline(config)
    pipeline.request_stop("SIGTERM")
    pipeline.request_stop("SIGTERM")
    assert pipeline._stopping.is_set()


async def test_shutdown_finishes_work_in_flight(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    task = asyncio.create_task(pipeline.process(fresh_token()))
    pipeline._tasks.add(task)
    await pipeline.shutdown()
    assert task.done()
    assert pipeline.risk.open_count == 1


# --- наблюдаемость --------------------------------------------------------


async def test_status_is_ok_and_free_of_secrets(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    await pipeline.process(fresh_token())
    status = pipeline.status()
    assert status["status"] == "ok"
    assert status["open_positions"] == 1
    assert status["trades_today"] == 1
    assert config.grok.key not in json.dumps(status, ensure_ascii=False)


async def test_status_degrades_when_breaker_opens(config):
    config.ops.breaker_failures = 1
    pipeline = Pipeline(config)
    pipeline.grok_ops.breaker.record_failure()
    assert pipeline.status()["status"] == "degraded"


async def test_status_degrades_when_stream_stalls(config):
    pipeline = Pipeline(config)
    pipeline._last_event_at -= 10_000
    status = pipeline.status()
    assert status["stalled"]
    assert status["status"] == "degraded"


async def test_metrics_count_stages(config):
    pipeline = Pipeline(config)
    wire(pipeline, REJECT)
    await pipeline.process(fresh_token())
    assert pipeline.metrics.counters["skip_checker"] == 1
    assert pipeline.metrics.counters["grok_ok_checker"] == 1


# --- защита режима live ---------------------------------------------------


def test_live_without_flag_refuses(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(LIVE_YAML)
    with pytest.raises(SystemExit) as exc:
        load_and_check(parse_args(["--config", str(cfg)]))
    assert "--i-understand-the-risk" in str(exc.value)


def test_live_with_flag_allowed(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(LIVE_YAML)
    config = load_and_check(parse_args(["--config", str(cfg), "--i-understand-the-risk"]))
    assert config.is_live


def test_missing_config_refuses(tmp_path):
    with pytest.raises(SystemExit):
        load_and_check(parse_args(["--config", str(tmp_path / "нет.yaml")]))


def test_broken_yaml_refuses(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("mode: [не закрыт\n")
    with pytest.raises(SystemExit) as exc:
        load_and_check(parse_args(["--config", str(cfg)]))
    assert "не читается" in str(exc.value)


def test_invalid_config_refuses_before_start(tmp_path):
    """Плохой конфиг должен падать на запуске, а не через час торговли."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(DRY_YAML + "risk:\n  max_sol_per_trade: 0\n")
    with pytest.raises(SystemExit) as exc:
        load_and_check(parse_args(["--config", str(cfg)]))
    assert "max_sol_per_trade" in str(exc.value)


def test_dry_run_needs_no_flag(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(DRY_YAML)
    assert not load_and_check(parse_args(["--config", str(cfg)])).is_live


def test_check_flag_exits_without_running(tmp_path, capsys):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(DRY_YAML)
    assert main(["--config", str(cfg), "--check"]) == 0
    printed = capsys.readouterr().out
    assert "xai-настоящий-ключ-1234" not in printed
    assert "dry-run" in printed


async def test_live_executor_stub_does_not_crash_the_pipeline(config):
    """Заглушка live поднимает NotImplementedError — это отказ ступени с
    громкой записью в лог, а не падение процесса и не тихая покупка."""
    config.mode = "live"
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    assert pipeline.executor.__class__.__name__ == "LiveExecutor"

    assert await pipeline.process(fresh_token()) is None
    assert pipeline.risk.open_count == 0
    records = list(read_log(config.logging.path))
    assert records[-1]["stage"] == "executor"
    assert records[-1]["reason"] == "executor_not_implemented"


# --- полный жизненный цикл ------------------------------------------------


async def test_serve_runs_then_stops_cleanly(config):
    """Старт, обработка токена, health наружу, SIGTERM, сохранение состояния."""
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    config.ops.health_port = port
    config.ops.heartbeat_seconds = 3600      # в тесте не нужен
    config.ops.shutdown_grace_seconds = 5

    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)

    processed = asyncio.Event()

    async def fake_stream():
        yield fresh_token()
        processed.set()
        await asyncio.sleep(3600)            # дальше поток просто живёт

    pipeline.monitor.stream = fake_stream    # type: ignore[method-assign]

    async with pipeline:
        serving = asyncio.create_task(pipeline.serve())
        await asyncio.wait_for(processed.wait(), timeout=5)
        for _ in range(50):                  # ждём, пока токен доедет до покупки
            if pipeline.risk.open_count:
                break
            await asyncio.sleep(0.02)

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n")
        await writer.drain()
        head, _, body = (await reader.read()).decode().partition("\r\n\r\n")
        writer.close()
        assert "200" in head.split("\r\n")[0]
        assert json.loads(body)["open_positions"] == 1

        pipeline.request_stop("SIGTERM")
        assert await asyncio.wait_for(serving, timeout=10) == 0

    saved = StateStore(config.ops.state_path).load()
    assert saved is not None and "Mint1111" in saved.positions
    assert [r["type"] for r in read_log(config.logging.path)] == ["buy"]


# --- память о создателях --------------------------------------------------


async def test_creator_who_rugged_is_blocked_next_time(config):
    """Слив попадает в книгу, и следующий токен того же адреса не доходит
    до единого запроса к Grok."""
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    await pipeline.process(fresh_token())
    position = pipeline.risk.positions["Mint1111"]

    crash_price(0.1)                      # токен сложился в десять раз
    await pipeline._sell(position, price=await pipeline._price(position.mint),
                         reason="stop_loss")
    assert pipeline.reputation.creators["Creator1"].rugs == 1

    calls_before = pipeline.grok_ops.budget.spent
    другой = fresh_token()
    другой.mint = "Mint2222"
    assert await pipeline.process(другой) is None
    assert pipeline.grok_ops.budget.spent == calls_before      # агентов не звали

    records = list(read_log(config.logging.path))
    assert records[-1]["stage"] == "reputation"
    assert "сливал" in records[-1]["detail"]


async def test_blocklist_survives_restart(config):
    first = Pipeline(config)
    wire(first, APPROVE)
    await first.process(fresh_token())
    position = first.risk.positions["Mint1111"]
    crash_price(0.05)
    await first._sell(position, price=await first._price(position.mint), reason="stop_loss")
    await first.shutdown()

    second = Pipeline(config)
    wire(second, APPROVE)
    second.restore()
    новый = fresh_token()
    новый.mint = "Mint3333"
    assert await second.process(новый) is None
    assert list(read_log(config.logging.path))[-1]["stage"] == "reputation"


async def test_second_token_from_same_creator_is_one_bet(config):
    """Два токена одного деплойера сливают вместе — это одна ставка."""
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    await pipeline.process(fresh_token())

    второй = fresh_token()
    второй.mint = "Mint4444"
    assert await pipeline.process(второй) is None
    records = list(read_log(config.logging.path))
    assert records[-1]["stage"] == "reputation"
    assert "уже открыта позиция" in records[-1]["detail"]


async def test_moderate_loss_does_not_blacklist(config):
    config.filter.rug_loss_pct = 60.0
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    await pipeline.process(fresh_token())
    position = pipeline.risk.positions["Mint1111"]

    crash_price(0.75)                     # минус 25%: неприятно, но не слив
    await pipeline._sell(position, price=await pipeline._price(position.mint),
                         reason="stop_loss")
    assert pipeline.reputation.creators["Creator1"].rugs == 0
    assert pipeline._creator_verdict(fresh_token()) is None


async def test_reputation_can_be_switched_off(config):
    config.filter.block_creator_after_rugs = 0
    config.filter.one_position_per_creator = False
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    await pipeline.process(fresh_token())
    position = pipeline.risk.positions["Mint1111"]
    crash_price(0.05)
    await pipeline._sell(position, price=await pipeline._price(position.mint),
                         reason="stop_loss")

    другой = fresh_token()
    другой.mint = "Mint5555"
    assert await pipeline.process(другой) is not None      # куплен, несмотря на слив


# --- уведомления ----------------------------------------------------------


def wire_alerts(pipeline: Pipeline) -> list[dict]:
    """Включить уведомления и собирать их в список вместо сети."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(204)

    pipeline.config.alerts.webhook_url = "https://hooks.example/тест"
    pipeline.notifier.config = pipeline.config.alerts
    pipeline.notifier._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    pipeline.notifier._owns_client = False   # мок переживает aclose между проверками
    return seen


async def flush_alerts(pipeline: Pipeline) -> None:
    """Дождаться отправки: notify кладёт задачу в фон и возвращает управление."""
    await pipeline.notifier.aclose()


async def test_buy_is_announced(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    seen = wire_alerts(pipeline)
    await pipeline.process(fresh_token())
    await pipeline.notifier.aclose()

    buys = [event for event in seen if event["event"] == "buy"]
    assert len(buys) == 1
    assert "CAT" in buys[0]["text"]
    assert buys[0]["fields"]["mint"] == "Mint1111"


async def test_rug_is_announced_separately_from_close(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    seen = wire_alerts(pipeline)
    await pipeline.process(fresh_token())
    position = pipeline.risk.positions["Mint1111"]

    crash_price(0.05)
    await pipeline._sell(position, price=await pipeline._price(position.mint),
                         reason="stop_loss")
    await pipeline.notifier.aclose()

    kinds = [event["event"] for event in seen]
    assert kinds.count("close") == 1
    assert kinds.count("rug") == 1
    assert "отсекаются" in next(e for e in seen if e["event"] == "rug")["text"]


async def test_ordinary_loss_is_not_announced_as_rug(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    seen = wire_alerts(pipeline)
    await pipeline.process(fresh_token())
    position = pipeline.risk.positions["Mint1111"]

    crash_price(0.8)
    await pipeline._sell(position, price=await pipeline._price(position.mint),
                         reason="stop_loss")
    await pipeline.notifier.aclose()
    assert "rug" not in [event["event"] for event in seen]


async def test_breaker_announced_once_per_transition(config):
    config.ops.breaker_failures = 1
    pipeline = Pipeline(config)
    seen = wire_alerts(pipeline)

    pipeline.grok_ops.breaker.record_failure()
    pipeline._check_transitions()
    pipeline._check_transitions()                  # второй раз молчим
    await flush_alerts(pipeline)
    breaker_events = [e for e in seen if e["event"] == "breaker"]
    assert len(breaker_events) == 1
    assert "разомкнута" in breaker_events[0]["text"]

    pipeline.grok_ops.breaker.record_success()
    pipeline._check_transitions()
    await flush_alerts(pipeline)
    assert [e["text"] for e in seen if e["event"] == "breaker"][-1].endswith("продолжается")


async def test_halt_is_announced(config):
    pipeline = Pipeline(config)
    seen = wire_alerts(pipeline)
    pipeline.risk.register_close("X", pnl_sol=-config.risk.daily_loss_limit_sol)
    pipeline._check_transitions()
    await pipeline.notifier.aclose()
    assert any(e["event"] == "halted" for e in seen)


async def test_alerts_off_by_default(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    assert not pipeline.notifier.enabled
    await pipeline.process(fresh_token())          # ничего не шлётся и не падает
    assert pipeline.notifier.snapshot() == {"sent": 0, "dropped": 0, "failed": 0}


# --- покупка без цены -----------------------------------------------------


async def test_buy_without_price_is_refused(config):
    """Позиция с нулевой ценой входа неуправляема: ни одно правило выхода
    на ней не срабатывает, и она висела бы открытой вечно."""
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    CURVE["sol"] = 0                                # провайдер не отдал резервы
    без_цены = fresh_token()
    без_цены.market_cap_sol = 0.0                   # и запасной прикидки тоже нет

    assert await pipeline.process(без_цены) is None
    assert pipeline.risk.open_count == 0
    records = list(read_log(config.logging.path))
    assert records[-1]["stage"] == "executor"
    assert records[-1]["reason"] == "execution_failed"


async def test_blind_position_degrades_health(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    await pipeline.process(fresh_token())

    pipeline.watcher.price_failures["Mint1111"] = pipeline.watcher.BLIND_AFTER
    status = pipeline.status()
    assert status["blind_positions"] == 1
    assert status["status"] == "degraded"


async def test_blind_position_is_announced(config):
    pipeline = Pipeline(config)
    wire(pipeline, APPROVE)
    seen = wire_alerts(pipeline)
    await pipeline.process(fresh_token())

    pipeline.watcher.price_failures["Mint1111"] = pipeline.watcher.BLIND_AFTER
    pipeline._check_transitions()
    await flush_alerts(pipeline)
    blind = [e for e in seen if e["event"] == "blind"]
    assert len(blind) == 1
    assert "не работают" in blind[0]["text"]
