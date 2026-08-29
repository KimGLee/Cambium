"""Kernel-owned runtime state model and Tool projection tests."""

import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import kblib  # noqa: E402
import metadata_execution_contract  # noqa: E402
import runtime_state_contract as contract  # noqa: E402
from queue_runtime import canon  # noqa: E402


class ShippedModelTests(unittest.TestCase):
    def test_shipped_model_is_closed_and_has_no_implementation_path(self):
        loaded = contract.load_model(REPOSITORY)
        self.assertEqual(contract.MODEL_ID,
                         loaded["document"]["model_id"])

        def strings(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key
                    yield from strings(item)
            elif isinstance(value, list):
                for item in value:
                    yield from strings(item)
            elif isinstance(value, str):
                yield value

        self.assertFalse(any(
            value.startswith("Tools/")
            for value in strings(loaded["document"])
        ))

    def test_longstanding_facade_constants_are_registry_projections(self):
        self.assertIs(kblib.BATCH_LIFECYCLE_TRANSITIONS,
                      contract.BATCH_LIFECYCLE_TRANSITIONS)
        self.assertIs(canon.STATES, contract.STATES)
        self.assertIs(canon.HOLDS, contract.HOLDS)
        self.assertIs(canon.TASK_STATES, contract.TASK_STATES)

    def test_registry_state_order_is_a_complete_presentation_projection(self):
        self.assertEqual(contract.QUEUE_STATES,
                         frozenset(contract.QUEUE_STATE_ORDER))
        self.assertEqual(contract.TASK_STATES,
                         frozenset(contract.TASK_STATE_ORDER))
        self.assertEqual(len(contract.QUEUE_STATES),
                         len(contract.QUEUE_STATE_ORDER))
        self.assertEqual(len(contract.TASK_STATES),
                         len(contract.TASK_STATE_ORDER))

    def test_k08_vocabulary_does_not_redeclare_runtime_task_states(self):
        vocabulary = kblib.parse_yaml_subset((
            REPOSITORY /
            "kernel/K08 Metadata and Status/vocabulary-base.yaml"
        ).read_text(encoding="utf-8"))

        self.assertNotIn("task_state", vocabulary)

    def test_canonical_ledger_identity_and_fingerprint_relationship(self):
        self.assertEqual(("coverage", "queue", "progress"),
                         contract.RUNTIME_LEDGER_IDS)
        self.assertEqual({
            "coverage": "coverage_sha256",
            "queue": "queue_sha256",
            "progress": "progress_sha256",
        }, dict(contract.RUNTIME_LEDGER_FINGERPRINT_BY_ID))

    def test_named_runtime_subsets_project_from_state_and_edge_semantics(self):
        self.assertEqual(
            frozenset(("merge-ready", "closed")),
            contract.QUEUE_DELTA_BOUND_STATES,
        )
        self.assertEqual(
            frozenset(("queued", "merge-ready")),
            contract.BATCH_OPENING_SOURCE_STATES,
        )
        self.assertEqual(
            frozenset(("open", "merge-ready", "closed")),
            contract.QUEUE_STARTED_STATES,
        )
        self.assertIn("merge-ready", contract.QUEUE_NONTERMINAL_STATES)
        self.assertEqual(
            frozenset(("planned", "active")),
            contract.BATCH_ACTIVATION_TASK_STATES,
        )

    def test_amendment_behavior_classes_project_from_operation_records(self):
        self.assertEqual(
            frozenset(("gap-routing-reconciliation",
                       "property-state-migration")),
            contract.SCOPE_PRESERVING_AMENDMENT_OPERATIONS,
        )
        self.assertEqual(
            frozenset(("scope-replan", "gap-routing-reconciliation",
                       "property-state-migration")),
            contract.STATE_REVISION_PRESERVING_AMENDMENT_OPERATIONS,
        )
        self.assertEqual(
            contract.STATE_REVISION_PRESERVING_AMENDMENT_OPERATIONS,
            contract.CANCEL_ID_FORBIDDEN_AMENDMENT_OPERATIONS,
        )

    def test_tool_registry_binds_each_current_execution_capability(self):
        document = metadata_execution_contract.load_operation_capabilities(
            REPOSITORY)
        registered = {
            row["capability_id"]: row
            for row in document["capabilities"]
        }
        expected_owners = {
            contract.ORDINARY_QUEUE_TRANSITION_CAPABILITY:
                "Tools/update_queue.py",
            contract.AMENDMENT_BATCH_CANCELLATION_CAPABILITY:
                "Tools/apply_amendment.py",
            contract.TASK_TRANSITION_CAPABILITY:
                "Tools/update_task.py",
            contract.CROSS_LEDGER_AMENDMENT_CAPABILITY:
                "Tools/apply_amendment.py",
            contract.SAME_SCOPE_QUEUE_REPLAN_CAPABILITY:
                "Tools/compile_queue.py",
        }
        self.assertEqual(set(expected_owners),
                         set(expected_owners).intersection(registered))
        for capability_id, owner in expected_owners.items():
            self.assertEqual("writer", registered[capability_id]["kind"])
            self.assertEqual(owner,
                             registered[capability_id]["implementation_owner"])


class ModelShapeTests(unittest.TestCase):
    def base(self):
        return copy.deepcopy(contract.load_model(REPOSITORY)["document"])

    def test_duplicate_state_fails_closed(self):
        document = self.base()
        document["queue"]["states"].append(
            copy.deepcopy(document["queue"]["states"][0]))
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError, "repeats state"):
            contract.validate_model(document)

    def test_unknown_edge_state_fails_closed(self):
        document = self.base()
        document["queue"]["edge_catalogs"][0]["edges"].append(
            ["queued", "invented"])
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError, "unknown state"):
            contract.validate_model(document)

    def test_duplicate_edge_fails_closed(self):
        document = self.base()
        document["task"]["edge_catalogs"][0]["edges"].append(
            copy.deepcopy(document["task"]["edge_catalogs"][0]["edges"][0]))
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError, "repeats edge"):
            contract.validate_model(document)

    def test_every_state_has_exactly_one_terminal_class(self):
        document = self.base()
        document["task"]["states"][0]["classes"] = ["active"]
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError,
                "exactly one of terminal or nonterminal"):
            contract.validate_model(document)

    def test_unknown_or_unpopulated_state_class_fails_closed(self):
        document = self.base()
        document["queue"]["states"][0]["classes"].append("invented-class")
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError, "unknown state class"):
            contract.validate_model(document)

        document = self.base()
        for state in document["queue"]["states"]:
            if "actionable-target" in state["classes"]:
                state["classes"].remove("actionable-target")
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError,
                "no member for state class"):
            contract.validate_model(document)

    def test_task_edge_may_not_cross_completion_semantics(self):
        document = self.base()
        maintenance = document["task"]["edge_catalogs"][1]
        maintenance["edges"].append(["active", "completion-candidate"])
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError,
                "outside maintenance semantics"):
            contract.validate_model(document)

    def test_unknown_catalog_reference_fails_closed(self):
        document = self.base()
        document["queue"]["current_authorizations"][0][
            "edge_catalog_ids"] = ["missing-catalog"]
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError, "unknown catalog"):
            contract.validate_model(document)

    def test_unknown_current_capability_fails_closed(self):
        document = self.base()
        document["queue"]["current_authorizations"][0][
            "capability_id"] = "invented-writer-v1"
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError,
                "current authorization capabilities"):
            contract.validate_model(document)

    def test_one_current_queue_edge_has_only_one_capability(self):
        document = self.base()
        document["queue"]["current_authorizations"][1][
            "edge_catalog_ids"].append("batch-ordinary-v1")
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError,
                "authorized by both"):
            contract.validate_model(document)

    def test_unknown_amendment_execution_capability_fails_closed(self):
        document = self.base()
        document["progress_controls"]["operational_amendment_operations"][0][
            "execution_capability"] = "invented-amendment-writer-v1"
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError,
                "unknown execution capability"):
            contract.validate_model(document)

    def test_unknown_amendment_operation_class_fails_closed(self):
        document = self.base()
        document["progress_controls"]["operational_amendment_operations"][0][
            "classes"].append("invented-operation-class")
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError,
                "unknown operation class"):
            contract.validate_model(document)

    def test_duplicate_json_keys_fail_before_shape_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root.joinpath(*contract.MODEL_PATH.split("/"))
            path.parent.mkdir(parents=True)
            path.write_text(
                '{"schema_version": 1, "schema_version": 1}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                    contract.RuntimeStateContractError, "repeats JSON key"):
                contract.load_model(root)


class TransitionMatrixTests(unittest.TestCase):
    def test_batch_writer_and_amendment_matrices_are_distinct(self):
        ordinary = {
            "queued": {"open"},
            "open": {"merge-ready"},
            "merge-ready": {"open", "closed"},
            "closed": set(),
            "cancelled": set(),
        }
        amendment = {
            "queued": {"cancelled"},
            "open": {"cancelled"},
            "merge-ready": set(),
            "closed": set(),
            "cancelled": set(),
        }
        observed_ordinary = contract.BATCH_LIFECYCLE_TRANSITIONS
        observed_amendment = {
            state: {
                after for before, after in
                contract.BATCH_TRANSITIONS_BY_CAPABILITY[
                    contract.AMENDMENT_BATCH_CANCELLATION_CAPABILITY]
                if before == state
            }
            for state in contract.QUEUE_STATES
        }
        self.assertEqual(ordinary, {
            state: set(targets)
            for state, targets in observed_ordinary.items()
        })
        self.assertEqual(amendment, observed_amendment)
        self.assertEqual(
            set(contract.BATCH_HISTORICAL_LIFECYCLE_EDGES),
            {(before, after) for before, targets in ordinary.items()
             for after in targets}.union(
                {(before, after) for before, targets in amendment.items()
                 for after in targets}),
        )

    def test_task_build_and_maintenance_edge_matrices(self):
        expected = {
            "build": {
                "planned": {"active", "paused", "blocked",
                            "completion-candidate", "cancelled"},
                "active": {"paused", "blocked", "completion-candidate",
                           "cancelled"},
                "paused": {"active", "blocked", "cancelled"},
                "blocked": {"active", "paused", "cancelled"},
                "completion-candidate": {
                    "active", "paused", "blocked", "complete", "cancelled"},
                "complete": set(),
                "cancelled": set(),
            },
            "maintenance": {
                "planned": {"active", "paused", "blocked", "complete",
                            "cancelled"},
                "active": {"paused", "blocked", "complete", "cancelled"},
                "paused": {"active", "blocked", "cancelled"},
                "blocked": {"active", "paused", "cancelled"},
                "completion-candidate": set(),
                "complete": set(),
                "cancelled": set(),
            },
        }
        for semantic, matrix in expected.items():
            edges = contract.TASK_TRANSITIONS_BY_SEMANTICS[semantic]
            observed = {
                state: {after for before, after in edges if before == state}
                for state in contract.TASK_STATES
            }
            self.assertEqual(matrix, observed)
            for before in contract.TASK_STATES:
                for after in contract.TASK_STATES:
                    self.assertEqual(
                        after in matrix[before],
                        contract.task_transition_is_authorized(
                            semantic, before, after),
                    )

    def test_historical_task_catalog_is_explicit_and_semantics_bound(self):
        for semantic in contract.COMPLETION_SEMANTICS:
            self.assertEqual(
                contract.TASK_TRANSITIONS_BY_SEMANTICS[semantic],
                contract.TASK_HISTORICAL_TRANSITIONS_BY_SEMANTICS[semantic],
            )
        self.assertFalse(contract.task_transition_is_authorized(
            "maintenance", "active", "completion-candidate",
            historical=True))

    def test_a_new_current_catalog_does_not_rewrite_historical_replay(self):
        document = copy.deepcopy(
            contract.load_model(REPOSITORY)["document"])
        replacement = copy.deepcopy(document["queue"]["edge_catalogs"][0])
        replacement["catalog_id"] = "batch-ordinary-v2"
        replacement["edges"].remove(["merge-ready", "open"])
        document["queue"]["edge_catalogs"].append(replacement)
        document["queue"]["current_authorizations"][0][
            "edge_catalog_ids"] = ["batch-ordinary-v2"]

        parsed = contract.validate_model(document)
        current = parsed["queue_current"][
            contract.ORDINARY_QUEUE_TRANSITION_CAPABILITY]["edges"]
        historical = parsed["queue_history"][
            contract.QUEUE_TRANSITION_REPLAY_PROTOCOL]["edges"]
        self.assertNotIn(("merge-ready", "open"), current)
        self.assertIn(("merge-ready", "open"), historical)


class ControlFinalityTests(unittest.TestCase):
    def test_guidance_and_amendment_finality_are_not_conflated(self):
        self.assertEqual({
            "verified", "deferred", "superseded", "not-applicable",
        }, set(contract.FINAL_GUIDANCE_STATUSES))
        self.assertEqual(
            set(contract.FINAL_GUIDANCE_STATUSES).union({"withdrawn"}),
            set(contract.AMENDMENT_FINALITY_REQUIREMENTS),
        )
        self.assertNotIn("approved", contract.AMENDMENT_FINALITY_REQUIREMENTS)
        self.assertNotIn("clarification-required",
                         contract.FINAL_GUIDANCE_STATUSES)
        self.assertTrue(contract.amendment_is_final("verified", True))
        self.assertFalse(contract.amendment_is_final("verified", False))
        self.assertTrue(contract.amendment_is_final("withdrawn", False))
        self.assertFalse(contract.amendment_is_final("withdrawn", True))
        self.assertTrue(contract.amendment_is_final("deferred", False))
        self.assertTrue(contract.amendment_is_final("deferred", True))

    def test_amendment_finality_rejects_unknown_and_duplicate_statuses(self):
        document = copy.deepcopy(
            contract.load_model(REPOSITORY)["document"])
        document["progress_controls"]["amendment_finality"].append({
            "status_id": "invented",
            "required_writeback_done": None,
        })
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError,
                "not an Amendment status"):
            contract.validate_model(document)

        document = copy.deepcopy(
            contract.load_model(REPOSITORY)["document"])
        document["progress_controls"]["amendment_finality"].append(
            copy.deepcopy(
                document["progress_controls"]["amendment_finality"][0]))
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError, "repeats status"):
            contract.validate_model(document)

    def test_operational_amendment_execution_classes(self):
        self.assertEqual({
            "scope-replan", "cancel-batch", "queue-replan",
            "gap-routing-reconciliation", "property-state-migration",
        }, set(contract.OPERATIONAL_AMENDMENT_OPERATIONS))
        self.assertEqual({
            "scope-replan", "cancel-batch", "gap-routing-reconciliation",
            "property-state-migration",
        }, set(contract.AMENDMENT_OPERATIONS_BY_EXECUTION_CAPABILITY[
            contract.CROSS_LEDGER_AMENDMENT_CAPABILITY]))


class NoDuplicateProductionConstantsTests(unittest.TestCase):
    MACHINE_VALUES = set().union(
        contract.QUEUE_STATES,
        contract.QUEUE_HOLD_STATES,
        contract.EXECUTION_MODES,
        contract.TASK_STATES,
        contract.COMPLETION_SEMANTICS,
        contract.GUIDANCE_DISPOSITIONS,
        contract.GUIDANCE_STATUSES,
        contract.AMENDMENT_STATUSES,
        contract.TERMINAL_AUDIT_STATES,
        contract.MAINTENANCE_COMPLETION_STATES,
        contract.OPERATIONAL_AMENDMENT_OPERATIONS,
    )
    MACHINE_CLOSED_SETS = {
        frozenset(values)
        for values in (
            contract.QUEUE_STATES,
            contract.QUEUE_ACTIVE_STATES,
            contract.QUEUE_TERMINAL_STATES,
            contract.QUEUE_NONTERMINAL_STATES,
            contract.TASK_STATES,
            contract.TASK_TERMINAL_STATES,
            contract.TASK_NONTERMINAL_STATES,
        )
        if len(values) >= 2
    }

    @staticmethod
    def _literal_string_container(value):
        if isinstance(value, (ast.List, ast.Set, ast.Tuple)):
            elements = value.elts
        elif (isinstance(value, ast.Call) and
              isinstance(value.func, ast.Name) and
              value.func.id in {"frozenset", "set", "tuple", "list"} and
              len(value.args) == 1 and
              isinstance(value.args[0], (ast.List, ast.Set, ast.Tuple))):
            elements = value.args[0].elts
        else:
            return None
        result = []
        for element in elements:
            if (not isinstance(element, ast.Constant) or
                    not isinstance(element.value, str)):
                return None
            result.append(element.value)
        return result

    def test_production_modules_do_not_redeclare_machine_closed_sets(self):
        findings = []
        for path in sorted(TOOLS.rglob("*.py")):
            if "tests" in path.parts or path.name == contract.__file__.split("/")[-1]:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                values = self._literal_string_container(node.value)
                if (values is not None and len(values) >= 2 and
                        set(values).issubset(self.MACHINE_VALUES)):
                    findings.append("%s:%d" %
                                    (path.relative_to(REPOSITORY), node.lineno))
        self.assertEqual([], findings)

    def test_production_membership_and_iteration_use_registry_projections(self):
        findings = []
        membership_ops = (ast.In, ast.NotIn)
        for path in sorted(TOOLS.rglob("*.py")):
            if ("tests" in path.parts or
                    path.name == contract.__file__.split("/")[-1]):
                continue
            tree = ast.parse(
                path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                candidates = []
                if isinstance(node, ast.For):
                    candidates.append(node.iter)
                elif isinstance(node, ast.Compare):
                    candidates.extend(
                        comparator
                        for operator, comparator in
                        zip(node.ops, node.comparators)
                        if isinstance(operator, membership_ops)
                    )
                for candidate in candidates:
                    values = self._literal_string_container(candidate)
                    if (values is not None and
                            len(values) == len(set(values)) and
                            frozenset(values) in self.MACHINE_CLOSED_SETS):
                        findings.append(
                            "%s:%d" %
                            (path.relative_to(REPOSITORY), node.lineno))
        self.assertEqual([], findings)


if __name__ == "__main__":
    unittest.main()
