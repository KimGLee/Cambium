"""The cold chain keeps every byte and drops the parse cost, fail-closed.

The incident: an adopter's shared close register reached 63MB because every
close attempt appended full candidate detail three times over, and the
close transition re-deserialized all of it on every run -- 75 seconds of
CPU against a 45-second execution channel.  Sealing is the structural
answer: verified frozen rows move verbatim into cold segments, thin
projections keep every ID resolvable, and the hot path never parses the
archive again.

The near-miss these tests exist for is the first version of that answer,
which checked only that each segment was present at its recorded byte
size.  A same-length edit to a sealed verdict passed silently, and the
projections consumers actually read -- ordinary lines in an ordinary
editable file -- were checked against nothing at all.  So these tests pin
the integrity edges as hard as the behaviour: content drift at constant
size fails closed, an edited or forged projection fails closed, a
manifest row deleted from under its seal receipt fails closed, an
unreferenced segment fails closed, an interrupted seal fails closed and
finishes deterministically, and a seal planned on bytes that changed
before the writer lock writes nothing at all.
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
for path in (str(TOOLS), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import kblib  # noqa: E402
import check_queue  # noqa: E402
import seal_receipts  # noqa: E402
from test_update_queue import UpdateQueueTests  # noqa: E402


class SealReceiptsTests(UpdateQueueTests):
    """Runs against the same live-writer fixture the queue suite uses."""

    def runTest(self):  # pragma: no cover - harness artifact
        pass

    def seal(self, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS / "seal_receipts.py"),
             str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False)

    def sealed_ids(self):
        index_path = self.root / kblib.RECEIPT_COLD_INDEX_PATH
        if not index_path.exists():
            return set()
        return {
            json.loads(line)["receipt_id"]
            for line in index_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    def test_sealing_a_closed_batch_keeps_the_runtime_clean(self):
        """The trio moves cold; the full validation stays green."""
        self.close_b1()
        before = check_queue.validate_runtime(self.root)
        self.assertEqual([], before["errors"])
        item = before["items_by_id"]["B1"]
        trio = {item["close_gate_receipt"],
                item["queue_consistency_receipt"],
                item["delta_apply_receipt"]}
        completed = self.seal("--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        sealed = self.sealed_ids()
        self.assertTrue(trio.issubset(sealed),
                        "the close bundle trio seals together")
        after = check_queue.validate_runtime(self.root)
        self.assertEqual([], after["errors"])
        for receipt_id in trio:
            self.assertNotIn(receipt_id, after["receipt_catalog"],
                             "sealed rows leave the hot catalog")
            self.assertIn(receipt_id, after["receipt_catalog"].cold)

    def test_sealing_refuses_a_runtime_with_errors(self):
        """A bundle that cannot replay hot cannot claim the shortcut."""
        self.close_b1()
        queue_path = self.root / check_queue.QUEUE_PATH
        text = queue_path.read_text(encoding="utf-8")
        queue_path.write_text(
            text.replace("state_revision: ", "state_revision: 9",
                         1), encoding="utf-8")
        completed = self.seal("--apply")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("pre-seal runtime validation", completed.stdout)
        self.assertEqual(set(), self.sealed_ids())

    def test_a_missing_cold_segment_fails_every_run_closed(self):
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        manifest = [
            json.loads(line) for line in
            (self.root / kblib.RECEIPT_COLD_MANIFEST_PATH)
            .read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        segment = next(row["segment"] for row in manifest
                       if row["kind"] == "sealed-receipts")
        os.rename(self.root / segment,
                  self.root / (segment + ".misplaced"))
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("is missing" in error and "fail-closed" in error
                            for error in result["errors"]),
                        result["errors"])

    def test_a_size_drifted_segment_fails_closed(self):
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        manifest = [
            json.loads(line) for line in
            (self.root / kblib.RECEIPT_COLD_MANIFEST_PATH)
            .read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        segment = next(row["segment"] for row in manifest
                       if row["kind"] == "sealed-receipts")
        with open(self.root / segment, "a", encoding="utf-8") as handle:
            handle.write("\n")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("may not drift" in error
                            for error in result["errors"]),
                        result["errors"])
        completed = self.seal("--verify")
        self.assertEqual(1, completed.returncode, completed.stdout)

    def test_verify_proves_sealed_bytes_against_the_manifest(self):
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        completed = self.seal("--verify")
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("match their manifest hashes", completed.stdout)

    # -- the fail-open that shipped first --------------------------------

    def manifest_rows(self):
        return [json.loads(line) for line in
                (self.root / kblib.RECEIPT_COLD_MANIFEST_PATH)
                .read_text(encoding="utf-8").splitlines() if line.strip()]

    def sealed_segment(self):
        return next(row["segment"] for row in self.manifest_rows()
                    if row["kind"] == "sealed-receipts")

    def rewrite(self, relative, lines):
        (self.root / relative).write_text(
            "".join(line + "\n" for line in lines), encoding="utf-8")

    def test_a_same_length_edit_to_a_sealed_record_fails_closed(self):
        """Presence and size prove nothing about content."""
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        segment = self.root / self.sealed_segment()
        text = segment.read_text(encoding="utf-8")
        self.assertIn('"result": "pass"', text)
        edited = text.replace('"result": "pass"', '"result": "fail"', 1)
        self.assertEqual(len(edited), len(text), "the edit keeps the length")
        segment.write_text(edited, encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(
            any("does not match the hash the manifest sealed" in error
                for error in result["errors"]), result["errors"])
        self.assertEqual(1, self.seal("--verify").returncode)

    def test_an_edited_projection_fails_closed(self):
        """The index is an ordinary editable file, so it is proved too."""
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        index = kblib.RECEIPT_COLD_INDEX_PATH
        lines = (self.root / index).read_text(
            encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines]
        target = next(row for row in rows if row.get("result") == "pass")
        target["result"] = "fail"
        self.rewrite(index, [
            json.dumps(row, ensure_ascii=False, sort_keys=True)
            for row in rows])
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(
            any("index rows attributed to seal" in error
                for error in result["errors"]), result["errors"])

    def test_a_forged_projection_cannot_manufacture_a_receipt(self):
        """Appending a row nobody sealed does not create evidence."""
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        index = self.root / kblib.RECEIPT_COLD_INDEX_PATH
        rows = [json.loads(line) for line in
                index.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        forged = dict(rows[0])
        forged["receipt_id"] = "audit-forged-00000000T000000Z-dead-0001"
        with open(index, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(forged, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        result = check_queue.validate_runtime(self.root)
        self.assertNotIn(forged["receipt_id"],
                         result["receipt_catalog"].cold)
        self.assertTrue(
            any("index rows attributed to seal" in error
                for error in result["errors"]), result["errors"])

    def test_a_deleted_manifest_row_fails_closed(self):
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        manifest = kblib.RECEIPT_COLD_MANIFEST_PATH
        lines = (self.root / manifest).read_text(
            encoding="utf-8").splitlines()
        self.rewrite(manifest, lines[1:])
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(
            any("manifest rows attributed to seal" in error
                for error in result["errors"]), result["errors"])

    def test_a_segment_no_manifest_row_names_fails_closed(self):
        """An unreferenced segment is an interrupted seal, not spare bytes."""
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        orphan = (self.root / kblib.RECEIPT_COLD_SEGMENT_PREFIX /
                  "batch-close-19700101T000000Z.jsonl")
        orphan.write_text("{}\n", encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("is in no manifest row" in error
                            for error in result["errors"]),
                        result["errors"])

    def test_a_seal_receipt_removed_from_the_hot_register_fails_closed(self):
        """The chain's root of trust is a receipt, and it never seals."""
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        receipts = self.root / ".cambium/receipts/seal-receipts.jsonl"
        receipts.write_text("", encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(
            any("absent from the hot catalog" in error
                for error in result["errors"]), result["errors"])

    # -- the lock window --------------------------------------------------

    def test_a_concurrent_append_between_plan_and_lock_writes_nothing(self):
        """The plan is compared byte for byte before the swap."""
        self.close_b1()
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        by_file = seal_receipts.plan_seal(self.root, result)
        self.assertTrue(by_file)
        before_tree = seal_receipts._receipt_tree_fingerprint(self.root)
        intruder = self.root / ".cambium/receipts/concurrent.jsonl"
        intruder.write_text(json.dumps({
            "receipt_id": "audit-intruder-20260814T000000Z-abcd-0001",
            "check": "probe", "target": ".", "result": "pass",
            "details": "a cooperating writer appended here",
            "checked_at": "2026-08-14T00:00:00Z", "tool": "probe",
            "tool_version": "1.0.0", "invalidated_by": None,
        }, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            seal_receipts.apply_seal(
                self.root, result, by_file,
                seal_receipts.SEAL_RECEIPTS_PATH, before_tree)
        self.assertIn("receipt tree changed", str(caught.exception))
        self.assertEqual(set(), self.sealed_ids())
        self.assertFalse(
            (self.root / kblib.RECEIPT_COLD_MANIFEST_PATH).exists())
        self.assertEqual([], check_queue.validate_runtime(
            self.root)["writer_locks"])

    # -- interruption -----------------------------------------------------

    def test_an_interrupted_seal_fails_closed_and_reconciles(self):
        """A begin with no complete is loud, and finishable."""
        self.close_b1()
        result = check_queue.validate_runtime(self.root)
        by_file = seal_receipts.plan_seal(self.root, result)
        boom = RuntimeError("power cut after the journal begin")

        def explode(root, pending):
            raise boom

        original = seal_receipts._publish
        seal_receipts._publish = explode
        try:
            with self.assertRaises(RuntimeError):
                seal_receipts.apply_seal(
                    self.root, result, by_file,
                    seal_receipts.SEAL_RECEIPTS_PATH)
        finally:
            seal_receipts._publish = original
        interrupted = check_queue.validate_runtime(self.root)
        self.assertTrue(any("never completed" in error
                            for error in interrupted["errors"]),
                        interrupted["errors"])
        self.assertTrue(interrupted["writer_locks"],
                        "an interrupted writer leaves its lock standing")
        self.assertEqual(0, seal_receipts.main(
            [str(self.root), "--reconcile", "--apply"]))
        finished = check_queue.validate_runtime(self.root)
        self.assertEqual([], finished["errors"])
        self.assertTrue(self.sealed_ids())

    def test_a_sealed_receipt_refuses_live_field_revalidation(self):
        """The fail-closed rule for consumers without a sealed branch."""
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        result = check_queue.validate_runtime(self.root)
        item = result["items_by_id"]["B1"]
        errors = []
        receipt = check_queue._require_receipt(
            result["receipt_catalog"], item["close_gate_receipt"],
            "sealed-consumer probe", errors,
            expected={"merged_snapshot_sha256": "sha256:" + "0" * 64})
        self.assertIsNone(receipt)
        self.assertTrue(any("sealed" in error for error in errors), errors)

    def test_transition_history_and_activation_stay_hot(self):
        """The never-seal set holds the global state spine."""
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        result = check_queue.validate_runtime(self.root)
        item = result["items_by_id"]["B1"]
        for receipt_id in item.get("transition_receipts") or []:
            self.assertIn(receipt_id, result["receipt_catalog"])
        self.assertIn(item["activation_receipt"],
                      result["receipt_catalog"])

    def test_sealing_is_idempotent_when_nothing_new_is_sealable(self):
        self.close_b1()
        self.assertEqual(0, self.seal("--apply").returncode)
        completed = self.seal("--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("nothing seal", completed.stdout.lower())

    def test_open_batches_never_seal(self):
        self.open_b1()
        completed = self.seal()
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("nothing sealable", completed.stdout)


if __name__ == "__main__":
    unittest.main()
