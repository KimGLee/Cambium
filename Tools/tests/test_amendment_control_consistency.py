"""Two Amendment-log defects that lived between tools, not inside one.

Each fix pins an agreement between two readers of the same Progress row.

First: K13/06 withdrawal is final -- "a withdrawn operational Amendment ...
authorizes nothing" -- and `check_queue` validates it as a terminal state.
`update_task._pending_controls` counted the same row as pending, because
`withdrawn` was absent from its final-status vocabulary. One withdrawn
registration therefore blocked every later task transition forever: the exact
wedge the withdrawal action was added to prevent, reintroduced one tool over.

Second: `check_queue._operational_amendment_registration_errors` returned no
errors for a row whose `operation` it did not recognize. The registration
binding below that guard is the entire evidence chain -- plan bytes, receipt,
three-state fingerprints -- so an unknown operation name was a way to hold an
`approved` row bound to nothing. A row with no `operation` at all is an
ordinary Guidance log entry and owes no binding; a row that *claims* one must
claim one the validator knows.

These are regression tests against the two-reader disagreements; neither adds
a rule of its own.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import check_queue  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(
        "_%s_under_test" % name, TOOLS / ("%s.py" % name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update_task = _load("update_task")


def progress_with(amendments):
    return {"guidance_queue": [], "amendments": amendments}


WITHDRAWN_ROW = {
    "id": "AM-001",
    "date": "2026-08-10",
    "summary": "registered against a stale plan; withdrawn per K13/06",
    "status": "withdrawn",
    "writeback_done": False,
    "withdrawal_reason": "planned final state failed deterministic checks",
}


class WithdrawnIsFinalInBothReaders(unittest.TestCase):
    def test_a_withdrawn_amendment_does_not_block_task_transitions(self):
        _guidance, pending = update_task._pending_controls(
            progress_with([dict(WITHDRAWN_ROW)]))
        self.assertEqual(
            [], pending,
            "check_queue treats a withdrawn registration as terminal and "
            "K13/06 says it authorizes nothing; counting it as pending here "
            "would let one withdrawn row wedge every future transition")

    def test_a_genuinely_pending_amendment_still_blocks(self):
        row = dict(WITHDRAWN_ROW)
        row.update({"status": "approved", "writeback_done": False})
        del row["withdrawal_reason"]
        _guidance, pending = update_task._pending_controls(
            progress_with([row]))
        self.assertEqual(["AM-001"], pending)

    def test_withdrawn_with_writeback_true_is_not_silently_final(self):
        """The malformed shape stays visible rather than gaining finality."""
        row = dict(WITHDRAWN_ROW)
        row["writeback_done"] = True
        _guidance, pending = update_task._pending_controls(
            progress_with([row]))
        self.assertEqual(
            ["AM-001"], pending,
            "check_queue rejects withdrawn/writeback-true as an invalid "
            "state; update_task must not treat the same bytes as settled")


class UnknownOperationFailsClosed(unittest.TestCase):
    def run_validator(self, amendment):
        return check_queue._operational_amendment_registration_errors(
            {}, amendment, "Progress amendments[0]", {}, {}, {},
            "sha256:" + "0" * 64, "sha256:" + "0" * 64, "sha256:" + "0" * 64)

    def test_an_unknown_operation_is_an_error_not_an_exemption(self):
        errors = self.run_validator({
            "id": "AM-002", "date": "2026-08-10",
            "summary": "novel operation", "status": "approved",
            "writeback_done": False, "operation": "policy-exception",
        })
        self.assertTrue(errors, "an unrecognized operation skipped every "
                                "registration binding; that is authorization "
                                "held with no registered evidence")
        self.assertIn("unknown operation", errors[0])
        self.assertIn("policy-exception", errors[0])

    def test_a_row_with_no_operation_owes_no_registration_binding(self):
        errors = self.run_validator({
            "id": "AM-003", "date": "2026-08-10",
            "summary": "ordinary guidance log entry", "status": "verified",
            "writeback_done": True,
        })
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
