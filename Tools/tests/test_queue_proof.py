import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TOOLS_DIR.parent
SCRIPT = TOOLS_DIR / "check_proof.py"
TEMPLATE = TOOLS_DIR / "schemas" / "terminal_proof.template.yaml"
sys.path.insert(0, str(TOOLS_DIR))

import check_proof
import kblib


class QueueProofStructuralTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.proof = kblib.parse_yaml_subset(
            TEMPLATE.read_text(encoding="utf-8")
        )
        self.proof.update({
            "standards_version": "cambium-test-v1",
            "selected_profile_manifest": "profiles/test/profile.md",
            "coverage_ledger_sha256": "sha256:" + "2" * 64,
            "progress_ledger_sha256": "sha256:" + "3" * 64,
            "required_queue_sha256": "sha256:" + "1" * 64,
            "remaining_required_work_units": 0,
        })

    def tearDown(self):
        self.tempdir.cleanup()

    def run_proof(self, proof):
        proof_path = self.root / "terminal-proof.yaml"
        proof_path.write_text(kblib.canonical_yaml(proof), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(proof_path)],
            text=True, capture_output=True, check=False,
        )

    def test_missing_queue_field_fails_closed(self):
        queue_fields = (
            "coverage_ledger_sha256", "progress_ledger_sha256",
            "required_queue_path", "queue_revision", "queue_state_revision",
            "required_queue_sha256", "remaining_required_work_units",
            "queue_check_receipt",
        )
        for field in queue_fields:
            with self.subTest(field=field):
                proof = dict(self.proof)
                del proof[field]
                result = self.run_proof(proof)
                self.assertEqual(
                    result.returncode, 1, result.stdout + result.stderr
                )
                self.assertIn("proof-field-missing", result.stdout)
                self.assertIn(field, result.stdout)

    def test_remaining_required_work_nonzero_fails_completion(self):
        self.proof["remaining_required_work_units"] = 1
        result = self.run_proof(self.proof)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("proof-zero-field", result.stdout)
        self.assertIn("remaining_required_work_units", result.stdout)

    def test_malformed_runtime_fingerprint_fails_closed(self):
        for field, check in (
                ("coverage_ledger_sha256",
                 "proof-coverage-fingerprint-invalid"),
                ("progress_ledger_sha256",
                 "proof-progress-fingerprint-invalid"),
                ("required_queue_sha256", "proof-queue-fingerprint-invalid")):
            with self.subTest(field=field):
                proof = dict(self.proof)
                proof[field] = "sha256:not-a-fingerprint"
                result = self.run_proof(proof)
                self.assertEqual(1, result.returncode,
                                 result.stdout + result.stderr)
                self.assertIn(check, result.stdout)

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


class TerminalRuntimeClosureTests(unittest.TestCase):
    def setUp(self):
        self.proof = {
            "task_id": "task-1",
            "scope_version": "s1",
            "contract_version": "c1",
            "standards_version": "cambium-test-v1",
            "selected_profile_manifest": "profiles/test/profile.md",
            "coverage_ledger_sha256": "sha256:" + "2" * 64,
            "progress_ledger_sha256": "sha256:" + "3" * 64,
        }
        self.progress = {
            "task_id": "task-1",
            "task_state": "completion-candidate",
            "contract": {
                "completion_semantics": "build",
                "scope_version": "s1",
                "contract_version": "c1",
                "standards_version": "cambium-test-v1",
                "selected_profile_manifest": "profiles/test/profile.md",
            },
            "amendments": [],
            "guidance_queue": [],
        }
        self.coverage = {
            "task_id": "task-1",
            "scope_version": "s1",
            "standards_version": "cambium-test-v1",
            "selected_profile_manifest": "profiles/test/profile.md",
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

    def test_nonterminal_task_state_fails(self):
        for state in ("planned", "active", "paused", "blocked", "cancelled"):
            with self.subTest(state=state):
                progress = dict(self.progress)
                progress["task_state"] = state
                failures = check_proof._validate_terminal_progress_state(
                    self.proof, progress
                )
                self.assertIn("progress-task-state-not-terminal-candidate",
                              self.checks(failures))

    def test_terminal_proof_rejects_maintenance_completion_semantics(self):
        progress = dict(self.progress)
        progress["contract"] = dict(self.progress["contract"])
        progress["contract"]["completion_semantics"] = "maintenance"
        failures = check_proof._validate_terminal_progress_state(
            self.proof, progress
        )
        self.assertIn(
            "progress-completion-semantics-not-build", self.checks(failures)
        )

    def test_pending_guidance_or_amendment_fails(self):
        progress = dict(self.progress)
        progress["guidance_queue"] = [
            {"id": "G-1", "status": "mapped"},
        ]
        progress["amendments"] = [
            {"id": "A-1", "status": "approved", "writeback_done": False},
            {"id": "A-2", "status": "verified", "writeback_done": False},
        ]
        checks = self.checks(check_proof._validate_terminal_progress_state(
            self.proof, progress
        ))
        self.assertIn("progress-guidance-pending", checks)
        self.assertIn("progress-amendment-pending", checks)
        self.assertIn("progress-amendment-writeback-pending", checks)

    def test_explicit_final_guidance_dispositions_are_not_pending(self):
        progress = dict(self.progress)
        progress["guidance_queue"] = [
            {"id": "G-1", "status": status}
            for status in sorted(check_proof.FINAL_GUIDANCE_STATUSES)
        ]
        progress["amendments"] = [
            {"id": "A-1", "status": "verified", "writeback_done": True},
            {"id": "A-2", "status": "deferred"},
        ]
        self.assertEqual([], check_proof._validate_terminal_progress_state(
            self.proof, progress
        ))

    def test_contract_identity_and_contract_version_must_match_proof(self):
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

    def test_canonical_progress_and_coverage_fingerprints_must_match_proof(self):
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

    def test_coverage_identity_drift_and_open_gaps_fail(self):
        self.coverage["scope_version"] = "s0"
        self.coverage["selected_profile_manifest"] = "profiles/other/profile.md"
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


class TerminalProofCanonicalCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        shutil.copytree(REPOSITORY_ROOT / "kernel", self.root / "kernel")
        shutil.copytree(REPOSITORY_ROOT / "profiles", self.root / "profiles")
        shutil.copytree(
            self.root / "profiles/examples/agent-atlas",
            self.root / "profiles/agent-atlas",
        )
        for path in (self.root / "profiles/agent-atlas").rglob("*"):
            if path.is_file() and path.suffix in (".md", ".yaml"):
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "profiles/examples/agent-atlas",
                        "profiles/agent-atlas",
                    ),
                    encoding="utf-8",
                )
        self.profile_manifest = "profiles/agent-atlas/profile.md"
        (self.root / "Tools/schemas").mkdir(parents=True)
        for name in ("check_profile.py", "kblib.py"):
            shutil.copy2(TOOLS_DIR / name, self.root / "Tools" / name)
        shutil.copy2(
            TOOLS_DIR / "schemas/execution_defaults.template.yaml",
            self.root / "Tools/schemas/execution_defaults.template.yaml",
        )
        (self.root / "Tools/check_queue.py").write_text(
            "raise SystemExit(0)\n", encoding="utf-8"
        )

        active_path = (
            self.root / "kernel/K00 Standards Control/03 Standards Governance.md"
        )
        active = active_path.read_text(encoding="utf-8")
        for placeholder, value in (
                ("{{ standards_version }}", "3.0.0"),
                ("{{ standards_status }}", "approved"),
                ("{{ standards_effective_date }}", "2026-08-04"),
                ("{{ selected_profile_manifest }}",
                 self.profile_manifest)):
            active = active.replace(placeholder, value)
        active_path.write_text(active, encoding="utf-8")

        state_dir = self.root / ".cambium/state"
        receipt_dir = self.root / ".cambium/receipts"
        state_dir.mkdir(parents=True)
        receipt_dir.mkdir(parents=True)
        queue = {
            "schema_version": 1,
            "task_id": "task-1",
            "scope_version": "s1",
            "queue_revision": 1,
            "state_revision": 0,
            "standards_version": "3.0.0",
            "selected_profile_manifest": self.profile_manifest,
            "required_queue": [{"id": "B1", "state": "closed"}],
        }
        queue_path = state_dir / "required_queue.yaml"
        queue_path.write_text(kblib.canonical_yaml(queue), encoding="utf-8")
        queue_sha = kblib.sha256_file(queue_path)
        progress = {
            "schema_version": 1,
            "task_id": "task-1",
            "task_state": "completion-candidate",
            "required_queue_path": check_proof.CANONICAL_QUEUE_PATH,
            "queue_revision": 1,
            "queue_state_revision": 0,
            "required_queue_sha256": queue_sha,
            "contract": {
                "contract_version": "c1",
                "completion_semantics": "build",
                "scope_version": "s1",
                "standards_version": "3.0.0",
                "selected_profile_manifest": self.profile_manifest,
            },
            "amendments": [],
            "guidance_queue": [],
        }
        (state_dir / "progress_ledger.yaml").write_text(
            kblib.canonical_yaml(progress), encoding="utf-8"
        )
        progress_sha = kblib.sha256_file(state_dir / "progress_ledger.yaml")
        coverage = {
            "schema_version": 1,
            "task_id": "task-1",
            "scope_version": "s1",
            "standards_version": "3.0.0",
            "selected_profile_manifest": self.profile_manifest,
            "open_gaps": [],
        }
        (state_dir / "coverage_ledger.yaml").write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8"
        )
        coverage_sha = kblib.sha256_file(state_dir / "coverage_ledger.yaml")

        self.receipt_id = (
            "audit-check_queue-20260804T000000Z-"
            "11111111111111111111111111111111-0001"
        )
        receipt = {
            "receipt_id": self.receipt_id,
            "tool": "check_queue",
            "tool_version": check_proof.check_queue.TOOL_VERSION,
            "check": "required_queue",
            "queue_check_mode": "require-complete",
            "result": "pass",
            "invalidated_by": None,
            "task_id": "task-1",
            "queue_revision": 1,
            "queue_state_revision": 0,
            "required_queue_sha256": queue_sha,
            "coverage_ledger_sha256": coverage_sha,
            "progress_ledger_sha256": progress_sha,
            "remaining_required_work_units": 0,
        }
        register = receipt_dir / "terminal.jsonl"
        register.write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
        )
        (receipt_dir / "terminal-full.jsonl").write_text(
            json.dumps({"result": "pass"}) + "\n", encoding="utf-8"
        )

        proof = kblib.parse_yaml_subset(TEMPLATE.read_text(encoding="utf-8"))
        proof.update({
            "task_id": "task-1",
            "scope_version": "s1",
            "contract_version": "c1",
            "coverage_ledger_sha256": coverage_sha,
            "progress_ledger_sha256": progress_sha,
            "required_queue_path": check_proof.CANONICAL_QUEUE_PATH,
            "queue_revision": 1,
            "queue_state_revision": 0,
            "required_queue_sha256": queue_sha,
            "remaining_required_work_units": 0,
            "queue_check_receipt": self.receipt_id,
            "standards_version": "3.0.0",
            "selected_profile_manifest": self.profile_manifest,
            "selected_route_ids": ["R01", "R08", "R12"],
            "selected_card_paths": [
                "kernel/Cards/R01 Core Bootstrap Card.md",
                "kernel/Cards/R08 Audit and Completion Card.md",
                "kernel/Cards/R12 Targeted and Specialized Audit Card.md",
            ],
            "selected_profile_route_ids": [],
            "selected_read_sets": [],
            "loaded_module_paths": [
                "kernel/K02 Build Execution/09 Required Queue.md",
            ],
            "guidance_cutoff_id": "G-000",
            "audit_receipt_register": ".cambium/receipts/terminal.jsonl",
            "full_deterministic_results":
                ".cambium/receipts/terminal-full.jsonl",
            "incremental_manual_scope": [],
        })
        self.proof_path = receipt_dir / "terminal-proof.yaml"
        self.proof_path.write_text(
            kblib.canonical_yaml(proof), encoding="utf-8"
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def run_proof(self, progress=check_proof.CANONICAL_PROGRESS_PATH,
                  coverage=check_proof.CANONICAL_COVERAGE_PATH,
                  write_receipt=False):
        command = [
            sys.executable, str(SCRIPT), str(self.proof_path),
            "--root", str(self.root), "--progress-ledger", progress,
            "--ledger", coverage,
        ]
        if write_receipt:
            command.extend([
                "--receipts", ".cambium/receipts/proof-check.jsonl",
            ])
        return subprocess.run(
            command,
            cwd=self.root, text=True, capture_output=True, check=False,
        )

    def test_complete_canonical_runtime_passes_terminal_proof(self):
        result = self.run_proof(write_receipt=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        receipt = json.loads((
            self.root / ".cambium/receipts/proof-check.jsonl"
        ).read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual("check_proof", receipt["tool"])
        self.assertEqual("proof-check-summary", receipt["check"])
        self.assertEqual("pass", receipt["result"])
        self.assertEqual(
            ".cambium/receipts/terminal-proof.yaml",
            receipt["terminal_proof_path"],
        )
        self.assertEqual(kblib.sha256_file(self.proof_path),
                         receipt["terminal_proof_sha256"])
        self.assertEqual(
            kblib.sha256_file(
                self.root / check_proof.CANONICAL_COVERAGE_PATH
            ),
            receipt["coverage_ledger_sha256"],
        )
        self.assertEqual(
            kblib.sha256_file(
                self.root / check_proof.CANONICAL_PROGRESS_PATH
            ),
            receipt["progress_ledger_sha256"],
        )

    def test_same_bytes_in_substitute_ledger_paths_cannot_pass(self):
        substitute_progress = self.root / "progress-substitute.yaml"
        substitute_coverage = self.root / "coverage-substitute.yaml"
        substitute_progress.write_bytes(
            (self.root / check_proof.CANONICAL_PROGRESS_PATH).read_bytes()
        )
        substitute_coverage.write_bytes(
            (self.root / check_proof.CANONICAL_COVERAGE_PATH).read_bytes()
        )
        result = self.run_proof(
            str(substitute_progress), str(substitute_coverage)
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("progress-ledger-noncanonical", result.stdout)
        self.assertIn("coverage-ledger-noncanonical", result.stdout)


class QueueProofLiveLinkageTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / ".cambium/state").mkdir(parents=True)
        (self.root / ".cambium/receipts").mkdir(parents=True)
        (self.root / "Tools").mkdir()

        self.queue = {
            "schema_version": 1,
            "task_id": "task-1",
            "scope_version": "s1",
            "queue_revision": 2,
            "state_revision": 7,
            "standards_version": "cambium-test-v1",
            "selected_profile_manifest": "profiles/test/profile.md",
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
                "standards_version": "cambium-test-v1",
                "selected_profile_manifest": "profiles/test/profile.md",
            },
        }
        self.receipt_id = (
            "audit-check_queue-20260804T000000Z-"
            "11111111111111111111111111111111-0001"
        )
        self.proof = {
            "task_id": "task-1",
            "scope_version": "s1",
            "standards_version": "cambium-test-v1",
            "selected_profile_manifest": "profiles/test/profile.md",
            "required_queue_path": check_proof.CANONICAL_QUEUE_PATH,
            "queue_revision": 2,
            "queue_state_revision": 7,
            "required_queue_sha256": self.queue_sha,
            "coverage_ledger_sha256": self.coverage_sha,
            "progress_ledger_sha256": self.progress_sha,
            "remaining_required_work_units": 0,
            "queue_check_receipt": self.receipt_id,
            "audit_receipt_register": ".cambium/receipts/terminal.jsonl",
        }
        self.receipt = {
            "receipt_id": self.receipt_id,
            "tool": "check_queue",
            "tool_version": check_proof.check_queue.TOOL_VERSION,
            "check": "required_queue",
            "queue_check_mode": "require-complete",
            "result": "pass",
            "invalidated_by": None,
            "task_id": "task-1",
            "queue_revision": 2,
            "queue_state_revision": 7,
            "required_queue_sha256": self.queue_sha,
            "coverage_ledger_sha256": self.coverage_sha,
            "progress_ledger_sha256": self.progress_sha,
            "remaining_required_work_units": 0,
        }
        self.write_checker(0)
        self.write_receipt(self.receipt)

    def tearDown(self):
        self.tempdir.cleanup()

    def write_checker(self, exit_code):
        (self.root / "Tools/check_queue.py").write_text(
            "raise SystemExit(%d)\n" % exit_code, encoding="utf-8"
        )

    def write_receipt(self, receipt):
        path = self.root / ".cambium/receipts/terminal.jsonl"
        path.write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
        )

    def checks(self, failures):
        return [failure[0] for failure in failures]

    def validate(self):
        return check_proof._validate_required_queue_linkage(
            self.root, self.proof, self.progress,
            self.coverage_sha, self.progress_sha,
        )

    def test_valid_queue_proof_linkage_passes(self):
        failures, live_passed = self.validate()
        self.assertTrue(live_passed)
        self.assertEqual(failures, [])

    def test_stale_hash_and_revision_fail(self):
        self.proof["required_queue_sha256"] = "sha256:" + "f" * 64
        self.proof["queue_state_revision"] = 6
        failures, _ = self.validate()
        checks = self.checks(failures)
        self.assertGreaterEqual(checks.count("proof-required-queue-mismatch"), 2)

    def test_stale_queue_receipt_fails(self):
        self.receipt["queue_state_revision"] = 6
        self.write_receipt(self.receipt)
        failures, _ = self.validate()
        self.assertIn("proof-queue-receipt-stale", self.checks(failures))

    def test_noncompletion_mode_or_checker_version_fails(self):
        for field, value in (("queue_check_mode", "consistency"),
                             ("tool_version", "0.9.0")):
            with self.subTest(field=field):
                receipt = dict(self.receipt)
                receipt[field] = value
                self.write_receipt(receipt)
                failures, _ = self.validate()
                self.assertIn("proof-queue-receipt-stale",
                              self.checks(failures))

    def test_invalidated_queue_receipt_fails(self):
        self.receipt["invalidated_by"] = "audit-check_queue-successor"
        self.write_receipt(self.receipt)
        failures, _ = self.validate()
        self.assertIn("proof-queue-receipt-stale", self.checks(failures))

    def test_missing_queue_receipt_fails(self):
        self.receipt["receipt_id"] = "audit-check_queue-other"
        self.write_receipt(self.receipt)
        failures, _ = self.validate()
        self.assertIn("proof-queue-receipt-missing", self.checks(failures))

    def test_live_check_queue_failure_fails(self):
        self.write_checker(1)
        failures, live_passed = self.validate()
        self.assertFalse(live_passed)
        self.assertIn("proof-queue-live-check-failed", self.checks(failures))

    def test_audit_receipt_register_must_stay_in_managed_namespace(self):
        outside = self.root / "terminal.jsonl"
        outside.write_text(json.dumps(self.receipt) + "\n", encoding="utf-8")
        self.proof["audit_receipt_register"] = "terminal.jsonl"
        failures, _ = self.validate()
        self.assertIn(
            "proof-queue-receipt-register-unreadable", self.checks(failures)
        )

    def test_audit_receipt_register_rejects_symlink_and_hardlink(self):
        source = self.root / ".cambium/receipts/terminal.jsonl"
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind):
                alias = self.root / (".cambium/receipts/%s.jsonl" % kind)
                if kind == "symlink":
                    alias.symlink_to(source)
                else:
                    os.link(source, alias)
                self.proof["audit_receipt_register"] = \
                    ".cambium/receipts/%s.jsonl" % kind
                failures, _ = self.validate()
                self.assertIn(
                    "proof-queue-receipt-register-unreadable",
                    self.checks(failures),
                )
                alias.unlink()

    def test_symlinked_canonical_queue_fails_closed(self):
        target = self.root / "queue-substitute.yaml"
        target.write_bytes(self.queue_path.read_bytes())
        self.queue_path.unlink()
        self.queue_path.symlink_to(target)
        failures, _ = self.validate()
        self.assertIn("proof-required-queue-unreadable", self.checks(failures))


if __name__ == "__main__":
    unittest.main()
