import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TOOLS_DIR.parent
SYNTHETIC_PROFILE = TOOLS_DIR / "tests" / "fixtures" / "synthetic_profile"
SCRIPT = TOOLS_DIR / "check_proof.py"
TEMPLATE = TOOLS_DIR / "schemas" / "terminal_proof.template.yaml"
SYNTHETIC_STANDARDS_VERSION = "3.2.0"
sys.path.insert(0, str(TOOLS_DIR))

import check_proof
import kblib


def materialize_synthetic_standards_state(document, profile_manifest):
    """Set fixture-owned active state in a generic or instantiated K00/03."""

    replacements = (
        ("Standards version", SYNTHETIC_STANDARDS_VERSION),
        ("Status", "approved"),
        ("Effective date", "2026-08-04"),
        ("Selected profile manifest", profile_manifest),
    )
    for field, value in replacements:
        pattern = r"(?m)^\| %s \| .* \|$" % re.escape(field)
        document, count = re.subn(
            pattern,
            "| %s | `%s` |" % (field, value),
            document,
        )
        if count != 1:
            raise AssertionError(
                "expected exactly one %s row in synthetic K00/03, found %d"
                % (field, count)
            )
    return document


class ActiveStandardsFixtureTests(unittest.TestCase):
    def test_materializer_replaces_populated_adopter_state(self):
        source = """\
| Field | Value |
|---|---|
| Standards version | `9.9.9` |
| Status | `superseded` |
| Effective date | `2099-01-01` |
| Selected profile manifest | `profiles/other/profile.md` |
"""
        rendered = materialize_synthetic_standards_state(
            source, "profiles/test-profile/profile.md"
        )
        self.assertIn(
            "| Standards version | `3.2.0` |", rendered
        )
        self.assertIn("| Status | `approved` |", rendered)
        self.assertIn(
            "| Selected profile manifest | "
            "`profiles/test-profile/profile.md` |",
            rendered,
        )


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
            "queue_check_receipt", "corpus_plan_check_receipt",
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

    def test_zero_receipts_never_reads_as_nothing_in_scope(self):
        """K12/16: silence about a dimension is not an applicability claim."""
        for mutation, check in (
                (lambda coverage: coverage.pop("formula_and_numeric"),
                 "proof-dimension-missing"),
                (lambda coverage: coverage.__setitem__(
                    "formula_and_numeric", []),
                 "proof-dimension-empty"),
                (lambda coverage: coverage.__setitem__(
                    "formula_and_numeric", "not-applicable:   "),
                 "proof-dimension-declaration-invalid"),
                (lambda coverage: coverage.__setitem__(
                    "formula_and_numeric", "none found"),
                 "proof-dimension-declaration-invalid")):
            with self.subTest(check=check):
                proof = dict(self.proof)
                proof["dimension_coverage"] = dict(proof["dimension_coverage"])
                mutation(proof["dimension_coverage"])
                result = self.run_proof(proof)
                self.assertEqual(
                    1, result.returncode, result.stdout + result.stderr)
                self.assertIn(check, result.stdout)
                self.assertIn("formula_and_numeric", result.stdout)

    def test_explicit_not_applicable_declaration_is_accepted(self):
        proof = dict(self.proof)
        proof["dimension_coverage"] = dict(proof["dimension_coverage"])
        proof["dimension_coverage"]["formula_and_numeric"] = (
            "not-applicable: no page in the frozen scope states a formula")
        result = self.run_proof(proof)
        self.assertNotIn("proof-dimension", result.stdout)

    def test_dimension_coverage_must_be_a_mapping(self):
        proof = dict(self.proof)
        proof["dimension_coverage"] = []
        result = self.run_proof(proof)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-coverage-invalid", result.stdout)

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
        self.root = Path("/tmp/current-evidence-fixture")
        self.receipt_id = "audit-check_links-current"
        self.receipt = {
            "receipt_id": self.receipt_id,
            "tool": "check_links",
            "result": "pass",
        }

    def runtime(self, *, current=None, historical=None, invalidated=None):
        return {
            "current_receipt_catalog": (
                {self.receipt_id: ("receipts.jsonl", self.receipt)}
                if current is None else current),
            "receipt_catalog": (
                {self.receipt_id: ("receipts.jsonl", self.receipt)}
                if historical is None else historical),
            "invalidated_evidence_receipt_ids": invalidated or [],
        }

    def test_reused_receipts_must_be_in_current_catalog(self):
        proof = {"reused_receipts": [{"receipt_id": self.receipt_id}]}
        self.assertEqual([], check_proof._reused_receipt_evidence_failures(
            self.root, proof, runtime=self.runtime()))

        failures = check_proof._reused_receipt_evidence_failures(
            self.root, proof,
            runtime=self.runtime(
                current={}, historical={
                    self.receipt_id: ("receipts.jsonl", self.receipt),
                }))
        self.assertEqual("proof-reused-receipt-not-current", failures[0][0])

    def test_empty_current_catalog_never_falls_back_to_history(self):
        proof = {"reused_receipts": [self.receipt_id]}
        failures = check_proof._reused_receipt_evidence_failures(
            self.root, proof,
            runtime=self.runtime(current={}, historical={
                self.receipt_id: ("receipts.jsonl", self.receipt),
            }))
        self.assertIn("historical evidence is not a fallback", failures[0][2])

    def test_invalidated_reused_receipt_fails_even_if_catalog_entry_exists(self):
        proof = {"reused_receipts": [self.receipt_id]}
        failures = check_proof._reused_receipt_evidence_failures(
            self.root, proof,
            runtime=self.runtime(invalidated=[self.receipt_id]))
        self.assertEqual("proof-reused-receipt-invalidated-evidence",
                         failures[0][0])


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

    def test_explicit_final_guidance_dispositions_are_not_pending(self):
        progress = dict(self.progress)
        progress["guidance_queue"] = [
            {"guidance_id": "G-1", "disposition": "queue-next",
             "status": status}
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
        (self.root / "profiles").mkdir()
        shutil.copy2(
            REPOSITORY_ROOT / "profiles/README.md",
            self.root / "profiles/README.md",
        )
        shutil.copytree(
            SYNTHETIC_PROFILE,
            self.root / "profiles/test-profile",
        )
        self.profile_manifest = "profiles/test-profile/profile.md"
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
        active = materialize_synthetic_standards_state(
            active, self.profile_manifest
        )
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
            "standards_version": SYNTHETIC_STANDARDS_VERSION,
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
                "standards_version": SYNTHETIC_STANDARDS_VERSION,
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
            "standards_version": SYNTHETIC_STANDARDS_VERSION,
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
            "gate_id": "required-queue-completion",
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
        (receipt_dir / "terminal-full.jsonl").write_text(
            json.dumps({"result": "pass"}) + "\n", encoding="utf-8"
        )

        corpus_receipt = kblib.make_receipt(
            "check_corpus_plan",
            check_proof.check_corpus_plan.TOOL_VERSION,
            "corpus_plan", self.profile_manifest, "pass",
            "terminal fixture Corpus Planning bytes passed", 1)
        corpus_receipt["gate_id"] = "corpus-plan-structure"
        corpus_receipt.update(
            check_proof.check_corpus_plan.current_freshness_binding(
                self.root, self.profile_manifest,
                task_id="task-1", queue_revision=1,
                queue_state_revision=0,
                coverage_ledger_sha256=coverage_sha,
                required_queue_sha256=queue_sha,
                progress_ledger_sha256=progress_sha,
                repository_snapshot_sha256=
                    kblib.repository_snapshot_sha256(self.root),
            ))
        # Two AuditPlan-completed records carrying an explicit K12/07
        # dimension, so the Proof's per-dimension accounting has real evidence
        # to resolve against.
        self.dimension_receipts = {}
        dimension_lines = []
        for index, dimension in enumerate(
                ("structure_and_links", "content_and_depth"), start=1):
            record = kblib.make_receipt(
                "manual-attestation", "1.0.0", "audit_dimension",
                "frozen snapshot", "pass",
                "fixture %s verdict for the frozen snapshot" % dimension,
                index)
            record["dimension"] = dimension
            self.dimension_receipts[dimension] = record["receipt_id"]
            dimension_lines.append(json.dumps(record, sort_keys=True) + "\n")
        register.write_text(
            json.dumps(receipt, sort_keys=True) + "\n" +
            json.dumps(corpus_receipt, sort_keys=True) + "\n" +
            "".join(dimension_lines),
            encoding="utf-8",
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
            "corpus_plan_check_receipt": corpus_receipt["receipt_id"],
            "standards_version": SYNTHETIC_STANDARDS_VERSION,
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
                "kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md",
            ],
            "guidance_cutoff_id": "G-000",
            "audit_receipt_register": ".cambium/receipts/terminal.jsonl",
            "full_deterministic_results":
                ".cambium/receipts/terminal-full.jsonl",
            "incremental_manual_scope": [],
            "corpus_plan_semantic_acceptance_receipt": None,
            "dimension_coverage": {
                "structure_and_links": [
                    self.dimension_receipts["structure_and_links"]],
                "content_and_depth": [
                    self.dimension_receipts["content_and_depth"]],
                "coverage_and_integration": [self.receipt_id],
                "guidance_and_contract": [corpus_receipt["receipt_id"]],
                "formula_and_numeric":
                    "not-applicable: the frozen one-batch fixture scope states "
                    "no formula, symbol, numeric example, or metric provenance",
                "source_and_currentness":
                    "not-applicable: the fixture scope cites no external "
                    "source and carries no time-sensitive claim",
                "rendering":
                    "not-applicable: visual_trigger: not_applicable, matching "
                    "rendering_evidence",
            },
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
        self.assertEqual(check_proof.TOOL_VERSION, receipt["tool_version"])
        self.assertEqual(check_proof.GATE_ID, receipt["gate_id"])
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
        proof = kblib.load_yaml_file(self.proof_path)
        self.assertEqual(proof["corpus_plan_check_receipt"],
                         receipt["corpus_plan_check_receipt"])

    def test_changed_corpus_plan_slot_invalidates_terminal_proof(self):
        slot = self.root / "profiles/test-profile/corpus-planning.yaml"
        slot.write_text(
            slot.read_text(encoding="utf-8") + "\n",
            encoding="utf-8")
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-corpus-plan-receipt-stale", result.stdout)

    def test_tampered_corpus_plan_receipt_binding_fails_closed(self):
        proof = kblib.load_yaml_file(self.proof_path)
        receipt_id = proof["corpus_plan_check_receipt"]
        register = self.root / proof["audit_receipt_register"]
        records = [json.loads(line) for line in register.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for record in records:
            if record.get("receipt_id") == receipt_id:
                record["selected_profile_manifest_sha256"] = \
                    "sha256:" + "0" * 64
        register.write_text("".join(
            json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8")
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-corpus-plan-receipt-stale", result.stdout)

    def test_corpus_receipt_in_history_but_not_current_fails_closed(self):
        proof = kblib.load_yaml_file(self.proof_path)
        runtime = check_proof.check_queue.validate_runtime(self.root)
        historical = check_proof.check_queue.historical_receipt_catalog(runtime)
        current = dict(check_proof.check_queue.current_receipt_catalog(runtime))
        current.pop(proof["corpus_plan_check_receipt"], None)
        filtered = dict(runtime)
        filtered["receipt_catalog"] = historical
        filtered["current_receipt_catalog"] = current
        with mock.patch.object(
                check_proof.check_queue, "validate_runtime",
                return_value=filtered):
            failures, passed = check_proof._validate_corpus_plan_linkage(
                self.root, proof, proof["progress_ledger_sha256"])
        self.assertFalse(passed)
        self.assertIn(
            "proof-corpus-plan-receipt-not-current",
            [failure[0] for failure in failures],
        )

    def rewrite_dimension_coverage(self, mutate):
        proof = kblib.load_yaml_file(self.proof_path)
        mutate(proof["dimension_coverage"])
        self.proof_path.write_text(
            kblib.canonical_yaml(proof), encoding="utf-8")

    def test_base_dimension_without_evidence_or_declaration_fails_closed(self):
        """A dimension nobody ran must not pass by having no receipts."""
        self.rewrite_dimension_coverage(
            lambda coverage: coverage.pop("formula_and_numeric"))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-missing", result.stdout)
        self.assertIn("formula_and_numeric", result.stdout)

    def test_dimension_receipt_absent_from_the_register_fails_closed(self):
        self.rewrite_dimension_coverage(
            lambda coverage: coverage.__setitem__(
                "formula_and_numeric",
                ["audit-manual-attestation-20260804T000000Z-"
                 "99999999999999999999999999999999-0001"]))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-missing", result.stdout)

    def test_receipt_filed_under_another_dimension_fails_closed(self):
        def move_content_receipt(coverage):
            coverage["content_and_depth"] = (
                "not-applicable: moved for this fixture")
            coverage["formula_and_numeric"] = [
                self.dimension_receipts["content_and_depth"]]

        self.rewrite_dimension_coverage(move_content_receipt)
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-mismatch", result.stdout)

    def test_receipt_cited_under_two_dimensions_fails_closed(self):
        self.rewrite_dimension_coverage(
            lambda coverage: coverage.__setitem__(
                "formula_and_numeric",
                [self.dimension_receipts["structure_and_links"]]))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-duplicate", result.stdout)

    def test_invalidated_dimension_receipt_fails_closed(self):
        register = self.root / ".cambium/receipts/terminal.jsonl"
        records = [json.loads(line) for line in register.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for record in records:
            if record.get("receipt_id") == self.dimension_receipts[
                    "content_and_depth"]:
                record["invalidated_by"] = "audit-superseding-review"
        register.write_text("".join(
            json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8")
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-invalidated", result.stdout)

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
            "gate_id": "required-queue-completion",
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

    def validate(self, current_catalog=None, invalidated_ids=None):
        if current_catalog is None:
            current_catalog = {
                self.receipt.get("receipt_id"):
                    (".cambium/receipts/terminal.jsonl", self.receipt),
            }
        runtime = {
            "current_receipt_catalog": current_catalog,
            "receipt_catalog": current_catalog,
            "invalidated_evidence_receipt_ids": invalidated_ids or [],
        }
        with mock.patch.object(
                check_proof.check_queue, "validate_runtime",
                return_value=runtime):
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

    def test_historical_catalog_is_not_a_current_evidence_fallback(self):
        failures, _ = self.validate(current_catalog={})
        self.assertIn("proof-queue-receipt-not-current",
                      self.checks(failures))

    def test_standards_invalidated_queue_receipt_fails_closed(self):
        failures, _ = self.validate(
            current_catalog={}, invalidated_ids=[self.receipt_id])
        self.assertIn("proof-queue-receipt-invalidated-evidence",
                      self.checks(failures))

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
