"""Pin the single K02 machine contract shared by Corpus Planning consumers."""

import ast
import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "tests"))

import Tools.execution.planning.corpus_planning_contract as contract  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402


class CorpusPlanningRegistryTests(unittest.TestCase):
    def setUp(self):
        self.document = contract.load_corpus_planning_contract()

    def test_shipped_registry_projects_the_existing_contract(self):
        values = contract.validate_corpus_planning_contract(self.document)

        self.assertEqual("Corpus Planning", values["slot_name"])
        self.assertEqual(
            ("Global Map", "Capability Matrix", "Gap Register"),
            contract.ARTIFACT_ROLES)
        self.assertEqual(
            {"configured", "not-applicable"},
            set(contract.APPLICABILITY_STATES))
        self.assertEqual(
            {"R13", "manifest"}, set(contract.CLOSE_TRIGGERS))
        self.assertEqual(23, len(contract.PASS_RECEIPT_BINDING_FIELDS))
        self.assertEqual(
            {"schema_version", "entries", "typed_dependencies"},
            set(contract.artifact_contract(
                "global_map")["document_fields"]))
        self.assertEqual(
            {"candidate", "confirmed", "promoted", "resolved",
             "deferred", "rejected"},
            set(contract.artifact_contract("gap_register")["statuses"]))

    def test_registry_envelopes_and_path_sha_rows_are_closed(self):
        cases = []
        extra_document = copy.deepcopy(self.document)
        extra_document["second_owner"] = True
        cases.append(extra_document)
        extra_slot = copy.deepcopy(self.document)
        extra_slot["slot_envelope"]["second_owner"] = True
        cases.append(extra_slot)
        unknown_requirement = copy.deepcopy(self.document)
        unknown_requirement["receipt_binding"]["path_sha_bindings"][0][
            "requirement"] = "sometimes"
        cases.append(unknown_requirement)
        duplicate_artifact_owner = copy.deepcopy(self.document)
        duplicate_artifact_owner["artifact_contracts"]["global_map"][
            "semantic_owner"] = "K02/06"
        cases.append(duplicate_artifact_owner)
        unknown_relation = copy.deepcopy(self.document)
        unknown_relation["artifact_contracts"]["global_map"][
            "relation_types"].append(
                unknown_relation["artifact_contracts"]["global_map"][
                    "relation_types"][0])
        cases.append(unknown_relation)

        for document in cases:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    contract.validate_corpus_planning_contract(document)

    def test_adopting_registry_cannot_drift_from_the_deployed_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / contract.CORPUS_PLANNING_CONTRACT_PATH
            target.parent.mkdir(parents=True)
            shutil.copy2(
                REPOSITORY / contract.CORPUS_PLANNING_CONTRACT_PATH, target)
            document = kblib.parse_yaml_subset(target.read_text(encoding="utf-8"))
            document["close_triggers"]["selected_route"] = "R99"
            target.write_text(kblib.canonical_yaml(document), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "differs from"):
                contract.current_corpus_planning_contract_values(root)


class CorpusPlanningEnvelopeTests(unittest.TestCase):
    def load(self, relative):
        return kblib.parse_yaml_subset(
            (REPOSITORY / relative).read_text(encoding="utf-8"))

    def load_template(self):
        return self.load("profiles/_template/corpus-planning.yaml")

    def test_both_existing_applicability_branches_validate(self):
        configured, configured_issues = \
            contract.validate_corpus_planning_envelope(self.load(
                "profiles/examples/worked-planning/corpus-planning.yaml"))
        inactive, inactive_issues = \
            contract.validate_corpus_planning_envelope(self.load_template())

        self.assertEqual((), configured_issues)
        self.assertEqual(contract.CONFIGURED_STATE, configured["mode"])
        self.assertEqual(4, len(configured["scale"]))
        self.assertEqual((), inactive_issues)
        self.assertEqual(contract.INACTIVE_STATE, inactive["mode"])
        self.assertEqual({}, inactive["artifact_bindings"])

    def test_envelope_shape_and_branch_rules_have_one_table_owner(self):
        configured = self.load(
            "profiles/examples/worked-planning/corpus-planning.yaml")
        inactive = self.load_template()

        cases = []

        value = copy.deepcopy(inactive)
        value["artifact_bindings"]["global_map"] = "planning/map.yaml"
        cases.append(("inactive-artifact", value, "inactive_artifacts"))

        value = copy.deepcopy(configured)
        value["schema_version"] = 2
        cases.append(("schema-version", value, "schema_version"))

        value = copy.deepcopy(configured)
        value["applicability"]["registration"] = "configured"
        cases.append(("nested-extra", value, "unsupported_fields"))

        value = copy.deepcopy(configured)
        value["applicability"]["state"] = None
        cases.append(("state", value, "applicability_state"))

        value = copy.deepcopy(configured)
        value["applicability"]["reason"] = "unexpected"
        cases.append(("configured-reason", value, "configured_reason"))

        value = copy.deepcopy(configured)
        value["artifact_bindings"]["global_map"] = "planning/map.md"
        cases.append(("artifact-suffix", value,
                      "configured_artifact_path"))

        value = copy.deepcopy(configured)
        value["artifact_bindings"]["global_map"] = \
            value["artifact_bindings"]["capability_matrix"]
        cases.append(("artifact-identity", value,
                      "artifact_bindings_distinct"))

        value = copy.deepcopy(configured)
        value["capability_scale"] = []
        cases.append(("scale-empty", value, "configured_scale_empty"))

        value = copy.deepcopy(configured)
        value["capability_scale"][1]["rank"] = 7
        cases.append(("scale-rank", value, "scale_rank_position"))

        value = copy.deepcopy(configured)
        for row in value["capability_scale"]:
            row["target_eligible"] = False
        cases.append(("target-eligible", value,
                      "configured_target_eligible"))

        value = copy.deepcopy(configured)
        value["pass_authority"]["decision_scope_id"] = "all-decisions"
        cases.append(("authority-scope", value,
                      "authority_decision_scope"))

        value = copy.deepcopy(configured)
        value.pop("pass_authority")
        cases.append(("required-fields", value, "missing_fields"))

        for label, document, expected_code in cases:
            with self.subTest(label=label):
                _normalized, issues = \
                    contract.validate_corpus_planning_envelope(document)
                self.assertIn(expected_code,
                              {issue["code"] for issue in issues}, issues)


class CorpusPlanningReceiptContractTests(unittest.TestCase):
    def binding(self, applicability):
        binding = {
            field: None for field in contract.PASS_RECEIPT_BINDING_FIELDS
        }
        binding["corpus_plan_applicability"] = applicability
        for path_field, sha_field, requirement in \
                contract.PASS_RECEIPT_PATH_SHA_BINDINGS:
            if requirement == "always" or \
                    applicability == contract.CONFIGURED_STATE:
                binding[path_field] = "path/%s" % path_field
                binding[sha_field] = "sha256:" + "a" * 64
        return binding

    def test_producer_shape_and_consumer_path_currentness_are_identical(self):
        for applicability in contract.APPLICABILITY_STATES:
            with self.subTest(applicability=applicability):
                binding = self.binding(applicability)
                self.assertEqual(
                    (), contract.receipt_binding_shape_issues(binding))
                self.assertEqual(
                    (), contract.receipt_path_currentness_issues(
                        binding, applicability))

    def test_one_binding_difference_is_reported_once_by_field(self):
        expected = self.binding(contract.CONFIGURED_STATE)
        receipt = dict(expected)
        receipt["global_map_sha256"] = "sha256:" + "b" * 64

        self.assertEqual(("global_map_sha256",), tuple(
            row["field"] for row in contract.receipt_binding_differences(
                receipt, expected)))

    def test_route_and_manifest_triggers_are_one_exact_closed_projection(self):
        cases = (
            ("unrelated", [], ["Topics/B.md"], ["Topics/A.md"],
             False, []),
            ("other-routes", ["R07", "R02"], ["Topics/B.md"],
             ["Topics/A.md"], False, []),
            ("route", [contract.CLOSE_ROUTE_TRIGGER], ["Topics/B.md"],
             ["Topics/A.md"], True, [contract.CLOSE_ROUTE_TRIGGER]),
            ("manifest", [], ["Topics/A.md"], ["Topics/A.md"],
             True, [contract.CLOSE_MANIFEST_TRIGGER]),
            ("both", [contract.CLOSE_ROUTE_TRIGGER], ["Topics/A.md"],
             ["Topics/A.md"], True, sorted(contract.CLOSE_TRIGGERS)),
        )
        for name, routes, manifest, affected, expected, expected_triggers \
                in cases:
            with self.subTest(name=name):
                required, triggers = contract.derive_close_requirement(
                    routes, manifest, affected)
                self.assertEqual(expected, required)
                self.assertEqual(expected_triggers, triggers)
                self.assertEqual(
                    (), contract.close_trigger_issues(required, triggers))

        issues = contract.close_trigger_issues(True, ["unknown"])
        self.assertIn("trigger_unsupported",
                      {issue["code"] for issue in issues})


class CorpusPlanningSingleOwnerTests(unittest.TestCase):
    def assignments(self, relative):
        tree = ast.parse((REPOSITORY / relative).read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
        return names

    def test_consumers_do_not_redeclare_contract_closed_sets(self):
        forbidden = {
            "CORPUS_PLANNING_FIELDS", "CORPUS_APPLICABILITY_FIELDS",
            "CORPUS_ARTIFACT_FIELDS", "CORPUS_SCALE_FIELDS",
            "CORPUS_AUTHORITY_FIELDS", "SLOT_FIELDS",
            "APPLICABILITY_FIELDS", "ARTIFACT_BINDING_FIELDS",
            "SCALE_ROW_FIELDS", "PASS_AUTHORITY_FIELDS", "PATH_SHA_FIELDS",
            "PASS_RECEIPT_BINDING_FIELDS", "CORPUS_PLAN_TRIGGERS",
            "CORPUS_PLAN_PATH_SHA_FIELDS",
            "GLOBAL_MAP_FIELDS", "GLOBAL_MAP_ENTRY_FIELDS",
            "GLOBAL_MAP_EDGE_FIELDS", "MATRIX_FIELDS",
            "CAPABILITY_FIELDS", "GAP_REGISTER_FIELDS", "GAP_FIELDS",
            "GAP_STATUSES", "RELATION_TYPES",
        }
        for relative in (
                "Tools/governance/profile/check_profile.py",
                "Tools/execution/planning/check_corpus_plan.py",
                "Tools/execution/task_runtime/queue_runtime/close_gate.py"):
            with self.subTest(relative=relative):
                self.assertEqual(
                    set(), forbidden.intersection(self.assignments(relative)))

    def test_each_producer_and_consumer_calls_the_shared_contract(self):
        required_symbols = {
            "Tools/governance/profile/check_profile.py": (
                "validate_corpus_planning_envelope",),
            "Tools/execution/planning/check_corpus_plan.py": (
                "artifact_contract",
                "validate_corpus_planning_envelope",
                "receipt_binding_shape_issues",
                "receipt_binding_differences", "derive_close_requirement"),
            "Tools/execution/task_runtime/queue_runtime/close_gate.py": (
                "close_trigger_issues", "receipt_binding_differences",
                "receipt_path_currentness_issues"),
            "Tools/execution/audit/check_batch_close.py": (
                "PASS_RECEIPT_BINDING_FIELDS",),
            "Tools/execution/audit/check_proof.py": (
                "PASS_RECEIPT_BINDING_FIELDS",),
        }
        for relative, symbols in required_symbols.items():
            source = (REPOSITORY / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertIn(
                    "import Tools.execution.planning.corpus_planning_contract "
                    "as corpus_planning_contract", source)
                for symbol in symbols:
                    self.assertIn(symbol, source)


if __name__ == "__main__":
    unittest.main()
