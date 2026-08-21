import contextlib
import io
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
SCRIPT = TOOLS_DIR / "check_proof.py"
TEMPLATE = TOOLS_DIR / "schemas" / "terminal_proof.template.yaml"
SYNTHETIC_STANDARDS_VERSION = "3.2.0"
sys.path.insert(0, str(TOOLS_DIR / "tests"))
sys.path.insert(0, str(TOOLS_DIR))

import check_proof
import kblib
import standards_state
import test_required_queue_e2e as required_queue_e2e


def materialize_synthetic_standards_state(profile_manifest):
    """Render the fixture-owned canonical adopter Standards state."""
    return standards_state.canonical_text({
        "schema_version": 1,
        "state_revision": 1,
        "standards_version": SYNTHETIC_STANDARDS_VERSION,
        "status": "approved",
        "effective_date": "2026-08-04",
        "selected_profile_manifest": profile_manifest,
        "latest_adoption_receipt": "audit-fixture-standards-adoption",
        "upstream_source_ref": None,
        "upstream_revision_id": None,
    })


class ActiveStandardsFixtureTests(unittest.TestCase):
    def test_materializer_renders_canonical_adopter_state(self):
        rendered = materialize_synthetic_standards_state(
            "profiles/test-profile/profile.md"
        )
        parsed = kblib.parse_yaml_subset(rendered)
        self.assertEqual("3.2.0", parsed["standards_version"])
        self.assertEqual("approved", parsed["status"])
        self.assertEqual(
            "profiles/test-profile/profile.md",
            parsed["selected_profile_manifest"],
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
        self.load_contract = {
            "selected_route_ids": ["R01"],
            "selected_card_paths": [
                "kernel/Cards/R01 Core Bootstrap Card.md",
            ],
            "selected_profile_route_ids": ["P:test:supplemental"],
            "selected_read_sets": [
                "kernel/Read Sets/R01 Core Bootstrap Read Set.md",
            ],
            "loaded_module_paths": [
                "kernel/K00 Standards Control/01 Operating Role and Reading Protocol.md",
            ],
        }
        self.proof = {
            "task_id": "task-1",
            "scope_version": "s1",
            "contract_version": "c1",
            "standards_version": "cambium-test-v1",
            "selected_profile_manifest": "profiles/test/profile.md",
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
                "standards_version": "cambium-test-v1",
                "selected_profile_manifest": "profiles/test/profile.md",
                **self.load_contract,
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

    def test_frozen_load_contract_must_match_proof_exactly(self):
        """A green live Queue gate cannot license a different Proof list."""
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
    @classmethod
    def setUpClass(cls):
        """Prepare one real completed runtime, then clone it per test."""
        cls._lifecycle = required_queue_e2e.RequiredQueueEndToEndTests(
            methodName="test_two_batch_lifecycle_is_resumable_and_completes")
        cls._lifecycle.setUp()
        try:
            cls._lifecycle.install_terminal_proof_environment()
            cls._lifecycle.merge_and_close("B1", "Topics/A.md")
            cls._lifecycle.merge_and_close("B2", "Topics/B.md")
            candidate_gate_path = \
                ".cambium/receipts/proof-candidate-gate.jsonl"
            candidate_gate = cls._lifecycle.run_tool(
                "check_queue.py", "--require-complete", "--receipts",
                candidate_gate_path)
            if candidate_gate.returncode != 0:
                raise AssertionError(candidate_gate.stdout)
            candidate_gate_id = json.loads(
                (cls._lifecycle.root / candidate_gate_path).read_text(
                    encoding="utf-8").splitlines()[-1])["receipt_id"]
            cls._lifecycle.task_transition(
                "completion-candidate", "--queue-check-receipt",
                candidate_gate_id, "--checkpoint-summary",
                "all Required work units are terminal")

            terminal_register = ".cambium/receipts/terminal.jsonl"
            terminal_gate = cls._lifecycle.run_tool(
                "check_queue.py", "--require-complete", "--receipts",
                terminal_register)
            if terminal_gate.returncode != 0:
                raise AssertionError(terminal_gate.stdout)
            runtime = check_proof.check_queue.validate_runtime(
                cls._lifecycle.root)
            if runtime["errors"]:
                raise AssertionError("\n".join(runtime["errors"]))
            cls._prepared_root = cls._lifecycle.root
        except BaseException:
            cls._lifecycle.tearDown()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._lifecycle.tearDown()

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "repo"
        shutil.copytree(self._prepared_root, self.root)
        self.profile_manifest = "profiles/test-profile/profile.md"

        runtime = check_proof.check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        queue = runtime["queue"]
        progress = runtime["progress"]
        contract = progress["contract"]
        self.terminal_load_contract = {
            field: contract[field] for field in (
                "selected_route_ids", "selected_card_paths",
                "selected_profile_route_ids", "selected_read_sets",
                "loaded_module_paths")
        }

        receipt_dir = self.root / ".cambium/receipts"
        register = receipt_dir / "terminal.jsonl"
        queue_receipt = json.loads(register.read_text(
            encoding="utf-8").splitlines()[-1])
        self.receipt_id = queue_receipt["receipt_id"]

        full_receipt = kblib.make_receipt(
            "fixture_deterministic_results", "1.0.0",
            "full_deterministic_results", ".", "pass",
            "fixture deterministic checks passed", 1)
        (receipt_dir / "terminal-full.jsonl").write_text(
            json.dumps(full_receipt, sort_keys=True) + "\n",
            encoding="utf-8")

        authorized_view, profile_errors = \
            check_proof.check_queue.profile_load_authorized_view(
                self.root, self.profile_manifest)
        self.assertEqual([], profile_errors)
        corpus_receipt = kblib.make_receipt(
            "check_corpus_plan",
            check_proof.check_corpus_plan.TOOL_VERSION,
            "corpus_plan", self.profile_manifest, "pass",
            "terminal fixture Corpus Planning bytes passed", 1)
        corpus_receipt["gate_id"] = "corpus-plan-structure"
        self.corpus_receipt_id = corpus_receipt["receipt_id"]
        corpus_receipt.update(
            check_proof.check_corpus_plan.current_freshness_binding(
                self.root, self.profile_manifest,
                task_id=queue["task_id"],
                queue_revision=queue["queue_revision"],
                queue_state_revision=queue["state_revision"],
                coverage_ledger_sha256=runtime["coverage_sha256"],
                required_queue_sha256=runtime["queue_sha256"],
                progress_ledger_sha256=runtime["progress_sha256"],
                repository_snapshot_sha256=
                    kblib.repository_snapshot_sha256(self.root),
                authorized_profile_view=authorized_view,
            ))

        self.dimension_receipts = {}
        records = [corpus_receipt]
        for index, (dimension, evidence_ref) in enumerate((
                ("structure_and_links", None),
                ("content_and_depth", None),
                ("coverage_and_integration", self.receipt_id),
                ("guidance_and_contract", corpus_receipt["receipt_id"]),
        ), start=1):
            record = kblib.make_receipt(
                "manual-attestation", "1.0.0", "audit_dimension",
                "frozen snapshot", "pass",
                "fixture %s verdict for the frozen snapshot" % dimension,
                index)
            record["dimension"] = dimension
            if evidence_ref is not None:
                record["evidence_ref"] = evidence_ref
            self.dimension_receipts[dimension] = record["receipt_id"]
            records.append(record)
        kblib.write_receipts(register, records)

        proof = kblib.parse_yaml_subset(TEMPLATE.read_text(encoding="utf-8"))
        proof.update({
            "task_id": queue["task_id"],
            "scope_version": contract["scope_version"],
            "contract_version": contract["contract_version"],
            "coverage_ledger_sha256": runtime["coverage_sha256"],
            "progress_ledger_sha256": runtime["progress_sha256"],
            "required_queue_path": check_proof.CANONICAL_QUEUE_PATH,
            "queue_revision": queue["queue_revision"],
            "queue_state_revision": queue["state_revision"],
            "required_queue_sha256": runtime["queue_sha256"],
            "remaining_required_work_units": runtime["remaining"],
            "queue_check_receipt": self.receipt_id,
            "corpus_plan_check_receipt": corpus_receipt["receipt_id"],
            "standards_version": contract["standards_version"],
            "selected_profile_manifest": self.profile_manifest,
            **self.terminal_load_contract,
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
                "coverage_and_integration": [
                    self.dimension_receipts["coverage_and_integration"]],
                "guidance_and_contract": [
                    self.dimension_receipts["guidance_and_contract"]],
                "formula_and_numeric":
                    "not-applicable: the frozen fixture scope states no "
                    "formula, symbol, numeric example, or metric provenance",
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
            kblib.canonical_yaml(proof), encoding="utf-8")

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
        expected_profile = check_proof.check_profile.evaluate_profile_load(
            self.root / "profiles/test-profile",
            root=self.root,
            receipt_identity=None,
        )
        self.assertTrue(expected_profile.authorized,
                        expected_profile.findings)
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
        self.assertEqual(
            expected_profile.profile_snapshot_sha256,
            receipt["profile_snapshot_sha256"],
        )
        self.assertEqual(
            expected_profile.profile_contract_fingerprint,
            receipt["profile_contract_fingerprint"],
        )
        self.assertEqual(
            expected_profile.profile_load_inputs_sha256,
            receipt["profile_load_inputs_sha256"],
        )
        self.assertEqual(
            kblib.repository_snapshot_sha256(self.root),
            receipt["repository_snapshot_sha256"],
        )
        for field in ("profile_snapshot_sha256",
                      "profile_contract_fingerprint",
                      "profile_load_inputs_sha256",
                      "repository_snapshot_sha256"):
            self.assertRegex(receipt[field], r"\Asha256:[0-9a-f]{64}\Z")

    def test_terminal_proof_runs_profile_load_producer_once(self):
        """Every consumer shares the one entry Profile authorization."""
        real_evaluate = check_proof.check_profile.evaluate_profile_load
        argv = [
            str(SCRIPT), str(self.proof_path),
            "--root", str(self.root),
            "--progress-ledger", check_proof.CANONICAL_PROGRESS_PATH,
            "--ledger", check_proof.CANONICAL_COVERAGE_PATH,
        ]
        output = io.StringIO()
        with mock.patch.object(
                check_proof.check_profile, "evaluate_profile_load",
                wraps=real_evaluate) as evaluate, \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(output):
            exit_code = check_proof.main()

        self.assertEqual(0, exit_code, output.getvalue())
        self.assertEqual(1, evaluate.call_count)

    def test_failed_profile_load_is_not_retried_by_corpus_consumer(self):
        """A failed entry producer remains one fail-closed observation."""
        registry = self.root / "profiles/test-profile/slots.md"
        registry.write_text(
            registry.read_text(encoding="utf-8").replace(
                "## Extension Dimensions\n",
                "## Broken Extension Dimensions\n", 1),
            encoding="utf-8")
        real_evaluate = check_proof.check_profile.evaluate_profile_load
        argv = [
            str(SCRIPT), str(self.proof_path),
            "--root", str(self.root),
            "--progress-ledger", check_proof.CANONICAL_PROGRESS_PATH,
            "--ledger", check_proof.CANONICAL_COVERAGE_PATH,
        ]
        output = io.StringIO()
        with mock.patch.object(
                check_proof.check_profile, "evaluate_profile_load",
                wraps=real_evaluate) as evaluate, \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(output):
            exit_code = check_proof.main()

        self.assertEqual(1, exit_code, output.getvalue())
        self.assertEqual(1, evaluate.call_count)
        self.assertIn(
            "proof-corpus-plan-profile-view-unavailable", output.getvalue())

    def test_profile_change_after_shared_evaluation_fails_currency_check(self):
        """Cached dimensions cannot mask Profile drift before the summary."""
        evaluation = check_proof.check_profile.evaluate_profile_load(
            self.root / "profiles/test-profile",
            root=self.root,
            receipt_identity=None,
        )
        self.assertTrue(evaluation.authorized, evaluation.findings)
        dimensions_before = check_proof._registered_receipt_dimensions(
            evaluation)
        self.assertTrue(dimensions_before[2], dimensions_before[3])

        registry = self.root / "profiles/test-profile/slots.md"
        registry.write_text(
            registry.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )

        # Enumeration still refers to the one authorized in-memory contract;
        # the final currency boundary then refuses to summarize it as current.
        self.assertEqual(
            dimensions_before,
            check_proof._registered_receipt_dimensions(evaluation),
        )
        failures = check_proof._profile_load_currency_failures(
            self.root, evaluation)
        self.assertEqual(
            ["proof-profile-snapshot-stale"],
            [failure[0] for failure in failures],
        )

    def test_profile_load_input_change_after_evaluation_fails_currency_check(self):
        """A stable Profile tree cannot hide changed root-owned load policy."""
        evaluation = check_proof.check_profile.evaluate_profile_load(
            self.root / "profiles/test-profile",
            root=self.root,
            receipt_identity=None,
        )
        self.assertTrue(evaluation.authorized, evaluation.findings)
        interface = self.root / check_proof.check_profile.DEFAULT_INTERFACE
        interface.write_text(
            interface.read_text(encoding="utf-8") +
            "\nCanonical interface revision B.\n",
            encoding="utf-8",
        )
        self.assertEqual(
            evaluation.profile_snapshot_sha256,
            kblib.repository_tree_sha256(
                self.root, evaluation.contract.profile_repo_dir),
        )
        failures = check_proof._profile_load_currency_failures(
            self.root, evaluation)
        self.assertEqual(
            ["proof-profile-load-inputs-stale"],
            [failure[0] for failure in failures],
        )

    def test_profile_a_b_a_during_terminal_run_cannot_publish_pass(self):
        """A restored A cannot erase runtime's observation of revision B."""
        real_evaluate = check_proof.check_profile.evaluate_profile_load
        real_validate = check_proof.check_queue.validate_runtime
        registry = self.root / "profiles/test-profile/slots.md"
        revision_a = registry.read_text(encoding="utf-8")

        def validate_during_revision_b(*args, **kwargs):
            registry.write_text(
                revision_a + "\n<!-- transient valid revision B -->\n",
                encoding="utf-8")
            try:
                return real_validate(*args, **kwargs)
            finally:
                registry.write_text(revision_a, encoding="utf-8")

        receipt_relative = ".cambium/receipts/toctou-proof-check.jsonl"
        argv = [
            str(SCRIPT), str(self.proof_path),
            "--root", str(self.root),
            "--progress-ledger", check_proof.CANONICAL_PROGRESS_PATH,
            "--ledger", check_proof.CANONICAL_COVERAGE_PATH,
            "--receipts", receipt_relative,
        ]
        output = io.StringIO()
        with mock.patch.object(
                check_proof.check_profile, "evaluate_profile_load",
                wraps=real_evaluate) as evaluate, \
                mock.patch.object(
                    check_proof.check_queue, "validate_runtime",
                    side_effect=validate_during_revision_b), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(output):
            exit_code = check_proof.main()

        self.assertEqual(1, exit_code, output.getvalue())
        self.assertEqual(1, evaluate.call_count)
        self.assertEqual(revision_a, registry.read_text(encoding="utf-8"))
        records = [
            json.loads(line) for line in
            (self.root / receipt_relative).read_text(
                encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertIn(
            "proof-queue-live-check-failed",
            [record["check"] for record in records],
        )
        self.assertFalse(any(
            record["check"] == "proof-check-summary" and
            record["result"] == "pass"
            for record in records
        ))

    def test_changes_after_consumers_fail_final_currency_cas(self):
        """The summary boundary rejects repo and state drift after reads."""
        real_evaluate = check_proof.check_profile.evaluate_profile_load
        real_corpus_linkage = check_proof._validate_corpus_plan_linkage
        registry = self.root / "profiles/test-profile/slots.md"

        def mutate_after_corpus(*args, **kwargs):
            result = real_corpus_linkage(*args, **kwargs)
            registry.write_text(
                registry.read_text(encoding="utf-8") +
                "\n<!-- post-consumer revision B -->\n",
                encoding="utf-8")
            progress = self.root / check_proof.CANONICAL_PROGRESS_PATH
            progress.write_text(
                progress.read_text(encoding="utf-8") + "\n",
                encoding="utf-8")
            return result

        receipt_relative = ".cambium/receipts/final-cas-proof-check.jsonl"
        argv = [
            str(SCRIPT), str(self.proof_path),
            "--root", str(self.root),
            "--progress-ledger", check_proof.CANONICAL_PROGRESS_PATH,
            "--ledger", check_proof.CANONICAL_COVERAGE_PATH,
            "--receipts", receipt_relative,
        ]
        output = io.StringIO()
        with mock.patch.object(
                check_proof.check_profile, "evaluate_profile_load",
                wraps=real_evaluate) as evaluate, \
                mock.patch.object(
                    check_proof, "_validate_corpus_plan_linkage",
                    side_effect=mutate_after_corpus), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(output):
            exit_code = check_proof.main()

        self.assertEqual(1, exit_code, output.getvalue())
        self.assertEqual(1, evaluate.call_count)
        records = [
            json.loads(line) for line in
            (self.root / receipt_relative).read_text(
                encoding="utf-8").splitlines() if line.strip()
        ]
        checks = [record["check"] for record in records]
        self.assertIn("proof-profile-view-stale", checks)
        self.assertIn("proof-runtime-state-stale", checks)
        self.assertIn("proof-repository-snapshot-stale", checks)
        self.assertNotIn("proof-check-summary", checks)

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
        failures, passed = check_proof._validate_corpus_plan_linkage(
            self.root, proof, proof["progress_ledger_sha256"],
            runtime=filtered,
            authorized_profile_view=runtime["_profile_authorized_view"],
            repository_snapshot_sha256=
                kblib.repository_snapshot_sha256(self.root))
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
        receipt_id = (
            "audit-manual-attestation-20260804T000000Z-"
            "99999999999999999999999999999999-0001")
        # Keep the ID current in the repository-wide catalog while omitting it
        # from the Proof's declared register, so this isolates the register
        # membership contract from the separate current-evidence contract.
        current_record = {
            "receipt_id": receipt_id,
            "tool": "manual-attestation",
            "tool_version": "1.0.0",
            "check": "audit_dimension",
            "target": "frozen snapshot",
            "result": "pass",
            "details": "fixture register-membership isolation",
            "dimension": "formula_and_numeric",
            "invalidated_by": None,
        }
        (self.root / ".cambium/receipts/current-outside-proof.jsonl").write_text(
            json.dumps(current_record, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.rewrite_dimension_coverage(
            lambda coverage: coverage.__setitem__(
                "formula_and_numeric", [receipt_id]))
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

    REGISTRY_TABLE_HEADER = (
        "| Dimension ID | Target list(s): `review`, `receipt`, or "
        "`review + receipt` | Meaning |\n|---|---|---|\n"
    )

    def rebind_corpus_plan_receipt(self):
        """Re-take the Corpus Planning receipt against the edited tree.

        Editing a profile file changes the frozen repository snapshot and the
        slot bytes that receipt binds, so without this every registry test
        would fail on Corpus Planning currency instead of on the behaviour
        under test.
        """
        def rebind(record):
            record.update(
                check_proof.check_corpus_plan.current_freshness_binding(
                    self.root, self.profile_manifest,
                    task_id=record["task_id"],
                    queue_revision=record["queue_revision"],
                    queue_state_revision=record["queue_state_revision"],
                    coverage_ledger_sha256=record["coverage_ledger_sha256"],
                    required_queue_sha256=record["required_queue_sha256"],
                    progress_ledger_sha256=record["progress_ledger_sha256"],
                    repository_snapshot_sha256=(
                        kblib.repository_snapshot_sha256(self.root)),
                ))

        self.rewrite_register_record(self.corpus_receipt_id, rebind)

    def rebind_profile_execution_receipts(self, authorized_view):
        """Re-take current runtime receipts against an authorized Profile edit.

        Extension-dimension tests intentionally revise the selected Profile
        after the completed-runtime fixture was built.  Current batch-close
        1.11 evidence and queue transitions bind that exact Profile revision,
        so update every already-profile-bound fixture receipt before testing
        the Terminal Proof obligation introduced by the new registration.
        """
        fields = (
            "selected_profile_manifest", "profile_snapshot_sha256",
            "profile_contract_fingerprint", "profile_load_inputs_sha256",
        )
        rebound = 0
        for register in sorted(
                (self.root / ".cambium/receipts").rglob("*.jsonl")):
            records = [
                json.loads(line)
                for line in register.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            changed = False
            for record in records:
                if not any(field in record for field in fields):
                    continue
                for field in fields:
                    if field in record:
                        record[field] = authorized_view[field]
                rebound += 1
                changed = True
            if changed:
                register.write_text("".join(
                    json.dumps(record, sort_keys=True) + "\n"
                    for record in records), encoding="utf-8")
        self.assertGreater(rebound, 0)

    def rewrite_extension_dimensions(self, block):
        """Replace the selected profile's Extension Dimensions registration.

        The typed Profile contract now carries Judgment Items and Scan
        Registrations in the same fixture file.  Replace only this H2 block;
        `block` of None removes it while preserving the other dependencies.
        """
        registry = self.root / "profiles/test-profile/slots.md"
        head, marker, remainder = registry.read_text(
            encoding="utf-8").partition("## Extension Dimensions\n")
        self.assertTrue(marker, "fixture slot file has no registration block")
        _old_block, next_heading, tail = remainder.partition(
            "\n## Judgment Items\n")
        self.assertTrue(next_heading, "fixture slot file has no Judgment Items")
        registry.write_text(
            head + ("" if block is None else marker + block) +
            next_heading + tail,
            encoding="utf-8")
        # A valid Profile revision needs a current Corpus receipt so extension
        # dimension tests isolate the Terminal obligation.  Deliberately
        # invalid revisions cannot produce that binding; leave the old receipt
        # stale and let the one Terminal profile-load report the root failure.
        authorized_view, _errors = \
            check_proof.check_queue.profile_load_authorized_view(
                self.root, self.profile_manifest)
        if authorized_view is not None:
            self.rebind_profile_execution_receipts(authorized_view)
            self.rebind_corpus_plan_receipt()

    def register_extension_dimension(self, targets="`review + receipt`"):
        """Register one profile-owned dimension the way a real profile does."""
        self.rewrite_extension_dimensions(
            "\n- Registration: Configured\n\n" + self.REGISTRY_TABLE_HEADER +
            "| `glossary` | %s | Fitness of the profile's terminology "
            "pages against its registered glossary contract. |\n" % targets)

    def append_dimension_record(self, dimension):
        """Append one passing AuditReceipt for `dimension` to the register."""
        record = kblib.make_receipt(
            "manual-attestation", "1.0.0", "audit_dimension",
            "frozen snapshot", "pass",
            "fixture %s verdict for the frozen snapshot" % dimension, 9)
        record["dimension"] = dimension
        register = self.root / ".cambium/receipts/terminal.jsonl"
        with register.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record["receipt_id"]

    def test_registered_receipt_dimension_omitted_from_the_proof_fails(self):
        """K12/16: a registered `receipt` dimension is not optional.

        The defect this closes: the profile registers a dimension, judgment
        items emit into it, and a Terminal Proof that never mentions it passes
        because the checker only ever iterated the base seven.
        """
        self.register_extension_dimension()
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-missing", result.stdout)
        self.assertIn("glossary", result.stdout)

    def test_registered_receipt_dimension_accounted_for_passes(self):
        """The obligation is dischargeable by receipts, like the base seven."""
        self.register_extension_dimension()
        receipt_id = self.append_dimension_record("glossary")
        self.rewrite_dimension_coverage(
            lambda coverage: coverage.__setitem__("glossary", [receipt_id]))
        result = self.run_proof()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_registered_dimension_declared_not_applicable_passes(self):
        self.register_extension_dimension()
        self.rewrite_dimension_coverage(
            lambda coverage: coverage.__setitem__(
                "glossary",
                "not-applicable: the frozen fixture scope holds no "
                "terminology page"))
        result = self.run_proof()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_registered_dimension_receipt_still_resolves_by_dimension(self):
        """A registered dimension reuses the base evidence rules unchanged."""
        self.register_extension_dimension()
        self.rewrite_dimension_coverage(
            lambda coverage: coverage.__setitem__(
                "glossary",
                [self.dimension_receipts["structure_and_links"]]))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-mismatch", result.stdout)

    def test_review_only_registration_owes_the_proof_no_entry(self):
        """Only a `receipt` target produces receipts to account for."""
        self.register_extension_dimension(targets="`review`")
        result = self.run_proof()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_review_only_dimension_cannot_supply_terminal_receipt(self):
        """The registry, not an ad-hoc Proof key, grants receipt authority."""
        self.register_extension_dimension(targets="`review`")
        receipt_id = self.append_dimension_record("glossary")
        self.rewrite_dimension_coverage(
            lambda coverage: coverage.__setitem__("glossary", [receipt_id]))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-review-only", result.stdout)

    def test_review_only_dimension_may_use_explicit_na_declaration(self):
        """K12/16 permits the key but grants it no receipt target."""
        self.register_extension_dimension(targets="`review`")
        self.rewrite_dimension_coverage(
            lambda coverage: coverage.__setitem__(
                "glossary",
                "not-applicable: the frozen scope has no terminology page"))
        result = self.run_proof()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_unregistered_extension_dimension_fails_closed(self):
        """Terminal Proof cannot invent a Profile extension dimension."""
        self.rewrite_dimension_coverage(
            lambda coverage: coverage.__setitem__(
                "invented_dimension",
                "not-applicable: no object in the frozen fixture scope"))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-unregistered", result.stdout)

    def test_registration_colliding_with_a_base_dimension_fails(self):
        """K12/07: the registry appends dimensions, it never redefines one."""
        self.rewrite_extension_dimensions(
            "\n- Registration: Configured\n\n" + self.REGISTRY_TABLE_HEADER +
            "| `rendering` | `review + receipt` | A second, profile-owned "
            "meaning for a base dimension name. |\n")
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("extension-dimension-base-collision",
                      result.stdout)
        self.assertIn("rendering", result.stdout)

    def test_registry_without_a_registration_block_fails_closed(self):
        """The silent-empty case: no block must not read as "registers none".

        Profile admission and Terminal Proof share one parser, so the malformed
        registry is rejected both when the profile loads and when the Proof
        tries to enumerate its receipt obligations.
        """
        self.rewrite_extension_dimensions(None)
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            "extension-dimensions-section-count", result.stdout)
        self.assertIn("proof-profile-not-loadable", result.stdout)

    def test_unreadable_target_list_fails_closed(self):
        """An unreadable target list leaves the obligation undecidable."""
        self.register_extension_dimension(targets="`review + audit`")
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            "extension-dimension-target-invalid", result.stdout)

    def test_registration_value_outside_the_interface_fails_closed(self):
        """Only `None` or `Configured` states what is registered."""
        self.rewrite_extension_dimensions(
            "\n- Registration: Not applicable — nothing to register\n\n" +
            self.REGISTRY_TABLE_HEADER)
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            "extension-dimensions-registration", result.stdout)

    def rewrite_register_record(self, receipt_id, mutate):
        """Apply one mutation to a record of the Audit Receipt Register."""
        register = self.root / ".cambium/receipts/terminal.jsonl"
        records = [json.loads(line) for line in register.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        matched = False
        for record in records:
            if record.get("receipt_id") == receipt_id:
                mutate(record)
                matched = True
        self.assertTrue(matched, receipt_id)
        register.write_text("".join(
            json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8")

    def test_invalidated_dimension_receipt_fails_closed(self):
        self.rewrite_register_record(
            self.dimension_receipts["content_and_depth"],
            lambda record: record.__setitem__(
                "invalidated_by", "audit-superseding-review"))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-invalidated", result.stdout)

    def test_standards_adoption_invalidated_dimension_receipt_fails_closed(self):
        """Immutable history cannot authorize a post-adoption Proof.

        This models the exact current view produced by a completed Standards
        adoption: the receipt remains in the historical catalog, while the
        adoption record removes it from current evidence and names its ID in
        the invalidation set.
        """
        receipt_id = self.dimension_receipts["content_and_depth"]
        runtime = check_proof.check_queue.validate_runtime(self.root)
        historical = dict(
            check_proof.check_queue.historical_receipt_catalog(runtime))
        self.assertIn(receipt_id, historical)
        filtered = dict(runtime)
        filtered["receipt_catalog"] = historical
        filtered["current_receipt_catalog"] = {
            key: value for key, value in historical.items()
            if key != receipt_id
        }
        filtered["invalidated_evidence_receipt_ids"] = [receipt_id]
        proof = kblib.load_yaml_file(self.proof_path)
        failures = check_proof._validate_dimension_coverage_evidence(
            self.root, proof, {receipt_id: "content_and_depth"},
            runtime=filtered,
        )
        self.assertIn(
            "proof-dimension-receipt-invalidated-evidence",
            [failure[0] for failure in failures],
        )

    def test_dimension_receipt_without_a_dimension_field_fails_closed(self):
        """Absence must not be read as agreement with the citing dimension."""
        self.rewrite_register_record(
            self.dimension_receipts["content_and_depth"],
            lambda record: record.pop("dimension"))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-mismatch", result.stdout)
        self.assertIn("content_and_depth", result.stdout)

    def test_dimensionless_receipt_cannot_be_moved_to_another_dimension(self):
        """The exact bypass: strip `dimension`, then cite it elsewhere."""
        self.rewrite_register_record(
            self.dimension_receipts["content_and_depth"],
            lambda record: record.pop("dimension"))

        def move_content_receipt(coverage):
            coverage["content_and_depth"] = (
                "not-applicable: moved for this fixture")
            coverage["formula_and_numeric"] = [
                self.dimension_receipts["content_and_depth"]]

        self.rewrite_dimension_coverage(move_content_receipt)
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-mismatch", result.stdout)

    def test_failed_dimension_receipt_cannot_carry_a_dimension(self):
        """A recorded failure verdict is not completion evidence."""
        self.rewrite_register_record(
            self.dimension_receipts["structure_and_links"],
            lambda record: record.__setitem__("result", "fail"))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-not-passed", result.stdout)
        self.assertIn("structure_and_links", result.stdout)

    def test_candidate_dimension_receipt_fails_closed(self):
        self.rewrite_register_record(
            self.dimension_receipts["structure_and_links"],
            lambda record: record.__setitem__("result", "candidate"))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-not-passed", result.stdout)

    def test_dimension_receipt_without_a_result_fails_closed(self):
        self.rewrite_register_record(
            self.dimension_receipts["structure_and_links"],
            lambda record: record.pop("result"))
        result = self.run_proof()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("proof-dimension-receipt-not-passed", result.stdout)

    def test_k12_07_passed_spelling_is_accepted(self):
        """The AuditReceipt shape writes `passed`; it is a passing verdict."""
        self.rewrite_register_record(
            self.dimension_receipts["structure_and_links"],
            lambda record: record.__setitem__("result", "passed"))
        result = self.run_proof()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

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
            "receipt_catalog": current_catalog,
            "invalidated_evidence_receipt_ids": invalidated_ids or [],
            "errors": runtime_errors or [],
            "writer_locks": [],
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
        failures, live_passed = self.validate(
            runtime_errors=["fixture runtime invalid"])
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

    def test_missing_shared_runtime_fails_closed_without_rerun(self):
        failures, live_passed = \
            check_proof._validate_required_queue_linkage(
                self.root, self.proof, self.progress,
                self.coverage_sha, self.progress_sha, runtime=None)
        self.assertFalse(live_passed)
        self.assertIn("proof-required-queue-runtime-unavailable",
                      self.checks(failures))


if __name__ == "__main__":
    unittest.main()
