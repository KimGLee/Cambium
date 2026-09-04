"""The Kernel registry, not Python prose, owns exception-policy semantics."""

import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
sys.path.insert(0, str(TOOLS))

import Tools.governance.control.contract_exception_policy as policy  # noqa: E402
from Tools.execution.task_runtime.queue_runtime import policy_exceptions  # noqa: E402
from Tools.tests.fixtures.contract.priority_quota_objects import (  # noqa: E402
    CONFIGURED_PRIORITY_QUOTA_RUBRIC,
    NONE_PRIORITY_QUOTA_RUBRIC,
)


class RegistryShapeTests(unittest.TestCase):

    def document(self):
        return copy.deepcopy(policy.load_policy_registry())

    def test_shipped_registry_loads_and_projects_the_existing_api(self):
        document = policy.load_policy_registry()
        records = policy.policy_registry_records(document)
        self.assertEqual(
            {"priority_quota.P0", "priority_quota.P1"},
            set(records))
        self.assertEqual(records, policy.POLICY_REGISTRY)
        self.assertTrue(all(
            set(row) == {"policy_id", "owner", "quota_class"}
            for row in document["families"][0]["policies"]))

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

    def test_limit_domain_is_projected_to_each_policy(self):
        document = self.document()
        domain = document["families"][0]["limit_domain"]
        records = policy.policy_registry_records(document)

        for record in records.values():
            self.assertEqual(domain["domain_id"], record["domain_id"])
            self.assertEqual(
                domain["minimum_inclusive"], record["minimum_inclusive"])
            self.assertEqual(
                domain["maximum_exclusive"], record["maximum_exclusive"])
            self.assertEqual(
                domain["joint_maximum_exclusive"],
                record["joint_maximum_exclusive"])

    def test_illegal_protocol_is_rejected(self):
        protocol = self.document()
        protocol["families"][0]["fingerprint_payload"][
            "protocol_version"] = 0
        with self.assertRaisesRegex(ValueError, "positive integer"):
            policy.policy_registry_records(protocol)

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


class FingerprintCurrentnessTests(unittest.TestCase):

    def document(self):
        return copy.deepcopy(policy.load_policy_registry())

    def test_effective_policy_fingerprint_is_stable(self):
        quota, quota_fingerprint, quota_errors = \
            policy.effective_priority_policy(NONE_PRIORITY_QUOTA_RUBRIC)
        self.assertEqual([], quota_errors)
        self.assertEqual(False, quota["enabled"])
        self.assertEqual("profile-none", quota["source"])
        self.assertEqual({}, quota["resolved"])
        again, again_fingerprint, again_errors = \
            policy.effective_priority_policy(NONE_PRIORITY_QUOTA_RUBRIC)
        self.assertEqual([], again_errors)
        self.assertEqual(quota, again)
        self.assertEqual(quota_fingerprint, again_fingerprint)
        self.assertRegex(quota_fingerprint, r"^sha256:[0-9a-f]{64}$")

    def test_registry_policy_revision_moves_the_effective_fingerprint(self):
        document = self.document()
        _old_policy, old_fingerprint, _errors = \
            policy.effective_priority_policy(NONE_PRIORITY_QUOTA_RUBRIC)
        document["families"][0]["fingerprint_payload"][
            "protocol_version"] += 1
        policy.policy_registry_records(document)
        _new_policy, new_fingerprint, errors = \
            policy.effective_priority_policy(
                NONE_PRIORITY_QUOTA_RUBRIC, registry=document)
        self.assertEqual([], errors)
        self.assertNotEqual(old_fingerprint, new_fingerprint)

    def test_none_has_no_numeric_fallback_and_configured_values_are_exact(self):
        inactive, _fingerprint, errors = policy.effective_priority_policy(
            NONE_PRIORITY_QUOTA_RUBRIC)
        self.assertEqual([], errors)
        self.assertIs(inactive["enabled"], False)
        self.assertEqual({}, inactive["resolved"])

        effective, _fingerprint, errors = policy.effective_priority_policy(
            CONFIGURED_PRIORITY_QUOTA_RUBRIC)
        self.assertEqual([], errors)
        self.assertIs(effective["enabled"], True)
        self.assertEqual(
            {"schema_version", "protocol_version", "enabled", "source",
             "resolved"}, set(effective))
        self.assertEqual(
            {"priority_quota.P0": 20.0, "priority_quota.P1": 30.0},
            effective["resolved"])


class PriorityQuotaRegistryConnectionTests(unittest.TestCase):

    def test_exception_shape_validation_consumes_registry_bounds(self):
        records = copy.deepcopy(policy.POLICY_REGISTRY)
        for row in records.values():
            if row.get("domain_id") == "percent-share-under-100":
                row["minimum_inclusive"] = 10
                row["maximum_exclusive"] = 90
                row["joint_maximum_exclusive"] = 90
        _effective, fingerprint, _errors = \
            policy.effective_priority_policy(CONFIGURED_PRIORITY_QUOTA_RUBRIC)
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


class EffectiveQuotaCeilingTests(unittest.TestCase):

    def test_inactive_configured_exception_and_joint_bound_matrix(self):
        inactive, _fingerprint, errors = policy.effective_priority_policy(
            NONE_PRIORITY_QUOTA_RUBRIC)
        self.assertEqual([], errors)
        self.assertEqual(({}, []), policy.effective_quota_ceilings(
            inactive, []))
        ceilings, errors = policy.effective_quota_ceilings(
            inactive, [{"policy_id": "priority_quota.P0", "limit": 40}])
        self.assertEqual({}, ceilings)
        self.assertTrue(any("not configured" in error for error in errors),
                        errors)

        configured, _fingerprint, errors = policy.effective_priority_policy(
            CONFIGURED_PRIORITY_QUOTA_RUBRIC)
        self.assertEqual([], errors)
        ceilings, errors = policy.effective_quota_ceilings(configured, [])
        self.assertEqual([], errors)
        self.assertEqual(
            {"priority_quota.P0": {"limit": 20.0, "source": "configured"},
             "priority_quota.P1": {"limit": 30.0, "source": "configured"}},
            ceilings)

        exception = {
            "decision_id": "PE-1",
            "policy_id": "priority_quota.P0",
            "limit": 40,
        }
        ceilings, errors = policy.effective_quota_ceilings(
            configured, [exception])
        self.assertEqual([], errors)
        self.assertEqual(40, ceilings["priority_quota.P0"]["limit"])
        self.assertEqual(
            "exception:PE-1", ceilings["priority_quota.P0"]["source"])

        exception["limit"] = 75
        _ceilings, errors = policy.effective_quota_ceilings(
            configured, [exception])
        self.assertTrue(any("strictly below" in error for error in errors),
                        errors)


if __name__ == "__main__":
    unittest.main()
