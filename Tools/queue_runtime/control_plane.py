"""Which pages are K13/10 Expression hubs, and may this batch touch them.

Hub and control-plane pages are shared by every concurrently admitted batch,
so a batch that edits one is not isolated from the others.  Admission is
therefore decided here rather than per page at the point of edit.
"""

import os

import check_profile
import kblib
import profile_layout_contract

from queue_runtime.primitives import nonempty_string
from queue_runtime.profile_view import (
    EXPRESSION_LAYER_SLOT,
    open_profile_view_read_scope,
    profile_view_snapshot_error,
    profile_load_authorized_view,
    profile_view_read_scope_errors,
)
from queue_runtime.repofs import (
    normalized_repository_path,
    _path_error,
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
HUB_DEPENDENCY_MAP_LABEL = "existing canonical dependency-map"


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
    """Derive hub pages for the explicit corrective-adoption escape only.

    Ordinary runtime consumers must use :func:`profile_hub_paths`, whose slot
    path comes from one authorized typed contract.  This raw manifest reader
    survives only so ``adopt_standards`` can inspect and replace an invalid
    current Profile without requiring that broken closure to authorize itself.
    """
    paths = set()
    if not nonempty_string(profile_manifest):
        return paths, []
    try:
        profile_layout_contract.parse_profile_manifest_path(profile_manifest)
    except profile_layout_contract.ProfileLayoutError:
        # The exact runtime shape is owned by
        # selected_profile_manifest_errors; this only refuses to read a
        # package that is not a profile manifest at all.
        return paths, []
    try:
        manifest_path = kblib.repository_path(
            root, profile_manifest, must_exist=True, reject_symlink=True)
        manifest_text = check_profile.read_text(manifest_path)
    except (OSError, UnicodeError, ValueError) as exc:
        return paths, ["selected profile manifest is unreadable, so the "
                       "K13/10 hub set cannot be derived: %s" % exc]
    binding = kblib.profile_slot_bindings(manifest_text).get(
        EXPRESSION_LAYER_SLOT)
    if not nonempty_string(binding):
        # No slot binding at all: the profile registers no expression hub.
        return paths, []
    profile_dir = os.path.dirname(manifest_path)
    kind, detail = kblib.resolve_profile_binding(binding, root, profile_dir)
    if kind != "path":
        return paths, [
            "selected profile %s binding is %s, so the K13/10 hub set cannot "
            "be derived" % (EXPRESSION_LAYER_SLOT, kind)
        ]
    try:
        text = check_profile.read_text(detail)
    except (OSError, UnicodeError, ValueError) as exc:
        return paths, ["selected profile %s is unreadable, so the K13/10 hub "
                       "set cannot be derived: %s" % (EXPRESSION_LAYER_SLOT,
                                                      exc)]
    for cells in check_profile.table_rows(text.splitlines()):
        if len(cells) != 2:
            continue
        label = check_profile.unbacktick(cells[0]).strip().lower()
        if not label.startswith(HUB_DEPENDENCY_MAP_LABEL):
            continue
        for declared in cells[1].split(";"):
            candidate = normalized_repository_path(declared)
            if candidate is None or candidate.lower() == "none":
                continue
            if "TODO(" in candidate or "/" not in candidate:
                # An unfilled sentinel or an opaque artifact ID is not a
                # decidable repository path; check_profile owns that verdict.
                continue
            if _path_error(root, candidate, must_exist=False) is None:
                paths.add(candidate)
    return paths, []


def profile_hub_paths(root, profile_manifest, *, authorized_view=None,
                      evaluate_if_missing=True,
                      allow_unadmitted_profile=False,
                      profile_read_scope=None):
    """Return Expression hubs from one snapshot-bound Profile view.

    K13/10 binds pages registered by the ``Expression Layer Entry`` into the
    hub set.  The slot path is taken from the typed dependency edges produced
    by the same ``profile-load`` invocation as ``authorized_view``; the
    manifest is never reparsed.  The complete Profile tree is CAS-checked
    before and after reading the slot, so a verdict for revision A cannot be
    combined with Expression rows from revision B.

    Direct callers may omit ``authorized_view`` and this function will create
    exactly one.  Such a direct call owns both currency checks.  The outer
    runtime instead passes the opaque read scope it opened after its own
    before check; this helper then reads the same immutable snapshot and lets
    the runtime's final check close the phase.  The unadmitted path is reserved
    for the explicit corrective-adoption escape.
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
    slot_paths = dict(authorized_view["_manifest_slot_paths"])
    expression_path = slot_paths.get(EXPRESSION_LAYER_SLOT)
    try:
        text = authorized_view["_profile_snapshot"].read_text(
            expression_path)
    except (KeyError, OSError, UnicodeError, ValueError) as exc:
        return set(), ["authorized selected profile %s is unreadable, so the "
                       "K13/10 hub set cannot be derived: %s" % (
                           EXPRESSION_LAYER_SLOT, exc)]
    if owns_currency_boundary:
        after_error = profile_view_snapshot_error(
            root, authorized_view, "after")
        if after_error:
            return set(), [after_error]

    paths = set()
    for cells in check_profile.table_rows(text.splitlines()):
        if len(cells) != 2:
            continue
        label = check_profile.unbacktick(cells[0]).strip().lower()
        if not label.startswith(HUB_DEPENDENCY_MAP_LABEL):
            continue
        for declared in cells[1].split(";"):
            candidate = normalized_repository_path(declared)
            if candidate is None or candidate.lower() == "none":
                continue
            if "TODO(" in candidate or "/" not in candidate:
                continue
            if _path_error(root, candidate, must_exist=False) is None:
                paths.add(candidate)
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
