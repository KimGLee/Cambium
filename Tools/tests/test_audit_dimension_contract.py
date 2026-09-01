"""Closed-contract tests for the K12 audit-dimension base registry."""

import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.governance.profile.check_profile as check_profile
import Tools.platform.common.kblib as kblib
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.governance.profile.profile_contract as profile_contract


class AuditDimensionContractTests(unittest.TestCase):
    def document(self):
        return copy.deepcopy(kblib.load_yaml_file(
            REPOSITORY /
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH))

    def test_shipped_registry_is_the_unique_machine_projection(self):
        values = audit_dimension_contract.validate_audit_dimension_base(
            self.document())
        self.assertEqual(
            tuple(self.document()["base_receipt_dimensions"]),
            values["base_receipt_dimensions"])
        self.assertEqual(
            frozenset(self.document()["evidence_roles"]),
            values["evidence_roles"])
        self.assertEqual(
            set(self.document()["extension_output_kinds"]),
            {output for outputs in
             values["extension_target_mappings"].values()
             for output in outputs})

    def test_duplicate_dimension_is_rejected(self):
        document = self.document()
        document["base_receipt_dimensions"].append(
            document["base_receipt_dimensions"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit_dimension_contract.validate_audit_dimension_base(document)

    def test_invalid_dimension_identifier_is_rejected(self):
        document = self.document()
        document["base_receipt_dimensions"][0] = "Structure/Links"
        with self.assertRaisesRegex(ValueError, "invalid value"):
            audit_dimension_contract.validate_audit_dimension_base(document)

    def test_duplicate_evidence_role_is_rejected(self):
        document = self.document()
        document["evidence_roles"].append(document["evidence_roles"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit_dimension_contract.validate_audit_dimension_base(document)

    def test_extension_target_outputs_must_close_over_registered_kinds(self):
        document = self.document()
        document["extension_target_mappings"][0]["outputs"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "unknown output kind"):
            audit_dimension_contract.validate_audit_dimension_base(document)

    def test_profile_load_currentness_binds_the_k12_registry_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in check_profile.CANONICAL_PROFILE_LOAD_INPUTS:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPOSITORY / relative, target)
            capabilities = kblib.load_yaml_file(
                REPOSITORY / check_profile.DEFAULT_OPERATION_CAPABILITIES)
            for relative in metadata_execution_contract.\
                    capability_implementation_paths(capabilities):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPOSITORY / relative, target)
            scans = kblib.load_yaml_file(
                REPOSITORY / profile_contract.SCAN_CAPABILITY_PATH)
            for relative in profile_contract.\
                    scan_capability_implementation_paths(scans):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPOSITORY / relative, target)

            _snapshots, before = check_profile.canonical_profile_load_inputs(
                root)
            registry = root / audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH
            registry.write_text(
                registry.read_text(encoding="utf-8") +
                "\n# byte-level currentness probe\n", encoding="utf-8")
            _snapshots, after = check_profile.canonical_profile_load_inputs(
                root)
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
