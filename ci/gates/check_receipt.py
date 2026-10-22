#!/usr/bin/env python3
"""Gate G-2 — verification receipts.

The gate this system exists for. A coding agent's characteristic failure is not writing bad code;
it is writing plausible code, reasoning convincingly about why it works, and reporting success
without ever executing it.

This gate does not ask whether the bot verified something. It asks for the exit code, and CI can
re-run the command. A model can be confident about a claim it never tested; it cannot fabricate a
0 that survives re-execution.

    python3 ci/gates/check_receipt.py --receipt .receipts/task.json --bot bot-03-android
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Commands that produce a green result from work that never ran.
BYPASS_PATTERNS: list[tuple[str, str]] = [
    (r"--no-verify", "skips git hooks, including the secret scanner"),
    (r"--no-gpg-sign", "skips commit signing"),
    (r"-x\s+test", "excludes the Gradle test task"),
    (r"-x\s+check", "excludes the Gradle check task"),
    (r"--skip-tests?\b", "skips tests"),
    (r"-DskipTests", "skips tests"),
    (r"-skipTesting", "skips xcodebuild tests"),
    (r"\|\|\s*true", "masks a non-zero exit code"),
    (r"\|\|\s*exit\s+0", "masks a non-zero exit code"),
    (r";\s*exit\s+0\s*$", "masks a non-zero exit code"),
    (r"--passWithNoTests", "passes when no tests ran"),
    (r"--exitcode-only", "discards output needed for review"),
    (r"2>\s*/dev/null", "hides the error stream"),
    (r"--auto-approve", "applies infrastructure without a reviewed plan"),
    (r"--force\b", "forces past a safety check"),
    (r"-f\s+--", "forces past a safety check"),
    (r"--ignore-errors", "continues past failures"),
    (r"pytest.*--co\b", "collect-only: no tests actually ran"),
    (r"--dry-run(?!=server)", "dry run: nothing actually executed"),
    (r"PUMPGROK_LIVE_ENABLE=(?:1|true)", "sets the live flag inline"),
    (r"--i-understand-the-risk", "vendor live bypass flag"),
]

REQUIRED_FIELDS = ["task_id", "bot", "commands", "claims", "unverified"]

# A degraded-mode turn acknowledgement (loop skill §3) — a human saying "work this ticket even
# though the memory brief failed". Not to be confused with `approvals[]`: G-6's `check_rollback.py`
# pairs `approvals[]` entries to destructive operations by count, so a turn ack landing there either
# falsely fails a properly-approved destructive op or silently satisfies the count for one nobody
# approved. loop_acks stays out of approvals[] and check_rollback.py must never read it.
REQUIRED_LOOP_ACK_FIELDS = ["condition", "operation", "ack_id", "human_granted_by", "at", "scope"]
LOOP_ACK_CONDITIONS = {"brief_degraded", "brief_no_revision_marker"}
SEAT_ID_RE = re.compile(
    r"^\s*(?:bot-0[0-9](?:-[a-z0-9-]+)?|the desk"
    r"|desk-[a-z][a-z0-9-]*)\s*$",
    re.IGNORECASE,
)

# Claims whose wording asserts exhaustiveness. These need more than one piece of evidence.
EXHAUSTIVE_RE = re.compile(
    r"\b(all|every|everything|fully|completely|entirely|no regressions|nothing broke)\b",
    re.IGNORECASE,
)

# A failure that reads back as "the target could not be found" is not the same evidence as
# "the target was searched, end to end, and found empty" — "file missing" must not stand in
# for "every value empty" (Greptile P1, PR #45, "Thin evidence passes strict validation").
MISSING_TARGET_RE = re.compile(
    r"no such file or directory|cannot access|does not exist\b|\bnot found\b"
    r"|filenotfounderror|\benoent\b",
    re.IGNORECASE,
)

# A quoted argument is the text a command searches FOR, not text describing what happened
# when it ran — `grep "not found" build.log` exiting 1 means "not found" appears nowhere in
# build.log, which is valid negative evidence, not a missing-target error. Stripped out
# before MISSING_TARGET_RE looks at the command text itself (Greptile P1, PR #45, "Search
# text mistaken for error").
_QUOTED_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')


def _strip_quoted(text: str) -> str:
    return _QUOTED_RE.sub("", text)


# A command that only tests whether a path exists (test -e/-f, [ -e/-f ], stat, a bare ls)
# never looks at content, so it cannot be the "whole scope searched" evidence an exhaustive
# content claim needs, however its exit code lands. Anchored end-to-end so a command that
# CHAINS a real content search after the existence check — `test -f X && grep ... X` failing
# because grep found nothing in an X that does exist — is not misread as existence-only just
# because it starts with one (Greptile P1, PR #45, "Compound content searches rejected").
EXISTENCE_ONLY_RE = re.compile(
    r"^\s*(?:test\s+-[a-z]\s+\S+|\[\s+-[a-z]\s+\S+\s+\]|stat\s+\S+|ls\s+[^|;&]*)\s*$",
    re.IGNORECASE,
)

# The narrower probe used specifically to corroborate a quiet-search sibling (see
# _is_positive_existence_check below). Covers `-f`/`-e`/`-d`/`-r` — the `test`/`[` flags that
# actually test something ON DISK (file exists, path exists, directory, readable) — because
# `test -n`/`-z` test whether a STRING is non-empty/empty, not whether a path exists on disk;
# a command like `test -n config.yaml` has nothing to do with the filesystem even though it
# names the path as its operand (Greptile P1, PR #45, "Unrelated checks confirm missing
# files"). `-d`/`-r` were added alongside `-f`/`-e` to match COMPOUND_EXISTENCE_GATE_RE below,
# which already accepts any single-letter test flag as the gate of a compound command — a
# successful `test -d config` (or `test -r config.yaml`) is just as real a sibling probe as
# `test -f`/`test -e` (Greptile P1, PR #45, "Valid filesystem probes rejected"). Captures both
# the flag and the exact path token: the flag is what lets the caller require the sibling's
# own predicate to logically IMPLY the compound's gate predicate, not merely equal it (see
# _is_positive_existence_check and _FLAG_IMPLIES) — `test -d config` succeeding says nothing
# about whether `test -f config` would too (Greptile P1, PR #45, "Mismatched probes
# corroborate searches"), while `test -f config` succeeding DOES prove `test -e config` would
# (Greptile P1, PR #45, "Valid probes rejected") — and the path is compared, after
# normalization (see _normalize_path), rather than by substring containment.
FILE_EXISTENCE_PROBE_RE = re.compile(
    r"^\s*(?:test\s+-(?P<flag1>[fedr])\s+(?P<path1>\S+)|\[\s+-(?P<flag2>[fedr])\s+(?P<path2>\S+)\s+\])\s*$",
    re.IGNORECASE,
)


# Trailing-slash collapse is safe only for a flag whose predicate already REQUIRES the
# target to be a directory: appending (or removing) a `/` cannot change the answer for `-d`,
# because POSIX pathname resolution treats a trailing slash as appending `.` to the path,
# which only succeeds when the path is already a directory — exactly what `-d` was going to
# require anyway. It is NOT safe for `-f`/`-e`/`-r`: a trailing slash forces that same `.`
# resolution on a path that is NOT necessarily a directory, so `test -f config.yaml/` fails
# for a regular file even though `test -f config.yaml` succeeds — the slash changes the
# answer, not just the spelling, for every flag except `-d` (Greptile P1, PR #45, "Directory
# probes treated as different" / "Different paths treated as equal").
_TRAILING_SLASH_SAFE_FLAGS = {"d"}


def _safe_normpath(path: str) -> str:
    """A restricted `posixpath.normpath` that only removes `.` components and empty
    components from doubled/trailing separators — it never cancels a `..` component against
    a preceding NAMED component, unlike `posixpath.normpath`, because that cancellation
    assumes the named component is a plain directory. When it is a symlink, `link/../config`
    does NOT resolve to `config`: POSIX pathname resolution walks into whatever `link`
    points at first, and `..` from there goes to THAT directory's parent, which can be
    anywhere. `posixpath.normpath("link/../config")` collapses this to `"config"` purely
    textually, with no filesystem access, so it wrongly treats `link/../config` and `config`
    as the same target — a `test -f config` sibling would then falsely corroborate a compound
    gated on `test -e link/../config`, an existence check on a completely different path if
    `link` is a symlink elsewhere (Greptile P1, PR #45 round 10, "Symlink-unsafe path collapse
    falsely corroborates searches"). Leaving every `..` in place (along with the named
    component before it) means such a path can never normalize to the same string as the
    plain target it was trying to impersonate. `.` components and empty components are always
    safe to drop regardless of symlinks: removing a redundant `./` or a doubled `/` never
    changes what the path resolves to.

    This IS intentionally overbroad in the safe direction, and round 11 confirmed there is no
    narrower fix: an honest `test -f dir/../config.yaml` sibling, where `dir` really is an
    ordinary directory, no longer corroborates a compound gated on plain `config.yaml` either
    (Greptile P1, PR #45 round 11, "Valid parent paths rejected"). That is deliberate, not an
    oversight — collapsing `X/../Y` only "when X is provably not a symlink" needs to actually
    resolve `X` against a live filesystem, which this gate does not have and must not acquire:
    `commands[].cmd` is self-reported text, checked independently of (and often long after,
    possibly on a different machine from) whenever the commands actually ran, so "the
    filesystem right now" is not evidence about what `X` was at receipt-writing time. Two
    narrower rules were considered and rejected as unsound: (1) collapsing only when both
    sides of the comparison already carry the identical unresolved `../` prefix verbatim —
    this never actually helps the reported case, since the gate's own path (`config.yaml`)
    carries no such prefix at all, so the two strings still would not match; (2) collapsing
    based on some syntactic heuristic for "looks like an ordinary directory" (e.g. no symlink-
    suggestive name) — there is no such heuristic, since a symlink can be named anything a
    real directory can. With neither option sound, the choice stays binary — collapse `..`
    past a named component always (unsound: the round-10 P1 above) or never (sound, but
    strictly more conservative) — and this gate keeps the sound side.
    """
    is_absolute = path.startswith("/")
    kept = [part for part in path.split("/") if part not in ("", ".")]
    if not kept:
        return "/" if is_absolute else "."
    joined = "/".join(kept)
    return ("/" + joined) if is_absolute else joined


def _requires_directory(path: str) -> bool:
    """True when the spelling can only resolve to a directory: a trailing `/`, or a final `.`
    component (`dir/.`). POSIX resolves both by appending `.`, which fails for a regular file,
    so `README.md/.` is a different target from `README.md`, exactly as `README.md/` is.
    Dropping that final `.` made an existence probe on `README.md` corroborate a search gated
    on `README.md/.` that never ran (Greptile P1, "Unrun searches look verified").
    """
    return path.endswith("/") or (path != "." and path.rsplit("/", 1)[-1] == ".")


def _normalize_path(path: str, flag: str | None = None) -> str:
    """Collapse equivalent relative spellings of the same path (`./config.yaml` vs
    `config.yaml`, or a doubled separator) so sibling-probe matching compares what the path
    actually points at instead of the exact characters used to write it — plain string
    equality treated `./config.yaml` and `config.yaml` as different targets and rejected a
    valid sibling probe under `--strict` (Greptile P1, PR #45, "Equivalent paths reject valid
    evidence"). Uses `_safe_normpath` rather than `posixpath.normpath`: the latter also
    collapses `a/../b` to `b` textually, which is unsound when `a` is a symlink (see
    `_safe_normpath`) — a `..` component is never cancelled here, so `link/../config` stays
    `link/../config` and cannot collide with a sibling probe on the plain `config`. On an
    empty result (a bare `.` or `./`) is not a meaningful path token here, so that edge case
    falls back to the original string rather than collapsing every such probe onto the same
    normalized value.

    A trailing slash is preserved by default rather than collapsed away: POSIX `test`/`[`
    requires a path with a trailing slash to resolve to a directory, so `test -f
    config.yaml/` FAILS even though `config.yaml` exists as a regular file — the slash
    changes what the check actually proves, not just how the path is spelled. Treating
    `config.yaml` and `config.yaml/` as the same normalized token would let a sibling on the
    bare path corroborate a compound gated on the slashed one, whose own existence check can
    fail for a reason that has nothing to do with content (Greptile P1, PR #45, "Different
    paths treated as equal"). That risk does not exist for `-d`: a directory check's own
    predicate already requires the target to resolve as a directory, so the trailing slash
    can never flip the answer — `test -d config` and `test -d config/` are the same check
    (Greptile P1, PR #45, "Directory probes treated as different"). Pass the command's own
    flag so only `-d` gets that collapse; every other flag keeps the slash significant.
    """
    requires_dir = _requires_directory(path)
    normalized = _safe_normpath(path)
    if normalized in ("", "."):
        return path
    flag_allows_collapse = flag is not None and flag.lower() in _TRAILING_SLASH_SAFE_FLAGS
    if flag_allows_collapse or not requires_dir or normalized.endswith("/"):
        return normalized
    return normalized + "/"


# A claim about a path's ABSENCE ("the file no longer exists", "path/to/x was removed") is
# a different claim from one about its CONTENT ("the deprecated token was removed from
# config.yaml") — only the latter needs a search of what is inside the target, and an
# existence probe proves nothing about it. Bare "removed"/"deleted"/"gone"/"exists"/"absent"
# is also exactly how content-removal claims get phrased, so those words are only accepted
# here when a path/file noun sits next to them; a handful of full phrases ("no longer
# exists", "does not exist", "not present") stay accepted on their own because they are
# unambiguously about a thing's existence, not its contents (Greptile P1, PR #45, "Existence
# check validates content" — tightened from the earlier bare-word-list version that let a
# sole "removed" wrongly pass a content claim on existence-only evidence).
_PATH_NOUN_RE = r"(?:file|path|director(?:y|ies)|dir|folder)"
ABSENCE_CLAIM_RE = re.compile(
    rf"\b{_PATH_NOUN_RE}\b.{{0,60}}\b(?:exists?|absent|removed|deleted|gone)\b"
    rf"|\b(?:exists?|absent|removed|deleted|gone)\b.{{0,60}}\b{_PATH_NOUN_RE}\b"
    rf"|\bno longer (?:exists?|present)\b"
    rf"|\bnot present\b"
    rf"|\bdoes(?:n't| not) exist\b",
    re.IGNORECASE,
)

# `test -f X && grep ... X` short-circuits on a missing X before the search clause ever
# runs, leaving the exact same exit code as "X exists but the search found nothing" — exit
# code alone cannot tell the two apart (Greptile P1, PR #45, "Missing file passes content
# claim"). Only captured output can: a search tool that actually ran and printed something
# (e.g. `grep -c` always prints a count, even "0") is evidence the chain reached it; a
# short-circuited chain prints nothing at all. Anchored to the START of the command (not
# end-to-end like EXISTENCE_ONLY_RE above), since a content search is chained on after it.
# The path AND flag each branch guards are captured so a quiet search (see SILENT_SEARCH_RE
# below) can be checked against a separate, independent existence command for that same path
# — tested with a predicate that implies this gate's own (see _FLAG_IMPLIES). The flag
# matters as much as the path: a sibling `test -d config` proves config is a directory, but
# the compound's own gate might be `test -f config && ...`, which FAILS for a directory
# (short-circuiting before grep ever runs) even though the sibling's `-d` check passed —
# comparing paths without also requiring the sibling's flag to imply this gate's flag lets
# that mismatched pair corroborate a compound that never actually searched anything (Greptile
# P1, PR #45, "Mismatched probes corroborate searches").
COMPOUND_EXISTENCE_GATE_RE = re.compile(
    r"^\s*(?:test\s+-(?P<gate_flag1>[a-z])\s+(?P<gate_path1>\S+)"
    r"|\[\s+-(?P<gate_flag2>[a-z])\s+(?P<gate_path2>\S+)\s+\])\s*&&",
    re.IGNORECASE,
)

# `grep -q`/`grep --quiet` is defined to print nothing at all, whether it matches or not —
# silence is its normal, successful behaviour, not a sign the chain short-circuited. But that
# cuts both ways: it also means a quiet search's empty output_tail can never be told apart
# from `test -f X` failing and the chain short-circuiting before grep ever ran — both leave
# the same non-zero exit code and the same empty output (Greptile P1, PR #45, "Missing file
# passes quiet-grep check"). Exit code plus output_tail alone cannot resolve that ambiguity,
# so a quiet-search chain needs independent proof the file existed: a separate, EARLIER
# command in the receipt that tests the exact same path and exits 0 (see
# _confirmed_by_sibling_existence_check below). Without that sibling evidence, a quiet-grep
# compound is rejected as content proof, same as the unquiet case above (Greptile P1, PR #45,
# "Silent searches fail validation" — superseded: accepting a bare quiet-grep chain on its own
# exit code let a missing file pass as a quiet no-match).
SILENT_SEARCH_RE = re.compile(r"\bgrep\b[^&|;]*(?:-[a-zA-Z]*q[a-zA-Z]*\b|--quiet\b)")


# A sibling's flag corroborates a compound's gate flag when passing the sibling's test
# GUARANTEES the gate's test would also have passed on the same path — a one-way logical
# implication, not flag equality. `-f`/`-d`/`-r` each require the target to exist as a
# precondition of their own, stricter test (regular file / directory / readable), so any of
# them passing proves `-e` (bare existence) would pass too; `-f` and `-d` are mutually
# exclusive type tests, and `-r` says nothing about type, so none of the three implies either
# of the other two. `-e` implies only itself: existing proves nothing about being a regular
# file, a directory, or readable. Requiring flag equality rejected the case where a stricter
# sibling (`-f`) corroborates a weaker compound gate (`-e`) even though the implication holds
# (Greptile P1, PR #45, "Valid probes rejected"); this lattice accepts that case while still
# rejecting the unsound direction (an `-e` sibling must not corroborate an `-f`-gated
# compound: existing doesn't prove being a regular file) and the unrelated-type case from the
# prior round (`-d` must not corroborate `-f`, or vice versa).
_FLAG_IMPLIES = {
    "f": {"f", "e"},
    "d": {"d", "e"},
    "r": {"r", "e"},
    "e": {"e"},
}


def _flag_implies(sibling_flag: str, gate_flag: str) -> bool:
    return gate_flag.lower() in _FLAG_IMPLIES.get(sibling_flag.lower(), set())


def _exit_code_value(cmd: object) -> int | None:
    """The command's recorded exit code as an int, or None if it is missing or not an integer.

    Booleans are rejected even though Python treats them as ints (`False == 0`), and a null
    or string result is not evidence of success or failure, so each is returned as None.
    """
    if not isinstance(cmd, dict):
        return None
    value = cmd.get("exit_code")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _is_positive_existence_check(cmd: dict, path: str, flag: str) -> bool:
    """True if `cmd` is a real file-existence probe (`test -f`/`-e`/`-d`/`-r`, or the
    `[ ... ]` equivalent — see FILE_EXISTENCE_PROBE_RE) naming `path`, whose own flag
    logically implies the compound's gate `flag` (see `_FLAG_IMPLIES`), that itself exited 0
    — independent proof the path would have passed the gate's own test before the compound
    command ran, not inferred from the exit code of a compound that might never have reached
    it.

    Three things a looser check would get wrong: a path match must be exact-token equality
    (after normalization), not substring (`config.yaml.bak` must not corroborate
    `config.yaml`); the flag must be a real filesystem test, not `test -n`/`-z` (those test a
    STRING's emptiness, not the filesystem, even when the string happens to be the path)
    (Greptile P1, PR #45, "Unrelated checks confirm missing files"); and the sibling's flag
    must IMPLY the compound's own gate flag, not merely equal it or be accepted regardless —
    a `test -d config` passing proves nothing about whether `test -f config` (a different,
    unimplied predicate on the same path) would also pass, so a `-d` sibling must not
    corroborate an `-f`-gated compound or vice versa (Greptile P1, PR #45, "Mismatched probes
    corroborate searches"), while a `test -f config` sibling DOES prove `test -e config` would
    pass, since being a regular file requires existing (Greptile P1, PR #45, "Valid probes
    rejected"). Comparing normalized paths means `test -f ./config.yaml` corroborates a
    sibling probe for `config.yaml` — the same file, spelled differently — instead of being
    rejected as a different target (Greptile P1, PR #45, "Equivalent paths reject valid
    evidence"); each path is normalized under its OWN command's flag, so `test -d config` and
    `test -d config/` still compare equal (Greptile P1, PR #45, "Directory probes treated as
    different") while `config.yaml` and `config.yaml/` remain distinct for every flag where
    the trailing slash can actually change the outcome (Greptile P1, PR #45, "Different paths
    treated as equal").
    """
    if _exit_code_value(cmd) != 0:
        return False
    match = FILE_EXISTENCE_PROBE_RE.match(str(cmd.get("cmd", "")).strip())
    if not match:
        return False
    matched_flag = match.group("flag1") or match.group("flag2")
    if not _flag_implies(matched_flag, flag):
        return False
    matched_path = match.group("path1") or match.group("path2")
    # Both paths are normalized under the SIBLING's flag, not each side's own flag: once the
    # sibling has proven the target's type (`-d` passing means it IS a directory), a trailing
    # slash on the gate's OWN path can no longer change the outcome either, since the gate's
    # test is already known to land on that same directory. Normalizing the gate's path under
    # its own `-e`/`-f`/`-r` flag instead treated `test -d config` as unable to corroborate
    # `test -e config/ && ...`, rejecting a directory that had already been proven to exist
    # (Greptile P1, PR #45, "Valid directory probe is rejected"). This is sound only because
    # `_flag_implies` already restricted the pair above: the one case where trailing-slash
    # significance is genuinely flag-dependent (`-d` vs `-f`/`-e`/`-r` on the same path) can
    # never reach here, since those flags don't imply each other.
    return _normalize_path(matched_path, matched_flag) == _normalize_path(path, matched_flag)


def _confirmed_by_sibling_existence_check(
    commands: list, path: str, flag: str, exclude_idx: int
) -> bool:
    """True if some EARLIER command (lower index than `exclude_idx`) independently proves
    `path` would have passed the compound's own `flag` test before the quiet-search compound
    at `exclude_idx` ran (see `_flag_implies` for what "would have passed" allows).

    This is the only evidence that can break the tie between a quiet-grep compound that
    actually ran and found nothing, and one whose leading existence check failed and never
    reached grep at all — both look identical from the compound command's own exit code and
    output_tail alone. Order matters as much as existence: a `test -f X` recorded AFTER the
    quiet search only proves X exists NOW — it could have been created after the search ran
    and found nothing, which is the exact ambiguity this function exists to resolve, not
    corroborate (Greptile P1, PR #45, "Later check validates earlier search"). So only a
    sibling strictly before `exclude_idx`, whose own test implies the compound's gate flag,
    counts.
    """
    return any(
        _is_positive_existence_check(other, path, flag)
        for j, other in enumerate(commands)
        if j < exclude_idx and isinstance(other, dict)
    )


class ReceiptError(Exception):
    pass


def load(path: Path) -> dict:
    if not path.exists():
        raise ReceiptError(
            f"no receipt at {path}\n"
            "  A completion claim requires a receipt. See skills/verification-receipts/SKILL.md"
        )
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ReceiptError(f"receipt is not valid JSON: {exc}") from exc


def _missing_field_problems(receipt: dict) -> list[str]:
    """Every receipt names its task, bot, commands, claims, and unverified list."""
    return [
        f"missing required field '{field}'" for field in REQUIRED_FIELDS if field not in receipt
    ]


def _structural_problems(commands: object, claims: object, unverified: object) -> list[str]:
    """Commands must be a non-empty list; claims and unverified must be lists."""
    problems: list[str] = []
    if not isinstance(commands, list) or not commands:
        problems.append("no commands recorded — nothing was actually run, so nothing is verified")
    if not isinstance(claims, list):
        problems.append("'claims' must be a list")
    if not isinstance(unverified, list):
        problems.append("'unverified' must be a list (an empty list is allowed but rarely honest)")
    return problems


def _bot_problems(receipt: dict, expected_bot: str | None) -> list[str]:
    """The receipt must name the bot the gate was invoked for."""
    if expected_bot and receipt.get("bot") != expected_bot:
        return [f"receipt bot '{receipt.get('bot')}' does not match --bot '{expected_bot}'"]
    return []


def _self_approval_problems(receipt: dict) -> list[str]:
    """Work must be reviewed by someone other than the bot that did it."""
    approved_by = receipt.get("approved_by")
    if not approved_by:
        return ["'approved_by' is missing — work must be reviewed by someone else"]
    if approved_by == receipt.get("bot"):
        return [
            f"self-approval: approved_by == {approved_by} ({approved_by}). "
            "A bot approving its own work removes the independent check."
        ]
    return []


# A bypass pattern that lands inside the quoted argument of a read-only search names the text
# being searched FOR (`grep -n -- "--no-verify" file`); nothing is skipped, so it is not a
# bypass. Only a single simple search command qualifies. Unquoted shell syntax anywhere on the
# line (separators, substitution, redirection, background) or an expansion inside the quotes
# means the quoted text might be executed, so every match stays a bypass (fail closed).
_SEARCH_TOOL_RE = re.compile(r"\s*(?:[efz]?grep|rg|ag|ack|git\s+grep)(?=\s|$)")
_SHELL_SYNTAX = frozenset("`$()<>;|&\n\r")


def _split_quotes(cmd: str) -> tuple[str, list[tuple[int, int]], bool]:
    """Blank the content of each quoted argument so the unquoted text can be inspected alone.

    Returns the line with every quoted span's content replaced by spaces (indices unchanged),
    the (open, close) index of each span, and False when a quote is never closed.
    """
    chars = list(cmd)
    spans: list[tuple[int, int]] = []
    i, n = 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if ch == "\\":
            i += 2
        elif ch in "'\"":
            j = i + 1
            while j < n and cmd[j] != ch:
                j += 2 if ch == '"' and cmd[j] == "\\" else 1
            if j >= n:
                return cmd, [], False
            spans.append((i, j))
            chars[i + 1 : j] = " " * (j - i - 1)
            i = j + 1
        else:
            i += 1
    return "".join(chars), spans, True


def _search_text_ranges(cmd: str) -> list[tuple[int, int]]:
    """Half-open index ranges of `cmd` that are text a search tool looks FOR, not shell syntax.

    Only quoted arguments after the search tool name qualify, and only when the line holds no
    unquoted shell syntax and no expansion inside the quotes. Anything else returns no ranges.
    """
    blanked, spans, balanced = _split_quotes(cmd)
    if not balanced or any(ch in _SHELL_SYNTAX for ch in blanked):
        return []
    tool = _SEARCH_TOOL_RE.match(blanked)
    if tool is None:
        return []
    ranges: list[tuple[int, int]] = []
    for open_idx, close_idx in spans:
        content = cmd[open_idx + 1 : close_idx]
        if open_idx < tool.end() or "$" in content or "`" in content:
            continue
        ranges.append((open_idx + 1, close_idx))
    return ranges


def _pattern_hits(pattern: str, cmd: str) -> list[tuple[int, int]]:
    """Every (start, end) span where `pattern` matches `cmd`, overlapping matches included."""
    regex = re.compile(pattern)
    hits: list[tuple[int, int]] = []
    for pos in range(len(cmd)):
        match = regex.match(cmd, pos)
        if match is not None:
            hits.append((pos, match.end()))
    return hits


def _bypass_problems(commands: object) -> list[str]:
    """Flag commands that produce a green result from work that never ran."""
    problems: list[str] = []
    for i, cmd in enumerate(commands if isinstance(commands, list) else []):
        cmd_str = str(cmd.get("cmd", "")) if isinstance(cmd, dict) else str(cmd)
        search_text = _search_text_ranges(cmd_str)
        for pattern, why in BYPASS_PATTERNS:
            if any(
                not any(lo <= start and end <= hi for lo, hi in search_text)
                for start, end in _pattern_hits(pattern, cmd_str)
            ):
                problems.append(
                    f"command[{i}] contains a bypass: {cmd_str!r}\n    matched {pattern!r} - {why}"
                )
    return problems


def _exit_code_problems(commands: object) -> list[str]:
    """Every command must record its exit code — an unrecorded code is not evidence."""
    problems: list[str] = []
    for i, cmd in enumerate(commands if isinstance(commands, list) else []):
        if not isinstance(cmd, dict):
            problems.append(f"command[{i}] must be an object with 'cmd' and 'exit_code'")
            continue
        if "cmd" not in cmd:
            problems.append(f"command[{i}] has no 'cmd'")
        if "exit_code" not in cmd:
            problems.append(
                f"command[{i}] has no 'exit_code' - an unrecorded exit code is not evidence"
            )
        elif _exit_code_value(cmd) is None:
            problems.append(
                f"command[{i}] 'exit_code' must be an integer, got "
                f"{type(cmd['exit_code']).__name__} - null, boolean, and string results "
                "are not evidence"
            )
    return problems


def _claim_problems(claims: object, commands: list, strict: bool) -> list[str]:
    """Every claim must cite a real command whose exit code supports it."""
    problems: list[str] = []
    for i, claim in enumerate(claims if isinstance(claims, list) else []):
        problems.extend(_check_claim(i, claim, commands, strict))
    return problems


def _check_claim(i: int, claim: object, commands: list, strict: bool) -> list[str]:
    """Validate one claim's evidence citation and, under --strict, its scope."""
    if not isinstance(claim, dict):
        return [f"claim[{i}] must be an object"]
    text = claim.get("claim", "<no text>")
    idx = claim.get("evidence_command_index")
    if idx is None:
        return [
            f"claim[{i}] {text!r} cites no command — "
            "a claim without evidence is a guess with confident phrasing"
        ]
    if isinstance(idx, bool) or not isinstance(idx, int) or not (0 <= idx < len(commands)):
        return [f"claim[{i}] {text!r} cites command index {idx}, which does not exist"]
    cited = commands[idx]
    exit_code = _exit_code_value(cited)
    if exit_code is None:
        return [
            f"claim[{i}] {text!r} cites command[{idx}] which records no integer exit_code - "
            "an unrecorded or non-integer result is not evidence, whether or not "
            "expects_failure is set"
        ]
    # A claim may legitimately cite a FAILING command: "reproduced the bug" is evidenced
    # by a non-zero exit. That reproduction step is what makes the later green run mean
    # something, so the gate must support it rather than forcing every claim to be green.
    expects_failure = bool(claim.get("expects_failure"))
    problems = _citation_problems(
        i, text=text, idx=idx, cited=cited, exit_code=exit_code, expects_failure=expects_failure
    )
    if strict and EXHAUSTIVE_RE.search(text):
        problems.extend(
            _exhaustive_problems(
                i,
                text=text,
                idx=idx,
                cited=cited,
                commands=commands,
                expects_failure=expects_failure,
            )
        )
    return problems


def _citation_problems(
    i: int,
    *,
    text: str,
    idx: int,
    cited: object,
    exit_code: object,
    expects_failure: bool,
) -> list[str]:
    """The cited command's exit code must match what the claim expects of it."""
    if expects_failure:
        if exit_code == 0:
            return [
                f"claim[{i}] {text!r} sets expects_failure but command[{idx}] exited 0\n"
                f"    {cited.get('cmd', '')!r}"
                if isinstance(cited, dict)
                else f"claim[{i}] {text!r} sets expects_failure but command[{idx}] exited 0"
            ]
        return []
    if exit_code != 0:
        return [
            f"claim[{i}] {text!r} cites command[{idx}] which exited {exit_code}\n"
            f"    {cited.get('cmd', '')!r}\n"
            f'    If this is a reproduction step, set "expects_failure": true on the claim.'
            if isinstance(cited, dict)
            else f"claim[{i}] {text!r} cites command[{idx}] which exited {exit_code}"
        ]
    return []


def _exhaustive_problems(
    i: int,
    *,
    text: str,
    idx: int,
    cited: object,
    commands: list,
    expects_failure: bool,
) -> list[str]:
    """Under --strict, an exhaustive claim needs evidence covering its whole scope."""
    if expects_failure:
        cmd_text = str(cited.get("cmd", "")) if isinstance(cited, dict) else ""
        output_tail = str(cited.get("output_tail", "")) if isinstance(cited, dict) else ""
        # A quiet-grep compound (`test -f X && grep -q PATTERN X`) with empty
        # output_tail is ambiguous on its own exit code alone (see SILENT_SEARCH_RE
        # above) — it needs one specific OTHER command as corroboration: a bare
        # existence check on that same path, with the SAME flag as this compound's own
        # gate, that itself exited 0. gate_path/gate_flag are set only when the cited
        # command is exactly that shape, so every other claim keeps the single-command
        # rule below unchanged.
        gate_match = COMPOUND_EXISTENCE_GATE_RE.match(cmd_text)
        gate_is_quiet_compound = (
            gate_match and not output_tail.strip() and SILENT_SEARCH_RE.search(cmd_text)
        )
        gate_path = (
            (gate_match.group("gate_path1") or gate_match.group("gate_path2"))
            if gate_is_quiet_compound
            else None
        )
        gate_flag = (
            (gate_match.group("gate_flag1") or gate_match.group("gate_flag2"))
            if gate_is_quiet_compound
            else None
        )
        if _unexplained_padding(commands, idx, gate_path, gate_flag):
            return [
                f"claim[{i}] {text!r} sets expects_failure and asserts "
                "exhaustiveness, and the receipt records other commands beyond the "
                "one cited that are not an EARLIER sibling existence check "
                "confirming the same exact path — they cannot be what makes this "
                "claim exhaustive, so its cited command must be the receipt's only "
                "command (or paired only with a command that tests the exact same "
                "path and exits 0, recorded BEFORE it) for this to pass under "
                "--strict"
            ]
        return _evidence_shape_problems(
            i,
            text=text,
            idx=idx,
            cmd_text=cmd_text,
            output_tail=output_tail,
            commands=commands,
            gate_path=gate_path,
            gate_flag=gate_flag,
        )
    if len(commands) < 2:
        return [
            f"claim[{i}] {text!r} asserts exhaustiveness but the receipt has "
            f"only {len(commands)} command(s)"
        ]
    return []


def _unexplained_padding(
    commands: list, idx: int, gate_path: str | None, gate_flag: str | None
) -> list[int]:
    """Other commands that neither prove the quiet search's target nor are the citation."""
    # A single expected-failure command CAN be exhaustive evidence: a search
    # that exits non-zero exactly when it finds nothing across its whole target
    # (e.g. a grep for any populated value) is reproduction evidence and total
    # coverage at once. What it must never do is borrow OTHER, unrelated
    # commands elsewhere in the receipt to look better-supported than it is —
    # that was the original bypass this check exists for (Greptile P1, PR #45):
    # a claim citing one narrow, failing command, padded by an unrelated command
    # recorded for something else (the fix that follows it, say). len(commands)
    # is a receipt-wide count, but here it is used the other way around from the
    # passing-evidence branch below: for THIS claim, more commands elsewhere in
    # the receipt is exactly the sign that something else might be doing the
    # padding, not more support — with one narrow exception: a command that
    # EARLIER in the receipt confirms gate_path existed is not padding the
    # claim's coverage, it is the only way a quiet-grep compound's ambiguous
    # exit code can be trusted at all (Greptile P1, PR #45, "Missing file passes
    # quiet-grep check"). That exception is order-sensitive: a matching command
    # recorded AFTER idx proves nothing about whether gate_path existed when the
    # quiet search ran (it could have been created afterward), so it still
    # counts as unexplained padding, not corroboration (Greptile P1, PR #45,
    # "Later check validates earlier search"). With no other, unexplained
    # command in the receipt to borrow from, this claim's cited command is
    # plainly its entire evidence, and its own scope is what a human reviewer
    # judges (approved_by), same as any other evidence-matching question this
    # gate cannot verify by itself.
    return [
        j
        for j, other in enumerate(commands)
        if j != idx
        and not (
            gate_path
            and isinstance(other, dict)
            and j < idx
            and _is_positive_existence_check(other, gate_path, gate_flag)
        )
    ]


def _evidence_shape_problems(
    i: int,
    *,
    text: str,
    idx: int,
    cmd_text: str,
    output_tail: str,
    commands: list,
    gate_path: str | None,
    gate_flag: str | None,
) -> list[str]:
    """The failure itself must read as a searched-and-empty scope, not a missing target."""
    # Clearing the padding concern above proves nothing by itself about WHY
    # the command failed. A claim that "every value is empty" needs a
    # failure that came from searching the content and finding nothing, not
    # from the target being absent — those are different facts, and only a
    # human (approved_by) can judge whether the command's own scope truly
    # covers "every"/"all". This gate can at least catch the shapes of thin
    # evidence that pattern most often: a missing-target error, a command
    # that only checks existence and never looks at content either way, and
    # a quiet-grep compound with no independent proof its target existed.
    if MISSING_TARGET_RE.search(output_tail) or MISSING_TARGET_RE.search(_strip_quoted(cmd_text)):
        return [
            f"claim[{i}] {text!r} sets expects_failure and asserts "
            f"exhaustiveness, but command[{idx}]'s evidence reads as the "
            'target being missing ("no such file", "not found", ...), '
            "not as a search that covered the claim's whole scope and found "
            "nothing — a missing target proves nothing about the content the "
            "claim describes"
        ]
    if EXISTENCE_ONLY_RE.search(cmd_text):
        if not ABSENCE_CLAIM_RE.search(text):
            return [
                f"claim[{i}] {text!r} asserts exhaustiveness over content, "
                f"but command[{idx}] ({cmd_text!r}) only tests whether a "
                "path exists — that proves nothing about the content "
                "inside it"
            ]
        # else: the claim is about the path's absence, not its content —
        # the existence probe's exit code is direct, sufficient evidence.
        return []
    if COMPOUND_EXISTENCE_GATE_RE.match(cmd_text) and not output_tail.strip():
        if not SILENT_SEARCH_RE.search(cmd_text):
            return [
                f"claim[{i}] {text!r} asserts exhaustiveness via a command "
                f"that chains a content search after an existence check "
                f"({cmd_text!r}) with no captured output — the existence "
                "check failing would short-circuit the chain and produce "
                "this exact same exit code without the search ever running. "
                "Record output_tail evidence that the search itself "
                "executed (e.g. a `grep -c` count), or cite the existence "
                "check and the search as separate commands"
            ]
        if not gate_path or not _confirmed_by_sibling_existence_check(
            commands, gate_path, gate_flag, idx
        ):
            return [
                f"claim[{i}] {text!r} asserts exhaustiveness via a "
                f"quiet search chained after an existence check "
                f"({cmd_text!r}) with no captured output — `grep -q`/"
                "`--quiet` prints nothing whether it matches or not, so "
                "this exit code is identical whether the search ran and "
                f"found nothing, or the existence check on {gate_path!r} "
                "failed and the chain short-circuited before grep ever "
                "ran. Record a separate command in 'commands', BEFORE "
                f"this one, that tests the exact path {gate_path!r} and "
                "exits 0, proving the file was actually there when the "
                "search ran — the same check recorded AFTER this command "
                "only proves the file exists now, not that it did then"
            ]
        # else: a separate, earlier command in the receipt already
        # proved the target present, so the chain's own exit code —
        # reachable only if its existence check passed too — is valid
        # negative content evidence.
    return []


def _loop_ack_problems(receipt: dict) -> list[str]:
    """Degraded-mode turn acks must each name a person, a condition, and this task."""
    # Optional: a receipt for a turn that never went degraded OMITS the field, or carries [].
    # A present-but-null field is a different shape from omission — `"loop_acks" in receipt`
    # (rather than `.get(...) is not None`) is what tells the two apart, so an explicit null
    # is caught here instead of silently reading the same as "no field at all".
    if "loop_acks" not in receipt:
        return []
    loop_acks = receipt.get("loop_acks")
    if not isinstance(loop_acks, list):
        return [
            "'loop_acks' must be a list — omit the field entirely if this turn never "
            "went degraded; do not set it to null"
        ]
    task_id = receipt.get("task_id")
    problems: list[str] = []
    for i, ack in enumerate(loop_acks):
        problems.extend(_check_loop_ack(i, ack, task_id))
    return problems


def _check_loop_ack(i: int, ack: object, task_id: object) -> list[str]:
    """Validate one degraded-mode acknowledgement object."""
    if not isinstance(ack, dict):
        return [f"loop_acks[{i}] must be an object"]
    problems: list[str] = []
    missing = [f for f in REQUIRED_LOOP_ACK_FIELDS if not ack.get(f)]
    if missing:
        problems.append(
            f"loop_acks[{i}] is missing {missing} — a degraded-mode ack records the "
            "condition, the operation, the ack id, the human who granted it, when, "
            "and the one turn it covers"
        )
    problems.extend(_granter_problems(i, ack))
    problems.extend(_condition_problems(i, ack))
    problems.extend(_scope_problems(i, ack, task_id))
    return problems


def _granter_problems(i: int, ack: dict) -> list[str]:
    """The granter must be a person, never a seat id."""
    granter = ack.get("human_granted_by")
    if granter is not None and not isinstance(granter, str):
        # A truthy non-string (e.g. `true`, an id, an object) would otherwise be
        # silently stringified below and could dodge both the missing-field check
        # (it is truthy) and the seat-name regex (it does not look like a seat).
        return [
            f"loop_acks[{i}] human_granted_by must be a string naming a person, "
            f"got {type(granter).__name__} ({granter!r})"
        ]
    if granter and SEAT_ID_RE.match(granter):
        return [
            f"loop_acks[{i}] human_granted_by is {granter!r}, which is a seat, not a "
            "human — degraded repo work needs a person's acknowledgement. The "
            "relaying seat goes in 'relayed_by'"
        ]
    return []


def _condition_problems(i: int, ack: dict) -> list[str]:
    """The condition must name a known degraded-mode cause."""
    cond = ack.get("condition")
    if cond and (not isinstance(cond, str) or cond not in LOOP_ACK_CONDITIONS):
        return [f"loop_acks[{i}] condition {cond!r} is not one of {sorted(LOOP_ACK_CONDITIONS)}"]
    return []


def _scope_names_task(scope: str, task_id: object) -> bool:
    """True when `scope` names `task_id` as a whole ticket identifier.

    A plain substring test let the scope "SPE-180010 only" authorise SPE-18001. The match
    must end at identifier boundaries on both sides, so a longer ID, or one with a prefix
    attached, never counts. A missing or empty task_id names nothing.
    """
    if not isinstance(task_id, str) or not task_id:
        return False
    pattern = rf"(?<![A-Za-z0-9_-]){re.escape(task_id)}(?![A-Za-z0-9_-])"
    return re.search(pattern, scope) is not None


def _scope_problems(i: int, ack: dict, task_id: object) -> list[str]:
    """The ack scope must bind the ack to this receipt's task."""
    scope = ack.get("scope")
    if scope is not None and not isinstance(scope, str):
        return [f"loop_acks[{i}] scope must be a string"]
    if scope and not _scope_names_task(scope, task_id):
        # An ack's scope is supposed to bind it to *this* turn. A scope carried
        # over from another ticket, or a blanket phrase like "all turns", is
        # truthy and would otherwise pass unnoticed.
        return [
            f"loop_acks[{i}] scope {scope!r} does not name this receipt's "
            f"task_id ({task_id!r}) as a whole ticket identifier - an ack scoped "
            "to another ticket (including one whose ID merely starts with this "
            "one), or a blanket scope, does not authorise this turn"
        ]
    return []


def _unverified_problems(unverified: object) -> list[str]:
    """Unverified entries must name something specific, not a vague hand-wave."""
    if isinstance(unverified, list) and not unverified:
        # Not a hard failure — occasionally true — but it is worth surfacing, because an
        # empty list asserts complete verification and that is rarely the case.
        print(
            "  NOTE: 'unverified' is empty. That asserts everything was verified. "
            "Confirm it is true rather than forgotten.",
            file=sys.stderr,
        )
    vague = {
        "some edge cases",
        "minor things",
        "full testing",
        "everything else",
        "various things",
        "misc",
        "other cases",
    }
    problems: list[str] = []
    for entry in unverified if isinstance(unverified, list) else []:
        if str(entry).strip().lower().rstrip(".") in vague:
            problems.append(
                f"unverified entry {entry!r} is too vague to be useful — "
                "name what was not verified and why"
            )
    return problems


def check(receipt: dict, expected_bot: str | None, strict: bool = False) -> list[str]:
    problems = _missing_field_problems(receipt)
    if problems:
        return problems

    commands = receipt["commands"]
    claims = receipt["claims"]
    unverified = receipt["unverified"]

    problems.extend(_structural_problems(commands, claims, unverified))
    problems.extend(_bot_problems(receipt, expected_bot))
    problems.extend(_self_approval_problems(receipt))
    problems.extend(_bypass_problems(commands))
    problems.extend(_exit_code_problems(commands))
    problems.extend(_claim_problems(claims, commands, strict))
    problems.extend(_loop_ack_problems(receipt))
    problems.extend(_unverified_problems(unverified))

    # --- deployment needs a rollback plan (G-5 handoff) --------------------
    if receipt.get("deployment") and not receipt.get("rollback_plan"):
        problems.append("deployment recorded but 'rollback_plan' is null — G-5 requires one")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate G-2: verification receipts")
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--bot", help="Expected bot id")
    ap.add_argument(
        "--strict", action="store_true", help="Also flag exhaustive claims backed by thin evidence"
    )
    args = ap.parse_args()

    try:
        receipt = load(args.receipt)
    except ReceiptError as exc:
        print(f"G-2 FAIL — {exc}", file=sys.stderr)
        return 1

    problems = check(receipt, args.bot, strict=args.strict)

    if problems:
        print(f"G-2 FAIL — {args.receipt}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n  See skills/verification-receipts/SKILL.md", file=sys.stderr)
        return 1

    n_cmds = len(receipt["commands"])
    n_claims = len(receipt["claims"])
    n_unver = len(receipt["unverified"])
    print(
        f"G-2 PASS — {receipt['task_id']}: "
        f"{n_cmds} command(s), {n_claims} substantiated claim(s), {n_unver} unverified item(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
