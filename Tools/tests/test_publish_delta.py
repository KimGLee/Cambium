"""Owner-focused contracts for publishing one candidate Coverage Delta.

The Queue lifecycle that creates an open batch is generated once into a
validated Integration checkpoint. This module owns only the adjacent
proposal-to-canonical-candidate seam; it does not replay Task planning,
Queue-open, audit production, Delta apply, or batch close.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.task_runtime.candidate_delta_runtime as candidate_delta_runtime  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
import publish_delta  # noqa: E402
from Tools.execution.task_runtime import queue_runtime  # noqa: E402
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
import Tools.knowledge.metadata.check_page_contract as check_page_contract  # noqa: E402
from Tools.tests.support.coverage_delta_fixture import (  # noqa: E402
    premerge_delta_document,
)
from Tools.tests.fixtures.integration.update_queue_checkpoints import (  # noqa: E402
    install_update_queue_checkpoint,
)


class CandidateDeltaContractTests(unittest.TestCase):
    """Keep identity and handoff-owner contracts independent of a runtime."""

    def test_expected_candidate_identity_is_absent_or_canonical_sha256(self):
        canonical = "sha256:" + "a" * 64
        self.assertEqual("absent", candidate_delta_runtime._expected_sha(
            "absent"))
        self.assertEqual(canonical, candidate_delta_runtime._expected_sha(
            canonical))
        for invalid in (None, "", "a" * 64, "sha256:" + "z" * 64):
            with self.subTest(invalid=invalid), self.assertRaises(
                    candidate_delta_runtime.CandidateDeltaError):
                candidate_delta_runtime._expected_sha(invalid)

    def test_queue_handoff_rejection_stops_before_target_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal = root / ".cambium/tmp/B1-proposal.yaml"
            proposal.parent.mkdir(parents=True)
            proposal.write_text(
                kblib.canonical_yaml({"batch": "B1", "pages": []}),
                encoding="utf-8",
            )
            runtime = {
                "queue_sha256": "sha256:" + "1" * 64,
                "coverage_sha256": "sha256:" + "2" * 64,
                "progress_sha256": "sha256:" + "3" * 64,
            }
            item = {"manifest": ["Topics/A.md"]}
            with mock.patch.object(
                    candidate_delta_runtime, "_runtime_and_item",
                    return_value=(runtime, item, ("Topics/A.md",))), \
                    mock.patch.object(
                        candidate_delta_runtime, "_handoff_errors",
                        return_value=["missing current page evidence"]), \
                    mock.patch.object(
                        candidate_delta_runtime, "_target_snapshot") as target:
                with self.assertRaisesRegex(
                        candidate_delta_runtime.CandidateDeltaError,
                        "not an admissible complete handoff"):
                    candidate_delta_runtime._plan(
                        root, "B1", ".cambium/tmp/B1-proposal.yaml", "absent")
            target.assert_not_called()


class CandidateDeltaPublicationIntegrationTests(unittest.TestCase):
    """Connect one validated open batch to the real candidate writer."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        install_update_queue_checkpoint(self.root, "open-b1")
        self.receipt = kblib.make_receipt(
            check_page_contract.TOOL,
            check_page_contract.TOOL_VERSION,
            check_page_contract.GATE_CHECK,
            "Topics/A.md",
            "pass",
            "fixture evidence for candidate Delta publication",
            1,
            receipt_type_id=check_page_contract.RECEIPT_TYPE_ID,
            root=self.root,
        )
        self.receipt["gate_id"] = check_page_contract.GATE_ID
        kblib.write_receipts(
            self.root / ".cambium/receipts/candidate-delta-fixture.jsonl",
            [self.receipt],
        )
        self.proposal_relative = ".cambium/tmp/B1-proposal.yaml"
        self.proposal_path = self.root / self.proposal_relative
        self.proposal_path.parent.mkdir(parents=True, exist_ok=True)
        self.delta_relative = ".cambium/deltas/B1.yaml"
        self.delta_path = self.root / self.delta_relative
        self.write_proposal()
        self.assertEqual(
            [], runtime_validation.validate_runtime(self.root)["errors"])

    def proposal(self, generated_at="2026-08-30T00:00:00Z"):
        return premerge_delta_document(
            "B1", "Topics/A.md", [self.receipt["receipt_id"]],
            generated_at=generated_at,
        )

    def write_proposal(self, *, generated_at="2026-08-30T00:00:00Z",
                       document=None):
        document = self.proposal(generated_at) if document is None else document
        self.proposal_path.write_text(
            kblib.canonical_yaml(document), encoding="utf-8")
        return document

    def publish(self, expected="absent"):
        return candidate_delta_runtime.publish_candidate_delta(
            self.root,
            batch_id="B1",
            proposal_path=self.proposal_relative,
            expected_delta_sha256=expected,
        )

    def test_current_publication_seam_is_fail_closed_idempotent_and_state_neutral(self):
        state_before = {
            path: kblib.sha256_file(self.root / path)
            for path in (
                queue_runtime.QUEUE_PATH,
                queue_runtime.COVERAGE_PATH,
                queue_runtime.PROGRESS_PATH,
            )
        }
        receipt_files_before = sorted(
            path.relative_to(self.root).as_posix()
            for path in (self.root / ".cambium/receipts").rglob("*")
            if path.is_file()
        )

        wrong = self.proposal()
        wrong["pages"][0]["path"] = "Topics/B.md"
        self.write_proposal(document=wrong)
        with self.assertRaisesRegex(
                candidate_delta_runtime.CandidateDeltaError,
                "frozen manifest"):
            candidate_delta_runtime.plan_candidate_delta(
                self.root,
                batch_id="B1",
                proposal_path=self.proposal_relative,
                expected_delta_sha256="absent",
            )
        self.assertFalse(self.delta_path.exists())

        self.write_proposal()
        planned = candidate_delta_runtime.plan_candidate_delta(
            self.root,
            batch_id="B1",
            proposal_path=self.proposal_relative,
            expected_delta_sha256="absent",
        )
        self.assertEqual(("planned", False),
                         (planned["status"], planned["applied"]))
        self.assertFalse(self.delta_path.exists())

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = publish_delta.main([
                str(self.root),
                "--batch", "B1",
                "--proposal", self.proposal_relative,
                "--expected-delta-sha256", "absent",
                "--apply",
            ])
        self.assertEqual(0, exit_code)
        first = json.loads(output.getvalue())
        self.assertEqual(("published", True),
                         (first["status"], first["applied"]))
        self.assertEqual(
            kblib.canonical_yaml(self.proposal()),
            self.delta_path.read_text(encoding="utf-8"),
        )
        self.assertEqual(1, os.stat(self.delta_path).st_nlink)
        runtime = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        record = next(
            value for value in runtime["managed_deltas"]
            if value["path"] == self.delta_relative
        )
        self.assertEqual("candidate", record["handoff_status"])
        self.assertEqual(first["delta_sha256"], record["sha256"])

        before_idempotent = os.stat(self.delta_path)
        same = self.publish()
        after_idempotent = os.stat(self.delta_path)
        self.assertEqual("already-present", same["status"])
        self.assertEqual(before_idempotent.st_ino, after_idempotent.st_ino)
        self.assertEqual(before_idempotent.st_mtime_ns,
                         after_idempotent.st_mtime_ns)

        self.write_proposal(generated_at="2026-08-30T00:01:00Z")
        replacement = self.publish(first["delta_sha256"])
        self.assertEqual("published", replacement["status"])
        replacement_bytes = self.delta_path.read_bytes()
        self.assertNotEqual(first["delta_sha256"],
                            replacement["delta_sha256"])

        self.write_proposal(generated_at="2026-08-30T00:02:00Z")
        for expected in ("absent", "sha256:" + "f" * 64):
            with self.subTest(stale_expected=expected), self.assertRaises(
                    candidate_delta_runtime.CandidateDeltaError):
                self.publish(expected)
            self.assertEqual(replacement_bytes, self.delta_path.read_bytes())

        with mock.patch.object(
                candidate_delta_runtime, "_post_publish_errors",
                return_value=["injected post-publication refusal"]):
            with self.assertRaises(candidate_delta_runtime.CandidateDeltaError):
                self.publish(replacement["delta_sha256"])
        self.assertEqual(replacement_bytes, self.delta_path.read_bytes())
        self.assertEqual(
            [], runtime_validation.validate_runtime(self.root)["errors"])
        self.assertEqual(state_before, {
            path: kblib.sha256_file(self.root / path) for path in state_before
        })
        self.assertEqual(receipt_files_before, sorted(
            path.relative_to(self.root).as_posix()
            for path in (self.root / ".cambium/receipts").rglob("*")
            if path.is_file()
        ))


class CandidateDeltaFilesystemSafetyTests(unittest.TestCase):
    """Exercise filesystem boundaries without constructing a Task runtime."""

    @staticmethod
    def root_with_namespaces(directory):
        root = Path(directory)
        (root / ".cambium/tmp").mkdir(parents=True)
        (root / ".cambium/deltas").mkdir(parents=True)
        return root

    def test_proposal_path_rejects_links_and_namespace_escape(self):
        for case in ("hardlink", "symlink", "escape"):
            with self.subTest(case=case), \
                    tempfile.TemporaryDirectory() as directory:
                root = self.root_with_namespaces(directory)
                proposal = root / ".cambium/tmp/B1-proposal.yaml"
                proposal.write_text("batch: B1\npages: []\n", encoding="utf-8")
                relative = ".cambium/tmp/B1-proposal.yaml"
                if case == "hardlink":
                    os.link(proposal, root / ".cambium/tmp/B1-hardlink.yaml")
                elif case == "symlink":
                    link = root / ".cambium/tmp/B1-symlink.yaml"
                    link.symlink_to(proposal)
                    relative = ".cambium/tmp/B1-symlink.yaml"
                else:
                    relative = ".cambium/tmp/../deltas/B1.yaml"
                with self.assertRaises(
                        candidate_delta_runtime.CandidateDeltaError):
                    candidate_delta_runtime._proposal_snapshot(root, relative)

    def test_canonical_target_rejects_multiple_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.root_with_namespaces(directory)
            target = root / ".cambium/deltas/B1.yaml"
            target.write_text("batch: B1\npages: []\n", encoding="utf-8")
            os.link(target, root / ".cambium/tmp/candidate-alias.yaml")
            with self.assertRaises(
                    candidate_delta_runtime.CandidateDeltaError):
                candidate_delta_runtime._target_snapshot(
                    root, ".cambium/deltas/B1.yaml")

    def test_rollback_restores_absence_or_previous_bytes(self):
        for previous_text in (None, "batch: B1\nprevious: true\n"):
            with self.subTest(previous=previous_text is not None), \
                    tempfile.TemporaryDirectory() as directory:
                root = self.root_with_namespaces(directory)
                target = root / ".cambium/deltas/B1.yaml"
                if previous_text is not None:
                    target.write_text(previous_text, encoding="utf-8")
                before = candidate_delta_runtime._target_snapshot(
                    root, ".cambium/deltas/B1.yaml")
                canonical_text = "batch: B1\npages: []\n"
                target.write_text(canonical_text, encoding="utf-8")
                plan = candidate_delta_runtime._PublicationPlan(
                    root=str(root),
                    batch_id="B1",
                    proposal_path=".cambium/tmp/B1-proposal.yaml",
                    expected_delta_sha256="absent",
                    delta_path=".cambium/deltas/B1.yaml",
                    canonical_text=canonical_text,
                    delta_sha256=kblib.sha256_bytes(canonical_text),
                    previous_delta_sha256=(
                        before.sha256 if before.exists else None),
                    action="replace" if before.exists else "create",
                    queue_sha256="sha256:" + "1" * 64,
                    coverage_sha256="sha256:" + "2" * 64,
                    progress_sha256="sha256:" + "3" * 64,
                    manifest=("Topics/A.md",),
                )
                candidate_delta_runtime._rollback(plan, before)
                if previous_text is None:
                    self.assertFalse(target.exists())
                else:
                    self.assertEqual(previous_text,
                                     target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
