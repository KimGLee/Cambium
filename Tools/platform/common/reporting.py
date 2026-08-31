"""Canonical receipt-to-stdout reporting shared by Tool entry points."""

import contextlib
import sys

import Tools.platform.common.kblib as kblib


JSON_RECEIPT_HELP = (
    "write this run's receipt objects to stdout as one canonical JSON array "
    "and move the human-readable report to stderr; receipt writing, verdicts, "
    "and exit codes are unchanged"
)

JSON_CHECK_HELP = (
    "write the receipts this run produced to stdout as one canonical JSON "
    "array and move the human-readable summary to stderr; receipts written "
    "and the exit code are unchanged"
)

JSON_RECEIPT_SUMMARY_HELP = (
    "write this run's receipt objects to stdout as one canonical JSON array "
    "and move the human summary to stderr; receipt writing and exit codes "
    "are unchanged"
)


class FindingSet:
    """Small in-memory set of structured checker findings.

    The class owns only the repeated four-field result envelope used by
    repository checkers.  The checker still owns every check identity,
    severity choice, detail, and final verdict.
    """

    def __init__(self):
        self.rows = []

    def add(self, check, target, result, details):
        self.rows.append({
            "check": check,
            "target": target,
            "result": result,
            "details": details,
        })

    def count(self, result):
        return sum(1 for row in self.rows if row["result"] == result)

    def failures(self):
        return [row for row in self.rows if row["result"] == "fail"]


def _write_receipts(stream, receipts):
    write_canonical_json_array(receipts, stream=stream)
    stream.flush()


def write_canonical_json(payload, *, stream=None):
    """Write one canonical JSON value plus its terminating newline."""
    stream = sys.stdout if stream is None else stream
    stream.write(kblib.canonical_json_bytes(payload).decode("utf-8"))
    stream.write("\n")


def write_canonical_json_array(values, *, stream=None, omit_if_empty=False):
    """Write one iterable as a canonical JSON array, optionally omitting it.

    This is a byte-projection helper only.  The caller still decides which
    objects belong in the array and whether an unanswered run has an output.
    Checking truthiness before materializing implements the current output
    contract for ``None`` and empty concrete sequences; a supplied iterable is
    otherwise serialized exactly once as ``list(values)``.
    """
    if omit_if_empty and not values:
        return
    write_canonical_json(list(values), stream=stream)


class JsonReceiptCollector:
    """Collect receipts produced below ``main`` and publish one JSON array.

    ``emit_empty`` distinguishes scanner interfaces, which answer with ``[]``,
    from transactional writers, whose refused/dry run has no receipt answer
    and therefore leaves stdout empty.
    """

    def __init__(self, *, emit_empty=False):
        self.emit_empty = bool(emit_empty)
        self._receipts = []

    def record(self, receipts):
        self._receipts.extend(receipts)
        return receipts

    def run(self, runner, *, stdout=None, stderr=None):
        stdout = sys.stdout if stdout is None else stdout
        stderr = sys.stderr if stderr is None else stderr
        self._receipts = []
        with contextlib.redirect_stdout(stderr):
            exit_code = runner()
        if self._receipts or self.emit_empty:
            _write_receipts(stdout, self._receipts)
        return exit_code


class RedirectedJsonReceipts:
    """Preserve the begin/record/finish protocol used by checker entry points."""

    def __init__(self):
        self._stdout = None
        self._receipts = None

    @property
    def enabled(self):
        return self._stdout is not None

    def begin(self, enabled):
        self._stdout = None
        self._receipts = None
        if enabled:
            self._stdout = sys.stdout
            sys.stdout = sys.stderr

    def record(self, receipts):
        if self.enabled:
            self._receipts = list(receipts)

    def finish(self, answered):
        stream = self._stdout
        receipts = self._receipts
        self._stdout = None
        self._receipts = None
        if stream is None:
            return
        sys.stdout = stream
        if answered and receipts is not None:
            _write_receipts(stream, receipts)


def run_redirected_json(reporter, runner):
    """Run one redirected checker and always restore its output boundary."""
    try:
        code = runner()
    except BaseException:
        reporter.finish(False)
        raise
    reporter.finish(True)
    return code
