"""Current Standards state consumes one complete adoption-evidence chain."""

import copy
import unittest
from pathlib import Path

import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.governance.standards.adoption_lineage_contract as contract
from Tools.governance.control import control_registry_contract
import Tools.governance.profile.profile_contract as profile_contract


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64
REVISION = "0123456789abcdef0123456789abcdef01234567"
MANIFEST = "profiles/example/profile.toml"
ADOPTION_ID = "audit-profile-adoption"
PROFILE_LOAD_ID = "audit-profile-load"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ColdAwareCatalog(dict):
    """Minimal hot/cold Catalog double that forbids accidental cold reads."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cold = {}

    def resolve(self, receipt_id):
        raise AssertionError(
            "current lineage must not resolve cold Receipt %s" % receipt_id)


def profile_load_gate_identity():
    registry, _capabilities, _metadata, errors = \
        control_registry_contract.load_current_control_contract(
            REPOSITORY_ROOT)
    if errors:
        raise AssertionError("invalid fixture Control Registry: %s" % errors)
    gate = registry[contract.PROFILE_LOAD_GATE_ID]
    return {
        "tool": gate["tool"],
        "tool_version": gate["tool_version"],
        "check": gate["check"],
        "gate_id": contract.PROFILE_LOAD_GATE_ID,
        "dimension": gate["dimensions"][0],
    }


def active_view(receipt_id=ADOPTION_ID):
    return {
        "active_standards_sha256": SHA_A,
        "upstream_revision_id": REVISION,
        "selected_profile_manifest": MANIFEST,
        "standards_status": "approved",
        "standards_effective_date": "2026-08-31",
        "standards_state_revision": 1,
        "latest_adoption_receipt": receipt_id,
        "upstream_source_ref": "fixture://cambium",
    }


def profile_evidence():
    return {
        "selected_profile_manifest": MANIFEST,
        "profile_snapshot_sha256": SHA_B,
        "profile_contract_fingerprint": SHA_C,
        "profile_load_inputs_sha256": SHA_D,
        "metadata_execution_contract_fingerprint": SHA_A,
    }


def profile_records():
    gate = {
        "receipt_id": PROFILE_LOAD_ID,
        "target": MANIFEST,
        "result": "pass",
        "invalidated_by": None,
        "upstream_revision_id": REVISION,
        "selected_profile_manifest": MANIFEST,
        "profile_snapshot_sha256": SHA_B,
        "profile_contract_fingerprint": SHA_C,
        "profile_load_inputs_sha256": SHA_D,
    }
    gate.update(profile_load_gate_identity())
    adoption = {
        "receipt_id": ADOPTION_ID,
        "tool": contract.PROFILE_ADOPTION_TOOL,
        "tool_version": contract.PROFILE_ADOPTION_TOOL_VERSION,
        "check": "profile_adoption",
        "result": "pass",
        "invalidated_by": None,
        "upstream_revision_id_after": REVISION,
        "selected_profile_manifest_after": MANIFEST,
        "standards_effective_date_after": "2026-08-31",
        "upstream_source_ref": "fixture://cambium",
        "standards_state_sha256_after": SHA_A,
        "profile_snapshot_sha256_after": SHA_B,
        "profile_contract_fingerprint_after": SHA_C,
        "profile_load_inputs_sha256_after": SHA_D,
        "profile_load_gate_id": contract.PROFILE_LOAD_GATE_ID,
        "profile_load_receipt_id": PROFILE_LOAD_ID,
    }
    return {
        PROFILE_LOAD_ID: (contract.ADOPTION_RECEIPT_PATH, gate),
        ADOPTION_ID: (contract.ADOPTION_RECEIPT_PATH, adoption),
    }


def standards_records():
    receipt = {
        "receipt_id": ADOPTION_ID,
        "tool": contract.STANDARDS_ADOPTION_TOOL,
        "tool_version": contract.STANDARDS_ADOPTION_TOOL_VERSION,
        "check": "standards_adoption",
        "gate_id": contract.STANDARDS_ADOPTION_GATE_ID,
        "transaction_phase": "commit",
        "actor_role": "integrator",
        "result": "pass",
        "invalidated_by": None,
        "upstream_revision_id_after": REVISION,
        "selected_profile_manifest_after": MANIFEST,
        "standards_effective_date_after": "2026-08-31",
        "upstream_source_ref": "fixture://cambium",
        "after_standards_state_sha256": SHA_A,
        "profile_snapshot_sha256_after": SHA_B,
        "profile_contract_fingerprint_after": SHA_C,
        "profile_load_inputs_sha256_after": SHA_D,
    }
    return {ADOPTION_ID: (contract.ADOPTION_RECEIPT_PATH, receipt)}


class AdoptionLineageContractTests(unittest.TestCase):
    def test_profile_after_image_bindings_derive_from_profile_load_owner(self):
        self.assertEqual(
            tuple(("%s_after" % field, field) for field in
                  profile_contract.
                  PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS),
            contract.PROFILE_BINDINGS,
        )

    def test_profile_adoption_consumes_current_profile_load_chain(self):
        self.assertEqual([], contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=profile_records(), root=REPOSITORY_ROOT))

    def test_profile_load_producer_identity_comes_from_control_registry(self):
        catalog = profile_records()
        record = copy.deepcopy(catalog[PROFILE_LOAD_ID][1])
        record["tool_version"] = "fixture-version"
        catalog[PROFILE_LOAD_ID] = (contract.ADOPTION_RECEIPT_PATH, record)
        errors = contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=catalog, root=REPOSITORY_ROOT)
        self.assertIn("tool_version", "\n".join(errors))

    def test_profile_adoption_missing_precursor_fails_closed(self):
        catalog = profile_records()
        del catalog[PROFILE_LOAD_ID]
        errors = contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=catalog, root=REPOSITORY_ROOT)
        self.assertIn("missing profile-load evidence", "\n".join(errors))

    def test_profile_adoption_cannot_authorize_different_profile_bytes(self):
        evidence = profile_evidence()
        evidence["profile_snapshot_sha256"] = "sha256:" + "e" * 64
        errors = contract.current_lineage_errors(
            active_view(), profile_evidence=evidence,
            catalog=profile_records(), root=REPOSITORY_ROOT)
        self.assertIn("does not bind current authorized Profile",
                      "\n".join(errors))

    def test_current_authority_never_resolves_a_cold_latest_receipt(self):
        catalog = ColdAwareCatalog()
        catalog.cold[ADOPTION_ID] = {
            "receipt_id": ADOPTION_ID,
            "result": "pass",
        }
        errors = contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=catalog, root=REPOSITORY_ROOT)
        self.assertIn("cold latest adoption receipt", "\n".join(errors))

        direct = standards_records()
        receipt = direct[ADOPTION_ID][1]
        direct[ADOPTION_ID] = (
            runtime_paths.RECEIPT_COLD_ROOT + "/segment.jsonl", receipt)
        errors = contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=direct, root=REPOSITORY_ROOT)
        self.assertIn("outside canonical adoption history", "\n".join(errors))

    def test_profile_precursor_must_remain_hot_with_current_adoption(self):
        records = profile_records()
        _path, gate = records.pop(PROFILE_LOAD_ID)
        catalog = ColdAwareCatalog(records)
        catalog.cold[PROFILE_LOAD_ID] = gate
        errors = contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=catalog, root=REPOSITORY_ROOT)
        self.assertIn("cold profile-load evidence", "\n".join(errors))

    def test_active_task_adoption_consumes_commit_after_image(self):
        self.assertEqual([], contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=standards_records()))

    def test_pending_after_image_requires_the_exact_receipt_identity(self):
        catalog = standards_records()
        receipt = catalog[ADOPTION_ID][1]
        catalog[ADOPTION_ID] = ("<pending-write>", receipt)
        self.assertEqual([], contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=catalog, pending_receipt_id=ADOPTION_ID))

        errors = contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=catalog, pending_receipt_id="another-receipt")
        self.assertIn("outside canonical adoption history", "\n".join(errors))

    def test_pending_identity_never_authorizes_an_arbitrary_path(self):
        catalog = standards_records()
        receipt = catalog[ADOPTION_ID][1]
        catalog[ADOPTION_ID] = ("other/pending.jsonl", receipt)
        errors = contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=catalog, pending_receipt_id=ADOPTION_ID)
        self.assertIn("outside canonical adoption history", "\n".join(errors))

    def test_active_task_adoption_rejects_prepare_or_wrong_after_image(self):
        catalog = standards_records()
        record = copy.deepcopy(catalog[ADOPTION_ID][1])
        record["transaction_phase"] = "prepare"
        record["after_standards_state_sha256"] = SHA_B
        catalog[ADOPTION_ID] = (contract.ADOPTION_RECEIPT_PATH, record)
        errors = contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=catalog)
        joined = "\n".join(errors)
        self.assertIn("transaction_phase", joined)
        self.assertIn("active_standards_sha256", joined)

    def test_unregistered_producer_is_not_guessed(self):
        catalog = standards_records()
        record = copy.deepcopy(catalog[ADOPTION_ID][1])
        record["tool_version"] = "future"
        catalog[ADOPTION_ID] = (contract.ADOPTION_RECEIPT_PATH, record)
        errors = contract.current_lineage_errors(
            active_view(), profile_evidence=profile_evidence(),
            catalog=catalog)
        self.assertIn("unregistered producer", "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
