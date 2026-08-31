"""One machine owner for Coverage, Work Spec, and Delta field shapes."""

import ast
import copy
import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import Tools.execution.task_runtime.amendment_policy as amendment_policy  # noqa: E402
import Tools.execution.task_runtime.amendment_plan as amendment_plan  # noqa: E402
import Tools.execution.planning.compile_queue as compile_queue  # noqa: E402
import Tools.execution.planning.coverage_contract as coverage_contract  # noqa: E402
import Tools.execution.planning.coverage_delta as coverage_delta  # noqa: E402
import Tools.platform.distribution.module_boundary_facts as module_boundary_facts  # noqa: E402
import Tools.execution.task_runtime.queue_runtime.coverage as runtime_coverage  # noqa: E402
import Tools.execution.task_runtime.queue_runtime.delta as runtime_delta  # noqa: E402
import Tools.execution.task_runtime.queue_runtime.runtime as runtime_validator  # noqa: E402
from Tools.tests.support.coverage_delta_fixture import (  # noqa: E402
    premerge_delta_document,
)


def coverage():
    return {
            "schema_version": 2,
        "task_id": "task",
        "updated_at": "2026-08-27T00:00:00Z",
        "scope_version": "s1",
        "upstream_revision_id": "3.9.2",
        "selected_profile_manifest": "profiles/p/profile.yaml",
        "batch_specs": [],
        "maintenance_candidates": [],
        "pages": [],
        "open_gaps": [],
    }


def batch_spec(batch_id="B1"):
    return {
        "id": batch_id,
        "family": "Core",
        "order_hint": 1,
        "source_route": "R03",
        "execution_mode": "serial-integrator",
        "depends_on": [],
        "confirmation_required": False,
        "work_spec_path": None,
        "work_spec_sha256": None,
    }


def required_page(batch_id="B1"):
    return {
        "path": "Topics/A.md",
        "coverage_disposition": "required",
        "canonical_owner": "Topics/A.md",
        "type": "concept",
        "priority": "P1",
        "tier": "M",
        "authoring_status": "drafted",
        "prerequisites": [],
        "batch": batch_id,
        "next_batch": batch_id,
        "deferred_reason": None,
        "reentry_condition": None,
        "gate_receipts": [],
        "property_state": {},
    }


def planned_page(batch_id="B1"):
    page = required_page(batch_id)
    for field in ("authoring_status", "gate_receipts", "property_state"):
        page.pop(field)
    return page


def _literal_string_set(node):
    """Read a top-level literal collection, including frozenset((...))."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and \
            node.func.id in ("frozenset", "set", "tuple", "list") and \
            len(node.args) == 1 and not node.keywords:
        node = node.args[0]
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return None
    values = []
    for child in node.elts:
        if not isinstance(child, ast.Constant) or not isinstance(
                child.value, str):
            return None
        values.append(child.value)
    return frozenset(values)


class SharedShapeOwnershipTests(unittest.TestCase):
    def test_every_consumer_projection_is_the_owner_object(self):
        self.assertIs(
            coverage_contract.COVERAGE_TOP_LEVEL_FIELDS,
            amendment_policy.TOP_LEVEL_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_TOP_LEVEL_FIELDS,
            runtime_validator.COVERAGE_TOP_LEVEL_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_TOP_LEVEL_FIELDS,
            compile_queue.COVERAGE_TOP_LEVEL_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_PAGE_FIELDS,
            amendment_policy.PAGE_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_PROMOTION_FIELDS,
            amendment_policy.PROMOTION_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_BATCH_SPEC_FIELDS,
            amendment_policy.BATCH_SPEC_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_BATCH_SPEC_FIELDS,
            runtime_coverage.COVERAGE_BATCH_SPEC_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_BATCH_SPEC_FIELDS,
            compile_queue.BATCH_SPEC_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_REROUTE_FIELDS,
            amendment_policy.REROUTE_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_REROUTE_FIELDS,
            compile_queue.REPLAN_PAGE_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_DELTA_FIELDS,
            runtime_delta.DELTA_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_DELTA_PAGE_CONTROL_FIELDS,
            runtime_delta.DELTA_CONTROL_FIELDS)
        self.assertIs(
            coverage_contract.COVERAGE_DELTA_PAGE_CONTROL_FIELDS,
            coverage_delta.DELTA_PAGE_CONTROL_FIELDS)

    def test_no_other_shipped_module_redeclares_a_shared_shape_literal(self):
        protected = {
            coverage_contract.COVERAGE_TOP_LEVEL_FIELDS,
            coverage_contract.COVERAGE_PAGE_FIELDS,
            coverage_contract.COVERAGE_PLANNED_PAGE_FIELDS,
            coverage_contract.COVERAGE_RUNTIME_PAGE_REQUIRED_FIELDS,
            coverage_contract.COVERAGE_REROUTE_FIELDS,
            coverage_contract.COVERAGE_BATCH_SPEC_FIELDS,
            coverage_contract.COVERAGE_DELTA_FIELDS,
            coverage_contract.COVERAGE_DELTA_PAGE_CONTROL_FIELDS,
        }
        owner_paths = {
            "execution/planning/coverage_contract.py",
        }
        duplicates = []
        for relative in module_boundary_facts.shipped_modules(str(TOOLS)):
            if relative in owner_paths:
                continue
            path = TOOLS / relative
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                value = node.value if isinstance(
                    node, (ast.Assign, ast.AnnAssign)) else None
                literal = _literal_string_set(value)
                if literal in protected:
                    duplicates.append("%s:%d" % (relative, node.lineno))
        self.assertEqual(
            [], duplicates,
            "shared shape literals must be projected from their owner: %s" %
            ", ".join(duplicates))


class SharedShapeBehaviorTests(unittest.TestCase):
    def test_planning_and_runtime_page_shapes_are_distinct_closed_forms(self):
        self.assertEqual(
            [], coverage_contract.page_shape_errors(
                planned_page(), "planned"))
        self.assertEqual(
            coverage_contract.PAGE_FORM_PLANNING,
            coverage_contract.classify_page_form(planned_page()))
        self.assertTrue(coverage_contract.is_planning_page(planned_page()))
        self.assertTrue(coverage_contract.is_complete_planning_page(
            planned_page()))
        self.assertEqual(
            [], coverage_contract.page_shape_errors(
                required_page(), "runtime"))
        self.assertEqual(
            coverage_contract.PAGE_FORM_CURRENT_RUNTIME,
            coverage_contract.classify_page_form(required_page()))
        self.assertFalse(coverage_contract.is_planning_page(required_page()))

        partial = planned_page()
        partial["authoring_status"] = "reviewed"
        errors = coverage_contract.page_shape_errors(partial, "partial")
        self.assertTrue(any("partially materializes" in error
                            for error in errors), errors)
        self.assertEqual(
            coverage_contract.PAGE_FORM_MALFORMED,
            coverage_contract.classify_page_form(partial))
        self.assertFalse(coverage_contract.is_complete_planning_page(
            {"path": "Topics/Only.md"}))
        self.assertEqual(
            coverage_contract.PAGE_FORM_MALFORMED,
            coverage_contract.classify_page_form({"path": "Topics/Only.md"}))

        incomplete_runtime = required_page()
        incomplete_runtime.pop("property_state")
        self.assertEqual(
            coverage_contract.PAGE_FORM_MALFORMED,
            coverage_contract.classify_page_form(incomplete_runtime))
        self.assertTrue(coverage_contract.page_shape_errors(
            incomplete_runtime, "incomplete runtime"))

    def test_unknown_coverage_top_level_field_stays_rejected_by_both_paths(self):
        current = coverage()
        proposal = copy.deepcopy(current)
        proposal["unexpected"] = True

        with self.assertRaisesRegex(
                ValueError,
                "unsupported top-level field\\(s\\): unexpected"):
            compile_queue.validate_same_scope_proposal(current, proposal)
        with self.assertRaisesRegex(
                ValueError,
                "unsupported top-level field\\(s\\): unexpected"):
            amendment_plan.validate_coverage_proposal(
                current, proposal, {
                    "scope_version_before": "s1",
                    "scope_version_after": "s1",
                })
        impact = amendment_policy.derive_amendment_impact(
            current, proposal, {"required_queue": []})
        self.assertIn(
            "unsupported Coverage top-level field change(s): unexpected",
            impact["forbidden_reasons"])

    def test_reroute_stays_accepted_by_compiler_and_classifier(self):
        current = coverage()
        current["batch_specs"] = [batch_spec()]
        current["pages"] = [required_page()]
        proposal = copy.deepcopy(current)
        proposal["pages"][0]["batch"] = "B2"
        proposal["pages"][0]["next_batch"] = "B2"

        self.assertEqual(
            ["Topics/A.md"],
            compile_queue.validate_same_scope_proposal(current, proposal))
        impact = amendment_policy.derive_amendment_impact(
            current, proposal,
            {"required_queue": [{"id": "B1", "state": "queued"}]})
        self.assertEqual([], impact["forbidden_reasons"])
        self.assertEqual(
            [amendment_policy.CHANGE_REQUIRED_REROUTE],
            impact["change_classes"])

    def test_apply_and_runtime_reject_each_delta_control_field(self):
        base_delta = premerge_delta_document(
            "B1", "Topics/A.md", ["gate-1"],
            generated_at="2026-08-27T00:00:00Z")
        item = {"id": "B1", "manifest": ["Topics/A.md"]}
        records = {
            "Topics/A.md": {"batch": "B1", "next_batch": "B1"},
        }
        ledger = {"open_gaps": []}
        for field in sorted(
                coverage_contract.COVERAGE_DELTA_PAGE_CONTROL_FIELDS):
            with self.subTest(field=field):
                delta = copy.deepcopy(base_delta)
                delta["pages"][0][field] = None
                apply_errors = coverage_delta.delta_policy_errors(delta)
                runtime_errors, _settlement, _report = \
                    runtime_delta.delta_handoff_errors(
                        ".cambium/deltas/B1.yaml", delta, item, records,
                        ledger, {}, {})
                self.assertIn(
                    "pages[0] contains worker-forbidden Coverage control "
                    "field(s): %s" % field,
                    apply_errors)
                self.assertIn(
                    "pages[0] contains control field(s): %s" % field,
                    runtime_errors)


if __name__ == "__main__":
    unittest.main()
