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
from types import SimpleNamespace
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import check_queue
import contract_exception_policy
import kblib
# The review-evidence validator is patched below, and after the package
# split its one caller reads the name from the module that defines it.
import queue_runtime.property_state
import standards_state
from profile_fixture import install_loadable_profile


class QueueFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root, profile_id="test-profile")

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

    def test_runtime_identity_must_match_approved_active_standards(self):
        baseline = check_queue.validate_runtime(self.root)
        self.assertEqual([], baseline["errors"])
        active = self.root / standards_state.STATE_PATH
        state = kblib.load_yaml_file(active)
        state["standards_version"] = "9.9.9"
        state["state_revision"] += 1
        active.write_text(
            standards_state.canonical_text(state), encoding="utf-8")

        result = check_queue.validate_runtime(self.root)

        self.assertTrue(any(
            "runtime standards_version" in error and "9.9.9" in error
            for error in result["errors"]), result["errors"])

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
                # The origin receipt is the first anchor of the contract
                # chain; a fixture that edits contract bytes must re-anchor
                # it, exactly as a real writer re-anchors on amendment.
                record["contract_sha256"] = check_queue._contract_sha256(
                    kblib.load_yaml_file(self.progress_path))
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
        text = manifest.read_text(encoding="utf-8")
        original = "- `Expression Layer Entry`: `slots.md`"
        self.assertIn(original, text)
        manifest.write_text(
            text.replace(
                original, "- `Expression Layer Entry`: %s" % binding, 1),
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

    def test_live_legacy_property_state_requires_migration_admission(self):
        coverage = kblib.load_yaml_file(self.coverage_path)
        for page in coverage["pages"]:
            page.pop("property_state")
        self.coverage_path.write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        self.refresh_initial_origin()

        strict = check_queue.validate_runtime(self.root)
        self.assertTrue(any(
            "property-state-migration Amendment" in error
            for error in strict["errors"]), strict["errors"])
        migration_before = check_queue.validate_runtime(
            self.root,
            allow_legacy_property_state_for_migration=True)
        self.assertEqual([], migration_before["errors"])
        with self.assertRaises(ValueError):
            check_queue.validate_runtime(
                self.root,
                state_overrides={check_queue.COVERAGE_PATH: (
                    kblib.canonical_yaml(coverage), coverage)},
                allow_legacy_property_state_for_migration=True)

    def test_legacy_marker_is_exact_or_page_field_is_reported_unowned(self):
        (self.root / "Topics/A.md").write_text(
            "---\nlast_reviewed: 2026-07-31\n---\n# A\n",
            encoding="utf-8")
        coverage = kblib.load_yaml_file(self.coverage_path)
        page = coverage["pages"][0]
        self.coverage_path.write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        self.refresh_initial_origin()

        unowned = check_queue.validate_runtime(self.root)
        self.assertTrue(any(
            "persists machine-managed field last_reviewed" in error and
            "without a current owner" in error
            for error in unowned["errors"]), unowned["errors"])

        page["legacy_property_state"] = {
            "last_reviewed": {
                "status": "legacy-unverified",
                "value": "2026-07-31",
            },
        }
        before_page_sha = kblib.sha256_file(self.root / "Topics/A.md")
        (self.root / "Topics/A.md").write_text(
            "---\n---\n# A\n", encoding="utf-8")
        migration_records = [{
            "path": "Topics/A.md",
            "before_page_sha256": before_page_sha,
            "after_page_sha256": kblib.sha256_file(
                self.root / "Topics/A.md"),
            "legacy_property_state": copy.deepcopy(
                page["legacy_property_state"]),
        }]
        self.coverage_path.write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        self.refresh_initial_origin()
        source = {
            "receipt_id": "audit-property-adoption",
            "tool": "apply_task_plan", "tool_version": "1.2.0",
            "check": "task_plan", "transaction_phase": "commit",
            "result": "pass", "invalidated_by": None,
            "operation_capability": "legacy-property-adoption-v1",
            "property_state_adoption_records": migration_records,
            "property_state_adoption_count": 1,
            "property_state_adoption_set_sha256":
                check_queue.metadata_property_state.
                legacy_property_migration_set_sha256(migration_records),
            "metadata_execution_contract_fingerprint":
                "sha256:" + "1" * 64,
            "metadata_execution_rule_fingerprint":
                "sha256:" + "2" * 64,
            "selected_profile_manifest":
                "profiles/test-profile/profile.md",
            "profile_snapshot_sha256": "sha256:" + "3" * 64,
            "profile_contract_fingerprint": "sha256:" + "4" * 64,
            "profile_load_inputs_sha256": "sha256:" + "5" * 64,
        }
        receipt_path = self.root / ".cambium/receipts/task-plans.jsonl"
        receipt_path.write_text(json.dumps(source) + "\n", encoding="utf-8")
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

        (self.root / "Topics/A.md").write_text(
            "---\nlast_reviewed: 2026-07-31\n---\n# A\n",
            encoding="utf-8")
        drifted = check_queue.validate_runtime(self.root)
        self.assertTrue(any(
            "legacy_property_state.last_reviewed" in error and
            "still has a persisted page copy" in error
            for error in drifted["errors"]), drifted["errors"])


class CorpusPlanEraMapTests(unittest.TestCase):
    """Every supported close era must resolve a corpus-plan child protocol.

    The incident: bumping the batch-close producer to 1.9.0 without adding
    the 1.8.0 -> 1.7.0 row left every real 1.8.0-era closed bundle that
    carried a Corpus Planning child failing consistency with "no registered
    historical child protocol" -- found by an adopter's live runtime, not
    by any fixture, because the fixtures restamp to older eras.  The map is
    an invariant of the version set, so pin it as one.
    """

    def test_every_supported_close_era_resolves_a_child_protocol(self):
        for version in check_queue.SUPPORTED_BATCH_CLOSE_TOOL_VERSIONS:
            if version == check_queue.BATCH_CLOSE_TOOL_VERSION:
                continue
            self.assertIn(
                version,
                check_queue.HISTORICAL_CORPUS_PLAN_TOOL_VERSIONS,
                "supported historical era %s has no corpus-plan child "
                "protocol; a real closed bundle of that era would fail "
                "every consistency run" % version)


class EvidenceIdentityLifecycleTests(unittest.TestCase):
    """One policy separates live authority from producer-era facts."""

    def setUp(self):
        self.receipt = {
            "selected_profile_manifest": "profiles/old/profile.md",
            "profile_snapshot_sha256": "sha256:" + "1" * 64,
            "profile_contract_fingerprint": "sha256:" + "2" * 64,
            "profile_load_inputs_sha256": "sha256:" + "3" * 64,
            "metadata_execution_contract_fingerprint":
                "sha256:" + "4" * 64,
        }
        self.live_profile = {
            "selected_profile_manifest": "profiles/new/profile.md",
            "profile_snapshot_sha256": "sha256:" + "5" * 64,
            "profile_contract_fingerprint": "sha256:" + "6" * 64,
            "profile_load_inputs_sha256": "sha256:" + "7" * 64,
        }
        self.live_metadata = "sha256:" + "8" * 64

    def errors(self, use, receipt=None):
        return check_queue._evidence_identity_errors(
            receipt or self.receipt, "fixture evidence", use=use,
            profile_view=self.live_profile,
            metadata_contract_fingerprint=self.live_metadata)

    def test_current_authority_and_active_transaction_require_live_identity(self):
        for use in (
                check_queue.EVIDENCE_USE_CURRENT_AUTHORIZATION,
                check_queue.EVIDENCE_USE_ACTIVE_TRANSACTION):
            with self.subTest(use=use):
                errors = self.errors(use)
                self.assertTrue(any(
                    "expected authorized Profile" in error
                    for error in errors), errors)
                self.assertTrue(any(
                    "stale relative to the live contract" in error
                    for error in errors), errors)

    def test_completed_event_and_terminal_history_replay_producer_identity(self):
        for use in (
                check_queue.EVIDENCE_USE_COMPLETED_EVENT,
                check_queue.EVIDENCE_USE_TERMINAL_HISTORY):
            with self.subTest(use=use):
                self.assertEqual([], self.errors(use))

    def test_every_lifecycle_rejects_malformed_producer_identity(self):
        malformed = dict(self.receipt)
        malformed["profile_snapshot_sha256"] = "not-a-sha"
        malformed["metadata_execution_contract_fingerprint"] = "not-a-sha"
        for use in check_queue.EVIDENCE_IDENTITY_USES:
            with self.subTest(use=use):
                errors = self.errors(use, malformed)
                self.assertTrue(any(
                    "invalid producer-era profile_snapshot_sha256" in error
                    for error in errors), errors)
                self.assertTrue(any(
                    "invalid producer-era metadata execution fingerprint" in
                    error for error in errors), errors)


class CurrentPropertyStateTests(unittest.TestCase):
    """Current owner state is strict without reinterpreting absent history."""

    META_SHA = "sha256:" + "8" * 64
    PROFILE_SHA = "sha256:" + "2" * 64
    PROFILE_CONTRACT_SHA = "sha256:" + "3" * 64
    PROFILE_INPUTS_SHA = "sha256:" + "4" * 64
    ACTIVE_SHA = "sha256:" + "5" * 64

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root, profile_id="test-profile")
        self.page_path = "Topics/A.md"
        self.gate = SimpleNamespace(
            gate_id="P:test-profile:readiness",
            transition_id="readiness-promotion",
            judgment_item_id="test-profile-foundation-depth",
            pass_authority_role_id="stopper",
            field_id="readiness_state",
            completion_values=("accepted", "rejected"),
            producer_kind="manual-attestation",
            producer_capability="manual-attestation-v1",
            producer_reference="stopper",
            receipt_schema="manual-gate-attestation-v1",
            consumer_capability="metadata-transition-integrator-v1",
        )
        self.profile_view = {
            "selected_profile_manifest":
                "profiles/test-profile/profile.md",
            "profile_snapshot_sha256": self.PROFILE_SHA,
            "profile_contract_fingerprint": self.PROFILE_CONTRACT_SHA,
            "profile_load_inputs_sha256": self.PROFILE_INPUTS_SHA,
            "_contract": SimpleNamespace(extension_gates=(self.gate,)),
        }
        self.active_view = {
            "active_standards_sha256": self.ACTIVE_SHA,
        }
        self.metadata_contract = SimpleNamespace(
            contract_fingerprint=self.META_SHA)
        self.rules = (
            self.date_rule("last_content_modified"),
            self.date_rule(
                "last_reviewed",
                invalidation="semantic-content-change-tombstone-v1"),
            check_queue.metadata_property_state.gate_projection_rule(
                "readiness_state", ("accepted", "rejected"),
                legacy_observation_values=(
                    "missing", "mapped", "accepted", "rejected")),
        )

    @staticmethod
    def date_rule(field, invalidation="owner-property-state-change-v1"):
        return {
            "field": field,
            "source_adapter": "coverage-property-state-v1",
            "value_shape": "date",
            "invalidation_rule": invalidation,
            "reconcile_policy": "upsert-exact-or-remove-v1",
        }

    def semantic(self, text):
        return check_queue.project_page_state.semantic_content_fingerprint(
            self.page_path, text, self.rules)

    def errors(self, row, catalog):
        coverage = {"pages": [row]}
        with mock.patch.object(
                check_queue.metadata_execution_contract,
                "load_metadata_execution_contract",
                return_value=self.metadata_contract), mock.patch.object(
                    check_queue.metadata_property_state,
                    "profile_gate_projection_rules",
                    return_value=self.rules):
            return check_queue._coverage_property_state_errors(
                str(self.root), coverage, catalog,
                {"task_id": "fixture-task"}, self.profile_view,
                self.active_view)

    def errors_with_projection(self, row, catalog, page_text):
        coverage = {"pages": [row]}
        with mock.patch.object(
                check_queue.metadata_execution_contract,
                "load_metadata_execution_contract",
                return_value=self.metadata_contract), mock.patch.object(
                    check_queue.metadata_property_state,
                    "profile_gate_projection_rules",
                    return_value=self.rules):
            return check_queue._coverage_property_state_errors(
                str(self.root), coverage, catalog,
                {"task_id": "fixture-task"}, self.profile_view,
                self.active_view,
                page_projection_overrides={self.page_path: page_text})

    def content_receipt(self, receipt_id, fingerprint):
        before = "sha256:" + "1" * 64
        records = [{
            "path": self.page_path,
            "semantic_content_sha256": before,
            "page_sha256": "sha256:" + "6" * 64,
        }]
        set_sha = check_queue.metadata_property_state.\
            semantic_baseline_set_sha256(records)
        return {
            "receipt_id": receipt_id,
            "tool": "apply_delta",
            "tool_version": check_queue.APPLY_DELTA_TOOL_VERSION,
            "check": "delta_apply",
            "target": "B1",
            "batch_id": "B1",
            "result": "pass",
            "invalidated_by": None,
            "actor_role": "integrator",
            "task_id": "fixture-task",
            "checked_at": "2026-08-20T03:04:05Z",
            "metadata_execution_contract_fingerprint": self.META_SHA,
            "metadata_execution_rule_fingerprint":
                check_queue.project_page_state._rules_fingerprint(self.rules),
            "semantic_content_protocol":
                check_queue.project_page_state.SEMANTIC_FINGERPRINT_PROTOCOL,
            "selected_profile_manifest":
                self.profile_view["selected_profile_manifest"],
            "profile_snapshot_sha256": self.PROFILE_SHA,
            "profile_contract_fingerprint": self.PROFILE_CONTRACT_SHA,
            "profile_load_inputs_sha256": self.PROFILE_INPUTS_SHA,
            "opening_transition_receipt": "audit-open-current",
            "manifest_semantic_before_set_sha256": set_sha,
            "property_events": [{
                "event": "semantic-content-change",
                "path": self.page_path,
                "accepted_on": "2026-08-20",
                "before_semantic_content_sha256": before,
                "after_semantic_content_sha256": fingerprint,
                "last_reviewed_invalidated": False,
                "invalidated_property_fields": [],
                "invalidated_property_records": [],
                "invalidated_property_receipt_ids": [],
            }],
        }

    def content_catalog(self, receipt):
        before = receipt["property_events"][0][
            "before_semantic_content_sha256"]
        records = [{
            "path": self.page_path,
            "semantic_content_sha256": before,
            "page_sha256": "sha256:" + "6" * 64,
        }]
        opening = {
            "receipt_id": receipt["opening_transition_receipt"],
            "tool": "update_queue",
            "tool_version": check_queue.UPDATE_QUEUE_TOOL_VERSION,
            "target": "B1",
            "before_state": "queued",
            "after_state": "open",
            "task_id": receipt["task_id"],
            "semantic_content_protocol":
                check_queue.project_page_state.SEMANTIC_FINGERPRINT_PROTOCOL,
            "manifest_semantic_before_records": records,
            "manifest_semantic_before_count": 1,
            "manifest_semantic_before_set_sha256":
                receipt["manifest_semantic_before_set_sha256"],
            "selected_profile_manifest":
                receipt["selected_profile_manifest"],
            "profile_snapshot_sha256":
                receipt["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                receipt["profile_contract_fingerprint"],
            "profile_load_inputs_sha256":
                receipt["profile_load_inputs_sha256"],
            "metadata_execution_contract_fingerprint":
                receipt["metadata_execution_contract_fingerprint"],
        }
        return {
            receipt["receipt_id"]: ("receipt.jsonl", receipt),
            opening["receipt_id"]: ("open.jsonl", opening),
        }

    def test_absent_property_state_is_a_legacy_boundary(self):
        errors = self.errors({"path": self.page_path}, {})
        self.assertTrue(any(
            "live legacy page must be adopted" in error
            for error in errors), errors)

    def test_final_state_accepts_full_legacy_observation_domain(self):
        """Post-write validation must not reapply current-owner rules.

        The migration planner and declaration validator already preserve a
        field's full vocabulary and an explicit blank date.  This is the
        final runtime boundary that previously accepted the proposed state
        and then rejected those same observations as if they were current
        Gate/date owners.
        """
        (self.root / self.page_path).write_text(
            "---\ntitle: A\n---\nBody\n", encoding="utf-8")
        row = {
            "path": self.page_path,
            "property_state": {},
            "legacy_property_state": {
                "readiness_state": {
                    "status": "legacy-unverified",
                    "value": "mapped",
                },
                "last_reviewed": {
                    "status": "legacy-unverified",
                    "value": None,
                },
            },
        }
        self.assertEqual([], self.errors(row, {}))

    def test_content_event_closes_owner_evidence_and_machine_fields(self):
        text = (
            "---\ntitle: A\nlast_content_modified: 2026-08-20\n"
            "---\nBody\n")
        (self.root / self.page_path).write_text(text, encoding="utf-8")
        fingerprint = self.semantic(text)
        self.assertEqual(
            fingerprint,
            self.semantic(text.replace(
                "---\nBody", "readiness_state: accepted\n---\nBody")))
        self.assertEqual(
            fingerprint,
            self.semantic(text.replace(
                "---\nBody", "readiness_state: rejected\n---\nBody")))
        self.assertEqual(
            fingerprint,
            self.semantic(text.replace(
                "---\nBody", "last_reviewed: 2099-01-01\n---\nBody")))
        receipt_id = "audit-content-current"
        row = {
            "path": self.page_path,
            "property_state": {
                "last_content_modified": {
                    "value": "2026-08-20",
                    "evidence_receipt": receipt_id,
                    "content_fingerprint": fingerprint,
                },
            },
        }
        receipt = self.content_receipt(receipt_id, fingerprint)
        catalog = self.content_catalog(receipt)
        self.assertEqual([], self.errors(row, catalog))

        projection_only = text.replace(
            "last_content_modified: 2026-08-20",
            "last_content_modified: 2099-01-01")
        self.assertEqual(fingerprint, self.semantic(projection_only))
        (self.root / self.page_path).write_text(
            projection_only, encoding="utf-8")
        drift = self.errors(row, catalog)
        self.assertTrue(any(
            "page projection is" in error for error in drift), drift)
        self.assertFalse(any(
            "stale content" in error or "current semantic content" in error
            for error in drift), drift)
        self.assertEqual([], self.errors_with_projection(
            row, catalog, text))

    def test_content_pointer_replays_canonical_producer_era_bindings(self):
        text = (
            "---\ntitle: A\nlast_content_modified: 2026-08-20\n"
            "---\nBody\n")
        (self.root / self.page_path).write_text(text, encoding="utf-8")
        fingerprint = self.semantic(text)
        receipt_id = "audit-content-current"
        record = {
            "value": "2026-08-20",
            "evidence_receipt": receipt_id,
            "content_fingerprint": fingerprint,
        }
        row = {"path": self.page_path,
               "property_state": {"last_content_modified": dict(record)}}
        absent = self.errors(row, {})
        self.assertTrue(any(
            "absent from the current receipt catalog" in error
            for error in absent), absent)

        row["property_state"]["last_content_modified"]["extra"] = True
        receipt = self.content_receipt(receipt_id, fingerprint)
        closed = self.errors(row, self.content_catalog(receipt))
        self.assertTrue(any("not closed" in error for error in closed), closed)

        row["property_state"]["last_content_modified"] = dict(record)
        receipt["metadata_execution_contract_fingerprint"] = "not-a-sha"
        stale = self.errors(row, self.content_catalog(receipt))
        self.assertTrue(any(
            "metadata execution fingerprint" in error
            for error in stale), stale)
        old_meta = "sha256:" + "9" * 64
        old_profile = "sha256:" + "0" * 64
        receipt["metadata_execution_contract_fingerprint"] = old_meta
        receipt["profile_snapshot_sha256"] = old_profile
        catalog = self.content_catalog(receipt)
        opening = catalog[receipt["opening_transition_receipt"]][1]
        opening["metadata_execution_contract_fingerprint"] = old_meta
        opening["profile_snapshot_sha256"] = old_profile
        self.assertEqual([], self.errors(row, catalog))

    def test_content_event_must_bind_exact_opening_before_image(self):
        text = (
            "---\ntitle: A\nlast_content_modified: 2026-08-20\n"
            "---\nBody\n")
        (self.root / self.page_path).write_text(text, encoding="utf-8")
        fingerprint = self.semantic(text)
        receipt = self.content_receipt("audit-content-current", fingerprint)
        row = {
            "path": self.page_path,
            "property_state": {
                "last_content_modified": {
                    "value": "2026-08-20",
                    "evidence_receipt": receipt["receipt_id"],
                    "content_fingerprint": fingerprint,
                },
            },
        }
        catalog = self.content_catalog(receipt)
        opening = catalog[receipt["opening_transition_receipt"]][1]
        opening["manifest_semantic_before_records"][0][
            "semantic_content_sha256"] = "sha256:" + "7" * 64
        errors = self.errors(row, catalog)
        self.assertTrue(any(
            "stale semantic before-set digest" in error or
            "frozen opening semantic fingerprint" in error
            for error in errors), errors)

    def test_property_fields_values_and_tombstones_are_closed(self):
        text = "---\ntitle: A\nreadiness_state: accepted\n---\nBody\n"
        (self.root / self.page_path).write_text(text, encoding="utf-8")
        fingerprint = self.semantic(text)
        record = {
            "value": "accepted",
            "evidence_receipt": "audit-gate",
            "content_fingerprint": fingerprint,
        }
        row = {
            "path": self.page_path,
            "property_state": {"unregistered_state": dict(record)},
        }
        unknown = self.errors(row, {})
        self.assertTrue(any("undeclared field" in error for error in unknown),
                        unknown)

        row["property_state"] = {"readiness_state": dict(record)}
        row["property_state"]["readiness_state"]["value"] = "maybe"
        bad_enum = self.errors(row, {})
        self.assertTrue(any("must be one of" in error for error in bad_enum),
                        bad_enum)

        row["property_state"]["readiness_state"]["value"] = None
        tombstone = self.errors(row, {})
        self.assertTrue(any("unauthorized null tombstone" in error
                            for error in tombstone), tombstone)

        row["property_state"] = {
            "last_reviewed": {
                "value": None,
                "evidence_receipt": "audit-content",
                "content_fingerprint": fingerprint,
            },
        }
        orphan = self.errors(row, {})
        self.assertTrue(any(
            "tombstone without the content-change state" in error
            for error in orphan), orphan)

    def test_review_replays_producer_era_while_profile_gate_stays_live(self):
        text = (
            "---\ntitle: A\nlast_reviewed: 2026-08-20\n"
            "readiness_state: accepted\n---\nBody\n")
        (self.root / self.page_path).write_text(text, encoding="utf-8")
        fingerprint = self.semantic(text)
        review_id = "audit-page-review"
        gate_id = "audit-gate"
        attestation_id = "audit-review-attestation"
        row = {
            "path": self.page_path,
            "property_state": {
                "last_reviewed": {
                    "value": "2026-08-20",
                    "evidence_receipt": review_id,
                    "content_fingerprint": fingerprint,
                },
                "readiness_state": {
                    "value": "accepted",
                    "evidence_receipt": gate_id,
                    "content_fingerprint": fingerprint,
                },
            },
        }
        review = {
            "receipt_id": review_id,
            "tool": check_queue.BATCH_CLOSE_TOOL,
            "tool_version": check_queue.BATCH_CLOSE_TOOL_VERSION,
            "check": "page_review_acceptance",
            "target": self.page_path,
            "result": "pass",
            "invalidated_by": None,
            "task_id": "fixture-task",
            "batch_id": "B1",
            "integrator_id": "integrator-a",
            "reviewer_id": "reviewer-b",
            "merged_snapshot_sha256": "sha256:" + "1" * 64,
            "checked_at": "2026-08-20T04:05:06Z",
            "reviewed_on": "2026-08-20",
            "semantic_content_sha256": fingerprint,
            "reviewer_attestation_receipt": attestation_id,
            "selected_profile_manifest":
                self.profile_view["selected_profile_manifest"],
            "profile_snapshot_sha256": self.PROFILE_SHA,
            "profile_contract_fingerprint": self.PROFILE_CONTRACT_SHA,
            "profile_load_inputs_sha256": self.PROFILE_INPUTS_SHA,
            "metadata_execution_contract_fingerprint": self.META_SHA,
        }
        manifest_sha = kblib.sha256_file(
            self.root / self.profile_view["selected_profile_manifest"])
        gate = {
            "receipt_id": gate_id,
            "tool": "record_gate_attestation",
            "tool_version": "1.0.0",
            "check": "profile-extension-gate",
            "target": self.page_path,
            "result": "pass",
            "invalidated_by": None,
            "checked_at": "2026-08-20T04:06:07Z",
            "details": "bounded acceptance",
            "attestation_statement": "bounded acceptance",
            "actor_role": "stopper",
            "gate_id": self.gate.gate_id,
            "transition_id": self.gate.transition_id,
            "judgment_item_id": self.gate.judgment_item_id,
            "property_field": self.gate.field_id,
            "requested_completion_value": "accepted",
            "pass_authority_role_id": self.gate.pass_authority_role_id,
            "producer_kind": self.gate.producer_kind,
            "producer_capability": self.gate.producer_capability,
            "producer_reference": self.gate.producer_reference,
            "receipt_schema": self.gate.receipt_schema,
            "consumer_capability": self.gate.consumer_capability,
            "semantic_content_fingerprint": fingerprint,
            "page_sha256": "sha256:" + "6" * 64,
            "selected_profile_manifest":
                self.profile_view["selected_profile_manifest"],
            "selected_profile_manifest_sha256": manifest_sha,
            "profile_snapshot_sha256": self.PROFILE_SHA,
            "profile_contract_fingerprint": self.PROFILE_CONTRACT_SHA,
            "profile_load_inputs_sha256": self.PROFILE_INPUTS_SHA,
            "active_standards_sha256": self.ACTIVE_SHA,
            "metadata_execution_contract_fingerprint": self.META_SHA,
        }
        catalog = {
            review_id: ("review.jsonl", review),
            gate_id: ("gate.jsonl", gate),
            attestation_id: ("review.jsonl", {
                "receipt_id": attestation_id,
                "tool": check_queue.BATCH_CLOSE_TOOL,
                "tool_version": check_queue.BATCH_CLOSE_TOOL_VERSION,
                "check": "batch_global_review_attestation",
                "target": "B1",
                "result": "pass",
                "invalidated_by": None,
                "task_id": "fixture-task",
                "batch_id": "B1",
                "integrator_id": "integrator-a",
                "reviewer_id": "reviewer-b",
                "merged_snapshot_sha256": "sha256:" + "1" * 64,
                "details": "independent review accepted",
            }),
        }
        coverage_sha = kblib.sha256_bytes(kblib.canonical_yaml(
            {"pages": [row]}).encode("utf-8"))
        state_sha = "sha256:" + "8" * 64
        page_after_sha = kblib.sha256_file(self.root / self.page_path)
        transition_id = "audit-gate-transition"
        catalog[transition_id] = ("gate-transition.jsonl", {
            "receipt_id": transition_id,
            "tool": "apply_metadata_transition",
            "tool_version": "1.0.0",
            "check": "metadata-transition",
            "target": self.page_path,
            "result": "pass",
            "invalidated_by": None,
            "actor_role": "integrator",
            "gate_id": self.gate.gate_id,
            "transition_id": self.gate.transition_id,
            "judgment_item_id": self.gate.judgment_item_id,
            "property_field": self.gate.field_id,
            "requested_completion_value": "accepted",
            "gate_receipt": gate_id,
            "gate_receipt_checked_at": gate["checked_at"],
            "semantic_content_fingerprint": fingerprint,
            "pass_authority_role_id": self.gate.pass_authority_role_id,
            "producer_kind": self.gate.producer_kind,
            "producer_capability": self.gate.producer_capability,
            "producer_reference": self.gate.producer_reference,
            "receipt_schema": self.gate.receipt_schema,
            "consumer_capability": self.gate.consumer_capability,
            "selected_profile_manifest":
                self.profile_view["selected_profile_manifest"],
            "selected_profile_manifest_sha256": manifest_sha,
            "profile_snapshot_sha256": self.PROFILE_SHA,
            "profile_contract_fingerprint": self.PROFILE_CONTRACT_SHA,
            "profile_load_inputs_sha256": self.PROFILE_INPUTS_SHA,
            "active_standards_sha256": self.ACTIVE_SHA,
            "metadata_execution_contract_fingerprint": self.META_SHA,
            "before_coverage_sha256": "sha256:" + "7" * 64,
            "after_coverage_sha256": coverage_sha,
            "before_required_queue_sha256": state_sha,
            "after_required_queue_sha256": state_sha,
            "before_progress_sha256": state_sha,
            "after_progress_sha256": state_sha,
            "before_page_sha256": gate["page_sha256"],
            "after_page_sha256": page_after_sha,
            "before_repository_snapshot_sha256": state_sha,
            "after_repository_snapshot_sha256": state_sha,
        })
        self.assertEqual([], self.errors(row, catalog))

        review["profile_contract_fingerprint"] = "sha256:" + "7" * 64
        self.assertEqual([], self.errors(row, catalog))
        gate["profile_contract_fingerprint"] = "sha256:" + "7" * 64
        stale = self.errors(row, catalog)
        self.assertTrue(any(
            "profile_contract_fingerprint" in error for error in stale),
            stale)
        gate["profile_contract_fingerprint"] = self.PROFILE_CONTRACT_SHA
        gate["requested_completion_value"] = "rejected"
        wrong_value = self.errors(row, catalog)
        self.assertTrue(any(
            "requested_completion_value" in error for error in wrong_value),
            wrong_value)
        gate["requested_completion_value"] = "accepted"
        review["target"] = "Topics/B.md"
        wrong_target = self.errors(row, catalog)
        self.assertTrue(any("target=" in error for error in wrong_target),
                        wrong_target)
        review["target"] = self.page_path
        catalog[attestation_id][1]["reviewer_id"] = "reviewer-c"
        wrong_attestation = self.errors(row, catalog)
        self.assertTrue(any(
            "reviewer attestation" in error and "reviewer_id" in error
            for error in wrong_attestation), wrong_attestation)


class InFlightPropertyStateTests(unittest.TestCase):
    """A prior batch's owner may drift only inside the next exact open set."""

    META_SHA = "sha256:" + "a" * 64
    PROFILE_SHA = "sha256:" + "b" * 64
    PROFILE_CONTRACT_SHA = "sha256:" + "c" * 64
    PROFILE_INPUTS_SHA = "sha256:" + "d" * 64

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root, profile_id="test-profile")
        self.path = "Topics/A.md"
        self.rule = CurrentPropertyStateTests.date_rule(
            "last_reviewed",
            invalidation="semantic-content-change-tombstone-v1")
        self.rules = (self.rule,)
        self.profile_view = {
            "selected_profile_manifest":
                "profiles/test-profile/profile.md",
            "profile_snapshot_sha256": self.PROFILE_SHA,
            "profile_contract_fingerprint": self.PROFILE_CONTRACT_SHA,
            "profile_load_inputs_sha256": self.PROFILE_INPUTS_SHA,
            "_contract": SimpleNamespace(extension_gates=()),
        }
        self.metadata_contract = SimpleNamespace(
            contract_fingerprint=self.META_SHA)

    def opening(self, manifest, fingerprints):
        records = [{
            "path": path,
            "page_sha256": "sha256:" + str(index + 1) * 64,
            "semantic_content_sha256": fingerprints[path],
        } for index, path in enumerate(manifest)]
        return {
            "receipt_id": "audit-open-b2",
            "tool": "update_queue",
            "tool_version": check_queue.UPDATE_QUEUE_TOOL_VERSION,
            "check": "queue_transition",
            "target": "B2",
            "before_state": "queued",
            "after_state": "open",
            "semantic_content_protocol":
                check_queue.project_page_state.SEMANTIC_FINGERPRINT_PROTOCOL,
            "manifest_semantic_before_records": records,
            "manifest_semantic_before_count": len(records),
            "manifest_semantic_before_set_sha256":
                check_queue.metadata_property_state.
                semantic_baseline_set_sha256(records),
            "selected_profile_manifest":
                self.profile_view["selected_profile_manifest"],
            "profile_snapshot_sha256": self.PROFILE_SHA,
            "profile_contract_fingerprint": self.PROFILE_CONTRACT_SHA,
            "profile_load_inputs_sha256": self.PROFILE_INPUTS_SHA,
            "metadata_execution_contract_fingerprint": self.META_SHA,
        }

    def property_errors(self, row, queue, catalog):
        with mock.patch.object(
                check_queue.metadata_property_state,
                "authorized_profile_projection_rules",
                return_value=(self.metadata_contract, self.rules)), \
                mock.patch.object(
                    check_queue.metadata_execution_contract,
                    "load_metadata_execution_contract",
                    return_value=self.metadata_contract), \
                mock.patch.object(
                    queue_runtime.property_state,
                    "_review_property_evidence_errors",
                    return_value=[]):
            return check_queue._coverage_property_state_errors(
                str(self.root), {"pages": [row]}, catalog, queue,
                self.profile_view, {"active_standards_sha256":
                                    "sha256:" + "e" * 64})

    def test_two_batch_edit_uses_second_opening_as_controlled_window(self):
        before_text = (
            "---\ntitle: A\nlast_reviewed: 2026-08-19\n---\nBody A\n")
        page = self.root / self.path
        page.write_text(before_text, encoding="utf-8")
        before = check_queue.project_page_state.semantic_content_fingerprint(
            self.path, before_text, self.rules)
        page.write_text(
            before_text.replace("Body A", "Body edited by B2"),
            encoding="utf-8")
        row = {"path": self.path, "property_state": {
            "last_reviewed": {
                "value": "2026-08-19",
                "evidence_receipt": "audit-review-b1",
                "content_fingerprint": before,
            },
        }}
        opening = self.opening([self.path], {self.path: before})
        queue = {"task_id": "fixture-task", "required_queue": [
            {"id": "B1", "state": "closed", "manifest": [self.path],
             "transition_receipts": []},
            {"id": "B2", "state": "open", "manifest": [self.path],
             "transition_receipts": [opening["receipt_id"]]},
        ]}
        catalog = {
            opening["receipt_id"]: ("open.jsonl", opening),
            "audit-review-b1": ("review.jsonl", {
                "receipt_id": "audit-review-b1",
            }),
        }
        self.assertEqual([], self.property_errors(row, queue, catalog))

    def test_nonmanifest_or_missing_current_opening_never_grants_window(self):
        text = "---\ntitle: A\nlast_reviewed: 2026-08-19\n---\nBody A\n"
        page = self.root / self.path
        page.write_text(text, encoding="utf-8")
        before = check_queue.project_page_state.semantic_content_fingerprint(
            self.path, text, self.rules)
        page.write_text(text.replace("Body A", "Body drift"), encoding="utf-8")
        row = {"path": self.path, "property_state": {
            "last_reviewed": {
                "value": "2026-08-19",
                "evidence_receipt": "audit-review-b1",
                "content_fingerprint": before,
            },
        }}
        owner = {"audit-review-b1": ("review.jsonl", {
            "receipt_id": "audit-review-b1",
        })}
        for name, item, catalog in (
                ("missing", {"id": "B2", "state": "open",
                             "manifest": [self.path],
                             "transition_receipts": []}, owner),
                ("nonmanifest", {"id": "B2", "state": "open",
                                 "manifest": ["Topics/B.md"],
                                 "transition_receipts": ["audit-open-b2"]},
                 dict(owner, **{
                     "audit-open-b2": ("open.jsonl", self.opening(
                         ["Topics/B.md"], {
                             "Topics/B.md": "sha256:" + "9" * 64}))
                 }))):
            with self.subTest(name=name):
                errors = self.property_errors(
                    row, {"task_id": "fixture-task",
                          "required_queue": [item]}, catalog)
                self.assertTrue(any(
                    "stale content" in error for error in errors), errors)


class CurrentOpenSemanticBaselineTests(unittest.TestCase):
    META_SHA = "sha256:" + "a" * 64
    PROFILE_SHA = "sha256:" + "b" * 64
    PROFILE_CONTRACT_SHA = "sha256:" + "c" * 64
    PROFILE_INPUTS_SHA = "sha256:" + "d" * 64

    def profile_view(self):
        return {
            "selected_profile_manifest": "profiles/test/profile.md",
            "profile_snapshot_sha256": self.PROFILE_SHA,
            "profile_contract_fingerprint": self.PROFILE_CONTRACT_SHA,
            "profile_load_inputs_sha256": self.PROFILE_INPUTS_SHA,
        }

    @staticmethod
    def records():
        return [
            {
                "path": "Topics/A.md",
                "semantic_content_sha256": "sha256:" + "1" * 64,
                "page_sha256": "sha256:" + "2" * 64,
            },
            {
                "path": "Topics/B.md",
                "semantic_content_sha256": "sha256:" + "3" * 64,
                "page_sha256": "sha256:" + "4" * 64,
            },
        ]

    def transition(self, version=None):
        records = self.records()
        return {
            "receipt_id": "audit-open-transition",
            "tool": "update_queue",
            "tool_version": version or check_queue.UPDATE_QUEUE_TOOL_VERSION,
            "before_state": "queued",
            "after_state": "open",
            "manifest_semantic_before_records": records,
            "manifest_semantic_before_count": len(records),
            "manifest_semantic_before_set_sha256": kblib.sha256_bytes(
                kblib.canonical_json_bytes(records)),
            "semantic_content_protocol":
                check_queue.project_page_state.SEMANTIC_FINGERPRINT_PROTOCOL,
            **self.profile_view(),
            "metadata_execution_contract_fingerprint": self.META_SHA,
        }

    def errors(self, transition, *, require_live_authority=True):
        contract = SimpleNamespace(contract_fingerprint=self.META_SHA)
        with mock.patch.object(
                check_queue.metadata_execution_contract,
                "load_metadata_execution_contract", return_value=contract):
            return check_queue._current_open_semantic_baseline_errors(
                "/fixture", transition,
                {"id": "B1", "manifest": [
                    "Topics/A.md", "Topics/B.md"]},
                self.profile_view(),
                require_live_authority=require_live_authority)

    def test_current_open_binds_exact_manifest_before_set(self):
        self.assertEqual([], self.errors(self.transition()))

        malformed = self.transition()
        malformed["manifest_semantic_before_records"] = list(reversed(
            malformed["manifest_semantic_before_records"]))
        malformed["manifest_semantic_before_count"] = 3
        malformed["manifest_semantic_before_set_sha256"] = (
            "sha256:" + "9" * 64)
        malformed["profile_snapshot_sha256"] = "sha256:" + "8" * 64
        malformed["metadata_execution_contract_fingerprint"] = (
            "sha256:" + "7" * 64)
        errors = self.errors(malformed)
        self.assertTrue(any("path-sorted" in error for error in errors),
                        errors)
        self.assertTrue(any("count must equal" in error for error in errors),
                        errors)
        self.assertTrue(any("does not bind" in error for error in errors),
                        errors)
        self.assertTrue(any("profile_snapshot_sha256" in error
                            for error in errors), errors)
        self.assertTrue(any("stale relative" in error for error in errors),
                        errors)

    def test_legacy_open_is_not_reinterpreted(self):
        for version in ("1.2.0", "1.3.0", "1.4.0"):
            with self.subTest(version=version):
                historical = {
                    "receipt_id": "audit-open-%s" % version,
                    "tool": "update_queue", "tool_version": version,
                    "before_state": "queued", "after_state": "open",
                }
                with mock.patch.object(
                        check_queue.metadata_execution_contract,
                        "load_metadata_execution_contract") as loader:
                    self.assertEqual([],
                        check_queue._current_open_semantic_baseline_errors(
                            "/fixture", historical,
                            {"id": "B1", "manifest": ["Topics/A.md"]},
                            self.profile_view()))
                loader.assert_not_called()

    def test_terminal_current_era_open_replays_producer_bindings(self):
        transition = self.transition()
        transition["profile_snapshot_sha256"] = "sha256:" + "8" * 64
        transition["metadata_execution_contract_fingerprint"] = (
            "sha256:" + "7" * 64)
        with mock.patch.object(
                check_queue.metadata_execution_contract,
                "load_metadata_execution_contract") as loader:
            self.assertEqual([], self.errors(
                transition, require_live_authority=False))
        loader.assert_not_called()

    def test_public_resolver_returns_only_current_latest_opening(self):
        current = self.transition()
        result = {
            "root": "/fixture",
            "items_by_id": {"B1": {
                "id": "B1",
                "manifest": ["Topics/A.md", "Topics/B.md"],
                "transition_receipts": ["audit-open-transition"],
            }},
            "current_receipt_catalog": {
                "audit-open-transition": ("receipts.jsonl", current),
            },
            "_profile_authorized_view": self.profile_view(),
        }
        contract = SimpleNamespace(contract_fingerprint=self.META_SHA)
        with mock.patch.object(
                check_queue.metadata_execution_contract,
                "load_metadata_execution_contract", return_value=contract):
            self.assertEqual({
                "Topics/A.md": "sha256:" + "1" * 64,
                "Topics/B.md": "sha256:" + "3" * 64,
            }, check_queue.current_opening_semantic_baseline(result, "B1"))

        legacy = dict(current, tool_version="1.4.0")
        result["current_receipt_catalog"]["audit-open-transition"] = (
            "receipts.jsonl", legacy)
        with self.assertRaisesRegex(ValueError, "legacy producer"):
            check_queue.current_opening_semantic_baseline(result, "B1")
        result["current_receipt_catalog"] = {}
        with self.assertRaisesRegex(ValueError, "no current opening receipt"):
            check_queue.current_opening_semantic_baseline(result, "B1")


class CurrentCloseTransitionMetadataTests(unittest.TestCase):
    META_SHA = "sha256:" + "a" * 64

    def transition(self, version=None):
        return {
            "receipt_id": "audit-close-transition",
            "tool": "update_queue",
            "tool_version": version or check_queue.UPDATE_QUEUE_TOOL_VERSION,
            "before_state": "merge-ready",
            "after_state": "closed",
            "close_gate_receipt": "audit-close-gate",
            "page_review_receipts": ["audit-page-a", "audit-page-b"],
            "page_review_receipt_count": 2,
            "metadata_execution_contract_fingerprint": self.META_SHA,
        }

    def catalog(self):
        return {
            "audit-close-gate": ("close.jsonl", {
                "receipt_id": "audit-close-gate",
                "page_review_receipts": ["audit-page-a", "audit-page-b"],
                "metadata_execution_contract_fingerprint": self.META_SHA,
            }),
        }

    def errors(self, transition, catalog=None):
        contract = SimpleNamespace(contract_fingerprint=self.META_SHA)
        with mock.patch.object(
                check_queue.metadata_execution_contract,
                "load_metadata_execution_contract", return_value=contract):
            return check_queue._current_close_transition_metadata_errors(
                "/fixture", transition, catalog or self.catalog(), "B1")

    def test_current_close_binds_exact_children_and_producer_metadata(self):
        self.assertEqual([], self.errors(self.transition()))

        malformed = self.transition()
        malformed["page_review_receipts"] = [
            "audit-page-b", "audit-page-a", "audit-page-b"]
        malformed["page_review_receipt_count"] = 2
        malformed["metadata_execution_contract_fingerprint"] = (
            "sha256:" + "b" * 64)
        errors = self.errors(malformed)
        self.assertTrue(any("must be sorted" in error for error in errors),
                        errors)
        self.assertTrue(any("must be unique" in error for error in errors),
                        errors)
        self.assertTrue(any("count must equal" in error for error in errors),
                        errors)
        self.assertTrue(any("exact child" in error for error in errors),
                        errors)
        self.assertTrue(any("differs from its close Gate" in error
                            for error in errors), errors)

    def test_terminal_current_era_close_survives_metadata_upgrade(self):
        transition = self.transition()
        catalog = self.catalog()
        old_fingerprint = "sha256:" + "b" * 64
        transition["metadata_execution_contract_fingerprint"] = \
            old_fingerprint
        catalog["audit-close-gate"][1][
            "metadata_execution_contract_fingerprint"] = old_fingerprint
        with mock.patch.object(
                check_queue.metadata_execution_contract,
                "load_metadata_execution_contract") as loader:
            self.assertEqual([], check_queue.
                _current_close_transition_metadata_errors(
                    "/fixture", transition, catalog, "B1"))
        loader.assert_not_called()

    def test_historical_close_is_not_reinterpreted(self):
        for version in ("1.2.0", "1.3.0", "1.4.0"):
            with self.subTest(version=version):
                historical = self.transition(version=version)
                historical.pop("page_review_receipts")
                historical.pop("page_review_receipt_count")
                historical.pop("metadata_execution_contract_fingerprint")
                with mock.patch.object(
                        check_queue.metadata_execution_contract,
                        "load_metadata_execution_contract") as loader:
                    self.assertEqual([],
                        check_queue._current_close_transition_metadata_errors(
                            "/fixture", historical, {}, "B1"))
                loader.assert_not_called()


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

    def grant_exception(self, limit, *, policy_id="coverage.reviewed_era",
                        scope_ref="fixture-task", fingerprint=None):
        """Write the contract exception this migration disposition needs."""
        if fingerprint is None:
            _policy, fingerprint, _errors = (
                contract_exception_policy.effective_coverage_policy())
        progress = kblib.load_yaml_file(self.progress_path)
        progress["contract"]["policy_exceptions"] = [{
            "decision_id": "PE-COV-1",
            "policy_id": policy_id,
            "baseline_policy_fingerprint": fingerprint,
            "limit": limit,
            "scope_kind": "task",
            "scope_ref": scope_ref,
            "rationale": "legacy reviewed records re-reviewed as their "
                         "batches run; ends at queue exhaustion",
            "approval_reference": "fixture migration declaration",
        }]
        self.progress_path.write_text(kblib.canonical_yaml(progress),
                                      encoding="utf-8")
        self.refresh_initial_origin()

    def test_a_bounded_exception_turns_the_candidate_into_a_note(self):
        """The disposition K02/01 offers must not wedge the queue.

        Activation consumes a PASSING readiness gate, so while the declared
        exception had no machine carrier, choosing it left the candidate
        standing forever and no batch could ever be activated again.
        """
        self.set_page(0, authoring_status="reviewed", gate_receipts=[])
        blocked = self.run_cli()
        self.assertEqual(2, blocked.returncode, blocked.stdout)
        self.assertIn("[HOLD]", blocked.stdout)

        self.grant_exception(1)
        covered = self.run_cli()
        self.assertEqual(0, covered.returncode, covered.stdout)
        self.assertIn("[NOTE]", covered.stdout)
        self.assertIn("PE-COV-1", covered.stdout)
        self.assertNotIn("[HOLD] 1 Coverage record", covered.stdout)

    def test_the_ceiling_cannot_hide_one_more_record(self):
        """The bound is a count, so the grant shrinks as work proceeds."""
        self.set_page(0, authoring_status="reviewed", gate_receipts=[])
        self.set_page(1, authoring_status="reviewed", gate_receipts=[])
        self.grant_exception(1)
        completed = self.run_cli()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("2 record(s) exceed the 1", completed.stdout)

    def test_an_exception_for_another_task_does_not_cover_this_one(self):
        self.set_page(0, authoring_status="reviewed", gate_receipts=[])
        self.grant_exception(5, scope_ref="some-other-task")
        completed = self.run_cli()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("[HOLD]", completed.stdout)

    def test_a_stale_fingerprint_names_why_it_no_longer_covers(self):
        """A grant judged against a superseded statement of the rule dies."""
        self.set_page(0, authoring_status="reviewed", gate_receipts=[])
        self.grant_exception(5, fingerprint="sha256:" + "a" * 64)
        completed = self.run_cli()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("superseded statement of the rule", completed.stdout)

    def test_a_quota_exception_does_not_cover_the_coverage_policy(self):
        self.set_page(0, authoring_status="reviewed", gate_receipts=[])
        self.grant_exception(5, policy_id="priority_quota.P0",
                             fingerprint="sha256:" + "b" * 64)
        completed = self.run_cli()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("[HOLD]", completed.stdout)


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

    def test_runtime_reuses_one_profile_load_view_for_hub_derivation(self):
        self.register_expression_layer([
            ("Existing canonical dependency-map path", "`Topics/A.md`"),
        ])
        producer = check_queue.check_profile.evaluate_profile_load
        calls = []

        def counted(*args, **kwargs):
            calls.append((args, kwargs))
            return producer(*args, **kwargs)

        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                side_effect=counted):
            result = check_queue.validate_runtime(self.root)

        self.assertEqual([], result["errors"])
        self.assertEqual(1, len(calls))
        self.assertNotIn("B1", result["ready"])
        self.assertIn(
            "Topics/A.md (Expression Layer Entry)",
            "; ".join(dict(result["blocked"])["B1"]),
        )

    def test_runtime_accepts_one_previously_authorized_profile_view(self):
        authorized_view, view_errors = \
            check_queue.profile_load_authorized_view(
                self.root, "profiles/test-profile/profile.md")
        self.assertEqual([], view_errors)
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                side_effect=AssertionError(
                    "injected view must suppress a second profile-load")) \
                as load:
            result = check_queue.validate_runtime(
                self.root, authorized_profile_view=authorized_view)

        load.assert_not_called()
        self.assertEqual([], result["errors"])
        self.assertIn("B1", result["ready"])

    def test_runtime_authority_context_reuses_the_indivisible_view_pair(self):
        initial = check_queue.validate_runtime(self.root)
        self.assertEqual([], initial["errors"])
        authority = check_queue.runtime_authority_context(initial)
        kwargs = check_queue.runtime_authority_validation_kwargs(authority)
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                side_effect=AssertionError(
                    "transaction context must suppress another profile-load")):
            rebound = check_queue.validate_runtime(self.root, **kwargs)

        self.assertEqual([], rebound["errors"])
        self.assertIs(initial["_profile_authorized_view"],
                      rebound["_profile_authorized_view"])
        self.assertIs(initial["_active_standards_authorized_view"],
                      rebound["_active_standards_authorized_view"])
        lock_fields = check_queue.runtime_authority_lock_fields(authority)
        self.assertEqual("profiles/test-profile/profile.md",
                         lock_fields["selected_profile_manifest"])
        for field in (
                "active_standards_sha256", "profile_snapshot_sha256",
                "profile_contract_fingerprint", "profile_load_inputs_sha256"):
            self.assertRegex(lock_fields[field], r"^sha256:[0-9a-f]{64}$")

    def test_runtime_rejects_stale_injected_active_standards_view(self):
        initial = check_queue.validate_runtime(self.root)
        self.assertEqual([], initial["errors"])
        authority = check_queue.runtime_authority_context(initial)
        active = self.root / check_queue.ACTIVE_STANDARDS_PATH
        state = kblib.load_yaml_file(active)
        state["state_revision"] += 1
        active.write_text(
            standards_state.canonical_text(state),
            encoding="utf-8")

        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                side_effect=AssertionError(
                    "stale transaction authority must fail, not rerun")) \
                as load:
            rebound = check_queue.validate_runtime(
                self.root,
                **check_queue.runtime_authority_validation_kwargs(authority))

        load.assert_not_called()
        self.assertIn(
            "active Standards state changed after identity admission",
            "; ".join(rebound["errors"]))

    def test_runtime_rejects_stale_injected_profile_view_without_rerun(self):
        authorized_view, view_errors = \
            check_queue.profile_load_authorized_view(
                self.root, "profiles/test-profile/profile.md")
        self.assertEqual([], view_errors)
        expression = self.root / dict(
            authorized_view["_manifest_slot_paths"])[
                check_queue.EXPRESSION_LAYER_SLOT]
        expression.write_text(
            expression.read_text(encoding="utf-8") +
            "\n<!-- revision B before runtime validation -->\n",
            encoding="utf-8",
        )
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                side_effect=AssertionError(
                    "stale injected view must fail, not silently rerun")) \
                as load:
            result = check_queue.validate_runtime(
                self.root, authorized_profile_view=authorized_view)

        load.assert_not_called()
        self.assertIn(
            "changed after profile-load authorization",
            "; ".join(result["errors"]),
        )
        self.assertNotIn("B1", result["ready"])

    def test_runtime_rejects_view_after_canonical_profile_input_changes(self):
        authorized_view, view_errors = \
            check_queue.profile_load_authorized_view(
                self.root, "profiles/test-profile/profile.md")
        self.assertEqual([], view_errors)
        interface = self.root / "profiles/README.md"
        interface.write_text(
            interface.read_text(encoding="utf-8") +
            "\n<!-- canonical input revision B -->\n",
            encoding="utf-8",
        )
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                side_effect=AssertionError(
                    "stale injected view must fail, not silently rerun")) \
                as load:
            result = check_queue.validate_runtime(
                self.root, authorized_profile_view=authorized_view)

        load.assert_not_called()
        self.assertIn(
            "canonical profile-load inputs changed",
            "; ".join(result["errors"]),
        )
        self.assertNotIn("B1", result["ready"])

    def test_runtime_cas_includes_kernel_metadata_field_registries(self):
        authorized_view, view_errors = \
            check_queue.profile_load_authorized_view(
                self.root, "profiles/test-profile/profile.md")
        self.assertEqual([], view_errors)
        applicability = self.root / (
            check_queue.check_profile.DEFAULT_APPLICABILITY_BASE)
        applicability.write_text(
            applicability.read_text(encoding="utf-8") +
            "\n# canonical applicability revision B\n",
            encoding="utf-8")
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                side_effect=AssertionError(
                    "stale injected view must fail, not silently rerun")) \
                as load:
            result = check_queue.validate_runtime(
                self.root, authorized_profile_view=authorized_view)

        load.assert_not_called()
        self.assertIn(
            "canonical profile-load inputs changed",
            "; ".join(result["errors"]))
        self.assertNotIn("B1", result["ready"])

    def test_runtime_cas_includes_property_state_implementation_bytes(self):
        authorized_view, view_errors = \
            check_queue.profile_load_authorized_view(
                self.root, "profiles/test-profile/profile.md")
        self.assertEqual([], view_errors)
        implementation = self.root / "Tools/metadata_property_state.py"
        implementation.write_text(
            implementation.read_text(encoding="utf-8") +
            "\n# implementation revision B\n", encoding="utf-8")
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                side_effect=AssertionError(
                    "stale injected view must fail, not silently rerun")) \
                as load:
            result = check_queue.validate_runtime(
                self.root, authorized_profile_view=authorized_view)

        load.assert_not_called()
        self.assertIn(
            "canonical profile-load inputs changed",
            "; ".join(result["errors"]))
        self.assertNotIn("B1", result["ready"])

    def test_hub_derivation_reads_authorized_snapshot_not_transient_live_bytes(self):
        self.register_expression_layer([
            ("Existing canonical dependency-map path", "`Topics/A.md`"),
        ])
        authorized_view, view_errors = \
            check_queue.profile_load_authorized_view(
                self.root, "profiles/test-profile/profile.md")
        self.assertEqual([], view_errors)
        expression = self.root / dict(
            authorized_view["_manifest_slot_paths"])[
                check_queue.EXPRESSION_LAYER_SLOT]
        expression.write_text(
            expression.read_text(encoding="utf-8").replace(
                "`Topics/A.md`", "`Topics/B.md`"),
            encoding="utf-8",
        )

        # Model A -> B -> A around both live-tree CAS observations.  A live
        # slot read would accept B; the immutable producer snapshot must still
        # supply A.
        with mock.patch.object(
                check_queue.kblib, "repository_tree_sha256",
                return_value=authorized_view[
                    "profile_snapshot_sha256"]):
            paths, errors = check_queue.profile_hub_paths(
                self.root, "profiles/test-profile/profile.md",
                authorized_view=authorized_view,
                evaluate_if_missing=False)
        self.assertEqual([], errors)
        self.assertIn("Topics/A.md", paths)
        self.assertNotIn("Topics/B.md", paths)

    def test_hub_derivation_rejects_revision_after_profile_load(self):
        producer = check_queue.profile_load_authorized_view
        calls = []

        def admit_then_mutate(*args, **kwargs):
            authorized_view, errors = producer(*args, **kwargs)
            calls.append(authorized_view)
            if len(calls) == 1 and authorized_view is not None:
                slot_paths = dict(
                    authorized_view["_manifest_slot_paths"])
                expression = self.root / slot_paths[
                    check_queue.EXPRESSION_LAYER_SLOT]
                expression.write_text(
                    expression.read_text(encoding="utf-8") +
                    "\n<!-- revision B after authorization -->\n",
                    encoding="utf-8",
                )
            return authorized_view, errors

        with mock.patch.object(
                check_queue, "profile_load_authorized_view",
                side_effect=admit_then_mutate):
            result = check_queue.validate_runtime(self.root)

        self.assertEqual(1, len(calls))
        self.assertNotIn("B1", result["ready"])
        self.assertIn(
            "changed after profile-load authorization",
            "; ".join(result["errors"]),
        )
        reasons = "; ".join(dict(result["blocked"])["B1"])
        self.assertIn("changed after profile-load authorization", reasons)
        self.assertIn("snapshot mismatch before Expression hub", reasons)

    def test_corrective_profile_mode_retains_a_valid_authorized_view(self):
        profile_producer = check_queue.check_profile.evaluate_profile_load
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                wraps=profile_producer) as profile_load:
            ordinary = check_queue.validate_runtime(self.root)
            corrective = check_queue.validate_runtime(
                self.root,
                allow_invalid_current_profile_for_corrective_adoption=True,
                allow_active_standards_mismatch_for_adoption=True,
            )

        # Each validation evaluates profile-load exactly once.  Corrective
        # permission does not discard either valid before-view and does not
        # trigger a speculative second Profile producer run.
        self.assertEqual(2, profile_load.call_count)
        self.assertEqual([], ordinary["errors"])
        self.assertEqual([], corrective["errors"])
        ordinary_view = ordinary["_profile_authorized_view"]
        corrective_view = corrective["_profile_authorized_view"]
        ordinary_standards = ordinary[
            "_active_standards_authorized_view"]
        corrective_standards = corrective[
            "_active_standards_authorized_view"]
        self.assertIsInstance(corrective_view, dict)
        self.assertIsInstance(corrective_standards, dict)
        for field in (
                "selected_profile_manifest", "profile_snapshot_sha256",
                "profile_contract_fingerprint",
                "profile_load_inputs_sha256"):
            self.assertEqual(ordinary_view[field], corrective_view[field])
        for field in (
                "standards_version", "selected_profile_manifest",
                "active_standards_sha256"):
            self.assertEqual(
                ordinary_standards[field], corrective_standards[field])

    def test_corrective_profile_escape_runs_one_failed_profile_load(self):
        self.register_expression_layer(None)
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                wraps=check_queue.check_profile.evaluate_profile_load) as load:
            result = check_queue.validate_runtime(
                self.root,
                allow_invalid_current_profile_for_corrective_adoption=True,
            )

        load.assert_called_once()
        self.assertEqual([], result["errors"])
        self.assertIsNone(result["_profile_authorized_view"])

    def test_registered_dependency_map_not_yet_created_is_a_candidate(self):
        (self.root / "Topics/A.md").unlink()
        self.register_expression_layer([
            ("Existing canonical dependency-map ID/path", "`Topics/A.md`"),
        ])
        result, reasons = self.blocked_reasons("B1")
        self.assertEqual([], reasons)
        self.assertEqual(["Topics/A.md (Expression Layer Entry)"],
                         result["hub_page_admission"]["B1"]["candidates"])

    def test_opaque_dependency_map_cells_are_skipped(self):
        self.register_expression_layer([
            ("Existing canonical dependency-map path", "`None`"),
            ("Existing canonical dependency-map ID", "`atlas-map-01`"),
        ])
        paths, errors = check_queue.profile_hub_paths(
            str(self.root), "profiles/test-profile/profile.md")
        self.assertEqual(set(), paths)
        self.assertEqual([], errors)

    def test_unfilled_dependency_map_is_rejected_by_profile_load(self):
        self.register_expression_layer([
            ("Existing canonical dependency-map ID/path", "TODO(profile)"),
        ])
        paths, errors = check_queue.profile_hub_paths(
            str(self.root), "profiles/test-profile/profile.md")
        self.assertEqual(set(), paths)
        self.assertIn("unfilled sentinel", "; ".join(errors))

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
        result = check_queue.validate_runtime(self.root)
        self.assertNotIn("B1", result["ready"])
        joined = "; ".join(result["errors"])
        self.assertIn("slot-binding-unresolved", joined)
        self.assertIn("Expression Layer Entry", joined)

    def test_unclassifiable_manifest_page_is_not_silently_admitted(self):
        for body in ("---\ntype: overview\n\n# A\n",
                     "---\ntype: overview\n  stray: 1\n---\n\n# A\n",
                     "---\n- overview\n---\n\n# A\n"):
            with self.subTest(body=body):
                self.write_page("Topics/A.md", body)
                result = check_queue.validate_runtime(self.root)
                self.assertNotIn("B1", result["ready"])
                if result["errors"]:
                    self.assertIn(
                        "invalid page frontmatter",
                        "; ".join(result["errors"]))
                else:
                    reasons = dict(result["blocked"]).get("B1", [])
                    self.assertIn(
                        "cannot be classified against K13/10 hub roles",
                        "; ".join(reasons))

    def test_shipped_example_profile_registration_is_parsed(self):
        # A shipped example is intentionally not a selectable runtime Profile;
        # exercise only the raw parser retained for corrective diagnostics.
        paths, errors = check_queue._unadmitted_profile_hub_paths(
            str(REPO), "profiles/examples/agent-atlas/profile.md")
        self.assertEqual([], errors)
        self.assertEqual({"Interview Preparation/Interview Overview.md"},
                         paths)


class CheckQueueTests(QueueFixture):
    def test_runtime_reuses_an_empty_revalidation_requirements_map(self):
        """An empty derived map is cached data, not a cache miss."""
        original = check_queue.standards_revalidation_requirements
        with mock.patch.object(
                check_queue, "standards_revalidation_requirements",
                wraps=original) as requirements_build:
            result = check_queue.validate_runtime(self.root)
            self.assertEqual(
                [], check_queue.outstanding_standards_revalidation(
                    result, "B1"))

        self.assertEqual([], result["errors"])
        self.assertEqual({}, result["_standards_revalidation_requirements"])
        self.assertEqual(1, requirements_build.call_count)

    def test_required_completion_predicate_consumes_only_runtime_result(self):
        result = {
            "errors": [],
            "writer_locks": [],
            "progress": {"contract": {"completion_semantics": "build"}},
            "queue": {"required_queue": [{"id": "B1"}]},
            "remaining": 0,
        }
        self.assertEqual(
            [], check_queue.required_queue_completion_errors(result))
        result["remaining"] = 1
        self.assertEqual(
            ["remaining_required_work_units=1, expected 0"],
            check_queue.required_queue_completion_errors(result))
        result["errors"] = ["authorized Profile snapshot mismatch"]
        self.assertEqual(
            ["authorized Profile snapshot mismatch"],
            check_queue.required_queue_completion_errors(result))

    def test_terminal_proof_116_history_requires_profile_binding_shape(self):
        receipt_id = "audit-proof-profile-binding"
        canonical = "sha256:" + "a" * 64
        base = {
            "tool_version": "1.16.0",
            "profile_snapshot_sha256": canonical,
            "profile_contract_fingerprint": canonical,
        }
        self.assertEqual(
            [], check_queue._terminal_proof_profile_binding_errors(
                base, receipt_id))
        for version in ("1.16.0", "1.16.1", "2.0.0"):
            for field in ("profile_snapshot_sha256",
                          "profile_contract_fingerprint"):
                with self.subTest(version=version, field=field):
                    receipt = dict(base, tool_version=version)
                    if version == "2.0.0":
                        receipt["profile_load_inputs_sha256"] = canonical
                        receipt["repository_snapshot_sha256"] = canonical
                    receipt.pop(field)
                    errors = \
                        check_queue._terminal_proof_profile_binding_errors(
                            receipt, receipt_id)
                    self.assertEqual(1, len(errors), errors)
                    self.assertIn("lacks canonical %s" % field, errors[0])

    def test_terminal_proof_117_history_requires_current_use_bindings(self):
        receipt_id = "audit-proof-profile-input-binding"
        canonical = "sha256:" + "a" * 64
        base = {
            "profile_snapshot_sha256": canonical,
            "profile_contract_fingerprint": canonical,
        }
        # Sealed 1.16 receipts predate this producer promise and remain valid.
        self.assertEqual(
            [], check_queue._terminal_proof_profile_binding_errors(
                dict(base, tool_version="1.16.0"), receipt_id))
        for version in ("1.17.0", "1.17.1", "2.0.0"):
            with self.subTest(version=version):
                errors = check_queue._terminal_proof_profile_binding_errors(
                    dict(base, tool_version=version), receipt_id)
                self.assertEqual(2, len(errors), errors)
                self.assertIn(
                    "profile_load_inputs_sha256", "; ".join(errors))
                self.assertIn(
                    "repository_snapshot_sha256", "; ".join(errors))
                self.assertEqual(
                    [], check_queue._terminal_proof_profile_binding_errors(
                        dict(base, tool_version=version,
                             profile_load_inputs_sha256=canonical,
                             repository_snapshot_sha256=canonical),
                        receipt_id))

    def test_terminal_proof_116_history_rejects_noncanonical_binding(self):
        receipt = {
            "tool_version": "1.16.0",
            "profile_snapshot_sha256": "sha256:" + "a" * 63,
            "profile_contract_fingerprint": "SHA256:" + "b" * 64,
        }
        errors = check_queue._terminal_proof_profile_binding_errors(
            receipt, "audit-proof-profile-binding")
        self.assertEqual(2, len(errors), errors)
        self.assertTrue(all("lacks canonical" in error for error in errors))

    def test_terminal_proof_117_history_rejects_noncanonical_input_binding(self):
        canonical = "sha256:" + "a" * 64
        receipt = {
            "tool_version": "1.17.0",
            "profile_snapshot_sha256": canonical,
            "profile_contract_fingerprint": canonical,
            "profile_load_inputs_sha256": "SHA256:" + "b" * 64,
            "repository_snapshot_sha256": canonical,
        }
        errors = check_queue._terminal_proof_profile_binding_errors(
            receipt, "audit-proof-profile-input-binding")
        self.assertEqual(1, len(errors), errors)
        self.assertIn("profile_load_inputs_sha256", errors[0])

    def test_terminal_proof_117_history_rejects_noncanonical_repository(self):
        canonical = "sha256:" + "a" * 64
        receipt = {
            "tool_version": "1.17.0",
            "profile_snapshot_sha256": canonical,
            "profile_contract_fingerprint": canonical,
            "profile_load_inputs_sha256": canonical,
            "repository_snapshot_sha256": "SHA256:" + "b" * 64,
        }
        errors = check_queue._terminal_proof_profile_binding_errors(
            receipt, "audit-proof-repository-binding")
        self.assertEqual(1, len(errors), errors)
        self.assertIn("repository_snapshot_sha256", errors[0])

    def test_terminal_proof_115_history_stays_compatible_without_binding(self):
        self.assertEqual(
            [], check_queue._terminal_proof_profile_binding_errors(
                {"tool_version": "1.15.0"}, "audit-proof-legacy"))

    def test_terminal_proof_history_does_not_reinterpret_canonical_digests(self):
        # Historical replay preserves the proof's producer-era statement.  A
        # canonical digest is shape-checked here; only the current completion
        # consumer compares it with live Profile evidence.
        receipt = {
            "tool_version": "1.16.0",
            "profile_snapshot_sha256": "sha256:" + "0" * 64,
            "profile_contract_fingerprint": "sha256:" + "f" * 64,
        }
        self.assertEqual(
            [], check_queue._terminal_proof_profile_binding_errors(
                receipt, "audit-proof-sealed"))

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
        proposal["batch_specs"].append({
            "id": "B3", "family": "Core", "order_hint": 3,
            "source_route": "R03", "execution_mode": "concurrent-worker",
            "depends_on": ["B2"], "confirmation_required": False,
            "work_spec_path": None, "work_spec_sha256": None,
        })
        proposal["pages"].append({
            "path": "Topics/C.md", "coverage_disposition": "required",
            "canonical_owner": "Topics/C.md", "type": "concept",
            "priority": "P1", "tier": "M",
            "authoring_status": "drafted",
            "prerequisites": ["Topics/B.md"], "batch": "B3",
            "next_batch": "B3", "deferred_reason": None,
            "reentry_condition": None, "gate_receipts": [],
            "property_state": {},
        })
        proposal_path = self.root / proposal_relative
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        proposal_path.write_text(kblib.canonical_yaml(proposal),
                                 encoding="utf-8")
        plan_relative = ".cambium/deltas/amendments/A-SCOPE.yaml"
        plan = {
            "schema_version": 1, "amendment_id": "A-SCOPE",
            "operation": "scope-replan",
            "affected_pages": ["Topics/C.md"],
            "affected_batches": ["B3"],
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

    def test_replan_protocol_compatibility_stays_fail_closed(self):
        queue = self.queue()
        queue["queue_revision"] = 2
        self.write_queue(queue)
        self.add_replan_amendment(
            "A-R1", 1, 2, kblib.sha256_file(self.queue_path),
            "audit-replan-r1",
        )

        registration_path = self.root / \
            ".cambium/receipts/amendment-registrations.jsonl"
        registration = json.loads(registration_path.read_text(
            encoding="utf-8").strip())
        registration["tool_version"] = \
            check_queue.REGISTER_AMENDMENT_TOOL_VERSION
        registration_path.write_text(json.dumps(registration) + "\n",
                                     encoding="utf-8")
        current_errors = "\n".join(
            check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("current registration decision_mode is invalid",
                      current_errors)
        self.assertIn("current registration change_classes must be",
                      current_errors)

        registration["tool_version"] = "9.9.9"
        registration_path.write_text(json.dumps(registration) + "\n",
                                     encoding="utf-8")
        replan_path = self.root / ".cambium/receipts/replans.jsonl"
        replan = json.loads(replan_path.read_text(encoding="utf-8").strip())
        replan["tool_version"] = "9.9.9"
        replan_path.write_text(json.dumps(replan) + "\n", encoding="utf-8")
        unknown_errors = "\n".join(
            check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("unsupported register_amendment producer version '9.9.9'",
                      unknown_errors)
        self.assertIn("unsupported compile_queue producer version '9.9.9'",
                      unknown_errors)

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
        install_loadable_profile(
            fresh, profile_id="sample", override_rows=override_rows)
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
        self.assertTrue(
            (fresh / standards_state.STATE_PATH).is_file(),
            "failed task initialization preserves pre-runtime governance")
        self.assertFalse((fresh / ".cambium/state").exists())
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
                self.assertIn("selected Profile failed profile-load",
                              completed.stdout)
                self.assertIn("override-value-domain", completed.stdout)
                self.assertIn("expected a positive integer", completed.stdout)
                self.assertTrue(
                    (fresh / standards_state.STATE_PATH).is_file())
                self.assertFalse((fresh / ".cambium/state").exists())

    def test_init_creates_empty_state_without_fake_work_and_refuses_overwrite(self):
        fresh = Path(self.tmp.name) / "fresh"
        install_loadable_profile(fresh, profile_id="sample")
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
        install_loadable_profile(fresh, profile_id="sample")
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
        # 1, not argparse's stock 2: a missing required option is a usage
        # error, and 2 is reserved here for HOLD (no failure, candidates
        # remain).  Sharing one code made "you typed it wrong" and "clean but
        # not quiet" indistinguishable to every caller.  See
        # kblib.ArgumentParser.
        self.assertEqual(1, missing.returncode, missing.stdout)
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
