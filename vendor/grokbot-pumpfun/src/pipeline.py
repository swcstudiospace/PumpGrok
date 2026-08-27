"""Оркестратор: связывает все ступени в один поток.

    монитор → анализатор → аудитор → нарратив → тайминг → скоринг →
    чекер → риск-гейт → исполнение

Каждая ступень либо пропускает токен дальше, либо пишет skip с причиной и
на этом заканчивает. Дорогие ступени стоят после дешёвых: до grok-4
доходит только то, что пережило фильтр кодом, метрики, трёх быстрых
агентов и скоринговый порог.

Процесс рассчитан на то, чтобы жить сутками: состояние переживает
рестарт, SIGTERM останавливает аккуратно, расход Grok ограничен, живость
видна снаружи через /healthz.

Запуск:
    python -m src.pipeline --config config.yaml
    python -m src.pipeline --config config.yaml --check          # только проверить
    python -m src.pipeline --config config.yaml --i-understand-the-risk   # для live
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from .agents import AuditorAgent, CheckerAgent, NarrativeAgent, TimingAgent
from .alerts import Notifier
from .analyzer import Analyzer, compute_metrics, enrich_token
from .executor import BaseExecutor, build_executor, new_position
from .log import TradeLog, setup_logging
from .models import Analysis, Config, ConfigError, Position, Token
from .monitor import LaunchMonitor
from .ops import (
    GrokOps,
    HealthServer,
    Heartbeat,
    Metrics,
    cancel_and_wait,
    drain,
    install_signal_handlers,
)
from .reputation import ReputationBook
from .risk import PositionWatcher, RiskManager
from .scoring import compute_scores, passes_threshold, weakest_component
from .state import StateStore

log = logging.getLogger("pipeline")

# Сколько токенов разбираем одновременно. Больше — упрёмся в лимиты Grok.
MAX_CONCURRENT_TOKENS = 4

# Столько без единого события из сокета — считаем поток застрявшим и
# сообщаем об этом в /healthz. Лончи на pump.fun идут непрерывно.
STALL_SECONDS = 600.0


class Pipeline:
    """Держит агентов, состояние риска и лог; гоняет токены по ступеням."""

    def __init__(self, config: Config, store: StateStore | None = None) -> None:
        self.config = config
        self.metrics = Metrics()
        self.trade_log = TradeLog.from_config(config)
        self.store = store if store is not None else StateStore(config.ops.state_path)
        self.risk = RiskManager(config, store=self.store)
        self.reputation = ReputationBook.load(config.ops.reputation_path)
        self.notifier = Notifier(config.alerts)
        self.grok_ops = GrokOps(config, self.metrics)

        self._grok_client = httpx.AsyncClient(
            timeout=config.grok.timeout_seconds,
            limits=httpx.Limits(max_connections=config.ops.grok_max_concurrency * 2),
        )
        self.auditor = AuditorAgent(config, self._grok_client, self.grok_ops)
        self.narrative = NarrativeAgent(config, self._grok_client, self.grok_ops)
        self.timing = TimingAgent(config, self._grok_client, self.grok_ops)
        self.checker = CheckerAgent(config, self._grok_client, self.grok_ops)

        self.analyzer = Analyzer(config)
        self.executor: BaseExecutor = build_executor(config)
        self.monitor = LaunchMonitor(config, on_skip=self._log_monitor_skip)
        self.watcher = PositionWatcher(self.risk, self._price, self._sell)
        self.health = HealthServer(
            config.ops.health_host, config.ops.health_port, self.status, self.metrics
        )
        self.heartbeat = Heartbeat(config.ops.heartbeat_seconds, self._heartbeat_status)

        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_TOKENS)
        self._tasks: set[asyncio.Task] = set()
        self._stopping = asyncio.Event()
        self._started_at = time.time()
        self._last_event_at = time.time()
        self._alerted: dict[str, bool] = {
            "breaker": False, "halted": False, "stalled": False, "blind": False,
        }

    # -- жизненный цикл ----------------------------------------------------

    async def __aenter__(self) -> Pipeline:
        await self.analyzer.__aenter__()
        await self.executor.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.watcher.stop()
        await self.heartbeat.stop()
        await self.health.stop()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.analyzer.__aexit__(*exc)
        await self.executor.__aexit__(*exc)
        await self._grok_client.aclose()

    def restore(self) -> None:
        """Поднять состояние прошлого запуска: позиции, лимиты дня, репутацию."""
        forgotten = self.reputation.forget_older_than(self.config.filter.forget_creators_after_days)
        log.info("книга репутации: %s%s", self.reputation.summary(),
                 f", забыто устаревших {forgotten}" if forgotten else "")
        if self.risk.restore():
            # Бюджет вызовов Grok продолжается с того же места, иначе
            # рестарт-петля выест дневной лимит за час.
            self.grok_ops.budget.spent = self.risk.grok_calls_today
            for mint, position in self.risk.positions.items():
                log.info("позиция под присмотром после рестарта: %s, вход %.12f, %.4f SOL",
                         mint[:8], position.entry_price, position.sol_spent)

    async def serve(self) -> int:
        """Полный жизненный цикл: старт, работа, аккуратная остановка."""
        install_signal_handlers(self.request_stop)
        self.restore()
        await self.health.start()
        self.watcher.start()
        self.heartbeat.start()
        log.info("пайплайн запущен: %s", self.config.summary())
        self.notifier.notify(
            "started", f"пайплайн запущен, режим {self.config.mode}",
            open_positions=self.risk.open_count, mode=self.config.mode,
        )

        consumer = asyncio.create_task(self._consume(), name="monitor-consumer")
        stopper = asyncio.create_task(self._stopping.wait(), name="stop-signal")
        await asyncio.wait({consumer, stopper}, return_when=asyncio.FIRST_COMPLETED)

        await cancel_and_wait(stopper)
        await cancel_and_wait(consumer)
        await self.shutdown()
        return 0

    def request_stop(self, reason: str = "stop") -> None:
        """Вызывается обработчиком сигнала. Второй сигнал не ускоряет выход."""
        if not self._stopping.is_set():
            log.info("получен %s — останавливаемся аккуратно", reason)
            self._stopping.set()
        else:
            log.warning("%s повторно, уже останавливаемся", reason)

    async def shutdown(self) -> None:
        """Доделать начатое, сохранить состояние, закрыть соединения."""
        done, cancelled = await drain(set(self._tasks), self.config.ops.shutdown_grace_seconds)
        self._tasks.clear()
        self._sync_counters()
        self.risk.persist()
        self._save_reputation()
        await self.watcher.stop()
        await self.heartbeat.stop()
        await self.health.stop()
        log.info(
            "остановлено: доделано %d, снято %d, открытых позиций %d, "
            "сделок за день %d, PnL %+.4f SOL, вызовов Grok %d",
            done, cancelled, self.risk.open_count, self.risk.trades_today,
            self.risk.realized_pnl_sol, self.grok_ops.budget.spent,
        )
        self.notifier.notify(
            "stopped",
            f"остановлен: открытых позиций {self.risk.open_count}, "
            f"PnL за день {self.risk.realized_pnl_sol:+.4f} SOL",
            open_positions=self.risk.open_count,
        )
        await self.notifier.aclose()
        if self.risk.positions:
            log.warning("позиции остаются открытыми: %s — стоп-лосс не работает, "
                        "пока процесс не поднят снова",
                        ", ".join(m[:8] for m in self.risk.positions))

    async def _consume(self) -> None:
        """Читать поток монитора и раздавать токены в обработку."""
        async for token in self.monitor.stream():
            self._last_event_at = time.time()
            self.metrics.inc("tokens_seen")
            self._check_transitions()
            if self._stopping.is_set():
                break
            if self.risk.halted:
                self.metrics.inc("skip_risk_halted")
                self.trade_log.skip(token, stage="risk", reason="daily_loss_limit_hit")
                continue
            task = asyncio.create_task(self._guarded(token), name=f"token-{token.mint[:8]}")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _guarded(self, token: Token) -> None:
        async with self._semaphore:
            try:
                await self.process(token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("токен %s уронил обработку: %s", token.mint, exc)
                self.metrics.inc("errors")
                self.trade_log.skip(token, stage="pipeline",
                                    reason="internal_error", detail=str(exc))

    # -- ступени -----------------------------------------------------------

    async def process(self, token: Token) -> Analysis | None:
        """Один токен от метрик до покупки. None, если отсеян."""
        log.info("разбираем %s (%s), покупателей %d",
                 token.symbol or "?", token.mint[:8], token.unique_buyers)
        self.reputation.observe(token.creator)

        # 1.5. Память о создателе. Бесплатная ступень перед всеми платными:
        # адрес, который уже сливал, дальше не идёт.
        blocked = self._creator_verdict(token)
        if blocked:
            return self._reject(Analysis(token=token), stage="reputation",
                                reason="creator_blocked", detail=blocked)

        # 2. Анализатор: сеть параллельно, метрики кодом.
        info, holders, trades = await self.analyzer.fetch(token.mint)
        enrich_token(token, info)
        metrics = compute_metrics(token, holders, trades)
        analysis = Analysis(token=token, metrics=metrics)

        ok, reason = self.analyzer.passes(metrics)
        if not ok:
            return self._reject(analysis, stage="analyzer", reason=reason,
                                detail=f"risk_score={metrics.risk_score}")

        # 3-5. Быстрые агенты параллельно. Тайминг обычно берётся из кэша.
        analysis.audit, analysis.narrative, analysis.timing = await asyncio.gather(
            self.auditor.run(token, trades, holders, metrics),
            self.narrative.run(token),
            self.timing.get(self._market_snapshot()),
        )

        # 6. Скоринг кодом.
        analysis.scores = compute_scores(analysis, self.config)
        ok, reason = passes_threshold(analysis.scores, self.config)
        if not ok:
            name, value = weakest_component(analysis.scores)
            return self._reject(analysis, stage="scoring", reason=reason,
                                detail=f"слабее всего {name}={value:.3f}")

        # 7. Адверсариальный чекер на сильной модели.
        analysis.checker = await self.checker.run(analysis)
        if not analysis.checker.approve:
            return self._reject(
                analysis, stage="checker", reason="checker_rejected",
                detail=f"{analysis.checker.reason} [{', '.join(analysis.checker.flags)}]",
            )

        # 8. Риск-гейт.
        decision = self.risk.evaluate(token.mint, analysis.scores.total)
        if not decision.approved:
            return self._reject(analysis, stage="risk", reason=decision.reason)

        # 9. Исполнение.
        self._sync_counters()
        try:
            result = await self.executor.buy(token, decision.size_sol)
        except NotImplementedError as exc:
            # Live-исполнитель — заглушка по замыслу: об этом надо кричать,
            # а не глотать как обычную ошибку ступени.
            log.error("исполнение не реализовано: %s", exc)
            return self._reject(analysis, stage="executor", reason="executor_not_implemented",
                                detail=str(exc))
        if not result.ok:
            return self._reject(analysis, stage="executor", reason="execution_failed",
                                detail=result.error)

        position = new_position(token, result, analysis.scores.total)
        self._sync_counters()
        self.risk.register_open(position)
        self.reputation.record_open(token.creator)
        self.trade_log.buy(analysis, size_sol=decision.size_sol,
                           entry_price=result.price, tx_hash=result.tx_hash)
        self.metrics.inc("buys")
        self.metrics.gauge("open_positions", self.risk.open_count)
        log.info("КУПЛЕНО %s на %.4f SOL, score %.3f, tx %s",
                 token.symbol or token.mint[:8], decision.size_sol,
                 analysis.scores.total, result.tx_hash)
        self.notifier.notify(
            "buy",
            f"куплен {token.symbol or token.mint[:8]} на {decision.size_sol:.4f} SOL, "
            f"score {analysis.scores.total:.3f}",
            mint=token.mint, size_sol=decision.size_sol,
            score=analysis.scores.total, tx=result.tx_hash,
        )
        return analysis

    def _reject(
        self, analysis: Analysis, *, stage: str, reason: str, detail: str | None = None
    ) -> Analysis | None:
        """Отказ на ступени: метрика, запись в лог, конец разбора."""
        self.metrics.inc(f"skip_{stage}")
        self.trade_log.skip(
            analysis.token, stage=stage, reason=reason, detail=detail,
            scores=analysis.scores if analysis.scores.total else None,
        )
        return None

    # -- состояние и наблюдаемость ----------------------------------------

    def _heartbeat_status(self) -> dict[str, Any]:
        """Снимок для heartbeat, попутно ловящий переходы.

        Во время застоя событий из сокета нет, и другого повода заметить
        его — тоже: heartbeat остаётся единственным тиком.
        """
        status = self.status()
        self._check_transitions(status)
        return status

    def _check_transitions(self, status: dict[str, Any] | None = None) -> None:
        """Отправить уведомление на смене состояния, а не на каждом тике."""
        if not self.notifier.enabled:
            return
        status = status or self.status()
        edges = {
            "breaker": (
                status["breaker"] == "open",
                "цепь Grok разомкнута — пайплайн не покупает",
                "цепь Grok замкнулась, работа продолжается",
            ),
            "halted": (
                bool(status["halted"]),
                f"дневной лимит убытка выбран ({self.risk.daily_loss:.4f} SOL), "
                "торговли сегодня не будет",
                "новые сутки, торговля возобновлена",
            ),
            "stalled": (
                bool(status["stalled"]),
                "поток лончей встал: нет событий из сокета",
                "поток лончей восстановился",
            ),
            "blind": (
                bool(status["blind_positions"]),
                f"нет цен по {status['blind_positions']} открытым позициям — "
                "стоп-лосс и take-profit по ним сейчас не работают",
                "цены по позициям снова приходят",
            ),
        }
        for name, (active, on_text, off_text) in edges.items():
            if active and not self._alerted[name]:
                self.notifier.notify(name, on_text, **{name: True})
            elif not active and self._alerted[name]:
                self.notifier.notify(name, off_text, **{name: False})
            self._alerted[name] = active

    def _creator_verdict(self, token: Token) -> str | None:
        """Причина не связываться с создателем этого токена, или None."""
        flt = self.config.filter
        verdict = self.reputation.verdict(token.creator, flt.block_creator_after_rugs)
        if verdict:
            return verdict
        if flt.one_position_per_creator and token.creator:
            same = [p.mint[:8] for p in self.risk.positions.values()
                    if p.creator == token.creator]
            if same:
                # Два токена одного деплойера — это одна ставка, а не две:
                # сливают их обычно вместе.
                return f"у создателя уже открыта позиция ({', '.join(same)})"
        return None

    def _save_reputation(self) -> None:
        self.reputation.save(self.config.ops.reputation_path)

    def _sync_counters(self) -> None:
        """Перенести расход Grok в состояние, которое ляжет на диск."""
        self.risk.grok_calls_today = self.grok_ops.budget.spent

    def status(self) -> dict[str, Any]:
        """Снимок для /healthz и heartbeat. Ничего секретного не содержит."""
        stalled = (time.time() - self._last_event_at) > STALL_SECONDS
        breaker = self.grok_ops.breaker.state
        blind = bool(self.watcher.blind)
        state = "degraded" if breaker == "open" or stalled or blind else "ok"
        return {
            "status": state,
            "mode": self.config.mode,
            "uptime_seconds": round(self.metrics.uptime_seconds, 1),
            "stalled": stalled,
            "seconds_since_event": round(time.time() - self._last_event_at, 1),
            "in_flight": len(self._tasks),
            "pending_launches": len(self.monitor.pending),
            "open_positions": self.risk.open_count,
            "blind_positions": len(self.watcher.blind),
            "trades_today": self.risk.trades_today,
            "realized_pnl_sol": round(self.risk.realized_pnl_sol, 6),
            "halted": self.risk.halted,
            "breaker": breaker,
            "grok_budget_remaining": self.grok_ops.budget.remaining,
            "grok_tokens_in": self.grok_ops.tokens_in,
            "grok_tokens_out": self.grok_ops.tokens_out,
            "blocked_creators": sum(
                1 for r in self.reputation.creators.values() if r.is_known_bad
            ),
            "alerts": self.notifier.snapshot(),
        }

    def _market_snapshot(self) -> dict[str, Any]:
        """Что пайплайн знает о рынке сам — уходит тайминг-агенту как контекст."""
        return {
            "pending_launches": len(self.monitor.pending),
            "open_positions": self.risk.open_count,
            "trades_today": self.risk.trades_today,
            "realized_pnl_sol": round(self.risk.realized_pnl_sol, 4),
        }

    def _log_monitor_skip(self, token: Token, reason: str) -> None:
        self.metrics.inc("skip_monitor")
        self.trade_log.skip(token, stage="monitor", reason=reason)

    async def _price(self, mint: str) -> float:
        return await self.executor.price(mint)

    async def _sell(self, position: Position, price: float, reason: str = "stop_loss") -> None:
        """Выход из позиции: продать, посчитать PnL, записать в лог."""
        try:
            result = await self.executor.sell(position)
        except NotImplementedError as exc:
            log.error("продажа не реализована, позиция %s остаётся открытой: %s",
                      position.mint[:8], exc)
            self.metrics.inc("sell_not_implemented")
            return
        proceeds = result.sol_amount if result.ok else position.token_amount * price
        pnl = proceeds - position.sol_spent
        exit_price = result.price or price
        change_pct = (
            (exit_price - position.entry_price) / position.entry_price * 100.0
            if position.entry_price else 0.0
        )
        self._sync_counters()
        self.risk.register_close(position.mint, pnl_sol=pnl)
        self.reputation.record_close(
            position.creator, pnl_sol=pnl, pnl_pct=change_pct,
            rug_loss_pct=self.config.filter.rug_loss_pct,
        )
        self._save_reputation()
        self.trade_log.close(position, exit_price=result.price or price,
                             pnl_sol=pnl, reason=reason, tx_hash=result.tx_hash)
        self.metrics.inc("closes")
        self.metrics.inc(f"exit_{reason}")
        self.metrics.gauge("open_positions", self.risk.open_count)
        log.info("ЗАКРЫТО %s по правилу %s, PnL %+.4f SOL", position.mint[:8], reason, pnl)
        self.notifier.notify(
            "close",
            f"закрыт {position.symbol or position.mint[:8]} по правилу {reason}: "
            f"{pnl:+.4f} SOL ({change_pct:+.1f}%)",
            mint=position.mint, reason=reason, pnl_sol=round(pnl, 6),
            pnl_pct=round(change_pct, 2),
        )
        if -change_pct >= self.config.filter.rug_loss_pct:
            self.notifier.notify(
                "rug",
                f"создатель {(position.creator or '?')[:8]} слил "
                f"{position.symbol or position.mint[:8]} ({change_pct:+.1f}%) — "
                "его следующие токены отсекаются на входе",
                creator=position.creator, mint=position.mint,
                pnl_pct=round(change_pct, 2),
            )
        self._check_transitions()


# --------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------


LIVE_WARNING = """
================================================================
  РЕЖИМ LIVE

  Пайплайн будет отправлять РЕАЛЬНЫЕ транзакции реальным кошельком
  из config.yaml. Мемкоины на бондинговой кривой теряют стоимость
  полностью и обычно. Потолок на сделку {max_sol} SOL, дневной лимит
  убытка {daily} SOL — это ограничители, а не гарантия.

  Запуск в live требует флага --i-understand-the-risk.
================================================================
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="grokbot-pumpfun")
    parser.add_argument("--config", default="config.yaml", help="путь к конфигу")
    parser.add_argument("--check", action="store_true",
                        help="проверить конфиг и выйти, ничего не запуская")
    parser.add_argument("--i-understand-the-risk", action="store_true",
                        help="обязателен для запуска в режиме live")
    return parser.parse_args(argv)


def load_and_check(args: argparse.Namespace) -> Config:
    """Прочитать конфиг, проверить пригодность, объяснить отказ по-человечески."""
    path = Path(args.config)
    if not path.exists():
        raise SystemExit(f"Конфига {path} нет. Скопируйте config.example.yaml в config.yaml.")

    try:
        config = Config.load(path)
    except Exception as exc:
        raise SystemExit(f"Конфиг {path} не читается: {exc}") from exc

    try:
        warnings = config.check_ready()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    for warning in warnings:
        print(f"ВНИМАНИЕ: {warning}", file=sys.stderr)

    if config.is_live:
        print(LIVE_WARNING.format(
            max_sol=config.risk.max_sol_per_trade,
            daily=config.risk.daily_loss_limit_sol,
        ), file=sys.stderr)
        if not getattr(args, "i_understand_the_risk", False):
            raise SystemExit(
                "Отказ: mode: live без флага --i-understand-the-risk. "
                "Либо верните mode: dry-run, либо подтвердите флагом."
            )
    return config


async def amain(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_and_check(args)
    setup_logging(config)

    if args.check:
        print(json.dumps(config.redacted(), ensure_ascii=False, indent=2))
        print("\nКонфиг пригоден для запуска.", file=sys.stderr)
        return 0

    async with Pipeline(config) as pipeline:
        return await pipeline.serve()


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(amain(argv))
    except KeyboardInterrupt:            # если сигнал пришёл до установки обработчиков
        print("\nостановлено", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
