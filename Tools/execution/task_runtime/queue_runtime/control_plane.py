"""Which pages are K13/10 Expression hubs, and may this batch touch them.

Hub and control-plane pages are shared by every concurrently admitted batch,
so a batch that edits one is not isolated from the others.  Admission is
therefore decided here rather than per page at the point of edit.
"""

import os

import Tools.governance.profile.profile_contract as profile_contract
import Tools.platform.common.kblib as kblib
import Tools.governance.profile.profile_layout_contract as profile_layout_contract

from Tools.execution.task_runtime.queue_runtime.primitives import nonempty_string
from Tools.execution.task_runtime.queue_runtime.profile_view import (
    EXPRESSION_LAYER_SLOT,
    open_profile_view_read_scope,
    profile_view_snapshot_error,
    profile_load_authorized_view,
    profile_view_read_scope_errors,
)
# K13/10 concurrency admission condition 2 ("B does not edit control or hub
# pages").  The kernel enumerates the members; these constants only spell the
# machine judgment for that enumeration.  `type` and `scope` are the K08
# closed vocabularies in `kernel/K08 Metadata and Status/vocabulary-base.yaml`;
# the profile side reuses the `Expression Layer Entry` rows the selected
# profile already registers, so no profile slot or interface is added here.
# The kernel's "other profile-registered hub roles" clause has no registration
# path today and therefore contributes no member; see K13/10.
HUB_PAGE_TYPES = frozenset(("overview", "runtime-card", "card-index"))
HUB_TERM_TYPE = "term"
HUB_TERM_SCOPE = "shared"
CONTROL_PLANE_PREFIXES = (
    "kernel/",
    profile_layout_contract.PROFILES_DIRECTORY + "/",
    "Tools/",
)


def batch_touches_control_plane(item):
    """Say whether one batch's own manifest edits the control plane.

    This is the governance predicate, and it is deliberately about the
    objects a batch changes rather than about which tool it runs.  A tool
    name can be avoided -- a file is editable without any writer -- while a
    batch that carries `kernel/`, `profiles/` or `Tools/` in its manifest is
    doing governance whatever it invokes, and it still has to reach
    merge-ready through the one edge no editor can route around.
    """
    if not isinstance(item, dict):
        return False
    for path in item.get("manifest") or []:
        if isinstance(path, str) and path.startswith(CONTROL_PLANE_PREFIXES):
            return True
    return False


def unadmitted_profile_hub_paths(root, profile_manifest):
    """Fail closed when corrective adoption has no authorized typed view.

    The hard-cut runtime does not parse an invalid Profile through a second,
    weaker Expression table reader.  A corrective serial-integrator may still
    replace that Profile, but concurrent hub admission remains unavailable
    until ``profile-load`` authorizes the current contract.
    """
    if not nonempty_string(profile_manifest):
        return set(), []
    return set(), [
        "selected Profile has no authorized typed Registered Artifacts "
        "projection, so the K13/10 hub set cannot be derived"
    ]


def profile_hub_paths(root, profile_manifest, *, authorized_view=None,
                      evaluate_if_missing=True,
                      allow_unadmitted_profile=False,
                      profile_read_scope=None):
    """Return Expression hubs from one snapshot-bound Profile view.

    K13/10 binds dependency-map pages registered by the ``Expression Layer
    Entry`` into the hub set.  The rows are projected from the typed contract
    produced by the same ``profile-load`` invocation as ``authorized_view``;
    neither the manifest nor the slot bytes are reparsed here.  The complete
    Profile tree is CAS-checked around the projection so a verdict for
    revision A cannot be combined with revision B's contract.

    Direct callers may omit ``authorized_view`` and this function will create
    exactly one.  Such a direct call owns both currency checks.  The outer
    runtime instead passes the opaque read scope it opened after its own
    before check; this helper consumes the contract bound to that scope and
    lets the runtime's final check close the phase.  The unadmitted path is
    reserved for the explicit corrective-adoption escape.
    """
    if type(evaluate_if_missing) is not bool:
        raise TypeError("evaluate_if_missing must be boolean")
    if type(allow_unadmitted_profile) is not bool:
        raise TypeError("allow_unadmitted_profile must be boolean")
    if allow_unadmitted_profile:
        if authorized_view is not None or profile_read_scope is not None:
            raise ValueError("corrective Profile hub derivation cannot accept "
                             "an authorized view or read scope")
        return unadmitted_profile_hub_paths(root, profile_manifest)

    if not nonempty_string(profile_manifest):
        return set(), []
    if authorized_view is None:
        if not evaluate_if_missing:
            # The caller already records the producer failure.  Do not create
            # a second observation window or duplicate its detailed
            # diagnostics.  Hub admission still fails closed: otherwise a
            # queued concurrent batch could be reported ready merely because
            # its selected Profile never produced an authorized view.
            return set(), ["selected Profile has no authorized view, so the "
                           "K13/10 hub set cannot be derived"]
        authorized_view, errors = profile_load_authorized_view(
            root, profile_manifest)
        if authorized_view is None:
            return set(), errors

    owns_currency_boundary = profile_read_scope is None
    if owns_currency_boundary:
        profile_read_scope, view_errors = open_profile_view_read_scope(
            root, profile_manifest, authorized_view)
    else:
        view_errors = profile_view_read_scope_errors(
            profile_read_scope, root, profile_manifest, authorized_view)
    if view_errors:
        return set(), view_errors
    try:
        paths = set(profile_contract.
                    expression_dependency_map_paths_projection(
                        authorized_view["_contract"]))
    except (KeyError, TypeError,
            profile_contract.ProfileContractError) as exc:
        return set(), ["authorized selected Profile has no valid typed "
                       "Registered Artifacts projection, so the K13/10 hub "
                       "set cannot be derived: %s" % exc]
    if owns_currency_boundary:
        after_error = profile_view_snapshot_error(
            root, authorized_view, "after")
        if after_error:
            return set(), [after_error]
    return paths, []


def _page_frontmatter(root, relative_path):
    """Return ``(exists, fields, error)`` for one repository page.

    ``fields`` is ``None`` when the page exists but its metadata cannot be
    read, which the caller reports instead of treating as "not a hub".
    """
    try:
        absolute = kblib.repository_path(root, relative_path)
    except (OSError, ValueError) as exc:
        return False, None, "path is unsafe: %s" % exc
    if os.path.islink(absolute) or not os.path.isfile(absolute):
        return False, {}, None
    try:
        with open(absolute, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError, ValueError) as exc:
        return True, None, "page is unreadable: %s" % exc
    raw = kblib.extract_frontmatter(text)
    if raw is None:
        if text.startswith("---\n") or text.startswith("---\r\n"):
            return True, None, "frontmatter has no closing fence"
        return True, {}, None
    try:
        fields = kblib.parse_yaml_subset(raw)
    except (ValueError, kblib.YamlSubsetError) as exc:
        return True, None, "frontmatter is unparsable: %s" % exc
    if not isinstance(fields, dict):
        return True, None, "frontmatter is not a mapping"
    return True, fields, None


def _hub_basis(fields):
    """Name the K13/10 hub role a page's own metadata proves, or ``None``."""
    page_type = fields.get("type")
    if page_type in HUB_PAGE_TYPES:
        return "type=%s" % page_type
    if page_type == HUB_TERM_TYPE and fields.get("scope") == HUB_TERM_SCOPE:
        return "type=%s scope=%s" % (HUB_TERM_TYPE, HUB_TERM_SCOPE)
    return None


def hub_page_admission(root, manifest, records, registered_hub_paths, cache):
    """Classify one batch manifest against K13/10 admission condition 2.

    The kernel forbids a concurrently admitted batch from *editing* a control
    or hub page.  A hub page that already exists is an edit and blocks
    activation; a hub page this batch creates is not, and is reported as a
    candidate for the integrator's post-merge hub synchronization step.  This
    only reports what the bytes say; choosing the execution mode is the
    integrator's decision.
    """
    blocking = []
    candidates = []
    unresolved = []
    for path in sorted(set(manifest or [])):
        if not nonempty_string(path):
            continue
        if path not in cache:
            cache[path] = _page_frontmatter(root, path)
        exists, fields, error = cache[path]
        registered = path in registered_hub_paths
        if error is not None:
            if exists and registered:
                blocking.append("%s (%s)" % (path, EXPRESSION_LAYER_SLOT))
            else:
                unresolved.append("%s (%s)" % (path, error))
            continue
        if exists:
            basis = _hub_basis(fields)
            if registered:
                basis = EXPRESSION_LAYER_SLOT if basis is None else basis
            if basis is not None:
                blocking.append("%s (%s)" % (path, basis))
            continue
        declared = records.get(path) or {}
        basis = None
        if declared.get("type") in HUB_PAGE_TYPES:
            basis = "Coverage type=%s" % declared.get("type")
        elif registered:
            basis = EXPRESSION_LAYER_SLOT
        if basis is not None:
            candidates.append("%s (%s)" % (path, basis))
    return {
        "blocking": blocking,
        "candidates": candidates,
        "unresolved": unresolved,
    }
