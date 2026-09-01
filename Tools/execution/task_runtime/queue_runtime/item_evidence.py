"""For one Queue item, is every piece of evidence its state claims present.

The per-batch join across close, delta, property, history and receipts.  This
is where the separately-validated parts are required to agree with each
other; each of them can be individually well formed and still describe a
state that never happened.
"""

import Tools.execution.context_delivery.card_activation as card_activation
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract

from Tools.execution.task_runtime.queue_runtime.canon import (
    ACTIVE_STATES,
    APPLY_AMENDMENT_TOOL_VERSION,
    HOLDS,
    SHA256_RE,
    STATES,
    TOOL,
    TOOL_VERSION,
    TERMINAL_STATES,
    UPDATE_QUEUE_TOOL_VERSION,
)
from Tools.execution.task_runtime.queue_runtime.close_gate import (
    closed_bundle_seal_state,
    closed_gate_errors,
    sealed_closed_bundle_errors,
)
from Tools.execution.task_runtime.queue_runtime.delta import (
    applied_rollback_restore_errors,
    closed_delta_apply_errors,
    settlement_binding_errors,
)
from Tools.execution.task_runtime.queue_runtime.item_history import undischarged_revalidation_hold
from Tools.execution.task_runtime.queue_runtime.primitives import (
    nonempty_string,
    timestamp_value,
    valid_timestamp,
)
from Tools.execution.task_runtime.queue_runtime.history_identity import (
    historical_receipt_identity_errors,
    accounted_upstream_revision_ids,
)
from Tools.execution.task_runtime.queue_runtime.property_state import (
    current_close_transition_metadata_errors,
    current_open_semantic_baseline_errors,
)
from Tools.execution.task_runtime.queue_runtime.receipts import (
    require_receipt,
    delta_gate_receipt_ids,
)
from Tools.execution.task_runtime.queue_runtime.review import batch_review_receipt_errors


INVALIDATION_FIELDS = frozenset((
    "transition_receipt", "invalidated_at", "reason",
    "delta_archive_path", "delta_sha256", "batch_receipts",
    "delta_gate_receipts", "revalidation_receipts",
))
# A rollback taken after the delta was applied additionally names the
# application it undoes and the byte-exact Coverage restore that undid it.
# The three appear together or not at all: a pre-apply rollback never touched
# Coverage and carries none of them, and a partial set would assert a restore
# nobody can verify.
INVALIDATION_APPLIED_ROLLBACK_FIELDS = frozenset((
    "delta_apply_receipt", "coverage_restored_from",
    "coverage_restored_sha256",
))


def item_evidence_errors(item, progress, records, catalog, current_catalog,
                          queue):
    errors = []
    item_id = item.get("id", "<unknown>")
    state = item.get("state")
    hold = item.get("hold_state")
    current_delta_gate_receipts = []
    accounted_versions = accounted_upstream_revision_ids(progress, queue)

    transition = None
    transition_history = []
    transition_ids = item.get("transition_receipts")
    if state != "queued" or transition_ids is not None:
        if (not isinstance(transition_ids, list) or not transition_ids or
                not all(nonempty_string(value) for value in transition_ids)):
            errors.append("%s state %s requires non-empty transition_receipts" %
                          (item_id, state))
            transition_ids = []
        elif len(transition_ids) != len(set(transition_ids)):
            errors.append("%s transition_receipts must be unique" % item_id)
        previous = None
        for position, receipt_id in enumerate(transition_ids):
            current = require_receipt(
                catalog, receipt_id,
                "%s transition[%d]" % (item_id, position), errors,
                expected={
                    "target": item_id,
                    "task_id": queue.get("task_id"),
                },
            )
            if current is None:
                continue
            producer = (current.get("tool"), current.get("tool_version"))
            if producer == ("update_queue", UPDATE_QUEUE_TOOL_VERSION):
                expected_check = "queue_transition"
                replay_protocol = \
                    runtime_state_contract.QUEUE_TRANSITION_REPLAY_PROTOCOL
            elif producer == ("apply_amendment", APPLY_AMENDMENT_TOOL_VERSION):
                expected_check = "amendment_queue_transition"
                replay_protocol = runtime_state_contract.AMENDMENT_BATCH_CANCELLATION_REPLAY_PROTOCOL
            else:
                errors.append("%s transition receipt %s has unsupported "
                              "producer %r/%r" %
                              (item_id, receipt_id,
                               producer[0], producer[1]))
                expected_check = None
                replay_protocol = None
            if expected_check is not None and current.get("check") != expected_check:
                errors.append("%s transition receipt %s check=%r, expected %r" %
                              (item_id, receipt_id, current.get("check"),
                               expected_check))
            transition_class = (
                runtime_state_contract.classify_queue_transition(
                    replay_protocol,
                    current.get("before_state"), current.get("after_state"),
                    current.get("before_hold_state"),
                    current.get("after_hold_state"), historical=True)
                if replay_protocol is not None else None
            )
            if transition_class is None:
                errors.append(
                    "%s transition receipt %s has lifecycle/hold edge "
                    "%r/%r -> %r/%r not authorized for its producer" %
                    (item_id, receipt_id,
                     current.get("before_state"),
                     current.get("before_hold_state"),
                     current.get("after_state"),
                     current.get("after_hold_state")))
            if (producer == ("update_queue", UPDATE_QUEUE_TOOL_VERSION) and
                    current.get("before_state") == "open" and
                    current.get("after_state") == "merge-ready"):
                errors.extend(settlement_binding_errors(
                    current, "%s merge-ready transition %s" %
                    (item_id, receipt_id)))
                if current.get("delta_path") != \
                        runtime_paths.child_path(
                            runtime_paths.DELTA_ROOT,
                            "%s.yaml" % item_id):
                    errors.append(
                        "%s merge-ready transition %s has noncanonical "
                        "delta_path" % (item_id, receipt_id))
                for field in (
                        "delta_sha256",
                        "settlement_coverage_sha256_before",
                        "settlement_prospective_coverage_sha256"):
                    if not SHA256_RE.fullmatch(str(current.get(field) or "")):
                        errors.append(
                            "%s merge-ready transition %s has invalid %s" %
                            (item_id, receipt_id, field))
            errors.extend(current_open_semantic_baseline_errors(
                records["root"], current, item,
                records.get("profile_view"),
                require_live_authority=state in ACTIVE_STATES))
            errors.extend(current_close_transition_metadata_errors(
                records["root"], current, catalog, item_id))
            if (current.get("before_state") not in STATES or
                    current.get("after_state") not in STATES):
                errors.append("%s transition receipt %s has invalid lifecycle "
                              "state edge %r -> %r" %
                              (item_id, receipt_id,
                               current.get("before_state"),
                               current.get("after_state")))
            if (current.get("before_hold_state") not in HOLDS or
                    current.get("after_hold_state") not in HOLDS):
                errors.append("%s transition receipt %s has invalid hold edge "
                              "%r -> %r" %
                              (item_id, receipt_id,
                               current.get("before_hold_state"),
                               current.get("after_hold_state")))
            before_revision = current.get("before_state_revision")
            after_revision = current.get("after_state_revision")
            if (not isinstance(before_revision, int) or
                    isinstance(before_revision, bool) or
                    not isinstance(after_revision, int) or
                    isinstance(after_revision, bool) or
                    after_revision != before_revision + 1 or
                    after_revision < 1 or
                    after_revision > queue.get("state_revision", -1)):
                errors.append("%s transition receipt %s has invalid state "
                              "revision edge %r -> %r" %
                              (item_id, receipt_id, before_revision,
                               after_revision))
            receipt_queue_revision = current.get("queue_revision")
            if (not isinstance(receipt_queue_revision, int) or
                    receipt_queue_revision < 1 or
                    receipt_queue_revision > queue.get("queue_revision", -1)):
                errors.append("%s transition receipt %s has invalid "
                              "queue_revision %r" %
                              (item_id, receipt_id, receipt_queue_revision))
            for fingerprint_field in (
                    "before_required_queue_sha256",
                    "after_required_queue_sha256"):
                fingerprint = current.get(fingerprint_field)
                if (not isinstance(fingerprint, str) or
                        not SHA256_RE.fullmatch(fingerprint)):
                    errors.append("%s transition receipt %s has invalid %s" %
                                  (item_id, receipt_id, fingerprint_field))
            if previous is not None:
                previous_time = timestamp_value(previous.get("checked_at"))
                current_time = timestamp_value(current.get("checked_at"))
                if (previous_time is not None and current_time is not None and
                        current_time < previous_time):
                    errors.append("%s transition timestamps move backward at %s" %
                                  (item_id, receipt_id))
                for left, right in (("after_state", "before_state"),
                                    ("after_hold_state", "before_hold_state")):
                    if previous.get(left) != current.get(right):
                        errors.append("%s transition history breaks between %s "
                                      "and %s" %
                                      (item_id,
                                       transition_ids[position - 1], receipt_id))
                        break
                if previous.get("after_state_revision") >= after_revision:
                    errors.append("%s transition revisions are not increasing" %
                                  item_id)
                if before_revision < previous.get("after_state_revision", -1):
                    errors.append("%s transition history moves state revision backward" %
                                  item_id)
                elif (before_revision == previous.get("after_state_revision") and
                      current.get("queue_revision") ==
                      previous.get("queue_revision") and
                      current.get("before_required_queue_sha256") !=
                      previous.get("after_required_queue_sha256")):
                    errors.append("%s adjacent transition fingerprints do not chain" %
                                  item_id)
            previous = current
            transition_history.append(current)
        if transition_history:
            transition = transition_history[-1]
            if transition_history[0].get("before_state") != "queued":
                errors.append("%s transition history must begin at queued" % item_id)
            if transition.get("after_state") != state:
                errors.append("%s last transition ends in %r, current state is %r" %
                              (item_id, transition.get("after_state"), state))
            if transition.get("after_hold_state") != hold:
                errors.append("%s last transition hold is %r, current hold is %r" %
                              (item_id, transition.get("after_hold_state"), hold))
        if state in ACTIVE_STATES:
            latest_opening = next((
                receipt for receipt in reversed(transition_history)
                if receipt.get("before_state") in
                runtime_state_contract.BATCH_OPENING_SOURCE_STATES
                and receipt.get("after_state") == "open"), None)
            if latest_opening is None:
                errors.append(
                    "%s live state %s has no opening semantic before-set" %
                    (item_id, state))
            elif (latest_opening.get("tool") != "update_queue" or
                    latest_opening.get("tool_version") !=
                    UPDATE_QUEUE_TOOL_VERSION):
                errors.append(
                    "%s live state %s uses a non-current opening producer "
                    "%r/%r" %
                    (item_id, state, latest_opening.get("tool"),
                     latest_opening.get("tool_version")))
    if state in TERMINAL_STATES and hold != "none":
        errors.append("%s history is immutable and must have hold_state none" %
                      item_id)

    # The hold sub-state machine, read over the whole ordered history rather
    # than the last edge.  An item sitting at any hold other than
    # `revalidation-required` while its revalidation obligation is still
    # undischarged reached that hold by routing around the clear, and an item
    # sitting at `none` has had the obligation silently dropped.  Both fail
    # closed here, including for state written by hand.
    if hold != "revalidation-required" and undischarged_revalidation_hold(
            transition_history):
        errors.append(
            "%s left revalidation-required for hold_state %r without the "
            "clearing evidence; the hold is discharged by its own gate, not "
            "by an intermediate hold" % (item_id, hold))

    if hold != "none" and not nonempty_string(item.get("hold_reason")):
        errors.append("%s hold_state %s requires hold_reason" % (item_id, hold))

    if state in runtime_state_contract.QUEUE_STARTED_STATES:
        if not valid_timestamp(item.get("opened_at")):
            errors.append("%s state %s requires a timezone-aware opened_at" %
                          (item_id, state))
        activation_expected = {
            "tool": TOOL,
            "tool_version": TOOL_VERSION,
            "check": "required_queue",
            "queue_check_mode": "require-ready:%s" % item_id,
            "task_id": queue.get("task_id"),
        }
        opening_transition = next((receipt for receipt in transition_history
                                   if receipt.get("before_state") == "queued" and
                                   receipt.get("after_state") == "open"), None)
        if opening_transition is not None:
            activation_expected.update({
                "queue_revision": opening_transition.get("queue_revision"),
                "queue_state_revision":
                    opening_transition.get("before_state_revision"),
                "required_queue_sha256":
                    opening_transition.get("before_required_queue_sha256"),
                "coverage_ledger_sha256":
                    opening_transition.get("before_coverage_sha256"),
                "progress_ledger_sha256":
                    opening_transition.get("before_progress_sha256"),
            })
        if item.get("confirmation_required"):
            activation_expected["confirmation_receipt"] = \
                item.get("confirmation_receipt")
        activation_receipt = require_receipt(
            catalog, item.get("activation_receipt"),
            "%s activation" % item_id, errors,
            expected=activation_expected,
        )
        # The admission gate remains current-contract history after the
        # `queued -> open` edge. Its exact current producer identity was
        # required above; retired activation producers are never interpreted.
        errors.extend(historical_receipt_identity_errors(
            activation_receipt, item.get("activation_receipt"),
            "%s activation" % item_id, accounted_versions))
        if (isinstance(activation_receipt, dict) and
                activation_receipt.get("tool") == TOOL and
                activation_receipt.get("tool_version") == TOOL_VERSION):
            activation_context = card_activation.context_from_receipt(
                activation_receipt)
            errors.extend(
                "%s activation %s" % (item_id, error)
                for error in card_activation.activation_context_errors(
                    activation_context))
            if opening_transition is not None:
                for field in (
                        "activation_protocol", "task_contract_sha256",
                        "reading_plan_sha256", "readback_plan_sha256",
                        "card_bundle_sha256", "delivery_mode",
                        "delivery_assurance", "execution_context_id"):
                    if opening_transition.get(field) != \
                            activation_receipt.get(field):
                        errors.append(
                            "%s opening transition does not preserve "
                            "activation %s" % (item_id, field))
        if item.get("confirmation_required"):
            require_receipt(
                catalog, item.get("confirmation_receipt"),
                "%s confirmation" % item_id, errors,
                expected={"check": "confirmation", "target": item_id},
            )

    if state in runtime_state_contract.QUEUE_DELTA_BOUND_STATES:
        if not valid_timestamp(item.get("merge_ready_at")):
            errors.append("%s state %s requires a timezone-aware merge_ready_at" %
                          (item_id, state))
        delta_path = item.get("delta_path")
        if not nonempty_string(delta_path):
            errors.append("%s state %s requires delta_path" % (item_id, state))
        else:
            expected_delta = runtime_paths.child_path(
                runtime_paths.DELTA_ROOT, "%s.yaml" % item_id)
            if delta_path != expected_delta:
                errors.append("%s delta_path must be exactly %s" %
                              (item_id, expected_delta))
            try:
                delta_file = kblib.managed_repository_path(
                    records["root"], delta_path, runtime_paths.DELTA_ROOT,
                    suffixes=(".yaml",), must_exist=True,
                )
                delta_data = kblib.load_yaml_file(delta_file)
                frozen_delta_sha = item.get("delta_sha256")
                if (not isinstance(frozen_delta_sha, str) or
                        not SHA256_RE.fullmatch(frozen_delta_sha)):
                    errors.append("%s state %s requires delta_sha256" %
                                  (item_id, state))
                elif kblib.sha256_file(delta_file) != frozen_delta_sha:
                    errors.append("%s delta bytes do not match frozen "
                                  "delta_sha256" % item_id)
                if delta_data.get("batch") != item_id:
                    errors.append("%s delta document batch must equal %s" %
                                  (item_id, item_id))
                try:
                    current_delta_gate_receipts = delta_gate_receipt_ids(
                        delta_data)
                except ValueError as exc:
                    errors.append("%s %s" % (item_id, exc))
                pages = delta_data.get("pages")
                if not isinstance(pages, list):
                    errors.append("%s delta pages must be an explicit list" % item_id)
                else:
                    delta_paths = []
                    for page_index, page in enumerate(pages):
                        if not isinstance(page, dict):
                            errors.append("%s delta pages[%d] must be a mapping" %
                                          (item_id, page_index))
                            continue
                        page_path = page.get("path")
                        if not nonempty_string(page_path):
                            errors.append("%s delta pages[%d] has no path" %
                                          (item_id, page_index))
                            continue
                        if page_path in delta_paths:
                            errors.append("%s delta repeats page %s" %
                                          (item_id, page_path))
                        delta_paths.append(page_path)
                        gate_receipts = page.get("gate_receipts")
                        if (not isinstance(gate_receipts, list) or
                                not gate_receipts or
                                not all(nonempty_string(value)
                                        for value in gate_receipts)):
                            errors.append("%s delta page %s requires gate_receipts" %
                                          (item_id, page_path))
                        else:
                            for receipt_id in gate_receipts:
                                require_receipt(
                                    catalog, receipt_id,
                                    "%s delta page %s" % (item_id, page_path),
                                    errors,
                                )
                    expected_paths = sorted(item.get("manifest") or [])
                    if sorted(delta_paths) != expected_paths:
                        errors.append("%s delta pages must equal its frozen manifest; "
                                      "found=%r expected=%r" %
                                      (item_id, sorted(delta_paths), expected_paths))
            except (OSError, ValueError, kblib.YamlSubsetError) as exc:
                errors.append("%s delta_path %r is unsafe or missing: %s" %
                              (item_id, delta_path, exc))
        receipts = item.get("batch_receipts")
        if not isinstance(receipts, list) or not receipts or not all(
                nonempty_string(value) for value in receipts):
            errors.append("%s state %s requires non-empty batch_receipts" %
                          (item_id, state))
        else:
            if len(receipts) != 1:
                errors.append("%s batch_receipts must contain exactly one "
                              "current batch-review gate" % item_id)
            else:
                batch_catalog = (current_catalog
                                 if state == "merge-ready" else catalog)
                errors.extend(batch_review_receipt_errors(
                    batch_catalog, receipts[0], item_id=item_id,
                    task_id=queue.get("task_id"),
                    delta_page_receipt_ids=current_delta_gate_receipts,
                ))
                merge_transition = next((
                    candidate for candidate in reversed(transition_history)
                    if candidate.get("before_state") == "open" and
                    candidate.get("after_state") == "merge-ready"
                ), None)
                if (merge_transition is not None and
                        merge_transition.get("evidence_receipt") != receipts[0]):
                    errors.append(
                        "%s open -> merge-ready transition evidence_receipt "
                        "must equal its batch-review gate %s" %
                        (item_id, receipts[0]))

    if state == "closed":
        if not valid_timestamp(item.get("closed_at")):
            errors.append("%s closed state requires a timezone-aware closed_at" %
                          item_id)
        seal_state = closed_bundle_seal_state(item, catalog)
        if seal_state == "mixed":
            errors.append(
                "%s close bundle is partially sealed; the batch-close "
                "gate, Queue consistency snapshot, and delta application "
                "seal together or not at all (K12/07)" % item_id)
        elif seal_state == "sealed":
            errors.extend(sealed_closed_bundle_errors(
                item, transition, catalog, queue,
            ))
        else:
            errors.extend(closed_gate_errors(
                item, transition, catalog, queue, accounted_versions,
                root=records.get("root"),
            ))
            errors.extend(closed_delta_apply_errors(
                item, transition, catalog, queue,
                root=records.get("root"),
            ))

    if state == "cancelled":
        if not valid_timestamp(item.get("cancelled_at")):
            errors.append("%s cancelled state requires a timezone-aware cancelled_at" %
                          item_id)
        if not nonempty_string(item.get("cancellation_amendment")):
            errors.append("%s cancelled state requires cancellation_amendment" %
                          item_id)
        amendment_id = item.get("cancellation_amendment")
        amendments = progress.get("amendments")
        matches = []
        if isinstance(amendments, list):
            matches = [entry for entry in amendments
                       if isinstance(entry, dict) and
                       entry.get("id") == amendment_id]
        if len(matches) != 1:
            errors.append("%s cancellation amendment %r must resolve uniquely" %
                          (item_id, amendment_id))
        else:
            amendment = matches[0]
            expected_amendment = {
                "status": "verified",
                "writeback_done": True,
                "operation": "cancel-batch",
                "cancel_batch_id": item_id,
                "affected_batches": [item_id],
            }
            for field, value in expected_amendment.items():
                if amendment.get(field) != value:
                    errors.append("%s cancellation Amendment %s=%r, expected %r" %
                                  (item_id, field, amendment.get(field), value))
            if sorted(amendment.get("affected_pages") or []) != sorted(
                    item.get("manifest") or []):
                errors.append("%s cancellation Amendment affected_pages must "
                              "equal its manifest" % item_id)
            verification_id = amendment.get("verification_receipt")
            require_receipt(
                catalog, verification_id,
                "%s cancellation Amendment commit" % item_id, errors,
                expected={
                    "tool": "apply_amendment",
                    "tool_version": APPLY_AMENDMENT_TOOL_VERSION,
                    "check": "amendment_transaction",
                    "target": amendment_id,
                    "transaction_phase": "commit",
                    "amendment_id": amendment_id,
                    "operation": "cancel-batch",
                    "actor_role": "integrator",
                },
            )
            if transition is None:
                errors.append("%s cancellation lacks its final transition" %
                              item_id)
            else:
                for field, value in {
                    "tool": "apply_amendment",
                    "check": "amendment_queue_transition",
                    "after_state": "cancelled",
                    "amendment_id": amendment_id,
                }.items():
                    if transition.get(field) != value:
                        errors.append("%s cancellation transition %s=%r, "
                                      "expected %r" %
                                      (item_id, field,
                                      transition.get(field), value))
                if transition.get("tool_version") != \
                        APPLY_AMENDMENT_TOOL_VERSION:
                    errors.append(
                        "%s cancellation transition has non-current "
                        "apply_amendment producer version %r" %
                        (item_id, transition.get("tool_version")))

    timestamp_bindings = []
    opening = next((entry for entry in transition_history
                    if entry.get("before_state") == "queued" and
                    entry.get("after_state") == "open"), None)
    latest_merge = next((entry for entry in reversed(transition_history)
                         if entry.get("before_state") == "open" and
                         entry.get("after_state") == "merge-ready"), None)
    if (latest_merge is not None and
            state in runtime_state_contract.QUEUE_DELTA_BOUND_STATES and
            latest_merge.get("tool") == "update_queue" and
            latest_merge.get("tool_version") == UPDATE_QUEUE_TOOL_VERSION):
        if latest_merge.get("delta_path") != item.get("delta_path"):
            errors.append("%s latest merge-ready transition does not bind "
                          "current delta_path" % item_id)
        if latest_merge.get("delta_sha256") != item.get("delta_sha256"):
            errors.append("%s latest merge-ready transition does not bind "
                          "current delta_sha256" % item_id)
    closing = next((entry for entry in reversed(transition_history)
                    if entry.get("after_state") == "closed"), None)
    cancelling = next((entry for entry in reversed(transition_history)
                       if entry.get("after_state") == "cancelled"), None)
    for field, event in (("opened_at", opening),
                         ("merge_ready_at", latest_merge),
                         ("closed_at", closing),
                         ("cancelled_at", cancelling)):
        if field not in item or event is None:
            continue
        item_time = timestamp_value(item.get(field))
        event_time = timestamp_value(event.get("checked_at"))
        if (item_time is not None and event_time is not None and
                item_time != event_time):
            errors.append("%s %s must equal its transition receipt time" %
                          (item_id, field))
        if item_time is not None:
            timestamp_bindings.append((field, item_time))
    chronological = {field: value for field, value in timestamp_bindings}
    for before_field, after_field in (
            ("opened_at", "merge_ready_at"),
            ("opened_at", "cancelled_at"),
            ("merge_ready_at", "closed_at")):
        if (before_field in chronological and after_field in chronological and
                chronological[after_field] < chronological[before_field]):
            errors.append("%s lifecycle time moves backward: %s < %s" %
                          (item_id, after_field, before_field))

    rollback_transitions = [
        entry for entry in transition_history
        if entry.get("before_state") == "merge-ready" and
        entry.get("after_state") == "open"
    ]
    invalidations = item.get("invalidation_history")
    if invalidations is None:
        invalidations = []
    if not isinstance(invalidations, list):
        errors.append("%s invalidation_history must be an explicit list" % item_id)
        invalidations = []
    if len(invalidations) != len(rollback_transitions):
        errors.append("%s invalidation_history has %d record(s), expected %d "
                      "from transition history" %
                      (item_id, len(invalidations), len(rollback_transitions)))
    seen_paths = set()
    seen_receipts = set()
    invalidated_receipts = set()
    previous_rollback_position = -1
    transition_positions = {
        receipt.get("receipt_id"): position
        for position, receipt in enumerate(transition_history)
        if isinstance(receipt, dict) and
        nonempty_string(receipt.get("receipt_id"))
    }
    for index, record in enumerate(invalidations):
        label = "%s invalidation_history[%d]" % (item_id, index)
        if not isinstance(record, dict):
            errors.append("%s must be a mapping" % label)
            continue
        missing = sorted(INVALIDATION_FIELDS - set(record))
        extra = sorted(set(record) - INVALIDATION_FIELDS -
                       INVALIDATION_APPLIED_ROLLBACK_FIELDS)
        applied_present = INVALIDATION_APPLIED_ROLLBACK_FIELDS & set(record)
        if missing:
            errors.append("%s misses explicit field(s): %s" %
                          (label, ", ".join(missing)))
        if extra:
            errors.append("%s has unsupported field(s): %s" %
                          (label, ", ".join(extra)))
        if applied_present and applied_present != \
                INVALIDATION_APPLIED_ROLLBACK_FIELDS:
            errors.append(
                "%s records an applied-delta rollback but misses explicit "
                "field(s): %s" %
                (label, ", ".join(sorted(
                    INVALIDATION_APPLIED_ROLLBACK_FIELDS - applied_present))))
        for field in sorted(applied_present):
            if not nonempty_string(record.get(field)):
                errors.append("%s %s must be non-empty" % (label, field))
        transition = (rollback_transitions[index]
                      if index < len(rollback_transitions) else None)
        if applied_present == INVALIDATION_APPLIED_ROLLBACK_FIELDS and all(
                nonempty_string(record.get(field))
                for field in INVALIDATION_APPLIED_ROLLBACK_FIELDS):
            errors.extend(applied_rollback_restore_errors(
                label, record, transition, catalog, item_id))
        receipt_id = record.get("transition_receipt")
        if not nonempty_string(receipt_id):
            errors.append("%s transition_receipt must be non-empty" % label)
        elif receipt_id in seen_receipts:
            errors.append("%s repeats transition receipt %s" %
                          (label, receipt_id))
        else:
            seen_receipts.add(receipt_id)
        if transition is not None:
            if transition.get("receipt_id") != receipt_id:
                errors.append("%s does not bind its ordered rollback transition" %
                              label)
            if transition.get("invalidation") != record:
                errors.append("%s differs from its transition receipt binding" %
                              label)
            record_time = timestamp_value(record.get("invalidated_at"))
            transition_time = timestamp_value(transition.get("checked_at"))
            if record_time is None or record_time != transition_time:
                errors.append("%s invalidated_at must equal transition time" %
                              label)
        if not nonempty_string(record.get("reason")):
            errors.append("%s reason must be non-empty" % label)
        delta_sha = record.get("delta_sha256")
        if not isinstance(delta_sha, str) or not SHA256_RE.fullmatch(delta_sha):
            errors.append("%s delta_sha256 is invalid" % label)
        batch_receipts = record.get("batch_receipts")
        if (not isinstance(batch_receipts, list) or not batch_receipts or
                not all(nonempty_string(value) for value in batch_receipts)):
            errors.append("%s batch_receipts must be a non-empty string list" %
                          label)
        elif len(batch_receipts) != len(set(batch_receipts)):
            errors.append("%s batch_receipts must be unique" % label)
        else:
            for batch_receipt in batch_receipts:
                require_receipt(
                    catalog, batch_receipt, "%s batch evidence" % label,
                    errors, expected={
                        "check": "batch_gate",
                        "target": item_id,
                    },
                )
            invalidated_receipts.update(batch_receipts)
        delta_gate_receipts = record.get("delta_gate_receipts")
        if (not isinstance(delta_gate_receipts, list) or
                not delta_gate_receipts or
                not all(nonempty_string(value)
                        for value in delta_gate_receipts)):
            errors.append("%s delta_gate_receipts must be a non-empty string "
                          "list" % label)
        elif (len(delta_gate_receipts) != len(set(delta_gate_receipts)) or
              delta_gate_receipts != sorted(delta_gate_receipts)):
            errors.append("%s delta_gate_receipts must be sorted and unique" %
                          label)
        else:
            for gate_receipt in delta_gate_receipts:
                require_receipt(catalog, gate_receipt,
                                 "%s delta page evidence" % label, errors)
            invalidated_receipts.update(delta_gate_receipts)
        revalidation_receipts = record.get("revalidation_receipts")
        if (not isinstance(revalidation_receipts, list) or
                not all(nonempty_string(value)
                        for value in revalidation_receipts)):
            errors.append("%s revalidation_receipts must be an explicit string "
                          "list" % label)
        elif len(revalidation_receipts) != len(set(revalidation_receipts)):
            errors.append("%s revalidation_receipts must be unique" % label)
        else:
            for gate_receipt in revalidation_receipts:
                require_receipt(catalog, gate_receipt,
                                 "%s revalidation evidence" % label, errors)
            invalidated_receipts.update(revalidation_receipts)
        if transition is not None:
            rollback_position = transition_positions.get(
                transition.get("receipt_id"))
            if rollback_position is not None:
                expected_revalidation = []
                for candidate in transition_history[
                        previous_rollback_position + 1:rollback_position]:
                    if (candidate.get("before_state") ==
                            candidate.get("after_state") and
                            candidate.get("before_hold_state") ==
                            "revalidation-required" and
                            candidate.get("after_hold_state") == "none"):
                        evidence = candidate.get("evidence_receipt")
                        if nonempty_string(evidence):
                            expected_revalidation.append(evidence)
                if revalidation_receipts != expected_revalidation:
                    errors.append("%s revalidation_receipts do not exactly bind "
                                  "this invalidated attempt" % label)
                previous_rollback_position = rollback_position
        archive_path = record.get("delta_archive_path")
        if not nonempty_string(archive_path):
            errors.append("%s delta_archive_path must be non-empty" % label)
            continue
        if archive_path in seen_paths:
            errors.append("%s repeats delta archive path %s" %
                          (label, archive_path))
        seen_paths.add(archive_path)
        try:
            archived = kblib.managed_repository_path(
                records["root"], archive_path, runtime_paths.RECEIPT_ROOT,
                suffixes=(".yaml",), must_exist=True,
            )
            if kblib.sha256_file(archived) != delta_sha:
                errors.append("%s archived delta bytes differ from delta_sha256" %
                              label)
            archived_data = kblib.load_yaml_file(archived)
            if archived_data.get("batch") != item_id:
                errors.append("%s archived delta batch does not match item" % label)
            try:
                archived_gate_receipts = delta_gate_receipt_ids(archived_data)
                if delta_gate_receipts != archived_gate_receipts:
                    errors.append("%s delta_gate_receipts do not exactly match "
                                  "the archived delta" % label)
            except ValueError as exc:
                errors.append("%s archived delta gate evidence is invalid: %s" %
                              (label, exc))
        except (OSError, ValueError, kblib.YamlSubsetError) as exc:
            errors.append("%s delta archive is unsafe or missing: %s" %
                          (label, exc))

    current_batch_receipts = item.get("batch_receipts")
    if isinstance(current_batch_receipts, list):
        replayed = sorted(set(current_batch_receipts).intersection(
            invalidated_receipts))
        if replayed:
            errors.append("%s current batch_receipts reuse invalidated ID(s): %s" %
                          (item_id, ", ".join(replayed)))
    replayed = sorted(set(current_delta_gate_receipts).intersection(
        invalidated_receipts))
    if replayed:
        errors.append("%s current delta gate_receipts reuse invalidated ID(s): %s" %
                      (item_id, ", ".join(replayed)))
    last_rollback_position = max(
        (transition_positions.get(receipt.get("receipt_id"), -1)
         for receipt in rollback_transitions), default=-1)
    for candidate in transition_history[last_rollback_position + 1:]:
        if (candidate.get("before_state") == candidate.get("after_state") and
                candidate.get("before_hold_state") == "revalidation-required" and
                candidate.get("after_hold_state") == "none" and
                candidate.get("evidence_receipt") in invalidated_receipts):
            errors.append("%s current revalidation admission reuses invalidated "
                          "receipt %s" %
                          (item_id, candidate.get("evidence_receipt")))
    return errors
