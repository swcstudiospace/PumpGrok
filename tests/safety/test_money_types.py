"""Money is integer base units, never float (INV-S-14).

Scope: ``src/pumpgrok/core/``, ``ledger/``, ``execution/``, ``risk/`` plus
``contracts/events/*.schema.json`` (R28).

- Every field or schema property whose name marks money (ends in
  ``_sol``, ``_lamports``, ``_tokens``, ``_base_units``, ``_cash``,
  ``_equity``, ``_fee``, ``_proceeds``, ``_cost_basis``, or equals
  ``cash``/``equity``/``fee``/``proceeds``/``cost_basis``) is ``int``
  (``MoneyInt`` is ``Annotated[int, Field(strict=True)]`` and counts).
- ``Decimal`` is allowed only for ratios and prices: names ending in
  ``_pct``, ``_fraction``, ``_ratio``, ``_price`` or starting with
  ``price``. Documented exceptions: ``RiskBudget.paper_equity_sol``
  (the one SOL-denominated config value, converted to lamports once at
  load, R28) and the raw phrase input of the ``_sol_to_lamports``
  boundary converter.
- No other annotation on a money name may be ``float``.
"""
import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "pumpgrok"

INT_MONEY_SUFFIXES = (
    "_sol",
    "_lamports",
    "_tokens",
    "_base_units",
    "_cash",
    "_equity",
    "_fee",
    "_proceeds",
    "_cost_basis",
)
INT_MONEY_NAMES = frozenset({"cash", "equity", "fee", "proceeds", "cost_basis"})

DECIMAL_SUFFIXES = ("_pct", "_fraction", "_ratio", "_price")

SCOPED_DIRS = ("core", "ledger", "execution", "risk")


def _is_money(name: str) -> bool:
    lowered = name.lower()
    return lowered in INT_MONEY_NAMES or lowered.endswith(INT_MONEY_SUFFIXES)


def _is_decimal_ok(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(DECIMAL_SUFFIXES) or lowered.startswith("price")


def _annotation(node: ast.AST) -> str:
    """Base annotation name, unwrapping Annotated[...] to its first argument."""
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id == "Annotated":
            inner = node.slice.elts[0] if isinstance(node.slice, ast.Tuple) else node.slice
            return _annotation(inner)
        return node.value.id
    text = ast.unparse(node)
    return text.split("[", maxsplit=1)[0].split("|", maxsplit=1)[0].strip().strip("'\"")


# Boundary converters that parse a human SOL string once (R28). The `str`
# argument is the raw phrase input; the return is int.
STR_BOUNDARY_CONVERTERS = frozenset({"_sol_to_lamports"})


def _scan_file(path: Path) -> list[str]:
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = path.name
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    owners: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in list(node.args.args) + list(node.args.kwonlyargs):
                owners[id(arg)] = node.name
    for node in ast.walk(tree):
        target: ast.AST | None = None
        annotation: ast.AST | None = None
        boundary = False
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, annotation = node.target, node.annotation
        elif isinstance(node, ast.arg) and node.annotation is not None:
            target, annotation = node, node.annotation
            boundary = owners.get(id(node)) in STR_BOUNDARY_CONVERTERS
        if target is None or annotation is None:
            continue
        name = target.id if isinstance(target, ast.Name) else target.arg
        if not _is_money(name):
            continue
        if name == "paper_equity_sol" and path.stem == "risk_budget":
            # The one documented SOL-denominated Decimal config value (R28).
            continue
        kind = _annotation(annotation)
        if boundary and kind == "str":
            continue
        if kind == "Decimal":
            if not _is_decimal_ok(name):
                found.append(f"{rel}:{node.lineno}: Decimal on non-ratio money {name}")
        elif kind == "float":
            found.append(f"{rel}:{node.lineno}: float on money {name}")
        elif kind not in ("int", "MoneyInt"):
            # MoneyInt is Annotated[int, Field(strict=True)] (R28).
            found.append(f"{rel}:{node.lineno}: {kind} on money {name}")
    return found


def _scan_schema(path: Path) -> list[str]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    schema = json.loads(path.read_text(encoding="utf-8"))
    found: list[str] = []

    def visit(node: object, trail: str) -> None:
        if not isinstance(node, dict):
            return
        types: set[str] = set()
        raw = node.get("type")
        if isinstance(raw, str):
            types.add(raw)
        for variant in node.get("anyOf", []) or []:
            if isinstance(variant, dict) and isinstance(variant.get("type"), str):
                types.add(str(variant["type"]))
        name = trail.rsplit("/", maxsplit=1)[-1]
        if _is_money(name) and "number" in types:
            found.append(f"{rel}:{trail}: number-typed money")
        for key in ("properties", "$defs", "definitions"):
            branch = node.get(key)
            if isinstance(branch, dict):
                for child, sub in branch.items():
                    visit(sub, f"{trail}/{child}" if trail else str(child))
        for key in ("items", "additionalProperties"):
            branch = node.get(key)
            if isinstance(branch, dict):
                visit(branch, trail + "[]")

    visit(schema, "")
    return found


def find_violations() -> list[str]:
    found: list[str] = []
    for dirname in SCOPED_DIRS:
        root = SRC / dirname
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            found.extend(_scan_file(path))
    schemas = REPO_ROOT / "contracts" / "events"
    for path in sorted(schemas.glob("*.schema.json")):
        found.extend(_scan_schema(path))
    return found


def test_no_float_money_fields() -> None:
    """INV-S-14: money is int, Decimal only for ratios and prices."""
    assert find_violations() == []


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("class M(BaseModel):\n    size_lamports: int\n", False),
        ("class M(BaseModel):\n    size_lamports: float\n", True),
        ("class M(BaseModel):\n    price_impact_pct: Decimal\n", False),
        ("class M(BaseModel):\n    paper_equity_sol: Decimal\n", False),
        ("class M(BaseModel):\n    timeout_s: float\n", False),
    ],
)
def test_probe_is_classified(tmp_path: Path, source: str, flagged: bool) -> None:
    package = tmp_path / "risk_budget.py"
    package.write_text(f"from pydantic import BaseModel\n{source}", encoding="utf-8")
    assert bool(_scan_file(package)) is flagged
