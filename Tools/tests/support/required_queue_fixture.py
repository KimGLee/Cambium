"""Shared fixture and scenario templates for current Queue lifecycles."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


TESTS = Path(__file__).resolve().parents[1]
TOOLS = TESTS.parent
REPOSITORY = TOOLS.parent
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))
import Tools.platform.distribution.module_boundary_facts as module_boundary_facts  # noqa: E402

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
import Tools.execution.audit.check_batch_close as check_batch_close
import Tools.execution.audit.batch_close_contract as batch_close_contract
import Tools.execution.audit.changed_scope_evidence_contract as changed_scope_evidence_contract
import Tools.execution.task_runtime.batch_settlement as batch_settlement
import Tools.execution.evidence.candidate_lifecycle as candidate_lifecycle
import Tools.knowledge.metadata.compose_page_contract as compose_page_contract
import Tools.knowledge.metadata.compose_vocab as compose_vocab
import Tools.platform.common.kblib as kblib
import Tools.knowledge.content.maintenance_candidates as maintenance_candidates
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.knowledge.metadata.metadata_property_state as metadata_property_state
import Tools.governance.profile.profile_admission as profile_admission
import Tools.knowledge.metadata.project_page_state as project_page_state
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.record_maintenance_evidence as record_maintenance_evidence
import Tools.platform.distribution.stamp_cards as stamp_cards
import Tools.governance.standards.standards_state as standards_state
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION, install_loadable_profile
from Tools.tests.support.initial_task_plan_fixture import (  # noqa: E402
    install_initial_task_plan_fixture,
)
from Tools.tests.support.coverage_delta_fixture import write_premerge_delta
from Tools.tests.fixtures.integration.checkpoint_contract import (
    copy_checkpoint_seed,
)


# ---------------------------------------------------------------------------
# Scenario templates.
#
# Most tests here walk one of a handful of identical prologues -- open B1,
# or merge-and-apply it, or close both Required batches, or convert the
# fixture to maintenance semantics and close everything -- and then assert
# one property of the result.  Each distinct prologue is walked exactly once
# per process into a template tree below.  Tests that only read the walked
# state share the template directly; tests that mutate any byte start from a
# private `shutil.copytree` copy of it.  The tools take the repository root
# from argv, so a copied root behaves identically; walk outputs the tests
# assert on (resume envelopes, refusal exits, receipt ids) ride along as
# recorded artifacts.
# ---------------------------------------------------------------------------


def install_terminal_proof_dependencies(root):
    """Reconstruct non-Profile dependencies of a terminal checkpoint."""
    root = Path(root)
    shutil.copytree(REPOSITORY / "kernel", root / "kernel", dirs_exist_ok=True)
    tools_root = root / "Tools"
    (tools_root / "schemas").mkdir(parents=True, exist_ok=True)
    module_boundary_facts.stage_shipped_modules(
        str(TOOLS.parent), str(root),
        ["check_profile", "check_residual_content", "check_queue"])
    shutil.copy2(
        TOOLS / "schemas/execution_defaults.template.yaml",
        tools_root / "schemas/execution_defaults.template.yaml")


def install_terminal_checkpoint_dependencies(root):
    """Rebuild the complete non-runtime tree of a terminal checkpoint."""
    install_loadable_profile(root)
    install_terminal_proof_dependencies(root)


class RequiredQueueFixture:
    """The fixture language every scenario class below shares.

    This is the original test class's helper set, unchanged; only the
    per-test tree construction moved out, into the template registry.
    """

    def build_repository_fixture(self):
        """Lay down the fixture tree the original per-test setUp built."""
        copy_checkpoint_seed(FIXTURE, self.root)
        install_loadable_profile(self.root)
        for name in ("deltas", "receipts", "reports"):
            (self.root / ".cambium" / name).mkdir(exist_ok=True)
        self.install_plain_s_audit_fixture()

    def install_plain_s_audit_fixture(self):
        """Make the shared lifecycle fixture a real, bounded S-tier run.

        These tests exercise Queue and close mechanics rather than M-tier
        semantic judgment.  The fixture therefore uses plain Markdown pages
        that satisfy the selected Profile's page contract, and the Kernel's
        real deterministic sampling rule supplies their review obligation.
        No production obligation is bypassed or replaced by fixture prose.
        """
        pages = (("A", "B1"), ("B", "B2"))
        for name, _batch in pages:
            (self.root / ("Topics/%s.md" % name)).write_text(
                "---\n"
                "type: concept\n"
                "domain: general\n"
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
        progress_path = self.root / queue_runtime.PROGRESS_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        for page in coverage["pages"]:
            page["tier"] = "S"
            page["priority"] = "P2"
        coverage_path.write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")

        progress = kblib.load_yaml_file(progress_path)
        progress["checkpoint"]["coverage_sha256"] = \
            kblib.sha256_file(coverage_path)
        progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")

        install_initial_task_plan_fixture(self.root)

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
        self.assertEqual(
            [], runtime_validation.validate_runtime(self.root)["errors"])

    def run_tool(self, name, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS / name), str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )


    def assert_resume_envelope(self, completed, next_action, root=None):
        """Assert the one-command restart contract, not only its action token.

        ``root`` names the tree the resume call actually read: this test's
        own tree by default, or a frozen template root when the call was
        recorded during a scenario walk.
        """
        output = completed.stdout
        result = runtime_validation.validate_runtime(
            self.root if root is None else root)
        for expected in (
                "task_id=fixture-task",
                'objective="Complete fixture Required Queue batches with durable evidence."',
                'exclusions=["Do not modify profile policy."]',
                "live.coverage_sha256=%s" % result.get("coverage_sha256"),
                "live.progress_sha256=%s" % result.get("progress_sha256"),
                "live.required_queue_sha256=%s" % result.get("queue_sha256"),
                "checkpoint.recorded_at=",
                "checkpoint.summary=",
                "checkpoint.binding=",
        ):
            self.assertIn(expected, output)
        self.assertTrue(any(
            line.startswith("  deltas=") or line.startswith("  delta=")
            for line in output.splitlines()), output)
        self.assertTrue(any(
            line.startswith("  locks=") or line.startswith("  lock=")
            for line in output.splitlines()), output)
        actions = [line for line in output.splitlines()
                   if line.startswith("next_action=")]
        self.assertEqual(["next_action=%s" % next_action], actions, output)

    def queue(self):
        return kblib.load_yaml_file(self.root / queue_runtime.QUEUE_PATH)

    def ready_receipt(self, batch_id):
        relative = ".cambium/receipts/ready-%s.jsonl" % batch_id
        result = self.run_tool(
            "check_queue.py", "--require-ready", batch_id,
            "--receipts", relative,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        record = json.loads((self.root / relative).read_text(
            encoding="utf-8").splitlines()[-1])
        return record["receipt_id"]

    def close_gate_receipt(self, batch_id, consistency_receipt):
        queue = self.queue()
        item = next(entry for entry in queue["required_queue"]
                    if entry["id"] == batch_id)
        revision = queue["state_revision"]
        runtime = runtime_validation.validate_runtime(self.root)
        settlement = batch_settlement.current_settlement_report(
            runtime["coverage"], batch_id)
        self.assertEqual([], settlement["errors"], settlement["errors"])
        baseline_errors, baseline = check_batch_close._candidate_baseline(
            str(self.root), runtime, batch_id)
        self.assertEqual([], baseline_errors, baseline_errors)
        applied = next(
            entry for entry in runtime["applied_delta_receipts"]
            if entry.get("batch") == batch_id)
        delta_apply_receipt = applied["selected_receipt"]
        delta_apply_record = queue_runtime.current_receipt_catalog(runtime)[
            delta_apply_receipt][1]
        review_checked_at = delta_apply_record["checked_at"]
        merged_snapshot_sha256 = kblib.repository_snapshot_sha256(self.root)
        evidence = {}
        records = []
        integrator_id = "fixture-integrator"
        reviewer_id = "fixture-reviewer"
        for field in batch_close_contract.CLOSED_LIST_EVIDENCE_FIELDS:
            receipt_id = "audit-e2e-closed-list-%s-r%d-%s" % (
                batch_id, revision, field)
            records.append({
                "receipt_id": receipt_id,
                "tool": "check_batch_close",
                "tool_version": queue_runtime.BATCH_CLOSE_TOOL_VERSION,
                "check": "closed_list_%s" % field,
                "target": ".",
                "batch_id": batch_id,
                "task_id": queue["task_id"],
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "result": "pass",
                "invalidated_by": None,
                "merged_snapshot_sha256": merged_snapshot_sha256,
                "candidate_evidence": [],
            })
            evidence[field] = receipt_id
        attestation_id = "audit-e2e-review-attestation-%s-r%d" % (
            batch_id, revision)
        evidence_relative = "%s/%s-r%d-fixture.jsonl" % (
            kblib.RECEIPT_COLD_EVIDENCE_PREFIX, batch_id, revision)
        evidence_file = self.root / evidence_relative
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        if not evidence_file.exists():
            evidence_file.write_bytes(b"")
        records.append({
            "receipt_id": attestation_id,
            "tool": "check_batch_close",
            "tool_version": queue_runtime.BATCH_CLOSE_TOOL_VERSION,
            "check": "batch_global_review_attestation",
            "target": batch_id,
            "batch_id": batch_id,
            "task_id": queue["task_id"],
            "integrator_id": integrator_id,
            "reviewer_id": reviewer_id,
            "result": "pass",
            "invalidated_by": None,
            "checked_at": "2026-08-04T02:30:00Z",
            "details": "fixture independent review attestation",
            "merged_snapshot_sha256": merged_snapshot_sha256,
            "accepted_candidate_count": 0,
            "accepted_candidate_types": [],
            "accepted_by_type_counts": {},
            "candidate_set_sha256": kblib.sha256_bytes(b""),
            "candidate_protocol": candidate_lifecycle.CANDIDATE_PROTOCOL,
            "candidate_baseline_protocol": baseline["protocol"],
            "candidate_baseline_receipt": baseline["attestation_receipt"],
            "carried_candidate_count": 0,
            "carried_candidate_set_sha256":
                candidate_lifecycle.candidate_set_sha256([]),
            "fresh_candidate_count": 0,
            "fresh_candidate_set_sha256":
                candidate_lifecycle.candidate_set_sha256([]),
            "candidate_evidence_path": evidence_relative,
            "candidate_evidence_sha256": kblib.sha256_bytes(b""),
            "candidate_evidence_bytes": 0,
            "candidate_evidence_records": 0,
            "candidate_dispositions": [],
        })
        metadata_contract = \
            metadata_execution_contract.load_metadata_execution_contract(
                self.root)
        profile_view = runtime["_profile_authorized_view"]
        projection_rules = \
            metadata_property_state.profile_gate_projection_rules(
                self.root, profile_view["_contract"].extension_gates,
                metadata_contract=metadata_contract,
                authorized_profile_contract=profile_view["_contract"])
        profile_bindings = {
            field: profile_view[field]
            for field in (
                "selected_profile_manifest", "profile_snapshot_sha256",
                "profile_contract_fingerprint", "profile_load_inputs_sha256",
            )
        }
        page_review_ids = []
        for index, relative in enumerate(sorted(item["manifest"])):
            page_review_id = "audit-e2e-page-review-%s-r%d-%d" % (
                batch_id, revision, index)
            page = kblib.repository_target_snapshot(
                self.root, relative, suffixes=".md", singly_linked=True)
            self.assertTrue(page.exists)
            records.append({
                "receipt_id": page_review_id,
                "tool": "check_batch_close",
                "tool_version": queue_runtime.BATCH_CLOSE_TOOL_VERSION,
                "check": "page_review_acceptance",
                "target": relative,
                "batch_id": batch_id,
                "task_id": queue["task_id"],
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "result": "pass",
                "invalidated_by": None,
                "checked_at": review_checked_at,
                "reviewed_on": review_checked_at[:10],
                "semantic_content_sha256":
                    project_page_state.semantic_content_fingerprint(
                        relative, page.read_text(), projection_rules),
                "metadata_execution_contract_fingerprint":
                    metadata_contract.contract_fingerprint,
                "merged_snapshot_sha256": merged_snapshot_sha256,
                "reviewer_attestation_receipt": attestation_id,
                **profile_bindings,
            })
            page_review_ids.append(page_review_id)
        page_review_ids.sort()
        global_review_id = "audit-e2e-global-review-%s-r%d" % (
            batch_id, revision)
        records.append({
            "receipt_id": global_review_id,
            "tool": "check_batch_close",
            "tool_version": queue_runtime.BATCH_CLOSE_TOOL_VERSION,
            "check": "batch_global_review",
            "target": batch_id,
            "batch_id": batch_id,
            "task_id": queue["task_id"],
            "integrator_id": integrator_id,
            "reviewer_id": reviewer_id,
            "result": "pass",
            "invalidated_by": None,
            "merged_snapshot_sha256": merged_snapshot_sha256,
            "reviewer_attestation_receipt": attestation_id,
            "closed_list_evidence": evidence,
        })
        close_id = "audit-e2e-batch-close-%s-r%d" % (batch_id, revision)
        records.append({
            "receipt_id": close_id,
            "tool": "check_batch_close",
            "tool_version": queue_runtime.BATCH_CLOSE_TOOL_VERSION,
            "check": "batch_close_gate",
            "target": batch_id,
            "batch_id": batch_id,
            "task_id": queue["task_id"],
            "integrator_id": integrator_id,
            "reviewer_id": reviewer_id,
            "result": "pass",
            "invalidated_by": None,
            "checked_at": "2026-08-04T02:30:00Z",
            "queue_revision": queue["queue_revision"],
            "queue_state_revision": queue["state_revision"],
            "required_queue_sha256": kblib.sha256_file(
                self.root / queue_runtime.QUEUE_PATH),
            "coverage_ledger_sha256": kblib.sha256_file(
                self.root / queue_runtime.COVERAGE_PATH),
            "progress_ledger_sha256": kblib.sha256_file(
                self.root / queue_runtime.PROGRESS_PATH),
            "delta_sha256": item["delta_sha256"],
            "delta_apply_receipt": delta_apply_receipt,
            "queue_consistency_receipt": consistency_receipt,
            "corpus_plan_required": False,
            "corpus_plan_triggers": [],
            "corpus_plan_receipt": None,
            "work_spec_path": item["work_spec_path"],
            "work_spec_sha256": item["work_spec_sha256"],
            "merged_snapshot_sha256": merged_snapshot_sha256,
            "reviewer_attestation_receipt": attestation_id,
            "global_review_receipt": global_review_id,
            "closed_list_evidence": evidence,
            "page_review_receipts": page_review_ids,
            "page_review_receipt_count": len(page_review_ids),
            "page_review_receipt_set_sha256":
                candidate_lifecycle.candidate_set_sha256(page_review_ids),
            "metadata_execution_contract_fingerprint":
                metadata_contract.contract_fingerprint,
            **profile_bindings,
        } | batch_settlement.close_binding(settlement))
        kblib.write_receipts(
            self.root / ".cambium/receipts/close-gates.jsonl", records)
        return close_id

    def transition(self, batch_id, transition, *evidence):
        queue = self.queue()
        result = self.run_tool(
            "update_queue.py", "--id", batch_id,
            "--transition", transition,
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / queue_runtime.QUEUE_PATH),
            "--actor-role", "integrator", "--apply", *evidence,
        )
        self.assertEqual(0, result.returncode, result.stdout)

    def task_transition(self, transition, *evidence):
        result = self.run_tool(
            "update_task.py", "--transition", transition,
            "--expected-progress-sha256",
            kblib.sha256_file(self.root / queue_runtime.PROGRESS_PATH),
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / queue_runtime.QUEUE_PATH),
            "--actor-role", "integrator", "--apply", *evidence,
        )
        self.assertEqual(0, result.returncode, result.stdout)

    def use_maintenance_completion(self):
        progress_path = self.root / queue_runtime.PROGRESS_PATH
        progress = kblib.load_yaml_file(progress_path)
        progress["contract"]["completion_semantics"] = "maintenance"
        progress["contract"]["completion_gate"] = (
            "maintenance budget manifest closed AND ledger advanced AND "
            "watermark advanced AND remaining_required_work_units=0 AND "
            "all applicable batch gates persisted"
        )
        progress["terminal_audit"] = {
            "state": "not-applicable",
            "terminal_proof_path": None,
            "terminal_proof_sha256": None,
            "terminal_proof_receipt": None,
            "queue_check_receipt": None,
        }
        progress["maintenance_completion"] = {
            "state": "pending",
            "completion_gate_receipt": None,
            "budget_manifest_receipt": None,
            "ledger_advance_receipt": None,
            "watermark_advance_receipt": None,
        }
        progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        coverage_path = self.root / queue_runtime.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        candidates = []
        for page in coverage["pages"]:
            path = page["path"]
            candidates.append({
                "candidate_id":
                    maintenance_candidates.candidate_id_for_path(path),
                "object_path": path,
                "source_kinds": ["freshness"],
                "priority": page["priority"],
                "previous_deferred_runs": 0,
                "consecutive_deferred_runs": 0,
                "reentered_after_terminal": False,
                "selection": "selected",
                "disposition": None,
                "disposition_reason": None,
            })
        coverage["maintenance_candidates"] = candidates
        coverage_path.write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        coverage_sha = kblib.sha256_file(coverage_path)
        receipt_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        receipts = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()]
        for receipt in receipts:
            if receipt.get("receipt_id") == "audit-fixture-initial-queue":
                receipt["contract_sha256"] = \
                    queue_runtime.contract_sha256(progress)
                receipt["before_coverage_sha256"] = coverage_sha
                receipt["after_coverage_sha256"] = coverage_sha
        receipt_path.write_text(
            "".join(json.dumps(receipt) + "\n" for receipt in receipts),
            encoding="utf-8",
        )
        self.assertEqual([], runtime_validation.validate_runtime(self.root)["errors"])

    def write_maintenance_evidence(self):
        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        queue = result["queue"]
        contract = result["progress"]["contract"]
        identity = {
            "task_id": queue["task_id"],
            "scope_version": contract["scope_version"],
            "upstream_revision_id": contract["upstream_revision_id"],
            "selected_profile_manifest":
                contract["selected_profile_manifest"],
        }

        budget_path = ".cambium/receipts/maintenance-budget.yaml"
        closed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        candidates = result["coverage"]["maintenance_candidates"]
        candidate_errors, candidate_context = \
            maintenance_candidates.validate_candidates(
                self.root, candidates, validate_prior=False)
        self.assertEqual([], candidate_errors)
        selected_objects = candidate_context["selected_objects"]
        run_id = "fixture-maintenance-run-1"
        required_batch_ids = [
            item["id"] for item in sorted(
                queue["required_queue"], key=lambda value: value["order"])
        ]
        budget = dict(identity)
        budget.update({
            "schema_version": 3,
            "run_id": run_id,
            "previous_maintenance_completion_receipt": None,
            "budget_unit": "pages",
            "budget_limit": len(selected_objects),
            "consumed_hours": None,
            "candidates": candidates,
            "selected_candidate_ids": candidate_context["selected_ids"],
            "deferred_candidate_ids": candidate_context["deferred_ids"],
            "selected_objects": selected_objects,
            "required_batch_ids": required_batch_ids,
            "deferred_count": 0,
            "open_items": 0,
            "state": "closed",
            "closed_at": closed_at,
        })
        (self.root / budget_path).write_text(
            kblib.canonical_yaml(budget), encoding="utf-8")
        watermark_path = runtime_paths.WATERMARK_PATH
        (self.root / ".cambium/state").mkdir(parents=True, exist_ok=True)
        watermark = {
            "updated_at": closed_at,
            "last_run_id": run_id,
            "last_batch_id": required_batch_ids[-1],
        }
        (self.root / watermark_path).write_text(
            kblib.canonical_yaml(watermark), encoding="utf-8")
        records = record_maintenance_evidence.build_receipts(
            str(self.root), runtime_validation.validate_runtime(self.root),
            budget_path, "sha256:" + "0" * 64,
            "sha256:" + "1" * 64,
        )
        kblib.write_receipts(
            self.root / record_maintenance_evidence.DEFAULT_RECEIPTS,
            records,
        )
        return tuple(receipt["receipt_id"] for receipt in records)

    def rebind_maintenance_budget_receipt(self, budget_receipt_id):
        evidence_path = \
            self.root / ".cambium/receipts/maintenance-evidence.jsonl"
        budget_path = self.root / ".cambium/receipts/maintenance-budget.yaml"
        receipts = [json.loads(line) for line in evidence_path.read_text(
            encoding="utf-8").splitlines()]
        receipt = next(value for value in receipts
                       if value["receipt_id"] == budget_receipt_id)
        receipt["budget_manifest_sha256"] = kblib.sha256_file(budget_path)
        evidence_path.write_text(
            "".join(json.dumps(value) + "\n" for value in receipts),
            encoding="utf-8",
        )

    def write_delta(self, batch_id, object_path, receipt_id):
        relative = ".cambium/deltas/%s.yaml" % batch_id
        return write_premerge_delta(
            self.root, relative, batch_id, object_path, [receipt_id],
            generated_at="2026-08-04T00:00:00Z")

    def prepare_premerge_audit_evidence(self, batch_id):
        """Prepare and discharge the real pre-merge AuditPlan closure."""
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
        """Publish the production wrapper over the complete pre-merge plan."""
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

    def install_terminal_proof_environment(self):
        install_terminal_proof_dependencies(self.root)

        manifest = "profiles/test-profile/profile.md"
        active_path = self.root / standards_state.STATE_PATH
        active, _view, errors = standards_state.snapshot(self.root)
        self.assertEqual([], errors)
        active = dict(active)
        active["selected_profile_manifest"] = manifest
        active_path.write_text(
            standards_state.canonical_text(active), encoding="utf-8")

        coverage_path = self.root / queue_runtime.COVERAGE_PATH
        queue_path = self.root / queue_runtime.QUEUE_PATH
        progress_path = self.root / queue_runtime.PROGRESS_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        queue = kblib.load_yaml_file(queue_path)
        progress = kblib.load_yaml_file(progress_path)
        coverage["selected_profile_manifest"] = manifest
        queue["selected_profile_manifest"] = manifest
        progress["contract"]["selected_profile_manifest"] = manifest
        selected_route_ids = ["R01", "R03", "R08", "R12"]
        cards, _read_sets = stamp_cards.discover_cards(self.root)
        progress["contract"].update({
            "selected_route_ids": selected_route_ids,
            "selected_card_paths": sorted(
                cards[route_id]["path"] for route_id in selected_route_ids),
            "selected_profile_route_ids": [],
            "selected_read_sets": [],
            "loaded_module_paths": [
                "kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md",
            ],
        })
        coverage_path.write_text(kblib.canonical_yaml(coverage), encoding="utf-8")
        queue_text = kblib.canonical_yaml(queue)
        queue_path.write_text(queue_text, encoding="utf-8")
        queue_sha = kblib.sha256_bytes(queue_text)
        coverage_sha = kblib.sha256_file(coverage_path)
        progress["required_queue_sha256"] = queue_sha
        progress["checkpoint"]["required_queue_sha256"] = queue_sha
        progress["checkpoint"]["coverage_sha256"] = coverage_sha
        progress_path.write_text(kblib.canonical_yaml(progress), encoding="utf-8")

        receipt_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        receipts = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()]
        for receipt in receipts:
            if receipt.get("receipt_id") == "audit-fixture-initial-queue":
                receipt["after_required_queue_sha256"] = queue_sha
                receipt["after_coverage_sha256"] = coverage_sha
                receipt["contract_sha256"] = \
                    queue_runtime.contract_sha256(progress)
        receipt_path.write_text("".join(json.dumps(receipt) + "\n"
                                        for receipt in receipts),
                                encoding="utf-8")
        self.assertEqual([], runtime_validation.validate_runtime(self.root)["errors"])

    def merge_and_apply(self, batch_id, object_path):
        ready = self.ready_receipt(batch_id)
        self.transition(batch_id, "open", "--gate-receipt", ready)
        _plan_path, page_receipt_id = \
            self.prepare_premerge_audit_evidence(batch_id)
        delta = self.write_delta(
            batch_id, object_path, page_receipt_id)
        batch_receipt = self.record_batch_review_wrapper(batch_id)
        self.transition(
            batch_id, "merge-ready", "--delta-path", delta,
            "--batch-receipt", batch_receipt,
        )

        coverage_path = self.root / queue_runtime.COVERAGE_PATH
        queue_path = self.root / queue_runtime.QUEUE_PATH
        applied = subprocess.run(
            [
                sys.executable, str(TOOLS / "apply_delta.py"),
                delta, "--root", str(self.root),
                "--expected-coverage-sha256",
                kblib.sha256_file(coverage_path),
                "--expected-queue-sha256", kblib.sha256_file(queue_path),
                "--actor-role", "integrator",
                "--receipts",
                ".cambium/receipts/delta-%s.jsonl" % batch_id,
                "--apply",
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, applied.returncode, applied.stdout)
        delta_apply_receipt = json.loads(
            (self.root / (".cambium/receipts/delta-%s.jsonl" % batch_id))
            .read_text(encoding="utf-8").splitlines()[-1]
        )["receipt_id"]

        closed = self.run_tool(
            "check_batch_close.py", "--batch", batch_id,
            "--integrator", "fixture-integrator",
            "--reviewer", "fixture-reviewer",
            "--review-attestation",
            "fixture reviewer independently confirms the merged batch",
            "--json",
        )
        self.assertEqual(0, closed.returncode, closed.stdout)
        json_lines = [
            line for line in closed.stdout.splitlines()
            if line.startswith("[{")
        ]
        self.assertEqual(1, len(json_lines), closed.stdout)
        close_rows = json.loads(json_lines[0])
        close_gate_rows = [
            receipt for receipt in close_rows
            if receipt.get("check") == "batch_close_gate"
        ]
        self.assertEqual(1, len(close_gate_rows), close_rows)
        close_receipt = close_gate_rows[0]["queue_consistency_receipt"]
        close_gate = close_gate_rows[0]["receipt_id"]
        return delta_apply_receipt, close_receipt, close_gate

    def merge_and_close(self, batch_id, object_path):
        delta_apply_receipt, close_receipt, close_gate = self.merge_and_apply(
            batch_id, object_path)
        self.transition(
            batch_id, "closed", "--gate-receipt", close_receipt,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
        )


class _ScenarioWalker(RequiredQueueFixture, unittest.TestCase):
    """Assertion-capable driver that walks a template scenario once.

    It defines no test methods, so discovery collects nothing from it; it
    exists so a walk can run the same helpers, with the same assertions,
    that each test ran back when it still walked a private tree.
    """

    def _walk(self):
        raise NotImplementedError("never scheduled as a test")

    @classmethod
    def at(cls, root):
        walker = cls("_walk")
        walker.root = root
        return walker


def _build_base(walker, inherited):
    walker.build_repository_fixture()


def _build_b1_open(walker, inherited):
    ready = walker.ready_receipt("B1")
    walker.transition(
        "B1", "open", "--gate-receipt", ready,
        "--at", "2026-08-04T01:00:00Z",
    )
    return {"b1_ready_receipt": ready}


def _build_b1_applied(walker, inherited):
    # The resume probe is recorded before any batch work.  --resume-status
    # reads and reports and writes nothing, so the tree this walk goes on to
    # build is byte-identical to one that never took the probe.
    resume_initial = walker.run_tool("check_queue.py", "--resume-status")
    delta_receipt, consistency_receipt, close_gate = \
        walker.merge_and_apply("B1", "Topics/A.md")
    return {
        "resume_initial": resume_initial,
        "b1_delta_apply_receipt": delta_receipt,
        "b1_queue_consistency_receipt": consistency_receipt,
        "b1_close_gate_receipt": close_gate,
    }


def _build_closed_b1(walker, inherited):
    walker.transition(
        "B1", "closed",
        "--gate-receipt", inherited["b1_queue_consistency_receipt"],
        "--close-gate-receipt", inherited["b1_close_gate_receipt"],
        "--delta-apply-receipt", inherited["b1_delta_apply_receipt"],
    )
    return {"resume_after_b1":
            walker.run_tool("check_queue.py", "--resume-status")}


def _build_closed_both(walker, inherited):
    walker.merge_and_close("B2", "Topics/B.md")


def _build_maintenance_base(walker, inherited):
    walker.use_maintenance_completion()
    # Three refusal probes, recorded as walk artifacts.  Each refuses before
    # writing -- no receipts flag, no state change -- so the tree the
    # maintenance-closed walk inherits is byte-identical to one that never
    # ran them; the probe for that claim is every downstream close and gate
    # in this chain still passing.
    wrong_gate = walker.run_tool("check_queue.py", "--require-complete")
    candidate = walker.run_tool(
        "update_task.py", "--transition", "completion-candidate",
        "--queue-check-receipt", "not-a-gate",
        "--checkpoint-summary", "must not enter build candidate",
        "--expected-progress-sha256",
        kblib.sha256_file(walker.root / queue_runtime.PROGRESS_PATH),
        "--expected-queue-sha256",
        kblib.sha256_file(walker.root / queue_runtime.QUEUE_PATH),
        "--actor-role", "integrator", "--apply",
    )
    early = walker.run_tool(
        "check_queue.py", "--require-maintenance-complete",
        "--budget-manifest-receipt", "missing-budget",
        "--ledger-advance-receipt", "missing-ledger",
        "--watermark-advance-receipt", "missing-watermark",
    )
    return {
        "maintenance_wrong_gate": wrong_gate,
        "maintenance_candidate_refusal": candidate,
        "maintenance_early_gate": early,
    }


def _build_maintenance_closed(walker, inherited):
    walker.merge_and_close("B1", "Topics/A.md")
    walker.merge_and_close("B2", "Topics/B.md")
    budget_id, ledger_id, watermark_id = walker.write_maintenance_evidence()
    return {
        "budget_receipt": budget_id,
        "ledger_receipt": ledger_id,
        "watermark_receipt": watermark_id,
    }


_TEMPLATE_PARENTS = {
    "base": None,
    "b1-open": "base",
    "b1-applied": "base",
    "closed-b1": "b1-applied",
    "closed-both": "closed-b1",
    "maintenance-base": "base",
    "maintenance-closed": "maintenance-base",
}
_TEMPLATE_BUILDERS = {
    "base": _build_base,
    "b1-open": _build_b1_open,
    "b1-applied": _build_b1_applied,
    "closed-b1": _build_closed_b1,
    "closed-both": _build_closed_both,
    "maintenance-base": _build_maintenance_base,
    "maintenance-closed": _build_maintenance_closed,
}
# name -> (TemporaryDirectory holder, template root, artifacts).  The holder
# reference keeps each template alive for the whole process; TemporaryDirectory
# finalizers remove the trees at interpreter exit.
_TEMPLATES = {}


def _template(name):
    """Return (root, artifacts) for ``name``, walking it on first use."""
    if name not in _TEMPLATES:
        holder = tempfile.TemporaryDirectory()
        root = Path(holder.name) / "repo"
        artifacts = {}
        parent = _TEMPLATE_PARENTS[name]
        if parent is not None:
            parent_root, parent_artifacts = _template(parent)
            artifacts.update(parent_artifacts)
            shutil.copytree(parent_root, root)
        walker = _ScenarioWalker.at(root)
        artifacts.update(_TEMPLATE_BUILDERS[name](walker, artifacts) or {})
        _TEMPLATES[name] = (holder, root, artifacts)
    _holder, root, artifacts = _TEMPLATES[name]
    return root, artifacts


class RequiredQueueLifecycleDriver(RequiredQueueFixture, unittest.TestCase):
    """Assertion-capable lifecycle driver with no discoverable test methods."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(_template("base")[0], self.root)

    def tearDown(self):
        self.temporary.cleanup()


__all__ = [
    "RequiredQueueFixture", "RequiredQueueLifecycleDriver",
    "_template",
]
