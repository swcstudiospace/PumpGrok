#!/usr/bin/env python3
"""Convert a Bandit JSON report into minimal SARIF 2.1.0.

Exists because bandit's own `-f sarif` cannot be combined with `-b/--baseline`
(confirmed: doing so errors out; see .github/workflows/security-pr.yml). The
Bandit PR gate baselines against the base ref so it only fails on genuinely new
findings; the SARIF artifact must reflect that same filtered set, not a fresh
unfiltered whole-repo scan, or it would list findings the gate itself already
suppressed as pre-existing.

    python3 ci/security/bandit_json_to_sarif.py bandit.json bandit.sarif
"""

from __future__ import annotations

import json
import sys
from urllib.parse import quote

SEVERITY_TO_LEVEL = {"HIGH": "error", "MEDIUM": "warning", "LOW": "note"}


def convert(json_path: str, sarif_path: str) -> None:
    data = json.load(open(json_path))
    results = []
    rules: dict[str, str] = {}

    for r in data.get("results", []):
        rule_id = r["test_id"]
        rules.setdefault(rule_id, r.get("test_name", rule_id))
        results.append({
            "ruleId": rule_id,
            "level": SEVERITY_TO_LEVEL.get(r.get("issue_severity", ""), "warning"),
            "message": {"text": r.get("issue_text", "")},
            "locations": [{
                "physicalLocation": {
                    # SARIF artifactLocation.uri is a URI, not a bare path: a literal '#' would
                    # be read as a fragment separator and a literal space makes the URI invalid
                    # outright — quote() percent-encodes both, keeping '/' as a path separator.
                    "artifactLocation": {"uri": quote(r["filename"], safe="/")},
                    "region": {"startLine": r.get("line_number", 1)},
                }
            }],
        })

    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "Bandit",
                "informationUri": "https://bandit.readthedocs.io/",
                "rules": [{"id": rid, "name": name} for rid, name in rules.items()],
            }},
            "results": results,
        }],
    }
    json.dump(sarif, open(sarif_path, "w"), indent=2)


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
