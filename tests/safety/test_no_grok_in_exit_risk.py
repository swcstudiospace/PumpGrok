"""Exit rules and risk never import the Grok gateway (T-14-06 scope)."""

import pathlib

FORBIDDEN = ("pumpgrok.grok", "pumpgrok/grok", "from pumpgrok.grok", "import grok")
WATCHED = [
    pathlib.Path("src/pumpgrok/supervisor/exit_rules.py"),
    *pathlib.Path("src/pumpgrok/risk").rglob("*.py"),
    *pathlib.Path("src/pumpgrok/execution").rglob("*.py"),
]


def test_no_grok_import_in_exit_risk_execution() -> None:
    offenders = []
    for path in WATCHED:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in source:
                offenders.append(f"{path}:{token}")
    assert offenders == [], offenders
