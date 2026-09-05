import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
SCRIPT = TOOLS_DIR / "check_proof.py"
sys.path.insert(0, str(TOOLS_DIR / "tests"))
sys.path.insert(0, str(TOOLS_DIR))

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.check_proof as check_proof
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.queue_check_receipt as queue_check_receipt


class TerminalProofCliBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_receipt_output_cannot_overwrite_runtime_state(self):
        state = self.root / ".cambium/state/required_queue.yaml"
        state.parent.mkdir(parents=True)
        state.write_text("sentinel\n", encoding="utf-8")
        before = state.read_bytes()
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             str(self.root / "missing-proof.yaml"),
             "--receipts", str(state)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("unsafe receipt path", result.stdout)
        self.assertEqual(before, state.read_bytes())


class CanonicalStateArgumentTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.canonical = self.root / check_proof.CANONICAL_PROGRESS_PATH
        self.canonical.parent.mkdir(parents=True)
        self.canonical.write_text("schema_version: 1\n", encoding="utf-8")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_only_exact_relative_or_absolute_canonical_path_is_accepted(self):
        for supplied in (check_proof.CANONICAL_PROGRESS_PATH,
                         str(self.canonical.resolve())):
            with self.subTest(supplied=supplied):
                resolved, error = check_proof._canonical_state_argument(
                    self.root, supplied, check_proof.CANONICAL_PROGRESS_PATH
                )
                self.assertIsNone(error)
                self.assertEqual(self.canonical.resolve(), resolved)

        substitute = self.root / "substitute-progress.yaml"
        substitute.write_bytes(self.canonical.read_bytes())
        for supplied in ("substitute-progress.yaml", str(substitute),
                         "../progress_ledger.yaml"):
            with self.subTest(supplied=supplied):
                resolved, error = check_proof._canonical_state_argument(
                    self.root, supplied, check_proof.CANONICAL_PROGRESS_PATH
                )
                self.assertIsNone(resolved)
                self.assertIsNotNone(error)

    def test_canonical_symlink_is_rejected_even_when_target_stays_in_root(self):
        target = self.root / "real-progress.yaml"
        target.write_bytes(self.canonical.read_bytes())
        self.canonical.unlink()
        self.canonical.symlink_to(target)
        resolved, error = check_proof._canonical_state_argument(
            self.root, check_proof.CANONICAL_PROGRESS_PATH,
            check_proof.CANONICAL_PROGRESS_PATH,
        )
        self.assertIsNone(resolved)
        self.assertIn("symlink", error)


class TerminalProofCurrentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.receipt_id = "audit-full-current"
        self.projection = audit_evidence_runtime.reconciliation_from_bindings(
            [{
                "obligation_id": "obligation-1",
                "due_stage": "pre-merge",
                "evidence_ref": self.receipt_id,
            }], {"obligation-1": "producer-evidence-1"})
        self.close = {
            "receipt_id": "close-1",
            "audit_plan_id": "audit-plan-1",
            "invalidated_by": None,
            **self.projection,
        }
        self.proof = {
            "reused_receipts": [],
            "superseded_receipts": [],
            "invalidated_receipts": [],
            "unresolved_invalidations": 0,
        }

    def runtime(self, *, close=None, invalidated=None):
        close = self.close if close is None else close
        entry = ("receipts/close.jsonl", close)
        return {
            "items_by_id": {
                "B001": {
                    "id": "B001",
                    "state": "closed",
                    "close_gate_receipt": close["receipt_id"],
                },
            },
            "current_receipt_catalog": {close["receipt_id"]: entry},
            "invalidated_evidence_receipt_ids": invalidated or [],
        }

    def test_current_plan_reconciliation_tracks_direct_and_precursor_invalidation(self):
        self.assertEqual(
            [], check_proof._terminal_reconciliation_failures(
                self.proof, self.runtime()))

        for invalidated in (self.receipt_id, "producer-evidence-1"):
            with self.subTest(invalidated=invalidated):
                runtime = self.runtime(invalidated=[invalidated])
                failures = check_proof._terminal_reconciliation_failures(
                    self.proof, runtime)
                checks = {failure[0] for failure in failures}
                self.assertIn("proof-invalidated-receipts-mismatch", checks)
                self.assertIn(
                    "proof-unresolved-invalidations-mismatch", checks)

                reconciled = copy.deepcopy(self.proof)
                reconciled.update({
                    "invalidated_receipts": [invalidated],
                    "unresolved_invalidations": 1,
                })
                self.assertEqual(
                    [], check_proof._terminal_reconciliation_failures(
                        reconciled, runtime))

    def test_terminal_reconciliation_lists_are_sorted_unique_receipt_ids(self):
        proof = copy.deepcopy(self.proof)
        proof["superseded_receipts"] = ["old-2", "old-1", "old-1"]

        failures = check_proof._terminal_reconciliation_failures(
            proof, self.runtime())

        self.assertEqual(
            "proof-superseded-receipts-invalid", failures[0][0])

class TerminalRuntimeClosureTests(unittest.TestCase):
    def setUp(self):
        self.load_contract = {
            "selected_route_ids": ["R01"],
            "selected_card_paths": [
                "Card/R01 Core Bootstrap Card.md",
            ],
            "selected_profile_route_ids": ["P:test:supplemental"],
            "selected_read_sets": [
                "Read Set/R01 Core Bootstrap Read Set.md",
            ],
            "loaded_module_paths": [
                "kernel/K00 Standards Control/02 Task Routing.md",
            ],
        }
        self.proof = {
            "task_id": "task-1",
            "scope_version": "s1",
            "contract_version": "c1",
            "upstream_revision_id": "cambium-test-v1",
            "selected_profile_manifest": "profiles/test/profile.toml",
            "coverage_ledger_sha256": "sha256:" + "2" * 64,
            "progress_ledger_sha256": "sha256:" + "3" * 64,
            **self.load_contract,
        }
        self.progress = {
            "task_id": "task-1",
            "task_state": "completion-candidate",
            "contract": {
                "completion_semantics": "build",
                "scope_version": "s1",
                "contract_version": "c1",
                "upstream_revision_id": "cambium-test-v1",
                "selected_profile_manifest": "profiles/test/profile.toml",
                **self.load_contract,
            },
            "amendments": [],
            "guidance_queue": [],
        }
        self.coverage = {
            "task_id": "task-1",
            "scope_version": "s1",
            "upstream_revision_id": "cambium-test-v1",
            "selected_profile_manifest": "profiles/test/profile.toml",
            "open_gaps": [],
        }

    @staticmethod
    def checks(failures):
        return [failure[0] for failure in failures]

    def test_terminal_candidate_with_reconciled_controls_and_no_gaps_passes(self):
        self.assertEqual([], check_proof._validate_terminal_progress_state(
            self.proof, self.progress
        ))
        self.assertEqual([], check_proof._validate_terminal_coverage_state(
            self.proof, self.progress, self.coverage
        ))

    def test_terminal_eligibility_rejects_noncandidate_and_maintenance(self):
        for state in ("planned", "active", "paused", "blocked", "cancelled"):
            with self.subTest(state=state):
                progress = dict(self.progress)
                progress["task_state"] = state
                failures = check_proof._validate_terminal_progress_state(
                    self.proof, progress
                )
                self.assertIn("progress-task-state-not-terminal-candidate",
                              self.checks(failures))
        progress = dict(self.progress)
        progress["contract"] = dict(self.progress["contract"])
        progress["contract"]["completion_semantics"] = "maintenance"
        failures = check_proof._validate_terminal_progress_state(
            self.proof, progress
        )
        self.assertIn(
            "progress-completion-semantics-not-build", self.checks(failures)
        )

    def test_pending_guidance_and_amendment_block_terminal(self):
        progress = dict(self.progress)
        progress["guidance_queue"] = [
            {"guidance_id": "G-1", "disposition": "queue-next",
             "status": "mapped"},
        ]
        progress["amendments"] = [
            {"id": "A-1", "status": "approved", "writeback_done": False},
            {"id": "A-2", "status": "verified", "writeback_done": False},
        ]
        failures = check_proof._validate_terminal_progress_state(
            self.proof, progress
        )
        checks = self.checks(failures)
        self.assertIn("progress-guidance-pending", checks)
        self.assertIn("guidance 'G-1' has non-final status 'mapped'",
                      "\n".join(detail for _, _, detail in failures))
        self.assertIn("progress-amendment-pending", checks)
        self.assertIn("progress-amendment-writeback-pending", checks)

    def test_frozen_contract_identity_and_load_must_match_proof(self):
        progress = dict(self.progress)
        progress["contract"] = dict(self.progress["contract"])
        progress["contract"]["contract_version"] = "c0"
        progress["task_id"] = "other-task"
        checks = self.checks(check_proof._validate_terminal_progress_state(
            self.proof, progress
        ))
        self.assertGreaterEqual(
            checks.count("proof-progress-contract-mismatch"), 2
        )
        for field in self.load_contract:
            with self.subTest(field=field):
                proof = dict(self.proof)
                proof[field] = []
                progress = dict(self.progress)
                progress["contract"] = dict(self.progress["contract"])
                failures = check_proof._validate_terminal_progress_state(
                    proof, progress)
                self.assertIn(
                    "proof-progress-contract-mismatch",
                    self.checks(failures),
                )

    def test_runtime_fingerprints_and_coverage_closure_must_match_proof(self):
        progress_checks = self.checks(
            check_proof._validate_terminal_progress_state(
                self.proof, self.progress, "sha256:" + "9" * 64
            )
        )
        coverage_checks = self.checks(
            check_proof._validate_terminal_coverage_state(
                self.proof, self.progress, self.coverage,
                "sha256:" + "8" * 64,
            )
        )
        self.assertIn("proof-progress-fingerprint-mismatch", progress_checks)
        self.assertIn("proof-coverage-fingerprint-mismatch", coverage_checks)
        self.coverage["scope_version"] = "s0"
        self.coverage["selected_profile_manifest"] = "profiles/other/profile.toml"
        self.coverage["open_gaps"] = [{"page": "Topics/Missing.md"}]
        checks = self.checks(check_proof._validate_terminal_coverage_state(
            self.proof, self.progress, self.coverage
        ))
        self.assertGreaterEqual(
            checks.count("proof-coverage-identity-mismatch"), 2
        )
        self.assertGreaterEqual(
            checks.count("coverage-progress-identity-mismatch"), 2
        )
        self.assertIn("coverage-open-gaps-remaining", checks)


class QueueProofLiveLinkageTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / ".cambium/state").mkdir(parents=True)
        (self.root / ".cambium/receipts").mkdir(parents=True)

        self.queue = {
            "schema_version": 1,
            "task_id": "task-1",
            "scope_version": "s1",
            "queue_revision": 2,
            "state_revision": 7,
            "upstream_revision_id": "cambium-test-v1",
            "selected_profile_manifest": "profiles/test/profile.toml",
            "required_queue": [
                {"id": "B1", "state": "closed"},
            ],
        }
        self.queue_path = (
            self.root / ".cambium/state/required_queue.yaml"
        )
        self.queue_path.write_text(
            kblib.canonical_yaml(self.queue), encoding="utf-8"
        )
        self.queue_sha = kblib.sha256_file(self.queue_path)
        self.coverage_sha = "sha256:" + "c" * 64
        self.progress_sha = "sha256:" + "d" * 64

        self.progress = {
            "schema_version": 1,
            "task_id": "task-1",
            "required_queue_path": check_proof.CANONICAL_QUEUE_PATH,
            "queue_revision": 2,
            "queue_state_revision": 7,
            "required_queue_sha256": self.queue_sha,
            "contract": {
                "scope_version": "s1",
                "upstream_revision_id": "cambium-test-v1",
                "selected_profile_manifest": "profiles/test/profile.toml",
            },
        }
        self.receipt = queue_check_receipt.make_check_receipt(
            {
                "root": self.root,
                "queue": self.queue,
                "queue_sha256": self.queue_sha,
                "coverage_sha256": self.coverage_sha,
                "progress_sha256": self.progress_sha,
                "remaining": 0,
            },
            "pass",
            "fixture Required Queue is complete",
            "require-complete",
        )
        self.receipt_id = self.receipt["receipt_id"]
        self.proof = {
            "task_id": "task-1",
            "scope_version": "s1",
            "upstream_revision_id": "cambium-test-v1",
            "selected_profile_manifest": "profiles/test/profile.toml",
            "required_queue_path": check_proof.CANONICAL_QUEUE_PATH,
            "queue_revision": 2,
            "queue_state_revision": 7,
            "required_queue_sha256": self.queue_sha,
            "coverage_ledger_sha256": self.coverage_sha,
            "progress_ledger_sha256": self.progress_sha,
            "remaining_required_work_units": 0,
            "queue_check_receipt": self.receipt_id,
            "terminal_audit_receipt_register":
                ".cambium/receipts/terminal.jsonl",
        }
        self.write_receipt(self.receipt)

    def tearDown(self):
        self.tempdir.cleanup()

    def write_receipt(self, receipt):
        path = self.root / ".cambium/receipts/terminal.jsonl"
        path.write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
        )

    def checks(self, failures):
        return [failure[0] for failure in failures]

    def validate(self, current_catalog=None, invalidated_ids=None,
                 runtime_errors=None):
        if current_catalog is None:
            current_catalog = {
                self.receipt.get("receipt_id"):
                    (".cambium/receipts/terminal.jsonl", self.receipt),
            }
        runtime = {
            "current_receipt_catalog": current_catalog,
            "invalidated_evidence_receipt_ids": invalidated_ids or [],
            "errors": runtime_errors or [],
            "_writer_locks": [],
            "queue": self.queue,
            "queue_sha256": self.queue_sha,
            "remaining": 0,
            "progress": dict(self.progress, task_state="completion-candidate",
                             contract=dict(
                                 self.progress["contract"],
                                 completion_semantics="build")),
        }
        return check_proof._validate_required_queue_linkage(
            self.root, self.proof, self.progress,
            self.coverage_sha, self.progress_sha, runtime=runtime)

    def test_valid_queue_proof_linkage_passes(self):
        failures, live_passed = self.validate()
        self.assertTrue(live_passed)
        self.assertEqual(failures, [])

    def test_queue_state_and_current_receipt_bindings_are_exact(self):
        self.proof["required_queue_sha256"] = "sha256:" + "f" * 64
        self.proof["queue_state_revision"] = 6
        failures, _ = self.validate()
        checks = self.checks(failures)
        self.assertGreaterEqual(checks.count("proof-required-queue-mismatch"), 2)
        self.proof["required_queue_sha256"] = self.queue_sha
        self.proof["queue_state_revision"] = 7

        current = self.receipt
        for field, value in (
                ("queue_state_revision", 6),
                ("queue_check_mode", "consistency"),
                ("tool_version", "0.9.0"),
                ("invalidated_by", "audit-check_queue-successor")):
            with self.subTest(field=field):
                self.receipt = dict(current, **{field: value})
                self.write_receipt(self.receipt)
                try:
                    failures, _ = self.validate()
                    self.assertIn(
                        "proof-queue-receipt-stale", self.checks(failures))
                finally:
                    self.receipt = current
                    self.write_receipt(current)

        other = dict(self.receipt, receipt_id="audit-check_queue-other")
        self.write_receipt(other)
        current_catalog = {
            self.receipt_id:
                (".cambium/receipts/terminal.jsonl", self.receipt),
        }
        failures, _ = self.validate(current_catalog=current_catalog)
        self.assertIn("proof-queue-receipt-missing", self.checks(failures))

    def test_shared_runtime_is_required_and_live_errors_fail_closed(self):
        failures, live_passed = self.validate(
            runtime_errors=["fixture runtime invalid"])
        self.assertFalse(live_passed)
        self.assertIn("proof-queue-live-check-failed", self.checks(failures))

        failures, live_passed = \
            check_proof._validate_required_queue_linkage(
                self.root, self.proof, self.progress,
                self.coverage_sha, self.progress_sha, runtime=None)
        self.assertFalse(live_passed)
        self.assertIn("proof-required-queue-runtime-unavailable",
                      self.checks(failures))

    def test_receipt_register_rejects_outside_symlink_and_hardlink(self):
        source = self.root / ".cambium/receipts/terminal.jsonl"
        outside = self.root / "terminal.jsonl"
        outside.write_text(json.dumps(self.receipt) + "\n", encoding="utf-8")
        aliases = {
            "outside": (outside, "terminal.jsonl"),
            "symlink": (
                self.root / ".cambium/receipts/symlink.jsonl",
                ".cambium/receipts/symlink.jsonl"),
            "hardlink": (
                self.root / ".cambium/receipts/hardlink.jsonl",
                ".cambium/receipts/hardlink.jsonl"),
        }
        aliases["symlink"][0].symlink_to(source)
        os.link(source, aliases["hardlink"][0])
        for kind, (_path, relative) in aliases.items():
            with self.subTest(kind=kind):
                self.proof["terminal_audit_receipt_register"] = relative
                failures, _ = self.validate()
                self.assertIn(
                    "proof-queue-receipt-register-unreadable",
                    self.checks(failures),
                )


if __name__ == "__main__":
    unittest.main()
