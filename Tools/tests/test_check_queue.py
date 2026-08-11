import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS))

import check_queue
import kblib


class QueueFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def queue_path(self):
        return self.root / check_queue.QUEUE_PATH

    @property
    def progress_path(self):
        return self.root / check_queue.PROGRESS_PATH

    @property
    def coverage_path(self):
        return self.root / check_queue.COVERAGE_PATH

    def queue(self):
        return kblib.load_yaml_file(self.queue_path)

    def write_queue(self, queue, sync_progress=True):
        text = kblib.canonical_yaml(queue)
        self.queue_path.write_text(text, encoding="utf-8")
        if sync_progress:
            progress = kblib.load_yaml_file(self.progress_path)
            progress["queue_revision"] = queue["queue_revision"]
            progress["queue_state_revision"] = queue["state_revision"]
            progress["required_queue_sha256"] = kblib.sha256_bytes(text)
            self.progress_path.write_text(kblib.canonical_yaml(progress),
                                          encoding="utf-8")

    def refresh_initial_origin(self):
        receipt_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        records = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for record in records:
            if record.get("receipt_id") == "audit-fixture-initial-queue":
                record["after_required_queue_sha256"] = kblib.sha256_file(
                    self.queue_path)
                record["after_coverage_sha256"] = kblib.sha256_file(
                    self.coverage_path)
                record["after_progress_sha256"] = kblib.sha256_file(
                    self.progress_path)
        receipt_path.write_text(
            "".join(json.dumps(record, separators=(",", ":")) + "\n"
                    for record in records),
            encoding="utf-8",
        )

    def set_work_spec_binding(self, batch_id, relative, fingerprint):
        queue = self.queue()
        item = next(entry for entry in queue["required_queue"]
                    if entry["id"] == batch_id)
        item["work_spec_path"] = relative
        item["work_spec_sha256"] = fingerprint
        coverage = kblib.load_yaml_file(self.coverage_path)
        spec = next(entry for entry in coverage["batch_specs"]
                    if entry["id"] == batch_id)
        spec["work_spec_path"] = relative
        spec["work_spec_sha256"] = fingerprint
        self.coverage_path.write_text(kblib.canonical_yaml(coverage),
                                      encoding="utf-8")
        self.write_queue(queue)
        self.refresh_initial_origin()

    def valid_work_spec(self, batch_id="B1", manifest=None):
        if manifest is None:
            manifest = ["Topics/A.md"]
        return {
            "schema_version": 1,
            "batch_id": batch_id,
            "manifest": manifest,
            "outcomes": [{
                "outcome_id": "OUT-001",
                "required_result": "The declared batch result exists.",
            }],
            "instructions": [{
                "instruction_id": "INS-001",
                "order": 1,
                "target_scope": list(manifest),
                "required_transformation": "Apply the declared change.",
                "depends_on": [],
            }],
            "acceptance_conditions": [{
                "condition_id": "ACC-001",
                "target_scope": list(manifest),
                "observable_predicate": "Every target passes its gate.",
                "evidence_requirement": "A current gate receipt exists.",
            }],
            "constraints": [{
                "constraint_id": "CON-001",
                "target_scope": ["batch"],
                "requirement": "Preserve the declared scope.",
            }],
        }

    def bind_work_spec_data(self, batch_id, data=None,
                            relative=".cambium/work_specs/B1.yaml"):
        if data is None:
            data = self.valid_work_spec(batch_id)
        text = kblib.canonical_yaml(data)
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        fingerprint = kblib.sha256_file(path)
        self.set_work_spec_binding(batch_id, relative, fingerprint)
        return relative, fingerprint

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root), *args],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def make_task_active_without_open(self):
        """Create the canonical pre-batch active exception via pause/resume."""
        for state, summary, at in (
                ("paused", "fixture pre-activation interruption",
                 "2026-08-04T00:01:00Z"),
                ("active", "fixture pre-activation resume",
                 "2026-08-04T00:02:00Z")):
            completed = subprocess.run(
                [sys.executable, str(TOOLS / "update_task.py"), str(self.root),
                 "--transition", state, "--checkpoint-summary", summary,
                 "--expected-progress-sha256",
                 kblib.sha256_file(self.progress_path),
                 "--expected-queue-sha256",
                 kblib.sha256_file(self.queue_path),
                 "--actor-role", "integrator", "--at", at, "--apply"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stdout)

    def write_writer_lock(self, operation):
        lock = self.root / ".cambium/tmp/state-writer.lock"
        lock.mkdir()
        owner = {
            "lock_name": "state-writer", "pid": 4242,
            "created_at": "2026-08-04T00:01:00Z",
            "operation": operation,
        }
        (lock / "owner.json").write_text(
            json.dumps(owner) + "\n", encoding="utf-8",
        )
        return lock

    def write_live_load_set(self, selected, loaded=()):
        """Declare the live contract's load set and re-anchor the contract.

        The contract anchor chain starts at the initial Queue receipt, so a
        fixture that edits the frozen contract moves that anchor with it or the
        runtime reports an unrelated anchor error instead of the finding under
        test.
        """
        progress = kblib.load_yaml_file(self.progress_path)
        progress["contract"]["selected_read_sets"] = list(selected)
        progress["contract"]["loaded_module_paths"] = list(loaded)
        self.progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        receipt_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        records = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for record in records:
            if record.get("receipt_id") == "audit-fixture-initial-queue":
                record["contract_sha256"] = kblib.sha256_bytes(
                    kblib.canonical_yaml(progress["contract"]))
        receipt_path.write_text(
            "".join(json.dumps(record, separators=(",", ":")) + "\n"
                    for record in records),
            encoding="utf-8",
        )
        self.refresh_initial_origin()

    def write_under_declaring_read_set(self):
        """Lay down a Read Set whose boundary names an undeclared leaf."""
        read_set = "kernel/Read Sets/R99 Live Fixture.md"
        leaf = "kernel/K99 Fixture/01 Required Leaf.md"
        read_set_path = self.root / read_set
        read_set_path.parent.mkdir(parents=True, exist_ok=True)
        read_set_path.write_text(
            "---\ntype: read-set\nroute_id: R99\n---\n\n"
            "## Start\n\n- [[%s|Required Leaf]]\n" % leaf[:-3],
            encoding="utf-8")
        leaf_path = self.root / leaf
        leaf_path.parent.mkdir(parents=True, exist_ok=True)
        leaf_path.write_text("## Purpose\n\nFixture.\n", encoding="utf-8")
        return read_set, leaf

    def open_b1_with_activation_receipt(self, **receipt_overrides):
        """Record an already-authorized `queued -> open` edge for B1.

        The activation receipt is history: it authorized an edge the Queue has
        already taken, and no sanctioned transaction can readmit the batch to
        restamp it under a newer producer identity.
        """
        before_sha = kblib.sha256_file(self.queue_path)
        queue = self.queue()
        item = queue["required_queue"][0]
        item.update({
            "state": "open",
            "opened_at": "2026-08-04T01:00:00Z",
            "activation_receipt": "audit-ready-b1",
            "transition_receipts": ["audit-transition-b1-open"],
        })
        queue["state_revision"] = 1
        self.write_queue(queue)
        activation = {
            "receipt_id": "audit-ready-b1", "tool": "check_queue",
            "tool_version": check_queue.TOOL_VERSION,
            "check": "required_queue",
            "queue_check_mode": "require-ready:B1",
            "result": "pass", "invalidated_by": None,
            "task_id": "fixture-task", "queue_revision": 1,
            "queue_state_revision": 0,
            "required_queue_sha256": before_sha,
            "standards_version": "3.0.0",
        }
        activation.update(receipt_overrides)
        receipts = [activation, {
            "receipt_id": "audit-transition-b1-open",
            "tool": "update_queue", "tool_version": "1.2.0",
            "check": "queue_transition", "target": "B1",
            "result": "pass", "invalidated_by": None,
            "task_id": "fixture-task", "queue_revision": 1,
            "before_state": "queued", "after_state": "open",
            "before_hold_state": "none", "after_hold_state": "none",
            "before_state_revision": 0, "after_state_revision": 1,
            "before_required_queue_sha256": before_sha,
            "after_required_queue_sha256": kblib.sha256_file(self.queue_path),
        }]
        receipt_path = self.root / ".cambium/receipts/history.jsonl"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            "".join(json.dumps(receipt) + "\n" for receipt in receipts),
            encoding="utf-8",
        )
        return "\n".join(check_queue.validate_runtime(self.root)["errors"])

    # --- K13/10 admission condition 2 (control / hub pages) helpers ---

    def write_page(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def set_coverage_page_field(self, page_path, field, value):
        coverage = kblib.load_yaml_file(self.coverage_path)
        page = next(entry for entry in coverage["pages"]
                    if entry["path"] == page_path)
        page[field] = value
        self.coverage_path.write_text(kblib.canonical_yaml(coverage),
                                      encoding="utf-8")
        self.refresh_initial_origin()

    def set_execution_mode(self, batch_id, mode):
        coverage = kblib.load_yaml_file(self.coverage_path)
        next(entry for entry in coverage["batch_specs"]
             if entry["id"] == batch_id)["execution_mode"] = mode
        self.coverage_path.write_text(kblib.canonical_yaml(coverage),
                                      encoding="utf-8")
        queue = self.queue()
        next(entry for entry in queue["required_queue"]
             if entry["id"] == batch_id)["execution_mode"] = mode
        self.write_queue(queue)
        self.refresh_initial_origin()

    def register_expression_layer(self, rows, binding="`expression-layer.md`"):
        """Register dependency-map rows in the fixture profile's slot."""
        manifest = self.root / "profiles/test-profile/profile.md"
        manifest.write_text(
            manifest.read_text(encoding="utf-8") +
            "\n## Implemented Slots\n\n- `Expression Layer Entry`: %s\n" %
            binding,
            encoding="utf-8",
        )
        if rows is None:
            return
        table = ["# Expression Layer", "", "## Registered Artifacts", "",
                 "- Registration: Configured", "", "| Property | Value |",
                 "|---|---|"]
        for label, value in rows:
            table.append("| %s | %s |" % (label, value))
        (self.root / "profiles/test-profile/expression-layer.md").write_text(
            "\n".join(table) + "\n", encoding="utf-8")

    def blocked_reasons(self, batch_id):
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        return result, dict(result["blocked"]).get(batch_id, [])


class ReviewedEraTests(QueueFixture):
    """K02/01: `reviewed` carries the era of the evidence that earned it."""

    def set_page(self, index, **fields):
        coverage = kblib.load_yaml_file(self.coverage_path)
        coverage["pages"][index].update(fields)
        self.coverage_path.write_text(kblib.canonical_yaml(coverage),
                                      encoding="utf-8")
        self.refresh_initial_origin()
        return coverage

    def test_reviewed_without_receipts_is_a_candidate(self):
        coverage = self.set_page(0, authoring_status="reviewed",
                                 gate_receipts=[])
        unsupported = check_queue.unsupported_reviewed_records(coverage)
        self.assertEqual([coverage["pages"][0]["path"]], unsupported)
        completed = self.run_cli()
        self.assertIn("no gate_receipts", completed.stdout)
        self.assertIn("K02/01", completed.stdout)

    def test_reviewed_with_receipts_is_accepted(self):
        coverage = self.set_page(0, authoring_status="reviewed",
                                 gate_receipts=["audit-some-receipt-0001"])
        self.assertEqual(
            [], check_queue.unsupported_reviewed_records(coverage))

    def test_other_statuses_owe_no_era(self):
        coverage = self.set_page(0, authoring_status="drafted",
                                 gate_receipts=[])
        self.assertEqual(
            [], check_queue.unsupported_reviewed_records(coverage))

    def test_unsupported_reviewed_never_becomes_an_error(self):
        # A hard failure would wedge the instance out of the migration that
        # resolves it.
        self.set_page(0, authoring_status="reviewed", gate_receipts=[])
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])


class HubPageAdmissionTests(QueueFixture):
    """K13/10 concurrency admission condition 2."""

    def test_existing_hub_page_in_manifest_blocks_activation(self):
        self.write_page("Topics/A.md", "---\ntype: overview\n---\n\n# A\n")
        result, reasons = self.blocked_reasons("B1")
        self.assertNotIn("B1", result["ready"])
        joined = "; ".join(reasons)
        self.assertIn("existing control or hub page(s): Topics/A.md", joined)
        self.assertIn("type=overview", joined)
        self.assertIn("exclusive", joined)
        self.assertIn("serial-integrator", joined)
        completed = self.run_cli("--require-ready", "B1")
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("existing control or hub page(s)", completed.stdout)
        self.assertIn("exclusive or serial-integrator", completed.stdout)

    def test_condition_two_is_reported_over_the_whole_queue(self):
        # The defect is time-invariant, so consistency mode reports it for
        # every queued batch at once instead of one batch at a time as each
        # reaches the head of the Queue.
        self.write_page("Topics/A.md", "---\ntype: overview\n---\n\n# A\n")
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        defects = "; ".join(result["structural_admission_defects"])
        self.assertIn("B1", defects)
        self.assertIn("Topics/A.md", defects)
        self.assertIn("execution_mode=", defects)
        consistency = self.run_cli()
        self.assertIn("manifest edits existing hub page(s)",
                      consistency.stdout)

    def test_condition_two_defect_is_a_candidate_not_an_error(self):
        # A hard error would wedge the instance: register_amendment and
        # apply_amendment both refuse to run against a runtime with errors,
        # and an Amendment is the only way to change execution_mode.
        self.write_page("Topics/A.md", "---\ntype: overview\n---\n\n# A\n")
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertTrue(result["structural_admission_defects"])

    def test_serial_integrator_batch_reports_no_structural_defect(self):
        self.write_page("Topics/A.md", "---\ntype: overview\n---\n\n# A\n")
        self.set_execution_mode("B1", "serial-integrator")
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual([], result["structural_admission_defects"])

    def test_runtime_card_and_card_index_types_are_hub_pages(self):
        for page_type in ("runtime-card", "card-index"):
            with self.subTest(page_type=page_type):
                self.write_page("Topics/A.md",
                                "---\ntype: %s\n---\n\n# A\n" % page_type)
                _, reasons = self.blocked_reasons("B1")
                self.assertIn("type=%s" % page_type, "; ".join(reasons))

    def test_shared_term_page_is_a_hub_page(self):
        self.write_page("Topics/A.md",
                        "---\ntype: term\nscope: shared\n---\n\n# A\n")
        _, reasons = self.blocked_reasons("B1")
        self.assertIn("type=term scope=shared", "; ".join(reasons))

    def test_term_page_outside_shared_scope_is_not_a_hub_page(self):
        for scope in ("domain-specific", "case-specific", "source-specific"):
            with self.subTest(scope=scope):
                self.write_page(
                    "Topics/A.md",
                    "---\ntype: term\nscope: %s\n---\n\n# A\n" % scope)
                result, reasons = self.blocked_reasons("B1")
                self.assertEqual([], reasons)
                self.assertIn("B1", result["ready"])
                self.assertEqual(
                    [], result["hub_page_admission"]["B1"]["blocking"])

    def test_ordinary_page_without_frontmatter_is_not_a_hub_page(self):
        result, reasons = self.blocked_reasons("B1")
        self.assertEqual([], reasons)
        self.assertIn("B1", result["ready"])

    def test_hub_page_created_by_this_batch_is_a_candidate_not_a_blocker(self):
        (self.root / "Topics/A.md").unlink()
        self.set_coverage_page_field("Topics/A.md", "type", "overview")
        result, reasons = self.blocked_reasons("B1")
        self.assertEqual([], reasons)
        self.assertIn("B1", result["ready"])
        self.assertEqual(["Topics/A.md (Coverage type=overview)"],
                         result["hub_page_admission"]["B1"]["candidates"])
        completed = self.run_cli("--require-ready", "B1")
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("hub_page_candidates=Topics/A.md (Coverage type=overview)",
                      completed.stdout)

    def test_serial_integrator_batch_may_edit_hub_pages(self):
        self.write_page("Topics/A.md", "---\ntype: overview\n---\n\n# A\n")
        self.set_execution_mode("B1", "serial-integrator")
        result, reasons = self.blocked_reasons("B1")
        self.assertEqual([], reasons)
        self.assertIn("B1", result["ready"])
        self.assertNotIn("B1", result["hub_page_admission"])
        completed = self.run_cli("--require-ready", "B1")
        self.assertEqual(0, completed.returncode, completed.stdout)

    def test_expression_layer_registered_dependency_map_is_a_hub_page(self):
        self.register_expression_layer([
            ("Stable artifact ID", "`probe`"),
            ("Existing canonical dependency-map path", "`Topics/A.md`"),
        ])
        _, reasons = self.blocked_reasons("B1")
        self.assertIn("Topics/A.md (Expression Layer Entry)",
                      "; ".join(reasons))

    def test_registered_dependency_map_not_yet_created_is_a_candidate(self):
        (self.root / "Topics/A.md").unlink()
        self.register_expression_layer([
            ("Existing canonical dependency-map ID/path", "`Topics/A.md`"),
        ])
        result, reasons = self.blocked_reasons("B1")
        self.assertEqual([], reasons)
        self.assertEqual(["Topics/A.md (Expression Layer Entry)"],
                         result["hub_page_admission"]["B1"]["candidates"])

    def test_unfilled_or_opaque_dependency_map_cells_are_skipped(self):
        self.register_expression_layer([
            ("Existing canonical dependency-map ID/path", "TODO(profile)"),
            ("Existing canonical dependency-map path", "`None`"),
            ("Existing canonical dependency-map ID", "`atlas-map-01`"),
        ])
        paths, errors = check_queue.profile_hub_paths(
            str(self.root), "profiles/test-profile/profile.md")
        self.assertEqual(set(), paths)
        self.assertEqual([], errors)

    def test_profile_without_expression_layer_slot_still_classifies(self):
        paths, errors = check_queue.profile_hub_paths(
            str(self.root), "profiles/test-profile/profile.md")
        self.assertEqual(set(), paths)
        self.assertEqual([], errors)
        self.write_page("Topics/A.md", "---\ntype: overview\n---\n\n# A\n")
        _, reasons = self.blocked_reasons("B1")
        self.assertIn("type=overview", "; ".join(reasons))

    def test_declared_expression_layer_slot_that_cannot_be_read_fails_closed(self):
        self.register_expression_layer(None)
        result, reasons = self.blocked_reasons("B1")
        self.assertNotIn("B1", result["ready"])
        joined = "; ".join(reasons)
        self.assertIn("hub set cannot be derived", joined)
        self.assertIn("serial-integrator", joined)

    def test_unclassifiable_manifest_page_is_not_silently_admitted(self):
        for body in ("---\ntype: overview\n\n# A\n",
                     "---\ntype: overview\n  stray: 1\n---\n\n# A\n",
                     "---\n- overview\n---\n\n# A\n"):
            with self.subTest(body=body):
                self.write_page("Topics/A.md", body)
                result, reasons = self.blocked_reasons("B1")
                self.assertNotIn("B1", result["ready"])
                self.assertIn("cannot be classified against K13/10 hub roles",
                              "; ".join(reasons))

    def test_shipped_example_profile_registration_is_parsed(self):
        paths, errors = check_queue.profile_hub_paths(
            str(REPO), "profiles/examples/agent-atlas/profile.md")
        self.assertEqual([], errors)
        self.assertEqual({"Interview Preparation/Interview Overview.md"},
                         paths)


class CheckQueueTests(QueueFixture):
    def test_live_task_contract_closure_gap_is_reported_not_refused(self):
        """An under-declared live load set is a finding, never a runtime error.

        The contract's five load fields are written only by a Standards
        adoption, whose plan bytes are then sealed into append-only receipts.
        Refusing the runtime that holds them would lock the instance out of the
        sole writer that can re-declare them, so the gap is reported on
        `task_runtime` and admission of the next plan is where K00/15 judges it.
        """
        read_set, leaf = self.write_under_declaring_read_set()
        self.write_live_load_set([read_set])

        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        gaps = result["task_runtime"]["contract_load_set_gaps"]
        self.assertTrue(any(
            "Progress contract.loaded_module_paths omits %s" % leaf in gap
            for gap in gaps), gaps)

    def test_a_broken_live_read_set_path_remains_a_runtime_error(self):
        """Unresolvable bytes are not an under-declaration and stay errors."""
        absent = "kernel/Read Sets/R99 Absent.md"
        self.write_live_load_set([absent])

        result = check_queue.validate_runtime(self.root)
        closure = [error for error in result["errors"]
                   if "Read Set load closure" in error]
        self.assertEqual(1, len(closure), result["errors"])
        self.assertIn(absent, closure[0])
        self.assertEqual([], result["task_runtime"]["contract_load_set_gaps"])

    def test_an_ordinary_selected_path_is_not_a_traversal_root(self):
        """A selected path proving no Read Set type is a structural error."""
        ordinary = "profiles/test-profile/ordinary.md"
        (self.root / ordinary).write_text(
            "## Start\n\n- [[Topics/A|A]]\n", encoding="utf-8")
        self.write_live_load_set([ordinary])

        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any(
            "does not prove frontmatter type" in error and ordinary in error
            for error in result["errors"]), result["errors"])
        self.assertEqual([], result["task_runtime"]["contract_load_set_gaps"])

    def test_a_superseded_activation_producer_version_is_not_an_error(self):
        """History is not invalidated by a later producer version bump.

        The receipt's own `standards_version` is the live identity, so the
        instance's own chain accounts for the era it claims; the `tool_version`
        it was stamped with is whatever `check_queue` was at the time.
        """
        errors = self.open_b1_with_activation_receipt(tool_version="0.1.0")
        self.assertNotIn("tool_version", errors)
        self.assertNotIn("claims standards_version", errors)

    def test_an_activation_receipt_era_nothing_accounts_for_is_refused(self):
        """The replacement check has teeth: an invented era is still refused."""
        errors = self.open_b1_with_activation_receipt(
            tool_version="0.1.0", standards_version="9.9.9")
        self.assertIn(
            "B1 activation receipt audit-ready-b1 claims "
            "standards_version='9.9.9'", errors)
        self.assertIn("no Standards adoption record or live identity", errors)

    def test_simple_batch_work_spec_pair_is_explicit_and_closed(self):
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])
        queue = self.queue()
        coverage = kblib.load_yaml_file(self.coverage_path)
        for field in check_queue.WORK_SPEC_FIELDS:
            queue["required_queue"][0].pop(field)
            coverage["batch_specs"][0].pop(field)
        self.coverage_path.write_text(kblib.canonical_yaml(coverage),
                                      encoding="utf-8")
        self.write_queue(queue)
        self.refresh_initial_origin()
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("misses explicit field(s)", errors)
        self.assertIn("work_spec_path", errors)
        self.assertIn("work_spec_sha256", errors)

    def test_complex_batch_work_spec_passes_and_resume_reports_binding(self):
        relative, fingerprint = self.bind_work_spec_data("B1")
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])
        resumed = self.run_cli("--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn(
            "work_spec.B1.path=%s sha256=%s" % (relative, fingerprint),
            resumed.stdout,
        )
        result = check_queue.validate_runtime(self.root)
        receipt = check_queue.make_check_receipt(
            result, "candidate", "resume", "resume-status")
        self.assertEqual({
            "batch_id": "B1", "work_spec_path": relative,
            "work_spec_sha256": fingerprint,
        }, receipt["batch_work_specs"][0])

    def test_work_spec_pair_and_managed_path_fail_closed(self):
        valid_sha = "sha256:" + "0" * 64
        cases = (
            ("half-null", None, valid_sha,
             "must both be null or both be non-null"),
            ("outside-namespace", ".cambium/receipts/B1.yaml", valid_sha,
             "must be a YAML file directly inside .cambium/work_specs/"),
            ("nested-namespace", ".cambium/work_specs/nested/B1.yaml", valid_sha,
             "must be a YAML file directly inside .cambium/work_specs/"),
            ("markdown-extension", ".cambium/work_specs/B1.md", valid_sha,
             "must be a YAML file directly inside .cambium/work_specs/"),
            ("missing-file", ".cambium/work_specs/missing.yaml", valid_sha,
             "unsafe or unreadable"),
            ("bad-sha", ".cambium/work_specs/missing.yaml", "sha256:BAD",
             "work_spec_sha256 must be null or sha256"),
        )
        for name, relative, fingerprint, expected in cases:
            with self.subTest(name=name):
                self.set_work_spec_binding("B1", relative, fingerprint)
                errors = "\n".join(
                    check_queue.validate_runtime(self.root)["errors"])
                self.assertIn(expected, errors)

    def test_work_spec_document_is_closed_and_manifest_order_is_exact(self):
        valid = self.valid_work_spec()
        cases = (
            ("not-yaml", "# No contract\n",
             "misses field(s)"),
            ("wrong-batch", dict(valid, batch_id="B2"),
             "does not equal Queue id"),
            ("wrong-manifest", dict(valid, manifest=["Topics/B.md"]),
             "must exactly equal Queue manifest in membership and order"),
            ("queue-owned-field", dict(valid, receipts=[]),
             "must not declare Queue-owned field path(s): receipts"),
        )
        for name, data, expected in cases:
            with self.subTest(name=name):
                text = data if isinstance(data, str) else kblib.canonical_yaml(data)
                path = self.root / ".cambium/work_specs/B1.yaml"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                self.set_work_spec_binding(
                    "B1", ".cambium/work_specs/B1.yaml",
                    kblib.sha256_file(path))
                errors = "\n".join(
                    check_queue.validate_runtime(self.root)["errors"])
                self.assertIn(expected, errors)

        ordered = self.valid_work_spec(manifest=["Topics/B.md", "Topics/A.md"])
        path = self.root / ".cambium/work_specs/order.yaml"
        path.write_text(kblib.canonical_yaml(ordered), encoding="utf-8")
        item = {
            "id": "B1", "manifest": ["Topics/A.md", "Topics/B.md"],
            "work_spec_path": ".cambium/work_specs/order.yaml",
            "work_spec_sha256": kblib.sha256_file(path),
        }
        errors = "\n".join(check_queue._work_spec_errors(self.root, item))
        self.assertIn("membership and order", errors)

        incomplete = self.valid_work_spec()
        incomplete["constraints"] = []
        path = self.root / ".cambium/work_specs/incomplete.yaml"
        path.write_text(kblib.canonical_yaml(incomplete), encoding="utf-8")
        item = {
            "id": "B1", "manifest": ["Topics/A.md"],
            "work_spec_path": ".cambium/work_specs/incomplete.yaml",
            "work_spec_sha256": kblib.sha256_file(path),
        }
        errors = "\n".join(check_queue._work_spec_errors(self.root, item))
        self.assertIn("constraints must be a non-empty list", errors)

    def test_work_spec_rejects_unfilled_template_and_queue_state_at_depth(self):
        template = (TOOLS / "schemas" / "batch_work_spec.template.yaml") \
            .read_text(encoding="utf-8")
        unfilled = template.replace("REPLACE-ME", "B1").replace(
            "path/to/first-object.md", "Topics/A.md")
        path = self.root / ".cambium/work_specs/B1.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(unfilled, encoding="utf-8")
        self.set_work_spec_binding(
            "B1", ".cambium/work_specs/B1.yaml", kblib.sha256_file(path))
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("unfilled template sentinel", errors)

        nested_state = self.valid_work_spec()
        nested_state["outcomes"][0]["required_result"] = {"state": "open"}
        _, _ = self.bind_work_spec_data("B1", nested_state)
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("outcomes.0.required_result.state", errors)

    def test_work_spec_instruction_graph_and_target_scopes_are_closed(self):
        data = self.valid_work_spec()
        data["instructions"] = [
            {
                "instruction_id": "INS-002", "order": 2,
                "target_scope": ["batch", "Topics/A.md"],
                "required_transformation": "Second change.",
                "depends_on": ["INS-001"],
            },
            {
                "instruction_id": "INS-001", "order": 1,
                "target_scope": ["Topics/Unknown.md"],
                "required_transformation": "First change.",
                "depends_on": ["INS-002"],
            },
        ]
        _, _ = self.bind_work_spec_data("B1", data)
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("instruction order must be unique, contiguous", errors)
        self.assertIn("batch and paths cannot be mixed", errors)
        self.assertIn("outside the Queue manifest", errors)
        self.assertIn("reference only earlier instructions", errors)

    def test_work_spec_record_fields_ids_and_text_are_closed(self):
        data = self.valid_work_spec()
        data["outcomes"].append({
            "outcome_id": "OUT-001", "required_result": "",
            "state": "closed",
        })
        data["constraints"][0]["constraint_id"] = "not stable!"
        _, _ = self.bind_work_spec_data("B1", data)
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("duplicate outcome_id", errors)
        self.assertIn("must not declare Queue-owned field", errors)
        self.assertIn("required_result must be a non-empty string", errors)
        self.assertIn("constraint_id must match", errors)

    def test_bound_work_spec_byte_change_invalidates_runtime(self):
        data = self.valid_work_spec()
        text = kblib.canonical_yaml(data)
        relative, _ = self.bind_work_spec_data("B1", data)
        (self.root / relative).write_text(text + "\nchanged\n",
                                          encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("Work Spec SHA mismatch", errors)

    def test_build_runtime_rejects_maintenance_candidate_state(self):
        coverage = kblib.load_yaml_file(self.coverage_path)
        coverage["maintenance_candidates"] = [{
            "candidate_id":
                check_queue.maintenance_candidates.candidate_id_for_path(
                    "Topics/A.md"),
            "object_path": "Topics/A.md",
            "source_kinds": ["freshness"],
            "priority": "P0",
            "previous_deferred_runs": 0,
            "consecutive_deferred_runs": 0,
            "reentered_after_terminal": False,
            "selection": "selected",
            "disposition": None,
            "disposition_reason": None,
        }]
        self.coverage_path.write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        errors = check_queue.validate_runtime(self.root)["errors"]
        self.assertTrue(any(
            "build completion semantics requires Coverage "
            "maintenance_candidates=[]" in error for error in errors), errors)

    def test_prior_maintenance_gate_must_have_one_task_completion_consumer(self):
        record = {
            "candidate_id":
                check_queue.maintenance_candidates.candidate_id_for_path(
                    "Topics/A.md"),
            "object_path": "Topics/A.md",
            "source_kinds": ["freshness"],
            "priority": "P0",
            "previous_deferred_runs": 0,
            "consecutive_deferred_runs": 0,
            "reentered_after_terminal": False,
            "selection": "selected",
            "disposition": None,
            "disposition_reason": None,
        }
        prior = kblib.make_receipt(
            check_queue.TOOL, check_queue.TOOL_VERSION, "required_queue",
            check_queue.QUEUE_PATH, "pass", "prior maintenance gate", 1,
        )
        prior["checked_at"] = "2026-08-03T00:00:00Z"
        prior.update({
            "queue_check_mode": "require-maintenance-complete",
            "completion_semantics": "maintenance",
            "task_id": "previous-task",
            "scope_version": "s0",
            "standards_version": "3.0.0",
            "selected_profile_manifest": "profiles/test-profile/profile.md",
            "queue_revision": 1,
            "queue_state_revision": 4,
            "required_queue_sha256": "sha256:" + "1" * 64,
            "coverage_ledger_sha256": "sha256:" + "2" * 64,
            "progress_ledger_sha256": "sha256:" + "3" * 64,
            "contract_sha256": "sha256:" + "4" * 64,
            "remaining_required_work_units": 0,
            "maintenance_run_id": "previous-run",
            "maintenance_candidate_states": [record],
            "maintenance_candidate_state_sha256":
                check_queue.maintenance_candidates.candidate_state_sha256(
                    [record]),
            "selected_candidate_ids": [record["candidate_id"]],
            "deferred_candidate_ids": [],
        })
        result = {"receipt_catalog": {
            prior["receipt_id"]: (".cambium/receipts/prior.jsonl", prior),
        }}
        contract = {
            "standards_version": "3.0.0",
            "selected_profile_manifest": "profiles/test-profile/profile.md",
        }
        errors = []
        check_queue._previous_maintenance_candidate_state(
            self.root, result, prior["receipt_id"], contract, errors)
        self.assertTrue(any("exactly one persisted maintenance task completion"
                            in error for error in errors), errors)

        consumer = kblib.make_receipt(
            "update_task", "1.1.0", "task_transition", "previous-task",
            "pass", "active -> complete", 1,
        )
        consumer["checked_at"] = "2026-08-03T00:01:00Z"
        consumer.update({
            "task_id": "previous-task",
            "completion_semantics": "maintenance",
            "contract_sha256": "sha256:" + "4" * 64,
            "before_task_state": "active",
            "after_task_state": "complete",
            "actor_role": "integrator",
            "queue_revision": 1,
            "queue_state_revision": 4,
            "before_coverage_sha256": "sha256:" + "2" * 64,
            "after_coverage_sha256": "sha256:" + "2" * 64,
            "before_required_queue_sha256": "sha256:" + "1" * 64,
            "after_required_queue_sha256": "sha256:" + "1" * 64,
            "before_progress_sha256": "sha256:" + "3" * 64,
            "after_progress_sha256": "sha256:" + "5" * 64,
            "evidence_receipt": prior["receipt_id"],
        })
        result["receipt_catalog"][consumer["receipt_id"]] = (
            ".cambium/receipts/prior-task.jsonl", consumer)
        errors = []
        _, records, fingerprint = \
            check_queue._previous_maintenance_candidate_state(
                self.root, result, prior["receipt_id"], contract, errors)
        self.assertEqual([], errors)
        self.assertEqual([record], records)
        self.assertEqual(
            prior["maintenance_candidate_state_sha256"], fingerprint)

    def test_simplified_fake_consumer_cannot_complete_predecessor(self):
        gate = kblib.make_receipt(
            check_queue.TOOL, check_queue.TOOL_VERSION, "required_queue",
            check_queue.QUEUE_PATH, "pass", "prior maintenance gate", 1,
        )
        gate.update({
            "queue_check_mode": "require-maintenance-complete",
            "completion_semantics": "maintenance",
            "task_id": "previous-task",
            "standards_version": "3.0.0",
            "selected_profile_manifest": "profiles/test-profile/profile.md",
            "remaining_required_work_units": 0,
            "maintenance_run_id": "previous-run",
            "maintenance_candidate_states": [],
            "maintenance_candidate_state_sha256":
                check_queue.maintenance_candidates.candidate_state_sha256([]),
            "selected_candidate_ids": [],
            "deferred_candidate_ids": [],
        })
        consumer = kblib.make_receipt(
            "update_task", "1.1.0", "task_transition", "previous-task",
            "pass", "active -> complete", 1,
        )
        consumer.update({
            "task_id": "previous-task",
            "completion_semantics": "maintenance",
            "after_task_state": "complete",
            "evidence_receipt": gate["receipt_id"],
        })
        result = {"receipt_catalog": {
            gate["receipt_id"]: ("prior.jsonl", gate),
            consumer["receipt_id"]: ("consumer.jsonl", consumer),
        }}
        errors = []
        check_queue._previous_maintenance_candidate_state(
            self.root, result, gate["receipt_id"], {
                "standards_version": "3.0.0",
                "selected_profile_manifest":
                    "profiles/test-profile/profile.md",
            }, errors)
        self.assertTrue(any("invalid contract_sha256" in error
                            for error in errors), errors)
        self.assertTrue(any("exactly one persisted maintenance task completion"
                            in error for error in errors), errors)

    def test_latest_consumed_matching_gate_is_the_unique_predecessor(self):
        def pair(task_id, run_id, gate_at, consumer_at, digit):
            queue_sha = "sha256:" + digit * 64
            coverage_sha = "sha256:" + str(int(digit) + 1) * 64
            progress_sha = "sha256:" + str(int(digit) + 2) * 64
            gate = kblib.make_receipt(
                check_queue.TOOL, check_queue.TOOL_VERSION,
                "required_queue", check_queue.QUEUE_PATH, "pass",
                "prior maintenance gate", int(digit),
            )
            gate["checked_at"] = gate_at
            gate.update({
                "queue_check_mode": "require-maintenance-complete",
                "completion_semantics": "maintenance",
                "task_id": task_id,
                "scope_version": "s0",
                "standards_version": "3.0.0",
                "selected_profile_manifest":
                    "profiles/test-profile/profile.md",
                "queue_revision": 1,
                "queue_state_revision": 2,
                "required_queue_sha256": queue_sha,
                "coverage_ledger_sha256": coverage_sha,
                "progress_ledger_sha256": progress_sha,
                "contract_sha256": "sha256:" + "f" * 64,
                "remaining_required_work_units": 0,
                "maintenance_run_id": run_id,
                "maintenance_candidate_states": [],
                "maintenance_candidate_state_sha256":
                    check_queue.maintenance_candidates.
                    candidate_state_sha256([]),
                "selected_candidate_ids": [],
                "deferred_candidate_ids": [],
            })
            consumer = kblib.make_receipt(
                "update_task", "1.1.0", "task_transition", task_id,
                "pass", "active -> complete", int(digit),
            )
            consumer["checked_at"] = consumer_at
            consumer.update({
                "task_id": task_id,
                "completion_semantics": "maintenance",
                "contract_sha256": "sha256:" + "f" * 64,
                "before_task_state": "active",
                "after_task_state": "complete",
                "actor_role": "integrator",
                "queue_revision": 1,
                "queue_state_revision": 2,
                "before_coverage_sha256": coverage_sha,
                "after_coverage_sha256": coverage_sha,
                "before_required_queue_sha256": queue_sha,
                "after_required_queue_sha256": queue_sha,
                "before_progress_sha256": progress_sha,
                "after_progress_sha256":
                    "sha256:" + str(int(digit) + 3) * 64,
                "evidence_receipt": gate["receipt_id"],
            })
            return gate, consumer

        older = pair(
            "task-old", "run-old", "2026-08-01T00:00:00Z",
            "2026-08-01T00:01:00Z", "1")
        newer = pair(
            "task-new", "run-new", "2026-08-02T00:00:00Z",
            "2026-08-02T00:01:00Z", "5")
        catalog = {}
        for gate, consumer in (older, newer):
            catalog[gate["receipt_id"]] = ("maintenance.jsonl", gate)
            catalog[consumer["receipt_id"]] = ("tasks.jsonl", consumer)
        result = {"receipt_catalog": catalog}
        errors = []
        selected = check_queue._latest_consumed_maintenance_gate(
            self.root, result, {
                "standards_version": "3.0.0",
                "selected_profile_manifest":
                    "profiles/test-profile/profile.md",
            }, current_task_id="task-current",
            current_maintenance_run_id="run-current", errors=errors)
        self.assertEqual([], errors)
        self.assertEqual(newer[0]["receipt_id"], selected)

        newer[1].pop("after_task_state")
        errors = []
        selected = check_queue._latest_consumed_maintenance_gate(
            self.root, result, {
                "standards_version": "3.0.0",
                "selected_profile_manifest":
                    "profiles/test-profile/profile.md",
            }, current_task_id="task-current",
            current_maintenance_run_id="run-current", errors=errors)
        self.assertEqual(older[0]["receipt_id"], selected)
        self.assertTrue(any("task completion" in error for error in errors),
                        errors)

        newer[1]["after_task_state"] = "complete"
        errors = []
        selected = check_queue._latest_consumed_maintenance_gate(
            self.root, result, {
                "standards_version": "3.0.0",
                "selected_profile_manifest":
                    "profiles/test-profile/profile.md",
            }, current_task_id="task-current",
            current_maintenance_run_id="run-new", errors=errors)
        self.assertEqual(older[0]["receipt_id"], selected)
        self.assertTrue(any("run_id run-new was already used" in error
                            for error in errors), errors)

    def test_runtime_profile_must_be_adopter_owned_and_instantiated(self):
        self.assertEqual([], check_queue.selected_profile_manifest_errors(
            self.root, "profiles/test-profile/profile.md"))

        template = self.root / "profiles/_template/profile.md"
        template.parent.mkdir(parents=True)
        template.write_text(
            "## Profile Identity\n\n- `profile_id`: `TODO(profile)`\n",
            encoding="utf-8")
        template_errors = "\n".join(
            check_queue.selected_profile_manifest_errors(
                self.root, "profiles/_template/profile.md"))
        self.assertIn("reserved/non-runnable", template_errors)
        self.assertIn("unfilled sentinel", template_errors)

        example = self.root / "profiles/examples/demo/profile.md"
        example.parent.mkdir(parents=True)
        example.write_text(
            "## Profile Identity\n\n- `profile_id`: `demo`\n",
            encoding="utf-8")
        example_errors = "\n".join(
            check_queue.selected_profile_manifest_errors(
                self.root, "profiles/examples/demo/profile.md"))
        self.assertIn("profiles/<id>/profile.md", example_errors)

        unfilled = self.root / "profiles/adopter/profile.md"
        unfilled.parent.mkdir(parents=True)
        unfilled.write_text(
            "## Profile Identity\n\n- `profile_id`: `adopter`\n\n"
            "TODO(profile)\n", encoding="utf-8")
        unfilled_errors = "\n".join(
            check_queue.selected_profile_manifest_errors(
                self.root, "profiles/adopter/profile.md"))
        self.assertIn("unfilled sentinel", unfilled_errors)

    def test_coverage_provenance_rejects_an_older_writer_after_image(self):
        old_queue_sha = "sha256:" + "1" * 64
        live_queue_sha = "sha256:" + "2" * 64
        old_coverage_sha = "sha256:" + "3" * 64
        live_coverage_sha = "sha256:" + "4" * 64
        queue = {
            "task_id": "fixture-task", "queue_revision": 2,
            "state_revision": 0, "required_queue": [],
        }
        progress = {
            "initial_queue_receipt": "audit-old-writer",
            "task_transition_receipts": [],
            "amendments": [{
                "verification_receipt": "audit-current-writer",
            }],
        }
        common = {
            "tool": "compile_queue", "result": "pass",
            "invalidated_by": None, "task_id": "fixture-task",
            "actor_role": "integrator", "queue_state_revision": 0,
        }
        old = dict(common, check="queue_structure",
                   after_required_queue_sha256=old_queue_sha,
                   after_queue_revision=1,
                   after_coverage_sha256=old_coverage_sha)
        current = dict(common, check="queue_replan",
                       after_required_queue_sha256=live_queue_sha,
                       after_queue_revision=2,
                       after_coverage_sha256=live_coverage_sha)
        catalog = {
            "audit-old-writer": ("history.jsonl", old),
            "audit-current-writer": ("history.jsonl", current),
        }
        errors = check_queue._coverage_provenance_errors(
            progress, queue, catalog, old_coverage_sha, live_queue_sha)
        self.assertTrue(any("not the after-image" in error
                            for error in errors), errors)
        self.assertEqual([], check_queue._coverage_provenance_errors(
            progress, queue, catalog, live_coverage_sha, live_queue_sha))

    def add_replan_amendment(self, amendment_id, before_revision,
                             after_revision, after_sha, receipt_id,
                             receipt_overrides=None, persist_receipt=True,
                             status="verified", writeback_done=True):
        diff_sha = "sha256:" + ("d" * 64)
        proposal_relative = (
            ".cambium/deltas/replans/%s.coverage.yaml" % amendment_id)
        proposal_path = self.root / proposal_relative
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        proposal_path.write_bytes(self.coverage_path.read_bytes())
        proposal_sha = kblib.sha256_file(proposal_path)
        coverage_sha = kblib.sha256_file(self.coverage_path)
        transaction_id = "txn-%s" % amendment_id
        registration_id = "audit-register-%s" % amendment_id.lower()
        record = {
            "id": amendment_id,
            "date": "2026-08-04",
            "summary": "same-scope Queue replan",
            "approval_reference": "user:fixture-approval",
            "registration_receipt": registration_id,
            "status": status,
            "writeback_done": writeback_done,
            "operation": "queue-replan",
            "coverage_proposal_path": proposal_relative,
            "coverage_proposal_sha256": proposal_sha,
            "affected_pages": [],
            "affected_batches": ["B1"],
            "scope_version_before": "s1",
            "scope_version_after": "s1",
            "queue_revision_before": before_revision,
            "queue_revision_after": after_revision,
            "queue_state_revision_before": 0,
            "queue_state_revision_after": 0,
            "replan_diff_sha256": diff_sha,
        }
        if status == "verified" and writeback_done is True:
            record.update({
                "transaction_receipt_id": receipt_id,
                "transaction_id": transaction_id,
                "after_required_queue_sha256": after_sha,
                "after_coverage_sha256": coverage_sha,
            })
        progress = kblib.load_yaml_file(self.progress_path)
        registration = {
            "receipt_id": registration_id,
            "tool": "register_amendment", "tool_version": "1.0.0",
            "check": "amendment_registration", "target": amendment_id,
            "result": "pass", "invalidated_by": None,
            "checked_at": "2026-08-04T00:00:00Z",
            "task_id": "fixture-task", "actor_role": "integrator",
            "amendment_id": amendment_id, "operation": "queue-replan",
            "approval_reference": "user:fixture-approval",
            "summary": "same-scope Queue replan",
            "affected_pages": [], "affected_batches": ["B1"],
            "scope_version_before": "s1", "scope_version_after": "s1",
            "queue_revision_before": before_revision,
            "queue_revision_after": after_revision,
            "state_revision_before": 0, "state_revision_after": 0,
            "coverage_proposal_path": proposal_relative,
            "coverage_proposal_sha256": proposal_sha,
            "replan_diff_sha256": diff_sha,
            "contract_sha256": check_queue._contract_sha256(progress),
            "before_coverage_sha256": coverage_sha,
            "after_coverage_sha256": coverage_sha,
            "before_required_queue_sha256":
                kblib.sha256_file(self.queue_path),
            "after_required_queue_sha256":
                kblib.sha256_file(self.queue_path),
            "before_progress_sha256": "sha256:" + ("1" * 64),
            "after_progress_sha256": "sha256:" + ("2" * 64),
        }
        progress.setdefault("amendments", []).append(record)
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        if status == "verified" and writeback_done is True:
            registration.update({
                "after_coverage_sha256": "sha256:" + ("c" * 64),
                "after_required_queue_sha256": "sha256:" + ("a" * 64),
                "after_progress_sha256": "sha256:" + ("e" * 64),
            })
        else:
            registration["after_progress_sha256"] = \
                kblib.sha256_file(self.progress_path)
        kblib.write_receipts(
            self.root / ".cambium/receipts/amendment-registrations.jsonl",
            [registration],
        )
        receipt = {
            "receipt_id": receipt_id,
            "tool": "compile_queue", "tool_version": "1.3.0",
            "check": "queue_replan", "target": check_queue.QUEUE_PATH,
            "result": "pass", "invalidated_by": None,
            "checked_at": "2026-08-04T00:01:00Z",
            "task_id": "fixture-task", "amendment_id": amendment_id,
            "registration_receipt": registration_id,
            "transaction_id": transaction_id, "transaction_phase": "commit",
            "actor_role": "integrator", "replan_diff_sha256": diff_sha,
            "coverage_proposal_path": proposal_relative,
            "coverage_proposal_sha256": proposal_sha,
            "affected_pages": [], "affected_batches": ["B1"],
            "before_queue_revision": before_revision,
            "after_queue_revision": after_revision,
            "queue_state_revision": 0,
            "before_required_queue_sha256": "sha256:" + ("a" * 64),
            "after_required_queue_sha256": after_sha,
            "before_coverage_sha256": "sha256:" + ("c" * 64),
            "after_coverage_sha256": coverage_sha,
            "before_progress_sha256": "sha256:" + ("e" * 64),
            "after_progress_sha256": "sha256:" + ("f" * 64),
        }
        receipt.update(receipt_overrides or {})
        if persist_receipt:
            kblib.write_receipts(
                self.root / ".cambium/receipts/replans.jsonl", [receipt]
            )
        return record, receipt

    def test_exact_live_state_fingerprints_and_error_shape(self):
        result = check_queue.validate_runtime(self.root)
        self.assertEqual(kblib.sha256_file(self.coverage_path),
                         result["coverage_sha256"])
        self.assertEqual(kblib.sha256_file(self.progress_path),
                         result["progress_sha256"])
        self.assertEqual(kblib.sha256_file(self.queue_path),
                         result["queue_sha256"])

        completed = self.run_cli("--resume-status")
        self.assertIn(
            "live.coverage_sha256=%s" % result["coverage_sha256"],
            completed.stdout,
        )
        self.assertIn(
            "live.progress_sha256=%s" % result["progress_sha256"],
            completed.stdout,
        )
        self.assertIn(
            "live.required_queue_sha256=%s" % result["queue_sha256"],
            completed.stdout,
        )

        self.coverage_path.unlink()
        failed = check_queue.validate_runtime(self.root)
        self.assertTrue(failed["errors"])
        self.assertIsNone(failed["coverage_sha256"])
        self.assertIsNone(failed["progress_sha256"])
        self.assertIsNone(failed["queue_sha256"])

    def test_valid_fixture_and_dependency_readiness(self):
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(["B1"], result["ready"])
        self.assertEqual(2, result["remaining"])
        blocked = dict(result["blocked"])
        self.assertIn("dependencies not closed: B1", blocked["B2"])
        completed = self.run_cli()
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("required_queue_sha256=sha256:", completed.stdout)

    def test_manifest_and_record_count_are_strict(self):
        for mutation, expected in (
            (lambda item: item.update(manifest=[]), "manifest must be non-empty"),
            (lambda item: item.update(record_count=0), "record_count must be a positive"),
            (lambda item: item.update(execution_mode="exclusive"),
             "execution_mode must be concurrent-worker"),
        ):
            with self.subTest(expected=expected):
                queue = self.queue()
                mutation(queue["required_queue"][0])
                self.write_queue(queue)
                errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
                self.assertIn(expected, errors)
                shutil.copyfile(FIXTURE / check_queue.QUEUE_PATH, self.queue_path)
                shutil.copyfile(FIXTURE / check_queue.PROGRESS_PATH,
                                self.progress_path)

    def test_coverage_and_manifest_must_agree_both_directions(self):
        queue = self.queue()
        queue["required_queue"][0]["manifest"] = ["Topics/B.md"]
        self.write_queue(queue)
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("not assigned to that batch in Coverage", errors)
        self.assertIn("Queue manifest omits it", errors)

    def test_noncancelled_queue_rejects_nonrequired_coverage_object(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        coverage["pages"][0]["coverage_disposition"] = "deferred"
        coverage_path.write_text(kblib.canonical_yaml(coverage), encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("non-Required Coverage disposition", errors)

    def test_duplicate_order_unknown_dependency_and_cycle_fail(self):
        queue = self.queue()
        queue["required_queue"][1]["order"] = 1
        queue["required_queue"][0]["depends_on"] = ["B2"]
        self.write_queue(queue)
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("repeats order", errors)
        self.assertIn("dependency cycle", errors)

    def test_stale_progress_fingerprint_fails(self):
        queue = self.queue()
        queue["required_queue"][0]["family"] = "Changed"
        self.write_queue(queue, sync_progress=False)
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("required_queue_sha256 does not match", errors)

    def test_pending_queue_replan_is_valid_but_blocks_activation(self):
        queue = self.queue()
        self.add_replan_amendment(
            "A-PENDING", queue["queue_revision"],
            queue["queue_revision"] + 1, "sha256:" + ("b" * 64),
            "unused-pending-receipt", persist_receipt=False,
            status="approved", writeback_done=False,
        )
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(["A-PENDING"],
                         result["pending_cross_ledger_amendments"])
        self.assertEqual([], result["ready"])
        self.assertIn("pending cross-Ledger Amendment(s): A-PENDING",
                      "\n".join(dict(result["blocked"])["B1"]))
        completed = self.run_cli("--require-ready", "B1")
        self.assertEqual(2, completed.returncode, completed.stdout)

    def test_registration_receipt_is_current_for_pending_and_history_for_verified(self):
        queue = self.queue()
        record, _ = self.add_replan_amendment(
            "A-AUTH", queue["queue_revision"],
            queue["queue_revision"] + 1, "sha256:" + ("b" * 64),
            "unused-commit", persist_receipt=False,
            status="approved", writeback_done=False,
        )
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        registration_id = record["registration_receipt"]
        registration = runtime["receipt_catalog"][registration_id]
        label = "Progress amendments[0]"
        pending_errors = check_queue._operational_amendment_registration_errors(
            runtime["progress"], record, label, {},
            {registration_id: registration}, runtime["queue"],
            runtime["coverage_sha256"], runtime["queue_sha256"],
            runtime["progress_sha256"],
        )
        self.assertTrue(any("missing receipt" in error
                            for error in pending_errors), pending_errors)

        record["status"] = "verified"
        record["writeback_done"] = True
        historical_errors = \
            check_queue._operational_amendment_registration_errors(
                runtime["progress"], record, label, {},
                {registration_id: registration}, runtime["queue"],
                runtime["coverage_sha256"], runtime["queue_sha256"],
                runtime["progress_sha256"],
            )
        self.assertEqual([], historical_errors)

    def test_pending_registration_must_bind_live_progress_bytes(self):
        queue = self.queue()
        self.add_replan_amendment(
            "A-PROGRESS", queue["queue_revision"],
            queue["queue_revision"] + 1, "sha256:" + ("b" * 64),
            "unused-commit", persist_receipt=False,
            status="approved", writeback_done=False,
        )
        receipt_path = self.root / \
            ".cambium/receipts/amendment-registrations.jsonl"
        registration = json.loads(receipt_path.read_text(
            encoding="utf-8").strip())
        registration["after_progress_sha256"] = "sha256:" + ("0" * 64)
        receipt_path.write_text(json.dumps(registration) + "\n",
                                encoding="utf-8")
        errors = check_queue.validate_runtime(self.root)["errors"]
        self.assertTrue(any(
            "current registration receipt has after_progress_sha256" in error
            for error in errors
        ), errors)

    def test_manual_pending_operational_row_without_registration_fails(self):
        queue = self.queue()
        record, _ = self.add_replan_amendment(
            "A-NO-REG", queue["queue_revision"],
            queue["queue_revision"] + 1, "sha256:" + ("b" * 64),
            "unused-commit", persist_receipt=False,
            status="approved", writeback_done=False,
        )
        progress = kblib.load_yaml_file(self.progress_path)
        progress["amendments"][-1].pop("registration_receipt")
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        errors = check_queue.validate_runtime(self.root)["errors"]
        self.assertTrue(any("registration must identify a receipt" in error
                            for error in errors), errors)

    def test_pending_queue_replan_shape_is_fail_closed(self):
        queue = self.queue()
        record, _ = self.add_replan_amendment(
            "A-PENDING", queue["queue_revision"],
            queue["queue_revision"] + 1, "sha256:" + ("b" * 64),
            "unused-pending-receipt", persist_receipt=False,
            status="approved", writeback_done=False,
        )
        progress = kblib.load_yaml_file(self.progress_path)
        record = progress["amendments"][-1]
        record["affected_batches"] = []
        record["queue_state_revision_after"] = 1
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("affected_batches must be a non-empty list", errors)
        self.assertIn("must not change the Queue state revision", errors)

    def test_pending_cross_ledger_amendment_blocks_ready_and_is_validated(self):
        proposal_relative = \
            ".cambium/deltas/amendments/A-SCOPE.coverage.yaml"
        proposal = kblib.load_yaml_file(self.coverage_path)
        proposal["scope_version"] = "s2"
        proposal["updated_at"] = "2026-08-04T01:00:00Z"
        proposal_path = self.root / proposal_relative
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        proposal_path.write_text(kblib.canonical_yaml(proposal),
                                 encoding="utf-8")
        plan_relative = ".cambium/deltas/amendments/A-SCOPE.yaml"
        plan = {
            "schema_version": 1, "amendment_id": "A-SCOPE",
            "operation": "scope-replan",
            "affected_pages": [], "affected_batches": [],
            "scope_version_before": "s1", "scope_version_after": "s2",
            "queue_revision_before": 1, "queue_revision_after": 2,
            "state_revision_before": 0, "state_revision_after": 0,
            "coverage_proposal_path": proposal_relative,
            "coverage_proposal_sha256": kblib.sha256_file(proposal_path),
            "cancel_batch_id": None,
        }
        (self.root / plan_relative).write_text(
            kblib.canonical_yaml(plan), encoding="utf-8")
        registered = subprocess.run(
            [sys.executable, str(TOOLS / "register_amendment.py"),
             str(self.root), "--operation", "scope-replan",
             "--plan", plan_relative,
             "--date", time.strftime("%Y-%m-%d", time.gmtime()),
             "--summary", "approved scope change",
             "--approval-reference", "user:fixture-approval",
             "--expected-coverage-sha256",
             kblib.sha256_file(self.coverage_path),
             "--expected-progress-sha256",
             kblib.sha256_file(self.progress_path),
             "--expected-queue-sha256",
             kblib.sha256_file(self.queue_path),
             "--actor-role", "integrator", "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, registered.returncode, registered.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(["A-SCOPE"],
                         result["pending_cross_ledger_amendments"])
        self.assertEqual([], result["ready"])
        completed = self.run_cli("--require-ready", "B1")
        self.assertEqual(2, completed.returncode, completed.stdout)

        progress = kblib.load_yaml_file(self.progress_path)
        progress["amendments"][0].pop("coverage_proposal_sha256")
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("coverage_proposal_sha256 must be sha256", errors)

    def test_verified_queue_replan_requires_persisted_receipt(self):
        queue = self.queue()
        queue["queue_revision"] = 2
        self.write_queue(queue)
        live_sha = kblib.sha256_file(self.queue_path)
        _, receipt = self.add_replan_amendment(
            "A-R1", 1, 2, live_sha, "audit-replan-r1",
            persist_receipt=False,
        )
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("references missing receipt audit-replan-r1", errors)

        # The compile_queue locked preflight may inject this exact receipt,
        # but ordinary validation still refuses non-persisted evidence.
        injected = check_queue.validate_runtime(
            self.root, extra_receipts=[receipt],
        )
        self.assertIn("is not persisted in the repository",
                      "\n".join(injected["errors"]))
        preflight = check_queue.validate_runtime(
            self.root, extra_receipts=[receipt],
            allow_pending_replan_receipts=True,
        )
        self.assertEqual([], preflight["errors"])

    def test_verified_queue_replan_receipt_binding_is_strict(self):
        queue = self.queue()
        queue["queue_revision"] = 2
        self.write_queue(queue)
        live_sha = kblib.sha256_file(self.queue_path)
        self.add_replan_amendment(
            "A-R1", 1, 2, live_sha, "audit-replan-r1",
            receipt_overrides={
                "amendment_id": "WRONG", "actor_role": "worker",
            },
        )
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("amendment_id='WRONG', expected 'A-R1'", errors)
        self.assertIn("actor_role='worker', expected 'integrator'", errors)

    def test_verified_queue_replan_registration_bridges_execution_state_and_time(self):
        queue = self.queue()
        queue["queue_revision"] = 2
        self.write_queue(queue)
        live_sha = kblib.sha256_file(self.queue_path)
        self.add_replan_amendment(
            "A-R1", 1, 2, live_sha, "audit-replan-r1",
        )
        registration_path = self.root / \
            ".cambium/receipts/amendment-registrations.jsonl"
        registration = json.loads(registration_path.read_text(
            encoding="utf-8").strip())
        registration["after_progress_sha256"] = "sha256:" + ("0" * 64)
        registration_path.write_text(json.dumps(registration) + "\n",
                                     encoding="utf-8")
        replan_path = self.root / ".cambium/receipts/replans.jsonl"
        commit = json.loads(replan_path.read_text(encoding="utf-8").strip())
        commit["checked_at"] = "2026-08-03T23:59:59Z"
        replan_path.write_text(json.dumps(commit) + "\n", encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("does not bridge to execution before_progress_sha256",
                      errors)
        self.assertIn("execution receipt predates its registration receipt",
                      errors)

    def test_verified_queue_replan_detects_tampered_after_sha(self):
        queue = self.queue()
        queue["queue_revision"] = 2
        self.write_queue(queue)
        live_sha = kblib.sha256_file(self.queue_path)
        self.add_replan_amendment(
            "A-R1", 1, 2, live_sha, "audit-replan-r1",
            receipt_overrides={
                "after_required_queue_sha256": "sha256:" + ("e" * 64),
            },
        )
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("Amendment after Required Queue SHA does not match", errors)
        self.assertIn("latest replan receipt does not match live Queue bytes",
                      errors)

    def test_consecutive_replans_keep_old_receipt_valid(self):
        queue = self.queue()
        queue["queue_revision"] = 3
        self.write_queue(queue)
        live_sha = kblib.sha256_file(self.queue_path)
        old_sha = "sha256:" + ("b" * 64)
        self.add_replan_amendment(
            "A-R1", 1, 2, old_sha, "audit-replan-r1",
        )
        self.add_replan_amendment(
            "A-R2", 2, 3, live_sha, "audit-replan-r2",
        )
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertNotEqual(old_sha, result["queue_sha256"])

    def test_queue_replan_receipt_cannot_be_reused(self):
        queue = self.queue()
        queue["queue_revision"] = 3
        self.write_queue(queue)
        live_sha = kblib.sha256_file(self.queue_path)
        self.add_replan_amendment(
            "A-R1", 1, 2, "sha256:" + ("b" * 64),
            "audit-replan-shared",
        )
        self.add_replan_amendment(
            "A-R2", 2, 3, live_sha, "audit-replan-shared",
            persist_receipt=False,
        )
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("reuses transaction receipt audit-replan-shared", errors)

    def test_planned_task_cannot_contain_started_lifecycle(self):
        progress = kblib.load_yaml_file(self.progress_path)
        progress["task_state"] = "planned"
        progress["task_transition_receipts"] = []
        progress["checkpoint"] = {
            "recorded_at": None, "summary": None,
            "task_state": "planned", "task_transition_receipt": None,
            "coverage_sha256": None, "required_queue_sha256": None,
            "queue_revision": progress["queue_revision"],
            "queue_state_revision": progress["queue_state_revision"],
        }
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])
        queue = self.queue()
        queue["required_queue"][0]["state"] = "open"
        self.write_queue(queue)
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("task_state=planned but lifecycle has started", errors)

    def test_direct_planned_activation_requires_bound_first_open(self):
        progress = kblib.load_yaml_file(self.progress_path)
        receipt_id = "audit-invalid-direct-activation"
        coverage_sha = kblib.sha256_file(self.coverage_path)
        queue_sha = kblib.sha256_file(self.queue_path)
        receipt = {
            "receipt_id": receipt_id, "tool": "update_task",
            "tool_version": "1.1.0", "check": "task_transition",
            "target": "fixture-task", "result": "pass",
            "invalidated_by": None, "checked_at": "2026-08-04T00:01:00Z",
            "task_id": "fixture-task", "completion_semantics": "build",
            "before_task_state": "planned", "after_task_state": "active",
            "actor_role": "integrator", "queue_revision": 1,
            "queue_state_revision": 0,
            "contract_sha256": check_queue._contract_sha256(progress),
            "before_coverage_sha256": coverage_sha,
            "after_coverage_sha256": coverage_sha,
            "before_required_queue_sha256": queue_sha,
            "after_required_queue_sha256": queue_sha,
            "before_progress_sha256": "sha256:" + "0" * 64,
            "after_progress_sha256": "sha256:" + "1" * 64,
            "evidence_receipt": None,
        }
        kblib.write_receipts(
            self.root / ".cambium/receipts/invalid-activation.jsonl",
            [receipt],
        )
        progress["task_state"] = "active"
        progress["task_transition_receipts"] = [receipt_id]
        progress["checkpoint"] = {
            "recorded_at": receipt["checked_at"],
            "summary": "invalid direct activation",
            "task_state": "active",
            "task_transition_receipt": receipt_id,
            "coverage_sha256": coverage_sha,
            "required_queue_sha256": queue_sha,
            "queue_revision": 1,
            "queue_state_revision": 0,
        }
        self.progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("first_open_batch_id", errors)
        self.assertIn("first_open_transition_receipt", errors)
        self.assertIn("state_revision 1", errors)

    def test_materialized_task_contract_is_receipt_anchored(self):
        baseline = kblib.load_yaml_file(self.progress_path)
        for field, value in (
                ("objective", "silently changed objective"),
                ("contract_version", "c2"),
                ("scope_version", "s2")):
            with self.subTest(field=field):
                progress = copy.deepcopy(baseline)
                progress["contract"][field] = value
                self.progress_path.write_text(
                    kblib.canonical_yaml(progress), encoding="utf-8")
                errors = "\n".join(
                    check_queue.validate_runtime(self.root)["errors"])
                self.assertIn(
                    "contract anchor chain does not bind the current Task "
                    "Contract",
                    errors,
                )

    def test_contract_remains_editable_before_initial_queue_materialization(self):
        queue = self.queue()
        queue["required_queue"] = []
        self.write_queue(queue)
        progress = kblib.load_yaml_file(self.progress_path)
        progress["initial_queue_receipt"] = None
        progress["contract"]["objective"] = "refined before Queue compile"
        self.progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        errors = check_queue.validate_runtime(
            self.root, allow_unmaterialized_queue=True)["errors"]
        self.assertFalse(any("contract anchor" in error for error in errors),
                         errors)

    def test_nonterminal_build_cannot_claim_terminal_audit_ready(self):
        self.make_task_active_without_open()
        progress = kblib.load_yaml_file(self.progress_path)
        progress["terminal_audit"]["state"] = "ready"
        progress["terminal_audit"]["queue_check_receipt"] = "audit-fake"
        self.progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn(
            "build task_state=active requires terminal_audit.state=not-started",
            errors,
        )

    def test_successor_must_name_existing_predecessor(self):
        queue = self.queue()
        queue["required_queue"][1]["successor_of"] = "NO-SUCH"
        self.write_queue(queue)
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("successor_of references unknown batch NO-SUCH", errors)

    def test_queued_hold_transition_requires_full_receipt(self):
        queue = self.queue()
        item = queue["required_queue"][0]
        item["hold_state"] = "blocked"
        item["hold_reason"] = "waiting for input"
        item["transition_receipts"] = ["audit-fake-hold"]
        queue["state_revision"] = 1
        self.write_queue(queue)
        kblib.write_receipts(
            self.root / ".cambium/receipts/fake.jsonl", [{
                "receipt_id": "audit-fake-hold", "result": "pass",
                "after_state_revision": 1,
            }]
        )
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("check=None, expected 'queue_transition'", errors)
        self.assertIn("invalid lifecycle state edge", errors)
        self.assertIn("invalid before_required_queue_sha256", errors)

    def test_retired_top_level_state_authorities_are_rejected(self):
        queue = self.queue()
        queue["active_batches"] = ["B1"]
        self.write_queue(queue)
        progress = kblib.load_yaml_file(self.progress_path)
        progress["active_batches"] = ["B1"]
        progress["merge_queue"] = []
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("Queue has unsupported top-level field(s): active_batches",
                      errors)
        self.assertIn("Progress has unsupported top-level field(s): "
                      "active_batches, merge_queue", errors)

    def test_task_contract_requires_objective_and_explicit_exclusions(self):
        baseline = kblib.load_yaml_file(self.progress_path)
        cases = (
            ("missing objective", lambda contract: contract.pop("objective"),
             "Progress contract misses explicit field(s): objective"),
            ("blank objective", lambda contract: contract.__setitem__(
                "objective", ""),
             "Progress contract.objective must be a non-empty string"),
            ("missing exclusions", lambda contract: contract.pop("exclusions"),
             "Progress contract misses explicit field(s): exclusions"),
            ("duplicate exclusions", lambda contract: contract.__setitem__(
                "exclusions", ["same", "same"]),
             "Progress contract.exclusions must not contain duplicates"),
            ("missing completion semantics", lambda contract: contract.pop(
                "completion_semantics"),
             "Progress contract misses explicit field(s): completion_semantics"),
            ("invalid completion semantics", lambda contract: contract.__setitem__(
                "completion_semantics", "mixed"),
             "completion_semantics must be build or maintenance"),
        )
        for label, mutate, expected in cases:
            with self.subTest(label=label):
                progress = copy.deepcopy(baseline)
                mutate(progress["contract"])
                self.progress_path.write_text(
                    kblib.canonical_yaml(progress), encoding="utf-8")
                errors = "\n".join(
                    check_queue.validate_runtime(self.root)["errors"])
                self.assertIn(expected, errors)

    def write_guidance_queue(self, entries):
        progress = kblib.load_yaml_file(self.progress_path)
        progress["guidance_queue"] = entries
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        self.refresh_initial_origin()
        return progress

    def guidance_errors(self):
        return "\n".join(
            error for error in check_queue.validate_runtime(self.root)["errors"]
            if "guidance_queue" in error
        )

    def test_guidance_records_use_kernel_field_names_and_closed_values(self):
        self.write_guidance_queue([
            {"guidance_id": "G-%03d" % index, "disposition": disposition,
             "status": "verified"}
            for index, disposition in enumerate(
                sorted(check_queue.GUIDANCE_DISPOSITIONS), start=1)
        ])
        self.assertEqual("", self.guidance_errors())

    def test_guidance_record_rejects_retired_field_names(self):
        self.write_guidance_queue([
            {"id": "G-001", "class": "apply-to-current-batch",
             "status": "verified"},
        ])
        errors = self.guidance_errors()
        self.assertIn("Progress guidance_queue[0] misses explicit field(s): "
                      "disposition, guidance_id", errors)
        self.assertIn("Progress guidance_queue[0] has unsupported field(s): "
                      "class, id", errors)

    def test_guidance_disposition_and_status_domains_are_closed(self):
        cases = (
            ("unknown disposition",
             {"guidance_id": "G-001", "disposition": "NOT-A-DISPOSITION-AT-ALL",
              "status": "verified"},
             "Progress guidance_queue[0] disposition has invalid value "
             "'NOT-A-DISPOSITION-AT-ALL'"),
            ("status borrowed from the disposition list",
             {"guidance_id": "G-001", "disposition": "queue-next",
              "status": "queue-next"},
             "Progress guidance_queue[0] status has invalid value "
             "'queue-next'"),
            ("misspelled final status",
             {"guidance_id": "G-001", "disposition": "queue-next",
              "status": "verifed"},
             "Progress guidance_queue[0] status has invalid value 'verifed'"),
        )
        for label, entry, expected in cases:
            with self.subTest(label=label):
                self.write_guidance_queue([entry])
                self.assertIn(expected, self.guidance_errors())

    def test_guidance_id_uniqueness_and_intermediate_status_stay_pending(self):
        progress = self.write_guidance_queue([
            {"guidance_id": "G-001", "disposition": "queue-next",
             "status": "mapped"},
            {"guidance_id": "G-001", "disposition": "queue-next",
             "status": "verified"},
        ])
        self.assertIn("Progress guidance_queue repeats guidance_id G-001",
                      self.guidance_errors())
        # `mapped` is an intermediate K13/06 status: structurally valid, and it
        # keeps the guidance pending for resume and batch close.
        pending_guidance, _ = check_queue._pending_control_ids(progress)
        self.assertEqual(["G-001"], pending_guidance)

    def test_last_reconciled_guidance_id_is_derived_not_stored(self):
        progress = self.write_guidance_queue([
            {"guidance_id": "G-001", "disposition": "queue-next",
             "status": "verified"},
            {"guidance_id": "G-002", "disposition": "queue-next",
             "status": "mapped"},
            {"guidance_id": "G-003", "disposition": "queue-next",
             "status": "received"},
            {"guidance_id": "G-004", "disposition": "queue-next",
             "status": "verified"},
        ])
        # The boundary is the longest recorded prefix that has left
        # `received`; the entries after it stay in pending_guidance.
        self.assertEqual("G-002",
                         check_queue._last_reconciled_guidance_id(progress))
        self.assertEqual(["G-002", "G-003"],
                         check_queue._pending_control_ids(progress)[0])
        # No checkpoint slot is created for it.
        self.assertNotIn("last_reconciled_guidance_id",
                         check_queue.CHECKPOINT_FIELDS)
        checkpoint = dict(progress["checkpoint"] or {})
        checkpoint["last_reconciled_guidance_id"] = "G-004"
        progress["checkpoint"] = checkpoint
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        self.assertIn(
            "Progress checkpoint has unsupported field(s): "
            "last_reconciled_guidance_id",
            "\n".join(check_queue.validate_runtime(self.root)["errors"]))

    def test_derived_guidance_boundary_is_monotone_over_mixed_dispositions(self):
        cases = (
            ("empty queue", [], None),
            ("only unreconciled",
             [{"guidance_id": "G-001", "disposition": "queue-next",
               "status": "received"}], None),
            ("superseded and deferred still count as reconciled",
             [{"guidance_id": "G-001", "disposition": "superseded",
               "status": "superseded"},
              {"guidance_id": "G-002", "disposition": "deferred",
               "status": "deferred"},
              {"guidance_id": "G-003", "disposition": "queue-next",
               "status": "mapped"}], "G-003"),
            ("a new received entry does not lower the boundary",
             [{"guidance_id": "G-001", "disposition": "superseded",
               "status": "superseded"},
              {"guidance_id": "G-002", "disposition": "deferred",
               "status": "deferred"},
              {"guidance_id": "G-003", "disposition": "queue-next",
               "status": "mapped"},
              {"guidance_id": "G-004", "disposition": "queue-next",
               "status": "received"}], "G-003"),
        )
        for label, entries, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(
                    expected,
                    check_queue._last_reconciled_guidance_id(
                        {"guidance_queue": entries}))

    def test_resume_status_reports_the_derived_guidance_boundary(self):
        receipt_path = ".cambium/receipts/resume.jsonl"
        self.write_guidance_queue([
            {"guidance_id": "G-001", "disposition": "apply-to-current-batch",
             "status": "verified"},
            {"guidance_id": "G-002", "disposition": "queue-next",
             "status": "mapped"},
        ])
        completed = self.run_cli("--resume-status", "--receipts", receipt_path)
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("last_reconciled_guidance_id=G-002", completed.stdout)
        self.assertIn("pending_guidance=G-002", completed.stdout)
        receipt = json.loads(
            (self.root / receipt_path).read_text(encoding="utf-8"))
        self.assertEqual("G-002", receipt["last_reconciled_guidance_id"])

    def test_unknown_coverage_disposition_cannot_disappear_from_queue(self):
        coverage = kblib.load_yaml_file(self.coverage_path)
        coverage["pages"][1]["coverage_disposition"] = "reuqired"
        self.coverage_path.write_text(kblib.canonical_yaml(coverage),
                                      encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("coverage_disposition must be one of", errors)
        self.assertIn("found 'reuqired'", errors)

    def test_coverage_page_missing_core_field_fails_closed(self):
        coverage = kblib.load_yaml_file(self.coverage_path)
        coverage["pages"][0].pop("gate_receipts")
        self.coverage_path.write_text(kblib.canonical_yaml(coverage),
                                      encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("misses core field(s): gate_receipts", errors)
        self.assertIn("gate_receipts must be an explicit string list", errors)

    def test_global_transition_history_requires_exact_complete_chain(self):
        sha_a = "sha256:" + ("a" * 64)
        sha_b = "sha256:" + ("b" * 64)
        sha_c = "sha256:" + ("c" * 64)
        gate = {
            "receipt_id": "gate-open", "result": "pass",
            "invalidated_by": None,
        }
        batch_gate = {
            "receipt_id": "gate-merge", "result": "pass",
            "invalidated_by": None,
        }
        first = {
            "receipt_id": "transition-1", "tool": "update_queue",
            "tool_version": "1.2.0", "check": "queue_transition",
            "target": "B1", "result": "pass", "invalidated_by": None,
            "task_id": "fixture-task", "actor_role": "integrator",
            "checked_at": "2026-08-04T01:00:00Z",
            "queue_revision": 1, "before_state_revision": 0,
            "after_state_revision": 1, "before_state": "queued",
            "after_state": "open", "before_hold_state": "none",
            "after_hold_state": "none", "evidence_receipt": "gate-open",
            "before_required_queue_sha256": sha_a,
            "after_required_queue_sha256": sha_b,
        }
        second = dict(first, **{
            "receipt_id": "transition-2",
            "checked_at": "2026-08-04T02:00:00Z",
            "before_state_revision": 1, "after_state_revision": 2,
            "before_state": "open", "after_state": "merge-ready",
            "evidence_receipt": "gate-merge",
            "before_required_queue_sha256": sha_b,
            "after_required_queue_sha256": sha_c,
        })
        items = {"B1": {
            "transition_receipts": ["transition-1", "transition-2"],
        }}
        catalog = {
            "gate-open": ("receipts.jsonl", gate),
            "gate-merge": ("receipts.jsonl", batch_gate),
            "transition-1": ("receipts.jsonl", first),
            "transition-2": ("receipts.jsonl", second),
        }
        queue = {"state_revision": 2, "queue_revision": 1}
        self.assertEqual([], check_queue._global_transition_errors(
            items, catalog, queue, sha_c,
        ))

        missing = {"B1": {"transition_receipts": ["transition-2"]}}
        errors = "\n".join(check_queue._global_transition_errors(
            missing, catalog, queue, sha_c,
        ))
        self.assertIn("missing=[1]", errors)

        duplicate = dict(second, receipt_id="transition-2b")
        duplicate_catalog = dict(catalog)
        duplicate_catalog["transition-2b"] = ("receipts.jsonl", duplicate)
        duplicate_items = {
            "B1": {"transition_receipts": ["transition-1", "transition-2"]},
            "B2": {"transition_receipts": ["transition-2b"]},
        }
        errors = "\n".join(check_queue._global_transition_errors(
            duplicate_items, duplicate_catalog, queue, sha_c,
        ))
        self.assertIn("repeated=[2]", errors)

    def test_global_transition_rejects_noop_actor_time_and_broken_sha(self):
        receipt = {
            "receipt_id": "transition-bad", "tool": "update_queue",
            "tool_version": "1.2.0", "check": "queue_transition",
            "target": "B1", "result": "pass", "invalidated_by": None,
            "task_id": "fixture-task", "actor_role": "worker",
            "checked_at": "not-a-time", "queue_revision": 1,
            "before_state_revision": 0, "after_state_revision": 1,
            "before_state": "queued", "after_state": "queued",
            "before_hold_state": "none", "after_hold_state": "none",
            "evidence_receipt": None,
            "before_required_queue_sha256": "sha256:" + ("a" * 64),
            "after_required_queue_sha256": "sha256:" + ("b" * 64),
        }
        errors = "\n".join(check_queue._global_transition_errors(
            {"B1": {"transition_receipts": ["transition-bad"]}},
            {"transition-bad": ("receipts.jsonl", receipt)},
            {"state_revision": 1, "queue_revision": 1},
            "sha256:" + ("c" * 64),
        ))
        self.assertIn("actor_role must be integrator", errors)
        self.assertIn("checked_at must be", errors)
        self.assertIn("state/hold no-op", errors)
        self.assertIn("latest transition receipt does not match", errors)

        receipt.update({
            "actor_role": "integrator",
            "checked_at": "2026-08-04T01:00:00Z",
            "before_state": "queued", "after_state": "closed",
        })
        errors = "\n".join(check_queue._global_transition_errors(
            {"B1": {"transition_receipts": ["transition-bad"]}},
            {"transition-bad": ("receipts.jsonl", receipt)},
            {"state_revision": 1, "queue_revision": 1},
            receipt["after_required_queue_sha256"],
        ))
        self.assertIn("illegal lifecycle edge", errors)

    def test_closed_delta_apply_receipt_is_historical_and_strict(self):
        queue = {
            "task_id": "fixture-task", "queue_revision": 4,
            "state_revision": 9,
        }
        item = {
            "id": "B1", "delta_path": ".cambium/deltas/B1.yaml",
            "delta_apply_receipt": "audit-delta-b1",
            "delta_sha256": "sha256:" + ("c" * 64),
        }
        before_queue_sha = "sha256:" + ("a" * 64)
        preclose_coverage_sha = "sha256:" + ("b" * 64)
        transition = {
            "queue_revision": 2, "before_state_revision": 5,
            "before_required_queue_sha256": before_queue_sha,
            "before_coverage_sha256": preclose_coverage_sha,
            "delta_apply_receipt": "audit-delta-b1",
        }
        receipt = {
            "receipt_id": "audit-delta-b1", "tool": "apply_delta",
            "tool_version": "1.4.0", "check": "delta_apply",
            "target": "B1", "result": "pass", "invalidated_by": None,
            "task_id": "fixture-task", "batch_id": "B1",
            "actor_role": "integrator",
            "coverage_ledger_path": check_queue.COVERAGE_PATH,
            "delta_path": ".cambium/deltas/B1.yaml",
            "delta_sha256": "sha256:" + ("c" * 64),
            "before_coverage_sha256": "sha256:" + ("d" * 64),
            "after_coverage_sha256": preclose_coverage_sha,
            "required_queue_sha256": before_queue_sha,
            "queue_revision": 2, "queue_state_revision": 5,
        }
        catalog = {"audit-delta-b1": ("delta.jsonl", receipt)}
        self.assertEqual([], check_queue._closed_delta_apply_errors(
            item, transition, catalog, queue,
        ))

        receipt["after_coverage_sha256"] = "sha256:" + ("e" * 64)
        errors = "\n".join(check_queue._closed_delta_apply_errors(
            item, transition, catalog, queue,
        ))
        self.assertIn("expected", errors)
        pending_catalog = {"audit-delta-b1": ("<pending-write>", receipt)}
        errors = "\n".join(check_queue._closed_delta_apply_errors(
            item, transition, pending_catalog, queue,
        ))
        self.assertIn("not persisted in the repository", errors)

    def test_nonqueued_state_requires_transition_receipt(self):
        queue = self.queue()
        item = queue["required_queue"][0]
        item.update({
            "state": "open", "opened_at": "2026-08-04T01:00:00Z",
            "activation_receipt": "audit-ready-1",
        })
        self.write_queue(queue)
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("requires non-empty transition_receipts", errors)

    def test_executing_batch_cannot_bypass_unclosed_dependency(self):
        before_sha = kblib.sha256_file(self.queue_path)
        queue = self.queue()
        item = queue["required_queue"][1]
        item.update({
            "state": "open",
            "opened_at": "2026-08-04T01:00:00Z",
            "activation_receipt": "audit-ready-b2",
            "transition_receipts": ["audit-transition-b2-open"],
        })
        queue["state_revision"] = 1
        self.write_queue(queue)
        receipts = [
            {
                "receipt_id": "audit-ready-b2", "tool": "check_queue",
                "tool_version": check_queue.TOOL_VERSION,
                "check": "required_queue", "queue_check_mode": "require-ready:B2",
                "result": "pass", "invalidated_by": None,
                "task_id": "fixture-task", "queue_revision": 1,
                "queue_state_revision": 0,
                "required_queue_sha256": before_sha,
            },
            {
                "receipt_id": "audit-transition-b2-open",
                "tool": "update_queue", "tool_version": "1.2.0",
                "check": "queue_transition", "target": "B2",
                "result": "pass", "invalidated_by": None,
                "task_id": "fixture-task", "queue_revision": 1,
                "before_state": "queued", "after_state": "open",
                "before_hold_state": "none", "after_hold_state": "none",
                "before_state_revision": 0, "after_state_revision": 1,
                "before_required_queue_sha256": before_sha,
                "after_required_queue_sha256": kblib.sha256_file(self.queue_path),
            },
        ]
        receipt_path = self.root / ".cambium/receipts/history.jsonl"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            "".join(json.dumps(receipt) + "\n" for receipt in receipts),
            encoding="utf-8",
        )
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("dependency B1 is queued, not closed", errors)

    def test_unfinished_required_object_needs_next_batch(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        coverage["pages"][0]["next_batch"] = None
        coverage_path.write_text(kblib.canonical_yaml(coverage), encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("has no explicit next_batch", errors)

    def test_materialized_batch_specs_are_a_closed_contract(self):
        baseline = kblib.load_yaml_file(self.coverage_path)
        cases = (
            ("missing", "source_route",
             "misses required field(s): source_route"),
            ("extra", "runtime_hint",
             "has unsupported field(s): runtime_hint"),
        )
        for action, field, expected in cases:
            with self.subTest(action=action, field=field):
                coverage = copy.deepcopy(baseline)
                if action == "missing":
                    del coverage["batch_specs"][0][field]
                else:
                    coverage["batch_specs"][0][field] = "not-owned-here"
                self.coverage_path.write_text(
                    kblib.canonical_yaml(coverage), encoding="utf-8")
                errors = "\n".join(
                    check_queue.validate_runtime(self.root)["errors"])
                self.assertIn(
                    "Coverage batch_specs[0] %s" % expected, errors)

    def test_batch_id_must_be_safe_single_segment(self):
        queue = self.queue()
        queue["required_queue"][0]["id"] = "../B1"
        self.write_queue(queue)
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("id must match", errors)

    def test_held_ready_gate_returns_two(self):
        self.make_task_active_without_open()
        queue = self.queue()
        held = subprocess.run(
            [sys.executable, str(TOOLS / "update_queue.py"), str(self.root),
             "--id", "B1", "--hold-state", "blocked", "--reason",
             "human input needed", "--expected-state-revision",
             str(queue["state_revision"]), "--expected-sha256",
             kblib.sha256_file(self.queue_path), "--actor-role",
             "integrator", "--apply"], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, held.returncode, held.stdout)
        completed = self.run_cli("--require-ready", "B1")
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("not executable", completed.stdout)

    def test_empty_queue_cannot_prove_completion(self):
        queue = self.queue()
        queue["required_queue"] = []
        self.write_queue(queue)
        progress = kblib.load_yaml_file(self.progress_path)
        progress["initial_queue_receipt"] = None
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        coverage = kblib.load_yaml_file(self.root / check_queue.COVERAGE_PATH)
        coverage["pages"] = []
        coverage["batch_specs"] = []
        (self.root / check_queue.COVERAGE_PATH).write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        completed = self.run_cli("--require-complete")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("empty Queue cannot prove completion", completed.stdout)

    def test_success_receipt_has_terminal_link_fields(self):
        receipts = ".cambium/receipts/check.jsonl"
        completed = self.run_cli("--receipts", receipts)
        self.assertEqual(0, completed.returncode, completed.stdout)
        import json
        receipt = json.loads((self.root / receipts).read_text(encoding="utf-8"))
        self.assertEqual("check_queue", receipt["tool"])
        self.assertEqual("consistency", receipt["queue_check_mode"])
        self.assertEqual(check_queue.TOOL_VERSION, receipt["tool_version"])
        self.assertEqual("fixture-task", receipt["task_id"])
        self.assertEqual(1, receipt["queue_revision"])
        self.assertEqual(0, receipt["queue_state_revision"])
        self.assertEqual(2, receipt["remaining_required_work_units"])
        self.assertRegex(receipt["required_queue_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            kblib.repository_snapshot_sha256(self.root),
            receipt["repository_snapshot_sha256"],
        )

    def test_resume_status_reports_canonical_state_and_receipt(self):
        receipt_path = ".cambium/receipts/resume.jsonl"
        completed = self.run_cli(
            "--resume-status", "--receipts", receipt_path,
        )
        self.assertEqual(2, completed.returncode, completed.stdout)
        for expected in (
                "task_id=fixture-task", "task_state=planned",
                'objective="Complete fixture Required Queue batches with durable evidence."',
                'exclusions=["Do not modify profile policy."]',
                "scope_version=s1", "standards_version=3.0.0",
                "selected_profile_manifest=profiles/test-profile/profile.md",
                "queue_revision=1", "state_revision=0",
                "checkpoint.recorded_at=None",
                "checkpoint.binding=initial",
                "last_reconciled_guidance_id=none",
                "task_transition.latest=none",
                "next_action=activate-ready-batch:B1",
                "batches.queued=B1,B2",
                "batches.open=none", "holds=none", "deltas=none",
                "locks=none", "resume the existing task with ready batch(es) B1"):
            self.assertIn(expected, completed.stdout)
        receipt = json.loads(
            (self.root / receipt_path).read_text(encoding="utf-8")
        )
        self.assertEqual("resume-status", receipt["queue_check_mode"])
        self.assertEqual("planned", receipt["task_state"])
        self.assertEqual(
            "Complete fixture Required Queue batches with durable evidence.",
            receipt["objective"])
        self.assertEqual(["Do not modify profile policy."],
                         receipt["exclusions"])
        self.assertEqual("planned", receipt["checkpoint"]["task_state"])
        self.assertEqual("initial", receipt["checkpoint_binding"])
        self.assertEqual([], receipt["managed_deltas"])
        self.assertEqual([], receipt["writer_locks"])

    def test_writer_lock_fails_closed_and_exposes_owner(self):
        lock = self.root / ".cambium/tmp/state-writer.lock"
        lock.mkdir()
        owner = {
            "lock_name": "state-writer", "pid": 4242,
            "created_at": "2026-08-04T00:01:00Z",
        }
        (lock / "owner.json").write_text(
            json.dumps(owner) + "\n", encoding="utf-8",
        )
        for arguments, expected_code in (
                ((), 2),
                (("--require-ready", "B1"), 2),
                (("--resume-status",), 2),
                (("--require-complete",), 1)):
            with self.subTest(arguments=arguments):
                completed = self.run_cli(*arguments)
                self.assertEqual(expected_code, completed.returncode,
                                 completed.stdout)
                self.assertIn(
                    "active or interrupted writer lock(s): "
                    ".cambium/tmp/state-writer.lock", completed.stdout,
                )
        resumed = self.run_cli("--resume-status")
        self.assertIn('"pid": 4242', resumed.stdout)
        self.assertIn("verify that no writer process remains", resumed.stdout)

    def test_interrupted_apply_delta_reports_planned_after_and_receipt(self):
        coverage_sha = kblib.sha256_file(self.coverage_path)
        queue_sha = kblib.sha256_file(self.queue_path)
        receipt_relative = ".cambium/receipts/audit-delta.jsonl"
        receipt_id = "audit-apply_delta-fixture"
        self.write_writer_lock({
            "tool": "apply_delta",
            "action": "apply-canonical-coverage-delta",
            "batch_id": "B1",
            "task_id": "fixture-task",
            "before_coverage_sha256": "sha256:" + "0" * 64,
            "planned_after_coverage_sha256": coverage_sha,
            "before_required_queue_sha256": queue_sha,
            "planned_after_required_queue_sha256": queue_sha,
            "before_progress_sha256": kblib.sha256_file(self.progress_path),
            "planned_after_progress_sha256":
                kblib.sha256_file(self.progress_path),
            "delta_sha256": "sha256:" + "1" * 64,
            "required_queue_sha256": queue_sha,
            "receipt_id": receipt_id,
            "receipt_path": receipt_relative,
        })
        receipt_path = self.root / receipt_relative
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps({
            "receipt_id": receipt_id,
            "tool": "apply_delta",
            "check": "delta_apply",
            "target": "B1",
            "task_id": "fixture-task",
            "batch_id": "B1",
            "result": "pass",
            "before_coverage_sha256": "sha256:" + "0" * 64,
            "after_coverage_sha256": coverage_sha,
            "before_required_queue_sha256": queue_sha,
            "after_required_queue_sha256": queue_sha,
            "before_progress_sha256": kblib.sha256_file(self.progress_path),
            "after_progress_sha256": kblib.sha256_file(self.progress_path),
            "delta_sha256": "sha256:" + "1" * 64,
        }) + "\n", encoding="utf-8")

        completed = self.run_cli("--resume-status")
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("state.coverage phase=planned-after", completed.stdout)
        self.assertIn("state.progress phase=before", completed.stdout)
        self.assertIn("state.queue phase=before", completed.stdout)
        self.assertIn('"matching_receipt": true', completed.stdout)
        self.assertIn('"result": "pass"', completed.stdout)
        self.assertIn('"status": "matching"', completed.stdout)
        self.assertIn(
            "reconciliation_hint=live state mixes before and planned-after "
            "fingerprints", completed.stdout,
        )

        receipt_path.unlink()
        absent = self.run_cli("--resume-status")
        self.assertEqual(2, absent.returncode, absent.stdout)
        self.assertIn('"matching_receipt": false', absent.stdout)
        self.assertIn('"status": "absent"', absent.stdout)

    def test_interrupted_writer_distinguishes_mixed_and_other_bytes(self):
        coverage_sha = kblib.sha256_file(self.coverage_path)
        queue_sha = kblib.sha256_file(self.queue_path)
        lock = self.write_writer_lock({
            "tool": "compile_queue",
            "action": "initial-compile",
            "before_coverage_sha256": "sha256:" + "0" * 64,
            "planned_after_coverage_sha256": coverage_sha,
            "before_required_queue_sha256": queue_sha,
            "planned_after_required_queue_sha256": "sha256:" + "1" * 64,
            "receipt_id": "audit-compile-fixture",
            "receipt_path": ".cambium/receipts/compile.jsonl",
        })
        mixed = self.run_cli("--resume-status")
        self.assertEqual(2, mixed.returncode, mixed.stdout)
        self.assertIn("state.coverage phase=planned-after", mixed.stdout)
        self.assertIn("state.queue phase=before", mixed.stdout)
        self.assertIn("reconciliation_hint=live state mixes before and "
                      "planned-after fingerprints", mixed.stdout)

        owner_path = lock / "owner.json"
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        owner["operation"]["planned_after_coverage_sha256"] = \
            "sha256:" + "2" * 64
        owner_path.write_text(json.dumps(owner) + "\n", encoding="utf-8")
        other = self.run_cli("--resume-status")
        self.assertEqual(2, other.returncode, other.stdout)
        self.assertIn("state.coverage phase=other", other.stdout)
        self.assertIn("reconciliation_hint=live state differs from recorded "
                      "before/planned-after fingerprints", other.stdout)

    def test_resume_status_paused_checkpoint_requires_explicit_resume(self):
        paused = subprocess.run(
            [sys.executable, str(TOOLS / "update_task.py"), str(self.root),
             "--transition", "paused", "--checkpoint-summary",
             "interrupted after inventory", "--at",
             "2026-08-04T00:02:00Z", "--expected-progress-sha256",
             kblib.sha256_file(self.progress_path),
             "--expected-queue-sha256", kblib.sha256_file(self.queue_path),
             "--actor-role", "integrator", "--apply"], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, paused.returncode, paused.stdout)
        completed = self.run_cli("--resume-status")
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("existing task_state=paused is non-terminal",
                      completed.stdout)
        self.assertIn("checkpoint.recorded_at=2026-08-04T00:02:00Z",
                      completed.stdout)
        self.assertIn('checkpoint.summary="interrupted after inventory"',
                      completed.stdout)
        self.assertIn("resume or resolve the existing paused task from its checkpoint",
                      completed.stdout)

    def test_resume_status_rejects_false_terminal_task_state(self):
        progress = kblib.load_yaml_file(self.progress_path)
        progress["task_state"] = "complete"
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        completed = self.run_cli("--resume-status")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("task_state=complete but 2 Required work unit(s) remain",
                      completed.stdout)
        self.assertIn("repair and reconcile the existing runtime",
                      completed.stdout)

    def test_resume_status_lists_invalid_unapplied_delta(self):
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text("batch: B1\npages: []\n", encoding="utf-8")
        completed = self.run_cli("--resume-status")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("unapplied delta", completed.stdout)
        self.assertIn(
            "delta=.cambium/deltas/B1.yaml batch=B1 state=queued",
            completed.stdout,
        )
        self.assertIn("repair and reconcile the existing runtime",
                      completed.stdout)

    def test_resume_status_rejects_generic_amendment_as_cancellation(self):
        progress = kblib.load_yaml_file(self.progress_path)
        progress["amendments"] = [
            {"id": "A-CANCEL-B1", "date": "2026-08-04",
             "summary": "cancel B1", "writeback_done": True},
            {"id": "A-CANCEL-B2", "date": "2026-08-04",
             "summary": "cancel B2", "writeback_done": True},
        ]
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        coverage_path = self.root / check_queue.COVERAGE_PATH
        for index, batch_id in enumerate(("B1", "B2")):
            before_queue_sha = kblib.sha256_file(self.queue_path)
            coverage = kblib.load_yaml_file(coverage_path)
            record = coverage["pages"][index]
            record["coverage_disposition"] = "deferred"
            record["deferred_reason"] = "task cancelled"
            record["reentry_condition"] = "new task Amendment"
            record["next_batch"] = None
            coverage_path.write_text(kblib.canonical_yaml(coverage),
                                     encoding="utf-8")
            queue = self.queue()
            item = queue["required_queue"][index]
            receipt_id = "audit-amendment-cancel-%s" % batch_id.lower()
            item.update({
                "state": "cancelled", "hold_state": "none",
                "cancelled_at": "2026-08-04T0%d:00:00Z" % (index + 1),
                "cancellation_amendment": "A-CANCEL-%s" % batch_id,
                "transition_receipts": [receipt_id],
            })
            before_revision = queue["state_revision"]
            queue["state_revision"] = before_revision + 1
            queue_text = kblib.canonical_yaml(queue)
            self.write_queue(queue)
            kblib.write_receipts(
                self.root / ".cambium/receipts/amendment-history.jsonl", [{
                    "receipt_id": receipt_id,
                    "tool": "apply_amendment", "tool_version": "1.1.0",
                    "check": "queue_transition", "target": batch_id,
                    "result": "pass", "invalidated_by": None,
                    "actor_role": "integrator",
                    "checked_at": "2026-08-04T0%d:00:00Z" % (index + 1),
                    "task_id": "fixture-task", "queue_revision": 1,
                    "before_state": "queued", "after_state": "cancelled",
                    "before_hold_state": "none", "after_hold_state": "none",
                    "before_state_revision": before_revision,
                    "after_state_revision": before_revision + 1,
                    "before_required_queue_sha256": before_queue_sha,
                    "after_required_queue_sha256":
                        kblib.sha256_bytes(queue_text),
                }])
        progress = kblib.load_yaml_file(self.progress_path)
        progress["task_state"] = "cancelled"
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        validation = check_queue.validate_runtime(self.root)
        self.assertTrue(validation["errors"])
        self.assertTrue(any("cancellation Amendment" in error
                            for error in validation["errors"]),
                        validation["errors"])
        self.assertEqual(0, validation["remaining"])
        completed = self.run_cli("--resume-status")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("cancellation Amendment", completed.stdout)

    def test_receipt_path_cannot_overwrite_authoritative_state(self):
        queue = self.queue_path.read_bytes()
        completed = self.run_cli(
            "--receipts", ".cambium/state/required_queue.yaml"
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual(queue, self.queue_path.read_bytes())

    def test_state_file_symlink_is_rejected(self):
        outside = Path(self.tmp.name) / "outside.yaml"
        outside.write_text(self.queue_path.read_text(encoding="utf-8"),
                           encoding="utf-8")
        self.queue_path.unlink()
        self.queue_path.symlink_to(outside)
        errors = check_queue.validate_runtime(self.root)["errors"]
        self.assertTrue(any("symlink" in error or "outside" in error
                            for error in errors), errors)

    def test_unapplied_or_unknown_managed_delta_fails(self):
        delta_dir = self.root / ".cambium/deltas"
        delta_dir.mkdir(parents=True, exist_ok=True)
        (delta_dir / "B1.yaml").write_text("batch: B1\npages: []\n",
                                            encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("unapplied delta", errors)
        (delta_dir / "B1.yaml").unlink()
        (delta_dir / "UNKNOWN.yaml").write_text(
            "batch: UNKNOWN\npages: []\n", encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("unknown batch UNKNOWN", errors)

    def init_profile_repo(self, override_rows=""):
        fresh = Path(self.tmp.name) / ("cap-%d" % len(
            list(Path(self.tmp.name).glob("cap-*"))))
        (fresh / "profiles" / "sample").mkdir(parents=True)
        (fresh / "profiles" / "sample" / "profile.md").write_text(
            "# Profile\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n\n"
            "## Execution Default Overrides\n\n"
            "| Override item ID from the registry | Non-default profile value |\n"
            "|---|---|\n" + override_rows, encoding="utf-8")
        return fresh

    def run_init(self, root, *extra):
        return subprocess.run(
            [sys.executable, str(TOOLS / "init_state.py"), str(root),
             "--task-id", "cap-task", "--objective", "Exercise the cap",
             "--exclude", "Do not infer Required work",
             "--scope-version", "s1", "--completion-semantics", "build",
             "--standards-version", "3.0.0", "--profile-manifest",
             "profiles/sample/profile.md", "--at", "2026-08-04T00:00:00Z",
             "--apply", *extra],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def test_profile_manifest_concurrency_cap_override_reaches_progress(self):
        fresh = self.init_profile_repo("| `concurrency_cap` | `5` |\n")
        completed = self.run_init(fresh)
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("concurrency_cap=5 (resolved from profile-manifest)",
                      completed.stdout)
        progress = kblib.load_yaml_file(fresh / check_queue.PROGRESS_PATH)
        self.assertEqual(5, progress["contract"]["concurrency_cap"])

    def test_unregistered_override_keeps_the_kernel_default_cap(self):
        fresh = self.init_profile_repo()
        completed = self.run_init(fresh)
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("concurrency_cap=3 (resolved from kernel-default)",
                      completed.stdout)
        progress = kblib.load_yaml_file(fresh / check_queue.PROGRESS_PATH)
        self.assertEqual(3, progress["contract"]["concurrency_cap"])

    def test_two_explicit_concurrency_cap_overrides_must_agree(self):
        fresh = self.init_profile_repo("| `concurrency_cap` | `5` |\n")
        conflicting = self.run_init(fresh, "--concurrency-cap", "2")
        self.assertEqual(1, conflicting.returncode, conflicting.stdout)
        self.assertIn("contradicts the selected profile manifest's registered "
                      "concurrency_cap 5", conflicting.stdout)
        self.assertFalse((fresh / ".cambium").exists())
        agreeing = self.run_init(fresh, "--concurrency-cap", "5")
        self.assertEqual(0, agreeing.returncode, agreeing.stdout)
        self.assertIn("concurrency_cap=5 (resolved from "
                      "task-contract+profile-manifest)", agreeing.stdout)

    def test_unusable_profile_concurrency_cap_fails_closed(self):
        for value in ("many", "0", "-1", "2.5"):
            with self.subTest(value=value):
                fresh = self.init_profile_repo(
                    "| `concurrency_cap` | `%s` |\n" % value)
                completed = self.run_init(fresh)
                self.assertEqual(1, completed.returncode, completed.stdout)
                self.assertIn("K13/10 requires a positive integer",
                              completed.stdout)
                self.assertFalse((fresh / ".cambium").exists())

    def test_init_creates_empty_state_without_fake_work_and_refuses_overwrite(self):
        fresh = Path(self.tmp.name) / "fresh"
        (fresh / "profiles" / "sample").mkdir(parents=True)
        (fresh / "profiles" / "sample" / "profile.md").write_text(
            "# Profile\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n", encoding="utf-8")
        command = [
            sys.executable, str(TOOLS / "init_state.py"), str(fresh),
            "--task-id", "new-task", "--objective",
            "Exercise an empty resumable task", "--exclude",
            "Do not infer Required work", "--scope-version", "s1",
            "--completion-semantics", "build",
            "--standards-version", "3.0.0", "--profile-manifest",
            "profiles/sample/profile.md", "--at", "2026-08-04T00:00:00Z",
            "--apply",
        ]
        first = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, first.returncode, first.stdout)
        self.assertIn("queue_revision=1 state_revision=0", first.stdout)
        self.assertIn("required_queue_sha256=sha256:", first.stdout)
        queue = kblib.load_yaml_file(fresh / check_queue.QUEUE_PATH)
        self.assertEqual([], queue["required_queue"])
        progress = kblib.load_yaml_file(fresh / check_queue.PROGRESS_PATH)
        self.assertEqual("Exercise an empty resumable task",
                         progress["contract"]["objective"])
        self.assertEqual(["Do not infer Required work"],
                         progress["contract"]["exclusions"])
        self.assertEqual("build",
                         progress["contract"]["completion_semantics"])
        resumed = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(fresh),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        for expected in (
                "task_id=new-task", "task_state=planned",
                'objective="Exercise an empty resumable task"',
                'exclusions=["Do not infer Required work"]',
                "live.coverage_sha256=sha256:",
                "live.progress_sha256=sha256:",
                "live.required_queue_sha256=sha256:",
                "checkpoint.recorded_at=None",
                "checkpoint.binding=initial", "deltas=none", "locks=none"):
            self.assertIn(expected, resumed.stdout)
        self.assertEqual(
            ["next_action=materialize-required-queue"],
            [line for line in resumed.stdout.splitlines()
             if line.startswith("next_action=")],
            resumed.stdout,
        )
        second = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        self.assertEqual(1, second.returncode, second.stdout)
        self.assertIn("nothing was overwritten", second.stdout)
        self.assertIn("task_id=new-task", second.stdout)
        self.assertIn("task_state=planned", second.stdout)
        self.assertIn("queue_revision=1", second.stdout)
        self.assertIn("state_revision=0", second.stdout)
        self.assertIn("Tools/check_queue.py", second.stdout)
        self.assertIn("--resume-status", second.stdout)

    def test_init_requires_and_materializes_one_completion_semantics(self):
        fresh = Path(self.tmp.name) / "maintenance-init"
        (fresh / "profiles" / "sample").mkdir(parents=True)
        (fresh / "profiles" / "sample" / "profile.md").write_text(
            "# Profile\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n", encoding="utf-8")
        base = [
            sys.executable, str(TOOLS / "init_state.py"), str(fresh),
            "--task-id", "maintenance-task", "--objective",
            "Run bounded maintenance", "--scope-version", "s1",
            "--standards-version", "3.0.0", "--profile-manifest",
            "profiles/sample/profile.md", "--at", "2026-08-04T00:00:00Z",
            "--apply",
        ]
        missing = subprocess.run(
            base, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False)
        self.assertEqual(2, missing.returncode, missing.stdout)
        self.assertIn("--completion-semantics", missing.stdout)
        completed = subprocess.run(
            base[:-1] + ["--completion-semantics", "maintenance", "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        progress = kblib.load_yaml_file(fresh / check_queue.PROGRESS_PATH)
        self.assertEqual("maintenance",
                         progress["contract"]["completion_semantics"])
        self.assertEqual("not-applicable",
                         progress["terminal_audit"]["state"])
        self.assertEqual("pending",
                         progress["maintenance_completion"]["state"])
        coverage = kblib.load_yaml_file(fresh / check_queue.COVERAGE_PATH)
        self.assertEqual([], coverage["maintenance_candidates"])

    def test_resume_action_prioritizes_pending_apply_without_deadlocking_task_resume(self):
        result = {
            "writer_locks": [],
            "progress": {"task_state": "active"},
            "items_by_id": {"B1": {
                "id": "B1", "state": "merge-ready", "hold_state": "none",
            }},
            "applied_delta_receipts": [{
                "batch": "B1", "selected_receipt": "audit-apply-B1",
            }],
            "pending_delta_applies": {
                "status": "close-required",
                "current": [{
                    "batch": "B1",
                    "selected_receipt": "audit-apply-B1",
                }],
                "stale": [],
            },
            "batch_close_recovery": {
                "status": "gate-required",
                "selected": None,
                "update_queue_command": None,
            },
            "task_runtime": {
                "pending_guidance": [{"id": "G1"}],
                "pending_amendments": [{"id": "A1"}],
            },
        }
        gate = "run-batch-close-gate:B1"
        self.assertEqual(gate, check_queue._resume_next_action(result, []))
        self.assertIn("run check_batch_close.py for applied batch B1",
                      check_queue._resume_recommendation(result, []))
        result["progress"]["task_state"] = "cancelled"
        self.assertEqual(gate, check_queue._resume_next_action(result, []))
        self.assertIn("before any Queue close, control input",
                      check_queue._resume_recommendation(result, []))
        result["progress"]["task_state"] = "paused"
        self.assertEqual("resume-paused-task",
                         check_queue._resume_next_action(result, []))
        self.assertIn("resume the paused task",
                      check_queue._resume_recommendation(result, []))
        result["progress"]["task_state"] = "blocked"
        self.assertEqual("resolve-blocked-task",
                         check_queue._resume_next_action(result, []))
        self.assertIn("resolve the blocked task state",
                      check_queue._resume_recommendation(result, []))
        result["progress"]["task_state"] = "active"
        result["batch_close_recovery"] = {
            "status": "ready-to-close",
            "selected": {
                "batch": "B1",
                "queue_consistency_receipt": "audit-consistency-B1",
                "close_gate_receipt": "audit-close-B1",
                "delta_apply_receipt": "audit-apply-B1",
            },
            "update_queue_command": "python3 Tools/update_queue.py ...",
        }
        close = ("close-applied-batch:B1:audit-consistency-B1:"
                 "audit-close-B1:audit-apply-B1")
        self.assertEqual(close, check_queue._resume_next_action(result, []))
        self.assertIn("python3 Tools/update_queue.py ...",
                      check_queue._resume_recommendation(result, []))
        self.assertIsNone(check_queue.delta_apply_write_barrier(
            result, "update_queue", "closed", "B1"))
        self.assertIn("only allowed", check_queue.delta_apply_write_barrier(
            result, "update_queue", "hold", "B1"))
        self.assertEqual("repair-runtime",
                         check_queue._resume_next_action(result, ["broken"]))
        result["writer_locks"] = [{"path": "state-writer.lock"}]
        self.assertEqual("reconcile-interrupted-write",
                         check_queue._resume_next_action(result, []))


if __name__ == "__main__":
    unittest.main()
