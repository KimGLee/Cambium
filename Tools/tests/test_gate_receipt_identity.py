"""Ownership tests for current Gate and Receipt identity.

The Control Registry owns Gate rows. ``gate_registry`` owns their projection
to installed producers, receipt matching, and lifecycle position. ``kblib``
owns the Required Queue identity copied into newly produced Receipts. Receipt
type dispatch, catalog heat/currentness, sealing, and Queue/Proof verdicts
have separate owner tests and are intentionally not replayed here.
"""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import Tools.knowledge.content.check_links as check_links  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.execution.task_runtime.queue_runtime.canon as runtime_canon  # noqa: E402
import Tools.execution.task_runtime.queue_runtime.gate_registry as gate_registry  # noqa: E402


IDENTITY = {
    "task_id": "fixture-task",
    "upstream_revision_id": "a" * 40,
    "selected_profile_manifest": "profiles/fixture/profile.toml",
}


def current_registry():
    registry, errors = gate_registry.standards_gate_registry(REPOSITORY)
    if errors:
        raise AssertionError("invalid current Gate registry: %s" % errors)
    return registry


def receipt_for(gate_id, predicate, *, dimension=None, mode=None):
    receipt = {
        "gate_id": gate_id,
        "tool": predicate["tool"],
        "tool_version": predicate["tool_version"],
        "check": predicate["check"],
    }
    registered = gate_registry.registered_gate_dimensions(
        gate_id, {gate_id: predicate})
    if dimension is None and registered:
        dimension = sorted(registered)[0]
    if dimension is not None:
        receipt["dimension"] = dimension

    expected_mode = predicate["mode"]
    if mode is None and expected_mode != "*":
        mode = (expected_mode[:-1] + "fixture"
                if expected_mode.endswith("*") else expected_mode)
    if mode is not None:
        receipt["queue_check_mode"] = mode
    return receipt


@contextmanager
def temporary_repository():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory, "repository")
        root.mkdir()
        yield root


def run_check_links(*arguments):
    stdout = io.StringIO()
    stderr = io.StringIO()
    previous = sys.argv
    try:
        sys.argv = ["check_links.py", *map(str, arguments)]
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = check_links.main()
        except SystemExit as exc:
            code = int(exc.code)
    finally:
        sys.argv = previous
    return SimpleNamespace(
        returncode=int(code or 0), stdout=stdout.getvalue(),
        stderr=stderr.getvalue())


class GateReceiptSelectorTests(unittest.TestCase):
    """Contract: one predicate owns every axis of Gate receipt identity."""

    def test_every_current_gate_accepts_its_exact_registered_identity(self):
        registry = current_registry()
        for gate_id, predicate in sorted(registry.items()):
            with self.subTest(gate_id=gate_id):
                receipt = receipt_for(gate_id, predicate)
                self.assertTrue(gate_registry.receipt_matches_gate_id(
                    receipt, gate_id, registry))

    def test_selector_axes_fail_closed(self):
        registry = current_registry()
        base_id = "wiki-link-integrity"
        base = receipt_for(base_id, registry[base_id])
        mutations = (
            ("gate-id", {"gate_id": "other"}),
            ("tool", {"tool": "other"}),
            ("tool-version", {"tool_version": "0"}),
            ("check", {"check": "other"}),
        )
        for name, changes in mutations:
            with self.subTest(axis=name):
                receipt = dict(base, **changes)
                self.assertFalse(gate_registry.receipt_matches_gate_id(
                    receipt, base_id, registry))

        for gate_id, predicate in sorted(registry.items()):
            expected_mode = predicate["mode"]
            if expected_mode == "*":
                continue
            with self.subTest(axis="mode", gate_id=gate_id):
                self.assertFalse(gate_registry.receipt_matches_gate_id(
                    receipt_for(gate_id, predicate, mode="wrong"),
                    gate_id, registry))

        dimensioned_id = "content-correctness"
        dimensions = registry[dimensioned_id]["dimensions"]
        receipt = receipt_for(
            dimensioned_id, registry[dimensioned_id],
            dimension=dimensions[0])
        self.assertTrue(gate_registry.receipt_matches_gate_id(
            receipt, dimensioned_id, registry, dimension=dimensions[0]))
        self.assertFalse(gate_registry.receipt_matches_gate_id(
            receipt, dimensioned_id, registry, dimension=dimensions[1]))
        self.assertFalse(gate_registry.receipt_matches_gate_id(
            {key: value for key, value in receipt.items()
             if key != "dimension"}, dimensioned_id, registry))

        undimensioned_id = runtime_canon.BATCH_REVIEW_GATE_ID
        undimensioned = receipt_for(
            undimensioned_id, registry[undimensioned_id])
        self.assertTrue(gate_registry.receipt_matches_gate_id(
            undimensioned, undimensioned_id, registry))
        self.assertFalse(gate_registry.receipt_matches_gate_id(
            dict(undimensioned, dimension=dimensions[0]),
            undimensioned_id, registry))


class GateProducerClosureTests(unittest.TestCase):
    """Contract: every current selector has one installed producer."""

    def test_current_registry_matches_all_installed_producers(self):
        registry = current_registry()
        self.assertEqual([], gate_registry.gate_registry_producer_errors(
            registry))

    def test_producer_drift_matrix(self):
        cases = (
            ("tool-version", "wiki-link-integrity",
             {"tool_version": "0"}, "stamps"),
            ("check", "wiki-link-integrity",
             {"check": "other"}, "writes"),
            ("queue-mode", "required-queue-admission",
             {"mode": "require-complete"}, "does not emit"),
            ("nonqueue-mode", "wiki-link-integrity",
             {"mode": "consistency"}, "only check_queue"),
            ("manual-version", "content-correctness",
             {"tool_version": "0"}, "protocol version"),
            ("unknown-producer", "wiki-link-integrity",
             {"tool": "check_nothing"}, "not an installed producer"),
            ("producer-dimension", "profile-load",
             {"dimensions": ("rendering",)}, "emits"),
            ("consumer-identity", "terminal-proof",
             {"tool_version": "0"}, "this checker consumes"),
        )
        for name, gate_id, changes, message in cases:
            with self.subTest(case=name):
                registry = current_registry()
                registry[gate_id] = dict(registry[gate_id], **changes)
                errors = gate_registry.gate_registry_producer_errors(registry)
                self.assertTrue(any(message in error for error in errors),
                                errors)

        registry = current_registry()
        registry["depth-balance"] = dict(registry["rendering"])
        errors = gate_registry.gate_registry_producer_errors(registry)
        self.assertTrue(any("share one receipt selector" in error
                            for error in errors), errors)


class GateLifecycleProjectionTests(unittest.TestCase):
    """Contract: lifecycle position partitions one Gate into one next action."""

    def test_batch_and_queue_positions_share_one_partition(self):
        registry = current_registry()
        gates = [
            "required-queue-admission",
            runtime_canon.BATCH_REVIEW_GATE_ID,
            "batch-close",
            "wiki-link-integrity",
            "terminal-proof",
        ]
        expected = {
            "queued": (
                ["required-queue-admission", "wiki-link-integrity"],
                ["batch-close", runtime_canon.BATCH_REVIEW_GATE_ID,
                 "terminal-proof"],
                [],
            ),
            "open": (
                [runtime_canon.BATCH_REVIEW_GATE_ID, "wiki-link-integrity"],
                ["batch-close", "terminal-proof"],
                ["required-queue-admission"],
            ),
            "merge-ready": (
                ["batch-close", "wiki-link-integrity"],
                [runtime_canon.BATCH_REVIEW_GATE_ID, "terminal-proof"],
                ["required-queue-admission"],
            ),
            "closed": (
                ["terminal-proof", "wiki-link-integrity"],
                [],
                ["batch-close", runtime_canon.BATCH_REVIEW_GATE_ID,
                 "required-queue-admission"],
            ),
        }
        for state, partition in expected.items():
            with self.subTest(state=state):
                self.assertEqual(
                    partition,
                    gate_registry.partition_boundary_gates_by_lifecycle(
                        gates, state, registry))

        self.assertEqual(
            (sorted(gates), [], []),
            gate_registry.partition_boundary_gates_by_lifecycle(
                gates, "unknown", registry))


class RuntimeReceiptIdentityTests(unittest.TestCase):
    """Contract: current Required Queue fields are the only inferred identity."""

    def test_required_queue_identity_projection_matrix(self):
        with temporary_repository() as root:
            self.assertEqual({}, kblib.runtime_receipt_identity(root))

            full = root / "full" / ".cambium/state/required_queue.yaml"
            full.parent.mkdir(parents=True)
            full.write_text(kblib.canonical_yaml(IDENTITY), encoding="utf-8")
            self.assertEqual(
                IDENTITY, kblib.runtime_receipt_identity(root / "full"))

            partial = root / "partial" / ".cambium/state/required_queue.yaml"
            partial.parent.mkdir(parents=True)
            partial.write_text(kblib.canonical_yaml({
                "task_id": "partial-task",
                "selected_profile_manifest": "profiles/p/profile.toml",
            }), encoding="utf-8")
            self.assertEqual(
                {"task_id": "partial-task",
                 "selected_profile_manifest": "profiles/p/profile.toml"},
                kblib.runtime_receipt_identity(root / "partial"))

            malformed = root / "malformed" / ".cambium/state/required_queue.yaml"
            malformed.parent.mkdir(parents=True)
            malformed.write_text("- not a mapping\n", encoding="utf-8")
            self.assertEqual(
                {}, kblib.runtime_receipt_identity(root / "malformed"))
            self.assertEqual({}, kblib.runtime_receipt_identity(None))


class RuntimeReceiptIdentitySlowTests(unittest.TestCase):
    def test_symlinked_queue_cannot_assert_runtime_identity(self):
        with temporary_repository() as root:
            state = root / ".cambium/state"
            state.mkdir(parents=True)
            outside = root / "outside.yaml"
            outside.write_text(kblib.canonical_yaml(IDENTITY), encoding="utf-8")
            (state / "required_queue.yaml").symlink_to(outside)

            self.assertEqual({}, kblib.runtime_receipt_identity(root))


class GateReceiptProducerConsumerTests(unittest.TestCase):
    """Integration: one real producer connects to the current Gate selector."""

    def test_check_links_receipt_binds_queue_and_matches_gate_owner(self):
        with temporary_repository() as root:
            (root / "Page.md").write_text("# Page\n", encoding="utf-8")
            queue = root / ".cambium/state/required_queue.yaml"
            queue.parent.mkdir(parents=True)
            queue.write_text(kblib.canonical_yaml(IDENTITY), encoding="utf-8")
            receipts = root / ".cambium/receipts/links.jsonl"
            receipts.parent.mkdir(parents=True)

            completed = run_check_links(root, "--receipts", receipts)
            self.assertEqual(
                completed.returncode, 0,
                completed.stdout + completed.stderr)
            rows = [json.loads(line) for line in receipts.read_text(
                encoding="utf-8").splitlines()]

        registry = current_registry()
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(receipt_id=row["receipt_id"]):
                self.assertEqual(
                    IDENTITY,
                    {field: row[field] for field in kblib.RECEIPT_IDENTITY_FIELDS})
                self.assertEqual(
                    row["receipt_type_id"], check_links.RECEIPT_TYPE_ID)
                self.assertTrue(gate_registry.receipt_matches_gate_id(
                    row, check_links.GATE_ID, registry))


if __name__ == "__main__":
    unittest.main()
