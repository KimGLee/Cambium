"""Tool-side registry for adopter-runtime object paths and classifications.

This registry classifies paths only. It does not define object schemas, state
transitions, authorization, or recovery behavior. Producers and consumers
import the same spelling from here so changing a physical location cannot
silently create a second runtime object.
"""

from collections import namedtuple
import os
import stat


RuntimeObject = namedtuple("RuntimeObject", ("category", "path"))
_PathReference = namedtuple(
    "PathReference", ("runtime_path_id", "constraint", "path"))

CANONICAL_STATE = "canonical-state"
BOUND_INPUT = "bound-input"
EVIDENCE = "evidence"
RECOVERY = "recovery"
TRANSIENT = "transient"
DERIVED_PROJECTION = "derived-projection"

RUNTIME_ROOT = ".cambium"
GOVERNANCE_ROOT = RUNTIME_ROOT + "/governance"
STATE_ROOT = RUNTIME_ROOT + "/state"
WORK_SPEC_ROOT = RUNTIME_ROOT + "/work_specs"
DELTA_ROOT = RUNTIME_ROOT + "/deltas"
RECEIPT_ROOT = RUNTIME_ROOT + "/receipts"
RECEIPT_COLD_ROOT = RECEIPT_ROOT + "/cold"
RECEIPT_COLD_SEGMENT_ROOT = RECEIPT_COLD_ROOT + "/segments"
RECEIPT_COLD_EVIDENCE_ROOT = RECEIPT_COLD_ROOT + "/close-evidence"
RECEIPT_COLD_PENDING_ROOT = RECEIPT_COLD_ROOT + "/pending"
TRANSIENT_ROOT = RUNTIME_ROOT + "/tmp"
DERIVED_ROOT = RUNTIME_ROOT + "/derived"
DERIVED_INTERFACE_ROOT = DERIVED_ROOT + "/interfaces"
DERIVED_HOST_CONFIG_ROOT = DERIVED_ROOT + "/host-configs"
REPORT_ROOT = RUNTIME_ROOT + "/reports"

_CHILD_NAMESPACE_ROOTS = frozenset((
    RUNTIME_ROOT,
    GOVERNANCE_ROOT,
    STATE_ROOT,
    WORK_SPEC_ROOT,
    DELTA_ROOT,
    RECEIPT_ROOT,
    RECEIPT_COLD_ROOT,
    RECEIPT_COLD_SEGMENT_ROOT,
    RECEIPT_COLD_EVIDENCE_ROOT,
    RECEIPT_COLD_PENDING_ROOT,
    TRANSIENT_ROOT,
    DERIVED_ROOT,
    DERIVED_INTERFACE_ROOT,
    DERIVED_HOST_CONFIG_ROOT,
    REPORT_ROOT,
))


def child_path(namespace_root, *parts):
    """Return a safe repository-relative child of a managed runtime root.

    Dynamic leaf identities remain owned by their producer, but every producer
    must derive the physical path from this registry.  Segments are deliberately
    restricted to one path component so a caller cannot smuggle an absolute
    path or traversal through a supposedly managed child.
    """
    if namespace_root not in _CHILD_NAMESPACE_ROOTS:
        raise ValueError("runtime child must use a registered runtime namespace")
    clean = []
    for part in parts:
        if not isinstance(part, str) or not part:
            raise ValueError("runtime child segments must be non-empty strings")
        if part in (".", "..") or "/" in part or "\\" in part:
            raise ValueError("unsafe runtime child segment: %r" % part)
        clean.append(part)
    if not clean:
        raise ValueError("runtime child requires at least one segment")
    return namespace_root + "/" + "/".join(clean)


REPLAN_DELTA_ROOT = child_path(DELTA_ROOT, "replans")
AMENDMENT_DELTA_ROOT = child_path(DELTA_ROOT, "amendments")
CONTRACT_AMENDMENT_DELTA_ROOT = child_path(
    DELTA_ROOT, "contract-amendments")
STANDARDS_ADOPTION_DELTA_ROOT = child_path(
    DELTA_ROOT, "standards-adoptions")
TASK_PLAN_DELTA_ROOT = child_path(DELTA_ROOT, "task-plans")
CORPUS_PLAN_ACCEPTANCE_DELTA_ROOT = child_path(
    DELTA_ROOT, "corpus-plan-acceptances")
INVALIDATED_DELTA_RECEIPT_ROOT = child_path(
    RECEIPT_ROOT, "invalidated-deltas")
PRE_APPLY_COVERAGE_RECEIPT_ROOT = child_path(
    RECEIPT_ROOT, "pre-apply-coverage")

_CHILD_NAMESPACE_ROOTS = _CHILD_NAMESPACE_ROOTS.union((
    REPLAN_DELTA_ROOT,
    AMENDMENT_DELTA_ROOT,
    CONTRACT_AMENDMENT_DELTA_ROOT,
    STANDARDS_ADOPTION_DELTA_ROOT,
    TASK_PLAN_DELTA_ROOT,
    CORPUS_PLAN_ACCEPTANCE_DELTA_ROOT,
    INVALIDATED_DELTA_RECEIPT_ROOT,
    PRE_APPLY_COVERAGE_RECEIPT_ROOT,
))

# A category can have more than one physical namespace, and one physical
# namespace can contain objects of different lifecycle classes. Governance
# identity and task state are both canonical state; reports and effective
# Profile projections are both reproducible derived material. Existing locks
# and journals physically remain below ``tmp`` or ``receipts/cold`` for
# compatibility, but their object classification is recovery, never transient.
# No unused ``.cambium/recovery`` directory is created merely to mirror the
# conceptual category.
CATEGORY_ROOTS = {
    CANONICAL_STATE: (
        GOVERNANCE_ROOT,
        STATE_ROOT,
    ),
    BOUND_INPUT: (
        WORK_SPEC_ROOT,
        DELTA_ROOT,
    ),
    EVIDENCE: (
        RECEIPT_ROOT,
        RECEIPT_COLD_ROOT,
        RECEIPT_COLD_SEGMENT_ROOT,
        RECEIPT_COLD_EVIDENCE_ROOT,
    ),
    RECOVERY: (
        TRANSIENT_ROOT,
        RECEIPT_COLD_PENDING_ROOT,
    ),
    TRANSIENT: (
        TRANSIENT_ROOT,
    ),
    DERIVED_PROJECTION: (
        DERIVED_ROOT,
        DERIVED_INTERFACE_ROOT,
        DERIVED_HOST_CONFIG_ROOT,
        REPORT_ROOT,
    ),
}

# Object identity is stable; these are physical locations, not a new object
# protocol. Directory objects are included because writers must agree on the
# namespace before resolving a file beneath it.
RUNTIME_OBJECTS = {
    "governance-root": RuntimeObject(CANONICAL_STATE, GOVERNANCE_ROOT),
    "state-root": RuntimeObject(CANONICAL_STATE, STATE_ROOT),
    "active-standards": RuntimeObject(
        CANONICAL_STATE, GOVERNANCE_ROOT + "/standards_state.yaml"),
    "required-queue": RuntimeObject(
        CANONICAL_STATE, STATE_ROOT + "/required_queue.yaml"),
    "coverage-ledger": RuntimeObject(
        CANONICAL_STATE, STATE_ROOT + "/coverage_ledger.yaml"),
    "progress-ledger": RuntimeObject(
        CANONICAL_STATE, STATE_ROOT + "/progress_ledger.yaml"),
    "scan-watermark": RuntimeObject(
        CANONICAL_STATE, STATE_ROOT + "/watermark.yaml"),
    "work-spec-root": RuntimeObject(
        BOUND_INPUT, WORK_SPEC_ROOT),
    "delta-root": RuntimeObject(
        BOUND_INPUT, DELTA_ROOT),
    "receipt-root": RuntimeObject(
        EVIDENCE, RECEIPT_ROOT),
    "receipt-cold-root": RuntimeObject(
        EVIDENCE, RECEIPT_COLD_ROOT),
    "receipt-cold-segment-root": RuntimeObject(
        EVIDENCE, RECEIPT_COLD_SEGMENT_ROOT),
    "receipt-cold-evidence-root": RuntimeObject(
        EVIDENCE, RECEIPT_COLD_EVIDENCE_ROOT),
    "receipt-cold-manifest": RuntimeObject(
        EVIDENCE, RECEIPT_COLD_ROOT + "/manifest.jsonl"),
    "receipt-cold-index": RuntimeObject(
        EVIDENCE, RECEIPT_COLD_ROOT + "/index.jsonl"),
    "receipt-cold-pending-root": RuntimeObject(
        RECOVERY, RECEIPT_COLD_PENDING_ROOT),
    "standards-adoption-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "standards-adoptions.jsonl")),
    "contract-amendment-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "contract-amendments.jsonl")),
    "corpus-plan-acceptance-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "corpus-plan-acceptance.jsonl")),
    "gate-attestation-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "gate-attestations.jsonl")),
    "task-transition-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "task-transitions.jsonl")),
    "task-plan-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "task-plans.jsonl")),
    "batch-close-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "batch-close.jsonl")),
    "queue-structure-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "queue-structure.jsonl")),
    "amendment-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "amendments.jsonl")),
    "batch-judgment-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "batch-judgments.jsonl")),
    "gate-result-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "gate-results.jsonl")),
    "queue-transition-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "queue-transitions.jsonl")),
    "seal-receipts": RuntimeObject(
        EVIDENCE, child_path(RECEIPT_ROOT, "seal-receipts.jsonl")),
    "replan-delta-root": RuntimeObject(
        BOUND_INPUT, REPLAN_DELTA_ROOT),
    "amendment-delta-root": RuntimeObject(
        BOUND_INPUT, AMENDMENT_DELTA_ROOT),
    "contract-amendment-delta-root": RuntimeObject(
        BOUND_INPUT, CONTRACT_AMENDMENT_DELTA_ROOT),
    "standards-adoption-delta-root": RuntimeObject(
        BOUND_INPUT, STANDARDS_ADOPTION_DELTA_ROOT),
    "task-plan-delta-root": RuntimeObject(
        BOUND_INPUT, TASK_PLAN_DELTA_ROOT),
    "corpus-plan-acceptance-delta-root": RuntimeObject(
        BOUND_INPUT, CORPUS_PLAN_ACCEPTANCE_DELTA_ROOT),
    "invalidated-delta-receipt-root": RuntimeObject(
        EVIDENCE, INVALIDATED_DELTA_RECEIPT_ROOT),
    "pre-apply-coverage-receipt-root": RuntimeObject(
        EVIDENCE, PRE_APPLY_COVERAGE_RECEIPT_ROOT),
    "state-writer-lock": RuntimeObject(
        RECOVERY, TRANSIENT_ROOT + "/state-writer.lock"),
    "state-writer-owner": RuntimeObject(
        RECOVERY, TRANSIENT_ROOT + "/state-writer.lock/owner.json"),
    "page-state-recovery-journal": RuntimeObject(
        RECOVERY,
        TRANSIENT_ROOT + "/state-writer.lock/page-state-transaction.json"),
    "receipt-append-free": RuntimeObject(
        RECOVERY, TRANSIENT_ROOT + "/receipt-append.free"),
    "receipt-append-held": RuntimeObject(
        RECOVERY, TRANSIENT_ROOT + "/receipt-append.held"),
    "receipt-seal-journal": RuntimeObject(
        RECOVERY, RECEIPT_ROOT + "/cold/journal.jsonl"),
    "transient-root": RuntimeObject(
        TRANSIENT, TRANSIENT_ROOT),
    "derived-root": RuntimeObject(
        DERIVED_PROJECTION, DERIVED_ROOT),
    "derived-interface-root": RuntimeObject(
        DERIVED_PROJECTION, DERIVED_INTERFACE_ROOT),
    "derived-cli-contract": RuntimeObject(
        DERIVED_PROJECTION,
        child_path(DERIVED_INTERFACE_ROOT, "cli-contract.yaml")),
    "derived-mcp-tools": RuntimeObject(
        DERIVED_PROJECTION,
        child_path(DERIVED_INTERFACE_ROOT, "mcp-tools.json")),
    "upstream-component-byte-manifest": RuntimeObject(
        DERIVED_PROJECTION,
        child_path(DERIVED_ROOT, "upstream-component-byte-manifest.tsv")),
    "derived-host-config-root": RuntimeObject(
        DERIVED_PROJECTION, DERIVED_HOST_CONFIG_ROOT),
    "effective-vocabulary": RuntimeObject(
        DERIVED_PROJECTION, DERIVED_ROOT + "/vocab.yaml"),
    "effective-page-contract": RuntimeObject(
        DERIVED_PROJECTION, DERIVED_ROOT + "/page_contract.yaml"),
    "report-root": RuntimeObject(
        DERIVED_PROJECTION, REPORT_ROOT),
    "required-queue-report": RuntimeObject(
        DERIVED_PROJECTION, child_path(REPORT_ROOT, "required_queue.md")),
}


# Agent-facing policy refers to runtime paths by the stable object identity,
# never by copying its current physical spelling.  ``runtime-root`` is the one
# path reference that is not itself a classified runtime object: it is the
# namespace containing every object below.  The projection is computed from
# the existing object registry, so it cannot become a second path owner.
_RUNTIME_ROOT_PATH_ID = "runtime-root"
_RUNTIME_PATH_REFERENCES = {
    _RUNTIME_ROOT_PATH_ID: _PathReference(
        _RUNTIME_ROOT_PATH_ID, "namespace", RUNTIME_ROOT),
}
_RUNTIME_PATH_REFERENCES.update({
    object_id: _PathReference(
        object_id,
        "namespace" if entry.path in _CHILD_NAMESPACE_ROOTS else "exact",
        entry.path,
    )
    for object_id, entry in RUNTIME_OBJECTS.items()
})


def path_reference_for(runtime_path_id):
    """Resolve one stable policy reference to its path and constraint kind."""
    try:
        return _RUNTIME_PATH_REFERENCES[runtime_path_id]
    except (KeyError, TypeError) as exc:
        raise KeyError(
            "unknown runtime path reference: %s" % runtime_path_id) from exc


def path_for(object_id):
    """Return the registered repository-relative path for ``object_id``."""
    try:
        return RUNTIME_OBJECTS[object_id].path
    except KeyError as exc:
        raise KeyError("unknown runtime object: %s" % object_id) from exc


def category_for(object_id):
    """Return the storage/lifecycle category for ``object_id``."""
    try:
        return RUNTIME_OBJECTS[object_id].category
    except KeyError as exc:
        raise KeyError("unknown runtime object: %s" % object_id) from exc


def roots_for(category):
    """Return the registered namespace roots for one lifecycle category."""
    try:
        return CATEGORY_ROOTS[category]
    except KeyError as exc:
        raise KeyError("unknown runtime category: %s" % category) from exc


def ensure_directory(root, object_id):
    """Create one registered runtime directory without following symlinks.

    The runtime root must already exist; this helper cannot instantiate an
    adopter or select a Profile. It only materializes a registered child
    namespace for a producer that is already authorized to write there.
    """
    entry = RUNTIME_OBJECTS.get(object_id)
    if entry is None:
        raise KeyError("unknown runtime object: %s" % object_id)
    if entry.path not in {
            path for paths in CATEGORY_ROOTS.values() for path in paths}:
        raise ValueError("runtime object is not a registered directory root")
    root_path = os.path.realpath(os.path.abspath(root))
    current = root_path
    for index, part in enumerate(entry.path.split("/")):
        current = os.path.join(current, part)
        if os.path.lexists(current):
            descriptor = os.lstat(current)
            if os.path.islink(current) or not stat.S_ISDIR(descriptor.st_mode):
                raise ValueError(
                    "runtime directory must not traverse a symlink or file: "
                    "%s" % entry.path)
            continue
        if index == 0:
            raise ValueError(
                "%s must exist before creating %s" %
                (RUNTIME_ROOT, entry.path))
        os.mkdir(current)
    return current


_paths = [entry.path for entry in RUNTIME_OBJECTS.values()]
if len(_paths) != len(set(_paths)):
    raise RuntimeError("runtime object registry contains duplicate paths")
if set(entry.category for entry in RUNTIME_OBJECTS.values()) != \
        set(CATEGORY_ROOTS):
    raise RuntimeError("runtime object registry/category roots are incomplete")


ACTIVE_STANDARDS_PATH = path_for("active-standards")
QUEUE_PATH = path_for("required-queue")
COVERAGE_PATH = path_for("coverage-ledger")
PROGRESS_PATH = path_for("progress-ledger")
WATERMARK_PATH = path_for("scan-watermark")

STATE_WRITER_LOCK_PATH = path_for("state-writer-lock")
STATE_WRITER_OWNER_PATH = path_for("state-writer-owner")
PAGE_STATE_RECOVERY_JOURNAL_PATH = path_for(
    "page-state-recovery-journal")
RECEIPT_APPEND_FREE_PATH = path_for("receipt-append-free")
RECEIPT_APPEND_HELD_PATH = path_for("receipt-append-held")
RECEIPT_SEAL_JOURNAL_PATH = path_for("receipt-seal-journal")
RECEIPT_COLD_MANIFEST_PATH = path_for("receipt-cold-manifest")
RECEIPT_COLD_INDEX_PATH = path_for("receipt-cold-index")
VOCAB_ARTIFACT_PATH = path_for("effective-vocabulary")
PAGE_CONTRACT_ARTIFACT_PATH = path_for("effective-page-contract")
CLI_CONTRACT_ARTIFACT_PATH = path_for("derived-cli-contract")
MCP_TOOLS_ARTIFACT_PATH = path_for("derived-mcp-tools")
HOST_CONFIG_ARTIFACT_ROOT = path_for("derived-host-config-root")
UPSTREAM_COMPONENT_MANIFEST_PATH = path_for(
    "upstream-component-byte-manifest")

STANDARDS_ADOPTION_RECEIPT_PATH = path_for("standards-adoption-receipts")
CONTRACT_AMENDMENT_RECEIPT_PATH = path_for("contract-amendment-receipts")
CORPUS_PLAN_ACCEPTANCE_RECEIPT_PATH = path_for(
    "corpus-plan-acceptance-receipts")
GATE_ATTESTATION_RECEIPT_PATH = path_for("gate-attestation-receipts")
TASK_TRANSITION_RECEIPT_PATH = path_for("task-transition-receipts")
TASK_PLAN_RECEIPT_PATH = path_for("task-plan-receipts")
BATCH_CLOSE_RECEIPT_PATH = path_for("batch-close-receipts")
QUEUE_STRUCTURE_RECEIPT_PATH = path_for("queue-structure-receipts")
AMENDMENT_RECEIPT_PATH = path_for("amendment-receipts")
BATCH_JUDGMENT_RECEIPT_PATH = path_for("batch-judgment-receipts")
GATE_RESULT_RECEIPT_PATH = path_for("gate-result-receipts")
QUEUE_TRANSITION_RECEIPT_PATH = path_for("queue-transition-receipts")
SEAL_RECEIPT_PATH = path_for("seal-receipts")
REQUIRED_QUEUE_REPORT_PATH = path_for("required-queue-report")

# Directories a task-runtime initializer materializes beside pre-existing
# governance state. ``governance`` itself is created by Profile adoption.
TASK_RUNTIME_ROOTS = (
    STATE_ROOT,
    WORK_SPEC_ROOT,
    DELTA_ROOT,
    RECEIPT_ROOT,
    REPORT_ROOT,
    TRANSIENT_ROOT,
)
TASK_RUNTIME_DIRECTORIES = tuple(
    path[len(RUNTIME_ROOT) + 1:] for path in TASK_RUNTIME_ROOTS)
