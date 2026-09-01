"""Current-contract Card activation objects for in-process tests.

The production module remains the owner of every field set and digest.  This
fixture only supplies stable values so consumers can test the current
producer/ack boundary without building a repository runtime.
"""

import copy

import Tools.execution.context_delivery.card_activation as card_activation
import Tools.platform.common.kblib as kblib


def sha256_fixture(character):
    return "sha256:" + character * 64


def current_activation_context(*, execution_context_id=None):
    """Return one closed current activation context with one preflight part."""
    reading_plan = {}
    readback_plan = []
    requirements = []
    review_sha = card_activation.review_requirement_set_sha256(requirements)
    task_contract_sha = sha256_fixture("7")
    reading_plan_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(reading_plan))
    readback_plan_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(readback_plan))
    piece = {
        "piece_id": "card:R01",
        "kind": "card",
        "path": "Card/R01.md",
        "sha256": sha256_fixture("1"),
        "bytes": 1,
        "route_id": "R01",
        "read_set": "Read Set/R01.md",
        "read_set_sha256": sha256_fixture("2"),
        "source_hash": "a" * 12,
        "reviewed_source_hash": "a" * 12,
        "reviewed_card_hash": "b" * 12,
        "readback_rule_ids": [],
        "phase": card_activation.PHASE_BATCH_PREFLIGHT,
    }
    environment = {
        "upstream_revision_id": "upstream-1",
        "selected_profile_manifest": "profiles/test/profile.yaml",
        "profile_snapshot_sha256": sha256_fixture("3"),
        "profile_contract_fingerprint": sha256_fixture("4"),
        "profile_load_inputs_sha256": sha256_fixture("5"),
        "resolver_version": card_activation.PHASE_RESOLVER_VERSION,
        "card_index_sha256": sha256_fixture("6"),
        "task_contract_sha256": task_contract_sha,
        "work_spec_path": None,
        "work_spec_sha256": None,
    }
    phases = []
    for phase_id in card_activation.PHASE_ORDER:
        piece_ids = (["card:R01"] if phase_id ==
                     card_activation.PHASE_BATCH_PREFLIGHT else [])
        parts = ([{
            "part_index": 0,
            "piece_ids": piece_ids,
            "envelope_bytes": 100,
        }] if piece_ids else [])
        phases.append({
            "phase_id": phase_id,
            "conditional": phase_id in card_activation.CONDITIONAL_PHASES,
            "standard": phase_id in card_activation.STANDARD_PHASES,
            "trigger": card_activation.PHASE_TRIGGERS[phase_id],
            "route_ids": ["R01"] if piece_ids else [],
            "piece_ids": piece_ids,
            "piece_count": len(piece_ids),
            "parts": parts,
            "part_count": len(parts),
        })
    phase_plan = {
        "protocol": card_activation.PHASE_PLAN_PROTOCOL,
        "phases": phases,
        "route_phases": {
            "R01": card_activation.PHASE_BATCH_PREFLIGHT,
        },
        "work_route_ids": None,
        "narrowed_by_work_spec": False,
        "environment": environment,
    }
    phase_plan_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(phase_plan))
    manifest = {
        "activation_protocol": card_activation.ACTIVATION_PROTOCOL,
        "task_id": "TASK-1",
        "batch_id": "B1",
        "upstream_revision_id": "upstream-1",
        "selected_profile_manifest": "profiles/test/profile.yaml",
        "required_queue_sha256": sha256_fixture("8"),
        "coverage_ledger_sha256": sha256_fixture("9"),
        "progress_ledger_sha256": sha256_fixture("a"),
        "queue_revision": 1,
        "queue_state_revision": 1,
        "active_standards_sha256": sha256_fixture("b"),
        "profile_snapshot_sha256": sha256_fixture("3"),
        "profile_contract_fingerprint": sha256_fixture("4"),
        "profile_load_inputs_sha256": sha256_fixture("5"),
        "task_contract_sha256": task_contract_sha,
        "card_index_sha256": sha256_fixture("6"),
        "reading_plan_sha256": reading_plan_sha,
        "readback_plan_sha256": readback_plan_sha,
        "reading_plan": reading_plan,
        "pieces": [piece],
        "piece_count": 1,
        "max_piece_envelope_bytes":
            card_activation.MAX_ACTIVATION_PIECE_ENVELOPE_BYTES,
        "readback_plan": readback_plan,
        "batch_review_plan": {
            "protocol": card_activation.BATCH_REVIEW_PLAN_PROTOCOL,
            "review_requirement_set_sha256": review_sha,
            "requirements": requirements,
        },
        "phase_plan": phase_plan,
        "phase_plan_sha256": phase_plan_sha,
    }
    return {
        "activation_protocol": card_activation.ACTIVATION_PROTOCOL,
        "task_contract_sha256": task_contract_sha,
        "reading_plan_sha256": reading_plan_sha,
        "readback_plan_sha256": readback_plan_sha,
        "review_requirement_set_sha256": review_sha,
        "phase_plan_sha256": phase_plan_sha,
        "card_bundle_sha256": kblib.sha256_bytes(
            kblib.canonical_json_bytes(manifest)),
        "activation_bundle_manifest": manifest,
        "delivery_mode": ("host-context-injection" if execution_context_id
                          else "cli-tool-result"),
        "delivery_assurance": ("host-bound" if execution_context_id
                               else "prepared"),
        "execution_context_id": execution_context_id,
    }


def rebind_activation_manifest(context):
    context["card_bundle_sha256"] = kblib.sha256_bytes(
        kblib.canonical_json_bytes(context["activation_bundle_manifest"]))
    return context


def revised_activation_context(context, **manifest_fields):
    """Copy and rebind one context after changing manifest-owned fields."""
    revised = copy.deepcopy(context)
    revised["activation_bundle_manifest"].update(manifest_fields)
    return rebind_activation_manifest(revised)


def phase_delivery_context(context, *, execution_context_id,
                           activation_receipt_id="audit-activation-1",
                           phase_id=None, part_index=0,
                           nonce="1" * 32):
    """Project one current phase part into the delivery binding contract."""
    phase_id = phase_id or card_activation.PHASE_BATCH_PREFLIGHT
    record = card_activation.phase_record(context, phase_id)
    if not isinstance(record, dict):
        raise ValueError("fixture activation has no phase %s" % phase_id)
    parts = record.get("parts") or []
    if part_index < 0 or part_index >= len(parts):
        raise ValueError("fixture activation has no part %d" % part_index)
    part = parts[part_index]
    delivery = {
        "phase_protocol": card_activation.PHASE_DELIVERY_PROTOCOL,
        "activation_receipt_id": activation_receipt_id,
        "batch_id": context["activation_bundle_manifest"]["batch_id"],
        "card_bundle_sha256": context["card_bundle_sha256"],
        "phase_plan_sha256": context["phase_plan_sha256"],
        "phase_id": phase_id,
        "part_index": part_index,
        "part_count": record["part_count"],
        "phase_piece_ids": list(part["piece_ids"]),
        "phase_envelope_bytes": part["envelope_bytes"],
        "delivery_attempt_id": card_activation.expected_delivery_attempt_id(
            context["card_bundle_sha256"], execution_context_id),
        "delivery_nonce": nonce,
        "delivery_mode": "host-context-injection",
        "delivery_assurance": "host-bound",
        "execution_context_id": execution_context_id,
    }
    return card_activation.phase_receipt_binding(delivery)
