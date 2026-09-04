"""Shared fixture for the current batch-close producer lifecycle."""

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


TESTS = Path(__file__).resolve().parents[1]
TOOLS = TESTS.parent
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.check_batch_close as check_batch_close
import Tools.execution.audit.changed_scope_evidence_contract as changed_scope_evidence_contract
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
import Tools.knowledge.metadata.compose_page_contract as compose_page_contract
import Tools.knowledge.metadata.compose_vocab as compose_vocab
import Tools.platform.common.kblib as kblib
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.platform.distribution.module_boundary_facts as module_boundary_facts
import Tools.governance.profile.profile_admission as profile_admission
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.tests.support.profile_fixture import (
    install_loadable_profile,
)
from Tools.tests.support.coverage_delta_fixture import write_premerge_delta
from Tools.tests.fixtures.integration.checkpoint_contract import (
    copy_checkpoint_seed,
)


class BatchCloseRuntimeActions:
    """Actions over an already legal current batch-close checkpoint."""

    def run_tool(self, name, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS / name), str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def queue(self):
        return kblib.load_yaml_file(self.root / queue_runtime.QUEUE_PATH)

    def transition(self, transition, *evidence):
        queue = self.queue()
        completed = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", transition,
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / queue_runtime.QUEUE_PATH),
            "--actor-role", "integrator", "--apply", *evidence,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)

    def batch_close(self, *extra):
        return self.run_tool(
            "check_batch_close.py", "--batch", "B1",
            "--integrator", "fixture-integrator",
            "--reviewer", "fixture-reviewer",
            "--review-attestation",
            "I reviewed the exact listed candidates and merged snapshot.",
            *extra,
        )

    def close_validation_kwargs(self, runtime, consistency):
        item = runtime["items_by_id"]["B1"]
        view = runtime["_profile_authorized_view"]
        contract = metadata_execution_contract.\
            load_metadata_execution_contract(self.root)
        return {
            "item_id": "B1",
            "root": self.root,
            "task_id": runtime["queue"]["task_id"],
            "queue_revision": runtime["queue"]["queue_revision"],
            "queue_state_revision": runtime["queue"]["state_revision"],
            "required_queue_sha256": runtime["queue_sha256"],
            "coverage_ledger_sha256": runtime["coverage_sha256"],
            "progress_ledger_sha256": runtime["progress_sha256"],
            "delta_sha256": item["delta_sha256"],
            "queue_consistency_receipt": consistency,
            "delta_apply_receipt": self.delta_apply_receipt,
            "work_spec_path": item["work_spec_path"],
            "work_spec_sha256": item["work_spec_sha256"],
            "manifest": item["manifest"],
            "selected_profile_manifest":
                runtime["queue"]["selected_profile_manifest"],
            "profile_snapshot_sha256": view["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                view["profile_contract_fingerprint"],
            "profile_load_inputs_sha256":
                view["profile_load_inputs_sha256"],
            "metadata_execution_contract_fingerprint":
                contract.contract_fingerprint,
            "authorized_profile_contract": view["_contract"],
            "authorized_metadata_contract": contract,
            "current_repository_snapshot_sha256":
                kblib.repository_snapshot_sha256(self.root),
            "historical": False,
        }

    @staticmethod
    def output_value(output, name):
        prefix = name + "="
        return next(line[len(prefix):] for line in output.splitlines()
                    if line.startswith(prefix))


class CheckBatchCloseFixture(BatchCloseRuntimeActions, unittest.TestCase):
    """E2E builder for the one-time batch-close checkpoint prologue."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        self.build_repository_fixture()
        self.prepare_applied_batch()

    def tearDown(self):
        self.temporary.cleanup()

    def build_repository_fixture(self):
        """Lay down the current Profile and repository dependency tree."""
        copy_checkpoint_seed(FIXTURE, self.root)
        for name in ("deltas", "receipts", "reports"):
            (self.root / ".cambium" / name).mkdir(exist_ok=True)
        self.install_profile_and_tools()
        self.install_plain_s_audit_fixture()

    def install_profile_and_tools(self):
        install_loadable_profile(
            self.root,
            before_adoption=self.configure_batch_close_profile,
        )

    def configure_batch_close_profile(self, root, profile):
        """Finalize this scenario's Profile before its single adoption."""
        # The shared Profile fixture owns the complete current form and its
        # directory tree.  This scenario only replaces two existing slot
        # values with the batch-close-specific judgment and scan contracts;
        # it must not recreate the form or retain the retired slots.md bridge.
        audit_registry = profile / "registries/audit-dimensions.md"
        registry = profile / "registries/registered-scans.md"
        for slot in (audit_registry, registry):
            if not slot.is_file():
                raise AssertionError(
                    "shared Profile fixture omitted required slot: %s" %
                    slot.relative_to(self.root))
        audit_registry.write_text(
            "# Audit Dimension Registry\n\n"
            "## Extension Dimensions\n\n"
            "- Registration: None\n\n"
            "| Dimension ID | Target list(s): `review`, `receipt`, or "
            "`review + receipt` | Meaning |\n"
            "|---|---|---|\n\n"
            "## Judgment Items\n\n"
            "| Stable Judgment Item ID | Base or registered receipt "
            "Dimension ID | Exact kernel audit-layer name | Bounded audit "
            "object one run proves | Evidence role: `emits`, `consumes`, "
            "or `triggers` | Predicate owner (repo-relative path; optional "
            "`#heading`) |\n"
            "|---|---|---|---|---|---|\n"
            "| `fixture-item` | `coverage_and_integration` | `Batch Review` "
            "| The fixture scan candidates have accepted dispositions. | "
            "`emits` | `profiles/test-profile/registries/"
            "audit-dimensions.md#Residual Disposition` |\n\n"
            "## Residual Disposition\n\n"
            "The fixture verifier reports residual candidates.\n",
            encoding="utf-8",
        )
        registry.write_text(
            "# Registered Scan Registry\n\n## Scan Registrations\n\n"
            "| Stable Scan ID | Activation role | Whole-corpus scope/root | "
            "Verifier capability ID | Profile configuration reference or "
            "`None` | Candidate predicate/boundary | "
            "Judgment Item ID reference |\n"
            "|---|---|---|---|---|---|---|\n"
            "| `fixture-residuals` | `K12/09 item 6 — residual-content scan` | "
            "Whole repository | `fixture-residual-scan-v1` | `None` | "
            "candidate-only | `fixture-item` |\n",
            encoding="utf-8",
        )
        tools = root / "Tools"
        tools.mkdir(exist_ok=True)
        (tools / "schemas").mkdir(exist_ok=True)
        module_boundary_facts.stage_shipped_modules(
            str(TOOLS.parent), str(self.root), ["platform.common.kblib"])
        (tools / "fixture_residual.py").write_text(
            "#!/usr/bin/env python3\n"
            "import argparse, hashlib, json, os, sys\n"
            "sys.path.insert(0, os.path.dirname(os.path.dirname("
            "os.path.abspath(__file__))))\n"
            "import Tools.platform.common.kblib as kblib\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('root')\n"
            "p.add_argument('--scan-id', required=True)\n"
            "p.add_argument('--receipts')\n"
            "p.add_argument('--positive-controls-only', action='store_true')\n"
            "a=p.parse_args()\n"
            "def classify(text):\n"
            "    return text.startswith('residual:')\n"
            "controls=('residual:alpha','residual:beta')\n"
            "if not all(classify(item) for item in controls):\n"
            "    raise SystemExit(1)\n"
            "control_bytes=json.dumps(controls,separators=(',',':')).encode()\n"
            "control_fp='sha256:' + hashlib.sha256(control_bytes).hexdigest()\n"
            "config_fp='sha256:' + hashlib.sha256(b'fixture-config-v1').hexdigest()\n"
            "r=kblib.make_receipt('fixture_residual','1.0.0',"
            "'residual-content-summary',a.root,'pass',"
            "('fixture controls passed' if a.positive_controls_only else "
            "'fixture production scan passed'),1,"
            "receipt_type_id='registered-residual-scan-receipt-v1',"
            "root=a.root)\n"
            "r['scan_id']=a.scan_id\n"
            "r['config_fingerprint']=config_fp\n"
            "r['positive_control_result']='passed'\n"
            "r['positive_control_mode']='production-classifier'\n"
            "r['positive_control_count']=len(controls)\n"
            "r['positive_control_fingerprint']=control_fp\n"
            "kblib.write_receipts(a.receipts,[r])\n",
            encoding="utf-8",
        )
        if getattr(self, "state_mutating_scan", False):
            script = tools / "fixture_residual.py"
            script.write_text(
                script.read_text(encoding="utf-8") +
                "with open(os.path.join(a.root,'.cambium/state/"
                "coverage_ledger.yaml'),'a',encoding='utf-8') as fh:\n"
                "    fh.write('\\n')\n",
                encoding="utf-8",
            )
        (tools / "scan-capabilities.yaml").write_text(
            "schema_version: 1\n\n"
            "capabilities:\n"
            "  - capability_id: fixture-residual-scan-v1\n"
            "    invocation_contract: profile-registered-scan-v1\n"
            "    implementation_path: Tools/fixture_residual.py\n"
            "    configuration: none\n",
            encoding="utf-8")
        vocab_base = (
            "kernel/K08 Metadata and Status/vocabulary-base.yaml")
        (root / vocab_base).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TOOLS.parent / vocab_base, root / vocab_base)
        vocabulary_path = profile / "vocabulary-extensions.yaml"
        vocabulary = kblib.load_yaml_file(vocabulary_path)
        vocabulary["volatility_defaults"] = {"fixture": "stable"}
        vocabulary_path.write_text(
            kblib.canonical_yaml(vocabulary), encoding="utf-8")
        admission, admission_errors = profile_admission.admit_profile(
            root, profile)
        self.assertEqual([], admission_errors)
        rendered, _vocab, compile_errors = compose_vocab.compiled_artifact(
            root, admission)
        self.assertEqual([], compile_errors)
        vocab_path = root / runtime_paths.VOCAB_ARTIFACT_PATH
        vocab_path.parent.mkdir(parents=True, exist_ok=True)
        vocab_path.write_text(rendered, encoding="utf-8")

    def install_plain_s_audit_fixture(self):
        """Install the bounded page and Profile contracts this suite needs.

        Batch-close scenarios test the post-Delta Closed List rather than
        M-tier semantic judgment.  Plain S pages keep the real pre-merge
        lifecycle small while preserving every production obligation.
        """
        for name in ("A", "B"):
            (self.root / ("Topics/%s.md" % name)).write_text(
                "---\n"
                "type: concept\n"
                "domain: fixture\n"
                "scope: shared\n"
                "level: basic\n"
                "depth: atomic\n"
                "priority: P2\n"
                "---\n"
                "# %s\n\n"
                "## Synthetic Residual\n\n"
                "Accepted-root liveness marker for the registered fixture "
                "scan.\n" % name,
                encoding="utf-8",
            )

        coverage_path = self.root / queue_runtime.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        for page in coverage["pages"]:
            page["tier"] = "S"
            page["priority"] = "P2"
        coverage_path.write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        self.refresh_initial_fixture_origin()
        self.compile_profile_artifacts()
        self.assertEqual(
            [], runtime_validation.validate_runtime(self.root)["errors"])

    def refresh_initial_fixture_origin(self):
        """Rebind the immutable fixture origin after planned-state edits."""
        coverage_path = self.root / queue_runtime.COVERAGE_PATH
        progress_path = self.root / queue_runtime.PROGRESS_PATH
        receipt_path = (
            self.root / ".cambium/receipts/task-transitions.jsonl")
        progress = kblib.load_yaml_file(progress_path)
        progress["checkpoint"]["coverage_sha256"] = \
            kblib.sha256_file(coverage_path)
        progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")

        records = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for record in records:
            if record.get("receipt_id") == "audit-fixture-initial-queue":
                coverage_sha256 = kblib.sha256_file(coverage_path)
                record["before_coverage_sha256"] = coverage_sha256
                record["after_coverage_sha256"] = coverage_sha256
                record["after_progress_sha256"] = \
                    kblib.sha256_file(progress_path)
        receipt_path.write_text(
            "".join(json.dumps(record, separators=(",", ":")) + "\n"
                    for record in records), encoding="utf-8")

    def compile_profile_artifacts(self):
        """Compile both Profile-derived contracts from one admitted view."""
        admission, errors = profile_admission.admit_profile(self.root)
        self.assertEqual([], errors, errors)
        self.assertIsNotNone(admission)
        vocab_text, _vocab, errors = compose_vocab.compiled_artifact(
            self.root, admission)
        self.assertEqual([], errors, errors)
        page_contract_text, _contract, errors = \
            compose_page_contract.compiled_artifact(self.root, admission)
        self.assertEqual([], errors, errors)
        derived = self.root / runtime_paths.DERIVED_ROOT
        derived.mkdir(parents=True, exist_ok=True)
        (derived / "vocab.yaml").write_text(vocab_text, encoding="utf-8")
        (derived / "page_contract.yaml").write_text(
            page_contract_text, encoding="utf-8")

    def prepare_premerge_audit_evidence(self, batch_id):
        """Create the real AuditPlan and discharge its pre-merge closure."""
        prepared = self.run_tool(
            "prepare_audit_plan.py", "--batch", batch_id, "--apply")
        self.assertEqual(0, prepared.returncode, prepared.stdout)
        plan_result = json.loads(prepared.stdout)
        plan_path = plan_result["plan_path"]
        plan = kblib.load_yaml_file(self.root / plan_path)
        sampled_page_receipts = []

        for obligation in plan["obligations"]:
            if (obligation.get("status") != "required" or
                    obligation.get("due_stage") != "pre-merge"):
                continue
            common = (
                "--batch", batch_id,
                "--plan", plan_path,
                "--obligation-id", obligation["obligation_id"],
            )
            if obligation["evidence_kind"] == "batch-page-review-record":
                produced = self.run_tool(
                    "record_batch_page_review.py", *common,
                    "--page", obligation["target"],
                    "--variant", "s-sampled-page",
                    "--reviewer-context-id", "fixture-review-context",
                    "--reviewer-role", "reviewer",
                    "--verdict", "passed",
                    "--statement",
                    "fixture page satisfies the frozen sampled-review "
                    "acceptance contract",
                    "--apply",
                )
                self.assertEqual(0, produced.returncode, produced.stdout)
                evidence = json.loads(produced.stdout)
                sampled_page_receipts.append(evidence["receipt_id"])
                continue

            if obligation["producer_check"] == \
                    "changed_scope_rendering_escalation_record":
                produced = self.run_tool(
                    "record_rendering_verification.py", *common,
                    "--rendering-mode", "source-only", "--apply")
            elif (obligation.get("producer_capability") ==
                  changed_scope_evidence_contract.ADAPTER_CAPABILITY_ID or
                  obligation.get("producer_gate_id") is not None):
                produced = self.run_tool(
                    "record_changed_scope_evidence.py", *common, "--apply")
            else:
                self.fail(
                    "fixture has no producer dispatch for AuditPlan "
                    "obligation %s" % obligation["obligation_id"])
            self.assertEqual(0, produced.returncode, produced.stdout)
            evidence = json.loads(produced.stdout)

            if obligation["evidence_kind"] == "audit-receipt":
                completed = self.run_tool(
                    "complete_audit_receipt.py", *common,
                    "--evidence-receipt", evidence["receipt_id"],
                    "--apply",
                )
                self.assertEqual(0, completed.returncode, completed.stdout)

        self.assertEqual(1, len(sampled_page_receipts), plan)
        return plan_path, sampled_page_receipts[0]

    def record_batch_review_wrapper(self, batch_id):
        """Publish the production wrapper over the pre-merge plan closure."""
        reviewed = self.run_tool(
            "record_batch_review.py", "--batch", batch_id,
            "--actor-role", "integrator",
            "--statement",
            "fixture integrator confirms the complete frozen pre-merge "
            "AuditPlan evidence closure",
            "--apply", "--json",
        )
        self.assertEqual(0, reviewed.returncode, reviewed.stdout)
        receipts = json.loads(reviewed.stdout)
        self.assertEqual(1, len(receipts), receipts)
        return receipts[0]["receipt_id"]

    def prepare_applied_batch(self):
        ready_path = ".cambium/receipts/ready.jsonl"
        ready = self.run_tool(
            "check_queue.py", "--require-ready", "B1",
            "--receipts", ready_path)
        self.assertEqual(0, ready.returncode, ready.stdout)
        ready_id = json.loads((self.root / ready_path).read_text(
            encoding="utf-8"))["receipt_id"]
        self.transition("open", "--gate-receipt", ready_id)
        self.audit_plan_path, page_receipt_id = \
            self.prepare_premerge_audit_evidence("B1")
        delta_relative = ".cambium/deltas/B1.yaml"
        write_premerge_delta(
            self.root, delta_relative, "B1", "Topics/A.md",
            [page_receipt_id], generated_at="2026-08-05T00:00:00Z")
        batch_receipt_id = self.record_batch_review_wrapper("B1")
        self.transition(
            "merge-ready", "--delta-path", delta_relative,
            "--batch-receipt", batch_receipt_id)

        applied_path = ".cambium/receipts/applied.jsonl"
        applied = subprocess.run(
            [
                sys.executable, str(TOOLS / "apply_delta.py"),
                delta_relative,
                "--root", str(self.root),
                "--expected-coverage-sha256",
                kblib.sha256_file(self.root / queue_runtime.COVERAGE_PATH),
                "--expected-queue-sha256",
                kblib.sha256_file(self.root / queue_runtime.QUEUE_PATH),
                "--actor-role", "integrator", "--receipts", applied_path,
                "--apply",
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, applied.returncode, applied.stdout)
        self.delta_apply_receipt = json.loads(
            (self.root / applied_path).read_text(encoding="utf-8"))[
                "receipt_id"]

__all__ = ["BatchCloseRuntimeActions", "CheckBatchCloseFixture"]
