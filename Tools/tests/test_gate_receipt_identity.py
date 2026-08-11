import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
RUNTIME_FIXTURE = TOOLS_DIR / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS_DIR))

import check_links
import check_batch_close
import check_boundary_contract
import check_corpus_plan
import check_proof
import check_queue
import check_page_contract
import check_profile
import check_residual_content
import check_structure
import check_vocab
import adopt_standards
import kblib
import record_corpus_acceptance

# K12/18 files these two Gates' canonical judgment items under more than one
# receipt dimension, so K00/12 registers every one of them.
DIMENSIONS = {
    "source-promotion": ("coverage_and_integration", "source_and_currentness"),
    "expression-layer-acceptance": (
        "content_and_depth", "coverage_and_integration",
        "guidance_and_contract", "source_and_currentness",
        "structure_and_links"),
}
# The K00/12 `Lifecycle` cell for a Gate whose producer takes no batch, so no
# batch position can make it unproducible.
NOT_BATCH_SCOPED = check_queue.NOT_BATCH_SCOPED_GATE
# The cell for a Gate reachable only once the Queue holds no non-terminal
# batch, which is ahead of every live batch and behind none.
QUEUE_EXHAUSTED = check_queue.QUEUE_EXHAUSTED_GATE


class DeterministicGateReceiptIdentityTests(unittest.TestCase):
    def test_producer_constants_match_stable_gate_registry(self):
        repository_root = TOOLS_DIR.parent
        registry, errors = check_queue.standards_gate_registry(repository_root)
        self.assertEqual([], errors)
        expected = {
            check_profile.GATE_ID: {
                "tool": check_profile.TOOL,
                "tool_version": check_profile.TOOL_VERSION,
                "check": check_profile.GATE_CHECK,
                "mode": "*",
                "dimensions": (check_profile.GATE_DIMENSION,),
                "lifecycle_states": (NOT_BATCH_SCOPED,),
            },
            check_links.GATE_ID: {
                "tool": check_links.TOOL,
                "tool_version": check_links.TOOL_VERSION,
                "check": "link-check-summary",
                "mode": "*",
                "dimensions": ("*",),
                "lifecycle_states": (NOT_BATCH_SCOPED,),
            },
            check_vocab.GATE_ID: {
                "tool": check_vocab.TOOL,
                "tool_version": check_vocab.TOOL_VERSION,
                "check": "vocab-check-summary",
                "mode": "*",
                "dimensions": ("*",),
                "lifecycle_states": (NOT_BATCH_SCOPED,),
            },
            check_residual_content.GATE_ID: {
                "tool": check_residual_content.TOOL,
                "tool_version": check_residual_content.TOOL_VERSION,
                "check": "residual-content-summary",
                "mode": "*",
                "dimensions": ("*",),
                "lifecycle_states": (NOT_BATCH_SCOPED,),
            },
            check_batch_close.GATE_ID: {
                "tool": check_batch_close.TOOL,
                "tool_version": check_batch_close.TOOL_VERSION,
                "check": "batch_close_gate",
                "mode": "*",
                "dimensions": ("*",),
                # `check_batch_close` refuses a batch that is not
                # `merge-ready`, so no other position can produce this Gate.
                "lifecycle_states": ("merge-ready",),
            },
            check_proof.GATE_ID: {
                "tool": check_proof.TOOL,
                "tool_version": check_proof.TOOL_VERSION,
                "check": "proof-check-summary",
                "mode": "*",
                "dimensions": ("*",),
                # `check_proof` fails any non-zero
                # `remaining_required_work_units`, and cross-checks that field
                # against the live count of non-terminal Queue batches.
                "lifecycle_states": (QUEUE_EXHAUSTED,),
            },
            adopt_standards.GATE_ID: {
                "tool": adopt_standards.TOOL,
                "tool_version": adopt_standards.TOOL_VERSION,
                "check": "standards_adoption",
                "mode": "*",
                "dimensions": ("*",),
                "lifecycle_states": (NOT_BATCH_SCOPED,),
            },
            "corpus-plan-structure": {
                "tool": check_corpus_plan.TOOL,
                "tool_version": check_corpus_plan.TOOL_VERSION,
                "check": "corpus_plan",
                "mode": "*",
                "dimensions": ("*",),
                "lifecycle_states": (NOT_BATCH_SCOPED,),
            },
            "corpus-plan-semantic-acceptance": {
                "tool": record_corpus_acceptance.TOOL,
                "tool_version": record_corpus_acceptance.TOOL_VERSION,
                "check": "corpus_plan_semantic_acceptance",
                "mode": "*",
                "dimensions": ("*",),
                "lifecycle_states": (NOT_BATCH_SCOPED,),
            },
            check_queue.BATCH_REVIEW_GATE_ID: {
                "tool": check_queue.MANUAL_ATTESTATION_TOOL,
                "tool_version":
                    check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
                "check": check_queue.BATCH_REVIEW_CHECK,
                "mode": "*",
                # The wrapper binds member receipts that already carry the
                # verdicts, so K12/18 files it under no dimension at all.
                "dimensions": ("none",),
                # Only `open -> merge-ready` consumes it, and that edge
                # departs from `open`; the Delta page receipts it binds
                # exist nowhere else.
                "lifecycle_states": ("open",),
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
                "| Gate ID | Tool | Tool version | Check | Mode "
                "| Dimension | Lifecycle |\n"
                "|---|---|---|---|---|---|---|\n"
                "| unsafe | * | * | * | * | * | not-batch-scoped |\n",
                encoding="utf-8",
            )
            registry, errors = check_queue.standards_gate_registry(root)
        self.assertEqual({}, registry)
        self.assertTrue(any("must be exact" in error for error in errors),
                        errors)

    def parsed_registry(self, header, row):
        """Parse one synthetic Stable Gate ID Registry table."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry_path = root / check_queue.STANDARDS_GATE_REGISTRY_PATH
            registry_path.parent.mkdir(parents=True)
            separator = "|%s|" % "|".join(
                ["---"] * (header.count("|") - 1))
            registry_path.write_text(
                "## Stable Gate ID Registry\n\n%s\n%s\n%s\n" % (
                    header, separator, row),
                encoding="utf-8")
            return check_queue.standards_gate_registry(root)

    SIX_CELL_HEADER = ("| Gate ID | Tool | Tool version | Check | Mode "
                       "| Dimension |")
    SEVEN_CELL_HEADER = ("| Gate ID | Tool | Tool version | Check | Mode "
                         "| Dimension | Lifecycle |")

    def test_registry_rejects_a_row_without_the_lifecycle_cell(self):
        """A pre-column table is a parse failure, not a defaulted column."""
        registry, errors = self.parsed_registry(
            self.SIX_CELL_HEADER,
            "| wiki-link-integrity | check_links | 1.5.0 "
            "| link-check-summary | * | * |")
        self.assertEqual({}, registry)
        self.assertTrue(any("must have seven cells" in error
                            for error in errors), errors)

    def test_registry_rejects_an_unknown_lifecycle_value(self):
        """Only a batch lifecycle state or the not-batch-scoped marker."""
        registry, errors = self.parsed_registry(
            self.SEVEN_CELL_HEADER,
            "| wiki-link-integrity | check_links | 1.5.0 "
            "| link-check-summary | * | * | under-review |")
        self.assertEqual({}, registry)
        self.assertTrue(any(
            "registers Lifecycle under-review, which is neither a batch "
            "lifecycle state nor one of not-batch-scoped, queue-exhausted"
            in error for error in errors), errors)

    def test_registry_rejects_mixing_a_marker_with_another_position(self):
        """The three cell forms each answer the whole question alone."""
        for cell in ("not-batch-scoped, open", "queue-exhausted, merge-ready",
                     "not-batch-scoped, queue-exhausted"):
            with self.subTest(cell=cell):
                registry, errors = self.parsed_registry(
                    self.SEVEN_CELL_HEADER,
                    "| wiki-link-integrity | check_links | 1.5.0 "
                    "| link-check-summary | * | * | %s |" % cell)
                self.assertEqual({}, registry)
                self.assertTrue(any("mixes" in error and
                                    "with another position" in error
                                    for error in errors), errors)

    def test_registry_accepts_the_queue_exhausted_position(self):
        """A Queue-level position is a registrable cell, not an error."""
        registry, errors = self.parsed_registry(
            self.SEVEN_CELL_HEADER,
            "| wiki-link-integrity | check_links | 1.5.0 "
            "| link-check-summary | * | * | queue-exhausted |")
        self.assertEqual([], errors)
        self.assertEqual(("queue-exhausted",),
                         registry["wiki-link-integrity"]["lifecycle_states"])

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
            # The accepted root carries the known-residual sample the K12/09
            # item 6 non-triviality check reads as its positive control.
            (content / "Page.md").write_text(
                "---\ntype: interview-card\n---\n\n## Interview Card\n",
                encoding="utf-8")
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
                "  minimum_distinct: 2\n"
                "mandated_headings:\n"
                "  - Interview Card\n",
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

    def build_residual_corpus(self, root, residual_outside):
        """Lay out an accepted root plus optional residual content outside it."""
        content = root / "Content"
        content.mkdir()
        (content / "Card.md").write_text(
            "---\ntype: interview-card\n---\n\n## Interview Card\n",
            encoding="utf-8")
        (root / "Clean.md").write_text(
            "---\ntype: concept\n---\n\n## Body\n", encoding="utf-8")
        if residual_outside:
            (root / "Leftover.md").write_text(
                "---\ntype: interview-card\n---\n\n## Interview Card\n",
                encoding="utf-8")

    def write_residual_config(self, root, name, frontmatter_value, heading):
        config = root / name
        config.write_text(
            "residual_scan_config_version: 1\n"
            "allowed_roots:\n"
            "  - Content\n"
            "excluded_roots: []\n"
            "frontmatter_match:\n"
            "  field: type\n"
            "  values:\n"
            "    - %s\n"
            "heading_match:\n"
            "  any:\n"
            "    - %s\n"
            "  combination: []\n"
            "  minimum_distinct: 0\n"
            "mandated_headings:\n"
            "  - %s\n" % (frontmatter_value, heading, heading),
            encoding="utf-8",
        )
        return config

    def run_residual_scan(self, root, config, receipts):
        return self.run_tool(
            "check_residual_content.py", root,
            "--scan-id", "fixture-residual", "--config", config,
            "--receipts", receipts)

    def test_never_matching_matcher_cannot_report_a_clean_scan(self):
        """K12/09 item 6: an inert configuration is not scan evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.build_residual_corpus(root, residual_outside=True)
            config = self.write_residual_config(
                root, "inert.yaml", "zzz-never-emitted-type",
                "ZZZ Never Emitted Heading")
            receipts = root / "inert.jsonl"
            completed = self.run_residual_scan(root, config, receipts)
            self.assertEqual(1, completed.returncode,
                             completed.stdout + completed.stderr)
            rows = self.receipt_rows(receipts)
            self.assertEqual(
                ["residual-content-inert-matcher"],
                [row["check"] for row in rows if row["result"] == "fail"])
            self.assertNotIn(
                "residual-content-summary", [row["check"] for row in rows])
            self.assert_producer_identity(
                rows, check_residual_content.TOOL,
                check_residual_content.TOOL_VERSION,
                check_residual_content.GATE_ID)

    def test_honest_matcher_reports_the_same_corpus_as_candidates(self):
        """The control run: the honest configuration still finds the residue."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.build_residual_corpus(root, residual_outside=True)
            config = self.write_residual_config(
                root, "honest.yaml", "interview-card", "Interview Card")
            receipts = root / "honest.jsonl"
            completed = self.run_residual_scan(root, config, receipts)
            self.assertEqual(2, completed.returncode,
                             completed.stdout + completed.stderr)
            self.assertIn("Leftover.md", completed.stdout)
            rows = self.receipt_rows(receipts)
            self.assertEqual(
                [], [row["check"] for row in rows
                     if row["result"] == "fail"])
            summary = rows[-1]
            self.assertEqual("residual-content-summary", summary["check"])
            self.assertEqual("pass", summary["result"])
            self.assertEqual("passed", summary["positive_control_result"])
            self.assertEqual(
                "production-classifier", summary["positive_control_mode"])
            self.assertGreater(summary["positive_control_count"], 0)
            self.assertRegex(
                summary["positive_control_fingerprint"],
                r"\Asha256:[0-9a-f]{64}\Z")

    def test_explicit_positive_control_mode_matches_production_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.build_residual_corpus(root, residual_outside=True)
            config = self.write_residual_config(
                root, "honest.yaml", "interview-card", "Interview Card")
            control_receipts = root / "controls.jsonl"
            production_receipts = root / "production.jsonl"
            control = self.run_tool(
                "check_residual_content.py", root,
                "--scan-id", "fixture-residual", "--config", config,
                "--positive-controls-only", "--receipts", control_receipts)
            production = self.run_residual_scan(
                root, config, production_receipts)
            self.assertEqual(0, control.returncode,
                             control.stdout + control.stderr)
            self.assertEqual(2, production.returncode,
                             production.stdout + production.stderr)
            control_summary = self.receipt_rows(control_receipts)[-1]
            production_summary = self.receipt_rows(production_receipts)[-1]
            for field in check_batch_close.POSITIVE_CONTROL_BINDING_FIELDS:
                self.assertEqual(
                    control_summary.get(field), production_summary.get(field),
                    field)

    def test_clean_corpus_passes_and_names_the_positive_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.build_residual_corpus(root, residual_outside=False)
            config = self.write_residual_config(
                root, "honest.yaml", "interview-card", "Interview Card")
            receipts = root / "clean.jsonl"
            completed = self.run_residual_scan(root, config, receipts)
            self.assertEqual(0, completed.returncode,
                             completed.stdout + completed.stderr)
            summary = self.receipt_rows(receipts)[-1]
            self.assertEqual("residual-content-summary", summary["check"])
            self.assertEqual("pass", summary["result"])
            self.assertIn("Content/Card.md", summary["details"])
            self.assertEqual("passed", summary["positive_control_result"])
            self.assertEqual(
                "production-classifier", summary["positive_control_mode"])
            self.assertEqual(1, summary["positive_control_count"])
            self.assertRegex(
                summary["positive_control_fingerprint"],
                r"\Asha256:[0-9a-f]{64}\Z")

    def test_accepted_root_without_any_registered_structure_fails(self):
        """An accepted root that proves nothing cannot certify the scan."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = root / "Content"
            content.mkdir()
            (content / "Placeholder.md").write_text(
                "# Placeholder\n", encoding="utf-8")
            (root / "Clean.md").write_text("# Clean\n", encoding="utf-8")
            config = self.write_residual_config(
                root, "honest.yaml", "interview-card", "Interview Card")
            receipts = root / "unproven.jsonl"
            completed = self.run_residual_scan(root, config, receipts)
            self.assertEqual(1, completed.returncode,
                             completed.stdout + completed.stderr)
            self.assertEqual(
                ["residual-content-inert-matcher"],
                [row["check"] for row in self.receipt_rows(receipts)
                 if row["result"] == "fail"])

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


class StableGateRegistryProducerTableTests(unittest.TestCase):
    """The whole K00/12 table, not one column of one row.

    ``check_queue.gate_registry_producer_errors`` runs inside the registry
    parse, so an adopter's own ``check_queue.py`` run reports a row whose
    ``Tool``, ``Tool version``, ``Check`` or ``Mode`` its producer contradicts.
    """

    def registry(self):
        registry, errors = check_queue.standards_gate_registry(
            TOOLS_DIR.parent)
        self.assertEqual([], errors)
        return registry

    def run_tool(self, script, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS_DIR / script), *map(str, arguments)],
            text=True, capture_output=True, check=False,
        )

    def drifted(self, gate_id, **changes):
        registry = self.registry()
        registry[gate_id] = dict(registry[gate_id], **changes)
        return check_queue.gate_registry_producer_errors(registry)

    def test_every_registered_row_agrees_with_its_producer(self):
        self.assertEqual(
            [], check_queue.gate_registry_producer_errors(self.registry()))

    def test_the_assertion_runs_inside_the_registry_parse(self):
        """Not a test-only helper: the parse path itself must report it."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry_path = root / check_queue.STANDARDS_GATE_REGISTRY_PATH
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text(
                "## Stable Gate ID Registry\n\n"
                "| Gate ID | Tool | Tool version | Check | Mode "
                "| Dimension | Lifecycle |\n"
                "|---|---|---|---|---|---|---|\n"
                "| wiki-link-integrity | check_links | 9.9.9 "
                "| link-check-summary | * | * | not-batch-scoped |\n",
                encoding="utf-8",
            )
            registry, errors = check_queue.standards_gate_registry(root)
        self.assertIn("wiki-link-integrity", registry)
        self.assertTrue(any("stamps %s" % check_links.TOOL_VERSION in error
                            for error in errors), errors)

    def test_tool_version_drift_from_the_producer_is_reported(self):
        errors = self.drifted("batch-close", tool_version="9.9.9")
        self.assertTrue(any(
            "but check_batch_close stamps %s" % check_batch_close.TOOL_VERSION
            in error for error in errors), errors)

    def test_check_drift_from_the_producer_is_reported(self):
        errors = self.drifted("frontmatter-vocabulary", check="vocab-summary")
        self.assertTrue(any("writes vocab-check-summary" in error
                            for error in errors), errors)

    def test_queue_mode_must_round_trip_to_the_same_gate_id(self):
        errors = self.drifted("required-queue-admission",
                              mode="require-complete")
        self.assertTrue(any("which check_queue does not emit for that Gate"
                            in error for error in errors), errors)

    def test_only_check_queue_may_register_a_narrower_mode(self):
        """No other producer writes ``queue_check_mode`` to compare against."""
        errors = self.drifted("rendering", mode="consistency")
        self.assertTrue(any("only check_queue receipts carry queue_check_mode"
                            in error for error in errors), errors)

    def test_manual_rows_carry_the_current_protocol_version(self):
        errors = self.drifted("duplicate-detection", tool_version="0.9.0")
        self.assertTrue(any("manual-attestation protocol version 0.9.0"
                            in error for error in errors), errors)

    def test_a_row_may_not_register_an_uninstalled_producer(self):
        errors = self.drifted("wiki-link-integrity", tool="check_nothing")
        self.assertTrue(any("not an installed producer" in error
                            for error in errors), errors)

    def test_a_row_may_not_register_another_tools_gate_id(self):
        errors = self.drifted("wiki-link-integrity",
                              tool=check_vocab.TOOL,
                              tool_version=check_vocab.TOOL_VERSION,
                              check=check_vocab.GATE_CHECK)
        self.assertTrue(any("binds frontmatter-vocabulary to its receipts"
                            in error for error in errors), errors)

    def test_two_gate_ids_may_not_share_one_receipt_selector(self):
        errors = self.drifted(
            "depth-balance", check="rendering",
            dimensions=("rendering", "structure_and_links"))
        self.assertTrue(any("share one receipt selector" in error
                            for error in errors), errors)

    def test_every_row_registers_a_dimension_the_kernel_fixes(self):
        """F01-F03: the fifth selector column, checked against K12/07."""
        registry = self.registry()
        for gate_id, predicate in sorted(registry.items()):
            dimensions = predicate["dimensions"]
            self.assertTrue(dimensions, gate_id)
            if dimensions in (("*",), ("none",)):
                continue
            self.assertEqual(
                set(), set(dimensions) - check_queue.BASE_RECEIPT_DIMENSIONS,
                gate_id)
            if predicate["tool"] != check_queue.MANUAL_ATTESTATION_TOOL:
                producer = check_queue.producer_module(predicate["tool"])
                self.assertIsNotNone(producer, gate_id)
                self.assertEqual(
                    dimensions,
                    (getattr(producer, "GATE_DIMENSION", None),),
                    "%s narrows Dimension without a matching producer field"
                    % gate_id,
                )

    def test_the_two_dimension_projections_agree(self):
        """`check_queue` and `check_proof` project the same closed K12/07 set."""
        self.assertEqual(check_queue.BASE_RECEIPT_DIMENSIONS,
                         frozenset(check_proof.BASE_RECEIPT_DIMENSIONS))

    def test_a_named_producer_may_not_narrow_dimension(self):
        errors = self.drifted("wiki-link-integrity",
                              dimensions=("structure_and_links",))
        self.assertTrue(any("writes no dimension field" in error
                            for error in errors), errors)

    def test_an_invented_dimension_is_reported(self):
        errors = self.drifted("depth-balance", dimensions=("depth_balance",))
        self.assertTrue(any("K12/07 does not fix as a base receipt dimension"
                            in error for error in errors), errors)

    def test_a_hand_recorded_row_may_not_carry_the_unnarrowed_marker(self):
        errors = self.drifted("depth-balance", dimensions=("*",))
        self.assertTrue(any("manually dimensioned" in error
                            for error in errors), errors)

    def test_a_row_may_not_mix_the_markers_with_named_dimensions(self):
        errors = self.drifted("depth-balance",
                              dimensions=("content_and_depth", "none"))
        self.assertTrue(any("mixes" in error for error in errors), errors)

    def test_one_gate_id_covering_several_dimensions_is_registered_whole(self):
        """The reported one-to-many cases, counted from K12/08 and K12/18."""
        registry = self.registry()
        self.assertEqual(
            ("content_and_depth", "formula_and_numeric", "rendering",
             "source_and_currentness", "structure_and_links"),
            registry["content-correctness"]["dimensions"])
        self.assertEqual(("rendering", "structure_and_links"),
                         registry["rendering"]["dimensions"])

    def test_one_dimensions_receipt_does_not_satisfy_another(self):
        """The defect itself: A's attestation answering B's obligation."""
        registry = self.registry()
        attestation = {
            "gate_id": "content-correctness",
            "tool": check_queue.MANUAL_ATTESTATION_TOOL,
            "tool_version": check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
            "check": "content-correctness",
            "dimension": "structure_and_links",
        }
        # Registered for the Gate, so the unnarrowed predicate admits it ...
        self.assertTrue(check_queue.receipt_matches_gate_id(
            attestation, "content-correctness", registry))
        # ... but not for an obligation raised in a different dimension.
        self.assertFalse(check_queue.receipt_matches_gate_id(
            attestation, "content-correctness", registry,
            dimension="formula_and_numeric"))
        self.assertTrue(check_queue.receipt_matches_gate_id(
            dict(attestation, dimension="formula_and_numeric"),
            "content-correctness", registry,
            dimension="formula_and_numeric"))

    def test_an_attestation_without_a_dimension_is_rejected(self):
        """Silence is not a wildcard."""
        registry = self.registry()
        attestation = {
            "gate_id": "rendering",
            "tool": check_queue.MANUAL_ATTESTATION_TOOL,
            "tool_version": check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
            "check": "rendering",
        }
        self.assertFalse(check_queue.receipt_matches_gate_id(
            attestation, "rendering", registry))

    def test_a_none_dimension_gate_rejects_a_receipt_that_claims_one(self):
        registry = self.registry()
        wrapper = {
            "gate_id": check_queue.BATCH_REVIEW_GATE_ID,
            "tool": check_queue.MANUAL_ATTESTATION_TOOL,
            "tool_version": check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
            "check": check_queue.BATCH_REVIEW_CHECK,
        }
        self.assertTrue(check_queue.receipt_matches_gate_id(
            wrapper, check_queue.BATCH_REVIEW_GATE_ID, registry))
        self.assertFalse(check_queue.receipt_matches_gate_id(
            dict(wrapper, dimension="content_and_depth"),
            check_queue.BATCH_REVIEW_GATE_ID, registry))

    def test_the_registry_guard_runs_on_the_stamp_cards_gate_input(self):
        """Placement, not existence: an adopter must reach this guard.

        ``standards_gate_registry`` is otherwise reached only when a Standards
        revalidation is outstanding or an adoption plan is validated, so a
        producer version bumped without its K00/12 row surfaces first as a
        rejected receipt at ``open -> merge-ready``.  ``stamp_cards.py --check``
        is the run K00/12 names as the input of
        ``runtime-card-synchronization``, so the disagreement is reported there.
        """
        repository_root = TOOLS_DIR.parent
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            shutil.copytree(repository_root / "kernel", root / "kernel")
            shutil.copytree(
                repository_root / "Tools", root / "Tools",
                ignore=shutil.ignore_patterns("tests", "__pycache__"))

            clean = self.run_tool("stamp_cards.py", root, "--check")
            self.assertEqual(0, clean.returncode, clean.stdout + clean.stderr)

            registry_path = root / check_queue.STANDARDS_GATE_REGISTRY_PATH
            text = registry_path.read_text(encoding="utf-8")
            row = "| `batch-close` | `check_batch_close` | `%s` |" % (
                check_batch_close.TOOL_VERSION)
            self.assertIn(row, text)
            registry_path.write_text(
                text.replace(row, row.replace(
                    "`%s`" % check_batch_close.TOOL_VERSION, "`9.9.9`")),
                encoding="utf-8")

            drifted = self.run_tool("stamp_cards.py", root, "--check")
        self.assertEqual(1, drifted.returncode, drifted.stdout + drifted.stderr)
        self.assertIn("Gate ID batch-close registers Tool version 9.9.9",
                      drifted.stdout)
        self.assertIn("check_batch_close stamps %s"
                      % check_batch_close.TOOL_VERSION, drifted.stdout)

    def test_consumer_side_identity_must_match_the_registered_row(self):
        errors = self.drifted("terminal-proof", tool=check_vocab.TOOL,
                              tool_version=check_vocab.TOOL_VERSION,
                              check="proof-check-summary")
        self.assertTrue(any("this checker consumes its receipts as check_proof"
                            in error for error in errors), errors)

    def test_a_superseded_producer_version_is_still_refused_as_current(self):
        """Historical tolerance does not reach the current-action predicate.

        Historical validation stopped comparing `tool_version` to the current
        constant, because a sealed receipt cannot be restamped.  A receipt
        offered as authorization for a Gate ID now is a different question:
        `receipt_matches_gate_id` must still compare the registered producer
        tuple exactly, so a receipt whose Standards era this instance did pass
        through is nonetheless refused when its producer version has moved.
        """
        registry = self.registry()
        superseded = {
            "gate_id": "required-queue-consistency",
            "tool": check_queue.TOOL,
            "tool_version": "1.5.0",
            "check": "required_queue",
            "queue_check_mode": "consistency",
            "standards_version": "3.0.0",
        }
        self.assertIn(
            "3.0.0",
            check_queue.accounted_standards_versions(
                {"contract": {"standards_version": "3.0.0"},
                 "standards_adoptions": []}))
        self.assertFalse(check_queue.receipt_matches_gate_id(
            superseded, "required-queue-consistency", registry))
        self.assertEqual(
            check_queue.TOOL_VERSION,
            registry["required-queue-consistency"]["tool_version"])
        superseded["tool_version"] = check_queue.TOOL_VERSION
        self.assertTrue(check_queue.receipt_matches_gate_id(
            superseded, "required-queue-consistency", registry))

    def test_the_registered_lifecycle_column_partitions_by_position(self):
        """The K00/12 column, read through the one lifecycle map.

        `merge-ready -> open` is a sanctioned edge, so `open` is reachable
        from `open` and a `merge-ready` batch may still return for review;
        `queued` is reachable from nothing, so an admission gate is behind
        every batch that has left it.
        """
        registry = self.registry()
        probe = ["batch-close", "batch-review", "required-queue-admission",
                 "wiki-link-integrity"]
        expected = {
            "queued": (["required-queue-admission", "wiki-link-integrity"],
                       ["batch-close", "batch-review"], []),
            "open": (["batch-review", "wiki-link-integrity"],
                     ["batch-close"], ["required-queue-admission"]),
            "merge-ready": (["batch-close", "wiki-link-integrity"],
                            ["batch-review"], ["required-queue-admission"]),
            "closed": (["wiki-link-integrity"], [],
                       ["batch-close", "batch-review",
                        "required-queue-admission"]),
        }
        for state, partition in expected.items():
            with self.subTest(state=state):
                self.assertEqual(
                    partition,
                    check_queue.partition_boundary_gates_by_lifecycle(
                        probe, state, registry))

    def test_a_queue_exhausted_gate_is_deferred_by_every_live_batch(self):
        """The Queue-level position, judged the same way as a batch state.

        `required-queue-completion`, `maintenance-completion` and
        `terminal-proof` all refuse while any non-terminal batch remains, so
        every live batch has that position ahead of it and none has it behind:
        they are deferred everywhere and unrepeatable nowhere.
        """
        registry = self.registry()
        exhaustion = ["maintenance-completion", "required-queue-completion",
                      "terminal-proof"]
        for state in ("queued", "open", "merge-ready"):
            with self.subTest(state=state):
                self.assertEqual(
                    ([], exhaustion, []),
                    check_queue.partition_boundary_gates_by_lifecycle(
                        exhaustion, state, registry))
        for state in ("closed", "cancelled"):
            with self.subTest(state=state):
                self.assertEqual(
                    (exhaustion, [], []),
                    check_queue.partition_boundary_gates_by_lifecycle(
                        exhaustion, state, registry))

    def test_every_registered_position_is_one_of_the_three_forms(self):
        """No row falls outside the vocabulary the partition can read."""
        registry = self.registry()
        for gate_id in sorted(registry):
            with self.subTest(gate_id=gate_id):
                position = check_queue.registered_gate_position(
                    gate_id, registry)
                self.assertTrue(
                    position is None or
                    position == check_queue.QUEUE_EXHAUSTED_GATE or
                    (position and position.issubset(
                        set(kblib.BATCH_LIFECYCLE_TRANSITIONS))), position)

    def test_an_unknown_position_or_gate_leaves_every_gate_due(self):
        """Fail closed: nothing is waived on an answer the map cannot give."""
        registry = self.registry()
        self.assertEqual(
            (["batch-close", "required-queue-admission"], [], []),
            check_queue.partition_boundary_gates_by_lifecycle(
                ["batch-close", "required-queue-admission"], "in-review",
                registry))
        self.assertEqual(
            (["never-registered"], [], []),
            check_queue.partition_boundary_gates_by_lifecycle(
                ["never-registered"], "open", registry))

    def test_completion_gate_families_have_stable_gate_ids(self):
        """K00/06 names these two gates; K13/11 requires them to pass."""
        registry = self.registry()
        for gate_id in ("source-promotion", "expression-layer-acceptance"):
            self.assertEqual(
                {"tool": check_queue.MANUAL_ATTESTATION_TOOL,
                 "tool_version": check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
                 "check": gate_id, "mode": "*",
                 "dimensions": DIMENSIONS[gate_id],
                 "lifecycle_states": (NOT_BATCH_SCOPED,)},
                registry.get(gate_id), gate_id)


class RuntimeReceiptIdentityTests(unittest.TestCase):
    """Every deterministic Gate producer must bind the Queue identity.

    ``check_queue.standards_revalidation_context`` rejects a boundary Gate
    receipt whose ``task_id`` / ``standards_version`` /
    ``selected_profile_manifest`` do not equal the live Required Queue, so a
    producer that never writes them can never clear a boundary it is named for.
    """

    IDENTITY = kblib.RECEIPT_IDENTITY_FIELDS

    def runtime_root(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        shutil.copytree(RUNTIME_FIXTURE, root)
        return root

    def queue_identity(self, root):
        queue = kblib.load_yaml_file(root / check_queue.QUEUE_PATH)
        return {field: queue[field] for field in self.IDENTITY}

    def run_tool(self, script, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS_DIR / script), *map(str, arguments)],
            text=True, capture_output=True, check=False,
        )

    def receipt_rows(self, path):
        return [json.loads(line) for line in Path(path).read_text(
            encoding="utf-8").splitlines()]

    def test_identity_is_read_from_the_canonical_required_queue(self):
        root = self.runtime_root()
        self.assertEqual(
            {"task_id": "fixture-task", "standards_version": "3.0.0",
             "selected_profile_manifest": "profiles/test-profile/profile.md"},
            kblib.runtime_receipt_identity(root))

    def test_absent_runtime_omits_the_fields_instead_of_writing_null(self):
        """Absence, not ``null``: an unread field is never asserted.

        Consumers that demand an explicit binding spell it
        ``field not in receipt or receipt.get(field) != expected``.  An
        explicit ``null`` would satisfy the presence half of that test, so
        writing one could admit a receipt those consumers reject today.
        """
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual({}, kblib.runtime_receipt_identity(temporary))
            receipt = kblib.make_receipt(
                "check_links", "1.5.0", "link-check-summary", ".", "pass",
                "no runtime", 1, root=temporary)
        self.assertEqual({}, kblib.runtime_receipt_identity(None))
        for field in self.IDENTITY:
            self.assertNotIn(field, receipt)

    def test_unreadable_or_partial_queue_binds_only_what_it_can_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / ".cambium" / "state"
            state.mkdir(parents=True)
            queue = state / "required_queue.yaml"
            self.assertEqual({}, kblib.runtime_receipt_identity(root))

            queue.write_text("- not a mapping\n", encoding="utf-8")
            self.assertEqual({}, kblib.runtime_receipt_identity(root))

            queue.write_text("\ttask_id: tabbed\n", encoding="utf-8")
            self.assertEqual({}, kblib.runtime_receipt_identity(root))

            queue.write_text(
                "task_id: partial-task\n"
                "selected_profile_manifest: profiles/p/profile.md\n",
                encoding="utf-8")
            identity = kblib.runtime_receipt_identity(root)
            self.assertEqual(
                {"task_id": "partial-task",
                 "selected_profile_manifest": "profiles/p/profile.md"},
                identity)
            self.assertNotIn("standards_version", identity)

            elsewhere = root / "elsewhere.yaml"
            elsewhere.write_text("task_id: smuggled\n", encoding="utf-8")
            queue.unlink()
            queue.symlink_to(elsewhere)
            self.assertEqual({}, kblib.runtime_receipt_identity(root))

    def test_check_links_receipts_bind_the_queue_identity(self):
        root = self.runtime_root()
        receipts = root / ".cambium" / "receipts" / "links.jsonl"
        receipts.parent.mkdir(parents=True, exist_ok=True)
        completed = self.run_tool("check_links.py", root,
                                  "--receipts", receipts)
        self.assertEqual(0, completed.returncode,
                         completed.stdout + completed.stderr)
        rows = self.receipt_rows(receipts)
        expected = self.queue_identity(root)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(
                expected, {field: row.get(field) for field in self.IDENTITY})

    def test_check_vocab_receipts_bind_the_queue_identity(self):
        root = self.runtime_root()
        vocab = root / "vocab.yaml"
        vocab.write_text(
            "fields:\n"
            "  priority:\n"
            "    values:\n"
            "      - P0\n"
            "    owner: fixture\n",
            encoding="utf-8",
        )
        receipts = root / ".cambium" / "receipts" / "vocab.jsonl"
        receipts.parent.mkdir(parents=True, exist_ok=True)
        completed = self.run_tool(
            "check_vocab.py", root, "--vocab", vocab,
            "--quota-p0", "100", "--quota-p1", "100", "--receipts", receipts)
        self.assertIn(completed.returncode, (0, 2),
                      completed.stdout + completed.stderr)
        rows = self.receipt_rows(receipts)
        expected = self.queue_identity(root)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(
                expected, {field: row.get(field) for field in self.IDENTITY})

    def test_check_links_still_produces_receipts_without_a_runtime(self):
        """A generic check outside any Cambium runtime must keep working."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Page.md").write_text("# Page\n", encoding="utf-8")
            receipts = root / "links.jsonl"
            completed = self.run_tool("check_links.py", root,
                                      "--receipts", receipts)
            self.assertEqual(0, completed.returncode,
                             completed.stdout + completed.stderr)
            rows = self.receipt_rows(receipts)
        self.assertTrue(rows)
        for row in rows:
            for field in self.IDENTITY:
                self.assertNotIn(field, row)

    def test_deterministic_gate_producers_are_the_registered_set(self):
        """Guard the scope of this binding against a new deterministic gate."""
        registry, errors = check_queue.standards_gate_registry(
            TOOLS_DIR.parent)
        self.assertEqual([], errors)
        producers = {}
        for gate_id, predicate in registry.items():
            producers.setdefault(predicate["tool"], set()).add(gate_id)
        self.assertEqual(
            {check_profile.TOOL, check_links.TOOL, check_vocab.TOOL,
             check_residual_content.TOOL,
             check_batch_close.TOOL, check_corpus_plan.TOOL,
             record_corpus_acceptance.TOOL, adopt_standards.TOOL,
             check_structure.TOOL, check_page_contract.TOOL,
             check_boundary_contract.TOOL},
            set(producers) - {check_queue.MANUAL_ATTESTATION_TOOL,
                              check_queue.TOOL, check_proof.TOOL})
        self.assertEqual(
            15, len(producers[check_queue.MANUAL_ATTESTATION_TOOL]))


if __name__ == "__main__":
    unittest.main()
