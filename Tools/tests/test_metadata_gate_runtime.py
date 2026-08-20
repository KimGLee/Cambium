"""Focused tests for typed Extension Gate evidence and integration."""

import copy
from dataclasses import replace
import io
import os
from pathlib import Path
from types import SimpleNamespace
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import apply_metadata_transition
import kblib
import metadata_execution_contract
import metadata_gate_runtime
import metadata_property_state
import project_page_state
import profile_contract
import record_gate_attestation
import record_gate_result


PAGE = "Notes/Target.md"
PAGE_TEXT = """---
type: concept
---
# Target

Substantive content.
"""


class MetadataGateRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        (self.root / ".cambium/state").mkdir(parents=True)
        (self.root / ".cambium/tmp").mkdir()
        (self.root / ".cambium/receipts").mkdir()
        (self.root / "Notes").mkdir()
        (self.root / PAGE).write_text(PAGE_TEXT, encoding="utf-8")
        self.coverage = {
            "schema_version": 1,
            "pages": [{"path": PAGE}],
        }
        self.coverage_path = (
            self.root / ".cambium/state/coverage_ledger.yaml")
        self.coverage_path.write_text(
            kblib.canonical_yaml(self.coverage), encoding="utf-8")
        self.gate = SimpleNamespace(
            gate_id="P:sample:readiness",
            transition_id="readiness-promotion",
            judgment_item_id="sample-readiness",
            pass_authority_role_id="release-reviewer",
            field_id="readiness_state",
            completion_values=("accepted", "rejected"),
            producer_kind="manual-attestation",
            producer_capability="manual-attestation-v1",
            producer_reference="release-reviewer",
            receipt_schema="manual-gate-attestation-v1",
            consumer_capability="metadata-transition-integrator-v1",
        )
        self.rules = metadata_execution_contract.AuthorizedProjectionRules(
            (metadata_gate_runtime.synthetic_projection_rule(self.gate),),
            "sha256:" + "8" * 64,
            "sha256:" + "2" * 64)
        page = kblib.repository_target_snapshot(
            self.root, PAGE, suffixes=".md", singly_linked=True)
        semantic = project_page_state.semantic_content_fingerprint(
            PAGE, page.read_text(), self.rules)
        profile_view = {
            "selected_profile_manifest": "profiles/sample/profile.md",
            "profile_snapshot_sha256": "sha256:" + "1" * 64,
            "profile_contract_fingerprint": "sha256:" + "2" * 64,
            "profile_load_inputs_sha256": "sha256:" + "3" * 64,
        }
        authority = {
            "root": os.path.realpath(str(self.root)),
            "profile_view": profile_view,
            "active_standards_view": {
                "active_standards_sha256": "sha256:" + "4" * 64,
            },
        }
        runtime = {
            "root": str(self.root),
            "errors": [],
            "writer_locks": [],
            "coverage": copy.deepcopy(self.coverage),
            "coverage_sha256": kblib.sha256_file(self.coverage_path),
            "queue_sha256": "sha256:" + "5" * 64,
            "progress_sha256": "sha256:" + "6" * 64,
            "current_receipt_catalog": {},
            "receipt_catalog": {},
        }
        self.context = metadata_gate_runtime.GateRuntimeContext(
            root=os.path.realpath(str(self.root)), runtime=runtime,
            authority=authority, gate=self.gate, rules=self.rules,
            page_path=PAGE, page_snapshot=page,
            semantic_content_fingerprint=semantic,
            selected_profile_manifest_sha256="sha256:" + "7" * 64,
            metadata_contract_fingerprint="sha256:" + "8" * 64,
        )
        self.receipt = record_gate_attestation.build_attestation_receipt(
            self.context, "accepted", "release-reviewer",
            "The bounded readiness predicate passes.")
        self.context.runtime["current_receipt_catalog"] = {
            self.receipt["receipt_id"]: (
                ".cambium/receipts/gate-attestations.jsonl", self.receipt),
        }

    def test_manual_producer_rejects_wrong_role_and_value(self):
        with self.assertRaisesRegex(ValueError, "expected 'release-reviewer'"):
            record_gate_attestation.build_attestation_receipt(
                self.context, "accepted", "worker", "passes")
        with self.assertRaisesRegex(ValueError, "not authorized"):
            record_gate_attestation.build_attestation_receipt(
                self.context, "invented", "release-reviewer", "passes")

    def test_consumer_rejects_stale_content_profile_and_schema(self):
        stale_content = replace(
            self.context,
            semantic_content_fingerprint="sha256:" + "9" * 64)
        with self.assertRaisesRegex(
                ValueError, "semantic_content_fingerprint"):
            metadata_gate_runtime.validate_gate_receipt(
                stale_content, self.receipt, "accepted")

        authority = copy.deepcopy(self.context.authority)
        authority["profile_view"]["profile_snapshot_sha256"] = \
            "sha256:" + "a" * 64
        stale_profile = replace(self.context, authority=authority)
        with self.assertRaisesRegex(ValueError, "profile_snapshot_sha256"):
            metadata_gate_runtime.validate_gate_receipt(
                stale_profile, self.receipt, "accepted")

        wrong_schema = dict(self.receipt)
        wrong_schema["receipt_schema"] = "deterministic-gate-result-v1"
        with self.assertRaisesRegex(ValueError, "receipt_schema"):
            metadata_gate_runtime.validate_gate_receipt(
                self.context, wrong_schema, "accepted")

    def test_current_catalog_is_not_replaced_by_historical_receipt(self):
        runtime = dict(self.context.runtime)
        runtime["current_receipt_catalog"] = {}
        runtime["receipt_catalog"] = {
            self.receipt["receipt_id"]: ("history.jsonl", self.receipt),
        }
        stale = replace(self.context, runtime=runtime)
        with self.assertRaisesRegex(ValueError, "current receipt catalog"):
            metadata_gate_runtime.current_gate_receipt(
                stale, self.receipt["receipt_id"], "accepted")

    def test_transition_does_not_hide_corrupt_existing_owner_state(self):
        coverage = copy.deepcopy(self.coverage)
        coverage["pages"][0]["property_state"] = {
            "readiness_state": {
                "value": "invented",
                "evidence_receipt": self.receipt["receipt_id"],
                "content_fingerprint":
                    self.context.semantic_content_fingerprint,
            },
        }
        with self.assertRaisesRegex(ValueError, "undeclared enum value"):
            metadata_property_state.apply_gate_transition(
                coverage, PAGE, "readiness_state", "accepted",
                self.receipt["receipt_id"],
                self.context.semantic_content_fingerprint,
                self.gate.completion_values)

    def test_real_profile_contract_drives_generic_gate_context(self):
        manifest = "profiles/examples/agent-atlas/profile.md"
        contract = profile_contract.load_profile_contract(
            REPOSITORY, REPOSITORY / manifest)
        self.assertTrue(contract.authorized, contract.diagnostics)
        profile_snapshot = kblib.repository_tree_sha256(
            REPOSITORY, "profiles/examples/agent-atlas")
        authority = {
            "root": os.path.realpath(str(REPOSITORY)),
            "profile_view": {
                "selected_profile_manifest": manifest,
                "profile_snapshot_sha256": profile_snapshot,
                "profile_contract_fingerprint":
                    contract.profile_contract_fingerprint,
                "profile_load_inputs_sha256": "sha256:" + "b" * 64,
                "_contract": contract,
            },
            "active_standards_view": {
                "active_standards_sha256": "sha256:" + "c" * 64,
            },
        }
        runtime = {"errors": [], "writer_locks": []}
        context = metadata_gate_runtime.load_gate_context(
            REPOSITORY, "P:agent-atlas:interview-readiness",
            "kernel/Read Sets/R07 Long-running Execution Read Set.md",
            runtime=runtime, authority=authority)
        self.assertEqual("interview_status", context.gate.field_id)
        self.assertEqual(("interview-ready",),
                         context.gate.completion_values)
        synthetic = context.rules[-1]
        self.assertEqual("enum", synthetic["value_shape"])
        self.assertEqual(["interview-ready"],
                         synthetic["allowed_values"])

    def test_profile_rule_set_covers_all_gates_and_unions_same_field(self):
        gates = (
            SimpleNamespace(
                field_id="alpha_state", completion_values=("ready",)),
            SimpleNamespace(
                field_id="beta_state", completion_values=("verified",)),
            SimpleNamespace(
                field_id="alpha_state", completion_values=("rejected",)),
        )
        rules = metadata_property_state.profile_gate_projection_rules(
            REPOSITORY, gates,
            authorized_profile_contract=SimpleNamespace(
                authorized=True, extension_gates=gates,
                profile_contract_fingerprint="sha256:" + "f" * 64))
        extension = {rule["field"]: rule for rule in rules
                     if rule["field"] in ("alpha_state", "beta_state")}
        self.assertEqual({"alpha_state", "beta_state"}, set(extension))
        self.assertEqual(
            ["ready", "rejected"],
            extension["alpha_state"]["allowed_values"])

    def test_projector_rejects_uncomposed_synthetic_rule_tuple(self):
        with self.assertRaisesRegex(
                ValueError, "authorized typed Profile composition"):
            project_page_state.build_projection_plan(
                self.root, ledger_override=self.coverage,
                rules=(metadata_gate_runtime.synthetic_projection_rule(
                    self.gate),))

    def _deterministic_context(self):
        tool_path = self.root / "Tools/sample_readiness_scan.py"
        tool_path.parent.mkdir(exist_ok=True)
        tool_path.write_text(
            "#!/usr/bin/env python3\n# frozen sample verifier\n",
            encoding="utf-8")
        scan = SimpleNamespace(
            scan_id="sample-readiness-scan",
            script_repo_path="Tools/sample_readiness_scan.py",
            config_dependency=None,
        )
        gate = SimpleNamespace(
            gate_id="P:sample:deterministic-readiness",
            transition_id="deterministic-readiness-promotion",
            judgment_item_id="sample-deterministic-readiness",
            pass_authority_role_id="automated-verifier",
            field_id="readiness_state",
            completion_values=("accepted",),
            producer_kind="deterministic",
            producer_capability="registered-scan-v1",
            producer_reference=scan.scan_id,
            receipt_schema="deterministic-gate-result-v1",
            consumer_capability="metadata-transition-integrator-v1",
        )
        authority = copy.deepcopy(self.context.authority)
        authority["profile_view"]["_contract"] = SimpleNamespace(
            registered_scans=(scan,))
        return replace(self.context, gate=gate, authority=authority), scan

    def _scan_command_patch(self, scan, *extra):
        return mock.patch.object(
            metadata_gate_runtime.profile_contract,
            "compile_registered_scan_command",
            return_value=(
                sys.executable,
                str(self.root / scan.script_repo_path),
                str(self.root),
            ) + tuple(extra))

    @staticmethod
    def _scan_receipt(scan_id="sample-readiness-scan"):
        return {
            "receipt_id": "scan-pass-1",
            "tool": "sample_readiness_scan",
            "tool_version": "1.0.0",
            "check": "sample-readiness",
            "target": "repository",
            "result": "pass",
            "details": "registered scan passed",
            "checked_at": "2026-08-20T00:00:00Z",
            "seq": 1,
            "invalidated_by": None,
            "scan_id": scan_id,
        }

    def test_deterministic_adapter_runs_exact_scan_and_builds_typed_receipt(self):
        context, scan = self._deterministic_context()
        source = self._scan_receipt()

        def run(command, **_kwargs):
            self.assertNotEqual(
                os.path.realpath(command[1]),
                os.path.realpath(self.root / scan.script_repo_path))
            self.assertEqual(
                b"#!/usr/bin/env python3\n# frozen sample verifier\n",
                Path(command[1]).read_bytes())
            output_path = command[command.index("--receipts") + 1]
            Path(output_path).write_bytes(
                kblib.canonical_json_bytes(source) + b"\n")
            return __import__("subprocess").CompletedProcess(
                command, 0, stdout="scan passed\n")

        with self._scan_command_patch(scan), \
                mock.patch.object(
                    record_gate_result.subprocess, "run", side_effect=run):
            result = record_gate_result.run_registered_gate_scan(context)
            receipt = record_gate_result.build_gate_result_receipt(
                context, result)
        self.assertEqual("deterministic-gate-result-v1",
                         receipt["receipt_schema"])
        self.assertEqual("accepted",
                         receipt["requested_completion_value"])
        self.assertEqual(source, receipt["registered_scan_receipt"])
        with self._scan_command_patch(scan):
            self.assertEqual(
                receipt,
                metadata_gate_runtime.validate_gate_receipt(
                    context, receipt, "accepted"))

    def test_deterministic_adapter_rejects_wrong_scan_and_repository_drift(self):
        context, scan = self._deterministic_context()

        def wrong_scan(command, **_kwargs):
            output_path = command[command.index("--receipts") + 1]
            Path(output_path).write_bytes(kblib.canonical_json_bytes(
                self._scan_receipt("other-scan")) + b"\n")
            return __import__("subprocess").CompletedProcess(
                command, 0, stdout="scan passed\n")

        command_patch = self._scan_command_patch(scan)
        with command_patch, mock.patch.object(
                record_gate_result.subprocess, "run", side_effect=wrong_scan):
            with self.assertRaisesRegex(ValueError, "expected"):
                record_gate_result.run_registered_gate_scan(context)

        source = self._scan_receipt()

        def passing_scan(command, **_kwargs):
            output_path = command[command.index("--receipts") + 1]
            Path(output_path).write_bytes(
                kblib.canonical_json_bytes(source) + b"\n")
            return __import__("subprocess").CompletedProcess(
                command, 0, stdout="scan passed\n")

        with self._scan_command_patch(scan), \
                mock.patch.object(
                    record_gate_result.subprocess, "run",
                    side_effect=passing_scan), \
                mock.patch.object(
                    record_gate_result.kblib,
                    "repository_snapshot_sha256",
                    side_effect=("sha256:" + "1" * 64,
                                 "sha256:" + "2" * 64)):
            with self.assertRaisesRegex(ValueError, "repository changed"):
                record_gate_result.run_registered_gate_scan(context)

    def test_deterministic_adapter_rejects_tool_a_to_b_to_a_swap(self):
        context, scan = self._deterministic_context()
        source = self._scan_receipt()
        live_tool = self.root / scan.script_repo_path
        original = live_tool.read_bytes()

        def transient_swap(command, **_kwargs):
            # The invoked script is a frozen copy, never either transient live
            # generation.  Restoring the original bytes still changes the
            # live file generation and must fail the exact pre/post CAS.
            self.assertNotEqual(
                os.path.realpath(command[1]), os.path.realpath(live_tool))
            live_tool.write_bytes(b"raise SystemExit('transient')\n")
            live_tool.write_bytes(original)
            output_path = command[command.index("--receipts") + 1]
            Path(output_path).write_bytes(
                kblib.canonical_json_bytes(source) + b"\n")
            return __import__("subprocess").CompletedProcess(
                command, 0, stdout="scan passed\n")

        with self._scan_command_patch(scan), mock.patch.object(
                record_gate_result.subprocess, "run",
                side_effect=transient_swap):
            with self.assertRaisesRegex(
                    ValueError, "tool identity or bytes changed"):
                record_gate_result.run_registered_gate_scan(context)

    def test_deterministic_adapter_executes_authorized_snapshot_config(self):
        context, scan = self._deterministic_context()
        profile_dir = self.root / "profiles/sample"
        profile_dir.mkdir(parents=True)
        config_path = profile_dir / "scan-config.yaml"
        authorized = b"schema_version: 1\nmode: exact\n"
        config_path.write_bytes(authorized)
        scan.config_dependency = SimpleNamespace(
            path="profiles/sample/scan-config.yaml")
        authority = dict(context.authority)
        profile_view = dict(context.profile_view)
        profile_view["_profile_snapshot"] = kblib.repository_tree_snapshot(
            self.root, "profiles/sample")
        authority["profile_view"] = profile_view
        context = replace(context, authority=authority)
        source = self._scan_receipt()

        def run(command, **_kwargs):
            config_argument = command[command.index("--config") + 1]
            self.assertNotEqual(
                os.path.realpath(config_argument),
                os.path.realpath(config_path))
            self.assertEqual(authorized, Path(config_argument).read_bytes())
            # The live Profile path is not an execution input.  Even an A-B-A
            # swap cannot cause the scan to consume bytes other than the
            # profile-load-authorized snapshot staged above.
            config_path.write_bytes(b"schema_version: 9\n")
            config_path.write_bytes(authorized)
            output_path = command[command.index("--receipts") + 1]
            Path(output_path).write_bytes(
                kblib.canonical_json_bytes(source) + b"\n")
            return __import__("subprocess").CompletedProcess(
                command, 0, stdout="scan passed\n")

        with self._scan_command_patch(
                scan, "--config", "profiles/sample/scan-config.yaml"), \
                mock.patch.object(
                    record_gate_result.subprocess, "run", side_effect=run):
            result = record_gate_result.run_registered_gate_scan(context)
        self.assertEqual(
            kblib.sha256_bytes(authorized), result["config_sha256"])

    def test_deterministic_transition_rejects_other_page_changed_after_scan(self):
        context, scan = self._deterministic_context()
        source = self._scan_receipt()

        def run(command, **_kwargs):
            output_path = command[command.index("--receipts") + 1]
            Path(output_path).write_bytes(
                kblib.canonical_json_bytes(source) + b"\n")
            return __import__("subprocess").CompletedProcess(
                command, 0, stdout="scan passed\n")

        with self._scan_command_patch(scan), mock.patch.object(
                record_gate_result.subprocess, "run", side_effect=run):
            result = record_gate_result.run_registered_gate_scan(context)
            receipt = record_gate_result.build_gate_result_receipt(
                context, result)
        context.runtime["current_receipt_catalog"] = {
            receipt["receipt_id"]: (
                ".cambium/receipts/gate-results.jsonl", receipt),
        }
        (self.root / "Notes/Other.md").write_text(
            "# Other\n\nChanged after the vault-wide scan.\n",
            encoding="utf-8")
        with self._scan_command_patch(scan):
            with self.assertRaisesRegex(ValueError, "repository snapshot"):
                apply_metadata_transition.prepare_transition(
                    context, receipt["receipt_id"], "accepted",
                    actor_role="integrator")

    def test_deterministic_receipt_rejects_tampered_embedded_pass(self):
        context, scan = self._deterministic_context()
        source = self._scan_receipt()
        result = {
            "summary": source,
            "summary_sha256": kblib.sha256_bytes(
                kblib.canonical_json_bytes(source)),
            "receipt_set_sha256": "sha256:" + "1" * 64,
            "receipt_count": 1,
            "command_sha256": "sha256:" + "2" * 64,
            "tool_sha256": "sha256:" + "4" * 64,
            "config_sha256": None,
            "python_runtime_sha256": "sha256:" + "5" * 64,
            "execution_input_sha256": "sha256:" + "6" * 64,
            "repository_snapshot_sha256": "sha256:" + "3" * 64,
        }
        with self._scan_command_patch(scan):
            inputs = metadata_gate_runtime.deterministic_scan_input_binding(
                context, scan)
            for result_field, input_field in (
                    ("command_sha256", "command_sha256"),
                    ("tool_sha256", "tool_sha256"),
                    ("config_sha256", "config_sha256"),
                    ("python_runtime_sha256", "python_runtime_sha256"),
                    ("execution_input_sha256", "execution_input_sha256")):
                result[result_field] = inputs[input_field]
            result["repository_snapshot_sha256"] = \
                kblib.repository_snapshot_sha256(self.root)
            receipt = record_gate_result.build_gate_result_receipt(
                context, result)
            missing_body = copy.deepcopy(receipt)
            missing_body.pop("registered_scan_receipt")
            with self.assertRaisesRegex(ValueError, "embedded scan receipt"):
                metadata_gate_runtime.validate_gate_receipt(
                    context, missing_body, "accepted",
                    require_current_repository=False,
                    allow_projected_page=True)
            tampered = copy.deepcopy(receipt)
            tampered["registered_scan_receipt"]["result"] = "candidate"
            with self.assertRaisesRegex(ValueError, "hash is invalid"):
                metadata_gate_runtime.validate_gate_receipt(
                    context, tampered, "accepted")

            wrong_tool = copy.deepcopy(receipt)
            wrong_tool["registered_scan_receipt"]["tool"] = "other_scan"
            wrong_tool["registered_scan_receipt_sha256"] = kblib.sha256_bytes(
                kblib.canonical_json_bytes(
                    wrong_tool["registered_scan_receipt"]))
            with self.assertRaisesRegex(ValueError, "wrong tool"):
                metadata_gate_runtime.validate_gate_receipt(
                    context, wrong_tool, "accepted")

    def _dynamic_runtime(self, *_args, **_kwargs):
        runtime = dict(self.context.runtime)
        runtime["coverage"] = kblib.load_yaml_file(self.coverage_path)
        runtime["coverage_sha256"] = kblib.sha256_file(self.coverage_path)
        runtime["errors"] = []
        return runtime

    def _run_apply(self, append=None):
        arguments = [
            str(self.root), "--gate-id", self.gate.gate_id,
            "--page", PAGE, "--value", "accepted",
            "--gate-receipt", self.receipt["receipt_id"],
            "--actor-role", "integrator",
            "--expected-coverage-sha256",
            self.context.runtime["coverage_sha256"],
            "--expected-page-sha256", self.context.page_snapshot.sha256,
            "--apply",
        ]
        patches = [
            mock.patch.object(
                apply_metadata_transition.metadata_gate_runtime,
                "load_gate_context", return_value=self.context),
            mock.patch.object(
                apply_metadata_transition.check_queue, "validate_runtime",
                side_effect=self._dynamic_runtime),
            mock.patch.object(
                apply_metadata_transition.check_queue,
                "runtime_authority_validation_kwargs", return_value={}),
            mock.patch.object(
                apply_metadata_transition.check_queue,
                "runtime_authority_lock_fields", return_value={}),
            mock.patch.object(
                apply_metadata_transition.metadata_gate_runtime,
                "require_context_current", return_value=None),
            mock.patch.object(
                apply_metadata_transition.metadata_gate_runtime,
                "require_authorities_current", return_value=None),
        ]
        if append is not None:
            patches.append(mock.patch.object(
                apply_metadata_transition.kblib,
                "write_receipts_observed", side_effect=append))
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
                patches[5]:
            if len(patches) == 7:
                with patches[6], redirect_stdout(stdout), redirect_stderr(stderr):
                    code = apply_metadata_transition.main(arguments)
            else:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = apply_metadata_transition.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_success_atomically_updates_owner_and_page(self):
        code, stdout, stderr = self._run_apply()
        self.assertEqual(0, code, stdout + stderr)
        state = kblib.load_yaml_file(self.coverage_path)["pages"][0][
            "property_state"]["readiness_state"]
        self.assertEqual("accepted", state["value"])
        self.assertEqual(self.receipt["receipt_id"],
                         state["evidence_receipt"])
        page = (self.root / PAGE).read_text(encoding="utf-8")
        self.assertIn("readiness_state: accepted", page)
        self.assertFalse((self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_absent_receipt_failure_rolls_back_owner_and_page(self):
        before_coverage = self.coverage_path.read_bytes()
        before_page = (self.root / PAGE).read_bytes()

        def fail_append(*_args, **_kwargs):
            return "absent", OSError("injected append failure"), {}

        code, stdout, stderr = self._run_apply(fail_append)
        self.assertEqual(1, code, stdout + stderr)
        self.assertEqual(before_coverage, self.coverage_path.read_bytes())
        self.assertEqual(before_page, (self.root / PAGE).read_bytes())
        self.assertFalse((self.root / ".cambium/tmp/state-writer.lock").exists())


if __name__ == "__main__":
    unittest.main()
