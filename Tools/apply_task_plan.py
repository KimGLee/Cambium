#!/usr/bin/env python3
"""Materialize a task's runtime from one operator-confirmed plan.

`init_state.py` creates the namespace and stops: the Task Contract's five
loaded-set fields are empty, Coverage holds no pages, and the Queue is empty
because nothing is inferred. Until this tool existed no writer owned the edge
that fills them, so the only way forward was to hand-edit canonical runtime
state -- which R01 forbids, and which leaves no evidence of what was confirmed.

This is that writer. It consumes one closed restricted-YAML plan, verifies the
runtime is still the empty skeleton the plan was prepared against, and writes
the Contract and the Coverage inventory as one transaction.

It deliberately does not write the Queue. `check_queue._coverage_provenance_
errors` states that before the first Queue materialization both Coverage and
the Contract are adopter inputs; after it, every canonical write must be the
after-image of a receipt from a closed set of writers. Writing the Queue here
would cross that line and require adding an entry to that set. Materializing
the Queue is already owned by `compile_queue --apply`, which is in the set and
which syncs the Progress revision, fingerprint, and initial Queue receipt this
transaction has no business touching.

So the split follows the machine's own boundary: this tool fills the adopter
inputs, `compile_queue --apply` materializes from them. The state in between is
not an inconsistent window -- it is exactly the pre-materialization state the
runtime model already blesses, and a crash there is resumed by running the
compiler.

What it will not do: infer. The plan supplies which objects are Required, who
owns them, their priority, dependencies, and batch assignment. Exactly two
derivations are allowed, both deterministic and both owned elsewhere -- the
Queue from the confirmed Coverage, and the Card/Read Set closure from the
confirmed route IDs. Everything else is an answer the operator gave.

It also refuses to run twice with different bytes. A plan interrupted mid-write
may be re-applied from the same path and SHA to finish; a *different* plan
applied over a materialized runtime would be a scope change routed around the
Amendment machinery, and is rejected. Later change belongs to replan,
Amendment, or a successor task.

Exit codes: 0 = dry run reported or transaction committed; 1 = refused.
"""

import contextlib
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_proof
import check_queue
import compile_queue
import kblib
import amendment_policy
import metadata_execution_contract
import metadata_property_state
import project_page_state

TOOL = "apply_task_plan"
TOOL_VERSION = "1.2.0"
CHECK = "task_plan"
PLAN_PREFIX = ".cambium/deltas/task-plans"
RECEIPT_PATH = ".cambium/receipts/task-plans.jsonl"
SENTINEL = "TODO(plan)"
LEGACY_PROPERTY_ADOPTION_OPERATION = "legacy-property-adoption-v1"

PLAN_FIELDS = {
    "schema_version", "plan_id", "task_id", "approval_reference",
    "before", "contract_after", "coverage_after",
}
BEFORE_FIELDS = {"coverage_sha256", "queue_sha256", "progress_sha256"}
COVERAGE_AFTER_FIELDS = {"pages", "batch_specs"}

# Owned by K13/02; this tool supplies values for exactly this closed set and
# never adds a field.  Kept in step with check_queue's own contract field set.
CONTRACT_FIELDS = set(check_queue.CONTRACT_FIELDS).union((
    "amendment_authority",
))
CONTRACT_OPTIONAL_FIELDS = set(check_queue.CONTRACT_OPTIONAL_FIELDS).union((
    "amendment_authority",
))

STATE_NAMES = ("coverage", "queue", "progress")
# Only these are written; the Queue is read for its before-image and left
# to its own writer.
WRITTEN_NAMES = ("coverage", "progress")


# ---------------------------------------------------------------------------
# `--json` output (machine-readable receipts)
#
# Purely additive: without the flag not one byte of this tool's behaviour
# moves.  With it, everything written for a person goes to stderr and stdout
# carries this run's receipt objects, serialized verbatim as one canonical
# JSON array.
#
# Nothing is filtered or renamed.  `schemas/receipt.template.jsonl` guarantees
# only the base fields every receipt carries; extension fields differ per
# producer and are discoverable from the receipt itself, which is why that
# template says in its own text that its examples are "not the complete set".
# A field allowlist here would silently drop exactly the fields a caller came
# for.
#
# This tool's receipts are written from inside its transaction helpers, well
# below `main`, so the run collects them where they are handed to the receipt
# writer rather than threading an accumulator through every frame.
# ---------------------------------------------------------------------------
JSON_HELP = ("write this run's receipt objects to stdout as one canonical "
             "JSON array and move the human-readable report to stderr; "
             "receipt writing, verdicts, and exit codes are unchanged")

_JSON_RECEIPTS = []


def _record_receipts(receipts):
    """Remember the exact receipt objects handed to the receipt writer."""
    _JSON_RECEIPTS.extend(receipts)
    return receipts


def emit_json_receipts(receipts):
    """Write the exact receipt objects this run produced to real stdout.

    The one canonical serializer is `kblib.canonical_json_bytes`; this module
    owns no serializer of its own.  A run that produced no receipt writes
    nothing, which keeps the already-settled rejection shape (empty stdout,
    one line of reason on stderr, exit 1) intact.
    """
    if not receipts:
        return
    sys.stdout.write(
        kblib.canonical_json_bytes(list(receipts)).decode("utf-8") + "\n")


def _run_reporting_json(runner):
    """Run `runner`, reserving stdout for JSON and giving stderr the prose."""
    with contextlib.redirect_stdout(sys.stderr):
        exit_code = runner()
    emit_json_receipts(_JSON_RECEIPTS)
    return exit_code


class Refusal(Exception):
    """A condition that stops the transaction before any byte is written."""


def _load_plan(root, relative):
    path = kblib.managed_repository_path(
        root, relative, PLAN_PREFIX, suffixes=(".yaml",), must_exist=True)
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        plan = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise Refusal("task plan is not UTF-8: %s" % exc)
    except kblib.YamlSubsetError as exc:
        raise Refusal("task plan is not the restricted YAML subset: %s" % exc)
    if not isinstance(plan, dict):
        raise Refusal("task plan top level must be a mapping")
    return path, raw, plan


def _closed(mapping, allowed, label, optional=frozenset()):
    if not isinstance(mapping, dict):
        raise Refusal("%s must be a mapping" % label)
    unknown = sorted(set(mapping) - set(allowed))
    missing = sorted(set(allowed) - set(optional) - set(mapping))
    if unknown:
        raise Refusal("%s has unsupported field(s): %s"
                      % (label, ", ".join(unknown)))
    if missing:
        raise Refusal("%s is missing field(s): %s" % (label, ", ".join(missing)))


def _validate_plan_shape(plan):
    # First, because it is the one refusal whose cause is "nothing has been
    # filled in yet".  Reporting a malformed SHA to an operator who copied the
    # template and has not touched it names a symptom instead of the cause.
    if SENTINEL in kblib.canonical_yaml(plan):
        raise Refusal(
            "task plan still carries the template's %s sentinel; every one of "
            "them is an answer this transaction will not invent" % SENTINEL)
    _closed(plan, PLAN_FIELDS, "task plan")
    if plan["schema_version"] != 1:
        raise Refusal("task plan schema_version must be 1")
    for field in ("plan_id", "task_id", "approval_reference"):
        value = plan[field]
        if not isinstance(value, str) or not value.strip():
            raise Refusal("task plan %s must be a nonempty string" % field)
    _closed(plan["before"], BEFORE_FIELDS, "task plan before")
    for field, value in sorted(plan["before"].items()):
        if not (isinstance(value, str) and check_queue.SHA256_RE.fullmatch(value)):
            raise Refusal(
                "task plan before.%s must be spelled sha256:<64 hex digits>; "
                "`check_queue.py . --resume-status` reports the three current "
                "values" % field)
    _closed(plan["contract_after"], CONTRACT_FIELDS,
            "task plan contract_after",
            optional=CONTRACT_OPTIONAL_FIELDS)
    authority = plan["contract_after"].get("amendment_authority")
    if authority is not None:
        authority_errors = amendment_policy.amendment_authority_errors(
            authority, "task plan contract_after.amendment_authority")
        if authority_errors:
            raise Refusal(
                "task plan amendment authority is not the K13/02 shape:\n  %s"
                % "\n  ".join(authority_errors[:8]))
    _closed(plan["coverage_after"], COVERAGE_AFTER_FIELDS,
            "task plan coverage_after")
    for field in sorted(COVERAGE_AFTER_FIELDS):
        if not isinstance(plan["coverage_after"][field], list):
            raise Refusal("task plan coverage_after.%s must be a list" % field)
    if not plan["coverage_after"]["pages"]:
        raise Refusal(
            "task plan coverage_after.pages is empty; a plan that materializes "
            "no Required object leaves the runtime exactly as init_state left "
            "it and has nothing to confirm")
    for index, page in enumerate(plan["coverage_after"]["pages"]):
        label = "task plan coverage_after.pages[%d]" % index
        if not isinstance(page, dict):
            raise Refusal("%s must be a mapping" % label)
        if "property_state" not in page or not isinstance(
                page.get("property_state"), dict):
            raise Refusal(
                "%s must carry an explicit property_state mapping; an empty "
                "mapping is the current no-owner state" % label)
        if page.get("property_state"):
            raise Refusal(
                "%s is a new runtime page and may not claim pre-existing "
                "current property evidence" % label)
        if "legacy_property_state" in page:
            raise Refusal(
                "%s is a new runtime page and may not claim legacy property "
                "observations" % label)


def _state_paths(root):
    return {
        "coverage": kblib.managed_repository_path(
            root, check_queue.COVERAGE_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True),
        "queue": kblib.managed_repository_path(
            root, check_queue.QUEUE_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True),
        "progress": kblib.managed_repository_path(
            root, check_queue.PROGRESS_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True),
    }


def _read_state(paths):
    raw = {}
    documents = {}
    for name, path in paths.items():
        with open(path, "rb") as handle:
            raw[name] = handle.read()
        documents[name] = kblib.parse_yaml_subset(raw[name].decode("utf-8"))
    return raw, documents


def _require_before_match(plan, raw):
    for name in STATE_NAMES:
        expected = plan["before"]["%s_sha256" % name]
        actual = kblib.sha256_bytes(raw[name])
        if expected != actual:
            raise Refusal(
                "%s is %s but the plan was prepared against %s; the runtime "
                "moved after this plan was confirmed, so re-prepare it rather "
                "than merging" % (name, actual, expected))


def _require_empty_skeleton(documents, plan):
    coverage, queue, progress = (documents["coverage"], documents["queue"],
                                 documents["progress"])
    if coverage.get("pages"):
        raise Refusal(
            "Coverage already holds page records; this transaction "
            "materializes an empty skeleton once. A later change is a replan, "
            "an Amendment, or a successor task")
    if queue.get("required_queue"):
        raise Refusal(
            "the Required Queue is already materialized; applying a different "
            "plan over it would route a scope change around the Amendment "
            "machinery")
    if progress.get("task_state") != "planned":
        raise Refusal(
            "task_state is %r; initial planning applies only to a task that "
            "has not started" % progress.get("task_state"))
    for name in STATE_NAMES:
        recorded = documents[name].get("task_id")
        if recorded != plan["task_id"]:
            raise Refusal(
                "%s records task_id %r but the plan names %r"
                % (name, recorded, plan["task_id"]))


def _derive_property_state_adoption(root, pages, profile_view):
    """Derive honest legacy observations from immutable page snapshots.

    The operator confirms inventory and scope, not evidence it cannot prove.
    Existing machine fields are therefore observed by the writer itself under
    the same Core + typed-Profile rule set later used by ``check_queue``.  The
    result records either an exact page SHA and explicit unverified values, or
    an absent page and an empty owner state.  Nothing here manufactures a
    review/content date or receipt.
    """
    try:
        metadata_contract, rules = \
            metadata_property_state.authorized_profile_projection_rules(
                root, profile_view)
        if not metadata_execution_contract.compiled_capability_supports(
                metadata_contract, LEGACY_PROPERTY_ADOPTION_OPERATION,
                LEGACY_PROPERTY_ADOPTION_OPERATION, kind="writer"):
            raise ValueError(
                "compiled metadata contract does not authorize the %s "
                "writer operation" % LEGACY_PROPERTY_ADOPTION_OPERATION)
    except (OSError, TypeError, UnicodeError, ValueError,
            metadata_execution_contract.MetadataExecutionContractError) as exc:
        raise Refusal(
            "cannot compose the metadata rules used for initial property "
            "adoption: %s" % exc)
    indexed = {}
    for index, row in enumerate(pages):
        path = row.get("path") if isinstance(row, dict) else None
        if (not isinstance(path, str) or not path.strip() or
                path in indexed):
            raise Refusal(
                "coverage_after.pages[%d] has no unique page path" % index)
        indexed[path] = row
    try:
        adoption = metadata_property_state.build_legacy_property_removal_plan(
            root, sorted(indexed), rules=rules)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        raise Refusal(
            "cannot freeze initial property source pages: %s" % exc)
    for record in adoption["records"]:
        legacy = record["legacy_property_state"]
        if legacy:
            indexed[record["path"]][
                check_queue.LEGACY_PROPERTY_STATE_FIELD] = \
                copy.deepcopy(legacy)
    adoption["metadata_execution_contract_fingerprint"] = \
        metadata_contract.contract_fingerprint
    adoption["metadata_execution_rule_fingerprint"] = \
        adoption["plan"].contract_rule_fingerprint
    adoption["operation_capability"] = \
        LEGACY_PROPERTY_ADOPTION_OPERATION
    return adoption


def _require_property_sources_current(root, adoption):
    """CAS every page/absence from which the migration was derived."""
    for record in adoption["records"]:
        path = record["path"]
        snapshot = kblib.repository_target_snapshot(
            root, path, suffixes=(".md", ".MD"), singly_linked=True)
        current = snapshot.sha256 if snapshot.exists else None
        if current != record["before_page_sha256"]:
            raise Refusal(
                "initial property source page %s changed between planning "
                "and commit" % path)
    current_metadata = \
        metadata_execution_contract.load_metadata_execution_contract(root)
    if current_metadata.contract_fingerprint != adoption[
            "metadata_execution_contract_fingerprint"]:
        raise Refusal(
            "metadata execution contract changed between initial property "
            "adoption planning and commit")


def _build_after(root, documents, plan, profile_view):
    coverage = copy.deepcopy(documents["coverage"])
    progress = copy.deepcopy(documents["progress"])
    coverage["pages"] = copy.deepcopy(plan["coverage_after"]["pages"])
    coverage["batch_specs"] = copy.deepcopy(plan["coverage_after"]["batch_specs"])
    adoption = _derive_property_state_adoption(
        root, coverage["pages"], profile_view)
    contract = copy.deepcopy(progress.get("contract") or {})
    contract.update(copy.deepcopy(plan["contract_after"]))
    derived = _derive_load_sets(root, contract)
    progress["contract"] = contract

    # Compiled here only to prove the plan yields a Queue at all; the document
    # is reported and discarded.  Materializing it is compile_queue's edge.
    # Its structural rules -- every Required object carries an explicit batch,
    # dependencies resolve, orders are contiguous -- are the compiler's to
    # state, so they are surfaced verbatim rather than restated here.
    try:
        queue, _changed = compile_queue.compile_document(
            copy.deepcopy(documents["queue"]), coverage)
    except (ValueError, TypeError) as exc:
        raise Refusal(
            "the Queue compiler rejects this plan's Coverage, so no runtime "
            "could be materialized from it: %s" % exc)
    return coverage, queue, progress, derived, adoption


def _validate_proposed(root, coverage, progress, documents,
                       property_adoption):
    """Validate the state this transaction writes, with the Queue untouched.

    A Coverage inventory whose batches have no Queue items is not a broken
    runtime; it is the unmaterialized one, and `validate_runtime` already has
    a name for it. `allow_unmaterialized_queue` suppresses exactly two
    findings -- a batch spec with no Queue item, and a page assigned to a
    batch the Queue does not carry -- and only while the Queue is genuinely
    empty. `compile_queue.main` sets the same flag when it reads this state to
    compile from it, so this validation asks the state the same question its
    next reader will.
    """
    texts = {
        "coverage": kblib.canonical_yaml(coverage),
        "progress": kblib.canonical_yaml(progress),
    }
    errors = check_queue.validate_runtime(
        root,
        state_overrides={
            check_queue.COVERAGE_PATH: (texts["coverage"], coverage),
            check_queue.PROGRESS_PATH: (texts["progress"], progress),
        },
        page_projection_overrides=property_adoption["after_text_by_path"],
        allow_unmaterialized_queue=True,
    )["errors"]
    return texts, errors


def _strings(values):
    return set(value for value in (values or [])
               if isinstance(value, str) and value)


def _derive_load_sets(root, contract):
    """Complete the three derived load fields from the confirmed route IDs.

    This is one of the two derivations a plan may carry, and the one that makes
    the plan writable at all. A kernel route's Card and Read Set are registered
    facts, and a Read Set's transitive closure is a pure function of repository
    bytes: R01 alone reaches every other route and well over a hundred modules.
    Requiring an operator to type that by hand would produce a declaration
    nobody checked, and `check_proof` enforces the same agreement at Terminal
    against the same two indexes -- by which point the Contract is frozen and
    the task that wrote it can no longer repair it.

    So routes are the answer and the closure is the resolution. What the plan
    lists is never dropped, only completed: a profile supplemental Read Set has
    no machine-readable registry (`profiles/README.md` says so outright), so it
    stays something the plan names and this function closes over.
    """
    card_map, read_map, registry_errors = check_proof.load_route_registry(root)
    if registry_errors:
        raise Refusal(
            "the Card/Read Set registry is not sound, so a route selection "
            "cannot be resolved against it: %s" % registry_errors[0])

    # R01 is the mandatory entry route, not an operator choice.  Resolving it
    # here prevents a newly planned task from reaching its first activation
    # with a frozen contract that no valid Card Bundle can satisfy.
    routes = sorted(_strings(contract.get("selected_route_ids")) | {"R01"})
    contract["selected_route_ids"] = routes
    unknown = [route for route in routes if route not in read_map]
    if unknown:
        raise Refusal("selected_route_ids names unregistered route(s): %s"
                      % ", ".join(unknown))

    cards = _strings(contract.get("selected_card_paths"))
    registered_cards = {entry["path"] for entry in card_map.values()}
    foreign = sorted(card for card in cards
                     if card in registered_cards and card not in
                     {card_map[route]["path"] for route in routes})
    if foreign:
        raise Refusal(
            "selected_card_paths declares %s, whose route is not in "
            "selected_route_ids" % ", ".join(foreign))

    seeds = _strings(contract.get("selected_read_sets")) | {
        read_map[route]["path"] for route in routes}
    read_sets, modules, invalid, closure_errors = \
        check_queue._read_set_load_closure(
            root, seeds, contract.get("selected_profile_manifest"),
            contract.get("selected_profile_route_ids"))
    if closure_errors or invalid:
        raise Refusal(
            "the selected routes' Read Set closure does not resolve:\n  %s"
            % "\n  ".join(closure_errors or sorted(invalid)))

    contract["selected_card_paths"] = sorted(
        cards | {card_map[route]["path"] for route in routes})
    contract["selected_read_sets"] = sorted(read_sets)
    contract["loaded_module_paths"] = sorted(
        _strings(contract.get("loaded_module_paths")) | modules)
    return {"routes": len(routes),
            "read_sets": len(contract["selected_read_sets"]),
            "modules": len(contract["loaded_module_paths"])}


def _receipt(plan, phase, result, details, seq):
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK, plan["plan_id"], result, details, seq,
        identity={
            "task_id": plan["task_id"],
            "standards_version": plan["contract_after"]["standards_version"],
            "selected_profile_manifest":
                plan["contract_after"]["selected_profile_manifest"],
        })
    # No gate_id: this proves a transaction happened, not that a lifecycle
    # boundary may be crossed.  The state it writes is consumed by the Queue
    # consistency, admission, and corpus-plan gates that already exist.
    receipt["transaction_phase"] = phase
    return receipt


def prepare(root, plan_relative):
    """Everything that can refuse, before any byte is written."""
    plan_path, plan_raw, plan = _load_plan(root, plan_relative)
    _validate_plan_shape(plan)
    paths = _state_paths(root)
    raw, documents = _read_state(paths)
    _require_before_match(plan, raw)
    _require_empty_skeleton(documents, plan)

    current = check_queue.validate_runtime(root)
    if current["errors"]:
        raise Refusal(
            "the current runtime does not validate; repair it before "
            "materializing a plan over it:\n  %s"
            % "\n  ".join(current["errors"][:5]))

    authority = check_queue.runtime_authority_context(current)
    coverage, queue, progress, derived, property_adoption = _build_after(
        root, documents, plan, authority["profile_view"])

    # The derivation must satisfy the checker that judges the same declaration,
    # rather than being trusted because this module wrote it.  K00/15 places
    # that judgment on a plan being admitted, which is exactly here: the live
    # path reports these as gaps rather than errors only so an already-sealed
    # contract stays repairable.
    _errors, gaps = check_queue._live_read_set_load_findings(
        root, progress["contract"])
    if gaps:
        raise Refusal(
            "the derived load declaration does not satisfy the checker that "
            "judges it:\n  %s" % "\n  ".join(gaps[:10]))

    texts, errors = _validate_proposed(
        root, coverage, progress, documents, property_adoption)
    if errors:
        raise Refusal(
            "the runtime this plan proposes does not validate:\n  %s"
            % "\n  ".join(errors[:10]))

    return {
        "root": root,
        "plan": plan,
        "plan_path": os.path.relpath(plan_path, root).replace(os.sep, "/"),
        "plan_sha": kblib.sha256_bytes(plan_raw),
        "paths": paths,
        "before_raw": raw,
        "before_sha": {name: kblib.sha256_bytes(raw[name])
                       for name in STATE_NAMES},
        "after_text": texts,
        "after_sha": {name: kblib.sha256_bytes(texts[name].encode("utf-8"))
                      for name in WRITTEN_NAMES},
        "queue": queue,
        "queue_revision": documents["queue"].get("queue_revision"),
        "derived": derived,
        "property_adoption": property_adoption,
        "authority": authority,
    }


def _lock_operation(prepared, commit, abort):
    plan = prepared["plan"]
    operation = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "action": "initial-task-planning",
        "target": plan["plan_id"],
        "task_id": plan["task_id"],
        "plan_path": prepared["plan_path"],
        "plan_sha256": prepared["plan_sha"],
        "commit_receipt_id": commit["receipt_id"],
        "abort_receipt_id": abort["receipt_id"],
        # The generic writer recovery protocol (`check_queue`
        # `_bind_generic_lock_receipts`) reads these three to decide whether
        # the declared receipt actually landed after an interruption.
        "receipt_id": commit["receipt_id"],
        "receipt_path": RECEIPT_PATH,
        "transaction_phase": "commit",
        "property_state_adoption_set_sha256":
            prepared["property_adoption"]["set_sha256"],
        "metadata_execution_contract_fingerprint":
            prepared["property_adoption"][
                "metadata_execution_contract_fingerprint"],
        "metadata_execution_rule_fingerprint":
            prepared["property_adoption"][
                "metadata_execution_rule_fingerprint"],
        "operation_capability": prepared["property_adoption"][
            "operation_capability"],
    }
    operation.update(check_queue.runtime_authority_lock_fields(
        prepared["authority"]))
    for name in STATE_NAMES:
        operation["before_%s_sha256" % name] = prepared["before_sha"][name]
    for name in WRITTEN_NAMES:
        operation["planned_after_%s_sha256" % name] = prepared["after_sha"][name]
    # The recovery semantic cross-check reads the longer Required Queue
    # spelling from writer-lock metadata; both names identify the same file.
    operation["before_required_queue_sha256"] = prepared["before_sha"]["queue"]
    return operation


def commit(prepared, receipt_path):
    """Write all three documents under one lease, restoring on any failure."""
    plan = prepared["plan"]
    root = prepared["root"]
    commit_receipt = _receipt(
        plan, "commit", "pass",
        "wrote the Task Contract and %d Coverage record(s) from plan %s; the "
        "Queue it compiles to has %d item(s) and is materialized by "
        "compile_queue"
        % (len(plan["coverage_after"]["pages"]), prepared["plan_path"],
           len(prepared["queue"].get("required_queue") or [])), 1)
    # The state edge, on the receipt itself, so the generic writer recovery
    # protocol can compare declared intent against the landed receipt.
    commit_receipt.update({
        "before_coverage_sha256": prepared["before_sha"]["coverage"],
        "before_required_queue_sha256": prepared["before_sha"]["queue"],
        "before_progress_sha256": prepared["before_sha"]["progress"],
        "after_coverage_sha256": prepared["after_sha"]["coverage"],
        "after_progress_sha256": prepared["after_sha"]["progress"],
        "property_state_adoption_records": copy.deepcopy(
            prepared["property_adoption"]["records"]),
        "property_state_adoption_count":
            prepared["property_adoption"]["count"],
        "property_state_adoption_set_sha256":
            prepared["property_adoption"]["set_sha256"],
        "metadata_execution_contract_fingerprint":
            prepared["property_adoption"][
                "metadata_execution_contract_fingerprint"],
        "metadata_execution_rule_fingerprint":
            prepared["property_adoption"][
                "metadata_execution_rule_fingerprint"],
        "operation_capability": prepared["property_adoption"][
            "operation_capability"],
    })
    profile_view = prepared["authority"]["profile_view"]
    for field in (
            "selected_profile_manifest", "profile_snapshot_sha256",
            "profile_contract_fingerprint", "profile_load_inputs_sha256"):
        commit_receipt[field] = profile_view.get(field)
    abort_receipt = _receipt(
        plan, "abort", "fail",
        "initial task planning aborted and the empty skeleton restored", 2)
    operation = _lock_operation(prepared, commit_receipt, abort_receipt)

    with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
        with kblib.no_authoritative_write_guard(lease):
            for name in STATE_NAMES:
                with open(prepared["paths"][name], "rb") as handle:
                    live = handle.read()
                if kblib.sha256_bytes(live) != prepared["before_sha"][name]:
                    raise Refusal(
                        "%s changed between planning and commit" % name)
            check_queue.require_runtime_authority_current(
                root, prepared["authority"],
                "runtime authority changed before initial property adoption")
            _require_property_sources_current(
                root, prepared["property_adoption"])
        written = []
        page_transaction = None
        try:
            page_plan = prepared["property_adoption"]["plan"]
            if any(page.changed for page in page_plan.pages):
                page_transaction = project_page_state.stage_projection_plan(
                    root, page_plan, lease,
                    transaction_id="task-plan-property-%s" %
                    commit_receipt["receipt_id"])
            for name in WRITTEN_NAMES:
                kblib.atomic_write_text(
                    prepared["paths"][name], prepared["after_text"][name])
                written.append(name)
            check_queue.require_runtime_authority_current(
                root, prepared["authority"],
                "runtime authority changed during initial property adoption")
            _require_property_sources_current(
                root, prepared["property_adoption"])
            if page_transaction is not None:
                page_transaction.publish()
            post = check_queue.validate_runtime(
                root, extra_receipts=[commit_receipt],
                allow_unmaterialized_queue=True,
                **check_queue.runtime_authority_validation_kwargs(
                    prepared["authority"]))
            if post["errors"]:
                raise Refusal(
                    "initial property adoption after-image does not validate: "
                    "%s" % "; ".join(post["errors"][:10]))
            before = kblib.receipt_append_observation(
                receipt_path, [commit_receipt])
            outcome, error, _ = kblib.write_receipts_observed(
                receipt_path, _record_receipts([commit_receipt]),
                before=before)
            if error is not None:
                raise error
            if outcome != "present":
                raise Refusal(
                    "commit receipt append reported %r; the transaction is "
                    "uncertain and the lease is preserved for reconciliation"
                    % outcome)
            persisted = check_queue.validate_runtime(
                root, allow_unmaterialized_queue=True,
                **check_queue.runtime_authority_validation_kwargs(
                    prepared["authority"]))
            if persisted["errors"]:
                raise Refusal(
                    "persisted initial property adoption does not validate: "
                    "%s" % "; ".join(persisted["errors"][:10]))
            if page_transaction is not None:
                page_transaction.commit()
        except Exception as original:
            if (page_transaction is not None and
                    page_transaction.state == "commit-cleanup-failed"):
                raise ValueError(
                    "initial property adoption committed but page recovery "
                    "cleanup is incomplete; inspect the retained writer "
                    "journal: %s" % original) from original
            rollback_failures = []
            if (page_transaction is not None and
                    page_transaction.state not in
                    ("rolled-back", "committed")):
                try:
                    page_transaction.rollback()
                except Exception as exc:
                    rollback_failures.append("page projection: %s" % exc)
            for name in reversed(written):
                try:
                    kblib.atomic_write_text(
                        prepared["paths"][name],
                        prepared["before_raw"][name].decode("utf-8"))
                except Exception as exc:
                    rollback_failures.append("%s: %s" % (name, exc))
            if rollback_failures:
                raise ValueError(
                    "initial property adoption failed and rollback is "
                    "incomplete: %s; %s" %
                    (original, "; ".join(rollback_failures))) from original
            abort_before = kblib.receipt_append_observation(
                receipt_path, [abort_receipt])
            abort_outcome, abort_error, _ = kblib.write_receipts_observed(
                receipt_path, _record_receipts([abort_receipt]),
                before=abort_before)
            if abort_error is not None or abort_outcome != "present":
                raise ValueError(
                    "initial property adoption rolled back but abort evidence "
                    "is incomplete: outcome=%s error=%s" %
                    (abort_outcome, abort_error)) from original
            lease.mark_reconciled()
            raise
    return commit_receipt


def _compile_command(prepared):
    """The exact next command, with the Queue's untouched CAS values filled in.

    `compile_queue --apply` requires the Queue revision and fingerprint it is
    replacing.  This transaction does not move either, so it already holds both
    exactly; printing the literal command spares the operator from deriving a
    compare-and-swap value by hand, which is the step most likely to be skipped.
    """
    return ("python3 Tools/compile_queue.py . --apply --actor-role integrator "
            "--expected-queue-revision %s --expected-sha256 %s"
            % (prepared["queue_revision"], prepared["before_sha"]["queue"]))


def _report(prepared):
    plan = prepared["plan"]
    items = prepared["queue"].get("required_queue") or []
    print("apply_task_plan: plan %s task %s"
          % (plan["plan_id"], plan["task_id"]))
    print("  confirmed by: %s" % plan["approval_reference"])
    print("  Coverage records: %d" % len(plan["coverage_after"]["pages"]))
    print("  batch specs: %d" % len(plan["coverage_after"]["batch_specs"]))
    print("  Queue items it compiles to: %d" % len(items))
    print("  resolved from %d selected route(s): %d Read Set(s), %d module(s)"
          % (prepared["derived"]["routes"], prepared["derived"]["read_sets"],
             prepared["derived"]["modules"]))
    for name in WRITTEN_NAMES:
        print("  %s: %s -> %s"
              % (name, prepared["before_sha"][name][:12],
                 prepared["after_sha"][name][:12]))
    print("  queue: unchanged; materialized by its own writer")
    print("  next: %s" % _compile_command(prepared))


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Materialize a task runtime from one confirmed plan.")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--plan", required=True,
                        help="repository-relative path under %s" % PLAN_PREFIX)
    parser.add_argument("--receipts", default=RECEIPT_PATH,
                        help="receipt JSONL path under .cambium/receipts")
    parser.add_argument("--apply", action="store_true",
                        help="write the transaction; omit for a dry run")
    parser.add_argument("--json", action="store_true", help=JSON_HELP)
    args = parser.parse_args(argv)
    if not args.json:
        return _run(args)
    return _run_reporting_json(lambda: _run(args))


def _run(args):
    """This tool's own run; `main` above owns only argument parsing."""
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False)
        prepared = prepare(root, args.plan)
    except (Refusal, OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc)
        return 1

    _report(prepared)
    if not args.apply:
        print("apply_task_plan: dry run; re-run with --apply to commit")
        return 0

    try:
        receipt = commit(prepared, receipt_path)
    except (Refusal, OSError, ValueError, TypeError) as exc:
        print("[FAIL] %s" % exc)
        return 1
    print("apply_task_plan: committed as %s" % receipt["receipt_id"])
    print("apply_task_plan: the Queue is unmaterialized until you run")
    print("  %s" % _compile_command(prepared))
    return 0


if __name__ == "__main__":
    sys.exit(main())
