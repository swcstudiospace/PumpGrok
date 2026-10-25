"""Operator registry wiring: seat resolution and tool-call tails."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pumpgrok.cli.codes import EXIT_OK, EXIT_UNFLATTENED, _TOOLS_HELP
from pumpgrok.cli.errors import UsageError, _not_implemented, _say, _tool_error
from pumpgrok.config.settings import Settings, load_settings
from pumpgrok.contracts.projection import short_to_seat
from pumpgrok.core.errors import PumpgrokError
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.replay.clock import WallClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.tools import build_operator_registry

log = logging.getLogger("pumpgrok.cli")


def _repo_root() -> Path:
    """Repo root for repo-anchored tool inputs (ownership.yaml, gates dir)."""
    return Path(__file__).resolve().parents[3]


def _seat_manifest_id(seat: str) -> str:
    """Map a CLI --seat to a roster seat id.

    Accepts a roster short (chief, scout, ...), the operator seat ``desk``
    (the console acts under the supervisor seat until Phase 4 operator
    identity lands with approvals), or a full seat id (bot-04-sniper).
    Unknown values are usage errors. The sniper/exit string filter in
    :func:`pumpgrok.cli.errors._refuse_forbidden_seat` stays a policy layer; the control is the
    registry grant plus the approval record (R63).
    """
    if seat == "desk":
        return "bot-00-chief"
    shorts = short_to_seat()
    if seat in shorts:
        return shorts[seat]
    return seat


async def _with_tools(
    verb: str,
    seat: str,
    settings: Settings,
    capabilities: Sequence[str],
    use: Callable[[list[Tool]], Awaitable[int]],
) -> int:
    """Build the operator registry, resolve ``seat``, find every capability (I1).

    Each find refusal prints the JSON envelope with the mapped exit before
    anything runs. Otherwise ``use`` receives the resolved tools and decides:
    call one (functional backends), fail on the approval gate (paper), or
    return not-yet-implemented (Phase 4 orchestration). No tool implementation
    is ever imported or called directly here; everything goes through find().
    """
    reg, manifests, client = build_operator_registry(
        data_dir=Path("var") / "desk",
        repo_root=_repo_root(),
        settings=settings,
        ledger_path=PAPER_LEDGER_PATH,
        seed=settings.replay.seed,
    )
    try:
        try:
            manifest = manifests[_seat_manifest_id(seat)]
        except KeyError:
            raise UsageError(f"bad --seat {seat!r}: unknown seat") from None
        factory = IdFactory(WallClock(), make_rng(settings.replay.seed))
        with bind_correlation(CorrelationId.new(factory)):
            tools: list[Tool] = []
            for capability in capabilities:
                try:
                    tools.append(
                        reg.find(
                            capability,
                            max_side_effect=SideEffect.PAPER_WRITE,
                            bot=manifest,
                        )
                    )
                except PumpgrokError as exc:
                    return _tool_error(verb, exc.code, exc.message)
            return await use(tools)
    finally:
        await client.aclose()


def _run_wired(
    verb: str,
    seat: str,
    settings: Settings,
    capabilities: Sequence[str],
    use: Callable[[list[Tool]], Awaitable[int]],
) -> int:
    """Run one wired verb: registry build, find (I1), then the verb tail."""
    return asyncio.run(_with_tools(verb, seat, settings, capabilities, use))


def _unflattened_lines(dumped: dict[str, Any]) -> list[str]:
    """One stderr line per flatten outcome that did not close, and per run that did not finish.

    A position with no outcome row (flatten ``blocked`` or ``unavailable``) is named by the run
    status instead, since nothing was closed for it either.
    """
    lines: list[str] = []
    for outcome in dumped.get("flatten_outcomes", []):
        if outcome.get("status") != "closed":
            lines.append(
                "killswitch flatten: UNFLATTENED "
                f"mint={outcome.get('mint')} ticket_id={outcome.get('ticket_id')} "
                f"status={outcome.get('status')} detail={outcome.get('detail')}"
            )
    run_status = dumped.get("flatten_status")
    if run_status in ("blocked", "unavailable"):
        lines.append(
            "killswitch flatten: UNFLATTENED "
            f"flatten_status={run_status} detail={dumped.get('flatten_detail')}"
        )
    return lines


def _call_use(
    verb: str,
    index: int,
    fields: dict[str, Any],
    check: Callable[[dict[str, Any]], list[str]] | None = None,
) -> Callable[[list[Tool]], Awaitable[int]]:
    """Tail that validates one input through the tool spec and calls the tool (B5).

    The input model comes from the resolved spec, so the CLI never imports a
    tool module. Success prints the output JSON; PumpgrokError (including the
    absent-backend not_yet_implemented) prints the envelope with the exit map.
    """

    async def use(tools: list[Tool]) -> int:
        tool = tools[index]
        try:
            payload = tool.spec.input_model(**fields)
        except ValidationError as exc:
            return _tool_error(
                verb,
                "invalid_arguments",
                f"invalid arguments for {tool.spec.name}: {exc.errors()[0]['msg']}",
            )
        try:
            out = await tool(payload)
        except PumpgrokError as exc:
            return _tool_error(verb, exc.code, exc.message)
        dumped = out.model_dump(mode="json")
        _say(sys.stdout, json.dumps(dumped))
        if check is not None:
            problems = check(dumped)
            if problems:
                _say(sys.stderr, *problems)
                return EXIT_UNFLATTENED
        return EXIT_OK

    return use


def _skip_use(verb: str) -> Callable[[list[Tool]], Awaitable[int]]:
    """Tail for Phase 4 orchestration verbs: find (I1) proves the path, then exit 5."""

    async def use(_tools: list[Tool]) -> int:
        return _not_implemented(verb)

    return use


def _find_only(verb: str, seat: str, settings: Settings, capabilities: Sequence[str]) -> int:
    """Section-12 verb whose multi-tool orchestration lands in Phase 4 (B5 partial).

    Every catalog tool resolves through find (I1 enforced; a wrong seat prints
    the refusal envelope instead of 5), then the verb returns the
    not-yet-implemented envelope because calling would need network backends
    or Phase 4 orchestration. No tool implementation is called.
    """
    return _run_wired(verb, seat, settings, capabilities, _skip_use(verb))


def _tools_schema(tool_id: str) -> int:
    """Hidden developer verb (B8): print one catalog tool JSON schema, exit 0."""

    async def _schema() -> int:
        settings = load_settings()
        reg, _, client = build_operator_registry(
            data_dir=Path("var") / "desk",
            repo_root=_repo_root(),
            settings=settings,
            ledger_path=PAPER_LEDGER_PATH,
            seed=settings.replay.seed,
        )
        try:
            try:
                spec = reg.spec(tool_id)
            except KeyError:
                return _tool_error(f"tools {tool_id}", "unknown_tool", f"unknown tool: {tool_id}")
            _say(
                sys.stdout,
                json.dumps(
                    {
                        "name": spec.name,
                        "description": spec.description,
                        "input_schema": spec.input_model.model_json_schema(),
                        "output_schema": spec.output_model.model_json_schema(),
                        "side_effect": str(spec.side_effect),
                        "timeout_s": spec.timeout_s,
                        "rate_limit_key": spec.rate_limit_key,
                        "requires_approval": spec.requires_approval,
                        "idempotent": spec.idempotent,
                        "backend": spec.backend,
                    }
                ),
            )
            return EXIT_OK
        finally:
            await client.aclose()

    return asyncio.run(_schema())


def _tools_entry(rest: list[str]) -> int:
    """Route the hidden `tools` verb without argparse (B8: absent from top help)."""
    if not rest:
        raise UsageError("tools requires a tool id (try `pumpgrok tools exec.quote --help`)")
    if rest in (["--help"], ["-h"]):
        _say(sys.stdout, *_TOOLS_HELP)
        return EXIT_OK
    tool_id = rest[0]
    if tool_id.startswith("-"):
        raise UsageError(f"unexpected arguments for `tools`: {' '.join(rest)}")
    if rest[1:] not in ([], ["--help"], ["-h"]):
        raise UsageError(f"unexpected arguments for `tools {tool_id}`: {' '.join(rest[1:])}")
    return _tools_schema(tool_id)


def _verb_label(args: argparse.Namespace) -> str:
    """Audit label for a find-only verb: the verb plus its subcommand, when it has one."""
    verb: str = args.verb
    cmd: str | None = getattr(args, "cmd", None)
    return verb if cmd is None else f"{verb} {cmd}"
