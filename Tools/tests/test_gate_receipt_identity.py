import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import check_links
import check_batch_close
import check_corpus_plan
import check_proof
import check_queue
import check_residual_content
import check_vocab
import adopt_standards
import record_corpus_acceptance


class DeterministicGateReceiptIdentityTests(unittest.TestCase):
    def test_producer_constants_match_stable_gate_registry(self):
        repository_root = TOOLS_DIR.parent
        registry, errors = check_queue.standards_gate_registry(repository_root)
        self.assertEqual([], errors)
        expected = {
            check_links.GATE_ID: {
                "tool": check_links.TOOL,
                "tool_version": check_links.TOOL_VERSION,
                "check": "link-check-summary",
                "mode": "*",
            },
            check_vocab.GATE_ID: {
                "tool": check_vocab.TOOL,
                "tool_version": check_vocab.TOOL_VERSION,
                "check": "vocab-check-summary",
                "mode": "*",
            },
            check_residual_content.GATE_ID: {
                "tool": check_residual_content.TOOL,
                "tool_version": check_residual_content.TOOL_VERSION,
                "check": "residual-content-summary",
                "mode": "*",
            },
            check_batch_close.GATE_ID: {
                "tool": check_batch_close.TOOL,
                "tool_version": check_batch_close.TOOL_VERSION,
                "check": "batch_close_gate",
                "mode": "*",
            },
            check_proof.GATE_ID: {
                "tool": check_proof.TOOL,
                "tool_version": check_proof.TOOL_VERSION,
                "check": "proof-check-summary",
                "mode": "*",
            },
            adopt_standards.GATE_ID: {
                "tool": adopt_standards.TOOL,
                "tool_version": adopt_standards.TOOL_VERSION,
                "check": "standards_adoption",
                "mode": "*",
            },
            "corpus-plan-structure": {
                "tool": check_corpus_plan.TOOL,
                "tool_version": check_corpus_plan.TOOL_VERSION,
                "check": "corpus_plan",
                "mode": "*",
            },
            "corpus-plan-semantic-acceptance": {
                "tool": record_corpus_acceptance.TOOL,
                "tool_version": record_corpus_acceptance.TOOL_VERSION,
                "check": "corpus_plan_semantic_acceptance",
                "mode": "*",
            },
            check_queue.BATCH_REVIEW_GATE_ID: {
                "tool": check_queue.MANUAL_ATTESTATION_TOOL,
                "tool_version":
                    check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
                "check": check_queue.BATCH_REVIEW_CHECK,
                "mode": "*",
            },
        }
        for gate_id, predicate in expected.items():
            self.assertEqual(predicate, registry.get(gate_id), gate_id)

    def test_registered_gate_rejects_wrong_tool_version(self):
        registry, errors = check_queue.standards_gate_registry(
            TOOLS_DIR.parent)
        self.assertEqual([], errors)
        receipt = {
            "gate_id": "required-queue-consistency",
            "tool": check_queue.TOOL,
            "tool_version": "0.0.0",
            "check": "required_queue",
            "queue_check_mode": "consistency",
        }
        self.assertFalse(check_queue.receipt_matches_gate_id(
            receipt, "required-queue-consistency", registry))
        receipt["tool_version"] = check_queue.TOOL_VERSION
        self.assertTrue(check_queue.receipt_matches_gate_id(
            receipt, "required-queue-consistency", registry))

    def test_registry_rejects_wildcard_producer_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry_path = root / check_queue.STANDARDS_GATE_REGISTRY_PATH
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text(
                "## Stable Gate ID Registry\n\n"
                "| Gate ID | Tool | Tool version | Check | Mode |\n"
                "|---|---|---|---|---|\n"
                "| unsafe | * | * | * | * |\n",
                encoding="utf-8",
            )
            registry, errors = check_queue.standards_gate_registry(root)
        self.assertEqual({}, registry)
        self.assertTrue(any("must be exact" in error for error in errors),
                        errors)

    def test_current_batch_review_cannot_wrap_absent_page_evidence(self):
        wrapper_id = "audit-batch-review"
        wrapper = {
            "receipt_id": wrapper_id,
            "tool": check_queue.MANUAL_ATTESTATION_TOOL,
            "tool_version": check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
            "gate_id": check_queue.BATCH_REVIEW_GATE_ID,
            "check": check_queue.BATCH_REVIEW_CHECK,
            "target": "B1", "task_id": "fixture-task", "batch_id": "B1",
            "delta_page_receipt_ids": ["audit-invalidated-page"],
            "result": "pass", "invalidated_by": None,
        }
        errors = check_queue.batch_review_receipt_errors(
            {wrapper_id: ("current.jsonl", wrapper)}, wrapper_id,
            item_id="B1", task_id="fixture-task",
            delta_page_receipt_ids=["audit-invalidated-page"],
        )
        self.assertTrue(any("references missing receipt "
                            "audit-invalidated-page" in error
                            for error in errors), errors)

    def run_tool(self, script, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS_DIR / script), *map(str, arguments)],
            text=True, capture_output=True, check=False,
        )

    def receipt_rows(self, path):
        return [json.loads(line) for line in path.read_text(
            encoding="utf-8").splitlines()]

    def assert_producer_identity(self, rows, tool, version, gate_id):
        self.assertTrue(rows)
        self.assertEqual({tool}, {row.get("tool") for row in rows})
        self.assertEqual({version}, {row.get("tool_version") for row in rows})
        self.assertEqual({gate_id}, {row.get("gate_id") for row in rows})

    def test_check_links_receipts_bind_registered_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Page.md").write_text("# Page\n", encoding="utf-8")
            receipts = root / "links.jsonl"
            completed = self.run_tool(
                "check_links.py", root, "--receipts", receipts)
            self.assertEqual(0, completed.returncode,
                             completed.stdout + completed.stderr)
            rows = self.receipt_rows(receipts)
            self.assertEqual("link-check-summary", rows[-1]["check"])
            self.assert_producer_identity(
                rows, check_links.TOOL, check_links.TOOL_VERSION,
                check_links.GATE_ID)

    def test_check_vocab_receipts_bind_registered_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Page.md").write_text(
                "---\npriority: P0\n---\n\n# Page\n", encoding="utf-8")
            vocab = root / "vocab.yaml"
            vocab.write_text(
                "fields:\n"
                "  priority:\n"
                "    values:\n"
                "      - P0\n"
                "    owner: fixture\n",
                encoding="utf-8",
            )
            receipts = root / "vocab.jsonl"
            completed = self.run_tool(
                "check_vocab.py", root, "--vocab", vocab,
                "--quota-p0", "100", "--quota-p1", "100",
                "--receipts", receipts)
            self.assertEqual(0, completed.returncode,
                             completed.stdout + completed.stderr)
            rows = self.receipt_rows(receipts)
            self.assertEqual("vocab-check-summary", rows[-1]["check"])
            self.assert_producer_identity(
                rows, check_vocab.TOOL, check_vocab.TOOL_VERSION,
                check_vocab.GATE_ID)

    def test_residual_receipts_bind_registered_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = root / "Content"
            content.mkdir()
            (content / "Page.md").write_text("# Page\n", encoding="utf-8")
            (root / "Other.md").write_text("# Other\n", encoding="utf-8")
            config = root / "residual.yaml"
            config.write_text(
                "residual_scan_config_version: 1\n"
                "allowed_roots:\n"
                "  - Content\n"
                "excluded_roots: []\n"
                "frontmatter_match:\n"
                "  field: type\n"
                "  values:\n"
                "    - interview-card\n"
                "heading_match:\n"
                "  any:\n"
                "    - Interview Card\n"
                "  combination:\n"
                "    - Question\n"
                "    - Answer\n"
                "  minimum_distinct: 2\n",
                encoding="utf-8",
            )
            receipts = root / "residual.jsonl"
            completed = self.run_tool(
                "check_residual_content.py", root,
                "--scan-id", "fixture-residual", "--config", config,
                "--receipts", receipts)
            self.assertEqual(0, completed.returncode,
                             completed.stdout + completed.stderr)
            rows = self.receipt_rows(receipts)
            self.assertEqual("residual-content-summary", rows[-1]["check"])
            self.assert_producer_identity(
                rows, check_residual_content.TOOL,
                check_residual_content.TOOL_VERSION,
                check_residual_content.GATE_ID)

    def test_check_proof_failure_receipt_binds_registered_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipts = root / "proof.jsonl"
            completed = self.run_tool(
                "check_proof.py", root / "missing-proof.yaml",
                "--receipts", receipts)
            self.assertEqual(1, completed.returncode,
                             completed.stdout + completed.stderr)
            rows = self.receipt_rows(receipts)
            self.assertEqual("proof-unreadable", rows[0]["check"])
            self.assert_producer_identity(
                rows, check_proof.TOOL, check_proof.TOOL_VERSION,
                check_proof.GATE_ID)


if __name__ == "__main__":
    unittest.main()
