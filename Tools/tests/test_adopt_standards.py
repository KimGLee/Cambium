import copy
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import adopt_standards
import check_batch_close
import check_page_contract
import check_profile
import check_queue
# The requirements derivation is spied on below, and its caller reads
# that name in the module the caller lives in.
import queue_runtime.runtime
import check_vocab
import kblib
import seal_receipts
import standards_state
import update_queue
from profile_fixture import install_loadable_profile
from test_update_queue import UpdateQueueTests


class AdoptStandardsTests(unittest.TestCase):
    GOVERNANCE = "kernel/K00 Standards Control/03 Standards Governance.md"
    PLAN = ".cambium/deltas/standards-adoptions/SA-001.yaml"
    RECEIPTS = ".cambium/receipts/standards-adoptions.jsonl"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        governance = self.root / self.GOVERNANCE
        governance.parent.mkdir(parents=True, exist_ok=True)
        governance.write_text(
            "## Standards State And Adoption History\n\n"
            "Adopter state is external to the Kernel.\n",
            encoding="utf-8",
        )
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        registry.write_text(
            "## Stable Gate ID Registry\n\n"
            "| Gate ID | Tool | Tool version | Check | Mode | Dimension "
            "| Lifecycle |\n"
            "|---|---|---|---|---|---|---|\n"
            "| profile-load | check_profile | %s | profile-check-summary | * | guidance_and_contract | not-batch-scoped |\n"
            "| wiki-link-integrity | check_links | 1.6.0 | link-check-summary | * | * | not-batch-scoped |\n"
            "| required-queue-consistency | check_queue | %s | required_queue | consistency | * | not-batch-scoped |\n"
            "| required-queue-admission | check_queue | %s | required_queue | require-ready:* | * | queued |\n"
            "| batch-close | check_batch_close | %s | batch_close_gate | * | * | merge-ready |\n\n"
            "## Standards Revalidation Capability Registry\n\n"
            "| Gate ID | Role | Owner | Claim edge | Scope protocol | Binding protocol |\n"
            "|---|---|---|---|---|---|\n"
            "| profile-load | special-owner | profile-load | after-image-admission | profile-after-image | profile-fingerprints |\n"
            "| wiki-link-integrity | semantic-leaf | batch-close | project-to-owner | inherit-owner-scope | owner-member-chain |\n"
            "| required-queue-consistency | immediate-owner | required-queue-consistency | adoption-commit | runtime-after-image | runtime-state-fingerprints |\n"
            "| required-queue-admission | native-owner | required-queue-admission | native-transition | native-owner-scope | native-owner-receipt |\n"
            "| batch-close | native-owner | batch-close | native-transition | native-owner-scope | native-owner-receipt |\n" % (
                check_profile.TOOL_VERSION,
                check_queue.TOOL_VERSION,
                check_queue.TOOL_VERSION,
                check_batch_close.TOOL_VERSION,
            ),
            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, relative):
        return kblib.load_yaml_file(self.root / relative)

    def run_tool(self, tool, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / tool), str(self.root), *args],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def pause(self):
        completed = self.run_tool(
            "update_task.py", "--transition", "paused",
            "--checkpoint-summary", "pause before Standards adoption",
            "--expected-progress-sha256",
            kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at", "2026-08-05T00:03:00Z",
            "--apply",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)

    def open_b1_and_hold_for_revalidation(self):
        gate_run = self.run_tool(
            "check_queue.py", "--require-ready", "B1", "--receipts",
            ".cambium/receipts/gates.jsonl")
        self.assertEqual(0, gate_run.returncode, gate_run.stdout)
        gate = json.loads((self.root / ".cambium/receipts/gates.jsonl")
                          .read_text(encoding="utf-8").splitlines()[-1])
        queue = self.load(check_queue.QUEUE_PATH)
        opened = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "open",
            "--gate-receipt", gate["receipt_id"],
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at", "2026-08-05T00:01:00Z",
            "--apply")
        self.assertEqual(0, opened.returncode, opened.stdout)
        queue = self.load(check_queue.QUEUE_PATH)
        held = self.run_tool(
            "update_queue.py", "--id", "B1", "--hold-state",
            "revalidation-required", "--reason",
            "Standards predicate changed",
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at", "2026-08-05T00:02:00Z",
            "--apply")
        self.assertEqual(0, held.returncode, held.stdout)
        return gate["receipt_id"]

    def plan(self, *, invalidated_receipt=None, overrides=None):
        # The live adopter state starts aligned to approved 3.0.  The plan
        # proposes 3.1 while K00/03 remains an unchanged rules owner.
        queue = self.load(check_queue.QUEUE_PATH)
        progress = self.load(check_queue.PROGRESS_PATH)
        contract = progress["contract"]
        semantic = invalidated_receipt is not None
        profile_evidence, profile_errors = check_queue.profile_load_evidence(
            self.root, queue["selected_profile_manifest"])
        self.assertEqual([], profile_errors)
        plan = {
            "schema_version": 2,
            "adoption_id": "SA-001",
            "task_id": queue["task_id"],
            "task_state_before": progress["task_state"],
            "contract_version_before": contract["contract_version"],
            "contract_version_after": "c2" if semantic else
                contract["contract_version"],
            "standards_version_before": queue["standards_version"],
            "standards_version_after": "3.1.0",
            "standards_effective_date_after": "2026-08-06",
            "standards_state_sha256_before": kblib.sha256_file(
                self.root / standards_state.STATE_PATH),
            "selected_profile_manifest_before":
                queue["selected_profile_manifest"],
            "selected_profile_manifest_after":
                queue["selected_profile_manifest"],
            "governance_revision_ref": self.GOVERNANCE,
            "governance_revision_sha256": kblib.sha256_file(
                self.root / self.GOVERNANCE),
            # The 1.5 upstream identity pair; the fixture corpus tracks a
            # nominal upstream so the recorded form is exercised.
            "upstream_source_ref": "https://example.test/cambium.git",
            "upstream_revision_id": "0123456789abcdef0123456789abcdef01234567",
            "standards_snapshot_sha256_after":
                kblib.repository_tree_sha256(self.root, "kernel"),
            "profile_snapshot_sha256_after":
                profile_evidence["profile_snapshot_sha256"],
            "profile_contract_fingerprint_after":
                profile_evidence["profile_contract_fingerprint"],
            "profile_load_inputs_sha256_after":
                profile_evidence["profile_load_inputs_sha256"],
            "selected_route_ids_after": copy.deepcopy(
                contract["selected_route_ids"]),
            "selected_card_paths_after": copy.deepcopy(
                contract["selected_card_paths"]),
            "selected_profile_route_ids_after": copy.deepcopy(
                contract["selected_profile_route_ids"]),
            "selected_read_sets_after": copy.deepcopy(
                contract["selected_read_sets"]),
            "loaded_module_paths_after": copy.deepcopy(
                contract["loaded_module_paths"]),
            "queue_revision_before": queue["queue_revision"],
            "queue_revision_after": queue["queue_revision"] + 1,
            "queue_state_revision_before": queue["state_revision"],
            "coverage_sha256_before": kblib.sha256_file(
                self.root / check_queue.COVERAGE_PATH),
            "required_queue_sha256_before": kblib.sha256_file(
                self.root / check_queue.QUEUE_PATH),
            "progress_sha256_before": kblib.sha256_file(
                self.root / check_queue.PROGRESS_PATH),
            "changed_predicates": [],
            "invalidated_evidence": [],
            "invalidation_boundaries": [],
            "immediate_gate_reruns": ["required-queue-consistency"],
            "boundary_gate_reruns": [],
        }
        if semantic:
            plan.update({
                "changed_predicates": [{
                    "predicate_id": "PRED-READY-001",
                    "owner_path": self.GOVERNANCE,
                    "change_kind": "modified",
                    "affected_gate_ids": ["required-queue-consistency"],
                }],
                "invalidated_evidence": [{
                    "receipt_id": invalidated_receipt,
                    "predicate_ids": ["PRED-READY-001"],
                    "dimension_ids": ["coverage_and_integration"],
                    "boundary_ids": ["INV-B1-READY"],
                    "reason_code": "predicate-changed",
                    "revalidation_scope_ids": ["B1"],
                }],
                "invalidation_boundaries": [{
                    "boundary_id": "INV-B1-READY",
                    "predicate_ids": ["PRED-READY-001"],
                    "target_kind": "batch",
                    "target_ids": ["B1"],
                    "required_gate_ids": ["required-queue-consistency"],
                }],
                "boundary_gate_reruns": ["required-queue-consistency"],
            })
        if overrides:
            plan.update(copy.deepcopy(overrides))
        path = self.root / self.PLAN
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
        return plan

    def command(self, *, apply=False, actor="worker"):
        args = [str(self.root), "--plan", self.PLAN]
        if apply:
            args.extend(["--apply", "--actor-role", actor])
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = adopt_standards.main(args)
        return code, stdout.getvalue()

    @staticmethod
    def legacy_plan_shape(plan):
        """Project a current plan onto the immutable pre-1.7 schema."""
        legacy = copy.deepcopy(plan)
        legacy["schema_version"] = 1
        legacy.pop("standards_effective_date_after", None)
        legacy.pop("standards_state_sha256_before", None)
        return legacy

    def test_a_contract_amendment_may_follow_an_adoption(self):
        """The other guarded contract writer must not be locked out.

        The latest-adoption binding was written when `adopt_standards` was
        the only writer of a materialized contract, so it read "the adoption
        is the last word on contract_version" -- a sentence no kernel module
        states.  Once the K13/06 Contract Amendment writer existed, that
        made every post-adoption amendment invalid, and the combination had
        no test because the amendment fixtures carry no adoption record.
        Here the amendment row supersedes exactly one field; everything the
        amendment cannot touch stays strictly bound.
        """
        self.pause()
        self.plan()
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        record = result["progress"]["standards_adoptions"][-1]

        progress = self.load(check_queue.PROGRESS_PATH)
        progress["contract"]["contract_version"] = "c-amended"
        progress.setdefault("amendments", []).append({
            "operation": "contract-amendment",
            "contract_version_before": record["contract_version_after"],
            "contract_version_after": "c-amended",
        })
        errors = check_queue.standards_adoption_errors(
            str(self.root), progress, result["receipt_catalog"],
            result["queue"])
        self.assertEqual(
            [], [e for e in errors if "contract_version_after" in e],
            "an amendment continuing from this adoption supersedes the "
            "adoption's contract_version binding")

        # Everything the amendment writer cannot touch stays bound.
        progress["contract"]["standards_version"] = "9.9.9"
        errors = check_queue.standards_adoption_errors(
            str(self.root), progress, result["receipt_catalog"],
            result["queue"])
        self.assertTrue(
            any("standards_version_after" in e for e in errors), errors)

    def test_an_unrelated_amendment_does_not_release_the_binding(self):
        """Only an amendment that literally continues from it supersedes."""
        self.pause()
        self.plan()
        self.assertEqual(0, self.command(apply=True, actor="integrator")[0])
        result = check_queue.validate_runtime(self.root)
        progress = self.load(check_queue.PROGRESS_PATH)
        progress["contract"]["contract_version"] = "c-drifted"
        progress.setdefault("amendments", []).append({
            "operation": "contract-amendment",
            "contract_version_before": "c-something-else",
            "contract_version_after": "c-drifted",
        })
        errors = check_queue.standards_adoption_errors(
            str(self.root), progress, result["receipt_catalog"],
            result["queue"])
        self.assertTrue(
            any("contract_version_after" in e for e in errors), errors)

    def test_upstream_identity_is_recorded_and_half_a_pair_is_refused(self):
        """1.5: the adoption record is what makes up/downstream comparable.

        The distribution publishes no version numbers, so the upstream pair
        (or its explicit null form) is required, recorded, receipt-bound,
        and surfaced by resume-status.  Half a pair identifies nothing and
        is refused; a legacy record without the fields stays valid history.
        """
        self.pause()
        plan = self.plan()
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        record = result["progress"]["standards_adoptions"][0]
        self.assertEqual("https://example.test/cambium.git",
                         record["upstream_source_ref"])
        self.assertEqual("0123456789abcdef0123456789abcdef01234567",
                         record["upstream_revision_id"])
        resume = self.run_tool("check_queue.py", "--resume-status")
        self.assertIn(
            "standards_upstream=https://example.test/cambium.git@0123456789"
            "abcdef0123456789abcdef01234567", resume.stdout)

    def test_a_declared_null_upstream_pair_is_an_answer(self):
        self.pause()
        plan = self.plan(overrides={
            "upstream_source_ref": None, "upstream_revision_id": None})
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        record = result["progress"]["standards_adoptions"][0]
        self.assertIsNone(record["upstream_source_ref"])
        self.assertIsNone(record["upstream_revision_id"])
        resume = self.run_tool("check_queue.py", "--resume-status")
        self.assertIn("standards_upstream=none-declared", resume.stdout)

    def test_half_an_upstream_pair_is_refused(self):
        self.pause()
        self.plan(overrides={"upstream_revision_id": None})
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(1, code, output)
        self.assertIn("both name the upstream or both be null", output)

    def test_noop_dry_run_and_missing_register_apply(self):
        self.pause()
        plan = self.plan()
        state_paths = [self.root / path for path in (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH)]
        before = [path.read_bytes() for path in state_paths]
        code, output = self.command()
        self.assertEqual(0, code, output)
        self.assertEqual(before, [path.read_bytes() for path in state_paths])
        self.assertFalse((self.root / self.RECEIPTS).exists())

        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("paused", result["progress"]["task_state"])
        self.assertEqual(2, result["queue"]["queue_revision"])
        self.assertEqual(0, result["queue"]["state_revision"])
        record = result["progress"]["standards_adoptions"][0]
        self.assertNotIn("after_progress_sha256", record)
        self.assertEqual(
            plan["profile_contract_fingerprint_after"],
            record["profile_contract_fingerprint_after"])
        self.assertEqual(
            plan["profile_load_inputs_sha256_after"],
            record["profile_load_inputs_sha256_after"])
        lines = [json.loads(line) for line in (self.root / self.RECEIPTS)
                 .read_text(encoding="utf-8").splitlines()]
        self.assertEqual(3, len(lines))
        self.assertEqual("prepare", lines[0]["transaction_phase"])
        self.assertEqual("required_queue", lines[1]["check"])
        self.assertEqual("commit", lines[2]["transaction_phase"])
        adoption_rows = [row for row in lines
                         if row.get("tool") == adopt_standards.TOOL]
        # Candidate Profile evaluation is in-memory transaction evidence.  It
        # must not publish a receipt whose selected after-image is combined
        # with the current Queue identity that exists before commit.
        self.assertFalse(any(
            row.get("tool") == check_profile.TOOL for row in lines))
        self.assertEqual(
            {plan["profile_contract_fingerprint_after"]},
            {row.get("profile_contract_fingerprint_after")
             for row in adoption_rows})
        self.assertEqual(
            {plan["profile_load_inputs_sha256_after"]},
            {row.get("profile_load_inputs_sha256_after")
             for row in adoption_rows})
        self.assertEqual(
            {adopt_standards.TOOL_VERSION},
            {row.get("tool_version") for row in adoption_rows})
        self.assertEqual(
            {adopt_standards.GATE_ID},
            {row.get("gate_id") for row in adoption_rows})

    def test_apply_appends_to_existing_receipt_register(self):
        self.pause()
        existing = kblib.make_receipt(
            "fixture", "1", "fixture", "before", "pass", "existing", 1)
        receipt_path = self.root / self.RECEIPTS
        kblib.write_receipts(receipt_path, [existing])
        self.plan()
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        rows = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()]
        self.assertEqual(existing["receipt_id"], rows[0]["receipt_id"])
        self.assertEqual(4, len(rows))

    def test_state_write_failure_restores_before_bytes_and_records_abort(self):
        self.pause()
        self.plan()
        paths = [self.root / path for path in (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH, standards_state.STATE_PATH)]
        before = [path.read_bytes() for path in paths]
        original = kblib.atomic_write_text
        state_writes = {"count": 0}

        def fail_second_state_write(path, text, validator=None):
            if ".cambium/state" in str(path):
                state_writes["count"] += 1
                if state_writes["count"] == 2:
                    raise OSError("injected state write failure")
            return original(path, text, validator=validator)

        with mock.patch.object(
                adopt_standards.kblib, "atomic_write_text",
                side_effect=fail_second_state_write):
            code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(1, code, output)
        self.assertEqual(before, [path.read_bytes() for path in paths])
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())
        rows = [json.loads(line) for line in (self.root / self.RECEIPTS)
                .read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["prepare", "abort"],
                         [row["transaction_phase"] for row in rows])
        self.assertEqual(
            {adopt_standards.GATE_ID},
            {row.get("gate_id") for row in rows})
        ordinary_errors = check_queue.validate_runtime(self.root)["errors"]
        self.assertEqual([], ordinary_errors)
        recovered = check_queue.validate_runtime(
            self.root,
            allow_invalid_current_profile_for_corrective_adoption=True,
            allow_active_standards_mismatch_for_adoption=True)
        self.assertEqual([], recovered["errors"])

    def poison_selected_profile_closure(self):
        slots = self.root / "profiles/test-profile/slots.md"
        owned = "profiles/test-profile/slots.md#Synthetic Predicate"
        foreign = "profiles/foreign-profile/slots.md#Synthetic Predicate"
        text = slots.read_text(encoding="utf-8")
        self.assertIn(owned, text)
        slots.write_text(text.replace(owned, foreign, 1), encoding="utf-8")

    def revise_profile_load_inputs(self):
        interface = self.root / "profiles/README.md"
        interface.write_text(
            interface.read_text(encoding="utf-8") +
            "\nCanonical interface revision B.\n",
            encoding="utf-8",
        )

    def test_locked_prewrite_profile_cas_rejects_post_admission_drift(self):
        self.pause()
        self.plan()
        prepared = adopt_standards._prepare_result(self.root, self.PLAN)
        state_paths = [self.root / path for path in (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH)]
        before = [path.read_bytes() for path in state_paths]
        self.poison_selected_profile_closure()
        receipt_path = self.root / self.RECEIPTS

        with self.assertRaisesRegex(
                ValueError, "locked pre-write candidate Profile failed"):
            adopt_standards._commit_transaction(prepared, receipt_path)

        self.assertEqual(before, [path.read_bytes() for path in state_paths])
        self.assertFalse(receipt_path.exists())
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_locked_prewrite_cas_compares_the_typed_contract_fingerprint(self):
        self.pause()
        self.plan()
        prepared = adopt_standards._prepare_result(self.root, self.PLAN)
        prepared["profile_evidence"]["profile_contract_fingerprint"] = \
            "sha256:" + "0" * 64

        with self.assertRaisesRegex(
                ValueError, "profile_contract_fingerprint changed"):
            adopt_standards._commit_transaction(
                prepared, self.root / self.RECEIPTS)

        self.assertFalse((self.root / self.RECEIPTS).exists())
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_locked_prewrite_cas_compares_profile_load_inputs(self):
        self.pause()
        self.plan()
        prepared = adopt_standards._prepare_result(self.root, self.PLAN)
        prepared["profile_evidence"]["profile_load_inputs_sha256"] = \
            "sha256:" + "0" * 64

        with self.assertRaisesRegex(
                ValueError, "profile_load_inputs_sha256 changed"):
            adopt_standards._commit_transaction(
                prepared, self.root / self.RECEIPTS)

        self.assertFalse((self.root / self.RECEIPTS).exists())
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_postwrite_profile_drift_rolls_back_state_and_records_abort(self):
        self.pause()
        self.plan()
        state_paths = [self.root / path for path in (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH)]
        before = [path.read_bytes() for path in state_paths]
        original = kblib.atomic_write_text
        state_writes = {"count": 0}

        def poison_after_third_state_write(path, text, validator=None):
            result = original(path, text, validator=validator)
            if ".cambium/state" in str(path):
                state_writes["count"] += 1
                if state_writes["count"] == 3:
                    self.poison_selected_profile_closure()
            return result

        with mock.patch.object(
                adopt_standards.kblib, "atomic_write_text",
                side_effect=poison_after_third_state_write):
            code, output = self.command(apply=True, actor="integrator")

        self.assertEqual(1, code, output)
        self.assertIn("post-write candidate Profile failed", output)
        self.assertEqual(before, [path.read_bytes() for path in state_paths])
        rows = [json.loads(line) for line in (
            self.root / self.RECEIPTS).read_text(
                encoding="utf-8").splitlines()]
        self.assertEqual(
            ["prepare", "abort"],
            [row["transaction_phase"] for row in rows])
        self.assertFalse(any(
            row.get("tool") == check_profile.TOOL for row in rows))
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_postwrite_profile_load_input_drift_rolls_back_and_aborts(self):
        self.pause()
        self.plan()
        state_paths = [self.root / path for path in (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH)]
        before = [path.read_bytes() for path in state_paths]
        original = kblib.atomic_write_text
        state_writes = 0

        def revise_after_third_state_write(path, text, validator=None):
            nonlocal state_writes
            result = original(path, text, validator=validator)
            if ".cambium/state" in str(path):
                state_writes += 1
                if state_writes == 3:
                    self.revise_profile_load_inputs()
            return result

        with mock.patch.object(
                adopt_standards.kblib, "atomic_write_text",
                side_effect=revise_after_third_state_write):
            code, output = self.command(apply=True, actor="integrator")

        self.assertEqual(1, code, output)
        self.assertIn("post-write candidate Profile load inputs differ",
                      output)
        self.assertEqual(before, [path.read_bytes() for path in state_paths])
        rows = [json.loads(line) for line in (
            self.root / self.RECEIPTS).read_text(
                encoding="utf-8").splitlines()]
        self.assertEqual(
            ["prepare", "abort"],
            [row["transaction_phase"] for row in rows])
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_profile_drift_during_final_append_restores_state_and_keeps_lock(
            self):
        """A durable commit plus later failed CAS needs reconciliation."""
        self.pause()
        self.plan()
        state_paths = [self.root / path for path in (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH)]
        before = [path.read_bytes() for path in state_paths]
        original = kblib.write_receipts_observed
        poisoned = {"value": False}

        def poison_after_commit_append(path, receipts, before=None):
            outcome = original(path, receipts, before=before)
            if (not poisoned["value"] and any(
                    row.get("transaction_phase") == "commit"
                    for row in receipts)):
                poisoned["value"] = True
                self.poison_selected_profile_closure()
            return outcome

        with mock.patch.object(
                adopt_standards.kblib, "write_receipts_observed",
                side_effect=poison_after_commit_append):
            code, output = self.command(apply=True, actor="integrator")

        self.assertEqual(1, code, output)
        self.assertIn("post-final-receipt candidate Profile failed", output)
        self.assertIn("recovery is incomplete", output)
        self.assertEqual(before, [path.read_bytes() for path in state_paths])
        rows = [json.loads(line) for line in (
            self.root / self.RECEIPTS).read_text(
                encoding="utf-8").splitlines()]
        self.assertEqual(
            ["prepare", None, "commit", "abort"],
            [row.get("transaction_phase") for row in rows])
        lock = self.root / ".cambium/tmp/state-writer.lock"
        self.assertTrue(lock.is_dir())
        owner = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
        prepared_fingerprint = owner["operation"].get(
            "profile_contract_fingerprint_after")
        self.assertRegex(prepared_fingerprint, r"^sha256:[0-9a-f]{64}$")
        prepared_inputs = owner["operation"].get(
            "profile_load_inputs_sha256_after")
        self.assertRegex(prepared_inputs, r"^sha256:[0-9a-f]{64}$")

    def test_profile_load_input_drift_during_final_append_keeps_lock(self):
        self.pause()
        self.plan()
        state_paths = [self.root / path for path in (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH)]
        before = [path.read_bytes() for path in state_paths]
        original = kblib.write_receipts_observed
        revised = False

        def revise_after_commit_append(path, receipts, before=None):
            nonlocal revised
            outcome = original(path, receipts, before=before)
            if (not revised and any(
                    row.get("transaction_phase") == "commit"
                    for row in receipts)):
                revised = True
                self.revise_profile_load_inputs()
            return outcome

        with mock.patch.object(
                adopt_standards.kblib, "write_receipts_observed",
                side_effect=revise_after_commit_append):
            code, output = self.command(apply=True, actor="integrator")

        self.assertTrue(revised)
        self.assertEqual(1, code, output)
        self.assertIn(
            "post-final-receipt candidate Profile load inputs differ",
            output)
        self.assertIn("recovery is incomplete", output)
        self.assertEqual(before, [path.read_bytes() for path in state_paths])
        rows = [json.loads(line) for line in (
            self.root / self.RECEIPTS).read_text(
                encoding="utf-8").splitlines()]
        self.assertEqual(
            ["prepare", None, "commit", "abort"],
            [row.get("transaction_phase") for row in rows])
        self.assertTrue(
            (self.root / ".cambium/tmp/state-writer.lock").is_dir())

    def test_closed_schema_stale_hash_and_contract_bump_fail_closed(self):
        self.pause()
        base = self.plan()
        cases = (
            (dict(base, task_state_before="completion-candidate"),
             "active or paused"),
            (dict(base, objective="mutate forbidden state"),
             "unsupported field"),
            (dict(base, coverage_sha256_before="sha256:" + "0" * 64),
             "SHA does not match current bytes"),
            (dict(base, profile_contract_fingerprint_after=
                  "sha256:" + "0" * 64),
             "profile_contract_fingerprint_after is stale"),
            (dict(base, profile_load_inputs_sha256_after=
                  "sha256:" + "0" * 64),
             "profile_load_inputs_sha256_after is stale"),
            (dict(base, selected_route_ids_after=["R01"]),
             "requires a new contract_version"),
        )
        for candidate, expected in cases:
            with self.subTest(expected=expected):
                (self.root / self.PLAN).write_text(
                    kblib.canonical_yaml(candidate), encoding="utf-8")
                code, output = self.command()
                self.assertEqual(1, code, output)
                self.assertIn(expected, output)

    def test_governance_or_snapshot_drift_rejects_plan(self):
        self.pause()
        self.plan()
        governance = self.root / self.GOVERNANCE
        governance.write_text(
            governance.read_text(encoding="utf-8") + "\nchanged after plan\n",
            encoding="utf-8")
        code, output = self.command()
        self.assertEqual(1, code, output)
        self.assertTrue(
            "governance_revision_sha256" in output or
            "standards_snapshot_sha256_after" in output, output)

    def test_runtime_derives_revalidation_requirements_once(self):
        """One runtime view must not reparse every plan once per batch."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.plan(invalidated_receipt=invalidated_gate)
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)

        original_requirements = \
            check_queue.standards_revalidation_requirements
        with mock.patch.object(
                queue_runtime.runtime, "standards_revalidation_requirements",
                wraps=original_requirements) as requirements_build:
            first = check_queue.validate_runtime(self.root)
            result = check_queue.validate_runtime(self.root)

        self.assertEqual([], first["errors"])
        self.assertEqual([], result["errors"])
        self.assertEqual(2, requirements_build.call_count,
                         "each validation owns exactly one derived map")
        self.assertIn("_standards_revalidation_requirements", result)
        self.assertTrue(result["standards_revalidation_outstanding"]["B1"])

        # The cached private view is an optimization, not a new requirement
        # on helper callers.  Removing it must preserve the exact projection.
        reduced = {
            key: value for key, value in result.items()
            if key != "_standards_revalidation_requirements"
        }
        self.assertEqual(
            check_queue.outstanding_standards_revalidation(result, "B1"),
            check_queue.outstanding_standards_revalidation(reduced, "B1"),
        )
        self.assertEqual(
            check_queue.current_attempt_evidence_barrier(result, "B1"),
            check_queue.current_attempt_evidence_barrier(reduced, "B1"),
        )

    def test_semantic_adoption_preserves_history_but_filters_current_use(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.plan(invalidated_receipt=invalidated_gate)
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertIn(invalidated_gate, result["receipt_catalog"])
        self.assertNotIn(invalidated_gate, result["current_receipt_catalog"])
        item = result["items_by_id"]["B1"]
        self.assertEqual("open", item["state"])
        self.assertEqual("revalidation-required", item["hold_state"])
        self.assertEqual(invalidated_gate, item["activation_receipt"])
        self.assertEqual("run-standards-revalidation:B1",
                         check_queue.resume_next_action(result, []))
        for consumer in (
                "activation gate", "merge-ready batch gate",
                "delta application", "revalidation hold clear"):
            with self.subTest(consumer=consumer):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    update_queue._receipt(result, invalidated_gate, consumer)
        close_errors = check_queue.close_gate_receipt_errors(
            result["current_receipt_catalog"], invalidated_gate,
            item_id="B1", task_id=result["queue"]["task_id"],
            queue_revision=result["queue"]["queue_revision"],
            queue_state_revision=result["queue"]["state_revision"],
            required_queue_sha256=result["queue_sha256"],
            coverage_ledger_sha256=result["coverage_sha256"],
            progress_ledger_sha256=result["progress_sha256"],
            delta_sha256=None, queue_consistency_receipt=None,
            delta_apply_receipt=None)
        self.assertTrue(any(
            "does not exist" in error or "references missing receipt" in error
                            for error in close_errors), close_errors)

        cleared = self.run_tool(
            "update_queue.py", "--id", "B1", "--hold-state", "none",
            "--gate-receipt", invalidated_gate,
            "--expected-state-revision", str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator", "--at", "2026-08-05T00:03:00Z",
            "--apply")
        self.assertEqual(1, cleared.returncode, cleared.stdout)
        self.assertIn("--standards-revalidation-receipt", cleared.stdout)

        boundary_run = self.run_tool(
            "check_queue.py", "--receipts",
            ".cambium/receipts/post-adoption-consistency.jsonl")
        self.assertEqual(0, boundary_run.returncode, boundary_run.stdout)
        boundary = json.loads((
            self.root / ".cambium/receipts/post-adoption-consistency.jsonl"
        ).read_text(encoding="utf-8").splitlines()[-1])
        aggregate_run = self.run_tool(
            "check_queue.py", "--require-revalidation", "B1",
            "--boundary-gate-receipt",
            "required-queue-consistency=%s" % boundary["receipt_id"],
            "--receipts", ".cambium/receipts/revalidation.jsonl")
        self.assertEqual(0, aggregate_run.returncode, aggregate_run.stdout)
        aggregate = json.loads((
            self.root / ".cambium/receipts/revalidation.jsonl"
        ).read_text(encoding="utf-8").splitlines()[-1])
        transition_at = (datetime.fromisoformat(
            aggregate["checked_at"].replace("Z", "+00:00")) +
            timedelta(seconds=1)).astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z")
        refreshed = check_queue.validate_runtime(self.root)
        clear_current = self.run_tool(
            "update_queue.py", "--id", "B1", "--hold-state", "none",
            "--standards-revalidation-receipt", aggregate["receipt_id"],
            "--expected-state-revision",
            str(refreshed["queue"]["state_revision"]),
            "--expected-sha256", refreshed["queue_sha256"],
            "--actor-role", "integrator", "--at", transition_at, "--apply")
        self.assertEqual(0, clear_current.returncode, clear_current.stdout)
        final = check_queue.validate_runtime(self.root)
        self.assertEqual([], final["errors"])
        self.assertEqual("none", final["items_by_id"]["B1"]["hold_state"])
        self.assertEqual([], check_queue.outstanding_standards_revalidation(
            final, "B1"))
        # Runtime authorization views are deliberately in-process immutable
        # objects (their keys are private); this barrier test mutates only the
        # public Queue projection, so copy that serializable surface rather
        # than pretending the authority context is durable state.
        poisoned = copy.deepcopy({
            key: value for key, value in final.items()
            if not key.startswith("_")
        })
        poisoned_item = poisoned["items_by_id"]["B1"]
        poisoned_item["state"] = "merge-ready"
        poisoned_item["batch_receipts"] = [invalidated_gate]
        self.assertIn("current attempt references invalidated receipt",
                      check_queue.current_attempt_evidence_barrier(
                          poisoned, "B1"))

        # Producer-era regression: a registered producer bump after the
        # aggregate was consumed must not orphan the recorded consumption.
        # Rewriting the consumed aggregate's stored tool_version to an older
        # era simulates exactly the state a later `check_queue` bump leaves
        # behind; the replay honors the recorded era, so the boundary stays
        # discharged and the runtime stays consistent.
        revalidation_path = self.root / ".cambium/receipts/revalidation.jsonl"
        aged_rows = []
        for line in revalidation_path.read_text(
                encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("receipt_id") == aggregate["receipt_id"]:
                row["tool_version"] = "0.9.0"
            aged_rows.append(json.dumps(row, ensure_ascii=False))
        revalidation_path.write_text("\n".join(aged_rows) + "\n",
                                     encoding="utf-8")
        aged = check_queue.validate_runtime(self.root)
        self.assertEqual([], aged["errors"])
        self.assertEqual([], check_queue.outstanding_standards_revalidation(
            aged, "B1"))
        self.assertIsNone(
            check_queue.current_attempt_evidence_barrier(aged, "B1"))

    # --- Boundary gates against the target batch's lifecycle position ------
    #
    # `required-queue-admission` is producible only while a batch is `queued`
    # and `batch-close` only while it is `merge-ready`, so an `open` batch
    # named by a boundary carrying either can produce neither.  Requiring the
    # whole union at hold-discharge time therefore deadlocked the hold: the
    # only exit from `open` is `merge-ready`, which refuses a held batch, and
    # the hold refuses to clear without an aggregate naming every gate.
    LIFECYCLE_AFFECTED_GATES = [
        "required-queue-consistency", "wiki-link-integrity"]
    LIFECYCLE_GATES = ["batch-close", "required-queue-consistency"]
    LINK_RECEIPTS = ".cambium/receipts/links.jsonl"

    def register_link_gate(self):
        """Register the leaf and its native batch-close owner mapping."""
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        text = registry.read_text(encoding="utf-8")
        if "| wiki-link-integrity | check_links |" not in text:
            text = text.replace(
                "\n## Standards Revalidation Capability Registry\n",
                "\n| wiki-link-integrity | check_links | 1.6.0 "
                "| link-check-summary | * | * | not-batch-scoped |\n\n"
                "## Standards Revalidation Capability Registry\n")
            text += (
                "| wiki-link-integrity | semantic-leaf | batch-close "
                "| project-to-owner | inherit-owner-scope "
                "| owner-member-chain |\n")
            registry.write_text(text, encoding="utf-8")

    def install_revalidation_capability_fixture(self):
        """Install the closed two-registry subset these tests exercise.

        Most adoption tests predate the capability registry and intentionally
        keep their tiny four-row Gate fixture.  These focused tests need a
        closed capability table, so they replace that fixture locally rather
        than making every older test accidentally depend on the new policy.
        """
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        registry.write_text(
            "## Stable Gate ID Registry\n\n"
            "| Gate ID | Tool | Tool version | Check | Mode | Dimension "
            "| Lifecycle |\n"
            "|---|---|---|---|---|---|---|\n"
            "| profile-load | check_profile | %s | profile-check-summary "
            "| * | guidance_and_contract | not-batch-scoped |\n"
            "| frontmatter-vocabulary | check_vocab | %s "
            "| vocab-check-summary | * | * | not-batch-scoped |\n"
            "| required-queue-consistency | check_queue | %s "
            "| required_queue | consistency | * | not-batch-scoped |\n"
            "| required-queue-admission | check_queue | %s "
            "| required_queue | require-ready:* | * | queued |\n"
            "| batch-review | manual-attestation | %s | batch_gate "
            "| * | none | open |\n"
            "| batch-close | check_batch_close | %s | batch_close_gate "
            "| * | * | merge-ready |\n"
            "| page-contract | check_page_contract | %s "
            "| page-contract-summary | * | * | not-batch-scoped |\n"
            "| standards-adoption | adopt_standards | %s "
            "| standards_adoption | * | * | not-batch-scoped |\n"
            "| standards-revalidation | check_queue | %s "
            "| required_queue | require-revalidation:* | * | queued, open |\n"
            "| runtime-card-synchronization | manual-attestation | %s "
            "| runtime-card-synchronization | * | guidance_and_contract "
            "| not-batch-scoped |\n\n"
            "## Standards Revalidation Capability Registry\n\n"
            "| Gate ID | Role | Owner | Claim edge | Scope protocol "
            "| Binding protocol |\n"
            "|---|---|---|---|---|---|\n"
            "| profile-load | special-owner | profile-load "
            "| after-image-admission | profile-after-image "
            "| profile-fingerprints |\n"
            "| frontmatter-vocabulary | semantic-leaf | batch-close "
            "| project-to-owner | inherit-owner-scope "
            "| owner-member-chain |\n"
            "| required-queue-consistency | immediate-owner "
            "| required-queue-consistency | adoption-commit "
            "| runtime-after-image | runtime-state-fingerprints |\n"
            "| required-queue-admission | native-owner "
            "| required-queue-admission | native-transition "
            "| native-owner-scope | native-owner-receipt |\n"
            "| batch-review | native-owner | batch-review "
            "| native-transition | native-owner-scope "
            "| native-owner-receipt |\n"
            "| batch-close | native-owner | batch-close "
            "| native-transition | native-owner-scope "
            "| native-owner-receipt |\n"
            "| page-contract | semantic-leaf | batch-close "
            "| project-to-owner | inherit-owner-scope "
            "| owner-member-chain |\n"
            "| standards-adoption | mechanism-only | none "
            "| mechanism-input-only | none | not-authorizing |\n"
            "| standards-revalidation | mechanism-only | none "
            "| mechanism-input-only | none | not-authorizing |\n"
            "| runtime-card-synchronization | unsupported | none "
            "| none | none | not-authorizing |\n" % (
                check_profile.TOOL_VERSION,
                check_vocab.TOOL_VERSION,
                check_queue.TOOL_VERSION,
                check_queue.TOOL_VERSION,
                check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
                check_batch_close.TOOL_VERSION,
                check_page_contract.TOOL_VERSION,
                adopt_standards.TOOL_VERSION,
                check_queue.TOOL_VERSION,
                check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
            ), encoding="utf-8")

    def capability_boundary_plan(self, invalidated_receipt, affected,
                                 required):
        """Build one current plan using affected leaves and owner closure."""
        self.install_revalidation_capability_fixture()
        affected = sorted(affected)
        required = sorted(required)
        return self.plan(invalidated_receipt=invalidated_receipt, overrides={
            "changed_predicates": [{
                "predicate_id": "PRED-CAPABILITY-001",
                "owner_path": self.GOVERNANCE,
                "change_kind": "modified",
                "affected_gate_ids": affected,
            }],
            "invalidated_evidence": [{
                "receipt_id": invalidated_receipt,
                "predicate_ids": ["PRED-CAPABILITY-001"],
                "dimension_ids": ["coverage_and_integration"],
                "boundary_ids": ["INV-B1-CAPABILITY"],
                "reason_code": "gate-semantics-changed",
                "revalidation_scope_ids": ["B1"],
            }],
            "invalidation_boundaries": [{
                "boundary_id": "INV-B1-CAPABILITY",
                "predicate_ids": ["PRED-CAPABILITY-001"],
                "target_kind": "batch",
                "target_ids": ["B1"],
                "required_gate_ids": required,
            }],
            "boundary_gate_reruns": required,
        })

    def test_pre_1_6_history_replays_raw_and_recorded_gate_union(self):
        """Atlas's 1.5 plan keeps raw leaves plus its immediate Gate.

        Pre-1.6 plans recorded semantic leaves directly.  Their global rerun
        union was the raw affected Gate union plus every Gate explicitly
        recorded on a boundary; Queue consistency can therefore be present
        even when it was not named by the predicate's affected leaves.  That
        sealed producer-era shape must replay, while new admission remains on
        the projected owner contract.
        """
        self.pause()
        raw_leaves = ["frontmatter-vocabulary", "page-contract"]
        legacy_required = sorted((
            *raw_leaves, "required-queue-consistency"))
        current_plan = self.capability_boundary_plan(
            "audit-fixture-initial-queue",
            sorted((*raw_leaves, "required-queue-consistency")),
            ["batch-close", "required-queue-consistency"])
        self.assertEqual([], self.plan_errors(current_plan))
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)

        # The fixture writer can only emit today's 1.6 shape.  Re-form its
        # newly written, otherwise complete transaction as bytes an immutable
        # 1.5 producer would have left behind.
        plan_path = self.root / self.PLAN
        legacy_plan = self.legacy_plan_shape(self.load(self.PLAN))
        legacy_plan["changed_predicates"][0][
            "affected_gate_ids"] = raw_leaves
        legacy_plan["invalidation_boundaries"][0][
            "required_gate_ids"] = legacy_required
        legacy_plan["boundary_gate_reruns"] = legacy_required
        plan_path.write_text(
            kblib.canonical_yaml(legacy_plan), encoding="utf-8")
        legacy_plan_sha = kblib.sha256_file(plan_path)

        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = self.load(check_queue.PROGRESS_PATH)
        record = progress["standards_adoptions"][-1]
        record["plan_sha256"] = legacy_plan_sha
        record["boundary_gate_reruns"] = legacy_required
        for field in (
                "standards_effective_date_after",
                "standards_state_sha256_before",
                "after_standards_state_sha256"):
            record.pop(field, None)
        progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        legacy_progress_sha = kblib.sha256_file(progress_path)

        receipt_path = self.root / self.RECEIPTS
        receipts = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for receipt in receipts:
            if receipt.get("tool") == adopt_standards.TOOL:
                receipt["tool_version"] = "1.5.0"
                receipt["plan_sha256"] = legacy_plan_sha
                receipt["after_progress_sha256"] = legacy_progress_sha
                receipt["boundary_gate_reruns"] = legacy_required
                for field in (
                        "before_standards_state_sha256",
                        "after_standards_state_sha256",
                        "standards_effective_date_after"):
                    receipt.pop(field, None)
            if receipt.get("receipt_id") in record["immediate_gate_receipts"]:
                receipt["progress_ledger_sha256"] = legacy_progress_sha
        receipt_path.write_text(
            "".join(json.dumps(receipt, separators=(",", ":")) + "\n"
                    for receipt in receipts), encoding="utf-8")

        replay = check_queue.validate_runtime(self.root)
        self.assertEqual([], replay["errors"])
        self.assertEqual([], check_queue.standards_adoption_plan_errors(
            self.root, legacy_plan, catalog=replay["receipt_catalog"],
            queue=replay["queue"], progress=replay["progress"],
            validate_current=False, producer_tool_version="1.5.0"))

        bindings = check_queue.standards_revalidation_requirements(
            self.root, replay["progress"],
            catalog=replay["receipt_catalog"])["B1"]
        self.assertEqual([
            ("frontmatter-vocabulary", "frontmatter-vocabulary",
             "batch-close"),
            ("page-contract", "page-contract", "batch-close"),
            ("required-queue-consistency", "required-queue-consistency",
             "required-queue-consistency"),
        ], sorted((
            row["affected_gate_id"], row["required_gate_id"],
            row["mapped_owner_gate_id"]
        ) for row in bindings))

    def test_1_6_history_keeps_its_recorded_owner_projection(self):
        """A future capability edit cannot reinterpret a sealed 1.6 plan."""
        self.pause()
        plan = self.capability_boundary_plan(
            "audit-fixture-initial-queue", ["frontmatter-vocabulary"],
            ["batch-close"])
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        registry.write_text(
            registry.read_text(encoding="utf-8").replace(
                "| frontmatter-vocabulary | semantic-leaf | batch-close ",
                "| frontmatter-vocabulary | semantic-leaf | batch-review "),
            encoding="utf-8")
        runtime = check_queue.validate_runtime(self.root)

        legacy_plan = self.legacy_plan_shape(plan)
        historical = check_queue.standards_adoption_plan_errors(
            self.root, legacy_plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=False, producer_tool_version="1.6.0")
        self.assertEqual([], historical)

        current = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=True, producer_tool_version="1.6.0")
        self.assertTrue(any(
            "required_gate_ids adds owner Gate(s) not projected" in error and
            "batch-close" in error for error in current), current)
        self.assertTrue(any(
            "boundary_gate_reruns must equal the exact affected-gate union"
            in error and "batch-review" in error for error in current),
            current)

    def test_current_plan_rejects_an_unprojected_extra_owner(self):
        """Current required Gate IDs must equal, not widen, owner closure."""
        self.pause()
        plan = self.capability_boundary_plan(
            "audit-fixture-initial-queue", ["frontmatter-vocabulary"],
            ["batch-close", "batch-review"])
        errors = self.plan_errors(plan)
        self.assertTrue(any(
            "required_gate_ids adds owner Gate(s) not projected" in error and
            "batch-review" in error for error in errors), errors)
        self.assertTrue(any(
            "boundary_gate_reruns must equal the exact affected-gate union"
            in error and "batch-close" in error for error in errors), errors)

    def adoption_consistency_receipt(self):
        """Return the after-image consistency receipt the adoption recorded."""
        records = self.load(check_queue.PROGRESS_PATH)["standards_adoptions"]
        self.assertTrue(records)
        receipt_ids = records[-1]["immediate_gate_receipts"]
        self.assertEqual(1, len(receipt_ids))
        return receipt_ids[0]

    def test_queued_leaf_impacts_project_to_batch_close_without_raw_receipts(
            self):
        """AF-045 shape: two metadata leaves, one native close owner.

        Queue consistency is the only raw receipt the aggregate consumes.
        Both leaves are represented by the native batch-close owner, which is
        deferred to its ordinary transition instead of asking a queued batch
        for an unrelated one-page checker receipt.
        """
        self.pause()
        plan = self.capability_boundary_plan(
            "audit-fixture-initial-queue",
            ["frontmatter-vocabulary", "page-contract",
             "required-queue-consistency"],
            ["batch-close", "required-queue-consistency"])
        self.assertEqual([], self.plan_errors(plan))
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)

        consistency = self.adoption_consistency_receipt()
        emitted = [line.split("=", 1)[1] for line in output.splitlines()
                   if line.startswith("immediate_gate_receipt=")]
        self.assertEqual([consistency], emitted)
        progress = self.load(check_queue.PROGRESS_PATH)
        resumed = self.run_tool(
            "update_task.py", "--transition", "active",
            "--expected-progress-sha256",
            kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at",
            progress["standards_adoptions"][-1]["adopted_at"], "--apply")
        self.assertEqual(0, resumed.returncode, resumed.stdout)
        relative = ".cambium/receipts/capability-revalidation.jsonl"
        completed = self.run_tool(
            "check_queue.py", "--require-revalidation", "B1",
            "--boundary-gate-receipt",
            "required-queue-consistency=%s" % emitted[0],
            "--receipts", relative)
        self.assertEqual(0, completed.returncode, completed.stdout)
        context = json.loads((self.root / relative).read_text(
            encoding="utf-8").splitlines()[-1])
        self.assertEqual(["required-queue-consistency"],
                         context["immediate_gate_ids"])
        self.assertEqual(["batch-close"],
                         context["native_owner_gate_ids"])
        self.assertEqual(["batch-close"],
                         context["deferred_native_owner_gate_ids"])
        self.assertEqual(
            [{"required_gate_id": "required-queue-consistency",
              "receipt_id": consistency}],
            context["boundary_gate_receipts"])
        leaf_projection = {
            (row["affected_gate_id"], row["mapped_owner_gate_id"])
            for row in context["revalidation_bindings"]
            if row.get("affected_gate_id") in (
                "frontmatter-vocabulary", "page-contract")
        }
        self.assertEqual({
            ("frontmatter-vocabulary", "batch-close"),
            ("page-contract", "batch-close"),
        }, leaf_projection)

        admission_path = ".cambium/receipts/capability-admission.jsonl"
        admission_run = self.run_tool(
            "check_queue.py", "--require-ready", "B1",
            "--receipts", admission_path)
        self.assertEqual(0, admission_run.returncode, admission_run.stdout)
        admission = json.loads((self.root / admission_path).read_text(
            encoding="utf-8").splitlines()[-1])
        result = check_queue.validate_runtime(self.root)
        opened = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "open",
            "--gate-receipt", admission["receipt_id"],
            "--standards-revalidation-receipt", context["receipt_id"],
            "--expected-state-revision",
            str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator", "--at",
            self.seconds_after(admission["checked_at"], 1), "--apply")
        self.assertEqual(0, opened.returncode, opened.stdout)
        final = check_queue.validate_runtime(self.root)
        self.assertEqual([], final["errors"])
        self.assertEqual("open", final["items_by_id"]["B1"]["state"])
        self.assertEqual([], check_queue.outstanding_standards_revalidation(
            final, "B1"))

    def test_a_single_page_leaf_receipt_is_extra_not_authorization(self):
        """A leaf receipt cannot bypass its manifest-scoped composite."""
        self.pause()
        plan = self.capability_boundary_plan(
            "audit-fixture-initial-queue",
            ["page-contract", "required-queue-consistency"],
            ["batch-close", "required-queue-consistency"])
        self.assertEqual([], self.plan_errors(plan))
        self.assertEqual(0, self.command(
            apply=True, actor="integrator")[0])
        consistency = self.adoption_consistency_receipt()

        raw = kblib.make_receipt(
            check_page_contract.TOOL, check_page_contract.TOOL_VERSION,
            check_page_contract.GATE_CHECK, "Topics/A.md", "pass",
            "one page only", 1, root=self.root)
        raw["gate_id"] = check_page_contract.GATE_ID
        kblib.write_receipts(
            self.root / ".cambium/receipts/raw-page-contract.jsonl", [raw])
        result = check_queue.validate_runtime(self.root)
        _context, errors = check_queue.standards_revalidation_context(
            result, "B1", {
                "required-queue-consistency": consistency,
                "page-contract": raw["receipt_id"],
            })
        self.assertTrue(any(
            "receipt IDs must be exactly ['required-queue-consistency']"
            in error for error in errors), errors)

    def test_native_admission_is_deferred_while_the_batch_is_queued(self):
        """A native transition owner is never replaced by a raw receipt."""
        self.pause()
        plan = self.capability_boundary_plan(
            "audit-fixture-initial-queue",
            ["required-queue-admission", "required-queue-consistency"],
            ["required-queue-admission", "required-queue-consistency"])
        self.assertEqual([], self.plan_errors(plan))
        self.assertEqual(0, self.command(
            apply=True, actor="integrator")[0])
        consistency = self.adoption_consistency_receipt()
        result = check_queue.validate_runtime(self.root)
        context, errors = check_queue.standards_revalidation_context(
            result, "B1", {"required-queue-consistency": consistency})
        self.assertEqual([], errors)
        self.assertEqual(["required-queue-admission"],
                         context["native_owner_gate_ids"])
        self.assertEqual(["required-queue-admission"],
                         context["deferred_native_owner_gate_ids"])
        self.assertEqual([], context["unrepeatable_passed_gate_ids"])

    def test_current_plan_rejects_mechanism_only_and_unsupported_gates(self):
        """A tool in the registry is not necessarily boundary authority."""
        self.pause()
        for gate_id, role in (
                ("standards-adoption", "mechanism-only"),
                ("standards-revalidation", "mechanism-only"),
                ("runtime-card-synchronization", "unsupported")):
            with self.subTest(gate_id=gate_id):
                plan = self.capability_boundary_plan(
                    "audit-fixture-initial-queue", [gate_id], [gate_id])
                current = self.plan_errors(plan)
                capability_errors = [error for error in current if
                    "cannot be used as an adoption boundary Gate" in error]
                self.assertTrue(any(role in error
                                    for error in capability_errors), current)

                runtime = check_queue.validate_runtime(self.root)
                replay = check_queue.standards_adoption_plan_errors(
                    self.root, plan, catalog=runtime["receipt_catalog"],
                    queue=runtime["queue"], progress=runtime["progress"],
                    validate_current=False)
                self.assertEqual([], [error for error in replay if
                    "cannot be used as an adoption boundary Gate" in error])

    def test_current_merge_ready_native_owner_requires_rollback(self):
        """A plan cannot retroactively claim batch-review after its edge."""
        invalidated = self.open_b1_and_hold_for_revalidation()
        plan = self.capability_boundary_plan(
            invalidated, ["batch-review"], ["batch-review"])
        runtime = check_queue.validate_runtime(self.root)
        queue = copy.deepcopy(runtime["queue"])
        item = next(row for row in queue["required_queue"]
                    if row["id"] == "B1")
        item["state"] = "merge-ready"
        item["hold_state"] = "none"
        current = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=queue, progress=runtime["progress"],
            validate_current=True)
        self.assertTrue(any(
            ("rollback" in error.lower() or "roll it back" in error.lower())
            and "B1" in error for error in current), current)

        replay = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=queue, progress=runtime["progress"],
            validate_current=False)
        self.assertEqual([], [error for error in replay
                              if "rollback" in error.lower()])

    def lifecycle_boundary_plan(self, invalidated_gate):
        """Adopt one immediate owner and one future native owner."""
        self.register_link_gate()
        self.plan(invalidated_receipt=invalidated_gate, overrides={
            "changed_predicates": [{
                "predicate_id": "PRED-LIFECYCLE-001",
                "owner_path": self.GOVERNANCE,
                "change_kind": "modified",
                "affected_gate_ids": list(self.LIFECYCLE_AFFECTED_GATES),
            }],
            "invalidated_evidence": [{
                "receipt_id": invalidated_gate,
                "predicate_ids": ["PRED-LIFECYCLE-001"],
                "dimension_ids": ["coverage_and_integration"],
                "boundary_ids": ["INV-B1-LIFECYCLE"],
                "reason_code": "predicate-changed",
                "revalidation_scope_ids": ["B1"],
            }],
            "invalidation_boundaries": [{
                "boundary_id": "INV-B1-LIFECYCLE",
                "predicate_ids": ["PRED-LIFECYCLE-001"],
                "target_kind": "batch",
                "target_ids": ["B1"],
                "required_gate_ids": list(self.LIFECYCLE_GATES),
            }],
            "boundary_gate_reruns": list(self.LIFECYCLE_GATES),
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)

    def link_gate_receipt(self):
        """Produce the `wiki-link-integrity` receipt the boundary is owed."""
        receipts = self.root / self.LINK_RECEIPTS
        completed = self.run_tool(
            "check_links.py", "--receipts", str(receipts))
        self.assertEqual(0, completed.returncode, completed.stdout)
        return json.loads(receipts.read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]

    def revalidation_aggregate(self, link_receipt):
        """Run the aggregate with the adoption's immediate owner receipt.

        ``link_receipt`` remains an input to the helper so the surrounding
        seal/replay fixtures still prove a raw leaf can coexist in the receipt
        catalog; it is intentionally not offered as boundary authority.
        """
        del link_receipt
        consistency = self.adoption_consistency_receipt()
        relative = ".cambium/receipts/revalidation.jsonl"
        completed = self.run_tool(
            "check_queue.py", "--require-revalidation", "B1",
            "--boundary-gate-receipt",
            "required-queue-consistency=%s" % consistency,
            "--receipts", relative)
        self.assertEqual(0, completed.returncode, completed.stdout)
        return json.loads((self.root / relative).read_text(
            encoding="utf-8").splitlines()[-1])

    @staticmethod
    def seconds_after(stamp, seconds):
        """Return ``stamp`` advanced by ``seconds``, in receipt format.

        Transition timestamps may not move backward, so every step after the
        aggregate is derived from the aggregate's own clock rather than fixed.
        """
        return (datetime.fromisoformat(stamp.replace("Z", "+00:00")) +
                timedelta(seconds=seconds)).astimezone(
                    timezone.utc).isoformat().replace("+00:00", "Z")

    def clear_b1_hold(self, aggregate):
        """Discharge the `revalidation-required` hold with that aggregate."""
        transition_at = self.seconds_after(aggregate["checked_at"], 1)
        result = check_queue.validate_runtime(self.root)
        completed = self.run_tool(
            "update_queue.py", "--id", "B1", "--hold-state", "none",
            "--standards-revalidation-receipt", aggregate["receipt_id"],
            "--expected-state-revision",
            str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator", "--at", transition_at, "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        return transition_at

    def test_neither_unreachable_boundary_gate_has_a_producer_to_run(self):
        """The deadlock's two halves, stated against the tools themselves."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.lifecycle_boundary_plan(invalidated_gate)
        self.assertEqual(
            "open",
            check_queue.validate_runtime(self.root)["items_by_id"]["B1"]
            ["state"])

        admission = self.run_tool("check_queue.py", "--require-ready", "B1")
        self.assertEqual(1, admission.returncode, admission.stdout)
        self.assertIn("B1 is open, not queued", admission.stdout)

        close = self.run_tool(
            "check_batch_close.py", "--batch", "B1",
            "--integrator", "fixture-integrator",
            "--reviewer", "fixture-reviewer",
            "--review-attestation", "audit-absent-attestation")
        self.assertEqual(1, close.returncode, close.stdout)
        self.assertIn("B1 is open, not merge-ready", close.stdout)

    def test_an_open_batch_clears_with_immediate_owner_and_defers_close(self):
        """The hold clears without asking a raw semantic leaf to authorize."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.lifecycle_boundary_plan(invalidated_gate)
        aggregate = self.revalidation_aggregate(self.link_gate_receipt())

        self.assertEqual(self.LIFECYCLE_GATES, aggregate["required_gate_ids"])
        self.assertEqual(["required-queue-consistency"],
                         aggregate["due_gate_ids"])
        self.assertEqual(["batch-close"],
                         aggregate["deferred_to_later_transition_gate_ids"])
        self.assertEqual([], aggregate["unrepeatable_passed_gate_ids"])
        self.assertEqual("open", aggregate["target_batch_state"])
        self.assertEqual(
            [row["required_gate_id"]
             for row in aggregate["boundary_gate_receipts"]],
            ["required-queue-consistency"])

        self.clear_b1_hold(aggregate)
        final = check_queue.validate_runtime(self.root)
        self.assertEqual([], final["errors"])
        self.assertEqual("none", final["items_by_id"]["B1"]["hold_state"])
        self.assertEqual([], check_queue.outstanding_standards_revalidation(
            final, "B1"))

    def append_fixture_receipt(self, receipt_id, **fields):
        """Append one hand-written receipt to the fixture register."""
        receipt = {"receipt_id": receipt_id, "result": "pass",
                   "invalidated_by": None}
        receipt.update(fields)
        kblib.write_receipts(
            self.root / ".cambium/receipts/fixture.jsonl", [receipt])
        return receipt_id

    def merge_and_apply_b1(self, at):
        """Carry the cleared batch to `merge-ready` and apply its Delta."""
        queue = self.load(check_queue.QUEUE_PATH)
        self.append_fixture_receipt(
            "audit-page-1", check="fixture", target="Topics/A.md")
        self.append_fixture_receipt(
            "audit-batch-1", check=check_queue.BATCH_REVIEW_CHECK,
            target="B1", tool=check_queue.MANUAL_ATTESTATION_TOOL,
            tool_version=check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
            gate_id=check_queue.BATCH_REVIEW_GATE_ID,
            task_id=queue["task_id"], batch_id="B1",
            delta_page_receipt_ids=["audit-page-1"])
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(
            "batch: B1\ngenerated_at: %s\n"
            "pages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-page-1\n"
            "open_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n" % at,
            encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        merged = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-1",
            "--expected-state-revision",
            str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator", "--at", at, "--apply")
        self.assertEqual(0, merged.returncode, merged.stdout)
        relative = ".cambium/receipts/delta-B1.jsonl"
        applied = subprocess.run(
            [sys.executable, str(TOOLS / "apply_delta.py"),
             check_queue.COVERAGE_PATH, ".cambium/deltas/B1.yaml",
             "--root", str(self.root),
             "--expected-coverage-sha256",
             kblib.sha256_file(self.root / check_queue.COVERAGE_PATH),
             "--expected-queue-sha256",
             kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
             "--actor-role", "integrator", "--receipts", relative, "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False)
        self.assertEqual(0, applied.returncode, applied.stdout)
        return json.loads((self.root / relative).read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]

    def test_a_deferred_gate_is_still_required_at_the_transition_it_defers_to(
            self):
        """Deferral moves the claim; it does not waive it.

        `batch-close` was recorded as deferred rather than required, so the
        close transition -- which is where that Gate's producer can run --
        must still refuse without it.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.lifecycle_boundary_plan(invalidated_gate)
        aggregate = self.revalidation_aggregate(self.link_gate_receipt())
        self.assertEqual(["batch-close"],
                         aggregate["deferred_to_later_transition_gate_ids"])
        cleared_at = self.clear_b1_hold(aggregate)
        delta_apply_receipt = self.merge_and_apply_b1(
            self.seconds_after(cleared_at, 1))

        consistency = self.run_tool(
            "check_queue.py", "--receipts", ".cambium/receipts/close.jsonl")
        self.assertEqual(0, consistency.returncode, consistency.stdout)
        consistency_receipt = json.loads(
            (self.root / ".cambium/receipts/close.jsonl").read_text(
                encoding="utf-8").splitlines()[-1])["receipt_id"]
        result = check_queue.validate_runtime(self.root)
        self.assertEqual("merge-ready", result["items_by_id"]["B1"]["state"])
        attempted = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency_receipt,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision",
            str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator", "--at",
            self.seconds_after(cleared_at, 2), "--apply")
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("requires --close-gate-receipt", attempted.stdout)
        self.assertEqual(
            "merge-ready",
            self.load(check_queue.QUEUE_PATH)["required_queue"][0]["state"])

    def test_a_queue_exhaustion_gate_is_deferred_not_demanded_now(self):
        """A gate whose position is Queue exhaustion, not a batch state.

        `required-queue-completion` takes no batch, so it is not batch-scoped
        in the narrow sense -- but its producer refuses while any non-terminal
        batch remains, which every live batch is.  Treating it as producible
        now would deadlock the hold exactly as `batch-close` did.
        """
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        text = registry.read_text(encoding="utf-8").replace(
            "\n## Standards Revalidation Capability Registry\n",
            "\n| required-queue-completion | check_queue | %s "
            "| required_queue | require-complete | * | queue-exhausted |\n\n"
            "## Standards Revalidation Capability Registry\n" %
            check_queue.TOOL_VERSION)
        text += (
            "| required-queue-completion | native-owner "
            "| required-queue-completion | native-transition "
            "| native-owner-scope | native-owner-receipt |\n")
        registry.write_text(text, encoding="utf-8")
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        affected = ["required-queue-completion",
                    "required-queue-consistency", "wiki-link-integrity"]
        gates = ["batch-close", "required-queue-completion",
                 "required-queue-consistency"]
        self.register_link_gate()
        self.plan(invalidated_receipt=invalidated_gate, overrides={
            "changed_predicates": [{
                "predicate_id": "PRED-EXHAUSTION-001",
                "owner_path": self.GOVERNANCE,
                "change_kind": "modified",
                "affected_gate_ids": affected,
            }],
            "invalidated_evidence": [{
                "receipt_id": invalidated_gate,
                "predicate_ids": ["PRED-EXHAUSTION-001"],
                "dimension_ids": ["coverage_and_integration"],
                "boundary_ids": ["INV-B1-EXHAUSTION"],
                "reason_code": "predicate-changed",
                "revalidation_scope_ids": ["B1"],
            }],
            "invalidation_boundaries": [{
                "boundary_id": "INV-B1-EXHAUSTION",
                "predicate_ids": ["PRED-EXHAUSTION-001"],
                "target_kind": "batch",
                "target_ids": ["B1"],
                "required_gate_ids": gates,
            }],
            "boundary_gate_reruns": gates,
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)

        # The producer refuses while B1 is non-terminal, so this gate is as
        # unreachable from `open` as `batch-close` is.
        refused = self.run_tool("check_queue.py", "--require-complete")
        self.assertEqual(1, refused.returncode, refused.stdout)
        self.assertIn("remaining_required_work_units=2", refused.stdout)

        aggregate = self.revalidation_aggregate(self.link_gate_receipt())
        self.assertEqual(["required-queue-consistency"],
                         aggregate["due_gate_ids"])
        self.assertEqual(["batch-close", "required-queue-completion"],
                         aggregate["deferred_to_later_transition_gate_ids"])
        self.assertEqual([], aggregate["unrepeatable_passed_gate_ids"])
        self.clear_b1_hold(aggregate)
        final = check_queue.validate_runtime(self.root)
        self.assertEqual([], final["errors"])
        self.assertEqual("none", final["items_by_id"]["B1"]["hold_state"])

    def passed_only_boundary_plan(self, invalidated_gate, target_ids):
        """A boundary naming only a gate its targets have already left."""
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["changed_predicates"][0]["affected_gate_ids"] = [
            "required-queue-admission"]
        plan["invalidation_boundaries"][0].update({
            "required_gate_ids": ["required-queue-admission"],
            "target_ids": list(target_ids),
        })
        plan["boundary_gate_reruns"] = ["required-queue-admission"]
        return plan

    def test_a_boundary_of_only_passed_gates_is_refused_at_admission(self):
        """A current plan cannot retroactively defer an owner edge."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.passed_only_boundary_plan(invalidated_gate, ["B1"])
        dead = [error for error in self.plan_errors(plan)
                if "already passed Standards revalidation owner edge" in error]

        self.assertEqual(1, len(dead), dead)
        self.assertIn("INV-B1-READY", dead[0])
        self.assertIn("required-queue-admission", dead[0])
        self.assertIn("B1 (open", dead[0])
        self.assertIn("roll back", dead[0])

    def test_every_reached_batch_must_still_have_its_owner_edge_ahead(self):
        """One queued target cannot erase another target's passed edge.

        This boundary reaches queued B2 directly and open B1 through the
        invalidated evidence scope.  B2 can still run admission, but B1 cannot;
        owner projection is enforced per reached batch, so the current plan
        must roll B1 back or route its impact to a successor.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.passed_only_boundary_plan(invalidated_gate, ["B2"])
        self.assertEqual(["B1"],
                         plan["invalidated_evidence"][0][
                             "revalidation_scope_ids"])
        items = check_queue.validate_runtime(self.root)["items_by_id"]
        self.assertEqual("queued", items["B2"]["state"])
        self.assertEqual("open", items["B1"]["state"])
        passed = [error for error in self.plan_errors(plan)
                  if "already passed Standards revalidation owner edge" in error]
        self.assertEqual(1, len(passed), passed)
        self.assertIn("B1 (open: required-queue-admission)", passed[0])
        self.assertNotIn("B2 (queued", passed[0])

    def evidence_scoped_boundary_plan(self, invalidated_gate, scope_ids):
        """Reach a batch only through invalidated-evidence scope."""
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["changed_predicates"][0]["affected_gate_ids"] = [
            "required-queue-admission"]
        plan["invalidation_boundaries"][0].update({
            "required_gate_ids": ["required-queue-admission"],
            "target_kind": "terminal-audit",
            "target_ids": ["terminal-audit"],
        })
        plan["invalidated_evidence"][0]["revalidation_scope_ids"] = list(
            scope_ids)
        plan["boundary_gate_reruns"] = ["required-queue-admission"]
        return plan

    def test_a_boundary_reached_only_by_evidence_scope_is_judged_too(self):
        """Enforcement is per boundary, so the refusal must be too.

        A non-`batch` boundary binds a batch through its invalidated
        evidence's revalidation scope exactly as a batch target does, so a
        dead-gate refusal scoped to declared targets alone would miss it.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.evidence_scoped_boundary_plan(invalidated_gate, ["B1"])
        errors = self.plan_errors(plan)
        self.assertEqual([], [error for error in errors
                              if "no gate rerun" in error])
        dead = [error for error in errors
                if "already passed Standards revalidation owner edge" in error]

        self.assertEqual(1, len(dead), errors)
        self.assertIn("INV-B1-READY", dead[0])
        self.assertIn("required-queue-admission", dead[0])
        self.assertIn("B1 (open", dead[0])

    def test_an_evidence_scoped_boundary_a_batch_can_claim_still_stands(self):
        """Same route, live position: nothing is refused."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.evidence_scoped_boundary_plan(invalidated_gate, ["B2"])
        self.assertEqual([], [error for error in self.plan_errors(plan)
                              if "already passed Standards revalidation owner "
                              "edge" in error])

    def test_evidence_scope_cannot_route_a_new_owner_claim_to_closed_batch(self):
        """Terminal protection covers scope-derived as well as direct targets."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.evidence_scoped_boundary_plan(invalidated_gate, ["B1"])
        runtime = check_queue.validate_runtime(self.root)
        queue = copy.deepcopy(runtime["queue"])
        item = next(row for row in queue["required_queue"]
                    if row["id"] == "B1")
        item["state"] = "closed"
        item["hold_state"] = "none"

        current = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"], queue=queue,
            progress=runtime["progress"], validate_current=True)
        terminal = [error for error in current
                    if "post-admission owner claims on terminal batch" in error]
        self.assertEqual(1, len(terminal), current)
        self.assertIn("B1", terminal[0])
        self.assertIn("successor", terminal[0])

        replay = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"], queue=queue,
            progress=runtime["progress"], validate_current=False)
        self.assertEqual([], [error for error in replay
                              if "post-admission owner claims on terminal "
                              "batch" in error])

    def test_a_sealed_plan_of_only_passed_gates_still_replays_clean(self):
        """History is replayed under the rules of its own day.

        A completed adoption's plan bytes are fingerprinted inside append-only
        receipts, so an instance whose earlier boundary named only gates its
        batch has left has no sanctioned way to rewrite them.  Judging that
        plan here would strand it.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.passed_only_boundary_plan(invalidated_gate, ["B1"])
        self.assertEqual(1, len([error for error in self.plan_errors(plan)
                                 if "already passed Standards revalidation "
                                 "owner edge" in error]))
        runtime = check_queue.validate_runtime(self.root)
        replay = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=False)
        self.assertEqual([], [error for error in replay
                              if "already passed Standards revalidation owner "
                              "edge" in error])

    def test_affected_open_and_merge_ready_batches_fail_without_safe_state(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.plan(invalidated_receipt=invalidated_gate)
        runtime = check_queue.validate_runtime(self.root)
        queue = copy.deepcopy(runtime["queue"])
        item = next(row for row in queue["required_queue"]
                    if row["id"] == "B1")
        item["hold_state"] = "none"
        errors = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=queue, progress=runtime["progress"], validate_current=True)
        self.assertTrue(any("must already have hold_state" in error
                            for error in errors), errors)
        item["state"] = "merge-ready"
        errors = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=queue, progress=runtime["progress"], validate_current=True)
        self.assertTrue(any("roll it back" in error for error in errors), errors)

    def plan_errors(self, plan):
        runtime = check_queue.validate_runtime(self.root)
        return check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=True)

    def profile_admission_plan(self, downstream_gate_ids=()):
        """Build the admission-only boundary for a candidate Profile.

        The initial Queue materialization receipt is deliberately used as the
        invalidated evidence: unlike a batch-admission receipt, it has no Queue
        consumer that would independently require a batch revalidation scope.
        This lets the fixture isolate the profile-load boundary itself.
        """
        plan = self.plan(
            invalidated_receipt="audit-fixture-initial-queue")
        runtime_gate_ids = sorted(downstream_gate_ids)
        required_gate_ids = sorted(("profile-load", *runtime_gate_ids))
        plan["changed_predicates"][0]["affected_gate_ids"] = \
            required_gate_ids
        plan["invalidation_boundaries"][0].update({
            "target_kind": "profile-load",
            "target_ids": [plan["selected_profile_manifest_after"]],
            "required_gate_ids": required_gate_ids,
        })
        plan["invalidated_evidence"][0]["revalidation_scope_ids"] = []
        # profile-load ran against the writable after-image above.  Only Gate
        # IDs consumed later in the Queue belong in this runtime rerun union.
        plan["boundary_gate_reruns"] = runtime_gate_ids
        return plan

    def test_profile_load_boundary_targets_exactly_the_after_manifest(self):
        self.pause()
        plan = self.profile_admission_plan()
        plan["invalidation_boundaries"][0]["target_ids"] = [
            "profiles/test-profile/slots.md"]

        errors = self.plan_errors(plan)

        self.assertIn(
            "invalidation_boundaries[0] profile-load target_ids must contain "
            "only selected_profile_manifest_after", errors)

    def test_profile_load_boundary_must_name_its_admission_gate(self):
        self.pause()
        plan = self.profile_admission_plan()
        plan["invalidation_boundaries"][0]["required_gate_ids"] = []

        errors = self.plan_errors(plan)

        self.assertIn(
            "invalidation_boundaries[0] profile-load boundary must require "
            "the profile-load Gate at after-image admission", errors)

    def test_profile_selection_change_cannot_use_noop_adoption_branch(self):
        self.pause()
        install_loadable_profile(self.root, profile_id="next-profile")
        next_manifest = "profiles/next-profile/profile.md"
        governance = self.root / self.GOVERNANCE
        governance.write_text(
            governance.read_text(encoding="utf-8").replace(
                "profiles/test-profile/profile.md", next_manifest),
            encoding="utf-8")
        next_evidence, next_errors = check_queue.profile_load_evidence(
            self.root, next_manifest)
        self.assertEqual([], next_errors)
        plan = self.plan()
        plan.update({
            "contract_version_after": "c2",
            "selected_profile_manifest_after": next_manifest,
            "governance_revision_sha256": kblib.sha256_file(governance),
            "profile_snapshot_sha256_after":
                next_evidence["profile_snapshot_sha256"],
            "profile_contract_fingerprint_after":
                next_evidence["profile_contract_fingerprint"],
        })

        errors = self.plan_errors(plan)

        self.assertIn(
            "selected Profile change must declare a changed predicate whose "
            "affected_gate_ids include profile-load", errors)
        self.assertIn(
            "Profile authority change requires exactly one profile-load "
            "after-image invalidation boundary; found 0", errors)

    def test_profile_load_affected_predicate_requires_after_image_boundary(self):
        self.pause()
        plan = self.plan()
        plan.update({
            "contract_version_after": "c2",
            "changed_predicates": [{
                "predicate_id": "PRED-PROFILE-AUTHORITY",
                "owner_path": self.GOVERNANCE,
                "change_kind": "modified",
                "affected_gate_ids": ["profile-load"],
            }],
        })

        errors = self.plan_errors(plan)

        self.assertIn(
            "Profile authority change requires exactly one profile-load "
            "after-image invalidation boundary; found 0", errors)

    def test_profile_load_boundary_covers_every_affected_predicate(self):
        self.pause()
        plan = self.profile_admission_plan()
        plan["changed_predicates"].insert(0, {
            "predicate_id": "PRED-PROFILE-SECOND",
            "owner_path": self.GOVERNANCE,
            "change_kind": "modified",
            "affected_gate_ids": ["profile-load"],
        })

        errors = self.plan_errors(plan)

        self.assertIn(
            "invalidation_boundaries[0] profile-load boundary must reference "
            "every changed predicate whose affected_gate_ids include "
            "profile-load; omitted: PRED-PROFILE-SECOND", errors)

    def test_admission_only_profile_load_needs_no_batch_reach_or_rerun(self):
        self.pause()
        plan = self.profile_admission_plan()

        self.assertEqual(
            [], plan["invalidated_evidence"][0]["revalidation_scope_ids"])
        self.assertEqual([], plan["boundary_gate_reruns"])
        self.assertEqual([], self.plan_errors(plan))

    def test_profile_load_with_a_downstream_gate_still_needs_batch_reach(self):
        self.pause()
        self.register_link_gate()
        plan = self.profile_admission_plan(("wiki-link-integrity",))

        errors = self.plan_errors(plan)
        reach_errors = [
            error for error in errors
            if "boundary INV-B1-READY has target_kind 'profile-load' and no "
            "invalidated evidence scoping it to a Queue batch" in error
        ]
        self.assertEqual(1, len(reach_errors), errors)
        self.assertEqual(["wiki-link-integrity"],
                         plan["boundary_gate_reruns"])

        plan["invalidated_evidence"][0]["revalidation_scope_ids"] = ["B2"]
        self.assertEqual([], [
            error for error in self.plan_errors(plan)
            if "no gate rerun would ever be required" in error
        ])

    def test_plan_checks_the_after_profile_without_wedging_on_bad_current(self):
        """A bad selected Profile can migrate, but a bad candidate cannot.

        Ordinary validation and writers reject the broken current closure.
        Only the corrective adoption's current/before reads use the explicit
        smaller identity/sentinel escape; its after-image and post-write state
        still run canonical full profile-load.
        """
        self.pause()
        next_profile = install_loadable_profile(
            self.root, profile_id="next-profile")
        next_manifest = "profiles/next-profile/profile.md"
        governance = self.root / self.GOVERNANCE
        governance.write_text(
            governance.read_text(encoding="utf-8").replace(
                "profiles/test-profile/profile.md", next_manifest),
            encoding="utf-8")
        admitted_next_evidence, admitted_next_errors = \
            check_queue.profile_load_evidence(self.root, next_manifest)
        self.assertEqual([], admitted_next_errors)

        next_slots = next_profile / "slots.md"
        next_owned = "profiles/next-profile/slots.md#Synthetic Predicate"
        current_owned = "profiles/test-profile/slots.md#Synthetic Predicate"
        next_slots.write_text(
            next_slots.read_text(encoding="utf-8").replace(
                next_owned, current_owned, 1), encoding="utf-8")

        plan = self.profile_admission_plan()
        plan.update({
            "selected_profile_manifest_after": next_manifest,
            "governance_revision_sha256": kblib.sha256_file(governance),
            "profile_snapshot_sha256_after": kblib.repository_tree_sha256(
                self.root, "profiles/next-profile"),
            "profile_contract_fingerprint_after":
                admitted_next_evidence["profile_contract_fingerprint"],
        })
        plan["invalidation_boundaries"][0]["target_ids"] = [next_manifest]
        candidate_errors = self.plan_errors(plan)
        self.assertTrue(any(
            "selected Profile failed profile-load" in error and
            "predicate-owner-path-outside-profile" in error
            for error in candidate_errors), candidate_errors)

        # Repair the after-image, then make the current selected package carry
        # the same cross-Profile edge.  The live runtime remains operable and
        # the Standards plan is judged against the now-valid after-image.
        next_slots.write_text(
            next_slots.read_text(encoding="utf-8").replace(
                current_owned, next_owned, 1), encoding="utf-8")
        current_slots = self.root / "profiles/test-profile/slots.md"
        current_slots.write_text(
            current_slots.read_text(encoding="utf-8").replace(
                current_owned, next_owned, 1), encoding="utf-8")
        plan["profile_snapshot_sha256_after"] = \
            kblib.repository_tree_sha256(
                self.root, "profiles/next-profile")
        repaired_next_evidence, repaired_next_errors = \
            check_queue.profile_load_evidence(self.root, next_manifest)
        self.assertEqual([], repaired_next_errors)
        plan["profile_contract_fingerprint_after"] = \
            repaired_next_evidence["profile_contract_fingerprint"]

        current_errors = check_queue.profile_load_errors(
            self.root, "profiles/test-profile/profile.md")
        self.assertTrue(any(
            "predicate-owner-path-outside-profile" in error
            for error in current_errors), current_errors)
        ordinary_errors = check_queue.validate_runtime(self.root)["errors"]
        self.assertTrue(any(
            "predicate-owner-path-outside-profile" in error
            for error in ordinary_errors), ordinary_errors)
        corrective_current = check_queue.validate_runtime(
            self.root,
            allow_invalid_current_profile_for_corrective_adoption=True,
            allow_active_standards_mismatch_for_adoption=True)
        self.assertEqual([], corrective_current["errors"])
        with self.assertRaisesRegex(
                ValueError, "only to persisted current state"):
            check_queue.validate_runtime(
                self.root, state_overrides={},
                allow_invalid_current_profile_for_corrective_adoption=True)

        ordinary_writer = self.run_tool(
            "update_task.py", "--transition", "active",
            "--at", "2026-08-05T00:04:00Z")
        self.assertEqual(1, ordinary_writer.returncode, ordinary_writer.stdout)
        self.assertIn(
            "predicate-owner-path-outside-profile", ordinary_writer.stdout)
        self.assertEqual([], self.plan_errors(plan))

        (self.root / self.PLAN).write_text(
            kblib.canonical_yaml(plan), encoding="utf-8")
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        repaired = check_queue.validate_runtime(self.root)
        self.assertEqual([], repaired["errors"])
        self.assertEqual(next_manifest,
                         repaired["queue"]["selected_profile_manifest"])

    def test_boundary_without_any_enforcement_path_is_refused(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        for kind, targets in (
                ("terminal-audit", ["terminal-audit"]),
                ("maintenance-completion", ["maintenance-completion"]),
                ("profile-load", ["profiles/test-profile/profile.md"]),
                ("task", ["fixture-task"]),
                ("receipt", [invalidated_gate])):
            with self.subTest(target_kind=kind):
                plan = self.plan(invalidated_receipt=invalidated_gate)
                plan["invalidation_boundaries"][0].update({
                    "target_kind": kind, "target_ids": targets,
                })
                plan["invalidated_evidence"][0]["revalidation_scope_ids"] = []
                self.assertTrue(any(
                    "boundary INV-B1-READY has target_kind %r and no "
                    "invalidated evidence scoping it to a Queue batch" % kind
                    in error for error in self.plan_errors(plan)),
                    self.plan_errors(plan))

    def test_non_batch_boundary_stays_valid_when_evidence_scopes_a_batch(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["invalidation_boundaries"][0].update({
            "target_kind": "terminal-audit",
            "target_ids": ["terminal-audit"],
        })
        self.assertEqual(["B1"],
                         plan["invalidated_evidence"][0]["revalidation_scope_ids"])
        self.assertEqual([], [error for error in self.plan_errors(plan)
                              if "no gate rerun" in error])
        # Enforcement is per boundary, not per target_kind: this
        # `terminal-audit` boundary binds B1 exactly as a batch boundary would.
        requirements = check_queue.standards_revalidation_requirements(
            self.root, {"standards_adoptions": [{
                "plan_path": self.PLAN,
                "plan_sha256": kblib.sha256_file(self.root / self.PLAN),
                "adopted_at": "2026-08-04T00:05:00Z",
            }]})
        self.assertEqual(["INV-B1-READY"],
                         [row["boundary_id"] for row in requirements["B1"]])

    def test_a_historical_plan_is_not_refused_by_this_admission_rule(self):
        """A sealed adoption cannot be repaired, so it is not re-judged.

        The plan bytes of a completed adoption are fingerprinted inside
        append-only receipts (K13/15: the writer never edits historical
        receipt bytes), so an instance whose earlier plan carries an
        unreachable boundary has no sanctioned way to rewrite it.  Applying
        the admission rule to history would strand that instance
        permanently.  A live instance hit exactly this during an upgrade.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["invalidation_boundaries"][0].update({
            "target_kind": "profile-load",
            "target_ids": ["profiles/example/profile.md"],
        })
        plan["invalidated_evidence"][0]["revalidation_scope_ids"] = []

        admission = [error for error in self.plan_errors(plan)
                     if "no gate rerun" in error]
        self.assertEqual(1, len(admission), admission)

        runtime = check_queue.validate_runtime(self.root)
        replay = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=False)
        self.assertEqual([], [error for error in replay
                              if "no gate rerun" in error])

    READ_SET = "kernel/Read Sets/R99 Fixture Read Set.md"
    CROSS_READ_SET = "kernel/Read Sets/R98 Cross Referenced Read Set.md"
    PROFILE_READ_SET = "profiles/test-profile/P Supplemental Read Set.md"
    READ_SET_INDEX = "kernel/Read Sets/Fixture Route Index.md"
    LEAF_DIRECT = "kernel/K99 Fixture Family/01 Direct Leaf.md"
    LEAF_NESTED = "kernel/K99 Fixture Family/02 Nested Leaf.md"
    LEAF_PROFILE = "kernel/K99 Fixture Family/03 Profile Leaf.md"
    LEAF_RELATED = "kernel/K99 Fixture Family/04 Related Only Leaf.md"
    ORDINARY_SELECTED = "profiles/test-profile/ordinary.md"
    BOUND_PROFILE_FILE = "profiles/test-profile/profile.md"
    BOUND_TOOL_FILE = "Tools/fixture_tool.py"
    MODULE_OMISSION = "loaded_module_paths_after omits"
    READ_SET_OMISSION = "selected_read_sets_after omits"

    def load_set_baseline_errors(self):
        """Errors a plan of this fixture carries before any load set is set.

        The fixture task is `planned`, so `plan_errors` always reports that;
        comparing against this baseline states exactly what declaring a load
        set adds and nothing else.
        """
        return set(self.plan_errors(
            self.plan(overrides={"contract_version_after": "c2"})))

    def write_boundary_fixture(self):
        """Lay down a cycle-safe kernel/profile Read Set closure."""
        for relative in (self.LEAF_DIRECT, self.LEAF_NESTED,
                         self.LEAF_PROFILE, self.LEAF_RELATED):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("## Purpose\n\nFixture leaf.\n", encoding="utf-8")
        index = self.root / self.READ_SET_INDEX
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(
            "---\ntype: route-index\n---\n\n## Purpose\n\nNot a Read Set.\n",
            encoding="utf-8")
        tool = self.root / self.BOUND_TOOL_FILE
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text("# Extra bound tool.\n", encoding="utf-8")

        read_set = self.root / self.READ_SET
        read_set.parent.mkdir(parents=True, exist_ok=True)
        read_set.write_text(
            "---\ntype: read-set\nroute_id: R99\n---\n\n"
            "## Purpose\n\n"
            "Applicability only, so [[%s|Related Only Leaf]] here is not a\n"
            "loading boundary target.\n\n"
            "## Start\n\n"
            "- [[%s|Direct Leaf]]\n"
            "- First read [[%s|Cross Referenced]].\n"
            "- Consult [[%s|Route Index]].\n"
            "- Run `python3 Tools/check_queue.py .` before closing.\n\n"
            "## Related\n\n"
            "- [[%s|Related Only Leaf]]\n"
            % (self.LEAF_RELATED[:-3], self.LEAF_DIRECT[:-3],
               self.CROSS_READ_SET[:-3], self.READ_SET_INDEX[:-3],
               self.LEAF_RELATED[:-3]),
            encoding="utf-8")

        cross = self.root / self.CROSS_READ_SET
        cross.write_text(
            "---\ntype: read-set\nroute_id: R98\n---\n\n"
            "## Purpose\n\nKernel supplemental fixture.\n\n"
            "## Start\n\n"
            "- [[%s|Nested Leaf]]\n"
            "- [[%s|Profile Supplemental Read Set]]\n"
            % (self.LEAF_NESTED[:-3], self.PROFILE_READ_SET[:-3]),
            encoding="utf-8")

        profile = self.root / self.PROFILE_READ_SET
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(
            "---\ntype: profile-read-set\n"
            "route_id: P:test-profile:supplemental\nsupplements: R98\n---\n\n"
            "## Purpose\n\nProfile supplemental fixture.\n\n"
            "## Start\n\n"
            "- [[%s|Profile Leaf]]\n"
            "- [[%s|Cycle Back To Root]]\n"
            % (self.LEAF_PROFILE[:-3], self.READ_SET[:-3]),
            encoding="utf-8")

    def test_boundary_read_sets_form_a_transitive_cycle_safe_closure(self):
        """Referenced kernel and profile Read Sets must also be declared."""
        self.write_boundary_fixture()
        baseline = self.load_set_baseline_errors()
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_profile_route_ids_after": [
                "P:test-profile:supplemental"],
            "selected_read_sets_after": [self.READ_SET],
            "loaded_module_paths_after": sorted(
                (self.LEAF_DIRECT, self.LEAF_NESTED, self.LEAF_PROFILE,
                 self.READ_SET_INDEX)),
        })
        errors = self.plan_errors(plan)
        omissions = [error for error in errors
                     if self.READ_SET_OMISSION in error]

        self.assertEqual(2, len(omissions), errors)
        self.assertTrue(any(self.CROSS_READ_SET in error
                            for error in omissions), omissions)
        self.assertTrue(any(self.PROFILE_READ_SET in error
                            for error in omissions), omissions)
        self.assertEqual([], [error for error in errors
                              if self.MODULE_OMISSION in error])
        self.assertEqual(baseline | set(omissions), set(errors))

    def test_every_non_read_set_target_in_the_closure_must_be_loaded(self):
        """Nested leaves and a non-Read-Set index cannot disappear."""
        self.write_boundary_fixture()
        baseline = self.load_set_baseline_errors()
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_profile_route_ids_after": [
                "P:test-profile:supplemental"],
            "selected_read_sets_after": sorted(
                (self.READ_SET, self.CROSS_READ_SET, self.PROFILE_READ_SET)),
            "loaded_module_paths_after": sorted(
                (self.LEAF_DIRECT, self.BOUND_PROFILE_FILE,
                 self.BOUND_TOOL_FILE)),
        })
        errors = self.plan_errors(plan)
        omissions = [error for error in errors
                     if self.MODULE_OMISSION in error]

        self.assertEqual(3, len(omissions), errors)
        for target in (self.LEAF_NESTED, self.LEAF_PROFILE,
                       self.READ_SET_INDEX):
            self.assertTrue(any(target in error for error in omissions),
                            omissions)
        self.assertFalse(any(self.LEAF_RELATED in error for error in errors),
                         errors)
        self.assertEqual(baseline | set(omissions), set(errors))

        runtime = check_queue.validate_runtime(self.root)
        replay = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=False)
        self.assertEqual([], [error for error in replay if "_after omits" in error])

    def test_a_complete_closure_allows_additional_tool_and_profile_paths(self):
        """Containment allows route-bound files that no boundary names."""
        self.write_boundary_fixture()
        baseline = self.load_set_baseline_errors()
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_profile_route_ids_after": [
                "P:test-profile:supplemental"],
            "selected_read_sets_after": sorted(
                (self.READ_SET, self.CROSS_READ_SET, self.PROFILE_READ_SET)),
            "loaded_module_paths_after": sorted(
                (self.BOUND_PROFILE_FILE, self.BOUND_TOOL_FILE,
                 self.LEAF_DIRECT, self.LEAF_NESTED, self.LEAF_PROFILE,
                 self.READ_SET_INDEX)),
        })
        self.assertEqual(baseline, set(self.plan_errors(plan)))

    def test_a_selected_read_set_must_prove_its_document_type(self):
        """Ordinary Markdown is refused and its links are not traversed."""
        self.write_boundary_fixture()
        ordinary = self.root / self.ORDINARY_SELECTED
        ordinary.write_text(
            "## Start\n\n- [[%s|Not A Read Set Boundary]]\n" %
            self.LEAF_DIRECT[:-3], encoding="utf-8")
        baseline = self.load_set_baseline_errors()
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": [self.ORDINARY_SELECTED],
            "loaded_module_paths_after": [],
        })
        errors = self.plan_errors(plan)
        type_errors = [error for error in errors
                       if "does not prove frontmatter type" in error]

        self.assertEqual(1, len(type_errors), errors)
        self.assertIn(self.ORDINARY_SELECTED, type_errors[0])
        self.assertEqual([], [error for error in errors
                              if self.MODULE_OMISSION in error])
        self.assertEqual(baseline | set(type_errors), set(errors))

    def test_an_unreadable_read_set_is_reported_once_not_per_module(self):
        """A Read Set path that does not resolve is already reported."""
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": ["kernel/Read Sets/R99 Absent.md"],
            "loaded_module_paths_after": [],
        })
        errors = self.plan_errors(plan)
        self.assertEqual(1, len([error for error in errors
                                 if "selected_read_sets_after path" in error]),
                         errors)
        self.assertEqual([], [error for error in errors
                              if "_after omits" in error])

    def test_invalid_utf8_read_set_fails_closed(self):
        """A present but undecodable Read Set cannot shrink the closure."""
        relative = "kernel/Read Sets/R99 Invalid UTF8.md"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"---\ntype: read-set\n---\n\xff")
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": [relative],
            "loaded_module_paths_after": [],
        })
        errors = self.plan_errors(plan)
        self.assertTrue(any(
            relative in error and "unreadable UTF-8" in error
            for error in errors), errors)

    def test_invalid_utf8_boundary_target_fails_closed(self):
        read_set = self.root / self.READ_SET
        read_set.parent.mkdir(parents=True, exist_ok=True)
        target = "kernel/K99 Fixture Family/Invalid UTF8.md"
        read_set.write_text(
            "---\ntype: read-set\nroute_id: R99\n---\n\n"
            "## Start\n\n- [[%s|Broken Target]]\n" % target[:-3],
            encoding="utf-8")
        target_path = self.root / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"\xff")
        errors = self.plan_errors(self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": [self.READ_SET],
            "loaded_module_paths_after": [],
        }))
        self.assertTrue(any(
            target in error and "unreadable UTF-8" in error
            for error in errors), errors)

    def test_read_set_type_must_be_a_scalar_string(self):
        """Malformed YAML types are rejected without raising TypeError."""
        text = "---\ntype: [read-set]\n---\n\n## Start\n"
        self.assertIsNone(kblib.read_set_document_type(text))

    def test_malformed_load_lists_fail_without_validator_traceback(self):
        """Shape errors remain evidence even when elements are unhashable."""
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": [{"path": self.READ_SET}],
            "loaded_module_paths_after": [{"path": self.LEAF_DIRECT}],
        })
        errors = self.plan_errors(plan)
        self.assertTrue(any(
            "selected_read_sets_after must contain only non-empty strings"
            in error for error in errors), errors)
        self.assertTrue(any(
            "loaded_module_paths_after must contain only non-empty strings"
            in error for error in errors), errors)

    def test_profile_read_set_cannot_cross_the_selected_profile(self):
        """A supplemental route belongs only to its selected profile."""
        relative = "profiles/other-profile/P Other Read Set.md"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntype: profile-read-set\n"
            "route_id: P:test-profile:supplemental\n---\n\n"
            "## Start\n\n- [[%s|Leaf]]\n" % self.LEAF_DIRECT[:-3],
            encoding="utf-8")
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_profile_route_ids_after": [
                "P:test-profile:supplemental"],
            "selected_read_sets_after": [relative],
            "loaded_module_paths_after": [],
        })
        errors = self.plan_errors(plan)
        self.assertTrue(any(
            relative in error and "outside the selected profile directory"
            in error for error in errors), errors)

    def test_profile_read_set_route_must_be_selected(self):
        self.write_boundary_fixture()
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_profile_route_ids_after": [],
            "selected_read_sets_after": [self.PROFILE_READ_SET],
            "loaded_module_paths_after": [],
        })
        errors = self.plan_errors(plan)
        self.assertTrue(any(
            self.PROFILE_READ_SET in error and
            "not present in selected_profile_route_ids" in error
            for error in errors), errors)

    def test_boundary_parser_ignores_fences_and_accepts_indented_h2(self):
        text = (
            "## Purpose\n\n[[Ignored/Purpose]]\n\n"
            "  ## Start\n\n[[Included/Leaf]]\n\n"
            "[[Included/WithSuffix.md|Explicit suffix]]\n\n"
            "| Target |\n|---|\n| [[Included/Table\\|Alias]] |\n\n"
            "```markdown\n## Triggered\n[[Ignored/Fenced]]\n```\n\n"
            "   ## Gate\n\n[[Included/Gate]]\n\n"
            "## Related\n\n[[Ignored/Related]]\n")
        self.assertEqual(
            ["Included/Gate.md", "Included/Leaf.md", "Included/Table.md",
             "Included/WithSuffix.md"],
            kblib.read_set_boundary_targets(text))

    def test_batch_boundary_needs_no_invalidated_evidence_scope(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["invalidated_evidence"][0]["revalidation_scope_ids"] = []
        self.assertEqual([], [error for error in self.plan_errors(plan)
                              if "no gate rerun" in error])

    def test_invalidated_consumer_must_be_bound_by_its_own_scope(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["invalidation_boundaries"][0].update({
            "target_kind": "receipt",
            "target_ids": [invalidated_gate],
        })
        plan["invalidated_evidence"][0]["revalidation_scope_ids"] = []
        runtime = check_queue.validate_runtime(self.root)
        errors = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=True)
        self.assertTrue(any(
            "omitted from its own boundaries/revalidation scope: B1" in error
            for error in errors), errors)

    def test_current_catalog_and_gate_identity_never_fall_back(self):
        historical = {
            "OLD": (".cambium/receipts/old.jsonl", {
                "receipt_id": "OLD", "tool": check_queue.TOOL,
            })
        }
        self.assertEqual({}, check_queue.current_receipt_catalog({
            "receipt_catalog": historical,
        }))
        registry = {
            "required-queue-consistency": {
                "tool": check_queue.TOOL,
                "tool_version": check_queue.TOOL_VERSION,
                "check": "required_queue",
                "mode": "consistency",
            },
        }
        receipt = {
            "tool": check_queue.TOOL,
            "tool_version": check_queue.TOOL_VERSION,
            "check": "required_queue",
            "queue_check_mode": "consistency",
        }
        self.assertFalse(check_queue.receipt_matches_gate_id(
            receipt, "required-queue-consistency", registry))
        receipt["gate_id"] = "required-queue-consistency"
        self.assertTrue(check_queue.receipt_matches_gate_id(
            receipt, "required-queue-consistency", registry))

    def test_paused_task_must_resume_before_state_bound_revalidation(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.pause()
        self.plan(invalidated_receipt=invalidated_gate)
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual("resume-paused-task",
                         check_queue.resume_next_action(runtime, []))
        attempted = self.run_tool(
            "check_queue.py", "--require-revalidation", "B1")
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("requires task_state=active", attempted.stdout)

    UNDER_DECLARING_READ_SET = "kernel/Read Sets/R97 Live Contract Fixture.md"
    UNDER_DECLARED_LEAF = "kernel/K97 Fixture Family/01 Boundary Leaf.md"

    def under_declare_live_contract(self):
        """Leave the live contract declaring a Read Set but not its leaf.

        This reproduces the state a past adoption can seal in: the contract's
        five load fields are written only by this tool, so an instance whose
        earlier adoption wrote an incomplete declaration cannot repair it
        anywhere else.
        """
        read_set = self.root / self.UNDER_DECLARING_READ_SET
        read_set.parent.mkdir(parents=True, exist_ok=True)
        read_set.write_text(
            "---\ntype: read-set\nroute_id: R97\n---\n\n"
            "## Start\n\n- [[%s|Boundary Leaf]]\n" %
            self.UNDER_DECLARED_LEAF[:-3], encoding="utf-8")
        leaf = self.root / self.UNDER_DECLARED_LEAF
        leaf.parent.mkdir(parents=True, exist_ok=True)
        leaf.write_text("## Purpose\n\nFixture leaf.\n", encoding="utf-8")
        progress = self.load(check_queue.PROGRESS_PATH)
        progress["contract"]["selected_read_sets"] = [
            self.UNDER_DECLARING_READ_SET]
        progress["contract"]["loaded_module_paths"] = []
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress_path.write_text(kblib.canonical_yaml(progress),
                                 encoding="utf-8")
        receipt_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        rows = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            if row.get("receipt_id") == "audit-fixture-initial-queue":
                row["contract_sha256"] = kblib.sha256_bytes(
                    kblib.canonical_yaml(progress["contract"]))
                row["after_progress_sha256"] = kblib.sha256_file(progress_path)
        receipt_path.write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n"
                    for row in rows), encoding="utf-8")

    def test_an_under_declared_live_contract_does_not_block_the_sole_writer(
            self):
        """The writer that alone can re-declare the load set may still run.

        `_prepare_result` refuses to start while `validate_runtime` reports an
        error, so making the live contract's closure gap an error would leave
        the instance with an under-declaration it has no legal way to repair.
        The gap is reported instead, and the adoption that repairs it applies.
        """
        self.under_declare_live_contract()
        self.pause()
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        self.assertTrue(any(
            self.UNDER_DECLARED_LEAF in gap for gap in
            runtime["task_runtime"]["contract_load_set_gaps"]),
            runtime["task_runtime"]["contract_load_set_gaps"])

        # Admission still judges the declaration the plan writes: the plan
        # that omits the leaf is refused at plan validation, not at the
        # runtime precheck.
        self.plan(overrides={
            "selected_read_sets_after": [self.UNDER_DECLARING_READ_SET],
            "loaded_module_paths_after": [],
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(1, code, output)
        self.assertNotIn("current runtime is inconsistent", output)
        self.assertIn("invalid Standards adoption plan", output)
        self.assertIn("loaded_module_paths_after omits %s" %
                      self.UNDER_DECLARED_LEAF, output)

        # And the complete declaration applies, so the sole writer really is
        # the repair path for the field only it can write.
        self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": [self.UNDER_DECLARING_READ_SET],
            "loaded_module_paths_after": [self.UNDER_DECLARED_LEAF],
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        repaired = check_queue.validate_runtime(self.root)
        self.assertEqual([], repaired["errors"])
        self.assertEqual(
            [], repaired["task_runtime"]["contract_load_set_gaps"])
        self.assertEqual(
            [self.UNDER_DECLARED_LEAF],
            repaired["progress"]["contract"]["loaded_module_paths"])

    def rewrite_adoption_receipts(self, **field_overrides):
        """Restamp the persisted adoption receipts and return the errors.

        Receipts are append-only evidence, so an instance cannot rewrite them
        to satisfy a constant that moved after they were written; the fixture
        edits them only to stand in for bytes a past producer left behind.
        """
        rewritten_adopt_version = field_overrides.get(
            "tool_version", {}).get(adopt_standards.TOOL)
        legacy_plan_sha = None
        legacy_progress_sha = None
        immediate_receipts = set()
        if (isinstance(rewritten_adopt_version, str) and
                tuple(int(part) for part in
                      rewritten_adopt_version.split(".")) < (1, 7, 0)):
            plan_path = self.root / self.PLAN
            legacy_plan = self.legacy_plan_shape(self.load(self.PLAN))
            plan_path.write_text(
                kblib.canonical_yaml(legacy_plan), encoding="utf-8")
            legacy_plan_sha = kblib.sha256_file(plan_path)
            progress_path = self.root / check_queue.PROGRESS_PATH
            progress = self.load(check_queue.PROGRESS_PATH)
            record = progress["standards_adoptions"][-1]
            record["plan_sha256"] = legacy_plan_sha
            immediate_receipts.update(record["immediate_gate_receipts"])
            progress_path.write_text(
                kblib.canonical_yaml(progress), encoding="utf-8")
            legacy_progress_sha = kblib.sha256_file(progress_path)

        receipt_path = self.root / self.RECEIPTS
        rows = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            for field, by_tool in field_overrides.items():
                if row.get("tool") in by_tool:
                    row[field] = by_tool[row["tool"]]
            if (legacy_plan_sha is not None and
                    row.get("tool") == adopt_standards.TOOL):
                row["plan_sha256"] = legacy_plan_sha
                row["after_progress_sha256"] = legacy_progress_sha
            if row.get("receipt_id") in immediate_receipts:
                row["progress_ledger_sha256"] = legacy_progress_sha
        receipt_path.write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n"
                    for row in rows), encoding="utf-8")
        return check_queue.validate_runtime(self.root)["errors"]

    def commit_one_adoption(self):
        self.pause()
        self.plan()
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def test_superseded_producer_versions_do_not_invalidate_adoption_history(
            self):
        """A producer version bump cannot void the transactions it recorded.

        K00/03 requires a producer's `Tool version` cell to move in the
        revision that changes its accept or reject set, so every past receipt
        was stamped with a constant that revision retires.  The commit receipt
        and the immediate Queue gate it consumed are sealed history, and this
        instance passed through the era they claim.
        """
        self.commit_one_adoption()
        errors = self.rewrite_adoption_receipts(tool_version={
            adopt_standards.TOOL: "1.1.0",
            check_queue.TOOL: "1.5.0",
        })
        self.assertEqual([], errors)

    def test_pre_1_3_profile_change_replays_without_new_profile_bindings(self):
        """A sealed 1.2 transaction keeps the contract its producer promised.

        Version 1.2 neither persisted the typed Profile fingerprint nor
        required a Profile selection change to carry the 1.3 after-image
        profile-load boundary.  The fixture first uses the current writer to
        produce a structurally complete transition, then rewrites only the
        sealed artifacts to the exact older producer shape.  Runtime replay
        must accept it without loading old plan semantics through today's
        boundary contract; the same bytes remain invalid for new admission.
        """
        self.pause()
        install_loadable_profile(self.root, profile_id="next-profile")
        next_manifest = "profiles/next-profile/profile.md"
        governance = self.root / self.GOVERNANCE
        governance.write_text(
            governance.read_text(encoding="utf-8").replace(
                "profiles/test-profile/profile.md", next_manifest),
            encoding="utf-8")
        next_evidence, next_errors = check_queue.profile_load_evidence(
            self.root, next_manifest)
        self.assertEqual([], next_errors)

        plan = self.profile_admission_plan()
        plan.update({
            "selected_profile_manifest_after": next_manifest,
            "governance_revision_sha256": kblib.sha256_file(governance),
            "profile_snapshot_sha256_after":
                next_evidence["profile_snapshot_sha256"],
            "profile_contract_fingerprint_after":
                next_evidence["profile_contract_fingerprint"],
        })
        plan["invalidation_boundaries"][0]["target_ids"] = [next_manifest]
        (self.root / self.PLAN).write_text(
            kblib.canonical_yaml(plan), encoding="utf-8")
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)

        # Project the sealed plan/record/receipts back to the 1.2 producer
        # contract.  The state transition and selected after Profile stay the
        # same; only fields and boundary declarations 1.2 never promised are
        # absent.
        legacy_plan = self.legacy_plan_shape(self.load(self.PLAN))
        legacy_plan.pop("profile_contract_fingerprint_after")
        legacy_plan.pop("profile_load_inputs_sha256_after")
        legacy_plan["changed_predicates"] = []
        legacy_plan["invalidated_evidence"] = []
        legacy_plan["invalidation_boundaries"] = []
        legacy_plan["boundary_gate_reruns"] = []
        (self.root / self.PLAN).write_text(
            kblib.canonical_yaml(legacy_plan), encoding="utf-8")
        legacy_plan_sha = kblib.sha256_file(self.root / self.PLAN)

        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = self.load(check_queue.PROGRESS_PATH)
        record = progress["standards_adoptions"][0]
        record.pop("profile_contract_fingerprint_after")
        record.pop("profile_load_inputs_sha256_after")
        record["plan_sha256"] = legacy_plan_sha
        record["changed_predicate_ids"] = []
        record["invalidated_evidence_receipt_ids"] = []
        record["invalidation_boundary_ids"] = []
        record["boundary_gate_reruns"] = []
        progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        legacy_progress_sha = kblib.sha256_file(progress_path)

        receipt_path = self.root / self.RECEIPTS
        receipts = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for receipt in receipts:
            if receipt.get("tool") == adopt_standards.TOOL:
                receipt["tool_version"] = "1.2.0"
                receipt["plan_sha256"] = legacy_plan_sha
                receipt["after_progress_sha256"] = legacy_progress_sha
                receipt["changed_predicate_ids"] = []
                receipt["invalidated_evidence_receipt_ids"] = []
                receipt["invalidation_boundary_ids"] = []
                receipt["boundary_gate_reruns"] = []
                receipt.pop("profile_contract_fingerprint_after")
                receipt.pop("profile_load_inputs_sha256_after")
            if receipt.get("receipt_id") in record["immediate_gate_receipts"]:
                receipt["progress_ledger_sha256"] = legacy_progress_sha
        receipt_path.write_text(
            "".join(json.dumps(receipt, separators=(",", ":")) + "\n"
                    for receipt in receipts), encoding="utf-8")

        replay = check_queue.validate_runtime(self.root)
        self.assertEqual([], replay["errors"])
        self.assertNotIn(
            "profile_contract_fingerprint_after",
            replay["progress"]["standards_adoptions"][0])
        self.assertNotIn(
            "profile_load_inputs_sha256_after",
            replay["progress"]["standards_adoptions"][0])

        current_errors = check_queue.standards_adoption_plan_errors(
            self.root, legacy_plan, catalog=replay["receipt_catalog"],
            queue=replay["queue"], progress=replay["progress"],
            validate_current=True, producer_tool_version="1.2.0")
        self.assertTrue(any(
            "misses explicit field(s): profile_contract_fingerprint_after" in
            error for error in current_errors), current_errors)
        self.assertTrue(any(
            "Profile authority change requires exactly one profile-load" in
            error for error in current_errors), current_errors)

    def test_pre_1_4_history_replays_without_profile_load_input_binding(self):
        """A sealed 1.3 adoption retains its two-Profile-digest contract."""
        self.commit_one_adoption()

        plan_path = self.root / self.PLAN
        legacy_plan = self.legacy_plan_shape(self.load(self.PLAN))
        legacy_plan.pop("profile_load_inputs_sha256_after")
        plan_path.write_text(
            kblib.canonical_yaml(legacy_plan), encoding="utf-8")
        legacy_plan_sha = kblib.sha256_file(plan_path)

        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = self.load(check_queue.PROGRESS_PATH)
        record = progress["standards_adoptions"][0]
        record.pop("profile_load_inputs_sha256_after")
        record["plan_sha256"] = legacy_plan_sha
        progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        legacy_progress_sha = kblib.sha256_file(progress_path)

        receipt_path = self.root / self.RECEIPTS
        receipts = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for receipt in receipts:
            if receipt.get("tool") == adopt_standards.TOOL:
                receipt["tool_version"] = "1.3.0"
                receipt["plan_sha256"] = legacy_plan_sha
                receipt["after_progress_sha256"] = legacy_progress_sha
                receipt.pop("profile_load_inputs_sha256_after")
            if receipt.get("receipt_id") in record["immediate_gate_receipts"]:
                receipt["progress_ledger_sha256"] = legacy_progress_sha
        receipt_path.write_text(
            "".join(json.dumps(receipt, separators=(",", ":")) + "\n"
                    for receipt in receipts), encoding="utf-8")

        replay = check_queue.validate_runtime(self.root)
        self.assertEqual([], replay["errors"])
        sealed = replay["progress"]["standards_adoptions"][0]
        self.assertNotIn("profile_load_inputs_sha256_after", sealed)
        self.assertRegex(
            sealed["profile_contract_fingerprint_after"],
            r"^sha256:[0-9a-f]{64}$")

        current_errors = check_queue.standards_adoption_plan_errors(
            self.root, legacy_plan, catalog=replay["receipt_catalog"],
            queue=replay["queue"], progress=replay["progress"],
            validate_current=True, producer_tool_version="1.3.0")
        self.assertTrue(any(
            "misses explicit field(s): profile_load_inputs_sha256_after" in
            error for error in current_errors), current_errors)

    def test_historical_fingerprint_replay_is_sealed_not_reinterpreted(self):
        self.commit_one_adoption()
        runtime = check_queue.validate_runtime(self.root)
        recorded = runtime["progress"]["standards_adoptions"][0]
        self.assertRegex(
            recorded["profile_contract_fingerprint_after"],
            r"^sha256:[0-9a-f]{64}$")

        self.poison_selected_profile_closure()
        self.assertTrue(any(
            "predicate-owner-path-outside-profile" in error for error in
            check_queue.validate_runtime(self.root)["errors"]))
        self.assertEqual(
            [], check_queue.standards_adoption_errors(
                self.root, runtime["progress"],
                runtime["receipt_catalog"], runtime["queue"]))

    def test_legacy_present_fingerprint_must_still_be_canonical(self):
        self.pause()
        plan = self.plan()
        plan["profile_contract_fingerprint_after"] = "SHA256:NOT-CANONICAL"
        errors = check_queue.standards_adoption_plan_errors(
            self.root, plan, validate_current=False,
            producer_tool_version="1.2.0")
        self.assertIn(
            "Standards adoption plan profile_contract_fingerprint_after is "
            "not a SHA-256", errors)

    def test_legacy_present_fingerprint_stays_sealed_across_the_chain(self):
        self.commit_one_adoption()
        runtime = check_queue.validate_runtime(self.root)
        progress = copy.deepcopy(runtime["progress"])
        catalog = copy.deepcopy(runtime["receipt_catalog"])
        record = progress["standards_adoptions"][0]
        receipt_id = record["verification_receipt"]
        catalog[receipt_id][1]["tool_version"] = "1.2.0"
        record["profile_contract_fingerprint_after"] = \
            "sha256:" + "0" * 64

        errors = check_queue.standards_adoption_errors(
            self.root, progress, catalog, runtime["queue"])

        self.assertTrue(any(
            "profile_contract_fingerprint_after does not match its plan" in
            error for error in errors), errors)
        self.assertTrue(any(
            "receipt profile_contract_fingerprint_after does not match record" in
            error for error in errors), errors)

    def test_an_adoption_receipt_era_nothing_accounts_for_is_refused(self):
        """The replacement check has teeth without today's constants.

        The chain accounts for the version before and the version after every
        adoption this instance recorded, plus the live identity.  A commit
        receipt claiming anything else describes a transaction that never
        happened here.
        """
        self.commit_one_adoption()
        errors = self.rewrite_adoption_receipts(
            tool_version={adopt_standards.TOOL: "1.1.0"},
            standards_version={adopt_standards.TOOL: "9.9.9"})
        era_errors = [error for error in errors
                      if "claims standards_version='9.9.9'" in error]
        self.assertEqual(1, len(era_errors), errors)
        self.assertIn("commit receipt", era_errors[0])
        self.assertIn("no Standards adoption record or live identity",
                      era_errors[0])

    def test_the_accounted_era_set_is_the_instance_own_adoption_chain(self):
        """Both ends of every recorded step, plus the live identity."""
        self.commit_one_adoption()
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual(
            {"3.0.0", "3.1.0"},
            check_queue.accounted_standards_versions(
                runtime["progress"], runtime["queue"]))
        self.assertEqual(
            {"3.0.0"},
            check_queue.accounted_standards_versions(
                {"contract": {"standards_version": "3.0.0"},
                 "standards_adoptions": []}))

    # ------------------------------------------------------------------
    # Sealing must not un-replay a consumption a Queue transition recorded.
    #
    # The failure these pin: sealing kept every item's transition receipts
    # hot but moved the aggregates those transitions bind.  The consumption
    # replay resolves that aggregate through the catalog, the catalog never
    # reads the cold namespace, so the replay quietly found nothing and
    # reported bindings the transition had discharged as outstanding again
    # -- on batches by then closed, which `--require-revalidation` refuses.
    # Zero errors were reported the whole time.
    # ------------------------------------------------------------------

    # Borrowed from the Queue suite, which drives the same fixture: this
    # file can adopt and revalidate but has no hand-built close bundle, and
    # `check_batch_close.py` itself needs scaffolding this fixture lacks.
    append_receipt = UpdateQueueTests.append_receipt
    queue_gate = UpdateQueueTests.queue_gate
    close_gate = UpdateQueueTests.close_gate

    # Named fields whose consumers may resolve a sealed receipt.  Each entry
    # is a promise that a declared sealed branch handles that field; the
    # reachability assertion below is what keeps the promise a closed set
    # rather than a hand-written guess that drifts.
    SEALED_BRANCH_FIELDS = frozenset((
        # the closed-bundle identity branch (sealed_closed_bundle_errors)
        "close_gate_receipt", "queue_consistency_receipt",
        "delta_apply_receipt",
        # identity comparison and existence-only resolution
        # (require_receipt with no `expected`)
        "evidence_receipt", "revalidation_receipts",
        # the body branch added with this rule (Catalog.resolve_sealed)
        "standards_revalidation_receipt",
    ))

    def reachable_receipt_references(self, result):
        """``(field, receipt_id)`` pairs reached through the declared schema.

        Walks `check_queue.RECEIPT_REFERENCE_FIELDS` -- the named structural
        inventory of how a record references a receipt -- rather than
        sweeping values for anything that looks like an ID.  A sweep would
        answer a different question: it finds strings that happen to be
        receipt IDs, while the defect was about *fields* whose consumers
        resolve one.  Walking the schema also means a new reference field
        that nobody registered is invisible here and caught by the paired
        inventory test instead, which is where that failure belongs.
        """
        inventory = check_queue.RECEIPT_REFERENCE_FIELDS
        catalog = result["receipt_catalog"]
        found = []

        def visit(record, group):
            spec = inventory[group]
            for field in spec["scalar"]:
                value = record.get(field)
                if isinstance(value, str) and value:
                    found.append((field, value))
            for field in spec["list"]:
                for value in record.get(field) or []:
                    if isinstance(value, str) and value:
                        found.append((field, value))
            for field, child_group in spec["nested"]:
                child = record.get(field)
                for nested in (child if isinstance(child, list) else [child]):
                    if isinstance(nested, dict):
                        visit(nested, child_group)

        for item in (result.get("queue") or {}).get("required_queue") or []:
            visit(item, "item")
            for receipt_id in item.get("transition_receipts") or []:
                entry = catalog.get(receipt_id)
                if entry is not None:
                    visit(entry[1], "transition")
        return found

    def seal(self, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS / "seal_receipts.py"),
             str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False)

    def closed_b1_that_consumed_an_aggregate(self):
        """Drive B1 through a real revalidation and out to `closed`."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.lifecycle_boundary_plan(invalidated_gate)
        link_receipt = self.link_gate_receipt()
        # Produce one complete, legitimate attempt that no transition
        # consumes, then consume a fresh attempt.  Current metadata property
        # owners can correctly keep the entire close replay bundle hot; this
        # independent historical aggregate gives the sealing assertions a
        # cold candidate without weakening that owner-evidence guarantee.
        historical = self.revalidation_aggregate(link_receipt)
        aggregate = self.revalidation_aggregate(link_receipt)
        self.assertNotEqual(historical["receipt_id"], aggregate["receipt_id"])
        cleared_at = self.clear_b1_hold(aggregate)
        self.merge_and_apply_b1(self.seconds_after(cleared_at, 1))
        gate = self.queue_gate()
        close_gate = self.close_gate("B1", gate)
        result = check_queue.validate_runtime(self.root)
        applied = next(entry for entry in result["applied_delta_receipts"]
                       if entry.get("batch") == "B1")
        completed = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "closed",
            "--gate-receipt", gate, "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", applied["selected_receipt"],
            "--expected-state-revision",
            str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator",
            "--at", self.seconds_after(cleared_at, 3), "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        final = check_queue.validate_runtime(self.root)
        self.assertEqual([], final["errors"])
        self.assertEqual("closed", final["items_by_id"]["B1"]["state"])
        # The premise of every test below: this consumption really happened.
        self.assertEqual([], check_queue.outstanding_standards_revalidation(
            final, "B1"))
        return aggregate["receipt_id"], final

    def seal_ignoring_the_rule(self, result):
        """Reproduce an archive sealed by the protocol that had no rule.

        The repair has to work on instances already in this state, so it is
        tested against a real archive built the way 1.2.0 built one, not
        against a hand-placed cold row.
        """
        with mock.patch.object(seal_receipts, "_transition_bound_aggregates",
                               return_value=()):
            by_file = seal_receipts.plan_seal(str(self.root), result)
            seal_receipts.apply_seal(str(self.root), result, by_file,
                                     seal_receipts.SEAL_RECEIPTS_PATH)
        return by_file

    def test_a_consumed_revalidation_aggregate_is_never_sealed(self):
        aggregate_id, before = self.closed_b1_that_consumed_an_aggregate()
        planned = {receipt_id for rows in
                   seal_receipts.plan_seal(str(self.root), before).values()
                   for receipt_id, _ in rows}
        self.assertNotIn(aggregate_id, planned)
        self.assertTrue(planned, "the seal must still be sealing something")

        completed = self.seal("--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        after = check_queue.validate_runtime(self.root)
        self.assertEqual([], after["errors"])
        self.assertIn(aggregate_id, after["receipt_catalog"])
        self.assertNotIn(aggregate_id, after["receipt_catalog"].cold)
        self.assertEqual([], check_queue.outstanding_standards_revalidation(
            after, "B1"))

    def test_an_archive_sealed_before_the_rule_still_replays(self):
        aggregate_id, before = self.closed_b1_that_consumed_an_aggregate()
        self.seal_ignoring_the_rule(before)

        after = check_queue.validate_runtime(self.root)
        catalog = after["receipt_catalog"]
        self.assertNotIn(aggregate_id, catalog,
                         "the fixture must really have sealed it")
        self.assertIn(aggregate_id, catalog.cold)
        # The projection alone cannot answer this: the consumed keys are in
        # `revalidation_bindings` and the retraction test reads
        # `invalidated_by`, and the projection carries neither.
        self.assertNotIn("revalidation_bindings", catalog.cold[aggregate_id])
        body = catalog.resolve_sealed(aggregate_id)[1]
        self.assertTrue(body.get("revalidation_bindings"))

        self.assertEqual([], after["errors"])
        self.assertEqual([], check_queue.outstanding_standards_revalidation(
            after, "B1"))

    def test_a_sealed_body_whose_bytes_drifted_does_not_resolve(self):
        aggregate_id, before = self.closed_b1_that_consumed_an_aggregate()
        self.seal_ignoring_the_rule(before)
        catalog = check_queue.validate_runtime(self.root)["receipt_catalog"]
        segment = self.root / catalog.cold[aggregate_id]["segment"]
        lines = segment.read_bytes().splitlines(keepends=True)
        needle = ('"receipt_id": "%s"' % aggregate_id).encode("utf-8")
        changed = 0
        for index, line in enumerate(lines):
            if needle not in line:
                continue
            # A same-length edit of this exact aggregate: the projection
            # still names the line, and only re-proving the record's own hash
            # at the read can tell.  Do not assume it is the segment's first
            # row now that the fixture also carries independent history.
            rewritten = line.replace(
                b'"result": "pass"', b'"result": "PASS"', 1)
            changed += int(rewritten != line)
            lines[index] = rewritten
        self.assertEqual(1, changed, "target aggregate was not mutated once")
        segment.write_bytes(b"".join(lines))
        fresh = check_queue.receipt_catalog(str(self.root), [])
        fresh.cold = catalog.cold
        self.assertIsNone(fresh.resolve_sealed(aggregate_id))

    def test_an_unresolvable_consumed_aggregate_fails_the_run_closed(self):
        aggregate_id, before = self.closed_b1_that_consumed_an_aggregate()
        self.seal_ignoring_the_rule(before)
        catalog = check_queue.validate_runtime(self.root)["receipt_catalog"]
        (self.root / catalog.cold[aggregate_id]["segment"]).unlink()

        after = check_queue.validate_runtime(self.root)
        self.assertTrue(any(
            aggregate_id in error and
            "resolves neither in the hot register" in error
            for error in after["errors"]), after["errors"])
        # The replay cannot know what it cannot read, so B1's bindings do
        # come back as outstanding here -- that is exactly the reading this
        # rule refuses to let pass unremarked.  The guarantee is that the
        # run is not clean while it says so, and that recovery is routed to
        # the unreachable evidence rather than to a revalidation the closed
        # batch could never run.
        self.assertIn(
            "B1", after.get("standards_revalidation_outstanding") or {})
        self.assertEqual("repair-runtime",
                         check_queue.resume_next_action(after,
                                                         after["errors"]))

    def test_the_reference_inventory_matches_the_record_schemas(self):
        """The inventory may not drift from the records it describes."""
        inventory = check_queue.RECEIPT_REFERENCE_FIELDS
        item_fields = (set(inventory["item"]["scalar"]) |
                       set(inventory["item"]["list"]) |
                       {field for field, _ in inventory["item"]["nested"]})
        self.assertLessEqual(item_fields, check_queue.QUEUE_ITEM_FIELDS)
        invalidation_fields = (set(inventory["invalidation"]["scalar"]) |
                               set(inventory["invalidation"]["list"]))
        # An invalidation record's schema is both halves: a rollback taken
        # after the delta was applied additionally names the application it
        # undoes, and that name is a receipt reference like any other.
        self.assertLessEqual(
            invalidation_fields,
            check_queue.INVALIDATION_FIELDS |
            check_queue.INVALIDATION_APPLIED_ROLLBACK_FIELDS)

    def test_consumption_is_identical_across_the_seal(self):
        """Sealing is a parse-cost move; it may not change an answer."""
        _, before = self.closed_b1_that_consumed_an_aggregate()
        consumed_before = check_queue.consumed_standards_revalidation_keys(
            before["items_by_id"]["B1"], before["receipt_catalog"])
        self.assertTrue(consumed_before, "the premise: something was consumed")

        completed = self.seal("--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        after = check_queue.validate_runtime(self.root)
        self.assertTrue(after["receipt_catalog"].cold, "nothing sealed")
        self.assertEqual(
            consumed_before,
            check_queue.consumed_standards_revalidation_keys(
                after["items_by_id"]["B1"], after["receipt_catalog"]))

    def test_consumption_survives_an_archive_sealed_before_the_rule(self):
        _, before = self.closed_b1_that_consumed_an_aggregate()
        consumed_before = check_queue.consumed_standards_revalidation_keys(
            before["items_by_id"]["B1"], before["receipt_catalog"])
        self.seal_ignoring_the_rule(before)
        after = check_queue.validate_runtime(self.root)
        self.assertEqual(
            consumed_before,
            check_queue.consumed_standards_revalidation_keys(
                after["items_by_id"]["B1"], after["receipt_catalog"]))

    def test_every_sealed_reference_a_named_field_makes_has_a_branch(self):
        """The closed-set assertion whose absence let this ship.

        `_hot_reference_ids` enumerates protected fields by hand while
        consumers resolve receipt IDs from their own fields, so the defect
        was never one missing field -- it was that nothing compared the two
        sets.  Every reference the declared schema reaches that lands on a
        sealed receipt must sit at a field with a declared sealed branch.
        """
        _, before = self.closed_b1_that_consumed_an_aggregate()
        # Current sealing correctly keeps both transition-bound aggregates
        # and live property-owner close bundles hot.  Exercise the sealed
        # reference consumers against the supported legacy archive shape,
        # produced by the older protocol before the aggregate keep rule.
        self.seal_ignoring_the_rule(before)
        result = check_queue.validate_runtime(self.root)
        cold = result["receipt_catalog"].cold
        self.assertTrue(cold, "nothing sealed; the assertion is vacuous")

        references = self.reachable_receipt_references(result)
        self.assertTrue(references, "the schema walk reached nothing")
        sealed = [(field, receipt_id) for field, receipt_id in references
                  if receipt_id in cold]
        self.assertTrue(sealed, "no sealed reference was reached at all")
        self.assertEqual(
            [], [pair for pair in sealed
                 if pair[0] not in self.SEALED_BRANCH_FIELDS],
            "a record references a sealed receipt at a field no sealed "
            "branch covers")

    # ------------------------------------------------------------------
    # `run-standards-revalidation:<id>` must name a batch its own producer
    # would admit.  K00/12 gives that Gate the lifecycle cells `queued,
    # open`, so the token was naming closed batches for an aggregate
    # `--require-revalidation` refuses outright -- and because exactly one
    # token is reported per run, it hid every later row behind it.
    # ------------------------------------------------------------------

    def revalidation_result(self, **item):
        """A reduced resume context carrying one outstanding batch."""
        record = {"id": "B1", "order": 1, "state": "queued",
                  "hold_state": "none"}
        record.update(item)
        return {
            "standards_revalidation_outstanding": {
                "B1": [{"adoption_id": "SA-001", "boundary_id": "INV-B1",
                        "required_gate_id": "batch-close"}]},
            "items_by_id": {"B1": record},
            "progress": {"task_state": item.pop("task_state", "active")},
            "queue": {"required_queue": [{"id": "B1"}]},
        }

    def test_next_action_only_names_a_batch_the_producer_admits(self):
        cases = (
            ({"state": "queued"}, True),
            ({"state": "open", "hold_state": "revalidation-required"}, True),
            ({"state": "open", "hold_state": "none"}, False),
            ({"state": "closed"}, False),
            ({"state": "cancelled"}, False),
            ({"state": "merge-ready"}, False),
        )
        for item, admitted in cases:
            with self.subTest(**item):
                result = self.revalidation_result(**item)
                eligible = (
                    check_queue.standards_revalidation_producer_eligibility(
                        result, "B1") is None)
                self.assertEqual(admitted, eligible)
                self.assertEqual(
                    ["B1"] if admitted else [],
                    check_queue.actionable_revalidation_batches(result))
                token = check_queue.resume_next_action(result, [])
                if admitted:
                    self.assertEqual("run-standards-revalidation:B1", token)
                else:
                    self.assertNotIn("run-standards-revalidation", token)

    def test_a_named_batch_always_passes_the_producer_gate(self):
        """The acceptance condition, stated as the invariant it is."""
        for state in sorted(check_queue.STATES):
            for hold in sorted(check_queue.HOLDS):
                for task_state in ("active", "paused"):
                    result = self.revalidation_result(
                        state=state, hold_state=hold, task_state=task_state)
                    for batch_id in check_queue.actionable_revalidation_batches(
                            result):
                        self.assertIsNone(
                            check_queue
                            .standards_revalidation_producer_eligibility(
                                result, batch_id),
                            "named %s at state=%s hold=%s task=%s, which the "
                            "producer refuses" %
                            (batch_id, state, hold, task_state))


if __name__ == "__main__":
    unittest.main()
