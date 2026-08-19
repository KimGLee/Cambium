#!/usr/bin/env python3
"""Record, but never invent, Corpus Planning semantic acceptance.

The structural checker remains the sole producer of structural/reconciliation
evidence. This tool consumes a closed restricted-YAML authority decision plan,
produces one fresh structural receipt, and records the distinct authority
decision as append-only JSONL. It never writes planning artifacts or reports.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_corpus_plan
import kblib


TOOL = check_corpus_plan.SEMANTIC_ACCEPTANCE_TOOL
TOOL_VERSION = check_corpus_plan.SEMANTIC_ACCEPTANCE_TOOL_VERSION
# The Gate ID and the `Check` cell K00/12 registers for this recorder
# are owned next to K02/04's acceptance contract; this module
# re-exports them rather than restating them.
GATE_ID = check_corpus_plan.SEMANTIC_ACCEPTANCE_SCOPE
GATE_CHECK = check_corpus_plan.SEMANTIC_ACCEPTANCE_CHECK
DEFAULT_RECEIPTS = ".cambium/receipts/corpus-plan-acceptance.jsonl"


def _output(payload):
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _load_plan(root, relative):
    if (not isinstance(relative, str) or
            os.path.dirname(relative) !=
            check_corpus_plan.SEMANTIC_ACCEPTANCE_PLAN_PREFIX or
            not relative.endswith(".yaml")):
        raise ValueError(
            "--plan must name one YAML file directly under %s/" %
            check_corpus_plan.SEMANTIC_ACCEPTANCE_PLAN_PREFIX)
    absolute = kblib.managed_repository_path(
        root, relative,
        check_corpus_plan.SEMANTIC_ACCEPTANCE_PLAN_PREFIX,
        suffixes=(".yaml",), must_exist=True)
    plan = kblib.load_yaml_file(absolute)
    return absolute, plan


def _make_receipts(result, plan, plan_path, plan_sha, snapshot):
    structural = check_corpus_plan.make_pass_receipt(
        result, repository_snapshot_sha256=snapshot, seq=1)
    decisions = plan["decisions"]
    accepted = sum(
        1 for row in decisions if row.get("decision") == "accepted")
    rejected = len(decisions) - accepted
    semantic_result = "pass" if rejected == 0 else "fail"
    # The validated repository root also binds the Required Queue identity a
    # Gate consumer compares against; the artifact binding below still owns
    # every field it declares.
    semantic = kblib.make_receipt(
        TOOL, TOOL_VERSION,
        check_corpus_plan.SEMANTIC_ACCEPTANCE_CHECK,
        result["profile_manifest"], semantic_result,
        "authority_role=%s; accepted=%d; rejected=%d" %
        (plan["authority_role_id"], accepted, rejected),
        2, root=result.get("root"),
    )
    semantic.update(check_corpus_plan.receipt_binding(
        result, repository_snapshot_sha256=snapshot))
    semantic.update({
        "gate_id": GATE_ID,
        "acceptance_id": plan["acceptance_id"],
        "acceptance_plan_path": plan_path,
        "acceptance_plan_sha256": plan_sha,
        "authority_role_id": plan["authority_role_id"],
        "actor_role_id": plan["authority_role_id"],
        "decision_scope_id": plan["decision_scope_id"],
        "structural_check_receipt": structural["receipt_id"],
        "capability_decisions": plan["decisions"],
    })
    return structural, semantic


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Record a Profile-authorized Corpus Planning semantic decision "
            "as machine-readable JSONL"))
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument(
        "--plan", required=True,
        help=("closed restricted-YAML acceptance decision plan; one .yaml "
              "file directly under %s/" %
              check_corpus_plan.SEMANTIC_ACCEPTANCE_PLAN_PREFIX),
    )
    parser.add_argument(
        "--receipts", default=DEFAULT_RECEIPTS,
        help=("repository-relative JSONL path the receipts are appended to "
              "(default: %s)" % DEFAULT_RECEIPTS),
    )
    parser.add_argument(
        "--actor-role",
        help=(
            "declared authority Role ID; required with --apply and must equal "
            "the Profile/plan binding"),
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="append the structural and semantic receipts; default is dry-run",
    )
    args = parser.parse_args(argv)

    root = os.path.realpath(os.path.abspath(args.root))
    errors = []
    try:
        plan_absolute, plan = _load_plan(root, args.plan)
    except (OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        _output({"applied": False, "errors": [str(exc)], "status": "invalid"})
        return 1

    result = check_corpus_plan.validate_corpus_plan(root)
    errors.extend(
        "%s (%s): %s" %
        (error["check"], error["target"], error["details"])
        for error in result.get("errors") or [])
    errors.extend(check_corpus_plan.acceptance_plan_errors(root, plan, result))
    if args.actor_role is not None and args.actor_role != plan.get(
            "authority_role_id"):
        errors.append(
            "--actor-role=%r does not equal plan/Profile authority_role_id=%r" %
            (args.actor_role, plan.get("authority_role_id")))
    if args.apply and not args.actor_role:
        errors.append("--apply requires --actor-role")
    try:
        receipt_absolute = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False)
    except ValueError as exc:
        errors.append(str(exc))
        receipt_absolute = None
    try:
        snapshot = kblib.repository_snapshot_sha256(root)
        plan_sha = kblib.sha256_file(plan_absolute)
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
        snapshot = None
        plan_sha = None
    if errors:
        _output({"applied": False, "errors": errors, "status": "invalid"})
        return 1

    structural, semantic = _make_receipts(
        result, plan, args.plan, plan_sha, snapshot)
    pending_catalog = dict(
        (result.get("runtime") or {}).get("current_receipt_catalog") or {})
    pending_catalog[structural["receipt_id"]] = (
        "<pending-structural-receipt>", structural)
    receipt_errors = check_corpus_plan.semantic_acceptance_receipt_errors(
        root, semantic, result=result,
        repository_snapshot_sha256=snapshot,
        receipt_catalog=pending_catalog,
        structural_receipt=structural,
    )
    if receipt_errors:
        _output({
            "applied": False,
            "errors": receipt_errors,
            "status": "invalid",
        })
        return 1

    prospective_status = (
        "current" if semantic["result"] == "pass" else "rejected")
    if not args.apply:
        _output({
            "applied": False,
            "errors": [],
            "status": prospective_status,
            "structural_check_receipt": structural["receipt_id"],
            "semantic_acceptance_receipt": semantic["receipt_id"],
            "receipt_path": args.receipts,
        })
        return 0 if semantic["result"] == "pass" else 1

    outcome, write_error, _ = kblib.write_receipts_observed(
        receipt_absolute, [structural, semantic])
    if outcome != "present" or write_error is not None:
        details = (
            str(write_error) if write_error is not None
            else "receipt append outcome=%s" % outcome)
        _output({
            "applied": outcome == "present",
            "errors": [details],
            "status": "uncertain" if outcome == "uncertain" else "invalid",
            "structural_check_receipt": structural["receipt_id"],
            "semantic_acceptance_receipt": semantic["receipt_id"],
            "receipt_path": args.receipts,
        })
        return 1

    current = check_corpus_plan.validate_corpus_plan(root)
    current_snapshot = kblib.repository_snapshot_sha256(root)
    status = check_corpus_plan.semantic_acceptance_status(
        current, repository_snapshot_sha256=current_snapshot)
    expected_status = prospective_status
    if (status.get("status") != expected_status or
            status.get("receipt_id") != semantic["receipt_id"]):
        _output({
            "applied": True,
            "errors": [
                "receipt persisted but current bytes no longer match the "
                "recorded acceptance"],
            "status": status,
            "structural_check_receipt": structural["receipt_id"],
            "semantic_acceptance_receipt": semantic["receipt_id"],
            "receipt_path": args.receipts,
        })
        return 1
    _output({
        "applied": True,
        "errors": [],
        "status": status,
        "structural_check_receipt": structural["receipt_id"],
        "semantic_acceptance_receipt": semantic["receipt_id"],
        "receipt_path": args.receipts,
    })
    return 0 if semantic["result"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
