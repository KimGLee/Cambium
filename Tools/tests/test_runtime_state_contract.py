"""Owned tests for the current Kernel runtime-state machine contract.

The JSON registry is the semantic machine owner and ``runtime_state_contract``
is its sole parser/projection. Writer execution and CLI lifecycle scenarios
belong to their respective consumers and E2E suites.
"""

import copy
import json
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import Tools.execution.task_runtime.runtime_state_contract as contract


MODEL_FILE = REPOSITORY.joinpath(*contract.MODEL_PATH.split("/"))
MODEL = json.loads(MODEL_FILE.read_text(encoding="utf-8"))


def _states(section):
    return tuple(row["state_id"] for row in MODEL[section]["states"])


def _class_members(section, class_id):
    return frozenset(
        row["state_id"] for row in MODEL[section]["states"]
        if class_id in row["classes"])


def _catalogs(section):
    return {
        row["catalog_id"]: frozenset(map(tuple, row["edges"]))
        for row in MODEL[section]["edge_catalogs"]
    }


def _queue_authorizations():
    catalogs = _catalogs("queue")
    return {
        row["capability_id"]: frozenset().union(*(
            catalogs[catalog_id] for catalog_id in row["edge_catalog_ids"]
        ))
        for row in MODEL["queue"]["current_authorizations"]
    }


def _task_authorizations():
    catalogs = _catalogs("task")
    return {
        row["completion_semantics"]: frozenset().union(*(
            catalogs[catalog_id] for catalog_id in row["edge_catalog_ids"]
        ))
        for row in MODEL["task"]["current_authorizations"]
    }


class RuntimeStateModelIntegrationTests(unittest.TestCase):
    """One read-only loading seam for the shipped machine contract."""

    def test_shipped_model_loads_exact_current_registry(self):
        loaded = contract.load_model(REPOSITORY)

        self.assertEqual(MODEL, loaded["document"])
        self.assertEqual(contract.MODEL_ID, MODEL["model_id"])

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
            value.startswith("Tools/") for value in strings(MODEL)))


class RuntimeStateProjectionContractTests(unittest.TestCase):
    """Table-driven projections and predicates from the current registry."""

    def test_states_classes_and_ledgers_project_from_registry(self):
        self.assertEqual(_states("queue"), contract.QUEUE_STATE_ORDER)
        self.assertEqual(frozenset(_states("queue")), contract.QUEUE_STATES)
        self.assertEqual(
            frozenset(MODEL["queue"]["hold_states"]),
            contract.QUEUE_HOLD_STATES)
        self.assertEqual(
            frozenset(MODEL["queue"]["execution_modes"]),
            contract.EXECUTION_MODES)
        self.assertEqual(_states("task"), contract.TASK_STATE_ORDER)
        self.assertEqual(frozenset(_states("task")), contract.TASK_STATES)
        self.assertEqual(
            frozenset(MODEL["task"]["completion_semantics"]),
            contract.COMPLETION_SEMANTICS)

        queue_classes = {
            "active": contract.QUEUE_ACTIVE_STATES,
            "terminal": contract.QUEUE_TERMINAL_STATES,
            "nonterminal": contract.QUEUE_NONTERMINAL_STATES,
            "actionable-target": contract.QUEUE_ACTIONABLE_TARGET_STATES,
            "delta-bound": contract.QUEUE_DELTA_BOUND_STATES,
        }
        task_classes = {
            "active": contract.TASK_ACTIVE_STATES,
            "terminal": contract.TASK_TERMINAL_STATES,
            "nonterminal": contract.TASK_NONTERMINAL_STATES,
            "batch-activation-current":
                contract.BATCH_ACTIVATION_TASK_STATES,
            "build-proof-readable": contract.BUILD_PROOF_TASK_STATES,
            "standards-adoption-current":
                contract.STANDARDS_ADOPTION_TASK_STATES,
            "maintenance-completion-current":
                contract.MAINTENANCE_COMPLETION_TASK_STATES,
        }
        for class_id, observed in queue_classes.items():
            with self.subTest(section="queue", class_id=class_id):
                self.assertEqual(
                    _class_members("queue", class_id), observed)
        for class_id, observed in task_classes.items():
            with self.subTest(section="task", class_id=class_id):
                self.assertEqual(_class_members("task", class_id), observed)

        expected_ledgers = {
            row["ledger_id"]: row["fingerprint_field"]
            for row in MODEL["runtime_ledgers"]
        }
        self.assertEqual(
            tuple(expected_ledgers), contract.RUNTIME_LEDGER_IDS)
        self.assertEqual(
            expected_ledgers, dict(contract.RUNTIME_LEDGER_FINGERPRINT_BY_ID))

    def test_current_queue_authorization_and_classifier_matrix(self):
        expected = _queue_authorizations()
        observed = {
            owner: frozenset(edges)
            for owner, edges in contract.BATCH_TRANSITIONS_BY_CAPABILITY.items()
        }
        self.assertEqual(expected, observed)

        states = frozenset(_states("queue"))
        for owner, edges in expected.items():
            for before in states:
                for after in states:
                    expected_kind = (
                        contract.QUEUE_LIFECYCLE_TRANSITION
                        if (before, after) in edges else None)
                    with self.subTest(
                            owner=owner, before=before, after=after):
                        self.assertEqual(
                            expected_kind,
                            contract.classify_queue_transition(
                                owner, before, after, "none", "none"))

        ordinary = contract.ORDINARY_QUEUE_TRANSITION_CAPABILITY
        for state in contract.QUEUE_NONTERMINAL_STATES:
            for before_hold in contract.QUEUE_HOLD_STATES:
                for after_hold in contract.QUEUE_HOLD_STATES - {before_hold}:
                    self.assertEqual(
                        contract.QUEUE_HOLD_TRANSITION,
                        contract.classify_queue_transition(
                            ordinary, state, state,
                            before_hold, after_hold))
        for state in contract.QUEUE_TERMINAL_STATES:
            self.assertIsNone(contract.classify_queue_transition(
                ordinary, state, state, "none", "paused"))
        self.assertIsNone(contract.classify_queue_transition(
            ordinary, "invented", "open", "none", "none"))

    def test_current_task_authorization_matrix(self):
        expected = _task_authorizations()
        observed = {
            semantics: frozenset(edges)
            for semantics, edges in
            contract.TASK_TRANSITIONS_BY_SEMANTICS.items()
        }
        self.assertEqual(expected, observed)

        states = frozenset(_states("task"))
        for semantics, edges in expected.items():
            for before in states:
                for after in states:
                    with self.subTest(
                            semantics=semantics,
                            before=before, after=after):
                        self.assertEqual(
                            (before, after) in edges,
                            contract.task_transition_is_authorized(
                                semantics, before, after))
        self.assertFalse(contract.task_transition_is_authorized(
            "invented", "planned", "active"))

    def test_current_queue_reachability_is_derived_from_ordinary_edges(self):
        edges = _queue_authorizations()[
            contract.ORDINARY_QUEUE_TRANSITION_CAPABILITY]
        adjacency = {state: set() for state in _states("queue")}
        for before, after in edges:
            adjacency[before].add(after)

        for source in adjacency:
            expected = set()
            pending = list(adjacency[source])
            while pending:
                state = pending.pop()
                if state in expected:
                    continue
                expected.add(state)
                pending.extend(adjacency[state])
            with self.subTest(source=source):
                self.assertEqual(
                    frozenset(expected),
                    contract.reachable_batch_states(source))
        self.assertEqual(
            frozenset(), contract.reachable_batch_states("invented"))

    def test_current_control_finality_and_amendment_operations_project(self):
        finality = {
            row["status_id"]: row["required_writeback_done"]
            for row in MODEL["progress_controls"]["amendment_finality"]
        }
        self.assertEqual(
            finality, dict(contract.AMENDMENT_FINALITY_REQUIREMENTS))
        for status in MODEL["progress_controls"]["amendment_statuses"]:
            requirement = finality.get(status, "not-final")
            for writeback_done in (False, True):
                expected = (
                    requirement is None or
                    requirement is writeback_done
                ) if requirement != "not-final" else False
                with self.subTest(
                        status=status, writeback_done=writeback_done):
                    self.assertEqual(
                        expected,
                        contract.amendment_is_final(
                            status, writeback_done))

        operations = MODEL["progress_controls"][
            "operational_amendment_operations"]
        self.assertEqual(
            {row["operation_id"] for row in operations},
            set(contract.OPERATIONAL_AMENDMENT_OPERATIONS))
        for row in operations:
            self.assertIn(
                row["operation_id"],
                contract.AMENDMENT_OPERATIONS_BY_EXECUTION_CAPABILITY[
                    row["execution_capability"]])
            for class_id in row["classes"]:
                self.assertIn(
                    row["operation_id"],
                    contract.AMENDMENT_OPERATIONS_BY_CLASS[class_id])


class RuntimeStateValidationContractTests(unittest.TestCase):
    """Closed-shape failures use in-memory model variants only."""

    def test_invalid_current_model_variants_fail_closed(self):
        def duplicate_queue_state(document):
            document["queue"]["states"].append(
                copy.deepcopy(document["queue"]["states"][0]))

        def unknown_queue_edge_state(document):
            document["queue"]["edge_catalogs"][0]["edges"].append(
                ["queued", "invented"])

        def duplicate_task_edge(document):
            edges = document["task"]["edge_catalogs"][0]["edges"]
            edges.append(copy.deepcopy(edges[0]))

        def invalid_terminal_class(document):
            document["task"]["states"][0]["classes"] = ["active"]

        def unknown_queue_capability(document):
            document["queue"]["current_authorizations"][0][
                "capability_id"] = "invented-writer-v1"

        def overlapping_queue_owner(document):
            document["queue"]["current_authorizations"][1][
                "edge_catalog_ids"].append("batch-ordinary-v1")

        def cross_semantics_task_edge(document):
            document["task"]["edge_catalogs"][1]["edges"].append(
                ["active", "completion-candidate"])

        def unknown_amendment_capability(document):
            document["progress_controls"][
                "operational_amendment_operations"][0][
                    "execution_capability"] = "invented-writer-v1"

        def duplicate_finality(document):
            rows = document["progress_controls"]["amendment_finality"]
            rows.append(copy.deepcopy(rows[0]))

        def extra_top_level_key(document):
            document["unexpected_field"] = "invalid"

        cases = (
            duplicate_queue_state,
            unknown_queue_edge_state,
            duplicate_task_edge,
            invalid_terminal_class,
            unknown_queue_capability,
            overlapping_queue_owner,
            cross_semantics_task_edge,
            unknown_amendment_capability,
            duplicate_finality,
            extra_top_level_key,
        )
        for mutate in cases:
            with self.subTest(case=mutate.__name__):
                document = copy.deepcopy(MODEL)
                mutate(document)
                with self.assertRaises(contract.RuntimeStateContractError):
                    contract.validate_model(document)

    def test_duplicate_json_keys_fail_before_shape_validation(self):
        with self.assertRaisesRegex(
                contract.RuntimeStateContractError, "repeats JSON key"):
            contract._object_without_duplicate_keys((
                ("schema_version", 1),
                ("schema_version", 1),
            ))


if __name__ == "__main__":
    unittest.main()
