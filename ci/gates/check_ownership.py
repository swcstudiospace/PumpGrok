#!/usr/bin/env python3
"""Gate G-1 — path ownership.

A bot may only modify paths it owns in ownership.yaml. A path matching no pattern is UNOWNED and
fails the build: an unowned file is exactly where two bots collide silently, so treating it as
default-allow hides the collision until it produces a conflict nobody can adjudicate.

    python3 ci/gates/check_ownership.py --bot bot-04-sniper --base origin/main
    python3 ci/gates/check_ownership.py --validate-manifest
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("check_ownership: pyyaml is required (pip install pyyaml)")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "ownership.yaml"


def load_manifest(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"check_ownership: manifest not found at {path}")
    with path.open() as fh:
        return yaml.safe_load(fh)


def _segments_match(pattern: str, path: str) -> bool:
    """Match one '/'-separated segment at a time: '*' and '?' never cross a '/'."""
    pat_parts = pattern.split("/")
    path_parts = path.split("/")
    return len(pat_parts) == len(path_parts) and all(
        fnmatch.fnmatch(seg, pat) for pat, seg in zip(pat_parts, path_parts, strict=True)
    )


def _match(pattern: str, path: str) -> bool:
    """gitignore-ish glob matching.

    fnmatch treats '*' as matching '/', which would make 'web/*' match 'web/a/b.ts'. We handle
    the '**' case explicitly and anchor the rest so 'web/*' does not swallow subdirectories.
    """
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")

    if "**/" in pattern:
        # 'mine/**/*.py' keeps its 'mine/' anchor: the head must be a whole directory prefix, so
        # 'other/private.py' never matches. '**/*.rs' has an empty head and matches at any depth.
        # The tail must match some suffix of the remainder: 'a/b/c.rs' and 'c.rs' both match.
        head, tail = pattern.split("**/", 1)
        if head and not head.endswith("/"):
            return False
        if not path.startswith(head):
            return False
        parts = path[len(head) :].split("/")
        return any(_segments_match(tail, "/".join(parts[i:])) for i in range(len(parts)))

    if "/" not in pattern:
        # A bare pattern like 'Cargo.toml' or 'Dockerfile*' matches at any depth.
        return fnmatch.fnmatch(Path(path).name, pattern)

    return _segments_match(pattern, path)


def resolve_owner(path: str, manifest: dict) -> tuple[str | None, bool]:
    """Return (owner, is_contract_surface). Last matching rule wins."""
    owner: str | None = None
    contract = False
    for rule in manifest.get("ownership", []):
        for pattern in [p.strip() for p in rule["pattern"].split(",")]:
            if _match(pattern, path):
                owner = rule["owner"]
                contract = bool(rule.get("contract_surface"))
                break
    return owner, contract


def changed_files(base: str) -> list[str]:
    # --no-renames: with rename detection, --name-only lists only a rename's destination, so the
    # source owner would never be checked. Both sides of a move must reach classify_files.
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
    except subprocess.CalledProcessError as exc:
        sys.exit(f"check_ownership: git diff failed: {exc.stderr}")
    return [line for line in out.stdout.splitlines() if line.strip()]


def tracked_paths() -> list[str]:
    """Every path git tracks, repo-relative. The self-test walks this, not the working tree."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
    except subprocess.CalledProcessError as exc:
        sys.exit(f"check_ownership: git ls-files failed: {exc.stderr}")
    return [p for p in out.stdout.split("\0") if p]


def self_test(manifest: dict, paths: list[str]) -> list[str]:
    """R36: every tracked path resolves to exactly one declared owner.

    resolve_owner() returns a single owner per path by construction (last match wins), so the
    failure modes left are a path no rule claims and an owner the manifest never declares.
    Overlapping rules are deliberate (a general rule first, an override after), so overlap
    alone is not reported.
    """
    bots = set(manifest.get("bots", {}))
    problems: list[str] = []
    for path in paths:
        owner, _ = resolve_owner(path, manifest)
        if owner is None:
            problems.append(f"UNOWNED  {path}")
        elif owner not in bots:
            problems.append(f"UNDECLARED OWNER '{owner}'  {path}")
    return problems


def validate_manifest(manifest: dict, paths: list[str]) -> int:
    """Self-check: rules name declared bots, no duplicate patterns, every tracked path owned."""
    problems: list[str] = []
    bots = set(manifest.get("bots", {}))

    seen: set[str] = set()
    for rule in manifest.get("ownership", []):
        if rule["owner"] not in bots:
            problems.append(f"rule '{rule['pattern']}' names undeclared bot '{rule['owner']}'")
        for pattern in [p.strip() for p in rule["pattern"].split(",")]:
            if pattern in seen:
                problems.append(f"duplicate pattern '{pattern}' — later rule silently wins")
            seen.add(pattern)

    for surface, consumers in (manifest.get("contract_consumers") or {}).items():
        for consumer in consumers:
            if consumer not in bots:
                problems.append(
                    f"contract_consumers['{surface}'] names undeclared bot '{consumer}'"
                )

    problems.extend(self_test(manifest, paths))

    if problems:
        print("G-1 manifest validation FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(
        f"G-1 manifest OK — {len(bots)} bots, {len(manifest['ownership'])} rules; "
        f"{len(paths)} tracked path(s), each with one declared owner"
    )
    return 0


def classify_files(
    files: list[str], manifest: dict, bot: str
) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """Sort changed paths into unowned, foreign-owned, and contract-surface buckets."""
    unowned: list[str] = []
    foreign: list[tuple[str, str]] = []
    contracts: list[str] = []
    for path in files:
        owner, is_contract = resolve_owner(path, manifest)
        if owner is None:
            unowned.append(path)
        elif owner != bot:
            # Ownership is checked before the contract classification: a contract
            # surface owned by another seat is FOREIGN, not a NOTE. Otherwise a
            # non-owner edit to a shared contract passes G-1 on its flag alone.
            foreign.append((path, owner))
        elif is_contract:
            contracts.append(path)
    return unowned, foreign, contracts


def report_ownership_failure(bot: str, unowned: list[str], foreign: list[tuple[str, str]]) -> int:
    """Print the G-1 failure detail. Always returns 1."""
    print(f"G-1 FAIL — {bot}", file=sys.stderr)
    for path in unowned:
        print(f"  UNOWNED  {path}", file=sys.stderr)
        print(
            "           No ownership rule matches. Extend ownership.yaml (bot-02-risk).",
            file=sys.stderr,
        )
    for path, owner in foreign:
        print(f"  FOREIGN  {path}  (owned by {owner})", file=sys.stderr)
    if foreign:
        print(
            "\n  Cross-bot work goes through docs/cross-bot-protocol.md, not direct edits.",
            file=sys.stderr,
        )
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate G-1: path ownership")
    ap.add_argument("--bot", help="Bot id making the change")
    ap.add_argument("--base", default="origin/main", help="Base ref for the diff")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--validate-manifest", action="store_true")
    ap.add_argument("--files", nargs="*", help="Explicit file list instead of a git diff")
    args = ap.parse_args()

    manifest = load_manifest(args.manifest)

    if args.validate_manifest:
        return validate_manifest(manifest, tracked_paths())

    if not args.bot:
        sys.exit("check_ownership: --bot is required unless --validate-manifest")
    if args.bot not in manifest.get("bots", {}):
        sys.exit(f"check_ownership: unknown bot '{args.bot}'")

    files = args.files if args.files is not None else changed_files(args.base)
    if not files:
        print("G-1 PASS — no files changed")
        return 0

    unowned, foreign, contracts = classify_files(files, manifest, args.bot)

    if unowned or foreign:
        return report_ownership_failure(args.bot, unowned, foreign)

    print(f"G-1 PASS — {args.bot}: {len(files)} file(s) within owned paths")
    if contracts:
        print(f"  NOTE: {len(contracts)} contract surface file(s) touched — G-4 applies:")
        for path in contracts:
            print(f"    {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
