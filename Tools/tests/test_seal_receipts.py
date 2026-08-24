"""The cold chain keeps every byte and drops the parse cost, fail-closed.

The incident: an adopter's shared close register reached 63MB because every
close attempt appended full candidate detail three times over, and the
close transition re-deserialized all of it on every run.  The close
transition did not complete through the active execution channel.  Sealing
is the structural answer: verified frozen rows move verbatim into cold
segments, thin projections keep every ID resolvable, and the hot path
never parses the archive again.

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

Nearly every test here needs the same prologue -- close B1, often seal it
-- and replaying that prologue through the CLI for each test cost more
than every assertion combined.  The prologue is therefore walked once per
distinct scenario and kept as a template tree: tests that only read a
scenario share one tree, and tests that injure it each start from a
fresh copy.  A copy is honest because every path the chain records is
root-relative; the probe for that claim is the whole suite passing from
copied roots.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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


# A seal that dies mid-publication must leave a state the tool can finish,
# not one an operator has to reason about.  Proving that needs a writer that
# really stops -- an exception unwinds the interpreter and runs cleanup, and
# the recovery path deliberately refuses to adopt a lock whose owner process
# is still alive -- so each boundary is injured in a child that calls
# ``os._exit`` with the lock and journal exactly as a power cut would leave
# them.
CRASH_SCRIPT = r'''
import os, sys
sys.path.insert(0, %(tools)r)
sys.path.insert(0, %(tests)r)
import kblib, check_queue, seal_receipts

root, point = sys.argv[1], sys.argv[2]


def die():
    sys.stdout.flush()
    os._exit(97)


manifest = kblib.RECEIPT_COLD_MANIFEST_PATH
index = kblib.RECEIPT_COLD_INDEX_PATH
journal = kblib.RECEIPT_COLD_JOURNAL_PATH

real_publish = seal_receipts._publish
real_append = seal_receipts._append_lines
real_atomic = seal_receipts._write_atomic
real_receipts = kblib.write_receipts_observed
real_complete = seal_receipts._require_publication_complete
state = {"segments": 0, "rewrites": 0}


def publish(root_, pending):
    if point == "journal-begin":
        die()
    if point == "segments":
        for row in pending["manifest_rows"]:
            if row["kind"] != "sealed-receipts":
                continue
            full = os.path.join(root_, row["segment"])
            os.makedirs(os.path.dirname(full), mode=0o700, exist_ok=True)
            payload = seal_receipts._segment_payload_from_source(
                root_, row, pending["index_lines"])
            with open(full, "xb") as handle:
                handle.write(payload)
            die()
    return real_publish(root_, pending)


def receipts(path, records, **kwargs):
    if point == "seal-receipt":
        die()
    return real_receipts(path, records, **kwargs)


def append(path, lines):
    if point == "manifest" and path.endswith(os.path.basename(manifest)):
        die()
    if point == "torn-index-line" and path.endswith(os.path.basename(index)):
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(lines[0][:20] if lines else "{")
            handle.flush()
        die()
    real_append(path, lines)
    if point == "index" and path.endswith(os.path.basename(index)):
        die()
    if point == "complete" and path.endswith(os.path.basename(journal)):
        if any('"complete"' in line for line in lines):
            die()


def atomic(path, text):
    if point == "registers":
        die()
    if point == "torn-rewrite":
        temporary = path + ".seal-rewrite"
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text[:len(text) // 3])
            handle.flush()
        die()
    real_atomic(path, text)
    state["rewrites"] += 1
    if point == "rewrite":
        die()


seal_receipts._publish = publish
seal_receipts._append_lines = append
seal_receipts._write_atomic = atomic
seal_receipts._require_publication_complete = real_complete
kblib.write_receipts_observed = receipts

result = check_queue.validate_runtime(root)
by_file = seal_receipts.plan_seal(root, result)
seal_receipts.apply_seal(root, result, by_file,
                         seal_receipts.SEAL_RECEIPTS_PATH)
die()
'''


def _run_seal(root, *arguments):
    return subprocess.run(
        [sys.executable, str(TOOLS / "seal_receipts.py"),
         str(root), *arguments],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False)


class SealFixture(UpdateQueueTests):
    """Runs against the same live-writer fixture the queue suite uses."""

    def runTest(self):  # pragma: no cover - harness artifact
        pass

    def seal(self, *arguments):
        return _run_seal(self.root, *arguments)

    def close_b1(self):
        """Close B1 and leave one genuinely superseded B1 row to archive.

        The current Coverage owner now points at B1's Delta and page-review
        receipts.  Those receipts, and the complete close replay they need,
        must therefore remain hot until a later owner transition supersedes
        them.  Most tests in this class exercise the archive machinery rather
        than owner reachability, so give them an unrelated historical B1 row
        that is already unreferenced and may legitimately become cold.
        """
        completed = super().close_b1()
        self.append_receipt(
            "audit-superseded-b1-history", check="fixture_history",
            target="B1", batch_id="B1", tool="fixture",
            tool_version="1.0.0", checked_at="2026-08-04T03:01:00Z",
            details="superseded unreferenced fixture history")
        return completed

    def sealed_ids(self):
        index_path = self.root / kblib.RECEIPT_COLD_INDEX_PATH
        if not index_path.exists():
            return set()
        return {
            json.loads(line)["receipt_id"]
            for line in index_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

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

    def source_ids(self, relative):
        path = self.root / relative
        if not path.exists():
            return set()
        return {json.loads(line)["receipt_id"]
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()}

    def intruder_row(self, suffix="a"):
        return json.dumps({
            "receipt_id": "audit-intruder-20260814T000000Z-%s-0001" % suffix,
            "check": "probe", "target": ".", "result": "pass",
            "details": "a cooperating writer appended here",
            "checked_at": "2026-08-14T00:00:00Z", "tool": "probe",
            "tool_version": "1.0.0", "invalidated_by": None,
        }, ensure_ascii=False, sort_keys=True)

    CRASH_POINTS = (
        "journal-begin", "segments", "seal-receipt", "manifest", "index",
        "torn-index-line", "registers", "torn-rewrite", "rewrite", "complete",
    )

    def crash_child(self, point):
        """Seal in a child process that dies at one durable boundary."""
        script = CRASH_SCRIPT % {"tools": str(TOOLS), "tests": str(TESTS)}
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.root), point],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False)
        self.assertNotEqual(0, completed.returncode, completed.stdout)
        return completed

    def assert_recovers(self, point):
        interrupted = check_queue.validate_runtime(self.root)
        if point != "complete":
            self.assertTrue(
                any("never completed" in error or "interrupted seal" in error
                    for error in interrupted["errors"]),
                "%s: %r" % (point, interrupted["errors"]))
        completed = seal_receipts.main(
            [str(self.root), "--reconcile", "--apply"])
        self.assertEqual(0, completed, point)
        finished = check_queue.validate_runtime(self.root)
        self.assertEqual([], finished["errors"], point)
        self.assertTrue(self.sealed_ids(), point)
        self.assertEqual(0, self.seal("--verify").returncode, point)

    ATTESTATION_REGISTER = ".cambium/receipts/fixture.jsonl"
    CRAFTED_EVIDENCE = "%s/crafted-B1.jsonl" % kblib.RECEIPT_COLD_EVIDENCE_PREFIX

    def stock_evidence(self, payload):
        """Bind the real attestation to evidence with bytes worth tampering.

        The fixture's close accepts nothing, so its evidence file is empty
        and a same-length edit has nothing to edit.  The payload here holds
        no newline, so the attestation's record count stays the zero its
        accepted-candidate count already declares and only the two fields
        under test -- byte length and content hash -- change.
        """
        target = self.root / self.CRAFTED_EVIDENCE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        register = self.root / self.ATTESTATION_REGISTER
        records = [json.loads(line) for line in
                   register.read_text(encoding="utf-8").splitlines()
                   if line.strip()]
        bound = 0
        for record in records:
            if "candidate_evidence_path" not in record:
                continue
            record["candidate_evidence_path"] = self.CRAFTED_EVIDENCE
            record["candidate_evidence_sha256"] = kblib.sha256_bytes(payload)
            record["candidate_evidence_bytes"] = len(payload)
            record["candidate_evidence_records"] = payload.count(b"\n")
            bound += 1
        self.assertTrue(bound, "the close bundle binds candidate evidence")
        self.rewrite(self.ATTESTATION_REGISTER,
                     [json.dumps(record, ensure_ascii=False)
                      for record in records])
        return target


# ---------------------------------------------------------------------------
# Scenario templates.  Each distinct lifecycle prologue is walked once, into
# a frozen tree held for the whole run; tests take copies, never the tree.
# ---------------------------------------------------------------------------

_TEMPLATE_DIRS = []  # TemporaryDirectory handles, alive for the run
_CLOSED_ROOT = None
_SEALED_WALK = None


def _template_root():
    holder = tempfile.TemporaryDirectory(prefix="seal-template-")
    _TEMPLATE_DIRS.append(holder)
    return Path(holder.name) / "repo"


def closed_template_root():
    """Close B1 once -- open, merge, apply, gate, close -- and freeze it.

    This is the prologue every test below shares.  It is walked through the
    same helpers the queue suite uses, so its assertions run here too, once.
    """
    global _CLOSED_ROOT
    if _CLOSED_ROOT is None:
        builder = SealFixture("runTest")
        builder.setUp()
        try:
            builder.close_b1()
            root = _template_root()
            shutil.copytree(builder.root, root, symlinks=True)
        finally:
            builder.tearDown()
        _CLOSED_ROOT = root
    return _CLOSED_ROOT


class _SealedWalk(object):
    """One real seal of the closed tree, with every artifact of the walk.

    ``before`` is the full runtime validation of the closed tree the moment
    before the seal; ``applied``, ``verified`` and ``reapplied`` are the
    complete CLI results of the seal, its verification, and the idempotent
    second attempt.  The second attempt plans zero rows and writes nothing,
    so the tree after this walk is byte-for-byte the tree after ``applied``
    and copies taken from it are copies of a just-sealed archive.
    """

    def __init__(self):
        self.root = _template_root()
        shutil.copytree(closed_template_root(), self.root, symlinks=True)
        self.before = check_queue.validate_runtime(self.root)
        self.applied = _run_seal(self.root, "--apply")
        self.verified = _run_seal(self.root, "--verify")
        self.reapplied = _run_seal(self.root, "--apply")


def sealed_walk():
    global _SEALED_WALK
    if _SEALED_WALK is None:
        _SEALED_WALK = _SealedWalk()
    return _SEALED_WALK


class UnsealedFixtureTests(SealFixture):
    """Tests that need the live-writer fixture before any close.

    Nothing here is sealable yet, so each test builds the plain fixture
    tree the queue suite builds and shares no scenario with the classes
    below.
    """

    def test_current_coverage_property_evidence_stays_hot_after_batch_close(self):
        """A closed producer batch does not make current owner evidence cold."""
        current_id = "audit-page-review-current-owner"
        delta_id = "audit-delta-apply-current-owner"
        close_id = "audit-batch-close-b1"
        consistency_id = "audit-queue-consistency-b1"
        superseded_id = "audit-page-review-superseded"
        attestation_id = "audit-reviewer-attestation-b1"
        global_review_id = "audit-global-review-b1"
        closed_list_id = "audit-closed-list-b1"
        transition_id = "audit-close-transition-b1"
        relative = ".cambium/receipts/close-gates.jsonl"
        result = {
            "coverage": {
                "pages": [{
                    "path": "Topics/A.md",
                    "property_state": {
                        "last_reviewed": {
                            "value": "2026-08-20",
                            "evidence_receipt": current_id,
                            "content_fingerprint": "sha256:" + "a" * 64,
                        },
                    },
                }],
            },
            "items_by_id": {
                "B1": {
                    "id": "B1",
                    "state": "closed",
                    "transition_receipts": [transition_id],
                    "close_gate_receipt": close_id,
                    "queue_consistency_receipt": consistency_id,
                    "delta_apply_receipt": delta_id,
                },
            },
            "progress": {},
            "receipt_catalog": {
                current_id: (relative, {
                    "receipt_id": current_id,
                    "batch_id": "B1",
                    "check": "page_review_acceptance",
                    "reviewer_attestation_receipt": attestation_id,
                }),
                superseded_id: (relative, {
                    "receipt_id": superseded_id,
                    "batch_id": "B1",
                    "check": "page_review_acceptance",
                }),
                delta_id: (relative, {
                    "receipt_id": delta_id,
                    "batch_id": "B1",
                    "check": "delta_apply",
                }),
                close_id: (relative, {
                    "receipt_id": close_id,
                    "batch_id": "B1",
                    "check": "batch_close_gate",
                    "global_review_receipt": global_review_id,
                    "reviewer_attestation_receipt": attestation_id,
                    "page_review_receipts": [current_id],
                    "closed_list_evidence": {"links": closed_list_id},
                }),
                attestation_id: (relative, {
                    "receipt_id": attestation_id,
                    "check": "batch_global_review_attestation",
                }),
                global_review_id: (relative, {
                    "receipt_id": global_review_id,
                    "check": "batch_global_review",
                }),
                closed_list_id: (relative, {
                    "receipt_id": closed_list_id,
                    "check": "closed_list_links",
                }),
                consistency_id: (relative, {
                    "receipt_id": consistency_id,
                    "check": "required_queue",
                }),
                transition_id: (
                    ".cambium/receipts/queue-transitions.jsonl",
                    {
                        "receipt_id": transition_id,
                        "after_state": "closed",
                    },
                ),
            },
        }

        self.assertIn(current_id, seal_receipts._hot_reference_ids(result))
        self.assertNotIn(delta_id, seal_receipts._hot_reference_ids(result))
        self.assertIn(attestation_id,
                      seal_receipts._hot_reference_ids(result))
        planned = seal_receipts.plan_seal(str(self.root), result)
        planned_ids = {
            receipt_id for rows in planned.values()
            for receipt_id, _receipt in rows
        }
        self.assertNotIn(current_id, planned_ids)
        self.assertFalse(
            {close_id, consistency_id, delta_id, attestation_id,
             global_review_id, closed_list_id}.intersection(planned_ids),
            "a current owner reference keeps the hot close replay whole")
        self.assertIn(superseded_id, planned_ids)

    def test_open_batches_never_seal(self):
        self.open_b1()
        completed = self.seal()
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("nothing sealable", completed.stdout)


class SealedChainTests(SealFixture):
    """Asserts, many ways, against one shared walk of the whole chain.

    The walk -- close B1, seal the superseded history, verify the cold
    chain, then attempt a second seal -- ran once in ``sealed_walk()`` and
    kept its tree, exit codes and stdout.  Every test here reads that walk
    and writes nothing, so they may share it; anything that injures the
    sealed tree lives in ``SealedTreeTests`` and gets a private copy.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.walk = sealed_walk()

    def setUp(self):
        self.root = self.walk.root

    def tearDown(self):
        pass

    def test_sealing_keeps_current_owner_evidence_hot_and_runtime_clean(self):
        """Every live Coverage owner pointer survives a real seal run."""
        before = self.walk.before
        self.assertEqual([], before["errors"])
        current_property_evidence = {
            record.get("evidence_receipt")
            for page in before["coverage"].get("pages") or []
            for record in (page.get("property_state") or {}).values()
            if isinstance(record, dict)
        }
        self.assertTrue(current_property_evidence)
        current_attestations = {
            before["receipt_catalog"][receipt_id][1].get(
                "reviewer_attestation_receipt")
            for receipt_id in current_property_evidence
            if (receipt_id in before["receipt_catalog"] and
                before["receipt_catalog"][receipt_id][1].get("check") ==
                "page_review_acceptance")
        }
        current_attestations.discard(None)
        completed = self.walk.applied
        self.assertEqual(0, completed.returncode, completed.stdout)
        sealed = self.sealed_ids()
        self.assertFalse(current_property_evidence.intersection(sealed))
        self.assertFalse(current_attestations.intersection(sealed))
        after = check_queue.validate_runtime(self.root)
        self.assertEqual([], after["errors"])
        for receipt_id in current_property_evidence | current_attestations:
            self.assertIn(receipt_id, after["receipt_catalog"])

    def test_verify_proves_sealed_bytes_against_the_manifest(self):
        self.assertEqual(0, self.walk.applied.returncode)
        completed = self.walk.verified
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("match their manifest hashes", completed.stdout)

    def test_a_sealed_receipt_refuses_live_field_revalidation(self):
        """The fail-closed rule for consumers without a sealed branch."""
        self.assertEqual(0, self.walk.applied.returncode)
        result = check_queue.validate_runtime(self.root)
        errors = []
        receipt = check_queue.require_receipt(
            result["receipt_catalog"], "audit-superseded-b1-history",
            "sealed-consumer probe", errors,
            expected={"merged_snapshot_sha256": "sha256:" + "0" * 64})
        self.assertIsNone(receipt)
        self.assertTrue(any("sealed" in error for error in errors), errors)

    def test_transition_history_and_activation_stay_hot(self):
        """The never-seal set holds the global state spine."""
        self.assertEqual(0, self.walk.applied.returncode)
        result = check_queue.validate_runtime(self.root)
        item = result["items_by_id"]["B1"]
        for receipt_id in item.get("transition_receipts") or []:
            self.assertIn(receipt_id, result["receipt_catalog"])
        self.assertIn(item["activation_receipt"],
                      result["receipt_catalog"])

    def test_sealing_is_idempotent_when_nothing_new_is_sealable(self):
        self.assertEqual(0, self.walk.applied.returncode)
        completed = self.walk.reapplied
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("nothing seal", completed.stdout.lower())


class ClosedTreeTests(SealFixture):
    """Injures the moment between the close and the seal.

    Every test here mutates a closed-but-unsealed tree -- corrupting the
    queue, racing the lock window, crashing the writer, tampering with
    close evidence -- so none may share one.  Each starts from a fresh
    copy of the closed-B1 template instead of replaying the close.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(closed_template_root(), self.root, symlinks=True)

    def test_sealing_refuses_a_runtime_with_errors(self):
        """A bundle that cannot replay hot cannot claim the shortcut."""
        queue_path = self.root / check_queue.QUEUE_PATH
        text = queue_path.read_text(encoding="utf-8")
        queue_path.write_text(
            text.replace("state_revision: ", "state_revision: 9",
                         1), encoding="utf-8")
        completed = self.seal("--apply")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("pre-seal runtime validation", completed.stdout)
        self.assertEqual(set(), self.sealed_ids())

    # -- the lock window --------------------------------------------------

    def test_a_concurrent_append_between_plan_and_lock_writes_nothing(self):
        """The plan is compared byte for byte before the swap."""
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
            self.root)["_writer_locks"])

    # -- the append that a rewrite must never swallow ---------------------

    def test_an_append_landing_inside_the_rewrite_window_survives(self):
        """The reproduction: append after the hash check, before the swap.

        A writer that bypasses the append mutex still must not lose its
        row.  The rewrite carries the unplanned tail across instead of
        installing an image computed before it existed.
        """
        result = check_queue.validate_runtime(self.root)
        by_file = seal_receipts.plan_seal(self.root, result)
        target = sorted(by_file)[0]
        row = self.intruder_row()
        original_plan = seal_receipts._plan_payload

        def plan_then_intrude(root, res, files, stamp):
            planned = original_plan(root, res, files, stamp)
            with open(self.root / target, "a", encoding="utf-8") as handle:
                handle.write(row + "\n")
            return planned

        seal_receipts._plan_payload = plan_then_intrude
        try:
            receipt = seal_receipts.apply_seal(
                self.root, result, by_file,
                seal_receipts.SEAL_RECEIPTS_PATH)
        finally:
            seal_receipts._plan_payload = original_plan
        self.assertIsNotNone(receipt)
        self.assertIn(json.loads(row)["receipt_id"], self.source_ids(target),
                      "a seal may remove only the rows it sealed")

    def test_an_append_cannot_start_while_a_seal_holds_the_mutex(self):
        """The protocol itself: both sides take one exclusive marker."""
        register = ".cambium/receipts/concurrent.jsonl"
        row = self.intruder_row("b")
        script = (
            "import json, sys; sys.path.insert(0, %r)\n"
            "import kblib\n"
            "kblib.write_receipts(%r, [json.loads(%r)])\n"
            % (str(TOOLS), str(self.root / register), row))
        started = []

        def plan_then_race(root, res, files, stamp):
            planned = seal_receipts._plan_payload_original(
                root, res, files, stamp)
            started.append(subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
            time.sleep(0.4)
            self.assertIsNone(started[0].poll(),
                              "an appender must wait for the seal, not race it")
            return planned

        seal_receipts._plan_payload_original = seal_receipts._plan_payload
        seal_receipts._plan_payload = plan_then_race
        try:
            result = check_queue.validate_runtime(self.root)
            by_file = seal_receipts.plan_seal(self.root, result)
            self.assertIsNotNone(seal_receipts.apply_seal(
                self.root, result, by_file,
                seal_receipts.SEAL_RECEIPTS_PATH))
        finally:
            seal_receipts._plan_payload = \
                seal_receipts._plan_payload_original
        self.assertEqual(0, started[0].wait(timeout=30))
        self.assertIn(json.loads(row)["receipt_id"],
                      self.source_ids(register))
        self.assertEqual("free", kblib.receipt_append_mutex_state(self.root))

    # -- interruption: one crash per durable boundary ----------------------

    def test_every_durable_boundary_recovers(self):
        """One crash per publication step; each must reconcile to clean."""
        for point in self.CRASH_POINTS:
            with self.subTest(point=point):
                self.setUp()
                self.crash_child(point)
                self.assert_recovers(point)

    def test_reconcile_refuses_while_the_writer_is_alive(self):
        """A live seal is not a corpse; --reconcile will not rob it."""
        result = check_queue.validate_runtime(self.root)
        by_file = seal_receipts.plan_seal(self.root, result)
        original = seal_receipts._publish

        def explode(root, pending):
            raise RuntimeError("stop after the journal begin")

        seal_receipts._publish = explode
        try:
            with self.assertRaises(RuntimeError):
                seal_receipts.apply_seal(
                    self.root, result, by_file,
                    seal_receipts.SEAL_RECEIPTS_PATH)
        finally:
            seal_receipts._publish = original
        self.assertEqual(1, seal_receipts.main(
            [str(self.root), "--reconcile", "--apply"]),
            "the owner pid is this still-running process")

    def test_a_tampered_pending_record_fails_before_the_first_write(self):
        self.crash_child("journal-begin")
        pending_dir = self.root / seal_receipts.COLD_PENDING_PREFIX
        record = sorted(pending_dir.glob("*.json"))[0]
        data = json.loads(record.read_text(encoding="utf-8"))
        data["edits"] = []
        record.write_text(json.dumps(data, ensure_ascii=False,
                                     sort_keys=True), encoding="utf-8")
        self.assertEqual(1, seal_receipts.main(
            [str(self.root), "--reconcile", "--apply"]))
        self.assertEqual(set(), self.sealed_ids())

    # -- born-cold evidence ------------------------------------------------

    def test_a_same_length_edit_to_close_evidence_fails_closed(self):
        """Externalized detail is bound by hash, not by length."""
        evidence = self.stock_evidence(b'{"acceptance":"accepted"}')
        self.assertEqual([], check_queue.validate_runtime(
            self.root)["errors"], "the rebound attestation starts clean")
        before = evidence.read_bytes()
        edited = b'{"acceptance":"rejectd"}!'
        self.assertEqual(len(edited), len(before), "the edit keeps the length")
        evidence.write_bytes(edited)
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("candidate evidence file" in error and
                            "hashes to" in error
                            for error in result["errors"]), result["errors"])

    def test_tampered_close_evidence_cannot_be_sealed(self):
        """A seal must not mint a manifest hash for laundered bytes."""
        evidence = self.stock_evidence(b'{"acceptance":"accepted"}')
        evidence.write_bytes(b'{"acceptance":"rejectd"}!')
        completed = self.seal("--apply")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual(set(), self.sealed_ids())

    def test_a_seal_of_only_born_cold_evidence_writes_a_valid_namespace(self):
        """Manifest rows with no projections still need an index file."""
        original = seal_receipts.plan_seal
        seal_receipts.plan_seal = lambda root, result: {}
        try:
            result = check_queue.validate_runtime(self.root)
            self.assertEqual([], result["errors"])
            receipt = seal_receipts.apply_seal(
                self.root, result, {}, seal_receipts.SEAL_RECEIPTS_PATH)
        finally:
            seal_receipts.plan_seal = original
        self.assertIsNotNone(receipt)
        self.assertEqual(0, receipt["index_rows"])
        self.assertTrue((self.root / kblib.RECEIPT_COLD_INDEX_PATH).exists())
        self.assertEqual([], check_queue.validate_runtime(
            self.root)["errors"])
        self.assertEqual(0, self.seal("--verify").returncode)

    def test_verify_fails_while_a_seal_is_only_begun(self):
        """Manifest-absent is innocent only when the journal is balanced."""
        self.crash_child("journal-begin")
        self.assertFalse(
            (self.root / kblib.RECEIPT_COLD_MANIFEST_PATH).exists())
        completed = self.seal("--verify")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("never completed", completed.stdout)


class SealedTreeTests(SealFixture):
    """Injures a just-sealed archive; every test gets a private copy.

    Each test here edits, deletes, forges or re-links some piece of the
    sealed cold chain and proves the runtime fails closed, so none may
    share a tree.  Each starts from a fresh copy of the sealed-walk
    template; ``seal_apply`` is that walk's recorded CLI result, standing
    where each test used to run the identical seal itself.
    """

    def setUp(self):
        walk = sealed_walk()
        self.seal_apply = walk.applied
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(walk.root, self.root, symlinks=True)

    def test_a_missing_cold_segment_fails_every_run_closed(self):
        self.assertEqual(0, self.seal_apply.returncode)
        segment = self.sealed_segment()
        os.rename(self.root / segment,
                  self.root / (segment + ".misplaced"))
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("is missing" in error and "fail-closed" in error
                            for error in result["errors"]),
                        result["errors"])

    def test_a_size_drifted_segment_fails_closed(self):
        self.assertEqual(0, self.seal_apply.returncode)
        segment = self.sealed_segment()
        with open(self.root / segment, "a", encoding="utf-8") as handle:
            handle.write("\n")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("may not drift" in error
                            for error in result["errors"]),
                        result["errors"])
        completed = self.seal("--verify")
        self.assertEqual(1, completed.returncode, completed.stdout)

    # -- the fail-open that shipped first --------------------------------

    def test_a_same_length_edit_to_a_sealed_record_fails_closed(self):
        """Presence and size prove nothing about content."""
        self.assertEqual(0, self.seal_apply.returncode)
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
        self.assertEqual(0, self.seal_apply.returncode)
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
        self.assertEqual(0, self.seal_apply.returncode)
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
        self.assertEqual(0, self.seal_apply.returncode)
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
        self.assertEqual(0, self.seal_apply.returncode)
        orphan = (self.root / kblib.RECEIPT_COLD_SEGMENT_PREFIX /
                  "batch-close-19700101T000000Z.jsonl")
        orphan.write_text("{}\n", encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("is in no manifest row" in error
                            for error in result["errors"]),
                        result["errors"])

    def test_a_seal_receipt_removed_from_the_hot_register_fails_closed(self):
        """The chain's root of trust is a receipt, and it never seals."""
        self.assertEqual(0, self.seal_apply.returncode)
        receipts = self.root / ".cambium/receipts/seal-receipts.jsonl"
        receipts.write_text("", encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(
            any("absent from the hot catalog" in error
                for error in result["errors"]), result["errors"])

    # -- the archive must stay inside the repository -----------------------

    def test_a_symlinked_cold_directory_fails_closed(self):
        self.assertEqual(0, self.seal_apply.returncode)
        cold = self.root / kblib.RECEIPT_COLD_PREFIX
        elsewhere = Path(str(self.root) + "-cold-elsewhere")
        os.rename(cold, elsewhere)
        os.symlink(elsewhere, cold)
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("symlink" in error for error in result["errors"]),
                        result["errors"])

    def test_a_symlinked_segments_directory_fails_closed(self):
        """An intermediate component is checked, not just the leaf."""
        self.assertEqual(0, self.seal_apply.returncode)
        segments = self.root / kblib.RECEIPT_COLD_SEGMENT_PREFIX
        elsewhere = Path(str(self.root) + "-segments-elsewhere")
        os.rename(segments, elsewhere)
        os.symlink(elsewhere, segments)
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("symlink" in error for error in result["errors"]),
                        result["errors"])

    def test_a_hard_linked_cold_segment_fails_closed(self):
        """A second name for sealed bytes is a second writer for them."""
        self.assertEqual(0, self.seal_apply.returncode)
        segment = self.root / self.sealed_segment()
        os.link(segment, str(segment) + ".twin")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("hard link" in error
                            for error in result["errors"]), result["errors"])

    # -- the writer behind the archive -------------------------------------

    def test_an_unsupported_seal_producer_fails_closed(self):
        self.assertEqual(0, self.seal_apply.returncode)
        register = self.root / ".cambium/receipts/seal-receipts.jsonl"
        rows = [json.loads(line) for line in
                register.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        rows[0]["tool_version"] = "0.9.0"
        self.rewrite(".cambium/receipts/seal-receipts.jsonl",
                     [json.dumps(row, ensure_ascii=False) for row in rows])
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("not a supported sealing protocol" in error
                            for error in result["errors"]), result["errors"])
        self.assertEqual({}, result["receipt_catalog"].cold)


SEAL_TEST_CLASSES = (
    UnsealedFixtureTests,
    SealedChainTests,
    ClosedTreeTests,
    SealedTreeTests,
)


def load_tests(loader, standard_tests, pattern):
    """Collect this module's seal tests without replaying its fixture tests.

    Every class here inherits ``UpdateQueueTests`` for its transaction
    fixture and helpers.  Default discovery also collects the imported base
    class and every inherited ``test_*`` method, so the update-queue suite ran
    twice here in addition to its canonical run in ``test_update_queue.py``.
    Only methods declared by these subclasses are seal-specific coverage.
    """
    suite = loader.suiteClass()
    for test_class in SEAL_TEST_CLASSES:
        names = [
            name for name in loader.getTestCaseNames(test_class)
            if name in test_class.__dict__]
        suite.addTests(test_class(name) for name in names)
    return suite


if __name__ == "__main__":
    unittest.main()
