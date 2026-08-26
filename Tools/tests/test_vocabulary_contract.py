"""Single-owner and unchanged-behaviour tests for K08 Tool projections."""

import ast
import datetime
from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import check_freshness
import compile_queue
import freshness_engine
import kblib
import vocabulary_contract


def assignment_value(module, name):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    values = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name
               for target in targets):
            values.append(node.value)
    if len(values) != 1:
        raise AssertionError("expected one assignment for %s" % name)
    return values[0]


class VocabularyContractTests(unittest.TestCase):
    def source_document(self):
        return kblib.parse_yaml_subset(
            (REPOSITORY / vocabulary_contract.VOCABULARY_BASE_PATH).read_text(
                encoding="utf-8"))

    def test_shipped_projection_is_strict_and_immutable(self):
        projection = vocabulary_contract.load_vocabulary_base(REPOSITORY)
        self.assertEqual(
            {"P0": 0, "P1": 1, "P2": 2},
            dict(projection["priority_order"]))
        self.assertEqual(
            {"fast": 120, "slow": 365, "stable": None},
            dict(projection["review_intervals_days"]))
        with self.assertRaises(TypeError):
            projection["priority_values"] = ()
        with self.assertRaises(TypeError):
            projection["priority_order"]["P0"] = 9
        with self.assertRaises(TypeError):
            projection["review_intervals_days"]["fast"] = 1

    def test_projection_follows_owner_values_without_python_fallbacks(self):
        document = self.source_document()
        document["fields"]["priority"]["values"] = ["urgent", "normal"]
        document["fields"]["volatility"]["values"] = ["moving", "fixed"]
        document["review_intervals_days"] = {"moving": 7, "fixed": None}
        projection = vocabulary_contract.validate_vocabulary_base(document)
        self.assertEqual(
            {"urgent": 0, "normal": 1},
            dict(projection["priority_order"]))
        self.assertEqual(
            {"moving": 7, "fixed": None},
            dict(projection["review_intervals_days"]))

    def test_missing_extra_or_invalid_intervals_fail_closed(self):
        cases = []
        missing = self.source_document()
        del missing["review_intervals_days"]["fast"]
        cases.append(missing)
        extra = self.source_document()
        extra["review_intervals_days"]["invented"] = 9
        cases.append(extra)
        boolean = self.source_document()
        boolean["review_intervals_days"]["fast"] = True
        cases.append(boolean)
        duplicate_priority = self.source_document()
        duplicate_priority["fields"]["priority"]["values"].append("P0")
        cases.append(duplicate_priority)
        for document in cases:
            with self.subTest(document=document):
                with self.assertRaises(
                        vocabulary_contract.VocabularyContractError):
                    vocabulary_contract.validate_vocabulary_base(document)

    def test_all_runtime_compatibility_names_share_owner_identity(self):
        self.assertIs(
            vocabulary_contract.PRIORITY_ORDER,
            freshness_engine.PRIORITY_ORDER)
        self.assertIs(
            vocabulary_contract.PRIORITY_ORDER,
            compile_queue.PRIORITY)
        self.assertIs(
            vocabulary_contract.REVIEW_INTERVALS_DAYS,
            freshness_engine.INTERVAL_DAYS)
        self.assertIs(
            vocabulary_contract.REVIEW_INTERVALS_DAYS,
            check_freshness.INTERVAL_DAYS)

    def test_compatibility_assignments_are_projections_not_literals(self):
        for module, name in (
                (freshness_engine, "INTERVAL_DAYS"),
                (freshness_engine, "PRIORITY_ORDER"),
                (check_freshness, "INTERVAL_DAYS"),
                (compile_queue, "PRIORITY")):
            with self.subTest(module=module.__name__, name=name):
                value = assignment_value(module, name)
                self.assertIsInstance(value, ast.Attribute)
                self.assertEqual("vocabulary_contract", value.value.id)

    def test_queue_priority_tiebreak_behaviour_is_unchanged(self):
        def batch_spec(batch_id):
            return {
                "id": batch_id,
                "family": "Fixture",
                "order_hint": None,
                "source_route": None,
                "execution_mode": "concurrent-worker",
                "depends_on": [],
                "confirmation_required": False,
                "work_spec_path": None,
                "work_spec_sha256": None,
            }

        coverage = {
            "batch_specs": [
                batch_spec("B-P2"), batch_spec("B-P0"), batch_spec("B-P1")],
            "pages": [
                {"path": "P2.md", "coverage_disposition": "required",
                 "batch": "B-P2", "priority": "P2"},
                {"path": "P0.md", "coverage_disposition": "required",
                 "batch": "B-P0", "priority": "P0"},
                {"path": "P1.md", "coverage_disposition": "required",
                 "batch": "B-P1", "priority": "P1"},
            ],
        }
        compiled, _changed = compile_queue.compile_document(
            {"queue_revision": 0, "required_queue": []}, coverage)
        self.assertEqual(
            ["B-P0", "B-P1", "B-P2"],
            [item["id"] for item in compiled["required_queue"]])

    def test_freshness_cutoff_behaviour_is_unchanged(self):
        as_of = datetime.date(2026, 8, 27)
        baseline = as_of - datetime.timedelta(
            days=vocabulary_contract.REVIEW_INTERVALS_DAYS["fast"])
        snapshot = freshness_engine.PageSnapshot(
            path="Topic.md",
            frontmatter={
                "priority": "P0",
                "volatility": "fast",
                "last_verified": baseline.isoformat(),
            },
            modified_on=baseline,
        )
        outcome = freshness_engine.classify_page(
            snapshot, freshness_engine.FreshnessPolicy(as_of=as_of))
        self.assertEqual(freshness_engine.OVERDUE, outcome.kind)
        self.assertEqual(0, outcome.overdue_days)


if __name__ == "__main__":
    unittest.main()
