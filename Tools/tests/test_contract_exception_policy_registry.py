"""The Kernel registry, not Python prose, owns exception-policy semantics."""

import copy
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock


TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import contract_exception_policy as policy  # noqa: E402
from queue_runtime import policy_exceptions  # noqa: E402


NONE_RUBRIC = "## Priority Quota\n\n- Registration: None\n"


class RegistryShapeTests(unittest.TestCase):

    def document(self):
        return copy.deepcopy(policy.load_policy_registry())

    def test_shipped_registry_loads_and_projects_the_existing_api(self):
        document = policy.load_policy_registry()
        records = policy.policy_registry_records(document)
        self.assertEqual(
            {"priority_quota.P0", "priority_quota.P1",
             "coverage.reviewed_era"},
            set(records))
        self.assertEqual(records, policy.POLICY_REGISTRY)
        self.assertEqual(
            tuple(row["kernel_default"]
                  for row in document["families"][0]["policies"]),
            policy.PRIORITY_QUOTA_KERNEL_DEFAULTS)

    def test_missing_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(OSError):
                policy.load_policy_registry(root)

    def test_duplicate_policy_id_is_rejected(self):
        document = self.document()
        duplicate = copy.deepcopy(document["families"][0]["policies"][0])
        document["families"][0]["policies"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate policy_id"):
            policy.policy_registry_records(document)

    def test_illegal_protocol_and_default_are_rejected(self):
        protocol = self.document()
        protocol["families"][0]["fingerprint_payload"][
            "protocol_version"] = 0
        with self.assertRaisesRegex(ValueError, "positive integer"):
            policy.policy_registry_records(protocol)

        default = self.document()
        default["families"][0]["policies"][0]["kernel_default"] = 1000
        with self.assertRaisesRegex(ValueError, "outside its limit domain"):
            policy.policy_registry_records(default)

    def test_owner_path_must_be_safe_and_resolve_inside_kernel(self):
        escaping = self.document()
        escaping["families"][0]["policies"][0]["owner"] = \
            "kernel/../Tools/contract_exception_policy.py"
        with self.assertRaisesRegex(ValueError, "safe repository-relative"):
            policy.policy_registry_records(escaping)

        absent = self.document()
        absent["families"][0]["policies"][0]["owner"] = \
            "kernel/K00 Standards Control/does-not-exist.md"
        with self.assertRaisesRegex(ValueError, "does not resolve"):
            policy.policy_registry_records(absent)


class FingerprintCompatibilityAndCurrentnessTests(unittest.TestCase):

    def document(self):
        return copy.deepcopy(policy.load_policy_registry())

    def test_existing_effective_policy_fingerprints_are_byte_compatible(self):
        _quota, quota_fingerprint, quota_errors = \
            policy.effective_priority_policy(NONE_RUBRIC)
        _coverage, coverage_fingerprint, coverage_errors = \
            policy.effective_coverage_policy()
        self.assertEqual([], quota_errors)
        self.assertEqual([], coverage_errors)
        self.assertEqual(
            "sha256:0df9b16a8cbb04c17450a92b64d31b644f5c9ba8c5efd1308bcb006ce563f0c5",
            quota_fingerprint)
        self.assertEqual(
            "sha256:ac1fcfb8fae22e2f4308262e95ed671f6ead9fd664a52a4790084bc08be23c31",
            coverage_fingerprint)

    def test_registry_policy_revision_moves_the_effective_fingerprint(self):
        document = self.document()
        _old_policy, old_fingerprint, _errors = \
            policy.effective_priority_policy(NONE_RUBRIC)
        document["families"][0]["fingerprint_payload"][
            "protocol_version"] += 1
        policy.policy_registry_records(document)
        _new_policy, new_fingerprint, errors = \
            policy.effective_priority_policy(NONE_RUBRIC, registry=document)
        self.assertEqual([], errors)
        self.assertNotEqual(old_fingerprint, new_fingerprint)

        coverage = self.document()
        _old, old_coverage, _errors = policy.effective_coverage_policy()
        coverage["families"][1]["fingerprint_payload"]["rule"] += \
            " under the current Standards identity"
        policy.policy_registry_records(coverage)
        _new, new_coverage, errors = \
            policy.effective_coverage_policy(registry=coverage)
        self.assertEqual([], errors)
        self.assertNotEqual(old_coverage, new_coverage)

    def test_kernel_defaults_resolve_from_the_registry_values(self):
        document = self.document()
        rows = document["families"][0]["policies"]
        rows[0]["kernel_default"] = 20.0
        rows[1]["kernel_default"] = 30.0
        policy.policy_registry_records(document)
        effective, _fingerprint, errors = policy.effective_priority_policy(
            NONE_RUBRIC, registry=document)
        self.assertEqual([], errors)
        self.assertEqual(
            {"priority_quota.P0": 20.0, "priority_quota.P1": 30.0},
            effective["kernel_defaults"])
        self.assertEqual(effective["kernel_defaults"], effective["resolved"])


class SingleNumericAuthorityTests(unittest.TestCase):

    def test_production_consumers_do_not_redeclare_the_default_numbers(self):
        check_vocab = (TOOLS / "check_vocab.py").read_text(encoding="utf-8")
        self.assertNotRegex(check_vocab, r"default\s*=\s*(?:15|35)(?:\.0)?")
        self.assertIn(
            "contract_exception_policy.PRIORITY_QUOTA_KERNEL_DEFAULTS",
            check_vocab)

        owner = (REPO / "kernel/K00 Standards Control/"
                 "07 Effort Tiering and Priority Quota.md").read_text(
                     encoding="utf-8")
        self.assertIsNone(re.search(r"[≤<]=?\s*(?:15|35)\s*%", owner))
        self.assertIn("contract-exception-policy-base.yaml", owner)

    def test_exception_shape_validation_consumes_registry_bounds(self):
        records = copy.deepcopy(policy.POLICY_REGISTRY)
        for row in records.values():
            if row.get("limit_domain") == "percent-share-under-100":
                row["minimum_inclusive"] = 10
                row["maximum_exclusive"] = 90
                row["joint_maximum_exclusive"] = 90
        _effective, fingerprint, _errors = \
            policy.effective_priority_policy(NONE_RUBRIC)
        entry = {
            "decision_id": "PE-1",
            "policy_id": "priority_quota.P0",
            "baseline_policy_fingerprint": fingerprint,
            "limit": 5,
            "scope_kind": "task",
            "scope_ref": "task-1",
            "rationale": "bounded migration",
            "approval_reference": "approval-1",
        }
        with mock.patch.object(policy, "POLICY_REGISTRY", records):
            errors = policy_exceptions.policy_exception_errors([entry], "x")
        self.assertTrue(any("at least 10 and under 90" in error
                            for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
