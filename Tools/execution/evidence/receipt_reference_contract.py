"""Canonical typed graph for references between durable Receipt records.

This module owns the *shape* and the resolution requirement of a Receipt
reference.  It deliberately knows nothing about repositories, ledgers,
producer implementations, or the seal writer.  Those higher layers may walk
the graph, but they may not register another private list of reference fields.

``aggregate-closure`` is orthogonal to materialization.  A reference can need
only an ID, a proved cold projection, or a complete body, while also belonging
to an atomic close/revalidation/transaction closure.
"""

from dataclasses import dataclass


MATERIALIZATION_ID_ONLY = "id-only"
MATERIALIZATION_COLD_PROJECTION = "cold-projection"
MATERIALIZATION_BODY_REQUIRED = "body-required"
MATERIALIZATION_ORDER = {
    MATERIALIZATION_ID_ONLY: 0,
    MATERIALIZATION_COLD_PROJECTION: 1,
    MATERIALIZATION_BODY_REQUIRED: 2,
}

CARDINALITY_ONE = "one"
CARDINALITY_OPTIONAL = "zero-or-one"
CARDINALITY_MANY = "many"

CLOSE_BUNDLE_CLOSURE = "close-bundle"
BATCH_REVIEW_CLOSURE = "batch-review"
QUEUE_TRANSITION_CLOSURE = "queue-transition"
TASK_TRANSITION_CLOSURE = "task-transition"
TERMINAL_COMPLETION_CLOSURE = "terminal-completion"
MAINTENANCE_COMPLETION_CLOSURE = "maintenance-completion"
AMENDMENT_CLOSURE = "amendment"
REVALIDATION_CLOSURE = "standards-revalidation"
ADOPTION_CLOSURE = "standards-adoption"
WRITER_TRANSACTION_CLOSURE = "writer-transaction"

SOURCE_ITEM = "queue-item"
SOURCE_INVALIDATION = "queue-invalidation"
SOURCE_TRANSITION = "queue-transition"
SOURCE_TASK_TRANSITION = "task-transition"
SOURCE_PROGRESS = "progress-ledger"
SOURCE_PROGRESS_ADOPTION = "progress-standards-adoption"
SOURCE_STANDARDS_STATE = "active-standards-state"
SOURCE_PROFILE_ADOPTION = "profile-adoption-receipt"
SOURCE_STANDARDS_ADOPTION = "standards-adoption-receipt"
SOURCE_COVERAGE = "coverage-ledger"
SOURCE_CLOSE = "close-aggregate"
SOURCE_CLOSE_GLOBAL_REVIEW = "close-global-review"
SOURCE_CLOSE_ATTESTATION = "close-reviewer-attestation"
SOURCE_PAGE_REVIEW = "close-page-review"
SOURCE_AUDIT_RECEIPT = "audit-receipt"
SOURCE_DELTA_APPLY = "delta-apply"
SOURCE_REVALIDATION = "standards-revalidation-aggregate"
SOURCE_BATCH_REVIEW = "batch-review-aggregate"
SOURCE_WRITER_OPERATION = "writer-lock-operation"

# A projection is a consumer contract, not a seal-writer implementation
# detail.  The base fields are the current K12/07 projection; the graph adds
# fields named by typed cold-projection consumers.
BASE_COLD_PROJECTION_FIELDS = (
    "receipt_type_id", "tool", "tool_version", "check", "gate_id",
    "result", "target",
    "batch_id", "task_id", "upstream_revision_id",
    "selected_profile_manifest", "queue_check_mode", "checked_at",
)
PASS_PROJECTION_FIELDS = ("result", "invalidated_by")
IDENTITY_PROJECTION_FIELDS = (
    "tool", "tool_version", "check", "gate_id", "target", "result",
    "invalidated_by",
)


class ReceiptReferenceError(ValueError):
    """The typed reference graph cannot safely interpret a record."""


class UnknownReceiptSource(ReceiptReferenceError):
    """A caller requested a source kind the graph does not own."""


class ReferenceShapeError(ReceiptReferenceError):
    """A declared path has a value of the wrong structural type."""


class ReferenceCycleError(ReceiptReferenceError):
    """A recursive reference/source walk returned to an active node."""


class UnresolvedBodyReference(ReceiptReferenceError):
    """A body-required closure member cannot be resolved."""


@dataclass(frozen=True)
class ReceiptReferenceSpec:
    """One current-contract edge in the Receipt reference graph."""

    edge_id: str
    source_kind: str
    path: tuple
    cardinality: str
    materialization: str
    closure: str = None
    projection_fields: tuple = ()
    keep_hot: bool = False
    alias: bool = False


@dataclass(frozen=True)
class ReceiptReference:
    """One concrete ID extracted through a declared graph edge."""

    receipt_id: str
    spec: ReceiptReferenceSpec
    source_path: tuple


@dataclass(frozen=True)
class ResolvedReceipt:
    """Normalized resolver result for hot, projected-cold, or cold-body data."""

    receipt_id: str
    origin: str
    relative_path: str
    projection: dict
    body: dict


def _spec(edge_id, source_kind, path, cardinality, materialization,
          closure=None, projection_fields=(), keep_hot=False, alias=False):
    if materialization not in MATERIALIZATION_ORDER:
        raise ValueError("unknown Receipt materialization %r" % materialization)
    return ReceiptReferenceSpec(
        edge_id=edge_id,
        source_kind=source_kind,
        path=tuple(path),
        cardinality=cardinality,
        materialization=materialization,
        closure=closure,
        projection_fields=tuple(projection_fields),
        keep_hot=keep_hot,
        alias=alias,
    )


# Every reference path below is declared once.  ``keep_hot`` is deliberately
# separate from materialization: current consumers may require a complete
# body even when a projection exists, and the graph must not silently enlarge
# the set of rows that may seal.
RECEIPT_REFERENCE_SPECS = (
    # Required Queue item.
    _spec("queue-item.transition", SOURCE_ITEM, ("transition_receipts[]",),
          CARDINALITY_MANY, MATERIALIZATION_BODY_REQUIRED,
          QUEUE_TRANSITION_CLOSURE, keep_hot=True),
    _spec("queue-item.activation", SOURCE_ITEM, ("activation_receipt",),
          CARDINALITY_OPTIONAL, MATERIALIZATION_BODY_REQUIRED,
          keep_hot=True),
    _spec("queue-item.confirmation", SOURCE_ITEM,
          ("confirmation_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_COLD_PROJECTION,
          projection_fields=IDENTITY_PROJECTION_FIELDS, keep_hot=True),
    _spec("queue-item.batch-review", SOURCE_ITEM, ("batch_receipts[]",),
          CARDINALITY_MANY, MATERIALIZATION_BODY_REQUIRED,
          BATCH_REVIEW_CLOSURE, keep_hot=True),
    _spec("queue-item.queue-consistency", SOURCE_ITEM,
          ("queue_consistency_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_COLD_PROJECTION, CLOSE_BUNDLE_CLOSURE,
          projection_fields=IDENTITY_PROJECTION_FIELDS),
    _spec("queue-item.close-gate", SOURCE_ITEM, ("close_gate_receipt",),
          CARDINALITY_OPTIONAL, MATERIALIZATION_BODY_REQUIRED,
          CLOSE_BUNDLE_CLOSURE),
    _spec("queue-item.delta-apply", SOURCE_ITEM, ("delta_apply_receipt",),
          CARDINALITY_OPTIONAL, MATERIALIZATION_COLD_PROJECTION,
          CLOSE_BUNDLE_CLOSURE,
          projection_fields=IDENTITY_PROJECTION_FIELDS),

    # Invalidation history embedded by both item and transition records.
    _spec("invalidation.transition", SOURCE_INVALIDATION,
          ("transition_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, QUEUE_TRANSITION_CLOSURE,
          keep_hot=True),
    _spec("invalidation.delta-apply", SOURCE_INVALIDATION,
          ("delta_apply_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, keep_hot=True),
    _spec("invalidation.batch", SOURCE_INVALIDATION, ("batch_receipts[]",),
          CARDINALITY_MANY, MATERIALIZATION_COLD_PROJECTION,
          projection_fields=IDENTITY_PROJECTION_FIELDS, keep_hot=True),
    _spec("invalidation.delta-gate", SOURCE_INVALIDATION,
          ("delta_gate_receipts[]",), CARDINALITY_MANY,
          MATERIALIZATION_COLD_PROJECTION,
          projection_fields=PASS_PROJECTION_FIELDS, keep_hot=True),
    _spec("invalidation.revalidation", SOURCE_INVALIDATION,
          ("revalidation_receipts[]",), CARDINALITY_MANY,
          MATERIALIZATION_COLD_PROJECTION,
          REVALIDATION_CLOSURE, projection_fields=PASS_PROJECTION_FIELDS),

    # Queue transition receipt.  evidence_receipt and page_review_receipts are
    # aliases; the semantic owner edge supplies the stronger requirement.
    _spec("queue-transition.evidence", SOURCE_TRANSITION,
          ("evidence_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_ID_ONLY, alias=True),
    _spec("queue-transition.standards-revalidation", SOURCE_TRANSITION,
          ("standards_revalidation_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, REVALIDATION_CLOSURE,
          keep_hot=True),
    _spec("queue-transition.queue-consistency", SOURCE_TRANSITION,
          ("queue_consistency_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_COLD_PROJECTION, CLOSE_BUNDLE_CLOSURE,
          projection_fields=IDENTITY_PROJECTION_FIELDS, alias=True),
    _spec("queue-transition.close-gate", SOURCE_TRANSITION,
          ("close_gate_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, CLOSE_BUNDLE_CLOSURE, alias=True),
    _spec("queue-transition.delta-apply", SOURCE_TRANSITION,
          ("delta_apply_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_COLD_PROJECTION, CLOSE_BUNDLE_CLOSURE,
          projection_fields=IDENTITY_PROJECTION_FIELDS, alias=True),
    _spec("queue-transition.page-review", SOURCE_TRANSITION,
          ("page_review_receipts[]",), CARDINALITY_MANY,
          MATERIALIZATION_ID_ONLY, CLOSE_BUNDLE_CLOSURE, alias=True),

    # Task-transition receipts are retained by Progress and replayed as the
    # sole task-state history.  Their completion evidence is also projected
    # into the terminal/maintenance Progress blocks, while the first
    # activation binds the exact Queue transition that opened the task.
    _spec("task-transition.evidence", SOURCE_TASK_TRANSITION,
          ("evidence_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_COLD_PROJECTION, TASK_TRANSITION_CLOSURE,
          projection_fields=PASS_PROJECTION_FIELDS),
    _spec("task-transition.first-open", SOURCE_TASK_TRANSITION,
          ("first_open_transition_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, TASK_TRANSITION_CLOSURE,
          keep_hot=True),

    # Progress is the durable task-level receipt root.  Every reference field
    # in its closed schema is declared here, including aliases whose semantic
    # owner also appears in an append-only history list.  The complete bodies
    # of writer transactions, task transitions, terminal evidence,
    # maintenance evidence, and Amendments stay hot because their current
    # consumers replay fields that are not part of the cold projection.
    _spec("progress.initial-task-plan", SOURCE_PROGRESS,
          ("initial_task_plan_receipt",), CARDINALITY_ONE,
          MATERIALIZATION_BODY_REQUIRED, WRITER_TRANSACTION_CLOSURE,
          keep_hot=True),
    _spec("progress.initial-queue", SOURCE_PROGRESS,
          ("initial_queue_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, WRITER_TRANSACTION_CLOSURE,
          keep_hot=True),
    _spec("progress.task-transition-history", SOURCE_PROGRESS,
          ("task_transition_receipts[]",), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, TASK_TRANSITION_CLOSURE,
          keep_hot=True),
    _spec("progress.checkpoint-task-transition", SOURCE_PROGRESS,
          ("checkpoint", "task_transition_receipt"), CARDINALITY_OPTIONAL,
          MATERIALIZATION_ID_ONLY, TASK_TRANSITION_CLOSURE,
          keep_hot=True, alias=True),
    _spec("progress.terminal-proof", SOURCE_PROGRESS,
          ("terminal_audit", "terminal_proof_receipt"),
          CARDINALITY_OPTIONAL, MATERIALIZATION_BODY_REQUIRED,
          TERMINAL_COMPLETION_CLOSURE, keep_hot=True),
    _spec("progress.terminal-queue-check", SOURCE_PROGRESS,
          ("terminal_audit", "queue_check_receipt"),
          CARDINALITY_OPTIONAL, MATERIALIZATION_BODY_REQUIRED,
          TERMINAL_COMPLETION_CLOSURE, keep_hot=True),
    _spec("progress.maintenance-gate", SOURCE_PROGRESS,
          ("maintenance_completion", "completion_gate_receipt"),
          CARDINALITY_OPTIONAL, MATERIALIZATION_BODY_REQUIRED,
          MAINTENANCE_COMPLETION_CLOSURE, keep_hot=True),
    _spec("progress.maintenance-budget", SOURCE_PROGRESS,
          ("maintenance_completion", "budget_manifest_receipt"),
          CARDINALITY_OPTIONAL, MATERIALIZATION_BODY_REQUIRED,
          MAINTENANCE_COMPLETION_CLOSURE, keep_hot=True),
    _spec("progress.maintenance-ledger", SOURCE_PROGRESS,
          ("maintenance_completion", "ledger_advance_receipt"),
          CARDINALITY_OPTIONAL, MATERIALIZATION_BODY_REQUIRED,
          MAINTENANCE_COMPLETION_CLOSURE, keep_hot=True),
    _spec("progress.maintenance-watermark", SOURCE_PROGRESS,
          ("maintenance_completion", "watermark_advance_receipt"),
          CARDINALITY_OPTIONAL, MATERIALIZATION_BODY_REQUIRED,
          MAINTENANCE_COMPLETION_CLOSURE, keep_hot=True),
    _spec("progress.amendment-registration", SOURCE_PROGRESS,
          ("amendments[]", "registration_receipt"), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, AMENDMENT_CLOSURE, keep_hot=True),
    _spec("progress.amendment-withdrawal", SOURCE_PROGRESS,
          ("amendments[]", "withdrawal_receipt"), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, AMENDMENT_CLOSURE, keep_hot=True),
    _spec("progress.amendment-verification", SOURCE_PROGRESS,
          ("amendments[]", "verification_receipt"), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, AMENDMENT_CLOSURE, keep_hot=True),
    _spec("progress.amendment-replan-transaction", SOURCE_PROGRESS,
          ("amendments[]", "transaction_receipt_id"), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, AMENDMENT_CLOSURE, keep_hot=True),
    _spec("progress.amendment-previous-commit", SOURCE_PROGRESS,
          ("amendments[]", "previous_transaction_commit_receipt"),
          CARDINALITY_MANY, MATERIALIZATION_ID_ONLY, AMENDMENT_CLOSURE,
          keep_hot=True, alias=True),

    # Progress Standards-adoption record.
    _spec("progress-adoption.verification", SOURCE_PROGRESS_ADOPTION,
          ("verification_receipt",), CARDINALITY_ONE,
          MATERIALIZATION_BODY_REQUIRED, ADOPTION_CLOSURE, keep_hot=True),
    _spec("progress-adoption.immediate-gate", SOURCE_PROGRESS_ADOPTION,
          ("immediate_gate_receipts[]",), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, ADOPTION_CLOSURE, keep_hot=True),
    _spec("progress-adoption.invalidated-history", SOURCE_PROGRESS_ADOPTION,
          ("invalidated_evidence_receipt_ids[]",), CARDINALITY_MANY,
          MATERIALIZATION_ID_ONLY),
    _spec("standards-state.latest-adoption", SOURCE_STANDARDS_STATE,
          ("latest_adoption_receipt",), CARDINALITY_ONE,
          MATERIALIZATION_BODY_REQUIRED, ADOPTION_CLOSURE, keep_hot=True),

    # The two current-adoption Receipt bodies.  Active Standards state names
    # the final adoption Receipt; these edges complete the body dependency
    # graph without making Progress or a filename-based seal rule reproduce
    # either producer's fields.  Invalidated evidence remains historical
    # identity only and is not promoted back into current authority.
    _spec("profile-adoption.profile-load", SOURCE_PROFILE_ADOPTION,
          ("profile_load_receipt_id",), CARDINALITY_ONE,
          MATERIALIZATION_BODY_REQUIRED, ADOPTION_CLOSURE, keep_hot=True),
    _spec("standards-adoption.immediate-gate", SOURCE_STANDARDS_ADOPTION,
          ("immediate_gate_receipts[]",), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, ADOPTION_CLOSURE, keep_hot=True),
    _spec("standards-adoption.invalidated-history",
          SOURCE_STANDARDS_ADOPTION,
          ("invalidated_evidence_receipt_ids[]",), CARDINALITY_MANY,
          MATERIALIZATION_ID_ONLY),

    # Current Coverage property owners require the complete evidence body.
    _spec("coverage-page.gate-receipts", SOURCE_COVERAGE,
          ("pages[]", "gate_receipts[]"), CARDINALITY_MANY,
          MATERIALIZATION_COLD_PROJECTION,
          projection_fields=PASS_PROJECTION_FIELDS, keep_hot=True),
    _spec("coverage-property.evidence", SOURCE_COVERAGE,
          ("pages[]", "property_state{}", "evidence_receipt"),
          CARDINALITY_MANY, MATERIALIZATION_BODY_REQUIRED, keep_hot=True),

    # Current close aggregate. Retired close formats are external archives and
    # never enter this graph.
    _spec("close.queue-consistency", SOURCE_CLOSE,
          ("queue_consistency_receipt",), CARDINALITY_ONE,
          MATERIALIZATION_COLD_PROJECTION, CLOSE_BUNDLE_CLOSURE,
          projection_fields=IDENTITY_PROJECTION_FIELDS),
    _spec("close.delta-apply", SOURCE_CLOSE, ("delta_apply_receipt",),
          CARDINALITY_ONE, MATERIALIZATION_COLD_PROJECTION,
          CLOSE_BUNDLE_CLOSURE,
          projection_fields=IDENTITY_PROJECTION_FIELDS),
    _spec("close.global-review", SOURCE_CLOSE, ("global_review_receipt",),
          CARDINALITY_ONE, MATERIALIZATION_BODY_REQUIRED,
          CLOSE_BUNDLE_CLOSURE),
    _spec("close.reviewer-attestation", SOURCE_CLOSE,
          ("reviewer_attestation_receipt",), CARDINALITY_ONE,
          MATERIALIZATION_BODY_REQUIRED, CLOSE_BUNDLE_CLOSURE),
    _spec("close.corpus-plan", SOURCE_CLOSE, ("corpus_plan_receipt",),
          CARDINALITY_OPTIONAL, MATERIALIZATION_BODY_REQUIRED,
          CLOSE_BUNDLE_CLOSURE),
    _spec("close.page-review", SOURCE_CLOSE, ("page_review_receipts[]",),
          CARDINALITY_MANY, MATERIALIZATION_BODY_REQUIRED,
          CLOSE_BUNDLE_CLOSURE),
    _spec("close.closed-list", SOURCE_CLOSE, ("closed_list_evidence{}",),
          CARDINALITY_MANY, MATERIALIZATION_BODY_REQUIRED,
          CLOSE_BUNDLE_CLOSURE),
    _spec("close.closed-list-producer", SOURCE_CLOSE,
          ("closed_list_producer_evidence{}",), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, CLOSE_BUNDLE_CLOSURE),
    _spec("close.post-delta-evidence", SOURCE_CLOSE,
          ("post_delta_evidence_bindings[]", "evidence_ref"),
          CARDINALITY_MANY, MATERIALIZATION_BODY_REQUIRED,
          CLOSE_BUNDLE_CLOSURE),

    _spec("close-global.reviewer-attestation", SOURCE_CLOSE_GLOBAL_REVIEW,
          ("reviewer_attestation_receipt",), CARDINALITY_ONE,
          MATERIALIZATION_BODY_REQUIRED, CLOSE_BUNDLE_CLOSURE),
    _spec("close-global.closed-list", SOURCE_CLOSE_GLOBAL_REVIEW,
          ("closed_list_evidence{}",), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, CLOSE_BUNDLE_CLOSURE),
    _spec("close-global.closed-list-producer", SOURCE_CLOSE_GLOBAL_REVIEW,
          ("closed_list_producer_evidence{}",), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, CLOSE_BUNDLE_CLOSURE),
    _spec("close-global.post-delta-evidence", SOURCE_CLOSE_GLOBAL_REVIEW,
          ("post_delta_evidence_bindings[]", "evidence_ref"),
          CARDINALITY_MANY, MATERIALIZATION_BODY_REQUIRED,
          CLOSE_BUNDLE_CLOSURE),
    _spec("close-attestation.candidate-baseline", SOURCE_CLOSE_ATTESTATION,
          ("candidate_baseline_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_ID_ONLY, CLOSE_BUNDLE_CLOSURE),
    _spec("close-attestation.post-delta-evidence", SOURCE_CLOSE_ATTESTATION,
          ("post_delta_evidence_bindings[]", "evidence_ref"),
          CARDINALITY_MANY, MATERIALIZATION_BODY_REQUIRED,
          CLOSE_BUNDLE_CLOSURE),
    _spec("close-page.reviewer-attestation", SOURCE_PAGE_REVIEW,
          ("reviewer_attestation_receipt",), CARDINALITY_ONE,
          MATERIALIZATION_BODY_REQUIRED, CLOSE_BUNDLE_CLOSURE),

    # Full AuditReceipt links its historical attempt and producer evidence.
    _spec("audit-receipt.opening-transition", SOURCE_AUDIT_RECEIPT,
          ("opening_transition_receipt",), CARDINALITY_ONE,
          MATERIALIZATION_BODY_REQUIRED, CLOSE_BUNDLE_CLOSURE),
    _spec("audit-receipt.evidence", SOURCE_AUDIT_RECEIPT,
          ("evidence_ref",), CARDINALITY_ONE,
          MATERIALIZATION_BODY_REQUIRED, CLOSE_BUNDLE_CLOSURE),
    _spec("audit-receipt.reused-alias", SOURCE_AUDIT_RECEIPT,
          ("reused_receipt_id",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_ID_ONLY, CLOSE_BUNDLE_CLOSURE, alias=True),

    # Apply-delta evidence can be the current Coverage owner.
    _spec("delta-apply.opening-transition", SOURCE_DELTA_APPLY,
          ("opening_transition_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, QUEUE_TRANSITION_CLOSURE),
    _spec("delta-apply.invalidated-property-history", SOURCE_DELTA_APPLY,
          ("property_events[]", "invalidated_property_receipt_ids[]"),
          CARDINALITY_MANY, MATERIALIZATION_ID_ONLY),

    # Current revalidation reads Gate bodies; current-contract history reads
    # only the aggregate body and treats these child IDs as history.
    _spec("revalidation.boundary-gate", SOURCE_REVALIDATION,
          ("boundary_gate_receipts[]", "receipt_id"), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, REVALIDATION_CLOSURE),
    _spec("revalidation.gate-alias", SOURCE_REVALIDATION,
          ("revalidation_bindings[]", "gate_receipt_id"), CARDINALITY_MANY,
          MATERIALIZATION_ID_ONLY, REVALIDATION_CLOSURE, alias=True),
    _spec("revalidation.superseded-history", SOURCE_REVALIDATION,
          ("revalidation_bindings[]",
           "superseded_invalidated_receipt_ids[]"), CARDINALITY_MANY,
          MATERIALIZATION_ID_ONLY, REVALIDATION_CLOSURE),
    _spec("revalidation.revalidated-history", SOURCE_REVALIDATION,
          ("revalidated_invalidated_receipt_ids[]",), CARDINALITY_MANY,
          MATERIALIZATION_ID_ONLY, REVALIDATION_CLOSURE),

    # Batch-review wrapper.  Review registers remain unsealable in v1, but
    # their aggregate closure still belongs to the same typed graph.
    _spec("batch-review.delta-page", SOURCE_BATCH_REVIEW,
          ("delta_page_receipt_ids[]",), CARDINALITY_MANY,
          MATERIALIZATION_COLD_PROJECTION, BATCH_REVIEW_CLOSURE,
          projection_fields=PASS_PROJECTION_FIELDS),
    _spec("batch-review.judgment", SOURCE_BATCH_REVIEW,
          ("judgment_receipt_ids[]",), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, BATCH_REVIEW_CLOSURE),
    _spec("batch-review.audit-evidence", SOURCE_BATCH_REVIEW,
          ("audit_evidence_bindings[]", "evidence_ref"), CARDINALITY_MANY,
          MATERIALIZATION_BODY_REQUIRED, BATCH_REVIEW_CLOSURE),

    # Active writer lock owner.  The seal command still refuses every lock;
    # declaring its phase graph makes the refusal and recovery inspect the
    # same evidence closure rather than a transaction-id string sweep alone.
    _spec("writer.receipt", SOURCE_WRITER_OPERATION, ("receipt_id",),
          CARDINALITY_OPTIONAL, MATERIALIZATION_BODY_REQUIRED,
          WRITER_TRANSACTION_CLOSURE, keep_hot=True),
    _spec("writer.prepare", SOURCE_WRITER_OPERATION,
          ("prepare_receipt_id",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, WRITER_TRANSACTION_CLOSURE,
          keep_hot=True),
    _spec("writer.commit", SOURCE_WRITER_OPERATION,
          ("commit_receipt_id",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, WRITER_TRANSACTION_CLOSURE,
          keep_hot=True),
    _spec("writer.abort", SOURCE_WRITER_OPERATION,
          ("abort_receipt_id",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, WRITER_TRANSACTION_CLOSURE,
          keep_hot=True),
    _spec("writer.transition", SOURCE_WRITER_OPERATION,
          ("transition_receipt_id",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, WRITER_TRANSACTION_CLOSURE,
          keep_hot=True),
    _spec("writer.task-transition", SOURCE_WRITER_OPERATION,
          ("task_transition_receipt_id",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, WRITER_TRANSACTION_CLOSURE,
          keep_hot=True),
    _spec("writer.immediate-gate", SOURCE_WRITER_OPERATION,
          ("immediate_gate_receipt_id",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_BODY_REQUIRED, WRITER_TRANSACTION_CLOSURE,
          keep_hot=True),
    _spec("writer.registration", SOURCE_WRITER_OPERATION,
          ("registration_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_COLD_PROJECTION, WRITER_TRANSACTION_CLOSURE,
          projection_fields=IDENTITY_PROJECTION_FIELDS, keep_hot=True),
    _spec("writer.previous-commit", SOURCE_WRITER_OPERATION,
          ("previous_transaction_commit_receipt",), CARDINALITY_OPTIONAL,
          MATERIALIZATION_ID_ONLY, WRITER_TRANSACTION_CLOSURE,
          keep_hot=True),
)

_REFERENCE_SPEC_BY_ID = {
    spec.edge_id: spec for spec in RECEIPT_REFERENCE_SPECS
}
if len(_REFERENCE_SPEC_BY_ID) != len(RECEIPT_REFERENCE_SPECS):
    raise ValueError("Receipt reference edge IDs must be unique")


@dataclass(frozen=True)
class ChildSourceSpec:
    parent_kind: str
    path: tuple
    child_kind: str


CHILD_SOURCE_SPECS = (
    ChildSourceSpec(SOURCE_ITEM, ("invalidation_history[]",),
                    SOURCE_INVALIDATION),
    ChildSourceSpec(SOURCE_TRANSITION, ("invalidation",),
                    SOURCE_INVALIDATION),
    ChildSourceSpec(SOURCE_PROGRESS, ("standards_adoptions[]",),
                    SOURCE_PROGRESS_ADOPTION),
)

_KNOWN_SOURCE_KINDS = frozenset(
    spec.source_kind for spec in RECEIPT_REFERENCE_SPECS) | frozenset(
        child.parent_kind for child in CHILD_SOURCE_SPECS) | frozenset(
            child.child_kind for child in CHILD_SOURCE_SPECS)


def _field_token(token):
    if token.endswith("[]"):
        return token[:-2], "list"
    if token.endswith("{}"):
        return token[:-2], "mapping"
    return token, "scalar"


def _values_at_path(record, path):
    values = [record]
    for token in path:
        field, shape = _field_token(token)
        next_values = []
        for value in values:
            if not isinstance(value, dict):
                raise ReferenceShapeError(
                    "Receipt reference path %s reached a non-mapping" %
                    ".".join(path))
            if field not in value or value[field] is None:
                continue
            child = value[field]
            if shape == "list":
                if not isinstance(child, list):
                    raise ReferenceShapeError(
                        "Receipt reference path %s requires a list" %
                        ".".join(path))
                next_values.extend(child)
            elif shape == "mapping":
                if not isinstance(child, dict):
                    raise ReferenceShapeError(
                        "Receipt reference path %s requires a mapping" %
                        ".".join(path))
                next_values.extend(child.values())
            else:
                next_values.append(child)
        values = next_values
    return values


def reference_specs(source_kind):
    """Return the exact specs for one current source contract."""
    if source_kind not in _KNOWN_SOURCE_KINDS:
        raise UnknownReceiptSource(
            "unknown Receipt reference source kind %r" % source_kind)
    return tuple(
        spec for spec in RECEIPT_REFERENCE_SPECS
        if spec.source_kind == source_kind)


def reference_spec(edge_id):
    """Return one named edge or fail closed on an undeclared consumer."""
    try:
        return _REFERENCE_SPEC_BY_ID[edge_id]
    except KeyError as exc:
        raise UnknownReceiptSource(
            "unknown Receipt reference edge %r" % edge_id) from exc


def _iter_references(record, source_kind, recursive, prefix, active_records):
    if not isinstance(record, dict):
        raise ReferenceShapeError(
            "%s source must be a mapping" % source_kind)
    marker = id(record)
    if marker in active_records:
        raise ReferenceCycleError(
            "Receipt source nesting cycles at %s" % ".".join(prefix))
    active_records.add(marker)
    try:
        for spec in reference_specs(source_kind):
            for value in _values_at_path(record, spec.path):
                if not isinstance(value, str) or not value.strip():
                    raise ReferenceShapeError(
                        "%s must identify a non-empty Receipt ID" %
                        ".".join(prefix + spec.path))
                yield ReceiptReference(
                    receipt_id=value,
                    spec=spec,
                    source_path=prefix + spec.path,
                )
        if recursive:
            for child in CHILD_SOURCE_SPECS:
                if child.parent_kind != source_kind:
                    continue
                for index, nested in enumerate(
                        _values_at_path(record, child.path)):
                    if not isinstance(nested, dict):
                        raise ReferenceShapeError(
                            "%s child source must be a mapping" %
                            ".".join(prefix + child.path))
                    child_prefix = prefix + child.path + (str(index),)
                    yield from _iter_references(
                        nested, child.child_kind, recursive,
                        child_prefix, active_records)
    finally:
        active_records.remove(marker)


def iter_receipt_references(record, source_kind, recursive=True):
    """Yield concrete typed references, failing closed on shape/cycles."""
    return _iter_references(
        record, source_kind, recursive, (), set())


def reference_ids(record, source_kind, recursive=True,
                  closure=None, minimum_materialization=None,
                  keep_hot=None):
    """Return IDs selected by graph policy without re-encoding field names."""
    minimum = (MATERIALIZATION_ORDER[minimum_materialization]
               if minimum_materialization is not None else None)
    result = set()
    for reference in iter_receipt_references(
            record, source_kind, recursive=recursive):
        spec = reference.spec
        if closure is not None and spec.closure != closure:
            continue
        if minimum is not None and \
                MATERIALIZATION_ORDER[spec.materialization] < minimum:
            continue
        if keep_hot is not None and spec.keep_hot is not keep_hot:
            continue
        result.add(reference.receipt_id)
    return result


def edge_reference_ids(record, source_kind, edge_id, recursive=True):
    """Return concrete IDs for exactly one named edge."""
    declared = reference_spec(edge_id)
    if declared.source_kind != source_kind:
        raise UnknownReceiptSource(
            "Receipt edge %s does not belong to source %s" %
            (edge_id, source_kind))
    return {
        reference.receipt_id
        for reference in iter_receipt_references(
            record, source_kind, recursive=recursive)
        if reference.spec.edge_id == edge_id
    }


def walk_receipt_closure(record, source_kind, resolve_body, closure,
                         source_kind_resolver,
                         minimum_materialization=
                         MATERIALIZATION_BODY_REQUIRED):
    """Walk one typed aggregate closure and return every referenced ID.

    ``resolve_body`` must return a mapping for body-required members.  Missing
    bodies, malformed paths, and receipt cycles all fail closed.
    Parallel aliases to an already completed node are allowed; only a return
    to an active recursion node is a cycle.
    """
    minimum = MATERIALIZATION_ORDER[minimum_materialization]
    found = set()
    completed = set()
    active = set()

    def visit(body, kind):
        for reference in iter_receipt_references(
                body, kind, recursive=True):
            spec = reference.spec
            if spec.closure != closure or \
                    MATERIALIZATION_ORDER[spec.materialization] < minimum:
                continue
            receipt_id = reference.receipt_id
            found.add(receipt_id)
            if receipt_id in completed:
                continue
            if receipt_id in active:
                raise ReferenceCycleError(
                    "Receipt closure %s cycles at %s" %
                    (closure, receipt_id))
            target = resolve_body(receipt_id)
            if not isinstance(target, dict):
                raise UnresolvedBodyReference(
                    "Receipt closure %s cannot resolve body %s" %
                    (closure, receipt_id))
            target_kind = source_kind_resolver(target)
            if target_kind is None:
                completed.add(receipt_id)
                continue
            active.add(receipt_id)
            try:
                visit(target, target_kind)
            finally:
                active.remove(receipt_id)
            completed.add(receipt_id)

    visit(record, source_kind)
    return found


def walk_body_dependencies(record, source_kind, resolve_body,
                           source_kind_resolver):
    """Walk every body-required edge reachable from one current owner."""
    found = set()
    completed = set()
    active = set()

    def visit(body, kind):
        for reference in iter_receipt_references(body, kind, recursive=True):
            if reference.spec.materialization != \
                    MATERIALIZATION_BODY_REQUIRED:
                continue
            receipt_id = reference.receipt_id
            found.add(receipt_id)
            if receipt_id in completed:
                continue
            if receipt_id in active:
                raise ReferenceCycleError(
                    "Receipt body dependency cycles at %s" % receipt_id)
            target = resolve_body(receipt_id)
            if not isinstance(target, dict):
                raise UnresolvedBodyReference(
                    "Receipt body dependency cannot resolve %s" % receipt_id)
            target_kind = source_kind_resolver(target)
            if target_kind is None:
                completed.add(receipt_id)
                continue
            active.add(receipt_id)
            try:
                visit(target, target_kind)
            finally:
                active.remove(receipt_id)
            completed.add(receipt_id)

    visit(record, source_kind)
    return found


def schema_reference_fields(source_kind, include_child_sources=False):
    """Project top-level reference-bearing fields for schema parity tests."""
    fields = set()
    for spec in reference_specs(source_kind):
        field, _shape = _field_token(spec.path[0])
        fields.add(field)
    if include_child_sources:
        for child in CHILD_SOURCE_SPECS:
            if child.parent_kind == source_kind:
                field, _shape = _field_token(child.path[0])
                fields.add(field)
    return frozenset(fields)


def schema_reference_leaf_fields(source_kind):
    """Project the leaf field names owned by one source schema."""
    fields = set()
    for spec in reference_specs(source_kind):
        field, _shape = _field_token(spec.path[-1])
        fields.add(field)
    return frozenset(fields)


def cold_projection_fields():
    """Return the stable union required by all projection consumers."""
    fields = list(BASE_COLD_PROJECTION_FIELDS)
    for spec in RECEIPT_REFERENCE_SPECS:
        for field in spec.projection_fields:
            if field not in fields:
                fields.append(field)
    return tuple(fields)


RECEIPT_COLD_PROJECTION_FIELDS = cold_projection_fields()
