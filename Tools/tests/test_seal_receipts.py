"""Owned tests for the current hot -> cold Receipt seal lifecycle.

The Receipt graph owns projection fields, the typed Receipt registry owns
producer admission, and ``queue_runtime.receipts`` owns cold-catalog
validation. This suite keeps only the seal-specific contracts plus one
adjacent writer-to-catalog lifecycle. It deliberately starts from one legal
current-format historical Receipt instead of replaying Task, Queue, Batch,
Audit, and Delta lifecycles merely to manufacture a sealing input.
"""

import contextlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from Tools.execution.evidence import receipt_reference_contract
from Tools.execution.evidence import receipt_type_contract
from Tools.execution.evidence import seal_receipts
from Tools.execution.task_runtime import runtime_validation
from Tools.execution.task_runtime.queue_runtime import receipts as receipt_store
from Tools.knowledge.metadata import check_page_contract
from Tools.platform.common import kblib


REPOSITORY = Path(__file__).resolve().parents[2]
PAGE_RECEIPTS_PATH = ".cambium/receipts/page-contract.jsonl"


def _registry():
    return receipt_type_contract.load_receipt_type_registry(REPOSITORY)


def _page_receipt(sequence=1):
    receipt = kblib.make_receipt(
        check_page_contract.TOOL,
        check_page_contract.TOOL_VERSION,
        "page-contract-content",
        "Topics/A.md",
        "pass",
        "current-format page-contract history used by the seal fixture",
        sequence,
        receipt_type_id=check_page_contract.RECEIPT_TYPE_ID,
    )
    receipt["gate_id"] = check_page_contract.GATE_ID
    receipt["invalidated_by"] = "content-fingerprint-change"
    return receipt


def _write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


@contextlib.contextmanager
def _current_checkpoint():
    """Yield one current-format historical Receipt and its planner view."""
    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace) / "repo"
        (root / ".cambium/tmp").mkdir(parents=True)
        (root / ".cambium/state").mkdir(parents=True)
        receipt = _page_receipt()
        _write_rows(root / PAGE_RECEIPTS_PATH, [receipt])

        catalog = receipt_store.HistoricalReceiptCatalog({
            receipt["receipt_id"]: (PAGE_RECEIPTS_PATH, receipt),
        })
        catalog.root = str(root)
        catalog._type_registry = _registry()
        current_catalog = receipt_store.CurrentReceiptCatalog()
        current_catalog.root = str(root)
        current_catalog._type_registry = catalog._type_registry
        runtime = {
            "errors": [],
            "receipt_catalog": catalog,
            "current_receipt_catalog": current_catalog,
            "items_by_id": {},
            "coverage": {},
            "progress": {},
            "queue": {
                "task_id": "T-SEAL-CURRENT",
                "state_revision": 1,
                "queue_revision": 1,
            },
            "_active_standards_authorized_view": {},
            "_writer_locks": [],
            "pending_delta_applies": {},
            "cold_receipts": {},
        }
        yield root, runtime, receipt


def _plan(root, runtime):
    plan = seal_receipts.plan_seal(str(root), runtime)
    if set(plan) != {PAGE_RECEIPTS_PATH}:
        raise AssertionError("minimal current Receipt did not produce one plan")
    return plan


def _apply(root, runtime):
    """Exercise the real writer from one already-validated local checkpoint."""
    plan = _plan(root, runtime)
    before = seal_receipts._receipt_tree_fingerprint(str(root))
    # Full runtime validation has its own owner. This Integration supplies its
    # already-validated result and keeps the seal's CAS, locks, journal, and
    # publication real.
    with mock.patch.object(
            runtime_validation, "validate_runtime", return_value=runtime):
        receipt = seal_receipts.apply_seal(
            str(root), runtime, plan, seal_receipts.SEAL_RECEIPTS_PATH,
            before,
        )
    if receipt is None:
        raise AssertionError("minimal current Receipt produced no seal")
    return receipt


def _cold_result(root, seal_receipt, *, include_seal=True):
    hot = ({seal_receipt["receipt_id"]: (
        seal_receipts.SEAL_RECEIPTS_PATH, seal_receipt,
    )} if include_seal else {})
    catalog = receipt_store.HistoricalReceiptCatalog(hot)
    catalog.root = str(root)
    catalog._type_registry = _registry()
    errors = []
    cold = receipt_store.cold_receipt_store(str(root), errors, catalog)
    return catalog, cold, errors


def _pending(root, runtime):
    manifest, index, edits = seal_receipts._plan_payload(
        str(root), runtime, _plan(root, runtime), "20260831T000000Z")
    return seal_receipts._pending_record(
        str(root), runtime, seal_receipts.SEAL_RECEIPTS_PATH,
        manifest, index, edits,
    )


def _begin(root, pending):
    """Persist the exact current pending/journal binding used by recovery."""
    payload = json.dumps(pending, ensure_ascii=False, sort_keys=True)
    digest = kblib.sha256_bytes(payload.encode("utf-8"))
    pending["pending_sha256"] = digest
    relative = "%s/%s.json" % (
        seal_receipts.COLD_PENDING_PREFIX, pending["seal_receipt"])
    full = root / relative
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(payload, encoding="utf-8")
    entry = {
        "phase": "begin",
        "seal_receipt": pending["seal_receipt"],
        "pending_path": relative,
        "pending_sha256": digest,
    }
    seal_receipts._append_lines(
        root / kblib.RECEIPT_COLD_JOURNAL_PATH,
        [json.dumps(entry, ensure_ascii=False, sort_keys=True)],
    )
    return entry, full


def _sealed_segment(root):
    rows = [json.loads(line) for line in (
        root / kblib.RECEIPT_COLD_MANIFEST_PATH
    ).read_text(encoding="utf-8").splitlines() if line]
    return root / next(
        row["segment"] for row in rows
        if row["kind"] == "sealed-receipts")


class SealContractTests(unittest.TestCase):
    def test_projection_consumes_the_graph_owned_field_set(self):
        with mock.patch.object(
                receipt_reference_contract,
                "RECEIPT_COLD_PROJECTION_FIELDS", ("tool",)):
            row = seal_receipts._projection(
                "audit-projection-probe", "segment.jsonl", 1,
                '{"result":"pass","tool":"probe"}',
                {"tool": "probe", "result": "pass"},
            )

        self.assertEqual(
            {"receipt_id", "segment", "line", "record_sha256", "tool"},
            set(row),
        )

    def test_seal_receipt_validator_owns_current_identity_and_payload(self):
        receipt = kblib.make_receipt(
            seal_receipts.TOOL,
            seal_receipts.TOOL_VERSION,
            "receipt_seal",
            seal_receipts.SEAL_RECEIPTS_PATH,
            "pass",
            "current seal receipt fixture",
            1,
            receipt_type_id=seal_receipts.RECEIPT_TYPE_ID,
        )
        receipt.update({
            "manifest_rows_sha256": "sha256:" + "1" * 64,
            "index_rows_sha256": "sha256:" + "2" * 64,
            "sealed_segments": ["segment.jsonl"],
            "sealed_records": 1,
        })
        self.assertEqual([], seal_receipts.current_receipt_errors(receipt))

        mutations = {
            "missing-producer-version": {"tool_version": None},
            "missing-receipt-type": {"receipt_type_id": None},
            "missing-payload": {"manifest_rows_sha256": None},
        }
        for label, fields in mutations.items():
            with self.subTest(label=label):
                candidate = dict(receipt)
                for field, value in fields.items():
                    if value is None:
                        candidate.pop(field)
                    else:
                        candidate[field] = value
                errors = seal_receipts.current_receipt_errors(candidate)
                self.assertTrue(errors)


class SealLifecycleIntegrationTests(unittest.TestCase):
    def test_current_format_history_is_sealed_and_remains_read_only_cold(self):
        with _current_checkpoint() as (root, runtime, history_receipt):
            self.assertIn(
                history_receipt["receipt_id"], runtime["receipt_catalog"])
            self.assertNotIn(
                history_receipt["receipt_id"],
                runtime["current_receipt_catalog"],
            )
            seal_receipt = _apply(root, runtime)
            self.assertEqual("", (root / PAGE_RECEIPTS_PATH).read_text(
                encoding="utf-8"))
            self.assertEqual(
                [], seal_receipts.current_receipt_errors(seal_receipt))

            catalog, cold, errors = _cold_result(root, seal_receipt)
            self.assertEqual([], errors)
            self.assertEqual(
                {history_receipt["receipt_id"]}, set(cold["index"]))
            self.assertEqual(
                [seal_receipt["receipt_id"]], cold["seals"])
            self.assertIn(seal_receipt["receipt_id"], catalog)
            self.assertNotIn(seal_receipt["receipt_id"], catalog.cold)
            historical = catalog.resolve_sealed(history_receipt["receipt_id"])
            self.assertEqual(
                (_sealed_segment(root).relative_to(root).as_posix(),
                 history_receipt),
                historical,
            )
            self.assertEqual(
                "content-fingerprint-change",
                cold["index"][history_receipt["receipt_id"]]["invalidated_by"],
            )
            self.assertNotIn(history_receipt["receipt_id"], catalog)

    def test_writer_rejects_a_stale_plan_and_preserves_an_unplanned_append(self):
        with _current_checkpoint() as (root, runtime, _receipt):
            plan = _plan(root, runtime)
            before = seal_receipts._receipt_tree_fingerprint(str(root))
            appended = _page_receipt(2)
            with (root / PAGE_RECEIPTS_PATH).open("a", encoding="utf-8") \
                    as handle:
                handle.write(json.dumps(appended, sort_keys=True) + "\n")
            with mock.patch.object(
                    runtime_validation, "validate_runtime",
                    return_value=runtime):
                with self.assertRaisesRegex(ValueError, "receipt tree changed"):
                    seal_receipts.apply_seal(
                        str(root), runtime, plan,
                        seal_receipts.SEAL_RECEIPTS_PATH, before)
            self.assertFalse(
                (root / kblib.RECEIPT_COLD_MANIFEST_PATH).exists())

        with _current_checkpoint() as (root, runtime, planned):
            pending = _pending(root, runtime)
            appended = _page_receipt(2)
            with (root / PAGE_RECEIPTS_PATH).open("a", encoding="utf-8") \
                    as handle:
                handle.write(json.dumps(appended, sort_keys=True) + "\n")
            _begin(root, pending)
            seal_receipts._publish(str(root), pending)
            live_ids = {
                json.loads(line)["receipt_id"]
                for line in (root / PAGE_RECEIPTS_PATH).read_text(
                    encoding="utf-8").splitlines() if line
            }
            self.assertEqual({appended["receipt_id"]}, live_ids)
            _catalog, cold, errors = _cold_result(root, pending["receipt"])
            self.assertEqual([], errors)
            self.assertEqual({planned["receipt_id"]}, set(cold["index"]))


class SealRecoverySlowTests(unittest.TestCase):
    def test_hash_bound_pending_replays_idempotently_and_tamper_fails_closed(self):
        with _current_checkpoint() as (root, runtime, history_receipt):
            pending = _pending(root, runtime)
            entry, _pending_path = _begin(root, pending)
            index_path = root / kblib.RECEIPT_COLD_INDEX_PATH
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text('{"torn":', encoding="utf-8")

            errors = []
            loaded = seal_receipts._load_pending(str(root), entry, errors)
            self.assertEqual([], errors)
            self.assertIsNotNone(loaded)
            seal_receipts._publish(str(root), loaded)
            seal_receipts._publish(str(root), loaded)
            _catalog, cold, errors = _cold_result(
                root, loaded["receipt"])
            self.assertEqual([], errors)
            self.assertEqual(
                {history_receipt["receipt_id"]}, set(cold["index"]))

        with _current_checkpoint() as (root, runtime, _receipt):
            pending = _pending(root, runtime)
            entry, pending_path = _begin(root, pending)
            body = json.loads(pending_path.read_text(encoding="utf-8"))
            body["edits"] = []
            pending_path.write_text(
                json.dumps(body, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            errors = []
            self.assertIsNone(
                seal_receipts._load_pending(str(root), entry, errors))
            self.assertTrue(any("hashes to" in error for error in errors))


class ColdReceiptStoreIntegrationTests(unittest.TestCase):
    """One consumer-owned mutation matrix at the adjacent seal handoff."""

    def test_current_cold_chain_rejects_integrity_and_path_mutations(self):
        mutations = (
            "segment-byte-drift",
            "forged-index-row",
            "missing-seal-root",
            "cold-directory-symlink",
            "segment-hardlink",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with _current_checkpoint() as (root, runtime, _receipt):
                    seal_receipt = _apply(root, runtime)
                    include_seal = mutation != "missing-seal-root"
                    if mutation == "segment-byte-drift":
                        segment = _sealed_segment(root)
                        text = segment.read_text(encoding="utf-8")
                        edited = text.replace(
                            '"result": "pass"', '"result": "fail"', 1)
                        self.assertEqual(len(text), len(edited))
                        segment.write_text(edited, encoding="utf-8")
                        expected = "manifest sealed"
                    elif mutation == "forged-index-row":
                        index_path = root / kblib.RECEIPT_COLD_INDEX_PATH
                        row = json.loads(index_path.read_text(
                            encoding="utf-8").splitlines()[0])
                        row["receipt_id"] = "audit-forged-current-probe"
                        with index_path.open("a", encoding="utf-8") as handle:
                            handle.write(json.dumps(
                                row, ensure_ascii=False,
                                sort_keys=True) + "\n")
                        expected = "index rows attributed"
                    elif mutation == "missing-seal-root":
                        expected = "absent from the hot catalog"
                    elif mutation == "cold-directory-symlink":
                        cold = root / kblib.RECEIPT_COLD_PREFIX
                        elsewhere = root / ".cambium/receipts/cold-aside"
                        cold.rename(elsewhere)
                        cold.symlink_to(elsewhere, target_is_directory=True)
                        expected = "symlink"
                    else:
                        segment = _sealed_segment(root)
                        os.link(segment, str(segment) + ".twin")
                        expected = "hard links"

                    _catalog, _cold, errors = _cold_result(
                        root, seal_receipt, include_seal=include_seal)
                    self.assertTrue(
                        any(expected in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
