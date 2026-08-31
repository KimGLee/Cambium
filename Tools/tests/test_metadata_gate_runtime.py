"""Owned tests for the current typed metadata Gate evidence lifecycle."""

import copy
from dataclasses import replace
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock

import Tools.execution.evidence.metadata_gate_runtime as gate_runtime
import Tools.execution.evidence.record_gate_attestation as manual_producer
import Tools.execution.evidence.record_gate_result as scan_producer
import Tools.governance.control.metadata_execution_contract as metadata_contract
import Tools.knowledge.metadata.apply_metadata_transition as transition_writer
import Tools.knowledge.metadata.metadata_property_state as property_state
import Tools.knowledge.metadata.project_page_state as page_state
import Tools.platform.common.kblib as kblib


PAGE = "Notes/Target.md"
PAGE_TEXT = """---
type: concept
---
# Target

Substantive content.
"""


def _gate(producer_kind="manual-attestation"):
    deterministic = producer_kind == "deterministic"
    return SimpleNamespace(
        gate_id="P:sample:readiness",
        transition_id="readiness-promotion",
        judgment_item_id="sample-readiness",
        pass_authority_role_id=(
            "automated-verifier" if deterministic else "release-reviewer"),
        field_id="readiness_state",
        completion_values=("accepted",),
        producer_kind=producer_kind,
        producer_capability=(
            "registered-scan-v1" if deterministic
            else "manual-attestation-v1"),
        producer_reference=(
            "sample-readiness-scan" if deterministic
            else "release-reviewer"),
        receipt_schema=(
            "deterministic-gate-result-v1" if deterministic
            else "manual-gate-attestation-v1"),
        consumer_capability="typed-metadata-transition-v1",
    )


def _context(root="/not-accessed", gate=None, page_snapshot=None):
    gate = gate or _gate()
    profile_view = {
        "selected_profile_manifest": "profiles/sample/profile.md",
        "profile_snapshot_sha256": "sha256:" + "1" * 64,
        "profile_contract_fingerprint": "sha256:" + "2" * 64,
        "profile_load_inputs_sha256": "sha256:" + "3" * 64,
    }
    return gate_runtime.GateRuntimeContext(
        root=os.path.realpath(os.fspath(root)),
        runtime={"current_receipt_catalog": {}},
        authority={
            "root": os.path.realpath(os.fspath(root)),
            "profile_view": profile_view,
            "active_standards_view": {
                "active_standards_sha256": "sha256:" + "4" * 64,
            },
        },
        gate=gate,
        rules=(),
        page_path=PAGE,
        page_snapshot=(page_snapshot or SimpleNamespace(
            sha256="sha256:" + "5" * 64)),
        semantic_content_fingerprint="sha256:" + "6" * 64,
        selected_profile_manifest_sha256="sha256:" + "7" * 64,
        metadata_contract_fingerprint="sha256:" + "8" * 64,
    )


def _manual_receipt(context):
    bindings = gate_runtime.receipt_bindings(context, "accepted")
    statement = "The bounded readiness predicate passes."
    return {
        "receipt_id": "manual-gate-current-1",
        "receipt_type_id": gate_runtime.MANUAL_GATE_RECEIPT_TYPE_ID,
        "tool": gate_runtime.MANUAL_GATE_PRODUCER_IDENTITY.tool,
        "tool_version": gate_runtime.MANUAL_GATE_PRODUCER_IDENTITY.tool_version,
        "check": gate_runtime.MANUAL_GATE_PRODUCER_IDENTITY.check,
        "target": context.page_path,
        "result": "pass",
        "details": statement,
        "checked_at": "2026-08-31T00:00:00Z",
        "invalidated_by": None,
        **bindings,
        "actor_role": context.gate.pass_authority_role_id,
        "attestation_statement": statement,
    }


class MetadataGateEvidenceContractTests(unittest.TestCase):
    """Pure producer/consumer evidence contract; no runtime filesystem."""

    def test_manual_evidence_is_accepted_only_for_the_exact_gate_binding(self):
        context = _context()
        receipt = _manual_receipt(context)
        self.assertIs(
            receipt,
            gate_runtime.validate_gate_receipt(
                context, receipt, "accepted"))
        self.assertEqual(
            [], gate_runtime.current_manual_gate_receipt_errors(receipt))

        mutations = (
            ("semantic_content_fingerprint", "sha256:" + "9" * 64),
            ("profile_snapshot_sha256", "sha256:" + "a" * 64),
            ("receipt_schema", "other-schema"),
            ("actor_role", "worker"),
            ("tool", "other-producer"),
            ("tool_version", "9.0.0"),
            ("check", "other-check"),
            ("requested_completion_value", "rejected"),
            ("selected_profile_manifest", "profiles/other/profile.md"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(receipt)
                changed[field] = value
                with self.assertRaises(ValueError):
                    gate_runtime.validate_gate_receipt(
                        context, changed, "accepted")

    def test_manual_producer_cannot_override_profile_role_or_value(self):
        context = _context()
        with self.assertRaisesRegex(ValueError, "expected 'release-reviewer'"):
            manual_producer.build_attestation_receipt(
                context, "accepted", "worker", "passes")
        with self.assertRaisesRegex(ValueError, "not authorized"):
            manual_producer.build_attestation_receipt(
                context, "rejected", "release-reviewer", "passes")

    def test_runtime_and_authority_views_must_be_the_same_admission_pair(self):
        profile_view = {"selected_profile_manifest": "profiles/p/profile.md"}
        active_view = {"active_standards_sha256": "sha256:" + "c" * 64}
        runtime = {
            "_profile_authorized_view": profile_view,
            "_active_standards_authorized_view": active_view,
        }
        authority = {
            "profile_view": profile_view,
            "active_standards_view": active_view,
        }
        gate_runtime.require_paired_authority(runtime, authority)

        split = dict(authority, profile_view=dict(profile_view))
        with self.assertRaisesRegex(ValueError, "different admission"):
            gate_runtime.require_paired_authority(runtime, split)


class MetadataGateLifecycleIntegrationTests(unittest.TestCase):
    """Local current-contract checkpoints; no complete Task lifecycle."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        for relative in (
                ".cambium/state", ".cambium/tmp", ".cambium/receipts",
                "Notes"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        (self.root / PAGE).write_text(PAGE_TEXT, encoding="utf-8")
        self.coverage = {
            "schema_version": 1,
            "pages": [{"path": PAGE}],
        }
        self.coverage_path = self.root / \
            ".cambium/state/coverage_ledger.yaml"
        self.coverage_path.write_text(
            kblib.canonical_yaml(self.coverage), encoding="utf-8")
        rules = metadata_contract.AuthorizedProjectionRules(
            (property_state.gate_projection_rule(
                "readiness_state", ("accepted",)),),
            "sha256:" + "8" * 64,
            "sha256:" + "2" * 64)
        page = kblib.repository_target_snapshot(
            self.root, PAGE, suffixes=".md", singly_linked=True)
        self.context = replace(
            _context(self.root, page_snapshot=page),
            rules=rules,
            semantic_content_fingerprint=
                page_state.semantic_content_fingerprint(
                    PAGE, page.read_text(), rules))
        self.context.runtime.update({
            "root": str(self.root),
            "errors": [],
            "_writer_locks": [],
            "coverage": copy.deepcopy(self.coverage),
            "coverage_sha256": kblib.sha256_file(self.coverage_path),
            "queue_sha256": "sha256:" + "5" * 64,
            "progress_sha256": "sha256:" + "6" * 64,
            "receipt_catalog": {},
        })
        self.receipt = _manual_receipt(self.context)
        self.context.runtime["current_receipt_catalog"] = {
            self.receipt["receipt_id"]: (
                ".cambium/receipts/gate-attestations.jsonl", self.receipt),
        }

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
            "checked_at": "2026-08-31T00:00:00Z",
            "seq": 1,
            "invalidated_by": None,
            "scan_id": scan_id,
        }

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
        context = replace(self.context, gate=_gate("deterministic"))
        profile_view = dict(context.profile_view)
        profile_view["_contract"] = SimpleNamespace(
            registered_scans=(scan,))
        authority = dict(context.authority, profile_view=profile_view)
        return replace(context, authority=authority), scan

    def _scan_command_patch(self, scan):
        return mock.patch.object(
            gate_runtime.profile_contract,
            "compile_registered_scan_command",
            return_value=(
                sys.executable,
                str(self.root / scan.script_repo_path),
                str(self.root),
            ))

    def test_registered_scan_produces_one_bound_gate_receipt(self):
        context, scan = self._deterministic_context()
        source = self._scan_receipt()

        def run(command, **_kwargs):
            output = Path(command[command.index("--receipts") + 1])
            output.write_bytes(kblib.canonical_json_bytes(source) + b"\n")
            return __import__("subprocess").CompletedProcess(
                command, 0, stdout="scan passed\n")

        with self._scan_command_patch(scan), mock.patch.object(
                scan_producer.subprocess, "run", side_effect=run):
            result = scan_producer.run_registered_gate_scan(context)
            receipt = scan_producer.build_gate_result_receipt(context, result)
            self.assertIs(
                receipt,
                gate_runtime.validate_gate_receipt(
                    context, receipt, "accepted"))

            tampered = copy.deepcopy(receipt)
            tampered["registered_scan_receipt"]["result"] = "candidate"
            with self.assertRaisesRegex(ValueError, "hash is invalid"):
                gate_runtime.validate_gate_receipt(
                    context, tampered, "accepted",
                    require_current_repository=False)

    def _dynamic_runtime(self, *_args, **_kwargs):
        runtime = dict(self.context.runtime)
        runtime["coverage"] = kblib.load_yaml_file(self.coverage_path)
        runtime["coverage_sha256"] = kblib.sha256_file(self.coverage_path)
        runtime["errors"] = []
        return runtime

    def _run_apply(self, append=None):
        arguments = [
            str(self.root), "--gate-id", self.context.gate.gate_id,
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
                transition_writer.metadata_gate_runtime,
                "load_gate_context", return_value=self.context),
            mock.patch.object(
                transition_writer.runtime_validation, "validate_runtime",
                side_effect=self._dynamic_runtime),
            mock.patch.object(
                transition_writer.queue_runtime, "runtime_authority_context",
                return_value=self.context.authority),
            mock.patch.object(
                transition_writer.queue_runtime,
                "runtime_authority_validation_kwargs", return_value={}),
            mock.patch.object(
                transition_writer.queue_runtime,
                "runtime_authority_lock_fields", return_value={}),
            mock.patch.object(
                transition_writer.queue_runtime,
                "require_runtime_authority_current", return_value=None),
            mock.patch.object(
                transition_writer.metadata_gate_runtime,
                "require_context_current", return_value=None),
            mock.patch.object(
                transition_writer.metadata_gate_runtime,
                "require_authorities_current", return_value=None),
        ]
        if append is not None:
            patches.append(mock.patch.object(
                transition_writer.kblib,
                "write_receipts_observed", side_effect=append))
        stdout, stderr = io.StringIO(), io.StringIO()
        with ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            code = transition_writer.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_transition_atomically_updates_owner_and_page(self):
        code, stdout, stderr = self._run_apply()

        self.assertEqual(0, code, stdout + stderr)
        state = kblib.load_yaml_file(self.coverage_path)["pages"][0][
            "property_state"]["readiness_state"]
        self.assertEqual("accepted", state["value"])
        self.assertEqual(self.receipt["receipt_id"],
                         state["evidence_receipt"])
        self.assertIn(
            "readiness_state: accepted",
            (self.root / PAGE).read_text(encoding="utf-8"))
        self.assertFalse((
            self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_transition_receipt_failure_rolls_back_owner_and_page(self):
        before_coverage = self.coverage_path.read_bytes()
        before_page = (self.root / PAGE).read_bytes()

        def fail_append(*_args, **_kwargs):
            return "absent", OSError("injected append failure"), {}

        code, stdout, stderr = self._run_apply(fail_append)

        self.assertEqual(1, code, stdout + stderr)
        self.assertEqual(before_coverage, self.coverage_path.read_bytes())
        self.assertEqual(before_page, (self.root / PAGE).read_bytes())
        self.assertFalse((
            self.root / ".cambium/tmp/state-writer.lock").exists())


if __name__ == "__main__":
    unittest.main()
