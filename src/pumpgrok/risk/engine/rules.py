"""RiskEngine rule stages: the step walk, the CONFIRMING holding check and the probe claim.

RiskEngine._evaluate runs these stages in order. Each raises _Fail on the first refusal, and
the engine turns that into a rejected RiskDecision. Step order, skip rules and probe ownership
are exactly those the unsplit _evaluate applied (11-04 split, behavior unchanged).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pumpgrok.risk.breakers import BREAKER_NAMES
from pumpgrok.risk.engine.constants import _RECHECK_STEPS, EXIT_SKIP_STEPS, STEP_IDS
from pumpgrok.risk.engine.model import _Fail

if TYPE_CHECKING:
    from pumpgrok.risk.breakers import BreakerSet
    from pumpgrok.risk.engine.model import _StepCtx
    from pumpgrok.risk.engine.steps import _EngineSteps


@dataclass(frozen=True)
class ProbeView:
    """Half-open breakers seen at evaluation time.

    ``half_all`` are every half-open breaker, ``owned`` the ones this order already probes,
    and ``half_avail`` the ones a new probe may still be admitted on.
    """

    half_all: list[str]
    owned: list[str]
    half_avail: list[str]


def skip_step(step: str, ctx: _StepCtx) -> bool:
    """True when this step does not run for this order and stage."""
    if ctx.stage == "CONFIRMING" and step not in _RECHECK_STEPS:
        return True
    return ctx.is_exit_sell and step in EXIT_SKIP_STEPS


def walk_steps(engine: _EngineSteps, ctx: _StepCtx) -> None:
    """Run the R34 steps in STEP_IDS order; the first refusal raises _Fail and stops the walk."""
    for step in STEP_IDS:
        if skip_step(step, ctx):
            continue
        getattr(engine, f"_step_{step}")(ctx)


def confirm_holding(ctx: _StepCtx) -> None:
    """A sell sized at ACCEPTED must still find its holding at the fill.

    A flatten or another exit may have closed the position while this order slept.
    """
    if ctx.stage != "CONFIRMING" or ctx.is_buy:
        return
    held = ctx.state.positions.get(ctx.order.mint)
    if held is None or held.token_units <= 0:
        raise _Fail("no_position", f"mint={ctx.order.mint} holding closed before fill")


def snapshot_probes(
    breakers: BreakerSet, probe_owners: dict[str, str], order_hash: str
) -> ProbeView:
    """Drop probe owners whose probe is no longer in flight, then read the half-open breakers."""
    for name in list(probe_owners):
        if not breakers.by_name(name).probe_inflight:
            del probe_owners[name]
    half_all = [name for name in BREAKER_NAMES if breakers.by_name(name).half_open]
    # Probes this order already holds are its own: its repeat checks reuse them.
    owned = [name for name in half_all if probe_owners.get(name) == order_hash]
    return ProbeView(
        half_all=half_all,
        owned=owned,
        half_avail=breakers.half_open_breakers(),
    )


def claim_probe(
    breakers: BreakerSet,
    probe_owners: dict[str, str],
    ctx: _StepCtx,
    order_hash: str,
    probes: ProbeView,
) -> None:
    """A buy during a half-open breaker reuses its own probe, claims a free one, or is refused."""
    if not (ctx.is_buy and not ctx.is_exit_sell and probes.half_all):
        return
    if probes.owned:
        ctx.probe = True
    elif probes.half_avail and breakers.admit_probe(probes.half_avail[0]):
        probe_owners[probes.half_avail[0]] = order_hash
        ctx.probe = True
    else:
        raise _Fail("breaker_open", "probe inflight")
