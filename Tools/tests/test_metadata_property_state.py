import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import kblib
import metadata_execution_contract
import metadata_property_state as state


class MetadataPropertyStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        (self.root / "Tools/compiled").mkdir(parents=True)
        (self.root / "kernel/K08 Metadata and Status").mkdir(parents=True)
        for relative in (
                "Tools/operation-capabilities.yaml",
                "Tools/compiled/metadata-execution-contract.json",
                "kernel/K08 Metadata and Status/metadata-authority-base.yaml"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPOSITORY / relative, target)
        capabilities = kblib.parse_yaml_subset(
            (REPOSITORY / "Tools/operation-capabilities.yaml").read_text(
                encoding="utf-8"))
        for relative in metadata_execution_contract.\
                capability_implementation_paths(capabilities):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPOSITORY / relative, target)
        (self.root / "Topics").mkdir()
        (self.root / "Topics/A.md").write_text(
            "---\ntitle: A\nlast_reviewed: 2026-08-01\n---\nBody A\n",
            encoding="utf-8")
        self.coverage = {
            "pages": [{
                "path": "Topics/A.md",
                "coverage_disposition": "required",
                "authoring_status": "drafted",
                "next_batch": "B1",
            }],
        }
        ledger = self.root / ".cambium/state/coverage_ledger.yaml"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(
            kblib.canonical_yaml(self.coverage), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def receipt(self, check, receipt_id="audit-event-1",
                checked_at="2026-08-20T12:00:00Z"):
        return {
            "receipt_id": receipt_id,
            "tool": "fixture",
            "tool_version": "1.0.0",
            "check": check,
            "target": "Topics/A.md",
            "result": "pass",
            "invalidated_by": None,
            "checked_at": checked_at,
        }

    def fingerprint(self):
        return state.semantic_page_snapshot(
            self.root, "Topics/A.md")[1]

    def change_from(self, before_text, after_text):
        page = self.root / "Topics/A.md"
        page.write_text(before_text, encoding="utf-8")
        before = self.fingerprint()
        page.write_text(after_text, encoding="utf-8")
        return {"Topics/A.md": before}

    def test_content_change_establishes_owner_state_without_mtime(self):
        receipt = self.receipt("delta_apply")
        page = self.root / "Topics/A.md"
        original = page.read_text(encoding="utf-8")
        baseline = self.change_from(
            original, original.replace("Body A", "Body B"))
        proposed, paths, events = state.apply_content_change(
            self.coverage, self.root, ["Topics/A.md"], receipt,
            before_semantic_fingerprints=baseline)
        record = proposed["pages"][0]["property_state"][
            "last_content_modified"]
        self.assertEqual("2026-08-20", record["value"])
        self.assertEqual(receipt["receipt_id"], record["evidence_receipt"])
        self.assertEqual(self.fingerprint(), record["content_fingerprint"])
        self.assertEqual(("Topics/A.md",), paths)
        self.assertEqual(
            baseline["Topics/A.md"],
            events[0]["before_semantic_content_sha256"])

    def test_body_only_legacy_page_gets_owner_binding_without_fake_frontmatter(self):
        page = self.root / "Topics/A.md"
        baseline = self.change_from(
            "# A\n\nBody before\n", "# A\n\nBody only\n")
        proposed, paths, _events = state.apply_content_change(
            self.coverage, self.root, ["Topics/A.md"],
            self.receipt("delta_apply"),
            before_semantic_fingerprints=baseline)
        self.assertEqual(("Topics/A.md",), paths)
        self.assertIn(
            "last_content_modified",
            proposed["pages"][0]["property_state"])
        plan = state.build_projection_plan(self.root, proposed, paths)
        self.assertTrue(plan.pages[0].changed)
        after_text = plan.pages[0].after_data.decode("utf-8")
        frontmatter = kblib.parse_yaml_subset(
            kblib.extract_frontmatter(after_text))
        self.assertEqual("2026-08-20",
                         frontmatter["last_content_modified"])
        self.assertTrue(after_text.endswith("# A\n\nBody only\n"))
        self.assertEqual("# A\n\nBody only\n", page.read_text(encoding="utf-8"))

    def test_same_semantic_content_does_not_advance_date(self):
        page = self.root / "Topics/A.md"
        original = page.read_text(encoding="utf-8")
        baseline = self.change_from(
            original, original.replace("Body A", "Body B"))
        first, _paths, _events = state.apply_content_change(
            self.coverage, self.root, ["Topics/A.md"],
            self.receipt("delta_apply"),
            before_semantic_fingerprints=baseline)
        current = self.fingerprint()
        second, paths, events = state.apply_content_change(
            first, self.root, ["Topics/A.md"],
            self.receipt(
                "delta_apply", "audit-event-2", "2026-08-21T12:00:00Z"),
            before_semantic_fingerprints={"Topics/A.md": current})
        self.assertEqual(first, second)
        self.assertEqual((), paths)
        self.assertEqual((), events)

    def test_content_change_tombstones_stale_review(self):
        before = self.fingerprint()
        coverage = copy.deepcopy(self.coverage)
        coverage["pages"][0]["property_state"] = {
            "last_reviewed": {
                "value": "2026-08-19",
                "evidence_receipt": "audit-review-old",
                "content_fingerprint": before,
            },
        }
        (self.root / "Topics/A.md").write_text(
            "---\ntitle: A\nlast_reviewed: 2026-08-19\n---\nBody B\n",
            encoding="utf-8")
        proposed, _paths, events = state.apply_content_change(
            coverage, self.root, ["Topics/A.md"],
            self.receipt("delta_apply"),
            before_semantic_fingerprints={"Topics/A.md": before})
        review = proposed["pages"][0]["property_state"]["last_reviewed"]
        self.assertIsNone(review["value"])
        self.assertEqual(self.fingerprint(), review["content_fingerprint"])
        self.assertTrue(events[0]["last_reviewed_invalidated"])
        self.assertEqual(
            ["last_reviewed"],
            events[0]["invalidated_property_fields"])

    def test_second_content_change_refreshes_existing_review_tombstone(self):
        before = self.fingerprint()
        coverage = copy.deepcopy(self.coverage)
        coverage["pages"][0]["property_state"] = {
            "last_reviewed": {
                "value": None,
                "evidence_receipt": "audit-content-old",
                "content_fingerprint": before,
            },
        }
        page = self.root / "Topics/A.md"
        page.write_text(
            page.read_text(encoding="utf-8").replace("Body A", "Body B"),
            encoding="utf-8")
        receipt = self.receipt(
            "delta_apply", "audit-content-second",
            "2026-08-21T12:00:00Z")
        proposed, _paths, events = state.apply_content_change(
            coverage, self.root, ["Topics/A.md"], receipt,
            before_semantic_fingerprints={"Topics/A.md": before})
        tombstone = proposed["pages"][0]["property_state"]["last_reviewed"]
        self.assertIsNone(tombstone["value"])
        self.assertEqual("audit-content-second", tombstone["evidence_receipt"])
        self.assertEqual(self.fingerprint(), tombstone["content_fingerprint"])
        self.assertEqual(
            ["last_reviewed"],
            events[0]["invalidated_property_fields"])

    def test_content_change_removes_profile_gate_owner_and_page_copy(self):
        contract, core_rules = state._rules(self.root)
        gate_rule = state.gate_projection_rule(
            "readiness_state", ("accepted", "rejected"))
        rules = metadata_execution_contract.AuthorizedProjectionRules(
            tuple(core_rules) + (gate_rule,),
            contract.contract_fingerprint,
            "sha256:" + "1" * 64)
        page = self.root / "Topics/A.md"
        page.write_text(
            "---\ntitle: A\nreadiness_state: accepted\n---\nBody A\n",
            encoding="utf-8")
        before = state.semantic_page_snapshot(
            self.root, "Topics/A.md", rules=rules)[1]
        coverage = copy.deepcopy(self.coverage)
        coverage["pages"][0]["property_state"] = {
            "readiness_state": {
                "value": "accepted",
                "evidence_receipt": "audit-gate-old",
                "content_fingerprint": before,
            },
        }
        page.write_text(
            page.read_text(encoding="utf-8").replace("Body A", "Body B"),
            encoding="utf-8")
        proposed, paths, events = state.apply_content_change(
            coverage, self.root, ["Topics/A.md"],
            self.receipt("delta_apply"), rules=rules,
            before_semantic_fingerprints={"Topics/A.md": before})
        self.assertNotIn(
            "readiness_state", proposed["pages"][0]["property_state"])
        self.assertEqual(
            ["readiness_state"],
            events[0]["invalidated_property_fields"])
        plan = state.build_projection_plan(
            self.root, proposed, paths, rules=rules,
            authorized_owner_removals={
                "Topics/A.md": ["readiness_state"],
            })
        self.assertNotIn(b"readiness_state:", plan.pages[0].after_data)

    def test_projection_only_rewrite_does_not_create_content_event(self):
        before = self.fingerprint()
        page = self.root / "Topics/A.md"
        page.write_text(
            page.read_text(encoding="utf-8").replace(
                "last_reviewed: 2026-08-01",
                "last_reviewed: 2026-08-02"),
            encoding="utf-8")
        # last_reviewed is contract-managed and excluded from the semantic
        # fingerprint.  The opening baseline therefore proves that no
        # substantive content-change event occurred.
        self.assertEqual(before, self.fingerprint())
        proposed, paths, events = state.apply_content_change(
            self.coverage, self.root, ["Topics/A.md"],
            self.receipt("delta_apply"),
            before_semantic_fingerprints={"Topics/A.md": before})
        self.assertEqual(self.coverage, proposed)
        self.assertEqual((), paths)
        self.assertEqual((), events)

    def test_apply_time_first_observation_is_not_a_change_baseline(self):
        with self.assertRaisesRegex(ValueError, "before fingerprints"):
            state.apply_content_change(
                self.coverage, self.root, ["Topics/A.md"],
                self.receipt("delta_apply"),
                before_semantic_fingerprints={})

    def test_review_receipt_sets_current_value_and_projection_plan(self):
        fingerprint = self.fingerprint()
        contract, _rules = state._rules(self.root)
        receipt = self.receipt("page_review_acceptance", "audit-review-1")
        receipt.update({
            "reviewed_on": "2026-08-20",
            "semantic_content_sha256": fingerprint,
            "metadata_execution_contract_fingerprint":
                contract.contract_fingerprint,
        })
        proposed, paths = state.apply_review_acceptance(
            self.coverage, self.root, [receipt],
            metadata_contract_fingerprint=contract.contract_fingerprint)
        record = proposed["pages"][0]["property_state"]["last_reviewed"]
        self.assertEqual("2026-08-20", record["value"])
        plan = state.build_projection_plan(self.root, proposed, paths)
        self.assertTrue(plan.pages[0].changed)
        self.assertIn(
            b"last_reviewed: 2026-08-20", plan.pages[0].after_data)

    def test_content_change_takes_over_legacy_review_with_current_tombstone(self):
        coverage = copy.deepcopy(self.coverage)
        coverage["pages"][0].update({
            "property_state": {},
            "legacy_property_state": {
                "last_reviewed": {
                    "status": "legacy-unverified",
                    "value": "2026-08-01",
                },
            },
        })
        page = self.root / "Topics/A.md"
        before = self.fingerprint()
        page.write_text(
            page.read_text(encoding="utf-8").replace("Body A", "Body B"),
            encoding="utf-8")
        proposed, paths, events = state.apply_content_change(
            coverage, self.root, ["Topics/A.md"],
            self.receipt("delta_apply"),
            before_semantic_fingerprints={"Topics/A.md": before})
        row = proposed["pages"][0]
        self.assertNotIn("legacy_property_state", row)
        self.assertEqual(("Topics/A.md",), paths)
        self.assertTrue(events[0]["last_reviewed_invalidated"])
        self.assertEqual(
            ["last_reviewed"],
            events[0]["invalidated_property_fields"])
        self.assertIsNone(row["property_state"]["last_reviewed"]["value"])
        self.assertEqual(
            "audit-event-1",
            row["property_state"]["last_reviewed"]["evidence_receipt"])

    def test_current_review_takes_over_legacy_marker_atomically(self):
        coverage = copy.deepcopy(self.coverage)
        coverage["pages"][0].update({
            "property_state": {},
            "legacy_property_state": {
                "last_reviewed": {
                    "status": "legacy-unverified",
                    "value": "2026-08-01",
                },
            },
        })
        fingerprint = self.fingerprint()
        contract, _rules = state._rules(self.root)
        receipt = self.receipt(
            "page_review_acceptance", "audit-review-current")
        receipt.update({
            "reviewed_on": "2026-08-20",
            "semantic_content_sha256": fingerprint,
            "metadata_execution_contract_fingerprint":
                contract.contract_fingerprint,
        })
        proposed, _paths = state.apply_review_acceptance(
            coverage, self.root, [receipt],
            metadata_contract_fingerprint=contract.contract_fingerprint)
        row = proposed["pages"][0]
        self.assertNotIn("legacy_property_state", row)
        self.assertEqual(
            "2026-08-20",
            row["property_state"]["last_reviewed"]["value"])

    def test_stale_review_receipt_is_rejected(self):
        receipt = self.receipt("page_review_acceptance", "audit-review-1")
        receipt.update({
            "reviewed_on": "2026-08-20",
            "semantic_content_sha256": "sha256:" + "0" * 64,
        })
        with self.assertRaisesRegex(ValueError, "current semantic content"):
            state.apply_review_acceptance(
                self.coverage, self.root, [receipt])

    def test_gate_transition_is_closed_by_allowed_values(self):
        proposed = state.apply_gate_transition(
            self.coverage, "Topics/A.md", "interview_status",
            "interview-ready", "audit-gate-1", self.fingerprint(),
            ("draft", "interview-ready"))
        self.assertEqual(
            "interview-ready",
            proposed["pages"][0]["property_state"][
                "interview_status"]["value"])
        with self.assertRaisesRegex(ValueError, "not one of"):
            state.apply_gate_transition(
                self.coverage, "Topics/A.md", "interview_status",
                "invented", "audit-gate-1", self.fingerprint(),
                ("draft", "interview-ready"))


if __name__ == "__main__":
    unittest.main()
