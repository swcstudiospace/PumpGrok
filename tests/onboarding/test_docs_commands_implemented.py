"""Every documented `pumpgrok` command is a real parser path, and the onboarding docs
state the rules.

Commands are read from code spans and fenced blocks in the onboarding skills, the CHIEF prompt, its
generated agent file and the event runbook. Prose that mentions the program name is not a command.
A command with `<placeholder>` values must walk the real argparse tree; a command without
placeholders must also parse in full, with every required flag present.
"""

from __future__ import annotations

import argparse
import re
import shlex
from pathlib import Path

import pytest

from pumpgrok.cli.errors import UsageError
from pumpgrok.cli.parsing import build_parser

REPO_ROOT = Path(__file__).resolve().parents[2]

SETUP_SKILL = "skills/pumpgrok-setup/SKILL.md"
CONNECTIONS_SKILL = "skills/tool-connections/SKILL.md"
DOCTOR_SKILL = "skills/desk-doctor/SKILL.md"
CHIEF_PROMPT = "prompts/bot-00-chief.xml"
CHIEF_AGENT = "agents/chief.md"
EVENTS_RUNBOOK = "docs/runbooks/events.md"

DOC_FILES = (
    SETUP_SKILL,
    CONNECTIONS_SKILL,
    DOCTOR_SKILL,
    CHIEF_PROMPT,
    CHIEF_AGENT,
    EVENTS_RUNBOOK,
)

# A `pumpgrok` word followed by whitespace and a verb or flag. `pumpgrok-setup` and paths such as
# `src/pumpgrok/...` do not match: the name must not follow a word character, dot, slash or dash.
COMMAND_RE = re.compile(r"(?<![\w./-])pumpgrok(?=\s+[A-Za-z<-])")
SPAN_RE = re.compile(r"`([^`]+)`")
FENCE_COMMAND_RE = re.compile(r"\s*(?:uv run )?pumpgrok\s")
TRAILING_PUNCTUATION = ".,:;)'\""

# Command prefixes the setup skill must document. Each one must start a documented command.
SETUP_REQUIRED_COMMANDS = (
    "doctor --json",
    "onboarding init-key",
    "onboarding list",
    "onboarding access --seat",
    "onboarding revoke --seat",
    "onboarding rpc",
    "run --mode paper --once --replay",
    "run --mode paper --serve --replay",
    "state autonomy",
)

# Statements the docs must make. Compared case-insensitively after whitespace is collapsed.
SETUP_PHRASES = (
    "paper never asks for or reads a wallet, a private key or a seed phrase",
    "no secret is echoed",
    "PUMPGROK_GROK__API_KEY",
    "PUMPGROK_GROK_GATEWAY__ENABLED",
    "non-empty",
    "source=replay",
    "source=paper",
    "clone",
    "uv sync",
    "onboarding rpc",
    "configured endpoint",
    "missing decisions",
    "review gates stay explicit",
    "the desk starts in research",
)

CONNECTIONS_PHRASES = (
    "paper never connects a wallet",
    "separate",
    "typed",
    "public address",
    "explicit",
    "never accept, store, or request a seed phrase or private key",
    "onboarding rpc",
)

CHIEF_PHRASES = (
    "paper never asks for or reads a wallet, a private key or a seed phrase",
    "onboarding list",
    "onboarding access",
    "run --mode paper --once --replay",
)

EVENTS_PHRASES = (
    "paper start refused",
    "onboarding list",
    "run --mode paper --serve --replay",
)

SECRET_SHAPES = (
    re.compile(r"\bxai-[A-Za-z0-9]{10,}"),
    re.compile(r"\b(?:PUMPGROK_GROK__API_KEY|PUMPGROK_CONFIRMATION_KEY)\s*=\s*(?!<)\S"),
)


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _normalized(rel: str) -> str:
    return re.sub(r"\s+", " ", _read(rel)).lower()


def _command_text(candidate: str) -> str | None:
    """The command after `pumpgrok` in one candidate line or span, or None when there is none."""
    match = COMMAND_RE.search(candidate)
    if match is None:
        return None
    rest = candidate[match.end() :]
    for stop in ("|", "&", ";", " #"):
        rest = rest.split(stop, 1)[0]
    tokens = shlex.split(rest)
    if tokens:
        tokens[-1] = tokens[-1].rstrip(TRAILING_PUNCTUATION)
    return " ".join(tokens)


def _extract_commands(text: str) -> list[str]:
    """Every documented command: code spans anywhere, and fenced-block lines that
    begin a command."""
    found: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        candidates = [m.group(1) for m in SPAN_RE.finditer(line)]
        if in_fence and FENCE_COMMAND_RE.match(line):
            candidates.append(line.strip())
        for candidate in candidates:
            command = _command_text(candidate)
            if command is not None:
                found.append(command)
    return found


def _subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _walk_error(tokens: list[str]) -> str | None:
    """Walk the real parser tree: each verb and flag must exist, and the verb path must end."""
    parser = build_parser()
    pending_value = False
    for token in tokens:
        if pending_value:
            pending_value = False
            continue
        if token.startswith("--"):
            name = token.split("=", 1)[0]
            action = parser._option_string_actions.get(name)
            if action is None:
                return f"unknown option {name!r}"
            pending_value = action.nargs != 0 and "=" not in token
            continue
        subs = _subparsers(parser)
        if subs is None:
            continue
        if token not in subs.choices:
            return f"unknown verb {token!r}"
        parser = subs.choices[token]
    if _subparsers(parser) is not None:
        return "incomplete command: a subcommand is required"
    return None


def _full_parse_error(tokens: list[str]) -> str | None:
    """Parse a placeholder-free command in full: required flags and value types must hold."""
    try:
        build_parser().parse_args(tokens)
    except SystemExit as exc:
        return None if exc.code == 0 else f"argparse exit {exc.code}"
    except UsageError as exc:
        return str(exc)
    return None


def _command_problems(command: str) -> list[str]:
    tokens = shlex.split(command)
    problems: list[str] = []
    walk = _walk_error(tokens)
    if walk is not None:
        problems.append(walk)
    if not any("<" in token for token in tokens):
        full = _full_parse_error(tokens)
        if full is not None:
            problems.append(full)
    return problems


@pytest.mark.parametrize("rel", DOC_FILES)
def test_documented_commands_exist_in_the_parser(rel: str) -> None:
    commands = _extract_commands(_read(rel))
    assert commands, f"{rel}: no pumpgrok command documented"
    failures = {cmd: _command_problems(cmd) for cmd in commands}
    failures = {cmd: problems for cmd, problems in failures.items() if problems}
    assert not failures, f"{rel}: documented commands not in the real parser: {failures}"


def test_setup_documents_every_onboarding_command() -> None:
    commands = _extract_commands(_read(SETUP_SKILL))
    missing = [
        prefix
        for prefix in SETUP_REQUIRED_COMMANDS
        if not any(cmd == prefix or cmd.startswith(prefix + " ") for cmd in commands)
    ]
    assert not missing, f"{SETUP_SKILL} lacks commands: {missing}"


@pytest.mark.parametrize(
    ("rel", "phrases"),
    [
        (SETUP_SKILL, SETUP_PHRASES),
        (CONNECTIONS_SKILL, CONNECTIONS_PHRASES),
        (CHIEF_PROMPT, CHIEF_PHRASES),
        (CHIEF_AGENT, CHIEF_PHRASES),
        (EVENTS_RUNBOOK, EVENTS_PHRASES),
    ],
)
def test_onboarding_docs_state_the_paper_and_gate_rules(
    rel: str, phrases: tuple[str, ...]
) -> None:
    text = _normalized(rel)
    missing = [phrase for phrase in phrases if phrase.lower() not in text]
    assert not missing, f"{rel} lacks required statements: {missing}"


@pytest.mark.parametrize("rel", DOC_FILES)
def test_docs_never_show_a_secret_value(rel: str) -> None:
    text = _read(rel)
    hits = [pattern.pattern for pattern in SECRET_SHAPES if pattern.search(text)]
    assert not hits, f"{rel} shows a secret-shaped value: {hits}"
