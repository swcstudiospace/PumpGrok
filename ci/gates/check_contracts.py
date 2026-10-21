#!/usr/bin/env python3
"""Gate G-4 — contract-first changes.

A breaking change to a contract surface requires a version bump, a migration note, and an
acknowledgement from every consumer listed in ownership.yaml.

Contracts are the only shared surface in a platform-decomposed system. A field rename that takes
thirty seconds in the API repo breaks the iOS client silently, and the break is found weeks later
by a user. Consumer acknowledgement moves that discovery to the pull request.

    python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/feat-x.yaml
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
    sys.exit("check_contracts: pyyaml is required (pip install pyyaml)")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "ownership.yaml"

REQUIRED_CHANGE_FIELDS = ["change_id", "proposed_by", "surface", "breaking", "version", "summary"]


def load_manifest(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"check_contracts: manifest not found at {path}")
    return yaml.safe_load(path.read_text())


def contract_surfaces(manifest: dict) -> list[str]:
    out = []
    for rule in manifest.get("ownership", []):
        if rule.get("contract_surface"):
            out.extend(p.strip() for p in rule["pattern"].split(","))
    return out


def _match(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    if "**/" in pattern:
        tail = pattern.split("**/", 1)[1]
        return fnmatch.fnmatch(path, tail) or any(
            fnmatch.fnmatch(path, f"{'*/' * n}{tail}") for n in range(1, 8)
        )
    if "/" not in pattern:
        return fnmatch.fnmatch(Path(path).name, pattern)
    return fnmatch.fnmatch(path, pattern)


def required_consumers(surface_path: str, manifest: dict) -> list[str]:
    for pattern, consumers in (manifest.get("contract_consumers") or {}).items():
        if _match(pattern, surface_path):
            return list(consumers)
    return []


def declared_surfaces(doc: dict) -> list[str]:
    """Every surface the change document claims, from 'surface' plus optional 'surfaces'."""
    out: list[str] = []
    one = doc.get("surface")
    if isinstance(one, str) and one.strip():
        out.append(one.strip())
    for extra in doc.get("surfaces") or []:
        if str(extra).strip():
            out.append(str(extra).strip())
    return out


def _surface_match(pattern: str, path: str) -> bool:
    """Stricter than _match: no basename fallback.

    _match() falls back to comparing basenames for a pattern with no '/', which is right for
    ownership globs and wrong here — 'openapi.yaml' must not cover 'contracts/openapi.yaml'.
    A declared surface is an exact path, a directory glob, or an explicit glob.
    """
    if pattern == path:
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatch(path, pattern)


def changed_files(base: str) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"],
                         capture_output=True, text=True, cwd=REPO_ROOT)
    return [l for l in out.stdout.splitlines() if l.strip()]


def touched_contracts(files: list[str], manifest: dict) -> list[str]:
    surfaces = contract_surfaces(manifest)
    return [f for f in files if any(_match(p, f) for p in surfaces)]


def check_change_doc(doc: dict, manifest: dict, touched: list[str] | None = None,
                     change_path: Path | None = None) -> list[str]:
    problems: list[str] = []

    for field in REQUIRED_CHANGE_FIELDS:
        if field not in doc:
            problems.append(f"missing required field '{field}'")
    if problems:
        return problems

    surface = doc["surface"]
    breaking = doc["breaking"]
    acks = {a["bot"]: a for a in doc.get("acknowledgements", []) if isinstance(a, dict)}

    # The change document must actually describe THIS change.
    #
    # Without this, a document left in contracts/changes/ after its own change merged will
    # validate a later, unrelated change: the caller selects a document by globbing the
    # directory, the gate reads it, and a breaking change with no acknowledgements passes on
    # the strength of a stale non-breaking record. The document's declared surfaces are the
    # only thing tying it to a diff, so they have to cover the diff.
    surfaces = declared_surfaces(doc)
    if touched is not None and surfaces:
        # Compare the change document by resolved path, not by string: the gate may be run
        # from a subdirectory, and a document that failed to match its own entry in the diff
        # would be reported as an undeclared surface against itself.
        def _is_change_doc(rel: str) -> bool:
            if change_path is None:
                return False
            try:
                return (REPO_ROOT / rel).resolve() == change_path.resolve()
            except OSError:
                return False

        # contracts/changes/ is the protocol's own bookkeeping — change documents, the
        # template, the archive — not a surface any consumer builds against. Requiring a
        # document to declare those paths would mean every change that archives the previous
        # document, which is the normal flow, has to list the archived file as a surface it
        # changed. Noise, and it would push people toward a `contracts/**` wildcard that
        # satisfies the check while describing nothing.
        def _is_bookkeeping(rel: str) -> bool:
            return rel == "contracts/changes" or rel.startswith("contracts/changes/")

        undeclared = [
            t for t in touched
            if not _is_change_doc(t) and not _is_bookkeeping(t)
            and not any(_surface_match(p, t) for p in surfaces)
        ]
        if undeclared:
            problems.append(
                "change document does not cover every contract surface in this change.\n"
                "      Declared: " + ", ".join(surfaces) + "\n"
                "      Undeclared: " + ", ".join(undeclared) + "\n"
                "      Either this is the wrong change document — a stale one selected from\n"
                "      contracts/changes/ validates a change it never described — or the\n"
                "      paths above belong in its 'surfaces:' list."
            )

    needed = list(doc.get("consumers_required") or [])
    if not needed:
        for surf in surfaces:
            for consumer in required_consumers(surf, manifest):
                if consumer not in needed:
                    needed.append(consumer)
    if not needed:
        problems.append(
            f"no consumers resolved for surface '{surface}' — "
            "either the surface is wrong or contract_consumers needs an entry"
        )

    if breaking:
        # Every consumer must positively acknowledge.
        for consumer in needed:
            ack = acks.get(consumer)
            if ack is None:
                problems.append(
                    f"BREAKING change with no acknowledgement from '{consumer}'\n"
                    f"      A breaking change needs every consumer to confirm it can implement it."
                )
            elif not ack.get("ack"):
                note = ack.get("note", "no reason given")
                problems.append(f"consumer '{consumer}' REJECTED the change: {note}")

        if not doc.get("migration_note"):
            problems.append(
                "BREAKING change with no 'migration_note' — "
                "consumers need to know what to do, and why"
            )

        version = str(doc["version"])
        try:
            major = int(version.split(".")[0])
        except (ValueError, IndexError):
            problems.append(f"version '{version}' is not semver")
            major = None
        if major == 0:
            problems.append(
                f"BREAKING change at version '{version}' — a breaking change needs a major bump"
            )
        elif doc.get("previous_version"):
            try:
                prev_major = int(str(doc["previous_version"]).split(".")[0])
                if major <= prev_major:
                    problems.append(
                        f"BREAKING change but major version did not increase "
                        f"({doc['previous_version']} -> {version})"
                    )
            except (ValueError, IndexError):
                pass

    else:
        # Non-breaking: acknowledgements are informational, but a rejection still blocks.
        for consumer, ack in acks.items():
            if ack.get("ack") is False:
                problems.append(
                    f"consumer '{consumer}' rejected this non-breaking change: "
                    f"{ack.get('note', 'no reason given')}"
                )

    # The semantic-change trap: nothing detects a field whose meaning changed but whose
    # name and type did not. Require an explicit declaration either way.
    if "semantic_changes" not in doc:
        problems.append(
            "missing 'semantic_changes' — declare any field whose MEANING changed without its "
            "name or type changing, or set it to [] to confirm there are none. "
            "No tool can detect these."
        )

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate G-4: contract-first changes")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--change", type=Path, help="Path to the contract change document")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--files", nargs="*", help="Explicit file list instead of a git diff")
    args = ap.parse_args()

    manifest = load_manifest(args.manifest)
    files = args.files if args.files is not None else changed_files(args.base)
    touched = touched_contracts(files, manifest)

    if not touched:
        print("G-4 PASS — no contract surfaces touched")
        return 0

    print(f"G-4 — {len(touched)} contract surface file(s) touched:")
    for t in touched:
        print(f"    {t}")

    if not args.change:
        print(
            "\nG-4 FAIL — contract surfaces changed but no change document supplied.\n"
            "  A contract change needs a change document declaring whether it is breaking,\n"
            "  its version, its consumers, and their acknowledgements.\n"
            "  See docs/cross-bot-protocol.md §2",
            file=sys.stderr,
        )
        return 1

    if not args.change.exists():
        print(f"G-4 FAIL — change document not found: {args.change}", file=sys.stderr)
        return 1

    try:
        doc = yaml.safe_load(args.change.read_text())
    except yaml.YAMLError as exc:
        print(f"G-4 FAIL — change document is not valid YAML: {exc}", file=sys.stderr)
        return 1

    problems = check_change_doc(doc, manifest, touched=touched, change_path=args.change)

    if problems:
        print(f"\nG-4 FAIL — {args.change}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n  See docs/cross-bot-protocol.md and skills/contract-first-changes/SKILL.md",
              file=sys.stderr)
        return 1

    kind = "BREAKING" if doc["breaking"] else "non-breaking"
    n_acks = sum(1 for a in doc.get("acknowledgements", []) if a.get("ack"))
    print(f"\nG-4 PASS — {doc['change_id']}: {kind}, v{doc['version']}, {n_acks} acknowledgement(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
