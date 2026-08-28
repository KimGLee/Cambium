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

import corpus_planning_contract as contract  # noqa: E402
import kblib  # noqa: E402
import test_profile_onboarding_status as profile_fixture  # noqa: E402


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
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.template_profile = profile_fixture.fill_candidate(
            Path(self.temporary.name), "planning-template")

    def load(self, relative):
        return kblib.parse_yaml_subset(
            (REPOSITORY / relative).read_text(encoding="utf-8"))

    def load_template(self):
        return kblib.parse_yaml_subset(
            (self.template_profile / "corpus-planning.yaml").read_text(
                encoding="utf-8"))

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

    def test_inactive_payload_and_configured_scale_use_one_branch_algorithm(self):
        inactive = self.load_template()
        inactive["artifact_bindings"]["global_map"] = "planning/map.yaml"
        _, inactive_issues = \
            contract.validate_corpus_planning_envelope(inactive)
        configured = self.load(
            "profiles/examples/worked-planning/corpus-planning.yaml")
        configured["capability_scale"] = []
        _, configured_issues = \
            contract.validate_corpus_planning_envelope(configured)

        self.assertIn("inactive_artifacts",
                      {issue["code"] for issue in inactive_issues})
        self.assertIn("configured_scale_empty",
                      {issue["code"] for issue in configured_issues})


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

    def test_route_and_manifest_triggers_share_one_closed_projection(self):
        required, triggers = contract.derive_close_requirement(
            [contract.CLOSE_ROUTE_TRIGGER], ["Topics/A.md"],
            ["Topics/A.md"])

        self.assertTrue(required)
        self.assertEqual(sorted(contract.CLOSE_TRIGGERS), triggers)
        self.assertEqual((), contract.close_trigger_issues(required, triggers))
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
        }
        for relative in (
                "Tools/check_profile.py", "Tools/check_corpus_plan.py",
                "Tools/queue_runtime/close_gate.py"):
            with self.subTest(relative=relative):
                self.assertEqual(
                    set(), forbidden.intersection(self.assignments(relative)))

    def test_each_producer_and_consumer_calls_the_shared_contract(self):
        required_symbols = {
            "Tools/check_profile.py": (
                "validate_corpus_planning_envelope",),
            "Tools/check_corpus_plan.py": (
                "validate_corpus_planning_envelope",
                "receipt_binding_shape_issues",
                "receipt_binding_differences", "derive_close_requirement"),
            "Tools/queue_runtime/close_gate.py": (
                "close_trigger_issues", "receipt_binding_differences",
                "receipt_path_currentness_issues"),
            "Tools/check_batch_close.py": ("PASS_RECEIPT_BINDING_FIELDS",),
            "Tools/check_proof.py": ("PASS_RECEIPT_BINDING_FIELDS",),
        }
        for relative, symbols in required_symbols.items():
            source = (REPOSITORY / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertIn("import corpus_planning_contract", source)
                for symbol in symbols:
                    self.assertIn(symbol, source)


if __name__ == "__main__":
    unittest.main()
