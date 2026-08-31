"""Owned tests for the current Corpus semantic-acceptance transaction.

Corpus-plan structure, rank, order, and currentness predicates belong to
``check_corpus_plan``. This suite owns only the producer projection and one
real transaction from an already-valid, authority-confirmed plan through the
two Receipts, append, and consumer read-back.
"""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from Tools.execution.planning import check_corpus_plan
from Tools.execution.planning import record_corpus_acceptance as recorder
from Tools.execution.task_runtime import queue_runtime
from Tools.platform.common import kblib


PLAN_RELATIVE = ".cambium/deltas/corpus-plan-acceptances/CPA-001.yaml"
PROFILE_MANIFEST = "profiles/test-profile/profile.md"
CORPUS_SLOT = "profiles/test-profile/corpus-planning.yaml"
PROFILE_SCOPE = "profiles/test-profile/scope-and-architecture.md"
GLOBAL_MAP = "planning/global-map.yaml"
CAPABILITY_MATRIX = "planning/capability-matrix.yaml"
GAP_REGISTER = "planning/gap-register.yaml"


def _plan(decision="accepted"):
    return {
        "schema_version": 1,
        "acceptance_id": "CPA-001",
        "authority_role_id": "stopper",
        "decision_scope_id": "corpus-plan-semantic-acceptance",
        "decisions": [{
            "capability_id": "C-1",
            "decision": decision,
            "rationale": (
                "The current evidence supports the target outcome."
                if decision == "accepted"
                else "The evidence does not establish the target outcome."
            ),
        }],
    }


class CorpusAcceptanceProjectionContractTests(unittest.TestCase):
    """The producer mapping only; all plan predicates stay with their owner."""

    def test_confirmed_decision_projects_one_current_semantic_receipt(self):
        structural = {"receipt_id": "audit-structural-current"}
        binding = {
            "selected_profile_manifest":
                "profiles/test-profile/profile.md",
        }
        result = {
            "profile_manifest": "profiles/test-profile/profile.md",
            "root": None,
        }
        with self.subTest(decision="accepted"):
            with mock.patch.object(
                    check_corpus_plan, "make_pass_receipt",
                    return_value=structural), mock.patch.object(
                    check_corpus_plan, "receipt_binding",
                    return_value=binding):
                produced_structural, semantic = recorder._make_receipts(
                    result, _plan("accepted"), PLAN_RELATIVE,
                    "sha256:" + "a" * 64, "sha256:" + "b" * 64)
            self.assertIs(structural, produced_structural)
            self.assertEqual("pass", semantic["result"])
            self.assertEqual(
                structural["receipt_id"],
                semantic["structural_check_receipt"])
            self.assertEqual(
                _plan("accepted")["decisions"],
                semantic["capability_decisions"])
            self.assertEqual([], recorder.current_receipt_errors(semantic))

        with self.subTest(decision="rejected"):
            with mock.patch.object(
                    check_corpus_plan, "make_pass_receipt",
                    return_value=structural), mock.patch.object(
                    check_corpus_plan, "receipt_binding",
                    return_value=binding):
                _produced_structural, semantic = recorder._make_receipts(
                    result, _plan("rejected"), PLAN_RELATIVE,
                    "sha256:" + "a" * 64, "sha256:" + "b" * 64)
            self.assertEqual("fail", semantic["result"])
            self.assertEqual([], recorder.current_receipt_errors(semantic))


class RecordCorpusAcceptanceIntegrationTests(unittest.TestCase):
    """One local writer-to-consumer seam from a validated checkpoint.

    Corpus-plan parsing, Profile admission, Task initialization, and rank
    predicates have separate owners. This fixture therefore supplies their
    already-valid machine result directly and materializes only the exact
    files whose current bytes the Receipt contract binds.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self._write(PROFILE_MANIFEST, "# Test Profile\n")
        self._write(CORPUS_SLOT, "schema_version: 1\n")
        self._write(PROFILE_SCOPE, "# Scope\n")
        self._write(GLOBAL_MAP, "schema_version: 1\nentries: []\n")
        self._write(
            CAPABILITY_MATRIX,
            "schema_version: 1\ncapabilities: []\n",
        )
        self._write(GAP_REGISTER, "schema_version: 1\ngaps: []\n")
        self._write(
            queue_runtime.COVERAGE_PATH,
            "schema_version: 3\ntask_id: TASK-001\n",
        )
        self._write(
            queue_runtime.QUEUE_PATH,
            "schema_version: 3\n"
            "task_id: TASK-001\n"
            "queue_revision: 1\n"
            "state_revision: 1\n",
        )
        self._write(
            queue_runtime.PROGRESS_PATH,
            "schema_version: 3\ntask_id: TASK-001\n",
        )
        (self.root / ".cambium/receipts").mkdir(parents=True)
        self.plan_path = self.root / PLAN_RELATIVE
        self.plan_path.parent.mkdir(parents=True, exist_ok=True)
        self.plan_path.write_text(
            kblib.canonical_yaml(_plan()), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _catalog(self):
        path = self.root / ".cambium/receipts/corpus-plan-acceptance.jsonl"
        if not path.exists():
            return {}
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        return {record["receipt_id"]: record for record in records}

    def _validated_checkpoint(self):
        profile_snapshot = kblib.repository_tree_snapshot(
            self.root, "profiles/test-profile")
        artifacts = {
            "Global Map": GLOBAL_MAP,
            "Capability Matrix": CAPABILITY_MATRIX,
            "Gap Register": GAP_REGISTER,
        }
        runtime = {
            "errors": [],
            "queue": {
                "task_id": "TASK-001",
                "queue_revision": 1,
                "state_revision": 1,
                "selected_profile_manifest": PROFILE_MANIFEST,
            },
            "progress": {"contract": {
                "selected_profile_manifest": PROFILE_MANIFEST,
            }},
            "coverage_sha256": kblib.repository_file_snapshot(
                self.root, queue_runtime.COVERAGE_PATH).sha256,
            "queue_sha256": kblib.repository_file_snapshot(
                self.root, queue_runtime.QUEUE_PATH).sha256,
            "progress_sha256": kblib.repository_file_snapshot(
                self.root, queue_runtime.PROGRESS_PATH).sha256,
            "current_receipt_catalog": self._catalog(),
        }
        return {
            "root": str(self.root),
            "profile_manifest": PROFILE_MANIFEST,
            "slot_path": CORPUS_SLOT,
            "applicability": "configured",
            "slot": {
                "bindings": {
                    role: {
                        "value": relative,
                        "_snapshot": kblib.repository_file_snapshot(
                            self.root, relative),
                    }
                    for role, relative in artifacts.items()
                },
                "scale": [
                    {"rank": 0, "value": "Missing"},
                    {"rank": 1, "value": "Defensible"},
                ],
                "authorities": [{
                    "role_id": "stopper",
                    "decision_scope_id":
                        "corpus-plan-semantic-acceptance",
                }],
            },
            "profile_scope": {"path": PROFILE_SCOPE, "layers": [{
                "id": "L1", "directories": [],
                "responsibility": "Fixture scope.",
            }]},
            "global_map": {"entries": [{}], "edges": []},
            "matrix": {"capabilities": [{
                "id": "C-1",
                "current_level": "Defensible",
                "target_level": "Defensible",
            }]},
            "gap_register": {"gaps": [], "promotions": []},
            "runtime": runtime,
            "_authorized_profile_view": {
                "selected_profile_manifest": PROFILE_MANIFEST,
                "profile_snapshot_sha256": profile_snapshot.sha256,
                "profile_contract_fingerprint": "sha256:" + "a" * 64,
                "profile_load_inputs_sha256": "sha256:" + "b" * 64,
                "_profile_snapshot": profile_snapshot,
            },
            "errors": [],
        }

    def invoke(self, actor_role):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            return_code = recorder.main([
                str(self.root),
                "--plan", PLAN_RELATIVE,
                "--actor-role", actor_role,
                "--apply",
            ])
        return return_code, json.loads(output.getvalue())

    def test_confirmed_plan_appends_linked_receipts_and_reads_back_current(self):
        receipt_path = (
            self.root / ".cambium/receipts/corpus-plan-acceptance.jsonl")

        # The integration starts at the boundary owned by the already-run
        # structural checker. All producer, append, and acceptance-consumer
        # behavior below this boundary remains real.
        with mock.patch.object(
                check_corpus_plan, "validate_corpus_plan",
                side_effect=lambda *_args, **_kwargs:
                    self._validated_checkpoint()), mock.patch.object(
                check_corpus_plan.queue_runtime,
                "profile_load_authorized_view_currency_errors",
                return_value=[]):
            return_code, payload = self.invoke("stopper")
        self.assertEqual(0, return_code)
        self.assertTrue(payload["applied"])
        self.assertEqual("current", payload["status"]["status"])

        rows = [
            json.loads(line)
            for line in receipt_path.read_text(
                encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(2, len(rows))
        structural, semantic = rows
        self.assertEqual(
            ("check_corpus_plan", "corpus-plan-structure"),
            (structural["tool"], structural["gate_id"]),
        )
        self.assertEqual(
            ("record_corpus_acceptance",
             "corpus-plan-semantic-acceptance"),
            (semantic["tool"], semantic["gate_id"]),
        )
        self.assertEqual(
            structural["receipt_id"], semantic["structural_check_receipt"])
        self.assertEqual("stopper", semantic["authority_role_id"])
        self.assertEqual(_plan()["decisions"],
                         semantic["capability_decisions"])

        with mock.patch.object(
                check_corpus_plan.queue_runtime,
                "profile_load_authorized_view_currency_errors",
                return_value=[]):
            status = check_corpus_plan.semantic_acceptance_status(
                self._validated_checkpoint())
        self.assertEqual("current", status["status"])
        self.assertEqual(semantic["receipt_id"], status["receipt_id"])


if __name__ == "__main__":
    unittest.main()
