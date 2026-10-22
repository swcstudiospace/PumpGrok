"""Regression tests for ci/gates/check_contracts.py review findings (G-4)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

GATES = Path(__file__).resolve().parents[1] / "gates"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_contracts", GATES / "check_contracts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

BOTS = ["bot-00-chief", "bot-01-scout", "bot-04-sniper", "bot-09-journal"]
MANIFEST = {
    "bots": BOTS,
    "ownership": [],
    "contract_consumers": {"contracts/events/**": BOTS},
}
EVENT = "contracts/events/x.json"


def _doc(**overrides) -> dict:
    doc = {
        "change_id": "C-1",
        "proposed_by": "bot-04-sniper",
        "surface": EVENT,
        "breaking": False,
        "version": "1.1.0",
        "summary": "s",
        "semantic_changes": [],
        "acknowledgements": [{"bot": bot, "ack": True} for bot in BOTS],
    }
    doc.update(overrides)
    return doc


def _breaking(**overrides) -> dict:
    base = {
        "breaking": True,
        "version": "2.0.0",
        "previous_version": "1.0.0",
        "migration_note": "rename x",
    }
    base.update(overrides)
    return _doc(**base)


# Finding 6: a document must not shrink the manifest's consumer set.
class TestConsumersCannotBeShrunk:
    def test_document_cannot_drop_a_manifest_consumer(self):
        acks = [{"bot": b, "ack": True} for b in BOTS if b != "bot-09-journal"]
        doc = _breaking(consumers_required=["bot-00-chief"], acknowledgements=acks)
        problems = gate.check_change_doc(doc, MANIFEST, touched=[EVENT], change_path=None)
        assert any("no acknowledgement from 'bot-09-journal'" in p for p in problems)

    def test_document_may_add_a_consumer_without_dropping_manifest_ones(self):
        acks = [{"bot": b, "ack": True} for b in BOTS if b != "bot-00-chief"]
        doc = _breaking(consumers_required=["bot-09-journal"], acknowledgements=acks)
        problems = gate.check_change_doc(doc, MANIFEST)
        assert any("no acknowledgement from 'bot-00-chief'" in p for p in problems)


# Finding 7: a breaking major bump must be verifiable against a previous version.
class TestVersionBump:
    def test_breaking_at_unchanged_major_is_refused(self):
        doc = _breaking(version="1.0.0", previous_version="1.0.0")
        problems = gate.check_change_doc(doc, MANIFEST)
        assert any("major version did not increase" in p for p in problems)

    def test_breaking_without_previous_version_is_refused(self):
        doc = _breaking(version="2.0.0")
        del doc["previous_version"]
        problems = gate.check_change_doc(doc, MANIFEST)
        assert any("no 'previous_version'" in p for p in problems)

    def test_malformed_previous_version_is_refused(self):
        doc = _breaking(previous_version="banana")
        problems = gate.check_change_doc(doc, MANIFEST)
        assert any("previous_version 'banana' is not semver" in p for p in problems)

    def test_breaking_with_increased_major_passes(self):
        assert gate.check_change_doc(_breaking(), MANIFEST) == []


# Finding 8: a blank surface must not skip the coverage check.
class TestBlankSurfaceCoverage:
    def test_blank_surface_cannot_skip_coverage(self):
        doc = _doc(surface="", consumers_required=["bot-00-chief"])
        problems = gate.check_change_doc(doc, MANIFEST, touched=[EVENT])
        assert any("does not cover every contract surface" in p for p in problems)

    def test_no_touched_list_means_no_coverage_check(self):
        doc = _doc(surface="")
        problems = gate.check_change_doc(doc, MANIFEST, touched=None)
        assert not any("does not cover" in p for p in problems)


# Finding 9: an old change document must not validate a change it did not describe.
class TestChangeDocMustBeInDiff:
    def test_stale_document_not_in_diff_is_refused(self, tmp_path):
        doc_path = tmp_path / "contracts" / "changes" / "old.yaml"
        problems = gate._change_doc_in_diff_problems([EVENT], doc_path, repo_root=tmp_path)
        assert any("not added or updated in this diff" in p for p in problems)

    def test_document_added_in_diff_passes(self, tmp_path):
        doc_path = tmp_path / "contracts" / "changes" / "new.yaml"
        files = [EVENT, "contracts/changes/new.yaml"]
        assert gate._change_doc_in_diff_problems(files, doc_path, repo_root=tmp_path) == []

    def test_document_outside_repository_is_refused(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        problems = gate._change_doc_in_diff_problems(
            [EVENT], tmp_path / "elsewhere.yaml", repo_root=repo
        )
        assert any("outside this repository" in p for p in problems)


# Finding 18: a surface whose only consumer is the proposer needs no acks, not a refusal.
class TestProposerAsSoleConsumer:
    def test_surface_whose_only_consumer_is_the_proposer_passes(self):
        manifest = {
            "bots": BOTS,
            "ownership": [],
            "contract_consumers": {"contracts/tools/**": ["bot-04-sniper"]},
        }
        doc = _doc(
            surface="contracts/tools/x.yaml",
            acknowledgements=[],
        )
        touched = ["contracts/tools/x.yaml"]
        assert gate.check_change_doc(doc, manifest, touched=touched) == []

    def test_unknown_surface_is_still_refused(self):
        doc = _doc(surface="contracts/unknown.yaml", acknowledgements=[])
        problems = gate.check_change_doc(doc, MANIFEST)
        assert any("no consumers resolved" in p for p in problems)


# Findings 4/5 shared fixes in this gate: directory-anchored '**/' and no rename hiding.
class TestMatchAnchoring:
    def test_double_star_keeps_its_directory_anchor(self):
        assert gate._match("mine/**/*.py", "mine/a/b.py") is True
        assert gate._match("mine/**/*.py", "other/private.py") is False

    def test_leading_double_star_matches_at_any_depth(self):
        assert gate._match("**/*.rs", "a/b/c.rs") is True
        assert gate._match("**/*.rs", "c.rs") is True

    def test_wildcard_directory_prefix_still_matches(self):
        # A wildcard segment in the head must match by segment, not by literal prefix.
        assert gate._match("src/*/**/*.py", "src/app/main.py") is True
        assert gate._match("src/*/**/*.py", "src/app/sub/main.py") is True
        assert gate._match("src/*/**/*.py", "lib/app/main.py") is False
        assert gate._match("src/*/**/*.py", "src/main.py") is False
