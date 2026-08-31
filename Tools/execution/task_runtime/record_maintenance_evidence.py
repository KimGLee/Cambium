#!/usr/bin/env python3
"""Publish the three current receipts that bind one maintenance completion.

The maintenance envelope itself remains a user/Agent-confirmed bounded input.
This writer does not choose its candidate set, budget, or disposition.  It
reads that already-written manifest together with the current Coverage Ledger
and watermark, projects the three existing K00/K13 evidence requirements, and
refuses publication unless the existing maintenance consumer accepts their
complete binding.  It is consequently the sole machine producer of these
receipt kinds, rather than leaving fixtures or callers to fabricate them.
"""

import os
import sys

import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
from Tools.execution.task_runtime import queue_runtime
from Tools.execution.task_runtime import runtime_paths
from Tools.execution.task_runtime import runtime_validation
from Tools.execution.task_runtime.queue_runtime import maintenance
from Tools.execution.task_runtime.queue_runtime.primitives import (
    nonempty_string,
    valid_timestamp,
)
from Tools.knowledge.content import maintenance_candidates
from Tools.platform.common import reporting


TOOL = "record_maintenance_evidence"
TOOL_VERSION = "1.0.0"
BUDGET_RECEIPT_TYPE_ID = "maintenance-budget-manifest-receipt-v1"
LEDGER_RECEIPT_TYPE_ID = "maintenance-ledger-advance-receipt-v1"
WATERMARK_RECEIPT_TYPE_ID = "maintenance-watermark-advance-receipt-v1"
DEFAULT_RECEIPTS = runtime_paths.child_path(
    runtime_paths.RECEIPT_ROOT, "maintenance-evidence.jsonl")


_BASE_FIELDS = frozenset((
    "receipt_id", "receipt_type_id", "tool", "tool_version", "check",
    "target", "result", "details", "checked_at", "invalidated_by",
    "task_id", "scope_version", "upstream_revision_id",
    "selected_profile_manifest", "maintenance_run_id",
    "previous_maintenance_completion_receipt",
))


def _typed_errors(record, receipt_type_id, check, fields, *, target):
    errors = receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=receipt_type_id, tool=TOOL,
        tool_version=TOOL_VERSION, checks=check)
    if not isinstance(record, dict):
        return errors
    expected_fields = _BASE_FIELDS | frozenset(fields)
    actual_fields = frozenset(record)
    if actual_fields != expected_fields:
        errors.append("maintenance Receipt fields are not closed: missing=%s extra=%s" %
                      (sorted(expected_fields - actual_fields),
                       sorted(actual_fields - expected_fields)))
    for field in ("receipt_id", "details", "task_id", "scope_version",
                  "upstream_revision_id", "selected_profile_manifest",
                  "maintenance_run_id"):
        if not nonempty_string(record.get(field)):
            errors.append("maintenance Receipt has invalid %s" % field)
    if not valid_timestamp(record.get("checked_at")):
        errors.append("maintenance Receipt has invalid checked_at")
    if record.get("result") != "pass" or record.get("invalidated_by") is not None:
        errors.append("maintenance Receipt must be a current passing Receipt")
    previous = record.get("previous_maintenance_completion_receipt")
    if previous is not None and not nonempty_string(previous):
        errors.append("maintenance Receipt has invalid prior completion Receipt")
    if record.get("target") != target:
        errors.append("maintenance Receipt target does not match its evidence kind")
    return errors


def current_budget_receipt_errors(record, *, root=None):
    errors = _typed_errors(
        record, BUDGET_RECEIPT_TYPE_ID, "maintenance_budget_manifest", (
            "budget_manifest_path", "budget_manifest_sha256",
            "budget_manifest_state", "manifest_open_items",
            "maintenance_run_id", "maintenance_candidate_state_sha256",
            "budget_manifest_closed_at", "selected_candidate_ids",
            "deferred_candidate_ids",
        ), target=record.get("budget_manifest_path") if isinstance(record, dict) else None)
    if isinstance(record, dict):
        if not nonempty_string(record.get("budget_manifest_path")):
            errors.append("maintenance budget Receipt has invalid manifest path")
        if not isinstance(record.get("budget_manifest_sha256"), str) or not \
                queue_runtime.SHA256_RE.fullmatch(record["budget_manifest_sha256"]):
            errors.append("maintenance budget Receipt has invalid manifest fingerprint")
        if record.get("budget_manifest_state") != "closed" or \
                record.get("manifest_open_items") != 0:
            errors.append("maintenance budget Receipt must bind a closed empty manifest")
        if not valid_timestamp(record.get("budget_manifest_closed_at")):
            errors.append("maintenance budget Receipt has invalid closure time")
        for field in ("selected_candidate_ids", "deferred_candidate_ids"):
            if not isinstance(record.get(field), list) or not all(
                    nonempty_string(value) for value in record[field]):
                errors.append("maintenance budget Receipt has invalid %s" % field)
        if (not isinstance(record.get("maintenance_candidate_state_sha256"), str) or
                not queue_runtime.SHA256_RE.fullmatch(
                    record["maintenance_candidate_state_sha256"])):
            errors.append("maintenance budget Receipt has invalid candidate fingerprint")
    return errors


def current_ledger_receipt_errors(record, *, root=None):
    errors = _typed_errors(
        record, LEDGER_RECEIPT_TYPE_ID, "maintenance_ledger_advanced", (
            "coverage_ledger_path", "before_coverage_sha256",
            "after_coverage_sha256", "advanced", "maintenance_run_id",
            "coverage_updated_at", "before_maintenance_candidate_state_sha256",
            "after_maintenance_candidate_state_sha256",
        ), target=runtime_paths.COVERAGE_PATH)
    if isinstance(record, dict):
        if record.get("coverage_ledger_path") != runtime_paths.COVERAGE_PATH or \
                record.get("advanced") is not True:
            errors.append("maintenance Ledger Receipt has invalid current binding")
        for field in ("before_coverage_sha256", "after_coverage_sha256",
                      "before_maintenance_candidate_state_sha256",
                      "after_maintenance_candidate_state_sha256"):
            if (not isinstance(record.get(field), str) or
                    not queue_runtime.SHA256_RE.fullmatch(record[field])):
                errors.append("maintenance Ledger Receipt has invalid %s" % field)
        if not valid_timestamp(record.get("coverage_updated_at")):
            errors.append("maintenance Ledger Receipt has invalid coverage update time")
    return errors


def current_watermark_receipt_errors(record, *, root=None):
    errors = _typed_errors(
        record, WATERMARK_RECEIPT_TYPE_ID,
        "maintenance_watermark_advanced", (
            "watermark_path", "before_watermark_sha256",
            "after_watermark_sha256", "advanced", "maintenance_run_id",
            "watermark_updated_at", "watermark_run_id", "watermark_batch_id",
        ), target=runtime_paths.WATERMARK_PATH)
    if isinstance(record, dict):
        if record.get("watermark_path") != runtime_paths.WATERMARK_PATH or \
                record.get("advanced") is not True:
            errors.append("maintenance watermark Receipt has invalid current binding")
        for field in ("before_watermark_sha256", "after_watermark_sha256"):
            if (not isinstance(record.get(field), str) or
                    not queue_runtime.SHA256_RE.fullmatch(record[field])):
                errors.append("maintenance watermark Receipt has invalid %s" % field)
        for field in ("watermark_updated_at",):
            if not valid_timestamp(record.get(field)):
                errors.append("maintenance watermark Receipt has invalid %s" % field)
        for field in ("watermark_run_id", "watermark_batch_id"):
            if not nonempty_string(record.get(field)):
                errors.append("maintenance watermark Receipt has invalid %s" % field)
    return errors


def _load_manifest(root, relative_path):
    path = kblib.managed_repository_path(
        root, relative_path, runtime_paths.RECEIPT_ROOT,
        suffixes=(".yaml",), must_exist=True)
    document = kblib.load_yaml_file(path)
    if not isinstance(document, dict):
        raise ValueError("maintenance budget manifest must be a mapping")
    return path, document


def _load_watermark(root):
    path = kblib.managed_repository_path(
        root, runtime_paths.WATERMARK_PATH, runtime_paths.STATE_ROOT,
        suffixes=(".yaml",), must_exist=True)
    document = kblib.load_yaml_file(path)
    if not isinstance(document, dict):
        raise ValueError("maintenance watermark must be a mapping")
    return path, document


def _sha256(value, label):
    if not isinstance(value, str) or not queue_runtime.SHA256_RE.fullmatch(value):
        raise ValueError("%s must be sha256:<hex>" % label)
    return value


def build_receipts(root, result, budget_manifest_path,
                   before_coverage_sha256, before_watermark_sha256):
    """Build and validate all three receipts before any append occurs."""
    consumer_context = maintenance.MaintenanceConsumerContext.from_runtime(
        result)
    manifest_path, manifest = _load_manifest(root, budget_manifest_path)
    watermark_path, watermark = _load_watermark(root)
    before_coverage_sha256 = _sha256(
        before_coverage_sha256, "--before-coverage-sha256")
    before_watermark_sha256 = _sha256(
        before_watermark_sha256, "--before-watermark-sha256")
    after_coverage_sha256 = result.get("coverage_sha256")
    after_watermark_sha256 = kblib.sha256_file(watermark_path)
    if before_coverage_sha256 == after_coverage_sha256:
        raise ValueError("maintenance Coverage before-image equals current bytes")
    if before_watermark_sha256 == after_watermark_sha256:
        raise ValueError("maintenance watermark before-image equals current bytes")

    queue = result.get("queue") or {}
    contract = (result.get("progress") or {}).get("contract") or {}
    task_id = queue.get("task_id")
    run_id = manifest.get("run_id")
    if not nonempty_string(run_id):
        raise ValueError("maintenance budget manifest has no run_id")
    identity = {
        "task_id": task_id,
        "scope_version": contract.get("scope_version"),
        "upstream_revision_id": contract.get("upstream_revision_id"),
        "selected_profile_manifest": contract.get(
            "selected_profile_manifest"),
    }
    candidate_state = maintenance_candidates.candidate_state_sha256(
        manifest.get("candidates") if isinstance(manifest.get("candidates"), list)
        else [])
    previous_completion = manifest.get("previous_maintenance_completion_receipt")
    prior_errors = []
    _prior_receipt, _prior_candidates, prior_candidate_state = \
        maintenance.previous_maintenance_candidate_state(
            consumer_context, previous_completion, contract, prior_errors)
    if prior_errors:
        raise ValueError("maintenance predecessor is not current-contract: %s" %
                         "; ".join(prior_errors))
    common = {
        **identity,
        "maintenance_run_id": run_id,
        "previous_maintenance_completion_receipt": previous_completion,
    }
    budget = kblib.make_receipt(
        TOOL, TOOL_VERSION, "maintenance_budget_manifest", budget_manifest_path,
        "pass", "current maintenance budget manifest is closed", 1,
        receipt_type_id=BUDGET_RECEIPT_TYPE_ID, root=root)
    budget.update({
        **common,
        "budget_manifest_path": budget_manifest_path,
        "budget_manifest_sha256": kblib.sha256_file(manifest_path),
        "budget_manifest_state": manifest.get("state"),
        "manifest_open_items": manifest.get("open_items"),
        "budget_manifest_closed_at": manifest.get("closed_at"),
        "maintenance_candidate_state_sha256": candidate_state,
        "selected_candidate_ids": manifest.get("selected_candidate_ids"),
        "deferred_candidate_ids": manifest.get("deferred_candidate_ids"),
    })
    ledger = kblib.make_receipt(
        TOOL, TOOL_VERSION, "maintenance_ledger_advanced",
        runtime_paths.COVERAGE_PATH, "pass",
        "current Coverage Ledger advance is bound to maintenance", 2,
        receipt_type_id=LEDGER_RECEIPT_TYPE_ID, root=root)
    ledger.update({
        **common,
        "advanced": True,
        "coverage_ledger_path": runtime_paths.COVERAGE_PATH,
        "before_coverage_sha256": before_coverage_sha256,
        "after_coverage_sha256": after_coverage_sha256,
        "coverage_updated_at": (result.get("coverage") or {}).get("updated_at"),
        # The existing gate resolves the predecessor state; this writer only
        # binds the same declared manifest state to its current after-image.
        "before_maintenance_candidate_state_sha256":
            prior_candidate_state,
        "after_maintenance_candidate_state_sha256": candidate_state,
    })
    watermark_receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "maintenance_watermark_advanced",
        runtime_paths.WATERMARK_PATH, "pass",
        "current maintenance watermark advance is bound to the run", 3,
        receipt_type_id=WATERMARK_RECEIPT_TYPE_ID, root=root)
    watermark_receipt.update({
        **common,
        "advanced": True,
        "watermark_path": runtime_paths.WATERMARK_PATH,
        "before_watermark_sha256": before_watermark_sha256,
        "after_watermark_sha256": after_watermark_sha256,
        "watermark_updated_at": watermark.get("updated_at"),
        "watermark_run_id": watermark.get("last_run_id"),
        "watermark_batch_id": watermark.get("last_batch_id"),
    })
    records = (budget, ledger, watermark_receipt)
    for record, validator in zip(records, (
            current_budget_receipt_errors, current_ledger_receipt_errors,
            current_watermark_receipt_errors)):
        errors = validator(record, root=root)
        if errors:
            raise ValueError("invalid maintenance Receipt: %s" % "; ".join(errors))

    # Prove the shared K13 consumer accepts exactly these three records before
    # publishing them.  The candidate catalog remains in-memory: publication
    # is all-or-nothing from the consumer's point of view.
    proposed_context = consumer_context.with_pending_current(records)
    errors, _context = maintenance.maintenance_completion_gate_errors(
        proposed_context, budget["receipt_id"], ledger["receipt_id"],
        watermark_receipt["receipt_id"])
    if errors:
        raise ValueError("maintenance evidence is not consumable: %s" %
                         "; ".join(errors))
    return records


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Publish the current typed evidence for one maintenance completion")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--budget-manifest", required=True,
                        help="closed maintenance budget manifest under .cambium/receipts")
    parser.add_argument("--before-coverage-sha256", required=True,
                        help="Coverage Ledger fingerprint before this maintenance run")
    parser.add_argument("--before-watermark-sha256", required=True,
                        help="watermark fingerprint before this maintenance run")
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS,
                        help="current maintenance evidence JSONL destination")
    parser.add_argument("--apply", action="store_true",
                        help="append the three typed receipts")
    parser.add_argument("--json", action="store_true",
                        help="write published receipts as one JSON array")
    args = parser.parse_args(argv)
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        result = runtime_validation.validate_runtime(root)
        if result.get("errors"):
            raise ValueError("current runtime state: %s" %
                             "; ".join(result["errors"]))
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False)
        records = build_receipts(
            root, result, args.budget_manifest,
            args.before_coverage_sha256, args.before_watermark_sha256)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1
    if not args.apply:
        if not args.json:
            print("[PLAN] maintenance evidence will publish budget, Ledger, and watermark receipts")
        return 0
    try:
        kblib.write_receipts(receipt_path, records)
    except OSError as exc:
        print("[FAIL] cannot publish maintenance evidence: %s" % exc,
              file=sys.stderr)
        return 1
    if args.json:
        reporting.write_canonical_json_array(records)
    else:
        print("[OK] published maintenance evidence: %s" %
              ", ".join(record["receipt_id"] for record in records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
