import os
import sys
import unittest
from unittest import mock


TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import Tools.execution.evidence.metadata_gate_runtime as metadata_gate_runtime  # noqa: E402
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
from Tools.execution.task_runtime.queue_runtime import authority


class RuntimeValidationCompositionTests(unittest.TestCase):
    def test_correction_admission_does_not_mask_corruption(self):
        observation = {
            "errors": ["unusable evidence"], "structural_errors": [],
            "current_evidence_deficits": [{"code": "evidence-invalidated"}],
        }
        self.assertEqual(["unusable evidence"], authority.runtime_admission_errors(observation))
        for purpose in ("record-evidence-invalidation", "evidence-production",
                        "typed-field-metadata-transition", "merge-ready-evidence-rollback"):
            with self.subTest(purpose=purpose):
                self.assertEqual([], authority.runtime_admission_errors(
                    observation, purpose=purpose))
                corrupt = dict(observation, structural_errors=["corrupt state"])
                self.assertEqual(["corrupt state"], authority.runtime_admission_errors(
                    corrupt, purpose=purpose))
        with self.assertRaises(ValueError):
            authority.runtime_admission_errors(observation, purpose="ignore-errors")
        self.assertTrue(authority.runtime_admission_errors(
            {"errors": []}, purpose="record-evidence-invalidation"))

    def test_runtime_validation_injects_the_unique_gate_predicate(self):
        with mock.patch.object(
                runtime_validation.queue_runtime.runtime,
                "validate_runtime", return_value={"ok": True}) as validate:
            result = runtime_validation.validate_runtime("/workspace")
        self.assertEqual({"ok": True}, result)
        self.assertIs(
            metadata_gate_runtime.persisted_property_gate_errors,
            validate.call_args.kwargs["gate_evidence_errors"],
        )
        with self.assertRaisesRegex(TypeError, "cannot be overridden"):
            runtime_validation.validate_runtime(
                "/workspace", gate_evidence_errors=lambda *_: [])

    def test_gate_context_current_composes_both_currentness_owners(self):
        context = mock.Mock(root="/workspace", authority=object())
        resolved_runtime = object()
        with (
                mock.patch.object(
                    runtime_validation.queue_runtime,
                    "require_runtime_authority_current") as authority_current,
                mock.patch.object(
                    metadata_gate_runtime,
                    "require_context_current") as gate_current):
            runtime_validation.require_gate_context_current(
                context, "pre-write", runtime=resolved_runtime)

        authority_current.assert_called_once_with(
            context.root, context.authority, "pre-write")
        gate_current.assert_called_once_with(
            context, "pre-write", runtime=resolved_runtime)

if __name__ == "__main__":
    unittest.main()
