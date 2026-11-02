"""Build plans.json from units_v4 + plans_def; verify ownership, dependency order and PR topology.

Usage: cd /tmp/v4/final/tools && python3 build.py
Writes /tmp/v4/final/plans.json and /tmp/v4/final/_model.json (consumed by docs_gen.py).
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

sys.path.insert(0, "/root/src/repos/pumpgrok/ci/gates")
import check_ownership as co  # noqa: E402

from plans_def import OWNER_APPLIED, PLANS, PR_ORDER  # noqa: E402
from units_v4 import CHIEF, H, LIVE_CMD, OWN_CMD, SMOKE_CMD, TSMOKE_PIN_CMD, U  # noqa: E402

M = co.load_manifest(co.DEFAULT_MANIFEST)
BYPASS = re.compile(r"--no-verify|\|\|\s*true|2>/dev/null|--force\b|--co\b|--collect-only|--dry-run|PUMPGROK_LIVE_ENABLE")
errors: list[str] = []


def own(path: str) -> str | None:
    return co.resolve_owner(path.replace("**", "x").replace("*", "x"), M)[0]


# ------------------------------------------------------------------ unit -> plan
plan_of: dict[str, str] = {}
for pid, phase, seat, title, units, od, notes, pr in PLANS:
    for u in units:
        if u not in U:
            errors.append(f"plan {pid}: unknown unit {u}")
        if u in plan_of:
            errors.append(f"unit {u} in two plans {plan_of[u]} and {pid}")
        plan_of[u] = pid
for u in U:
    if u not in plan_of:
        errors.append(f"unit {u} is not in any plan")
phase_of_plan = {p[0]: p[1] for p in PLANS}
seat_of_plan = {p[0]: p[2] for p in PLANS}
CLOSER_PCL = {f"PCL-{n}" for n in (11, 12, 13, 15, 16, 17, 19)} | {"A11", "C-16"}
CLOSER_PLN = {f"PLN-{n}" for n in range(11, 20)}

# ------------------------------------------------------------------ files and ownership
plan_files: dict[str, list[str]] = {}
for pid, phase, seat, title, units, od, notes, pr in PLANS:
    files: list[str] = []
    for u in units:
        for f in U[u]["files"]:
            if f not in files:
                files.append(f)
        if seat != OWNER_APPLIED and U[u]["seat"] != seat:
            errors.append(f"plan {pid} seat {seat} but unit {u} seat {U[u]['seat']}")
    if pid == "18-07":
        files.append("prompts/bot-04-sniper.xml")
    owners = {f: own(f) for f in files}
    if seat != OWNER_APPLIED:
        for f, o in owners.items():
            if o != seat:
                errors.append(f"plan {pid}: {f} owned by {o}, plan seat {seat}")
    plan_files[pid] = files

# ------------------------------------------------------------------ dependencies
deps: dict[str, list[str]] = {p[0]: [] for p in PLANS}
oa: dict[str, list[str]] = {p[0]: [] for p in PLANS}
for pid, phase, seat, title, units, od, notes, pr in PLANS:
    for u in units:
        for d in U[u]["depends_on"]:
            if d.startswith("EXT:"):
                continue
            if d not in plan_of:
                errors.append(f"{u}: dependency {d} has no plan")
                continue
            dp = plan_of[d]
            if dp != pid and dp not in deps[pid]:
                deps[pid].append(dp)
        for d in U[u]["order_after"]:
            if d in plan_of and plan_of[d] != pid and plan_of[d] not in oa[pid] and plan_of[d] not in deps[pid]:
                oa[pid].append(plan_of[d])

# closers: PCL depends on every non-closer plan of its phase; PLN on every plan of its phase
by_phase: dict[int, list[str]] = defaultdict(list)
for p in PLANS:
    by_phase[p[1]].append(p[0])
pcl_plan = {p[1]: p[0] for p in PLANS if len(p[4]) == 1 and p[4][0] in CLOSER_PCL}
pln_plan = {p[1]: p[0] for p in PLANS if len(p[4]) == 1 and p[4][0] in CLOSER_PLN}
for ph in by_phase:
    deps[pcl_plan[ph]] = [q for q in by_phase[ph] if q not in (pcl_plan[ph], pln_plan[ph])]
    deps[pln_plan[ph]] = [q for q in by_phase[ph] if q != pln_plan[ph]]
deps[pcl_plan[19]] = ["19-01", "19-02", "19-03", "19-04", "19-05"]
# AUDIT-19 depends on everything before it
deps["19-08"] = [q for q in by_phase[19] if q not in ("19-08", "19-09")]

# phase monotonicity
for pid, dl in deps.items():
    for d in dl:
        if phase_of_plan[d] > phase_of_plan[pid]:
            errors.append(f"{pid} (phase {phase_of_plan[pid]}) depends on later-phase plan {d}")


def waves() -> dict[str, int]:
    wave: dict[str, int] = {}

    def w(p: str, stack=()) -> int:
        if p in wave:
            return wave[p]
        if p in stack:
            errors.append(f"cycle through {p}")
            return 0
        best = 1
        for d in deps[p] + oa[p]:
            if phase_of_plan[d] == phase_of_plan[p]:
                best = max(best, w(d, stack + (p,)) + 1)
        wave[p] = best
        return best

    for p in deps:
        w(p)
    return wave


wave = waves()

# order_after inference for shared explicit files across plans (same seat only; cross-seat sharing is an error)
sharing: dict[str, list[str]] = defaultdict(list)
for pid, files in plan_files.items():
    for f in files:
        if "*" not in f:
            sharing[f].append(pid)


def anc(p: str, seen=None) -> set[str]:
    seen = seen if seen is not None else set()
    for d in deps[p] + oa[p]:
        if d not in seen:
            seen.add(d)
            anc(d, seen)
    return seen


order_key = lambda p: (phase_of_plan[p], wave[p], p)  # noqa: E731
shared_table = []
for f, ps in sorted(sharing.items()):
    if len(ps) < 2:
        continue
    seats = {seat_of_plan[p] for p in ps}
    if len(seats - {OWNER_APPLIED}) > 1 and "18-07" not in ps:
        errors.append(f"file {f} shared across seats {seats}: {ps}")
    ps_sorted = sorted(ps, key=order_key)
    shared_table.append((f, ps_sorted))
    for a, b in zip(ps_sorted, ps_sorted[1:]):
        if a not in anc(b) and b not in anc(a) and a != b:
            oa[b].append(a)
wave = waves()

# ------------------------------------------------------------------ pull requests
pr_of: dict[str, str] = {p[0]: p[7] for p in PLANS}
pr_meta = {k: (seat, slug) for k, seat, slug in PR_ORDER}
pr_index = {k: i + 1 for i, (k, _, _) in enumerate(PR_ORDER)}
pr_plans: dict[str, list[str]] = defaultdict(list)
for p in PLANS:
    pr_plans[p[7]].append(p[0])
for k in pr_meta:
    if k not in pr_plans:
        errors.append(f"PR {k} has no plans")
for k in pr_plans:
    if k not in pr_meta:
        errors.append(f"plans refer to unknown PR {k}")
pr_deps: dict[str, set[str]] = {k: set() for k in pr_meta}
for pid in deps:
    for d in deps[pid] + oa[pid]:
        if pr_of[d] != pr_of[pid]:
            pr_deps[pr_of[pid]].add(pr_of[d])
    # every plan of a PR belongs to the PR seat
for k, ps in pr_plans.items():
    seats = {seat_of_plan[p] for p in ps}
    if len(seats) != 1:
        errors.append(f"PR {k} mixes seats {seats}")
# acyclic + consistent with PR_ORDER
for k, ds in pr_deps.items():
    for d in ds:
        if pr_index[d] > pr_index[k]:
            errors.append(f"PR order: {k} (#{pr_index[k]}) depends on later PR {d} (#{pr_index[d]})")
# transitive reduction for display
def reduce(k: str) -> list[str]:
    ds = set(pr_deps[k])
    red = set(ds)
    for d in ds:
        stack = list(pr_deps[d])
        seen = set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            red.discard(x)
            stack.extend(pr_deps[x])
    return sorted(red, key=lambda x: pr_index[x])


pr_deps_reduced = {k: reduce(k) for k in pr_meta}

# ------------------------------------------------------------------ human approver reasons
HUMAN_PATTERNS = [
    (".github/workflows/", "edits a GitHub workflow"),
    ("ci/", "edits ci/ (gates, ratchet tests)"),
    ("contracts/", "edits a contract surface"),
    ("services/desk-signer/", "edits the signer service"),
    ("src/pumpgrok/execution/live/", "edits execution/live"),
    ("src/pumpgrok/core/signer_protocol.py", "edits the signer protocol"),
    ("src/pumpgrok/config/sections/live.py", "defines live caps"),
    ("src/pumpgrok/config/sections/signer.py", "defines signer limits"),
    ("rules/", "edits the constitution rules"),
    (".gitignore", "edits .gitignore"),
    ("docker-compose.yml", "edits docker-compose.yml"),
    ("Dockerfile", "edits a Dockerfile"),
    (".planning/PROJECT.md", "edits PROJECT.md"),
    ("src/pumpgrok/config/promotion_thresholds.toml", "edits promotion thresholds"),
    ("src/pumpgrok/config/mint_lists.toml", "edits mint lists"),
    ("tests/fixtures/replay/pins/", "re-pins a hash oracle"),
    ("tests/safety/amendment_", "edits the amendment oracle"),
]
plan_human: dict[str, list[str]] = {}
for pid, phase, seat, title, units, od, notes, pr in PLANS:
    reasons: list[str] = []
    for u in units:
        if U[u]["human_gate"]:
            reasons.append(f"unit {u} is human-gated")
        if U[u]["amendment_wait"]:
            reasons.append(f"unit {u} waits for the amendment")
    for f in plan_files[pid]:
        for pat, why in HUMAN_PATTERNS:
            if f.startswith(pat) or f == pat:
                r = f"{why} ({f})"
                if not any(x.startswith(why) for x in reasons):
                    reasons.append(r)
    plan_human[pid] = reasons

# ------------------------------------------------------------------ acceptance
def code_plan(files: list[str]) -> bool:
    return any(f.startswith(("src/", "services/")) for f in files)


def test_plan(files: list[str]) -> bool:
    return any(f.startswith(("src/", "tests/", "services/", "Makefile", "pyproject.toml", ".github/", "ci/")) for f in files)


def pin_expr() -> str:
    return "p=$(python3 -c \"import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])\")"


def pcl_commands(phase: int) -> list[str]:
    n = phase
    cmds = [
        f"grep -qF 'Phase {n}: smoke-10m events.hash before: {H}' CHANGELOG.md",
        f"grep -qF 'Phase {n}: smoke-10m events.hash after: {H}' CHANGELOG.md",
    ]
    if n == 15:
        cmds.append(f"grep -qE 'Phase 15: trading-smoke events.hash before: [0-9a-f]{{64}}' CHANGELOG.md")
        cmds.append(f"{pin_expr()} && grep -qF \"Phase 15: trading-smoke events.hash after: $p\" CHANGELOG.md")
    else:
        cmds.append(f"{pin_expr()} && grep -qF \"Phase {n}: trading-smoke events.hash before: $p\" CHANGELOG.md && grep -qF \"Phase {n}: trading-smoke events.hash after: $p\" CHANGELOG.md")
    if n == 14:
        cmds.append("grep -qF 'events-smoke-10m events.hash' CHANGELOG.md")
        cmds.append("grep -qF 'events-soak-3d events.hash' CHANGELOG.md")
    if n == 19:
        cmds.append("for p in 11 12 13 14 15 16 17 18 19; do grep -qF \"Phase $p: smoke-10m events.hash after: " + H + "\" CHANGELOG.md || exit 1; done")
    cmds.append(SMOKE_CMD)
    return cmds


def acceptance(pid: str, phase: int, seat: str, units: list[str]) -> list[str]:
    cmds: list[str] = []
    for u in units:
        for c in U[u]["acceptance_commands"]:
            if c not in cmds:
                cmds.append(c)
    if len(units) == 1 and units[0] in (CLOSER_PCL | CLOSER_PLN) and units[0] in CLOSER_PCL:
        cmds = pcl_commands(phase)
    if units == ["PLN-%d" % phase] or (len(units) == 1 and units[0] in CLOSER_PLN):
        for f in U[units[0]]["files"]:
            if f.endswith("VERIFICATION.md"):
                cmds.append(f"test -f {f}")
    files = plan_files[pid]
    tail: list[str] = []
    if code_plan(files):
        tail += ["make lint", "make typecheck"]
    if test_plan(files) and pid != "11-01" and phase >= 11 and seat not in ("bot-09-journal",) and TSMOKE_PIN_CMD not in cmds:
        tail.append(TSMOKE_PIN_CMD)
    if test_plan(files) and SMOKE_CMD not in cmds:
        tail.append(SMOKE_CMD)
    if code_plan(files) and LIVE_CMD not in cmds:
        tail.append(LIVE_CMD)
    tail.append(OWN_CMD)
    for c in tail:
        if c not in cmds:
            cmds.append(c)
    # a trading pin check is meaningless in plan 11-01 before the pin exists: it ships the pin itself
    for c in cmds:
        if BYPASS.search(c):
            errors.append(f"{pid}: bypass pattern in command {c[:80]}")
    return cmds


# ------------------------------------------------------------------ emit plans.json
out = []
for pid, phase, seat, title, units, od, notes, pr in PLANS:
    reqs: list[str] = []
    for u in units:
        for r in U[u]["requirement_ids"]:
            if r not in reqs:
                reqs.append(r)
    amend = any(U[u]["amendment_wait"] for u in units)
    human = any(U[u]["human_gate"] for u in units) or pid == "18-07"
    if pid == "18-07":
        amend = False
    seat_set = sorted({own(f) for f in plan_files[pid]})
    unit_notes = {u: U[u]["notes"] for u in units if U[u]["notes"]}
    obj = {
        "id": pid,
        "phase": phase,
        "title": title,
        "seat": seat,
        "includes": units,
        "files": plan_files[pid],
        "depends_on": sorted(deps[pid], key=lambda x: (phase_of_plan[x], x)),
        "order_after": sorted(oa[pid], key=lambda x: (phase_of_plan[x], x)),
        "wave": wave[pid],
        "requirement_ids": reqs,
        "acceptance_commands": acceptance(pid, phase, seat, units),
        "human_gate": human,
        "amendment_wait": amend,
        "owner_decision": od,
        "notes": notes,
        "pr": pr,
        "seat_pure": seat != OWNER_APPLIED,
        "owners_of_files": seat_set,
        "human_approver_reasons": plan_human[pid],
        "external_prerequisites": sorted({d for u in units for d in U[u]["depends_on"] if d.startswith("EXT:")}),
        "unit_notes": unit_notes,
    }
    out.append(obj)

json.dump(out, open("/tmp/v4/final/plans.json", "w"), indent=1)
json.dump(
    {
        "plan_of": plan_of,
        "pr_plans": pr_plans,
        "pr_meta": pr_meta,
        "pr_order": [k for k, _, _ in PR_ORDER],
        "pr_deps": pr_deps_reduced,
        "shared": shared_table,
        "errors": errors,
    },
    open("/tmp/v4/final/_model.json", "w"),
    indent=1,
)
print("plans", len(out), "units", len(U), "PRs", len(pr_meta))
from collections import Counter

print("per phase", dict(sorted(Counter(p["phase"] for p in out).items())))
print("errors", len(errors))
for e in errors[:60]:
    print(" -", e)
