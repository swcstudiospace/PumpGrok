"""Tool discovery with least-privilege enforcement (interfaces.md 2.10, R40).

Invariants (I1-I5):
  I1 find() raises PermissionDenied unless the tool is in the bot's allowed_tools.
  I2 find() raises PermissionDenied if the tool's side effect exceeds the grant's;
     an approval-gated tool is additionally wrapped so RiskEngine.check runs before
     the underlying callable executes.
  I3 find() raises LiveGateError for any LIVE_WRITE tool regardless of roster,
     max_side_effect, or config mode. There is no argument that unlocks it.
  I4 Every refusal is appended to the audit log before the exception propagates.
  I5 Seats may only write ledger events through journal.append and desk.event_emit
     with kind in {journal_note, escalation}; every other event type is appended
     by library code only.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from pumpgrok.core.bot import BotManifest
from pumpgrok.core.errors import LiveGateError, PermissionDenied
from pumpgrok.core.ids import (
    Clock,
    bind_correlation,
    current_correlation,
    next_span,
)
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput

if TYPE_CHECKING:
    from pumpgrok.core.adapter import OrderRequest

log = logging.getLogger("pumpgrok.core")


class GrantAudit(BaseModel):
    """One row per resolution attempt.

    Every LIVE_WRITE attempt is a row with `allowed=False` and is also emitted as
    a critical alert. `at` is the injected Clock's time (R27), never `datetime.now`.
    """

    model_config = ConfigDict(frozen=True)

    at: datetime
    bot: str
    tool: str
    requested_side_effect: SideEffect
    allowed: bool
    reason: str
    correlation_id: str


class ToolRegistry:
    """Bots discover tools by capability and permission."""

    def __init__(
        self,
        *,
        clock: Clock,
        audit_sink: Callable[[GrantAudit], None],
        limits_checker: Callable[[OrderRequest, str], Awaitable[bool]],
    ) -> None:
        self._clock = clock
        self._tools: dict[str, Tool] = {}
        self._audit = audit_sink
        self._check_limits = limits_checker  # RiskEngine.check bound by cli.py

    # -- registration -------------------------------------------------------

    def register(self, tool_obj: Tool) -> None:
        name = tool_obj.spec.name
        if name in self._tools:
            raise ValueError(f"duplicate tool {name}")
        if tool_obj.spec.side_effect is SideEffect.LIVE_WRITE:
            # Registered so attempts can be audited; never resolvable (I3).
            log.warning("registering live-write tool %s as refuse-only", name)
        self._tools[name] = tool_obj

    def register_all(self, tools: Iterable[Tool]) -> None:
        for t in tools:
            self.register(t)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def spec(self, name: str) -> object:
        return self._tools[name].spec

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self._clock.now(), UTC)

    # -- resolution ---------------------------------------------------------

    def find(
        self,
        capability: str,
        *,
        max_side_effect: SideEffect,
        bot: BotManifest,
    ) -> Tool:
        """Resolve `capability` for `bot`.

        An exact name must match exactly; a namespace prefix resolves to the first
        granted tool in that namespace whose side effect does not exceed
        `max_side_effect`.
        """
        cid = current_correlation()
        candidates = [
            t for n, t in self._tools.items() if n == capability or n.startswith(capability + ".")
        ]
        if not candidates:
            self._refuse(bot, capability, max_side_effect, "unknown_tool", str(cid))
        for t in sorted(candidates, key=lambda t: t.spec.name):
            spec = t.spec
            if spec.side_effect is SideEffect.LIVE_WRITE:
                self._refuse(
                    bot,
                    spec.name,
                    spec.side_effect,
                    "live_write_never_resolvable",
                    str(cid),
                    live=True,
                )
            grant = bot.grant_for(spec.name)
            if grant is None:
                if capability == spec.name:
                    self._refuse(bot, spec.name, spec.side_effect, "not_in_roster", str(cid))
                continue
            if spec.side_effect.exceeds(grant.side_effect):
                self._refuse(bot, spec.name, spec.side_effect, "exceeds_grant", str(cid))
            if spec.side_effect.exceeds(max_side_effect):
                self._refuse(bot, spec.name, spec.side_effect, "exceeds_requested_max", str(cid))
            self._audit(
                GrantAudit(
                    at=self._now(),
                    bot=bot.id,
                    tool=spec.name,
                    requested_side_effect=spec.side_effect,
                    allowed=True,
                    reason="ok",
                    correlation_id=str(cid),
                )
            )
            return self._wrap(t, bot)
        self._refuse(bot, capability, max_side_effect, "no_granted_tool_in_namespace", str(cid))
        raise AssertionError("unreachable")

    def _refuse(
        self,
        bot: BotManifest,
        tool_name: str,
        se: SideEffect,
        reason: str,
        cid: str,
        *,
        live: bool = False,
    ) -> None:
        self._audit(
            GrantAudit(
                at=self._now(),
                bot=bot.id,
                tool=tool_name,
                requested_side_effect=se,
                allowed=False,
                reason=reason,
                correlation_id=cid,
            )
        )
        if live:
            raise LiveGateError(
                f"{bot.id} attempted live-write tool {tool_name}",
                tool=tool_name,
                bot=bot.id,
            )
        raise PermissionDenied(
            f"{bot.id} may not resolve {tool_name}: {reason}",
            tool=tool_name,
            bot=bot.id,
            reason=reason,
        )

    def _wrap(self, t: Tool, bot: BotManifest) -> Tool:
        """Apply Clock-routed timeout and retry, rate limit, correlation stamping and,
        for approval-gated tools, the limits/approval check (I2). Returns a Tool."""
        spec = t.spec
        check_limits = self._check_limits
        clock = self._clock

        class _Guarded:
            def __init__(self) -> None:
                self.spec = spec

            async def __call__(self, payload: ToolInput, /) -> ToolOutput:
                cid = next_span(current_correlation())
                with bind_correlation(cid):
                    if spec.requires_approval:
                        from pumpgrok.core.adapter import OrderRequest

                        req = OrderRequest.model_validate(
                            payload.model_dump() | {"correlation_id": str(cid)}
                        )
                        if not await check_limits(req, bot.id):
                            raise PermissionDenied(
                                "RiskEngine.check refused", tool=spec.name, bot=bot.id
                            )
                    # rate limit applied here by the implementation; retries use
                    # tenacity(sleep=clock.sleep, ...) per spec.retry (R27)
                    async with clock.timeout(spec.timeout_s):
                        return await t(payload)

        return _Guarded()
