"""Was the human review obligation answered for this batch.

The frozen judgment set, batch-level authorization, L-tier substantive
review, and the phase-delivery proof that one acting context saw all of it.
The last of those is the point: a review answered across two contexts is two
partial reviews.
"""

import card_activation
import kblib
import metadata_property_state

from queue_runtime.canon import (
    BATCH_REVIEW_GATE_ID,
    MANUAL_ATTESTATION_TOOL,
    MANUAL_ATTESTATION_TOOL_VERSION,
)
from queue_runtime.primitives import nonempty_string
from queue_runtime.receipts import (
    require_receipt,
    current_receipt_catalog,
)


BATCH_REVIEW_CHECK = "batch_gate"


def substantive_review_errors(result, item):
    """Return the K12/12 evidence gaps for one batch's L-tier manifest pages.

    Substantive correctness review is mandatory for L-tier pages and is
    produced by a procedurally separate context; batch integration requires
    that those receipts have all arrived.  This helper counts them for the
    merge-ready write guard: for every manifest page whose Coverage tier is
    ``L``, the current (adoption-filtered) catalog must hold at least one
    passing, non-invalidated receipt with ``check: substantive_review``
    targeting exactly that page.  S/M tiers are covered by batch spot checks
    and are not counted here.  This is a transition-time guard, not a
    runtime-wide validation: history closed before the guard shipped is not
    re-judged by it.
    """
    errors = []
    coverage = result.get("coverage") or {}
    tiers = {
        page.get("path"): page.get("tier")
        for page in coverage.get("pages") or []
        if isinstance(page, dict) and nonempty_string(page.get("path"))
    }
    reviewed_targets = set()
    for entry in current_receipt_catalog(result).values():
        receipt = entry[1] if isinstance(entry, tuple) else entry
        if not isinstance(receipt, dict):
            continue
        if (receipt.get("check") == "substantive_review" and
                receipt.get("result") == "pass" and
                receipt.get("invalidated_by") is None and
                nonempty_string(receipt.get("target"))):
            reviewed_targets.add(receipt.get("target"))
    for object_path in item.get("manifest") or []:
        if tiers.get(object_path) != "L":
            continue
        if object_path not in reviewed_targets:
            errors.append(
                "L-tier manifest page %s has no current passing "
                "substantive_review receipt (K12/12: mandatory for L-tier, "
                "produced by a context other than the author)" % object_path)
    return errors


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
    errors = []
    if not isinstance(item, dict):
        return ["phase delivery check requires one Queue item"]
    catalog = current_receipt_catalog(result)
    entry = catalog.get(item.get("activation_receipt"))
    activation = entry[1] if isinstance(entry, tuple) else entry
    if not isinstance(activation, dict):
        return errors
    if activation.get("activation_protocol") not in \
            card_activation.PHASED_PROTOCOLS:
        # Pre-phase eras owe their own era's obligation, replayed as written.
        return errors
    if activation.get("delivery_assurance") != "host-bound":
        return errors
    context = card_activation.context_from_receipt(activation)
    expected_ids = set(card_activation.phase_piece_ids(context, phase_id))
    if not expected_ids:
        return errors
    record = card_activation.phase_record(context, phase_id) or {}
    part_count = record.get("part_count")
    bundle_sha = activation.get("card_bundle_sha256")
    by_attempt = {}
    for candidate in catalog.values():
        receipt = candidate[1] if isinstance(candidate, tuple) else candidate
        if not isinstance(receipt, dict):
            continue
        if receipt.get("phase_ack_protocol") != \
                card_activation.PHASE_ACK_PROTOCOL:
            continue
        if receipt.get("phase_id") != phase_id:
            continue
        if receipt.get("card_bundle_sha256") != bundle_sha:
            continue
        if receipt.get("result") not in (None, "pass"):
            continue
        if receipt.get("invalidated_by") is not None:
            continue
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
        if item.get("state") not in ("open", "merge-ready"):
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
    the transition.  A batch activated under the pre-review era carries no
    obligations and must carry no judgment bindings: sealed history keeps
    its own shape.
    """
    errors = []
    item_id = item.get("id")
    catalog = current_receipt_catalog(result)
    activation_entry = catalog.get(item.get("activation_receipt")) if         isinstance(item.get("activation_receipt"), str) else None
    activation = activation_entry[1] if activation_entry else None
    protocol = activation.get("activation_protocol") if isinstance(
        activation, dict) else None
    # A batch whose activation predates delivery receipts entirely — or
    # was activated under v1 — predates the review era.  It owes nothing
    # and must carry nothing; the runtime validator, not this gate, is
    # what guarantees a current-era batch cannot shed its activation
    # receipt to slip into this branch.
    legacy = protocol != card_activation.ACTIVATION_PROTOCOL
    wrapper_fields = (
        "review_requirement_set_sha256", "judgment_receipt_ids",
        "judgment_record_set_sha256")
    if legacy:
        for field in wrapper_fields:
            if field in (wrapper_receipt or {}):
                errors.append(
                    "%s was activated under %s; its batch-review wrapper "
                    "must not carry %s" % (item_id, protocol, field))
        return errors

    view = result.get("_profile_authorized_view") or {}
    contract = view.get("_contract")
    if contract is None or not getattr(contract, "authorized", False):
        errors.append(
            "%s judgment validation requires one authorized typed Profile "
            "contract" % item_id)
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
    requirements = {
        row.judgment_item_id: row
        for row in getattr(contract, "batch_review_requirements", ())
    }

    wrapper = wrapper_receipt or {}
    if not expected:
        # A Profile with no requirements owes nothing: an absent binding IS
        # the empty set, so requirement-free adopters keep their exact
        # current wrapper shape.  A wrapper that does carry the fields must
        # still carry them correctly.
        if not any(field in wrapper for field in wrapper_fields):
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

    current_fingerprint = view.get("profile_contract_fingerprint")
    actual = []
    seen = {}
    for receipt_id in bound:
        entry = catalog.get(receipt_id)
        receipt = entry[1] if entry else None
        if not isinstance(receipt, dict):
            errors.append(
                "%s judgment receipt %s is absent from the current catalog" %
                (item_id, receipt_id))
            continue
        label = "%s judgment receipt %s" % (item_id, receipt_id)
        if receipt.get("invalidated_by") is not None:
            errors.append("%s is invalidated" % label)
            continue
        if (receipt.get("tool") != "record_batch_judgment" or
                receipt.get("check") != "profile_batch_judgment" or
                receipt.get("result") != "pass"):
            errors.append("%s is not a passing profile_batch_judgment" %
                          label)
            continue
        if receipt.get("task_id") != result["queue"].get("task_id"):
            errors.append("%s binds a different task" % label)
        if receipt.get("batch_id") != item_id:
            errors.append("%s binds a different batch" % label)
        if receipt.get("opening_transition_receipt") != item.get(
                "activation_receipt"):
            errors.append(
                "%s binds a different activation; a reopened batch redoes "
                "its judgments" % label)
        if receipt.get("review_requirement_set_sha256") != expected_sha:
            errors.append("%s binds a different requirement set" % label)
        if receipt.get("profile_contract_fingerprint") !=                 current_fingerprint:
            errors.append("%s binds a superseded Profile contract" % label)
        target = receipt.get("target")
        judgment_item_id = receipt.get("judgment_item_id")
        requirement = requirements.get(judgment_item_id)
        if requirement is None:
            errors.append("%s names an unregistered Judgment Item" % label)
            continue
        if receipt.get("reviewer_role") !=                 requirement.pass_authority_role_id:
            errors.append(
                "%s reviewer_role %r is not the registered pass authority "
                "%r" % (label, receipt.get("reviewer_role"),
                        requirement.pass_authority_role_id))
        if receipt.get("receipt_schema") != requirement.receipt_schema:
            errors.append("%s carries the wrong receipt schema" % label)
        if requirement.target_selector == "each-manifest-page":
            try:
                _snapshot, semantic_sha = metadata_property_state.                    semantic_page_snapshot(result["root"], target)
            except (OSError, TypeError, UnicodeError, ValueError) as exc:
                errors.append("%s target cannot be snapshotted: %s" %
                              (label, exc))
                semantic_sha = None
            if semantic_sha is not None and receipt.get(
                    "semantic_content_sha256") != semantic_sha:
                errors.append(
                    "%s was judged against different page bytes; the "
                    "changed page must be re-judged" % label)
        key = (target, judgment_item_id)
        if key in seen:
            errors.append(
                "%s duplicates the judgment %s already bound for %r" %
                (label, seen[key], key))
            continue
        seen[key] = receipt_id
        actual.append({
            "target": target,
            "judgment_item_id": judgment_item_id,
            "receipt_id": receipt_id,
        })

    expected_keys = {(row["target"], row["judgment_item_id"])
                     for row in expected}
    actual_keys = set(seen)
    for target, judgment_item_id in sorted(expected_keys - actual_keys):
        errors.append(
            "%s is missing the required judgment (%s, %s)" %
            (item_id, target, judgment_item_id))
    for target, judgment_item_id in sorted(actual_keys - expected_keys):
        errors.append(
            "%s binds the unexpected judgment (%s, %s)" %
            (item_id, target, judgment_item_id))
    if not errors and wrapper.get("judgment_record_set_sha256") !=             judgment_record_set_sha256(actual):
        errors.append(
            "%s batch review wrapper judgment_record_set_sha256 does not "
            "bind the exact actual judgment set" % item_id)
    return errors


def batch_review_receipt_errors(catalog, receipt_id, *, item_id, task_id,
                                delta_page_receipt_ids):
    """Validate the current batch-level authorization around page evidence.

    Page receipts may have been produced by older evidence protocols and are
    validated separately as history.  The lifecycle edge is authorized only
    by one current manual-attestation receipt that binds their exact IDs.
    """
    errors = []
    receipt = require_receipt(
        catalog, receipt_id, "%s batch review" % item_id, errors,
        expected={
            "tool": MANUAL_ATTESTATION_TOOL,
            "tool_version": MANUAL_ATTESTATION_TOOL_VERSION,
            "gate_id": BATCH_REVIEW_GATE_ID,
            "check": BATCH_REVIEW_CHECK,
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
