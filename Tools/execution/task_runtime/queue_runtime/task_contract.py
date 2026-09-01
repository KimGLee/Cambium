"""The immutable Task Contract, its anchor chain, and the Read Set it selects.

The canonical fingerprint, the hash-linked chain of anchors across adoptions
and Amendments, and the closure of Read Set loads the contract currently
selects.  These are one subject: the fingerprint is only meaningful against
the revision the chain places it at.
"""

import os

import Tools.platform.common.kblib as kblib
import Tools.execution.context_delivery.read_set_contract as read_set_contract
from Tools.execution.evidence import receipt_reference_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths

from Tools.execution.task_runtime.queue_runtime.canon import SHA256_RE
from Tools.execution.task_runtime.queue_runtime.primitives import nonempty_string


READ_SET_BOUNDARY_OWNER_PATH = read_set_contract.SCHEMA_PATH


def initial_task_plan_receipt_errors(root, progress, catalog, queue,
                                     queue_sha, coverage_sha, progress_sha):
    """Validate the unique transaction that created the planned runtime.

    Progress owns only the Receipt reference.  The typed reference graph owns
    its body-required resolution, while this Task Contract module validates
    the plan and state binding.  Once Queue materialization has anchored the
    Contract independently, the initial after-image remains history; before
    that boundary all three live Ledger bytes must equal the transaction's
    declared after-image.
    """
    errors = []
    receipt_id = progress.get("initial_task_plan_receipt")
    if not nonempty_string(receipt_id):
        return ["Progress initial_task_plan_receipt must identify a receipt"]
    try:
        resolved = catalog.resolve_reference(
            receipt_id, "progress.initial-task-plan")
    except (AttributeError, receipt_reference_contract.ReceiptReferenceError) \
            as exc:
        return ["Progress initial Task Plan Receipt cannot be resolved: %s" %
                exc]
    receipt = resolved.body if resolved is not None else None
    if not isinstance(receipt, dict):
        return ["Progress initial Task Plan Receipt %s requires its complete "
                "body" % receipt_id]
    expected = {
        "tool": "apply_task_plan",
        "check": "task_plan",
        "result": "pass",
        "invalidated_by": None,
        "transaction_phase": "commit",
        "task_id": progress.get("task_id"),
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            errors.append(
                "initial Task Plan Receipt %s has %s=%r, expected %r" %
                (receipt_id, field, receipt.get(field), value))
    for field in ("tool_version", "plan_id", "plan_path", "plan_sha256",
                  "approval_reference", "contract_version",
                  "contract_scope_version"):
        if not nonempty_string(receipt.get(field)):
            errors.append(
                "initial Task Plan Receipt %s has empty %s" %
                (receipt_id, field))
    if receipt.get("target") != receipt.get("plan_id"):
        errors.append(
            "initial Task Plan Receipt target does not match plan_id")
    plan_sha = receipt.get("plan_sha256")
    if not isinstance(plan_sha, str) or not SHA256_RE.fullmatch(plan_sha):
        errors.append("initial Task Plan Receipt has invalid plan_sha256")
    plan_path = receipt.get("plan_path")
    if nonempty_string(plan_path) and isinstance(plan_sha, str) and \
            SHA256_RE.fullmatch(plan_sha):
        try:
            path = kblib.managed_repository_path(
                root, plan_path, runtime_paths.TASK_PLAN_DELTA_ROOT,
                suffixes=(".yaml",), must_exist=True)
            if kblib.sha256_bytes(kblib.read_bytes(path)) != plan_sha:
                errors.append(
                    "initial Task Plan bytes no longer match its Receipt")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append("initial Task Plan path is unavailable: %s" % exc)
    for field in ("after_coverage_sha256", "after_required_queue_sha256",
                  "after_progress_sha256", "contract_sha256"):
        value = receipt.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            errors.append(
                "initial Task Plan Receipt has invalid %s" % field)
    # Before the independent Queue compiler publishes its first receipt, the
    # live runtime is exactly the Task Plan transaction after-image.
    if progress.get("initial_queue_receipt") is None:
        for field, live in (
                ("after_coverage_sha256", coverage_sha),
                ("after_required_queue_sha256", queue_sha),
                ("after_progress_sha256", progress_sha)):
            if receipt.get(field) != live:
                errors.append(
                    "unmaterialized runtime does not match initial Task Plan "
                    "%s" % field)
        if receipt.get("contract_sha256") != contract_sha256(progress):
            errors.append(
                "unmaterialized Task Contract does not match initial Task "
                "Plan Receipt")
        contract = progress.get("contract") or {}
        if receipt.get("upstream_revision_id") != contract.get(
                "upstream_revision_id"):
            errors.append(
                "initial Task Plan Receipt upstream_revision_id differs from "
                "the unmaterialized Task Contract")
        if receipt.get("selected_profile_manifest") != contract.get(
                "selected_profile_manifest"):
            errors.append(
                "initial Task Plan Receipt selected Profile differs from the "
                "unmaterialized Task Contract")
    return errors


def contract_sha256(progress):
    """Return the canonical fingerprint of the immutable Task Contract.

    Before initial Queue materialization the contract is still an adopter
    input.  Once materialized, the compiler receipt and every task-state
    transition must carry this exact fingerprint.  Until a dedicated contract
    Amendment writer exists, any later mutation therefore fails closed.
    """
    contract = progress.get("contract") if isinstance(progress, dict) else None
    if not isinstance(contract, dict):
        return None
    try:
        return kblib.sha256_bytes(kblib.canonical_yaml(contract))
    except (TypeError, ValueError, kblib.YamlSubsetError):
        return None


def contract_anchor_chain(progress, catalog):
    """Return the hash-linked Task Contract anchor chain.

    Scope Amendments and Standards adoptions are independent append-only logs.
    Their receipt before/after contract fingerprints, rather than list order,
    form one unambiguous chain.  This lets a later Amendment continue from an
    adopted Standards contract without either writer owning the other's log.
    """
    errors = []
    receipt_id = progress.get("initial_queue_receipt")
    entry = catalog.get(receipt_id) if nonempty_string(receipt_id) else None
    if entry is None:
        return [], errors
    initial = entry[1]
    anchor = initial.get("contract_sha256")
    revision = initial.get("after_queue_revision")
    version = initial.get("contract_version")
    scope = initial.get("contract_scope_version")
    if not isinstance(anchor, str) or not SHA256_RE.fullmatch(anchor):
        errors.append("initial Queue receipt has invalid contract_sha256")
        return [], errors
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        errors.append("initial Queue receipt has invalid contract anchor revision")
        return [], errors
    if not nonempty_string(version):
        errors.append("initial Queue receipt has invalid contract_version anchor")
    if not nonempty_string(scope):
        errors.append("initial Queue receipt has invalid contract_scope_version anchor")
    chain = [{
        "queue_revision": revision,
        "contract_sha256": anchor,
        "contract_version": version,
        "scope_version": scope,
        "receipt_id": receipt_id,
    }]
    events = []
    for amendment in progress.get("amendments", []) if isinstance(
            progress.get("amendments"), list) else []:
        if (not isinstance(amendment, dict) or
                amendment.get("operation") not in
                ("scope-replan", "cancel-batch", "contract-amendment") or
                amendment.get("status") != "verified" or
                amendment.get("writeback_done") is not True):
            continue
        commit_id = amendment.get("verification_receipt")
        commit_entry = catalog.get(commit_id) if nonempty_string(
            commit_id) else None
        if commit_entry is None:
            continue
        receipt = commit_entry[1]
        label = "Amendment %s contract anchor" % amendment.get("id")
        valid = True
        for field in ("before_contract_sha256", "after_contract_sha256"):
            value = receipt.get(field)
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                errors.append("%s has invalid %s" % (label, field))
                valid = False
        if receipt.get("after_contract_scope_version") != amendment.get(
                "scope_version_after"):
            errors.append("%s after scope does not match its Amendment" % label)
            valid = False
        if receipt.get("before_contract_scope_version") != amendment.get(
                "scope_version_before"):
            errors.append("%s before scope does not match its Amendment" % label)
            valid = False
        if (amendment.get("operation") == "contract-amendment" and
                receipt.get("before_contract_scope_version") !=
                receipt.get("after_contract_scope_version")):
            # Scope belongs to the replan machinery; a contract amendment
            # that moved scope_version would be a scope change routed
            # around the Coverage proposal it requires.
            errors.append("%s may not change scope_version" % label)
            valid = False
        if not nonempty_string(receipt.get("after_contract_version")):
            errors.append("%s has invalid after_contract_version" % label)
            valid = False
        if receipt.get("queue_revision_after") != amendment.get(
                "queue_revision_after"):
            errors.append(
                "%s queue revision does not match its Amendment" % label
            )
            valid = False
        if valid:
            events.append({
                "label": label,
                "receipt_id": commit_id,
                "before_sha": receipt.get("before_contract_sha256"),
                "after_sha": receipt.get("after_contract_sha256"),
                "before_version": receipt.get("before_contract_version"),
                "after_version": receipt.get("after_contract_version"),
                "before_scope": receipt.get("before_contract_scope_version"),
                "after_scope": receipt.get("after_contract_scope_version"),
                "revision_before": receipt.get("queue_revision_before"),
                "revision_after": receipt.get("queue_revision_after"),
            })
    for adoption in progress.get("standards_adoptions", []) if isinstance(
            progress.get("standards_adoptions"), list) else []:
        if not isinstance(adoption, dict):
            continue
        commit_id = adoption.get("verification_receipt")
        commit_entry = catalog.get(commit_id) if nonempty_string(
            commit_id) else None
        if commit_entry is None:
            continue
        receipt = commit_entry[1]
        label = "Standards adoption %s contract anchor" % adoption.get("id")
        valid = True
        for field in ("before_contract_sha256", "after_contract_sha256"):
            value = receipt.get(field)
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                errors.append("%s has invalid %s" % (label, field))
                valid = False
        if receipt.get("queue_revision_before") != adoption.get(
                "queue_revision_before") or receipt.get(
                    "queue_revision_after") != adoption.get(
                        "queue_revision_after"):
            errors.append("%s queue revision does not match its record" % label)
            valid = False
        if receipt.get("before_contract_scope_version") != receipt.get(
                "after_contract_scope_version"):
            errors.append("%s may not change scope_version" % label)
            valid = False
        if (receipt.get("before_contract_version") != adoption.get(
                "contract_version_before") or
                receipt.get("after_contract_version") != adoption.get(
                    "contract_version_after")):
            errors.append("%s contract versions do not match its record" % label)
            valid = False
        if valid:
            events.append({
                "label": label,
                "receipt_id": commit_id,
                "before_sha": receipt.get("before_contract_sha256"),
                "after_sha": receipt.get("after_contract_sha256"),
                "before_version": receipt.get("before_contract_version"),
                "after_version": receipt.get("after_contract_version"),
                "before_scope": receipt.get("before_contract_scope_version"),
                "after_scope": receipt.get("after_contract_scope_version"),
                "revision_before": receipt.get("queue_revision_before"),
                "revision_after": receipt.get("queue_revision_after"),
            })

    remaining = list(events)
    while remaining:
        # A queue-replan bumps the live queue_revision without touching the
        # Task Contract, so it is deliberately not an anchor event; the next
        # anchor event therefore continues from the same contract identity at
        # a strictly later revision. The contract bytes, version, and scope
        # remain the chain; revisions only need to stay monotonic and agree
        # with each event's own sealed before/after pair.
        candidates = [event for event in remaining
                      if event["before_sha"] == anchor and
                      event["before_version"] == version and
                      event["before_scope"] == scope and
                      isinstance(event["revision_before"], int) and
                      not isinstance(event["revision_before"], bool) and
                      event["revision_before"] >= revision]
        if not candidates:
            errors.extend("%s does not continue the prior contract anchor" %
                          event["label"] for event in remaining)
            break
        if len(candidates) != 1:
            errors.append("contract anchor chain forks at %s via %s" % (
                anchor, ", ".join(sorted(event["label"]
                                         for event in candidates))))
            break
        event = candidates[0]
        remaining.remove(event)
        next_revision = event["revision_after"]
        if (not isinstance(next_revision, int) or
                isinstance(next_revision, bool) or
                next_revision != event["revision_before"] + 1):
            errors.append("%s must increment queue_revision exactly once" %
                          event["label"])
            break
        anchor = event["after_sha"]
        version = event["after_version"]
        scope = event["after_scope"]
        revision = next_revision
        chain.append({
            "queue_revision": revision,
            "contract_sha256": anchor,
            "contract_version": version,
            "scope_version": scope,
            "receipt_id": event["receipt_id"],
        })

    if (isinstance(progress.get("queue_revision"), int) and
            not isinstance(progress.get("queue_revision"), bool) and
            revision > progress.get("queue_revision")):
        errors.append("contract anchor chain points beyond live Queue revision")
    live_contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    if chain:
        if anchor != contract_sha256(progress):
            errors.append("contract anchor chain does not bind the current Task Contract")
        if version != live_contract.get("contract_version"):
            errors.append("contract anchor chain does not bind current contract_version")
        if scope != live_contract.get("scope_version"):
            errors.append("contract anchor chain does not bind current scope_version")
    return chain, errors


def contract_sha_at_revision(chain, revision):
    anchors = [entry for entry in chain
               if isinstance(revision, int) and
               isinstance(entry.get("queue_revision"), int) and
               entry.get("queue_revision") <= revision]
    return anchors[-1].get("contract_sha256") if anchors else None


def read_set_load_closure(root, selected_paths,
                           selected_profile_manifest=None,
                           selected_profile_route_ids=None):
    """Resolve Read Sets and non-Read-Set targets from selected boundaries.

    Top-level Read Sets resolve only from their machine frontmatter declaration;
    Markdown sections and Wiki Links never change the closure.  Direct target
    paths enter ``modules`` and Read Set IDs traverse through the canonical
    declaration registry.  ``visited`` makes declared cycles benign.

    Profile supplemental Read Sets use the same machine ``load_edges`` shape.
    They are discovered only inside the selected Profile directory and must
    bind one selected ``P:<profile>:<route>`` identity.  Profile prose, Wiki
    Links, and registry tables never change the closure.  Kernel and Profile
    namespaces remain non-interchangeable.  Unsafe bytes, invalid declarations,
    unknown dependencies, and namespace/route mismatches are explicit errors.
    """
    selected = {
        value for value in (selected_paths or []) if nonempty_string(value)
    }
    read_sets = set()
    invalid_selected = set()
    modules = set()
    pending = []
    visited = set()
    closure_errors = []
    profile_dir = (os.path.dirname(selected_profile_manifest)
                   if nonempty_string(selected_profile_manifest) else None)
    profile_routes = {
        value for value in (selected_profile_route_ids or [])
        if nonempty_string(value)
    }
    read_set_schema = None
    try:
        read_set_schema = read_set_contract.load_schema(root)
        kernel_registry = read_set_contract.discover(
            root, schema=read_set_schema)
    except read_set_contract.ReadSetContractError as exc:
        kernel_registry = {}
        closure_errors.append(str(exc))
    kernel_paths = {
        record["path"]: record for record in kernel_registry.values()
    }
    profile_registry = {}
    if nonempty_string(selected_profile_manifest):
        try:
            profile_registry = read_set_contract.discover_profile(
                root, selected_profile_manifest)
        except read_set_contract.ReadSetContractError as exc:
            closure_errors.append(str(exc))
    profile_paths = {
        record["path"]: record for record in profile_registry.values()
    }

    def read_text(relative):
        try:
            path = kblib.repository_path(
                root, relative, must_exist=True, reject_symlink=True)
            with open(path, encoding="utf-8") as handle:
                return handle.read(), None
        except (OSError, UnicodeError, ValueError) as exc:
            return None, str(exc)

    def read_set_role_error(relative, text):
        if relative in kernel_paths:
            return None
        profile_record = profile_paths.get(relative)
        if profile_record is not None:
            route_id = profile_record["route_id"]
            if route_id in profile_routes:
                return None
            return ("%s declares profile Read Set route_id %r, which is not "
                    "present in selected_profile_route_ids" %
                    (relative, route_id))
        document_type = kblib.read_set_document_type(text)
        if document_type is None:
            return ("%s does not prove a canonical machine Read Set "
                    "declaration" % relative)
        return ("%s declares type %s but is absent from the canonical machine "
                "registry for %s" %
                (relative, document_type,
                 read_set_schema["path_prefix"]
                 if (read_set_schema is not None and
                     document_type == read_set_schema["document_type"])
                 else profile_dir))

    # A selected supplemental route already exists as a route decision.  Its
    # machine-declared Read Set path becomes a closure root; this resolves the
    # route-to-path binding without consulting the Profile's prose registry.
    for route_id in sorted(profile_routes):
        record = profile_registry.get(route_id)
        if record is None:
            closure_errors.append(
                "selected Profile route %s has no machine profile-read-set "
                "declaration inside %r" % (route_id, profile_dir))
            continue
        read_sets.add(record["path"])
        pending.append(record["path"])

    for relative in sorted(selected):
        text, read_error = read_text(relative)
        if text is None:
            closure_errors.append(
                "selected Read Set %s is unsafe or unreadable UTF-8: %s" %
                (relative, read_error))
            continue
        role_error = read_set_role_error(relative, text)
        if role_error:
            invalid_selected.add(relative)
            closure_errors.append(role_error)
            continue
        read_sets.add(relative)
        pending.append(relative)

    pending.sort(reverse=True)
    while pending:
        relative = pending.pop()
        if relative in visited:
            continue
        visited.add(relative)
        text, read_error = read_text(relative)
        if text is None:
            closure_errors.append(
                "transitively selected Read Set %s is unsafe or unreadable "
                "UTF-8: %s" % (relative, read_error))
            continue
        record = kernel_paths.get(relative) or profile_paths.get(relative)
        if record is None:
            closure_errors.append(
                "%s is absent from the canonical machine Read Set registry" %
                relative)
            continue
        declaration = record["declaration"]
        dependency_paths = []
        for route_id in read_set_contract.dependencies(declaration):
            dependency = (kernel_registry.get(route_id) or
                          profile_registry.get(route_id))
            if dependency is None:
                closure_errors.append(
                    "%s references unknown Read Set %s" %
                    (relative, route_id))
                continue
            if (route_id in profile_registry and
                    route_id not in profile_routes):
                closure_errors.append(
                    "%s references Profile Read Set %s, which is not present "
                    "in selected_profile_route_ids" % (relative, route_id))
                continue
            dependency_paths.append(dependency["path"])
        targets = read_set_contract.targets(declaration)

        for target in sorted(set(dependency_paths)):
            target_text, target_error = read_text(target)
            if target_text is None:
                closure_errors.append(
                    "Read Set dependency %s is unsafe or unreadable UTF-8: %s" %
                    (target, target_error))
                continue
            role_error = read_set_role_error(target, target_text)
            if role_error:
                closure_errors.append(role_error)
                continue
            if target not in read_sets:
                read_sets.add(target)
                pending.append(target)

        for target in targets:
            if target in kernel_paths or target in profile_paths:
                closure_errors.append(
                    "%s declares Read Set %s as a target path; machine Read "
                    "Set dependencies must use load_edges[].read_sets" %
                    (relative, target))
                continue
            target_text, target_error = read_text(target)
            if target_text is None:
                closure_errors.append(
                    "Read Set declared target %s is unsafe or unreadable "
                    "UTF-8: %s" % (target, target_error))
                continue
            document_type = kblib.read_set_document_type(target_text)
            if document_type is not None:
                closure_errors.append(
                    "%s target %s declares type %s but is not a registered "
                    "load_edges[].read_sets dependency" %
                    (relative, target, document_type))
                continue
            modules.add(target)

    return read_sets, modules, invalid_selected, sorted(set(closure_errors))


def live_read_set_load_findings(root, contract):
    """Return structural errors and closure gaps of the live Task Contract.

    The two findings are separated because only one of them can be repaired
    from where the checker stands.  A selected Read Set that is unsafe,
    unreadable, or unusable as a traversal root leaves the load declaration
    unresolvable, and no reading of history makes broken bytes resolvable, so
    it stays an error; ``invalid_selected`` is that same class, a path that
    cannot serve as a traversal root, and is reported with it.  A *completeness*
    gap -- a Read Set or a non-Read-Set target the resolved closure names and
    the declaration omits -- is returned separately and is never a runtime
    error.

    The reason is the one the plan-side twin states at ``validate_current``:
    the live contract's five load fields were written by a Standards adoption
    whose plan bytes are sealed into append-only receipts, and
    ``Tools/adopt_standards.py`` -- the only writer that can re-declare them
    for a running task -- refuses to start while ``validate_runtime`` reports
    an error.  Making the gap an error would therefore lock the instance out of
    the one transaction that repairs it, exactly as refusing a sealed
    historical plan would. The canonical Read Set contract therefore puts the
    completeness judgment where a declaration is still writable: a plan being
    admitted.
    """
    if not isinstance(contract, dict):
        return [], []
    selected_values = contract.get("selected_read_sets")
    loaded_values = contract.get("loaded_module_paths")
    if not isinstance(selected_values, list) or not isinstance(
            loaded_values, list):
        return [], []
    selected = set(value for value in selected_values
                   if nonempty_string(value))
    loaded = set(value for value in loaded_values
                 if nonempty_string(value))
    read_sets, modules, invalid_selected, closure_errors = \
        read_set_load_closure(
            root, selected,
            contract.get("selected_profile_manifest"),
            contract.get("selected_profile_route_ids"),
        )
    errors = ["Progress contract Read Set load closure: %s" % error
              for error in closure_errors]
    for target in sorted(invalid_selected):
        if not any(target in error for error in closure_errors):
            errors.append(
                "Progress contract.selected_read_sets path %s cannot be used "
                "as a Read Set traversal root, per %s" %
                (target, READ_SET_BOUNDARY_OWNER_PATH))
    gaps = []
    for target in sorted(read_sets - selected):
        gaps.append(
            "Progress contract.selected_read_sets omits %s, which a loading "
            "boundary of its transitive Read Set closure selects, per %s" %
            (target, READ_SET_BOUNDARY_OWNER_PATH))
    for target in sorted(modules - loaded):
        gaps.append(
            "Progress contract.loaded_module_paths omits %s, which a loading "
            "boundary in the transitive Read Set closure names, per %s" %
            (target, READ_SET_BOUNDARY_OWNER_PATH))
    return errors, gaps
