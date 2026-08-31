"""Was the human review obligation answered for this batch.

The frozen judgment set, batch-level authorization, L-tier substantive
review, and the phase-delivery proof that one acting context saw all of it.
The last of those is the point: a review answered across two contexts is two
partial reviews.
"""

import os

import Tools.execution.context_delivery.card_activation as card_activation
import Tools.platform.agent_interface.agent_interface_contract as agent_interface_contract
import Tools.execution.audit.batch_review_receipt_contract as batch_review_receipt_contract
import Tools.platform.common.kblib as kblib
import Tools.knowledge.metadata.metadata_property_state as metadata_property_state
import Tools.governance.profile.profile_batch_judgment_contract as profile_batch_judgment_contract

from Tools.execution.task_runtime.queue_runtime.canon import (
    ACTIVE_STATES,
    GATE_CHECK,
    QUEUE_PATH,
    TOOL,
    TOOL_VERSION,
)
from Tools.execution.task_runtime.queue_runtime.primitives import nonempty_string
from Tools.execution.task_runtime.queue_runtime.receipts import (
    require_receipt,
    current_receipt_catalog,
)
from Tools.platform.common.primitives import catalog_record


def _activation_phase_scope(result, item, phase_id):
    """Resolve the one current phased activation and its frozen phase."""
    errors = []
    if not isinstance(item, dict):
        return {"status": "invalid", "errors": [
            "phase delivery requires one Queue item"]}
    catalog = current_receipt_catalog(result)
    activation_id = item.get("activation_receipt")
    activation = catalog_record(catalog.get(activation_id))
    if not nonempty_string(activation_id) or not isinstance(activation, dict):
        return {"status": "invalid", "errors": [
            "phase delivery activation receipt is absent from current evidence"]}
    if activation.get("receipt_id") != activation_id:
        errors.append("activation catalog key differs from its receipt_id")
    expected_activation = {
        "tool": TOOL,
        "gate_id": "required-queue-admission",
        "check": GATE_CHECK,
        "queue_check_mode": "require-ready:%s" % item.get("id"),
        "target": QUEUE_PATH,
        "result": "pass",
        "invalidated_by": None,
        "task_id": (result.get("queue") or {}).get("task_id"),
    }
    for field, expected in expected_activation.items():
        if activation.get(field) != expected:
            errors.append(
                "activation receipt %s has %s=%r, expected %r" %
                (activation_id, field, activation.get(field), expected))
    if activation.get("tool_version") != TOOL_VERSION:
        errors.append(
            "activation receipt %s has tool_version=%r, expected %r" %
            (activation_id, activation.get("tool_version"), TOOL_VERSION))
    if errors:
        return {"status": "invalid", "errors": errors}
    if activation.get("activation_protocol") != \
            card_activation.ACTIVATION_PROTOCOL:
        return {"status": "invalid", "errors": [
            "activation receipt %s does not use the current protocol" %
            activation_id]}
    if activation.get("delivery_assurance") != "host-bound":
        return {"status": "not-applicable", "errors": []}
    context = card_activation.context_from_receipt(activation)
    context_errors = card_activation.activation_context_errors(context)
    if context_errors:
        return {"status": "invalid", "errors": [
            "activation context is invalid: %s" % "; ".join(context_errors)]}
    record = card_activation.phase_record(context, phase_id)
    if not isinstance(record, dict):
        return {"status": "invalid", "errors": [
            "activation has no frozen phase %s" % phase_id]}
    parts = record.get("parts")
    part_count = record.get("part_count")
    if (not isinstance(parts, list) or
            not isinstance(part_count, int) or isinstance(part_count, bool) or
            part_count < 0 or len(parts) != part_count):
        return {"status": "invalid", "errors": [
            "phase %s has an invalid frozen part plan" % phase_id]}
    return {
        "status": "active", "errors": [], "catalog": catalog,
        "activation_id": activation_id, "activation": activation,
        "context": context, "record": record,
    }


def _phase_part(scope, part_index):
    parts = scope["record"].get("parts") or []
    if (not isinstance(part_index, int) or isinstance(part_index, bool) or
            part_index < 0 or part_index >= len(parts) or
            not isinstance(parts[part_index], dict)):
        return None
    return parts[part_index]


def _resolve_activation_phase_receipt(scope, result, item, receipt_id, *,
                                      receipt_kind, phase_id, part_index=None):
    """Resolve one current delivery or ack through the same closed contract."""
    errors = []
    catalog = scope["catalog"]
    receipt = catalog_record(catalog.get(receipt_id))
    label = "phase %s %s" % (phase_id, receipt_kind)
    if not nonempty_string(receipt_id) or not isinstance(receipt, dict):
        return None, ["%s receipt is absent from current evidence" % label]
    if receipt.get("receipt_id") != receipt_id:
        errors.append("%s catalog key differs from its receipt_id" % label)
    if part_index is None:
        part_index = receipt.get("part_index")
    part = _phase_part(scope, part_index)
    if part is None:
        errors.append("%s has invalid part_index %r" % (label, part_index))
        expected_piece_ids = None
    else:
        expected_piece_ids = list(part.get("piece_ids") or [])
    queue = result.get("queue") or {}
    expected = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "check": GATE_CHECK,
        "target": QUEUE_PATH,
        "result": "pass",
        "invalidated_by": None,
        "task_id": queue.get("task_id"),
        "upstream_revision_id": queue.get("upstream_revision_id"),
        "selected_profile_manifest": queue.get("selected_profile_manifest"),
        "queue_revision": queue.get("queue_revision"),
        "queue_state_revision": queue.get("state_revision"),
        "required_queue_sha256": result.get("queue_sha256"),
        "coverage_ledger_sha256": result.get("coverage_sha256"),
        "progress_ledger_sha256": result.get("progress_sha256"),
        "batch_id": item.get("id"),
        "activation_receipt_id": scope["activation_id"],
        "card_bundle_sha256": scope["activation"].get(
            "card_bundle_sha256"),
        "phase_plan_sha256": scope["activation"].get("phase_plan_sha256"),
        "phase_id": phase_id,
        "part_index": part_index,
        "part_count": scope["record"].get("part_count"),
        "phase_piece_ids": expected_piece_ids,
        "delivery_mode": "host-context-injection",
        "delivery_assurance": "host-bound",
    }
    expected["queue_check_mode"] = "%s:%s:%s:%d" % (
        "deliver-phase" if receipt_kind == "delivery" else
        "ack-activation-phase", item.get("id"), phase_id,
        part_index if isinstance(part_index, int) else -1)
    expected_protocol = (card_activation.PHASE_DELIVERY_PROTOCOL
                         if receipt_kind == "delivery" else
                         card_activation.PHASE_ACK_PROTOCOL)
    protocol_field = ("phase_protocol" if receipt_kind == "delivery" else
                      "phase_ack_protocol")
    expected[protocol_field] = expected_protocol
    for field, value in expected.items():
        if receipt.get(field) != value:
            errors.append(
                "%s receipt %s has %s=%r, expected %r" %
                (label, receipt_id, field, receipt.get(field), value))
    context_id = receipt.get("execution_context_id")
    if not nonempty_string(context_id):
        errors.append("%s receipt %s lacks execution_context_id" %
                      (label, receipt_id))
    else:
        expected_attempt = card_activation.expected_delivery_attempt_id(
            scope["activation"].get("card_bundle_sha256"), context_id)
        if receipt.get("delivery_attempt_id") != expected_attempt:
            errors.append(
                "%s receipt %s has invalid delivery_attempt_id" %
                (label, receipt_id))
    if receipt_kind == "delivery":
        if not nonempty_string(receipt.get("delivery_nonce")):
            errors.append("%s receipt %s lacks delivery_nonce" %
                          (label, receipt_id))
        return (receipt if not errors else None), errors
    if receipt_kind != "ack":
        return None, errors + ["unsupported phase receipt kind %r" %
                               receipt_kind]
    parent_id = receipt.get("delivery_receipt_id")
    parent, parent_errors = _resolve_activation_phase_receipt(
        scope, result, item, parent_id, receipt_kind="delivery",
        phase_id=phase_id, part_index=part_index)
    errors.extend("%s parent: %s" % (label, error)
                  for error in parent_errors)
    if parent is not None:
        for field in (
                "activation_receipt_id", "batch_id", "card_bundle_sha256",
                "phase_plan_sha256", "phase_id", "part_index", "part_count",
                "phase_piece_ids", "delivery_attempt_id", "delivery_mode",
                "delivery_assurance", "execution_context_id"):
            if receipt.get(field) != parent.get(field):
                errors.append(
                    "%s receipt %s does not preserve parent %s" %
                    (label, receipt_id, field))
        if receipt.get("acked_nonce") != parent.get("delivery_nonce"):
            errors.append(
                "%s receipt %s does not bind the parent delivery nonce" %
                (label, receipt_id))
    return (receipt if not errors else None), errors


def resolve_activation_phase_receipt(result, item, receipt_id, *,
                                     receipt_kind, phase_id, part_index=None):
    """Public current-evidence resolver used by CLI, Runner and gates."""
    scope = _activation_phase_scope(result, item, phase_id)
    if scope["status"] != "active":
        return None, list(scope["errors"])
    return _resolve_activation_phase_receipt(
        scope, result, item, receipt_id, receipt_kind=receipt_kind,
        phase_id=phase_id, part_index=part_index)


def _activation_phase_inventory(result, item, phase_id):
    scope = _activation_phase_scope(result, item, phase_id)
    if scope["status"] != "active":
        return scope, {}, {}, list(scope["errors"])
    deliveries = {}
    acks = {}
    errors = []
    bundle_sha = scope["activation"].get("card_bundle_sha256")
    for receipt_id, entry in sorted(scope["catalog"].items()):
        receipt = catalog_record(entry)
        if not isinstance(receipt, dict) or \
                receipt.get("card_bundle_sha256") != bundle_sha or \
                receipt.get("phase_id") != phase_id:
            continue
        kind = None
        if receipt.get("phase_protocol") == \
                card_activation.PHASE_DELIVERY_PROTOCOL:
            kind = "delivery"
        elif receipt.get("phase_ack_protocol") == \
                card_activation.PHASE_ACK_PROTOCOL:
            kind = "ack"
        if kind is None:
            continue
        resolved, candidate_errors = _resolve_activation_phase_receipt(
            scope, result, item, receipt_id, receipt_kind=kind,
            phase_id=phase_id, part_index=receipt.get("part_index"))
        if candidate_errors:
            errors.extend("receipt %s: %s" % (receipt_id, error)
                          for error in candidate_errors)
        elif kind == "delivery":
            deliveries[receipt_id] = resolved
        else:
            acks[receipt_id] = resolved
    return scope, deliveries, acks, errors


def activation_phase_delivery_status(result, item, phase_id, *,
                                     actor_context_id=None):
    """Return the next delivery/ack position for one current phase.

    This is the read-only orchestration projection over the same activation
    receipt and ack records consumed by ``activation_phase_delivery_errors``.
    It does not choose a phase or write evidence; callers name an already-due
    phase and receive either complete, not-applicable, deliver, acknowledge,
    or invalid.
    """
    scope, deliveries, acks, _inventory_errors = \
        _activation_phase_inventory(result, item, phase_id)
    if scope["status"] == "not-applicable":
        return {"status": "not-applicable", "errors": []}
    if scope["status"] != "active":
        return {"status": "invalid",
                "errors": list(scope["errors"])}
    activation = scope["activation"]
    context = scope["context"]
    record = scope["record"]
    piece_ids = set(card_activation.phase_piece_ids(context, phase_id))
    part_count = record.get("part_count")
    if not piece_ids or part_count == 0:
        return {"status": "complete", "errors": [],
                "phase_id": phase_id, "part_count": 0}
    if (not isinstance(part_count, int) or isinstance(part_count, bool) or
            part_count < 1):
        return {"status": "invalid", "errors": [
            "phase %s has invalid part_count" % phase_id]}
    execution_context_id = actor_context_id or os.environ.get(
        agent_interface_contract.EXECUTION_CONTEXT_ENV)
    if not isinstance(execution_context_id, str) or not execution_context_id:
        return {"status": "invalid", "errors": [
            "host-bound phase delivery requires the current execution "
            "context identity"]}
    attempt_id = card_activation.expected_delivery_attempt_id(
        activation.get("card_bundle_sha256"), execution_context_id)
    acked_parts = set()
    acked_pieces = set()
    delivery_by_part = {}
    acked_delivery_ids = set()
    for receipt in acks.values():
        if receipt.get("delivery_attempt_id") != attempt_id:
            continue
        acked_parts.add(receipt.get("part_index"))
        acked_pieces.update(receipt.get("phase_piece_ids") or [])
        acked_delivery_ids.add(receipt.get("delivery_receipt_id"))
    for receipt_id, receipt in deliveries.items():
        if receipt.get("delivery_attempt_id") == attempt_id:
            delivery_by_part.setdefault(receipt.get("part_index"), []).append((
                receipt_id, receipt))
    if (acked_parts == set(range(part_count)) and
            piece_ids.issubset(acked_pieces)):
        return {
            "status": "complete", "errors": [], "phase_id": phase_id,
            "part_count": part_count, "delivery_attempt_id": attempt_id,
        }
    missing_parts = sorted(set(range(part_count)) - acked_parts)
    part = missing_parts[0]
    unacked = [row for row in delivery_by_part.get(part, [])
               if row[0] not in acked_delivery_ids]
    if len(unacked) > 1:
        return {"status": "invalid", "errors": [
            "phase %s part %d has multiple unacknowledged deliveries" %
            (phase_id, part)]}
    base = {
        "errors": [], "phase_id": phase_id, "part_index": part,
        "part_count": part_count, "delivery_attempt_id": attempt_id,
    }
    if unacked:
        receipt_id, receipt = unacked[0]
        return dict(base, status="acknowledge",
                    delivery_receipt_id=receipt_id,
                    delivery_nonce=receipt.get("delivery_nonce"))
    return dict(base, status="deliver")


def activation_phase_delivery_errors(result, item, phase_id, *,
                                     actor_context_id=None):
    """Prove one phase's frozen set reached the context that is acting now.

    Completeness is judged per attempt, never over their union.  One attempt
    has to cover the phase by itself, because the claim being tested is that
    a single reader received the whole thing: two half-deliveries to two
    contexts leave neither able to say it read the Card, and unioning them
    manufactures a reader that never existed.

    Which attempt has to be the covering one is what separates the callers:

    * an actor (a judgment, a governance write) must be covered by the
      attempt derived from its *own* context -- borrowing another context's
      ack chain would prove that somebody else read the Card.  Another
      context's chain sitting in the same history is not itself a fault;
      the actor's own absence is;
    * an integrator checking history at a queue edge is not the actor: it
      passes no ``actor_context_id`` and needs some one attempt to cover
      the phase, whichever context earned it.

    Every ack is already scoped to the current ``card_bundle_sha256``, so a
    complete chain from a superseded bundle -- internally consistent and
    worthless -- never enters the count.  An activation that never bound a
    host context is `prepared`/`degraded` and stays exempt (v3 D7): it may
    proceed, but nothing it produces may claim machine-enforced delivery.
    """
    scope, _deliveries, acks, _inventory_errors = \
        _activation_phase_inventory(result, item, phase_id)
    if scope["status"] == "not-applicable":
        return []
    if scope["status"] != "active":
        return list(scope["errors"])
    errors = []
    activation = scope["activation"]
    context = scope["context"]
    expected_ids = set(card_activation.phase_piece_ids(context, phase_id))
    if not expected_ids:
        return []
    record = scope["record"]
    part_count = record.get("part_count")
    bundle_sha = activation.get("card_bundle_sha256")
    by_attempt = {}
    for receipt in acks.values():
        earned = by_attempt.setdefault(
            receipt.get("delivery_attempt_id"),
            {"pieces": set(), "parts": set()})
        earned["pieces"].update(
            piece_id for piece_id in receipt.get("phase_piece_ids") or []
            if isinstance(piece_id, str))
        earned["parts"].add(receipt.get("part_index"))

    def _shortfall(earned):
        """Say how one attempt falls short of the phase, or None if it does not."""
        if earned is None:
            return "holds no ack of it at all"
        missing = sorted(expected_ids - earned["pieces"])
        if missing:
            return "covers %d of %d frozen piece(s), missing %s" % (
                len(expected_ids) - len(missing), len(expected_ids),
                ", ".join(missing[:4]) + ("..." if len(missing) > 4 else ""))
        if isinstance(part_count, int) and len(earned["parts"]) != part_count:
            return "acknowledges %d of %d frozen part(s)" % (
                len(earned["parts"]), part_count)
        return None

    if actor_context_id:
        expected_attempt = card_activation.expected_delivery_attempt_id(
            bundle_sha, actor_context_id)
        shortfall = _shortfall(by_attempt.get(expected_attempt))
        if shortfall:
            errors.append(
                "phase %s is not delivered to this actor: attempt %s %s%s" %
                (phase_id, expected_attempt, shortfall,
                 "" if not by_attempt else
                 "; %d other attempt(s) hold acks, and none of them is this "
                 "actor's" % len(
                     [key for key in by_attempt if key != expected_attempt])))
        return errors
    covering = [key for key, earned in by_attempt.items()
                if _shortfall(earned) is None]
    if not covering:
        if not by_attempt:
            errors.append(
                "phase %s is not delivered to this activation: none of its "
                "%d frozen piece(s) has a current ack" %
                (phase_id, len(expected_ids)))
        else:
            errors.append(
                "phase %s is not delivered to this activation: no single "
                "attempt covers it (%s)" %
                (phase_id, "; ".join(
                    "%s %s" % (key, _shortfall(earned))
                    for key, earned in sorted(
                        by_attempt.items(),
                        key=lambda row: str(row[0]))[:2])))
    return errors


def task_phase_delivery_errors(result, phase_id, *, actor_context_id=None):
    """Check one phase across every batch that still carries an activation.

    Some phases are entered by a task-level act rather than a batch one: a
    completion-candidate transition, a Standards governance write.  Those
    acts have no batch of their own, and a phase plan is frozen per batch,
    so the honest scope is every batch currently holding an activation.
    When none does the obligation has no carrier and this returns nothing --
    the gate declines to invent evidence it has no place to look for, which
    is the same reason K13/20 refuses to treat an admission receipt as
    delivery.
    """
    errors = []
    for item in (result.get("queue") or {}).get("required_queue") or []:
        if not isinstance(item, dict):
            continue
        if item.get("state") not in ACTIVE_STATES:
            continue
        for message in activation_phase_delivery_errors(
                result, item, phase_id, actor_context_id=actor_context_id):
            errors.append("%s: %s" % (item.get("id"), message))
    return errors


def judgment_record_set_sha256(records):
    """Hash the exact actual judgment set the batch-review wrapper binds."""
    identity = sorted(
        (
            {
                "target": row["target"],
                "judgment_item_id": row["judgment_item_id"],
                "receipt_id": row["receipt_id"],
            }
            for row in records
        ),
        key=lambda row: (row["judgment_item_id"], row["target"],
                         row["receipt_id"]),
    )
    return kblib.sha256_bytes(kblib.canonical_json_bytes(identity))


def batch_review_judgment_errors(result, item, wrapper_receipt):
    """Prove the Profile's frozen judgment obligations are exactly answered.

    Expected records come from the authorized Profile's Batch Review
    Requirements expanded over the frozen manifest — the same expansion the
    activation receipt froze at `queued -> open`.  Actual records come from
    the current `profile_batch_judgment` receipts the wrapper binds.  One
    missing, extra, duplicated, drifted, mis-roled, or reused record refuses
    the transition.
    """
    errors = []
    item_id = item.get("id")
    catalog = current_receipt_catalog(result)
    activation_entry = catalog.get(item.get("activation_receipt")) if         isinstance(item.get("activation_receipt"), str) else None
    activation = activation_entry[1] if activation_entry else None
    if not isinstance(activation, dict):
        errors.append("%s has no current activation receipt" % item_id)
        return errors
    if activation.get("activation_protocol") != \
            card_activation.ACTIVATION_PROTOCOL:
        errors.append("%s activation does not use the current protocol" %
                      item_id)
        return errors

    view = result.get("_profile_authorized_view") or {}
    contract = view.get("_contract")
    if contract is None or not getattr(contract, "authorized", False):
        errors.append(
            "%s judgment validation requires one authorized typed Profile "
            "contract" % item_id)
        return errors
    wrapper = wrapper_receipt or {}
    try:
        plan_sha256 = wrapper.get("audit_plan_sha256")
        plan = profile_batch_judgment_contract.load_bound_plan(
            result["root"], wrapper.get("audit_plan_path"),
            wrapper.get("audit_plan_id"), plan_sha256)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        errors.append(
            "%s Profile judgment validation requires the wrapper-bound "
            "AuditPlan: "
            "%s" % (item_id, exc))
        return errors
    try:
        expected = card_activation.expand_batch_review_requirements(
            contract, item)
    except (TypeError, ValueError) as exc:
        errors.append("%s requirement expansion failed: %s" % (item_id, exc))
        return errors
    expected_sha = card_activation.review_requirement_set_sha256(expected)
    if activation.get("review_requirement_set_sha256") != expected_sha:
        errors.append(
            "%s current Profile/manifest expansion no longer matches the "
            "activation-frozen requirement set; the batch must be "
            "reactivated" % item_id)
        return errors
    if wrapper.get("review_requirement_set_sha256") != expected_sha:
        errors.append(
            "%s batch review wrapper must bind "
            "review_requirement_set_sha256=%s" % (item_id, expected_sha))
    bound = wrapper.get("judgment_receipt_ids")
    if not isinstance(bound, list) or not all(
            nonempty_string(value) for value in bound):
        errors.append(
            "%s batch review wrapper judgment_receipt_ids must be an "
            "explicit string list" % item_id)
        return errors
    if bound != sorted(set(bound)):
        errors.append(
            "%s batch review wrapper judgment_receipt_ids must be sorted "
            "and unique" % item_id)
        return errors

    try:
        selected = profile_batch_judgment_contract.current_judgment_receipts(
            result["root"], plan, plan_sha256, contract, item, view, catalog)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        errors.append(
            "%s Profile judgment attempt resolution failed: %s" %
            (item_id, exc))
        return errors
    expected_bound = sorted(row["receipt_id"] for row in selected)
    if bound != expected_bound:
        errors.append(
            "%s batch review wrapper binds stale or incomplete judgment "
            "receipts: expected=%s actual=%s" %
            (item_id, expected_bound, bound))
    actual = [{
        "target": row["target"],
        "judgment_item_id": row["judgment_item_id"],
        "receipt_id": row["receipt_id"],
    } for row in selected]
    if (not errors and
            wrapper.get("judgment_record_set_sha256") !=
            judgment_record_set_sha256(actual)):
        errors.append(
            "%s batch review wrapper judgment_record_set_sha256 does not "
            "bind the exact actual judgment set" % item_id)
    return errors


def batch_review_receipt_errors(catalog, receipt_id, *, item_id, task_id,
                                delta_page_receipt_ids):
    """Validate the current batch-level authorization around page evidence.

    Page receipts are validated under the current hard-cut evidence contracts.
    The lifecycle edge is authorized only by one current manual-attestation
    receipt that binds their exact IDs.
    """
    errors = []
    receipt = require_receipt(
        catalog, receipt_id, "%s batch review" % item_id, errors,
        expected={
            "tool": batch_review_receipt_contract.PRODUCER_TOOL,
            "tool_version":
                batch_review_receipt_contract.PRODUCER_TOOL_VERSION,
            "receipt_type_id": batch_review_receipt_contract.RECEIPT_TYPE_ID,
            "gate_id": batch_review_receipt_contract.GATE_ID,
            "check": batch_review_receipt_contract.PRODUCER_CHECK,
            "target": item_id,
            "task_id": task_id,
            "batch_id": item_id,
        },
    )
    if receipt is None:
        return errors
    bound = receipt.get("delta_page_receipt_ids")
    expected = sorted(set(delta_page_receipt_ids or []))
    if (not isinstance(bound, list) or
            not all(nonempty_string(value) for value in bound)):
        errors.append(
            "%s batch review receipt %s delta_page_receipt_ids must be an "
            "explicit string list" % (item_id, receipt_id))
    elif bound != sorted(set(bound)):
        errors.append(
            "%s batch review receipt %s delta_page_receipt_ids must be "
            "sorted and unique" % (item_id, receipt_id))
    elif bound != expected:
        errors.append(
            "%s batch review receipt %s delta_page_receipt_ids=%r, "
            "expected exact Delta page receipt IDs %r" %
            (item_id, receipt_id, bound, expected))
    if isinstance(bound, list):
        for page_receipt_id in expected:
            require_receipt(
                catalog, page_receipt_id,
                "%s batch review page evidence" % item_id, errors,
            )
    return errors
