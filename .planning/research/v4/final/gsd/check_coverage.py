#!/usr/bin/env python3
"""Coverage check for the v4 GSD documents. Reads the written files, not the generators."""
import json
import re
import sys
import collections

D = "/tmp/v4/final/gsd"
PLANS = json.load(open("/tmp/v4/final/plans.json"))
REQ = open(D + "/REQUIREMENTS.md").read()
ROAD = open(D + "/ROADMAP.md").read()
PROJ = open(D + "/PROJECT.md").read()
STATE = open(D + "/STATE.md").read()
V3 = open("/root/src/repos/pumpgrok/.planning/REQUIREMENTS.md").read()

fail = []


def check(cond, msg):
    if not cond:
        fail.append(msg)


# 1. requirement ids from checkbox lines
ids = re.findall(r"^- \[.\] ([A-Z]+-\d+):", REQ, re.M)
check(len(ids) == len(set(ids)), "duplicate checkbox ids")
idset = set(ids)

# plan side
plan_ids = collections.defaultdict(set)
for p in PLANS:
    for r in p["requirement_ids"]:
        plan_ids[r].add(p["phase"])

check(idset == set(plan_ids), "id sets differ: only in requirements=%s only in plans=%s" % (sorted(idset - set(plan_ids)), sorted(set(plan_ids) - idset)))

# 2. traceability: exactly one row per id, one phase each, phase carried by a plan of that phase
trace = re.findall(r"^\| ([A-Z]+-\d+) \| Phase (\d+) [^|]+\| (\w+) \|$", REQ, re.M)
tc = collections.Counter(t[0] for t in trace)
check(all(n == 1 for n in tc.values()), "an id appears in more than one traceability row: %s" % [k for k, n in tc.items() if n > 1])
check(set(tc) == idset, "traceability ids differ from checkbox ids")
phase_of = {t[0]: int(t[1]) for t in trace}
check(all(t[2] == "Pending" for t in trace), "a status is not Pending")
for r, ph in phase_of.items():
    check(ph in plan_ids[r], "%s mapped to phase %d but carried by plans of phases %s" % (r, ph, sorted(plan_ids[r])))

# 3. roadmap requirement lines equal the traceability
road_req = {}
for m in re.finditer(r"### Phase (\d+): [^\n]*\n.*?\*\*Requirements\*\*: ([^\n]+)\n", ROAD, re.S):
    road_req[int(m.group(1))] = [x.strip() for x in m.group(2).split(",")]
check(sorted(road_req) == list(range(11, 20)), "roadmap phases: %s" % sorted(road_req))
rm = {}
for ph, rs in road_req.items():
    for r in rs:
        check(r not in rm, "%s listed in two roadmap phases" % r)
        rm[r] = ph
check(rm == phase_of, "roadmap Requirements lines differ from traceability")

# 4. cited ids valid; every phase requirement cited in a criterion of its phase
v3ids = set(re.findall(r"^- \[.\] ([A-Z]+-\d+):", V3, re.M))
for m in re.finditer(r"### Phase (\d+): .*?\*\*Success Criteria\*\*[^\n]*\n(.*?)\*\*Checkpoint\*\*", ROAD, re.S):
    ph = int(m.group(1))
    block = m.group(2)
    crit = re.findall(r"^  (\d+)\. (.*)$", block, re.M)
    check(len(crit) >= 8, "phase %d has %d criteria" % (ph, len(crit)))
    for n, c in crit:
        tail = re.findall(r"\(([^()]*)\)\s*$", c.strip())
        cited = [x for x in re.findall(r"[A-Z]+-\d+", c) if not x.startswith("G-")]
        for r in cited:
            check(r in idset or r in v3ids, "phase %d criterion %s cites unknown id %s" % (ph, n, r))
        check(bool(tail) and re.search(r"[A-Z]+-\d+", tail[-1]) is not None, "phase %d criterion %s does not end with a requirement id" % (ph, n))
    alltext = " ".join(c for _, c in crit)
    for r in road_req[ph]:
        check(r in alltext, "phase %d requirement %s not cited in a criterion" % (ph, r))

# 5. plan counts and ids in roadmap
for ph in range(11, 20):
    ps = [p["id"] for p in PLANS if p["phase"] == ph]
    m = re.search(r"### Phase %d: .*?\*\*Plans\*\*: (\d+) planned \(([^)]*)\)[^\n]*" % ph, ROAD, re.S)
    check(m is not None and int(m.group(1)) == len(ps), "plan count for phase %d" % ph)
    for i in ps:
        check(("%s" % i) in m.group(0), "plan %s missing from roadmap phase %d line" % (i, ph))
check(len(PLANS) == 74, "plans.json does not hold 74 plans")
check("Coverage: all %d v4 requirements" % len(idset) in ROAD, "roadmap coverage line count")
check("**Coverage: v4 requirements: %d total, %d mapped, 0 unmapped**" % (len(idset), len(phase_of)) in REQ, "requirements coverage line")
check("Coverage: v4 requirements" in REQ, "11-09 acceptance string 'Coverage: v4 requirements'")
check("Phase 11: Engineering foundation" in ROAD, "11-09 acceptance string 'Phase 11: Engineering foundation'")

# 6. progress table all Not started
prog = re.findall(r"^\| (\d+)\. [^|]+\| (\d+)/(\d+) \| ([^|]+) \| ([^|]+) \|$", ROAD, re.M)
check(len(prog) == 9 and all(p[3].strip() == "Not started" and p[1] == "0" for p in prog), "progress table")
for p in prog:
    check(int(p[2]) == len([x for x in PLANS if x["phase"] == int(p[0])]), "progress plan count phase %s" % p[0])

# 7. hygiene across all four docs
for name, txt in (("ROADMAP", ROAD), ("REQUIREMENTS", REQ), ("PROJECT", PROJ), ("STATE", STATE)):
    check(all(ord(c) < 128 for c in txt), "%s has non-ASCII" % name)
    for bad in ("--collect-only", "pytest --co ", "|| true", "--dry-run", "2>/dev/null", ">/dev/null"):
        check(bad not in txt, "%s contains forbidden %r" % (name, bad))
# STATE frontmatter
check(STATE.startswith("---\n") and "milestone: v4" in STATE and "total_plans: 74" in STATE and "total_phases: 9" in STATE, "state frontmatter")
check(PROJ.rstrip().endswith("*Last updated: 2026-10-28 after the v4 roadmap and requirements were written (owner decisions V4-1 to V4-14)*") or "2026-10-28" in PROJ.splitlines()[-1], "project footer date")
# V2 and V3 decisions verbatim
cur = open("/root/src/repos/pumpgrok/.planning/PROJECT.md").read().splitlines()
for line in cur:
    if re.match(r"^\| (D\d|R\d+|V2-O\d|V3-\d)[:]", line):
        check(line in PROJ.splitlines(), "decision row not verbatim: %s" % line[:60])

print("requirement ids (checkbox lines):", len(ids))
print("distinct ids in plans.json requirement_ids:", len(plan_ids))
print("ids in requirements but in no plan:", sorted(idset - set(plan_ids)))
print("ids in plans but not in requirements:", sorted(set(plan_ids) - idset))
print("traceability rows:", len(trace), "unique:", len(tc), "ids with more than one row:", [k for k, n in tc.items() if n > 1])
print("ids whose mapped phase is not a phase of a carrying plan:", [r for r, ph in phase_of.items() if ph not in plan_ids[r]])
cnt = collections.Counter(phase_of.values())
print("requirements per phase:", dict(sorted(cnt.items())), "sum", sum(cnt.values()))
multi = {r: sorted(v) for r, v in plan_ids.items() if len(v) > 1}
print("ids carried by plans of several phases, each resolved to exactly one:", {r: "%s -> %d" % (v, phase_of[r]) for r, v in sorted(multi.items())})
print("ROADMAP Requirements lines match Traceability:", rm == phase_of)
print("every phase requirement cited in a criterion of its phase:", not [f for f in fail if "not cited" in f])
if fail:
    print("FAILURES:")
    for f in fail:
        print(" -", f)
    sys.exit(1)
print("RESULT: OK")
