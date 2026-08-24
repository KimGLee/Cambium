"""The immutable Task Contract, its anchor chain, and the Read Set it selects.

The canonical fingerprint, the hash-linked chain of anchors across adoptions
and Amendments, and the closure of Read Set loads the contract currently
selects.  These are one subject: the fingerprint is only meaningful against
the revision the chain places it at.
"""

import os

import kblib

from queue_runtime.canon import SHA256_RE
from queue_runtime.primitives import _nonempty_string


READ_SET_BOUNDARY_OWNER_PATH = \
    "kernel/K00 Standards Control/15 Read Set Loading Boundaries.md"
READ_SET_PATH_PREFIX = "kernel/Read Sets/"


def _contract_sha256(progress):
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


def _contract_anchor_chain(progress, catalog):
    """Return the hash-linked Task Contract anchor chain.

    Scope Amendments and Standards adoptions are independent append-only logs.
    Their receipt before/after contract fingerprints, rather than list order,
    form one unambiguous chain.  This lets a later Amendment continue from an
    adopted Standards contract without either writer owning the other's log.
    """
    errors = []
    receipt_id = progress.get("initial_queue_receipt")
    entry = catalog.get(receipt_id) if _nonempty_string(receipt_id) else None
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
    if not _nonempty_string(version):
        errors.append("initial Queue receipt has invalid contract_version anchor")
    if not _nonempty_string(scope):
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
        commit_entry = catalog.get(commit_id) if _nonempty_string(
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
        if not _nonempty_string(receipt.get("after_contract_version")):
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
        commit_entry = catalog.get(commit_id) if _nonempty_string(
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
        if anchor != _contract_sha256(progress):
            errors.append("contract anchor chain does not bind the current Task Contract")
        if version != live_contract.get("contract_version"):
            errors.append("contract anchor chain does not bind current contract_version")
        if scope != live_contract.get("scope_version"):
            errors.append("contract anchor chain does not bind current scope_version")
    return chain, errors


def _contract_sha_at_revision(chain, revision):
    anchors = [entry for entry in chain
               if isinstance(revision, int) and
               isinstance(entry.get("queue_revision"), int) and
               entry.get("queue_revision") <= revision]
    return anchors[-1].get("contract_sha256") if anchors else None


def _read_set_load_closure(root, selected_paths,
                           selected_profile_manifest=None,
                           selected_profile_route_ids=None):
    """Resolve Read Sets and non-Read-Set targets from selected boundaries.

    Boundary references to another Read Set select that route too, so traversal
    continues until no new Read Set remains. ``visited`` makes cycles benign.
    A kernel Read Set proves both its canonical namespace and ``type:
    read-set``; a profile supplemental Read Set proves ``type:
    profile-read-set`` in its own frontmatter. Every other boundary target is
    a loaded module, including ordinary indexes inside ``kernel/Read Sets``.

    Every selected or boundary-referenced Read Set is decoded as UTF-8 and
    classified from its own frontmatter.  Kernel and profile namespaces are
    not interchangeable: ``read-set`` belongs under ``kernel/Read Sets/``;
    ``profile-read-set`` belongs under the selected profile directory and its
    route ID must be in the selected profile-route list.  Read/decode failures
    and namespace/route mismatches are explicit closure errors rather than a
    reason to silently shrink the load obligation.
    """
    selected = {
        value for value in (selected_paths or []) if _nonempty_string(value)
    }
    read_sets = set()
    invalid_selected = set()
    modules = set()
    pending = []
    visited = set()
    closure_errors = []
    profile_dir = (os.path.dirname(selected_profile_manifest)
                   if _nonempty_string(selected_profile_manifest) else None)
    profile_routes = {
        value for value in (selected_profile_route_ids or [])
        if _nonempty_string(value)
    }

    def read_text(relative):
        try:
            path = kblib.repository_path(
                root, relative, must_exist=True, reject_symlink=True)
            with open(path, encoding="utf-8") as handle:
                return handle.read(), None
        except (OSError, UnicodeError, ValueError) as exc:
            return None, str(exc)

    def frontmatter_fields(text):
        frontmatter = kblib.extract_frontmatter(text or "")
        if frontmatter is None:
            return {}
        try:
            fields = kblib.parse_yaml_subset(frontmatter)
        except (ValueError, kblib.YamlSubsetError):
            return {}
        return fields if isinstance(fields, dict) else {}

    def read_set_role_error(relative, text):
        document_type = kblib.read_set_document_type(text)
        if document_type is None:
            return ("%s does not prove frontmatter type read-set or "
                    "profile-read-set" % relative)
        if document_type == "read-set":
            if not relative.startswith(READ_SET_PATH_PREFIX):
                return ("%s declares type read-set outside the canonical %s "
                        "namespace" % (relative, READ_SET_PATH_PREFIX))
            return None
        if not profile_dir or not (relative == profile_dir or
                                   relative.startswith(profile_dir + "/")):
            return ("%s declares type profile-read-set outside the selected "
                    "profile directory %r" % (relative, profile_dir))
        route_id = frontmatter_fields(text).get("route_id")
        if not _nonempty_string(route_id) or route_id not in profile_routes:
            return ("%s declares profile Read Set route_id %r, which is not "
                    "present in selected_profile_route_ids" %
                    (relative, route_id))
        return None

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
        for target in kblib.read_set_boundary_targets(text):
            target_text, target_error = read_text(target)
            if target_text is None:
                closure_errors.append(
                    "Read Set boundary target %s is unsafe or unreadable "
                    "UTF-8: %s" % (target, target_error))
                continue
            document_type = (
                kblib.read_set_document_type(target_text)
            )
            if document_type is not None:
                role_error = read_set_role_error(target, target_text)
                if role_error:
                    closure_errors.append(role_error)
                    continue
                if target not in read_sets:
                    read_sets.add(target)
                    pending.append(target)
                continue
            modules.add(target)

    return read_sets, modules, invalid_selected, sorted(set(closure_errors))


def _live_read_set_load_findings(root, contract):
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
    historical plan would.  K00/15 puts the judgment where a declaration is
    still writable: a plan being admitted.
    """
    if not isinstance(contract, dict):
        return [], []
    selected_values = contract.get("selected_read_sets")
    loaded_values = contract.get("loaded_module_paths")
    if not isinstance(selected_values, list) or not isinstance(
            loaded_values, list):
        return [], []
    selected = set(value for value in selected_values
                   if _nonempty_string(value))
    loaded = set(value for value in loaded_values
                 if _nonempty_string(value))
    read_sets, modules, invalid_selected, closure_errors = \
        _read_set_load_closure(
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
