"""Canonical receipt-to-stdout reporting shared by Tool entry points."""

import contextlib
import functools
import io
import json
import sys

import Tools.platform.common.kblib as kblib
from Tools.platform.agent_interface import agent_interface_contract
from Tools.platform.common.host_environment import (
    HostEnvironmentUnavailable, host_handoff, validate_host_handoff,
)


def host_environment_boundary(function):
    """CLI-only handoff for an unperformed observation; never a Receipt verdict.

    No applied=False claim: an operation may have committed an earlier step
    before its resulting-state observation became unavailable.
    """
    @functools.wraps(function)
    def run(*args, **kwargs):
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                result = function(*args, **kwargs)
        except HostEnvironmentUnavailable as exc:
            write_canonical_json(host_handoff(
                exc.diagnostic(), prior_output=output.getvalue() or None))
            return 1
        except BaseException:
            sys.stdout.write(output.getvalue())
            raise
        sys.stdout.write(output.getvalue())
        return result
    return run


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


_APPEND_APPLIED = {
    "not-attempted": False,
    "absent": False,
    "present": True,
    "uncertain": None,
}
_PUBLICATION_FIELDS = frozenset(("append", "record_confirmation", "reused"))


def validate_publication_result(payload):
    """Validate transient mechanical facts, never a producer's business verdict."""
    if not isinstance(payload, dict):
        raise ValueError("publication result must be one object")
    publication = payload.get("publication")
    if not isinstance(publication, dict) or set(publication) != _PUBLICATION_FIELDS:
        raise ValueError("publication facts have an invalid field set")
    outcome = publication.get("append")
    if not isinstance(outcome, str) or outcome not in _APPEND_APPLIED:
        raise ValueError("publication append outcome is invalid")
    if "applied" not in payload or payload["applied"] is not _APPEND_APPLIED[outcome]:
        raise ValueError("applied must preserve the observed append outcome")
    confirmation = publication.get("record_confirmation")
    if confirmation not in ("confirmed", "unconfirmed"):
        raise ValueError("publication record confirmation is invalid")
    reused = publication.get("reused")
    if type(reused) is not bool:
        raise ValueError("publication reuse must be boolean")
    if reused and (outcome != "not-attempted" or confirmation != "confirmed"):
        raise ValueError("reuse requires confirmed existing evidence without an append")
    if confirmation == "confirmed" and outcome != "present" and not reused:
        raise ValueError("record confirmation requires observed publication or confirmed reuse")
    errors = payload.get("errors")
    if not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
        raise ValueError("publication errors must be a list of diagnostic strings")
    status = payload.get("status")
    if not isinstance(status, str) or not status:
        raise ValueError("publication status must be a nonempty producer label")
    if (outcome == "uncertain" or
            (outcome == "present" and (confirmation != "confirmed" or errors))):
        if status != "uncertain":
            raise ValueError("unconfirmed or errored publication must remain uncertain")
    return payload


def publication_result(publication, *, status, errors=(), reused=False, **fields):
    """Project append facts separately from the producer-owned business result.

    This transient response is not a Receipt and never authorizes consumption.
    A writer error cannot erase observed bytes or turn an unknown into absence.
    """
    if not isinstance(publication, kblib.ReceiptPublication):
        raise TypeError("publication result requires Receipt I/O facts")
    if reused and (publication.outcome != "not-attempted" or
                   not publication.confirmed):
        raise ValueError("reuse requires confirmed existing evidence without an append")
    messages = list(errors)
    if publication.error is not None and str(publication.error) not in messages:
        messages.append(str(publication.error))
    present = publication.outcome == "present"
    absent = publication.outcome in ("not-attempted", "absent")
    reliable = publication.confirmed and (present or reused) and not messages
    result = dict(fields, status=status if reliable or absent else "uncertain",
                applied=_APPEND_APPLIED.get(publication.outcome),
                errors=messages,
                publication={
                    "append": publication.outcome,
                    "record_confirmation": (
                        "confirmed" if publication.confirmed else "unconfirmed"),
                    "reused": reused,
                })
    return validate_publication_result(result)


def publication_result_reliable(payload):
    """Whether the operation boundary is settled, not whether its review passed."""
    validate_publication_result(payload)
    return payload["status"] != "uncertain"


def observe_tool_output(contract, stdout, exit_code, arguments, *, host_boundary=False):
    """One CLI/MCP/Runner observation of declared output and unsettled outcomes.

    An allowed Host handoff can cross any ordinary output shape, but never
    becomes a Receipt or a claim of no write. Ordinary business payloads keep
    their declared shape; their evidence acceptance remains with consumers.
    """
    agent_interface_contract.validate_output_contract(contract)
    if type(host_boundary) is not bool:
        raise ValueError("Host boundary declaration must be boolean")
    try:
        candidate = json.loads(stdout.decode("utf-8"))
    except (UnicodeError, ValueError):
        candidate = None
    if isinstance(candidate, dict) and "host_environment" in candidate:
        observation = {"stdout_parse": "parsed", "stdout_json": candidate,
                       "output_reliable": False}
        try:
            if not host_boundary:
                raise ValueError("tool has no declared Host environment boundary")
            validate_host_handoff(candidate)
        except ValueError as exc:
            observation.update(stdout_parse="unparseable", stdout_parse_error=str(exc))
        return observation
    observation = agent_interface_contract.decode_output(
        contract, stdout, exit_code, arguments)
    if (observation["stdout_parse"] == "parsed" and
            contract["result_contract"] == "receipt-publication"):
        try:
            observation["output_reliable"] = publication_result_reliable(
                observation["stdout_json"])
        except ValueError as exc:
            observation.update(stdout_parse="unparseable", output_reliable=False,
                               stdout_parse_error=str(exc))
    return observation


def observe_invocation(contract, stdout, exit_code, arguments, *,
                       binding, host_boundary=False):
    """Settle transport facts once; preserve output even if invocation fails.

    A failed business operation can still have consumed its input. Missing
    consumption on a claimed clean/HOLD return is an invocation failure, not
    permission to retry a child that may already have committed.
    """
    observed = observe_tool_output(
        contract, stdout, exit_code, arguments, host_boundary=host_boundary)
    errors = []
    if type(exit_code) is not int or exit_code not in agent_interface_contract.PROCESS_VERDICTS:
        errors.append("unregistered process exit code: %r" % exit_code)
    if binding["acknowledgement_error"]:
        errors.append(binding["acknowledgement_error"])
    if exit_code in (0, 2) and binding["missing"]:
        errors.append("child did not consume admitted paths: %s" % binding["missing"])
    observed.update(invocation_errors=errors, invocation_reliable=not errors)
    return observed


def validate_receipt_process(exit_code, receipts):
    """Check a complete checker result before any domain-specific projection.

    Fail and candidate results may be reliable observations; the consuming
    Gate/scan decides which are acceptable. This checks neither currentness
    nor authorization and never rewrites the actual process code.
    """
    if type(exit_code) is not int or exit_code not in agent_interface_contract.PROCESS_VERDICTS:
        raise ValueError("checker returned an unregistered exit code: %r" % exit_code)
    if not isinstance(receipts, list) or not receipts or any(
            not isinstance(receipt, dict) for receipt in receipts):
        raise ValueError("checker must emit one nonempty Receipt array")
    try:
        calculated = kblib.exit_code(receipts)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("checker emitted an invalid result: %s" % exc) from exc
    if calculated != exit_code:
        raise ValueError("checker exit %d disagrees with receipt results (expected %d)" %
                         (exit_code, calculated))
    return receipts


def write_publication_result(publication, *, json_output, status, errors=(), **fields):
    """Emit the same operation facts through JSON or the existing human mode."""
    payload = publication_result(publication, status=status, errors=errors, **fields)
    if json_output:
        write_canonical_json(payload)
    else:
        facts = payload["publication"]
        stream = sys.stderr if payload["errors"] else sys.stdout
        print("[%s] receipt append=%s; record confirmation=%s" % (
            payload["status"].upper(), facts["append"],
            facts["record_confirmation"]), file=stream)
        for receipt in payload.get("receipts", ()):
            print("receipt: %s" % receipt["receipt_id"], file=stream)
        for error in payload["errors"]:
            print(error, file=stream)
    return payload


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
