"""Tracer: tools/list for chief equals roster plus core over HTTP (TOOL-010).

Entry ``name`` is the transport form (dots to underscores), ``description``
and ``inputSchema`` are verbatim from the roster YAML. No tool logic is
asserted here beyond what the roster files declare.
"""

from __future__ import annotations

import yaml
from conftest import HTTP_OK, rpc_call

from pumpgrok.contracts.projection import effective_roster, transport_name


def _roster_doc(contracts_dir, seat_id):  # type: ignore[no-untyped-def]
    doc = yaml.safe_load((contracts_dir / f"{seat_id}.yaml").read_text(encoding="utf-8"))
    core = yaml.safe_load((contracts_dir / "_core.yaml").read_text(encoding="utf-8"))
    return {entry["name"]: entry for entry in list(doc["tools"]) + list(core["tools"])}


def test_chief_tools_list_equals_roster_plus_core(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts_dir, _registry, _manifests = gateway
    status, body = rpc_call(base_url, "chief", "tools/list", tokens["chief"])
    assert status == HTTP_OK, body
    served = {entry["name"]: entry for entry in body["result"]["tools"]}
    expected = {transport_name(entry["name"]) for entry in effective_roster("bot-00-chief")}
    assert set(served) == expected


def test_chief_entry_schema_verbatim(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, contracts_dir, _registry, _manifests = gateway
    status, body = rpc_call(base_url, "chief", "tools/list", tokens["chief"])
    assert status == HTTP_OK, body
    served = {entry["name"]: entry for entry in body["result"]["tools"]}
    roster = _roster_doc(contracts_dir, "bot-00-chief")
    brief = served["desk_brief"]
    assert brief["description"] == roster["desk.brief"]["description"]
    assert brief["inputSchema"] == roster["desk.brief"]["input"]
