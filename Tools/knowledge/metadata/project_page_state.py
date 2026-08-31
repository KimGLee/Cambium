#!/usr/bin/env python3
"""Project contract-declared owner state onto page frontmatter (K08/07).

The metadata execution contract, rather than this module, declares which
fields this writer may project, where their canonical values live, which
evidence they require, and how page copies reconcile.  Coverage remains the
state owner; a page value is never promoted into authority by this tool.

Dry runs build an immutable projection plan without taking the runtime writer
lock.  ``--apply`` builds that plan once while holding the shared writer lock,
stages every changed after-image, performs one exact final identity-and-bytes
descriptor open per changed page, and then publishes the batch.  Original page
inodes are retained as rollback images until the whole batch and its Ledger
binding have been revalidated.  Cooperating writers share the lock; unexpected
namespace drift still fails closed.  A fully restored failure clears the lock,
while an unproven rollback deliberately keeps its recovery journal.
"""

import errno
import hashlib
import json
import os
import re
import stat
import sys
import uuid

import Tools.platform.common.kblib as kblib
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.knowledge.metadata.metadata_page_state_contract as metadata_page_state_contract
import Tools.platform.repository.path_capability as path_capability
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.repository import repository

TOOL = "project_page_state"
TOOL_VERSION = "2.0.0"
WRITER_CAPABILITY = "project-page-state-v2"
UPSERT_EXACT_OR_REMOVE_POLICY = \
    metadata_execution_contract.UPSERT_EXACT_OR_REMOVE_POLICY
CONTENT_CHANGE_REMOVE_OWNER_RULE = \
    "remove-owner-and-page-copy-on-semantic-content-change-v1"
SEMANTIC_FINGERPRINT_PROTOCOL = "cambium-semantic-page-v1"
TEMP_PREFIX = runtime_paths.RUNTIME_ROOT + "-page-state-"
JOURNAL_NAME = os.path.basename(
    runtime_paths.PAGE_STATE_RECOVERY_JOURNAL_PATH)


class PageProjection:
    """One immutable page before-image and its validated planned after-image."""

    __slots__ = ("relative", "snapshot", "after_data", "changes")

    def __init__(self, relative, snapshot, after_data, changes):
        self.relative = relative
        self.snapshot = snapshot
        self.after_data = after_data
        self.changes = tuple(changes)

    @property
    def changed(self):
        return bool(self.changes)


class ProjectionPlan:
    """One Ledger snapshot and every selected typed page target."""

    __slots__ = (
        "ledger", "pages", "rules", "contract_rule_fingerprint",
        "revalidate_contract",
    )

    def __init__(self, ledger, pages, rules, revalidate_contract):
        self.ledger = ledger
        self.pages = tuple(pages)
        self.rules = tuple(rules)
        self.contract_rule_fingerprint = \
            metadata_page_state_contract.rules_fingerprint(self.rules)
        self.revalidate_contract = bool(revalidate_contract)


class StagedProjection:
    """A staged after-image plus its exact original-inode rollback claim."""

    __slots__ = (
        "projection", "parent_fd", "temporary_name", "backup_name",
        "stage_artifact_name", "rollback_artifact_name", "stage_fd",
        "stage_dev", "stage_ino", "stage_mode", "claimed", "published",
    )

    def __init__(self, projection, parent_fd, temporary_name, backup_name,
                 stage_fd, stage_descriptor):
        self.projection = projection
        self.parent_fd = parent_fd
        self.temporary_name = temporary_name
        self.backup_name = backup_name
        self.stage_artifact_name = temporary_name
        self.rollback_artifact_name = backup_name
        self.stage_fd = stage_fd
        self.stage_dev = stage_descriptor.st_dev
        self.stage_ino = stage_descriptor.st_ino
        self.stage_mode = stage_descriptor.st_mode
        self.claimed = False
        self.published = False


def _staged_artifact_descriptor(staged):
    return {
        "path": staged.projection.relative,
        "parent": staged.projection.snapshot.parent_repository_path,
        "staged_after_image": staged.stage_artifact_name,
        "staged_after_image_active": staged.temporary_name,
        "staged_after_device": staged.stage_dev,
        "staged_after_inode": staged.stage_ino,
        "staged_after_sha256": kblib.sha256_bytes(
            staged.projection.after_data),
        "rollback_image": staged.rollback_artifact_name,
        "rollback_image_active": staged.backup_name,
        "claimed": staged.claimed,
        "published": staged.published,
    }


def _render_scalar(value):
    """Render one scalar through the shared restricted-YAML serializer."""
    rendered = kblib.canonical_yaml({"value": value})
    return rendered[len("value: "):].rstrip("\n")


def _projection_rules(root):
    """Load this writer's rules through the sole contract API.

    Keeping the dependency here is deliberate: page planning never parses the
    generated JSON itself and cannot grow a second interpretation of the
    compiler's envelope.
    """
    contract = metadata_execution_contract.load_metadata_execution_contract(
        root)
    raw_rules = metadata_execution_contract.rules_for_capability(
        contract, WRITER_CAPABILITY)
    if not isinstance(raw_rules, (list, tuple)) or not raw_rules:
        raise ValueError(
            "metadata execution contract authorizes no %s rules" %
            WRITER_CAPABILITY)
    rules = []
    seen = set()
    for index, rule in enumerate(raw_rules):
        if not isinstance(rule, dict):
            raise ValueError("field_rules[%d] must be a mapping" % index)
        field = rule.get("field")
        if not isinstance(field, str) or not field.strip():
            raise ValueError(
                "field_rules[%d] field must be a non-empty string" % index)
        if field in seen:
            raise ValueError(
                "metadata execution contract repeats page projection for %s" %
                field)
        seen.add(field)
        adapter = rule.get("source_adapter")
        if adapter not in frozenset((
                metadata_page_state_contract.ROW_VALUE_ADAPTER,)).union(
                metadata_page_state_contract.PROPERTY_VALUE_ADAPTERS):
            raise ValueError(
                "page projection field %s uses unsupported source adapter %r" %
                (field, adapter))
        metadata_page_state_contract.validate_value_rule(rule, field)
        _reconcile_policy(rule, field)
        rules.append(dict(rule))
    return tuple(rules)


def _reconcile_policy(rule, field):
    """Accept the sole reconciliation protocol this writer implements."""
    raw = rule.get("reconcile_policy")
    if raw == UPSERT_EXACT_OR_REMOVE_POLICY:
        return "exact"
    raise ValueError(
        "page projection field %s has unsupported reconcile policy %r" %
        (field, raw))


def semantic_content_fingerprint(relative, text, rules):
    """Hash page semantics while excluding every contract-managed copy.

    Frontmatter is canonicalized as data so key order and scalar quoting are
    not treated as a substantive edit.  The body bytes and canonical path are
    bound exactly.  The exclusion set is derived solely from ``rules``;
    adding a new machine projection therefore cannot accidentally invalidate
    its own review/content-change evidence.
    """
    match = metadata_page_state_contract.FRONTMATTER.match(text)
    projected = {
        rule.get("field") for rule in rules if isinstance(rule, dict)
    }
    if match:
        fields = metadata_page_state_contract.frontmatter_mapping(
            text, relative)
        semantic_fields = {
            name: value for name, value in fields.items()
            if name not in projected
        }
        body = text[match.end():]
    else:
        # A body-only Markdown page still has semantic content even
        # though there is no page-side projection surface yet.  Its owner
        # state may therefore be bound and invalidated without fabricating a
        # frontmatter block; applicability/write-back remains a separate
        # contract decision.
        semantic_fields = {}
        body = text
    canonical_frontmatter = json.dumps(
        semantic_fields, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"))
    material = (
        SEMANTIC_FINGERPRINT_PROTOCOL + "\0" + relative + "\0" +
        canonical_frontmatter + "\0" + body
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(material).hexdigest()


def _property_states(row, rules, relative):
    state = row.get("property_state")
    if state is None:
        return {}
    if not isinstance(state, dict):
        raise ValueError(
            "Coverage property_state for %s must be a mapping" % relative)
    allowed = {
        rule.get("field") for rule in rules
        if rule.get("source_adapter") in
        metadata_page_state_contract.PROPERTY_VALUE_ADAPTERS
    }
    extra = sorted(set(state) - allowed)
    if extra:
        raise ValueError(
            "Coverage property_state for %s has undeclared field(s): %s" %
            (relative, ", ".join(extra)))
    return state


def project_page(text, row, rules, authorized_owner_removals=()):
    """Return ``(new_text, changes)`` for one page and compiled rule set."""
    match = metadata_page_state_contract.FRONTMATTER.match(text)
    relative = str(row.get("path") or "<page>")
    frontmatter = match.group(2) if match else ""
    fields = metadata_page_state_contract.frontmatter_mapping(
        text, relative) if match else {}
    fingerprint = semantic_content_fingerprint(relative, text, rules)
    property_states = _property_states(row, rules, relative)
    removal_fields = set(authorized_owner_removals)
    changes = []
    for rule in rules:
        name = rule["field"]
        _reconcile_policy(rule, name)
        owner_exists, owner_value = metadata_page_state_contract.owner_value(
            row, rule, relative, fingerprint, property_states)
        if not owner_exists:
            if name in fields:
                if name in removal_fields:
                    if (rule.get("source_adapter") not in
                            metadata_page_state_contract.
                            PROPERTY_VALUE_ADAPTERS or
                            rule.get("invalidation_rule") !=
                            CONTENT_CHANGE_REMOVE_OWNER_RULE):
                        raise ValueError(
                            "page projection removal of %s for %s is not "
                            "authorized by its compiled invalidation rule" %
                            (name, relative))
                    frontmatter = re.sub(
                        r"^%s:.*\n?" % re.escape(name), "", frontmatter,
                        count=1, flags=re.M)
                    changes.append((name, fields[name], None))
                    continue
                raise ValueError(
                    "Coverage row for %s has no evidence-backed owner state "
                    "for persisted %s" % (relative, name))
            continue
        page_value = fields.get(name)
        pattern = metadata_page_state_contract.field_pattern(name)
        found = pattern.search(frontmatter) if name in fields else None
        if name in fields and not found:
            raise ValueError(
                "%s declares top-level %s but its source line cannot be "
                "located" % (relative, name))
        if owner_value is None or owner_value == "":
            if name in fields:
                frontmatter = re.sub(
                    r"^%s:.*\n?" % re.escape(name), "", frontmatter,
                    count=1, flags=re.M)
                changes.append((name, page_value, None))
        elif name not in fields:
            rendered = "%s: %s" % (name, _render_scalar(owner_value))
            frontmatter = (frontmatter + "\n" + rendered
                           if frontmatter else rendered)
            changes.append((name, None, owner_value))
        elif page_value != owner_value:
            frontmatter = pattern.sub(
                "%s: %s" % (name, _render_scalar(owner_value)),
                frontmatter, count=1)
            changes.append((name, page_value, owner_value))
    if not changes:
        return text, []
    if match:
        projected = match.group(1) + frontmatter + match.group(3) + \
            text[match.end():]
    else:
        # A property-state upsert is allowed to materialize the smallest
        # valid frontmatter block.  Existing-copy-only rules still skip
        # absent fields above, so this does not turn ledger row projections
        # into implicit page creation.
        projected = "---\n" + frontmatter + "\n---\n" + text
    metadata_page_state_contract.frontmatter_mapping(projected, relative)
    return projected, changes


def _ledger_rows(document, rules):
    """Load the closed page-path projection needed by this writer."""
    if not isinstance(document, dict):
        raise ValueError("Coverage Ledger must be a mapping")
    pages = document.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Coverage Ledger pages must be an explicit list")
    rows = {}
    for index, row in enumerate(pages):
        label = "Coverage pages[%d]" % index
        if not isinstance(row, dict):
            raise ValueError("%s must be a mapping" % label)
        relative = row.get("path")
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError("%s path must be a non-empty string" % label)
        if relative in rows:
            raise ValueError("Coverage repeats page path %s" % relative)
        _property_states(row, rules, relative)
        rows[relative] = row
    return rows


def _page_snapshot(root, relative):
    """Return one existing or safely-missing canonical Markdown target."""
    return kblib.repository_target_snapshot(
        root, relative, suffixes=".md", singly_linked=True)


def _restored_before_image(before, after):
    """Verify restored inode/bytes while allowing link-driven ctime changes."""
    return (
        before.exists and after.exists and before.dev == after.dev and
        before.ino == after.ino and before.mode == after.mode and
        after.nlink == 1 and before.size == after.size and
        before.mtime_ns == after.mtime_ns and before.data == after.data
    )


def _build_plan(root, selected_pages, ledger_override=None, rules=None,
                authorized_owner_removals=None):
    """Read each authority exactly once and return one validated plan.

    ``ledger_override`` is a proposed complete Coverage mapping.  It lets the
    Integrator derive page after-images from the same proposed owner state it
    is about to transact, without publishing Coverage early.  The live Ledger
    snapshot is still retained in the plan as the compare-and-swap before
    image.
    """
    if (rules is not None and not isinstance(
            rules, metadata_execution_contract.AuthorizedProjectionRules)):
        raise ValueError(
            "explicit projection rules must come from one authorized typed "
            "Profile composition")
    contract_bound = rules is None
    active_rules = tuple(rules if rules is not None else
                         _projection_rules(root))
    if not active_rules:
        raise ValueError("page projection requires at least one compiled rule")
    ledger = metadata_page_state_contract.coverage_ledger_snapshot(root)
    document = (kblib.parse_yaml_subset(ledger.read_text())
                if ledger_override is None else ledger_override)
    rows = _ledger_rows(document, active_rules)
    selected = selected_pages if selected_pages else sorted(rows)
    unknown = [page for page in (selected_pages or []) if page not in rows]
    if unknown:
        raise ValueError("not in the Coverage Ledger: %s" % ", ".join(unknown))
    if len(selected) != len(set(selected)):
        raise ValueError("selected pages must not contain duplicates")

    pages = []
    removals = authorized_owner_removals or {}
    if (not isinstance(removals, dict) or
            any(not isinstance(path, str) or not isinstance(fields, (list, tuple))
                for path, fields in removals.items())):
        raise TypeError(
            "authorized_owner_removals must map page paths to field lists")
    unknown_removal_paths = sorted(set(removals) - set(selected))
    if unknown_removal_paths:
        raise ValueError(
            "authorized owner removals name unselected pages: %s" %
            ", ".join(unknown_removal_paths))
    rules_by_field = {rule.get("field"): rule for rule in active_rules}
    for relative, fields in removals.items():
        if (list(fields) != sorted(set(fields)) or
                any(not isinstance(field, str) or not field
                    for field in fields)):
            raise ValueError(
                "authorized owner removals for %s must be a sorted unique "
                "field list" % relative)
        for field in fields:
            rule = rules_by_field.get(field)
            if (not isinstance(rule, dict) or
                    rule.get("source_adapter") not in
                    metadata_page_state_contract.PROPERTY_VALUE_ADAPTERS or
                    rule.get("invalidation_rule") !=
                    CONTENT_CHANGE_REMOVE_OWNER_RULE):
                raise ValueError(
                    "authorized owner removal %s/%s is outside the compiled "
                    "semantic-content invalidation rules" %
                    (relative, field))
    for relative in selected:
        snapshot = _page_snapshot(root, relative)
        if not snapshot.exists:
            property_states = _property_states(
                rows[relative], active_rules, relative)
            if property_states:
                raise ValueError(
                    "Coverage has current property_state for unmaterialized "
                    "page %s" % relative)
            pages.append(PageProjection(relative, snapshot, None, ()))
            continue
        text = snapshot.read_text()
        new_text, changes = project_page(
            text, rows[relative], active_rules,
            authorized_owner_removals=removals.get(relative, ()))
        after_data = new_text.encode("utf-8")
        if changes:
            # The after-image must pass the same parser before staging.
            metadata_page_state_contract.frontmatter_mapping(
                new_text, relative)
        pages.append(PageProjection(relative, snapshot, after_data, changes))
    return ProjectionPlan(
        ledger, pages, active_rules, revalidate_contract=contract_bound)


def build_projection_plan(root, selected_pages=None, ledger_override=None,
                          rules=None, authorized_owner_removals=None):
    """Public pure planning API for a caller that owns the writer lock.

    This function performs no write and takes no lock.  A state Integrator may
    pass a proposed Coverage mapping and explicit already-authorized rules,
    then stage the returned page after-images inside its broader transaction.
    """
    return _build_plan(
        root, selected_pages, ledger_override=ledger_override, rules=rules,
        authorized_owner_removals=authorized_owner_removals)


def _report_plan(plan, apply):
    planned = 0
    touched = 0
    for page in plan.pages:
        if not page.changed:
            continue
        touched += 1
        planned += len(page.changes)
        for name, before, after in page.changes:
            print("  [%s] %s %s: %r -> %s" %
                  ("PROJECT" if apply else "PLAN", page.relative, name,
                   before, "removed (owner empty)" if after is None
                   else repr(after)))
    return touched, planned


def _open_parent(root, relative):
    """Open a canonical no-follow parent and return ``(fd, basename)``."""
    capability, parent_fd, basename = \
        kblib.open_path_capability_parent(relative, "transaction")
    if capability is not None:
        return parent_fd, basename
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_only = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_only is None:
        raise OSError(errno.ENOTSUP,
                      "safe page projection requires O_NOFOLLOW and "
                      "O_DIRECTORY", relative)
    flags = (os.O_RDONLY | nofollow | directory_only |
             getattr(os, "O_CLOEXEC", 0))
    parent_fd = os.open(os.path.realpath(os.path.abspath(root)), flags)
    try:
        parts = relative.split("/")
        for component in parts[:-1]:
            entries = os.listdir(parent_fd)
            if component not in entries:
                raise OSError(errno.ENOENT, "page parent disappeared", relative)
            listed = os.stat(component, dir_fd=parent_fd,
                             follow_symlinks=False)
            if stat.S_ISLNK(listed.st_mode):
                raise ValueError("page path must not contain a symlink component")
            child = os.open(component, flags, dir_fd=parent_fd)
            opened = os.fstat(child)
            if (not stat.S_ISDIR(opened.st_mode) or
                    (listed.st_dev, listed.st_ino) !=
                    (opened.st_dev, opened.st_ino)):
                os.close(child)
                raise OSError(errno.EAGAIN, "page parent identity changed",
                              relative)
            os.close(parent_fd)
            parent_fd = child
        return parent_fd, parts[-1]
    except Exception:
        os.close(parent_fd)
        raise


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(errno.EIO, "short staged page write")
        view = view[written:]


def _stage_page(root, projection):
    """Durably stage one after-image without rereading its before-image."""
    parent_fd, _basename = _open_parent(root, projection.relative)
    temporary_name = TEMP_PREFIX + "after-" + uuid.uuid4().hex
    backup_name = TEMP_PREFIX + "before-" + uuid.uuid4().hex
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = (os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow |
             getattr(os, "O_CLOEXEC", 0))
    fd = None
    try:
        fd = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
        os.fchmod(fd, stat.S_IMODE(projection.snapshot.mode))
        _write_all(fd, projection.after_data)
        os.fsync(fd)
        descriptor = os.fstat(fd)
        if (not stat.S_ISREG(descriptor.st_mode) or descriptor.st_nlink != 1 or
                descriptor.st_size != len(projection.after_data)):
            raise OSError(errno.EIO, "staged after-image is invalid",
                          projection.relative)
        return StagedProjection(
            projection, parent_fd, temporary_name, backup_name, fd,
            descriptor)
    except Exception:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except OSError:
            pass
        os.close(parent_fd)
        raise


def _read_named_target(parent_fd, basename, relative):
    """Perform the one full final CAS read and retain its descriptor."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise OSError(errno.ENOTSUP, "final page CAS requires O_NOFOLLOW",
                      relative)
    if basename not in os.listdir(parent_fd):
        raise OSError(errno.ENOENT, "page target disappeared", relative)
    fd = os.open(basename, os.O_RDONLY | nofollow |
                 getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("%s must remain a singly-linked regular file" %
                             relative)
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        named = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
        if (path_capability.stat_identity(before) !=
                path_capability.stat_identity(after) or
                (after.st_dev, after.st_ino) != (named.st_dev, named.st_ino)):
            raise OSError(errno.EAGAIN, "page changed during final CAS",
                          relative)
        return fd, after, b"".join(chunks)
    except Exception:
        os.close(fd)
        raise


def _matches_before(snapshot, descriptor, data):
    return (
        snapshot.exists and snapshot.dev == descriptor.st_dev and
        snapshot.ino == descriptor.st_ino and
        snapshot.mode == descriptor.st_mode and
        snapshot.nlink == descriptor.st_nlink and
        snapshot.size == descriptor.st_size and
        snapshot.mtime_ns == getattr(
            descriptor, "st_mtime_ns", int(descriptor.st_mtime * 1e9)) and
        snapshot.ctime_ns == getattr(
            descriptor, "st_ctime_ns", int(descriptor.st_ctime * 1e9)) and
        snapshot.data == data
    )


def _read_exact_descriptor(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _publish_staged(root, staged):
    """Publish one stage while preserving the exact original inode."""
    page = staged.projection
    parent_fd, basename = _open_parent(root, page.relative)
    target_fd = None
    try:
        parent = os.fstat(parent_fd)
        staged_parent = os.fstat(staged.parent_fd)
        if ((parent.st_dev, parent.st_ino) !=
                (staged_parent.st_dev, staged_parent.st_ino) or
                (parent.st_dev, parent.st_ino) !=
                (page.snapshot.parent_dev, page.snapshot.parent_ino)):
            raise OSError(errno.EAGAIN, "page parent changed before publication",
                          page.relative)
        target_fd, descriptor, data = _read_named_target(
            parent_fd, basename, page.relative)
        if not _matches_before(page.snapshot, descriptor, data):
            raise OSError(errno.EAGAIN,
                          "page identity or bytes changed before publication",
                          page.relative)

        # Bind the staged after-image itself before changing the canonical
        # namespace.  Its descriptor has remained open since staging, so a
        # name swap, symlink replacement, or in-place mutation fails here.
        os.lseek(staged.stage_fd, 0, os.SEEK_SET)
        stage_data = []
        while True:
            chunk = os.read(staged.stage_fd, 1024 * 1024)
            if not chunk:
                break
            stage_data.append(chunk)
        stage_descriptor = os.fstat(staged.stage_fd)
        named_stage = os.stat(staged.temporary_name,
                              dir_fd=staged.parent_fd,
                              follow_symlinks=False)
        if (not stat.S_ISREG(named_stage.st_mode) or named_stage.st_nlink != 1 or
                (named_stage.st_dev, named_stage.st_ino) !=
                (staged.stage_dev, staged.stage_ino) or
                (stage_descriptor.st_dev, stage_descriptor.st_ino,
                 stage_descriptor.st_mode) !=
                (staged.stage_dev, staged.stage_ino, staged.stage_mode) or
                b"".join(stage_data) != page.after_data):
            raise OSError(errno.EAGAIN,
                          "staged page identity or bytes changed",
                          page.relative)

        # Re-read the retained target descriptor at the last point before the
        # namespace claim.  This detects same-inode writes that attempted to
        # disguise themselves by restoring size/timestamps after final CAS.
        held_data = _read_exact_descriptor(target_fd)
        held = os.fstat(target_fd)
        named_before_claim = os.stat(
            basename, dir_fd=parent_fd, follow_symlinks=False)
        if (not _matches_before(page.snapshot, held, held_data) or
                (named_before_claim.st_dev, named_before_claim.st_ino) !=
                (held.st_dev, held.st_ino)):
            raise OSError(errno.EAGAIN,
                          "page changed at the publication boundary",
                          page.relative)

        # Hard-linking the validated inode to its pre-registered recovery name
        # is the no-clobber claim.  The canonical name is removed only after
        # both names are proven to identify the held descriptor.
        os.link(basename, staged.backup_name,
                src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                follow_symlinks=False)
        staged.claimed = True
        os.fsync(parent_fd)
        claimed = os.stat(staged.backup_name, dir_fd=parent_fd,
                          follow_symlinks=False)
        held_data = _read_exact_descriptor(target_fd)
        held = os.fstat(target_fd)
        if ((claimed.st_dev, claimed.st_ino) != (held.st_dev, held.st_ino) or
                held.st_mode != descriptor.st_mode or held.st_nlink != 2 or
                held.st_size != descriptor.st_size or
                getattr(held, "st_mtime_ns", int(held.st_mtime * 1e9)) !=
                getattr(descriptor, "st_mtime_ns",
                        int(descriptor.st_mtime * 1e9)) or
                page.snapshot.data != data or page.snapshot.data != held_data):
            raise OSError(errno.EAGAIN,
                          "claimed page differs from validated before-image",
                          page.relative)
        named_before_unlink = os.stat(
            basename, dir_fd=parent_fd, follow_symlinks=False)
        if ((named_before_unlink.st_dev, named_before_unlink.st_ino) !=
                (held.st_dev, held.st_ino)):
            raise OSError(errno.EAGAIN,
                          "canonical page changed during claim",
                          page.relative)
        os.unlink(basename, dir_fd=parent_fd)

        # link(2) is an atomic no-clobber install: if an uncooperative writer
        # creates the basename after our claim, EEXIST preserves its file and
        # leaves the recovery lock plus original inode for reconciliation.
        os.link(staged.temporary_name, basename,
                src_dir_fd=staged.parent_fd, dst_dir_fd=parent_fd,
                follow_symlinks=False)
        # The canonical name now exists and must be treated as published even
        # if the subsequent stage-byte proof rejects it; rollback will then
        # remove only the bound stage inode and restore the original claim.
        staged.published = True
        # The stage name remains linked until the installed canonical name has
        # been proven to be this exact regular inode with the planned bytes.
        stage_data_after_link = _read_exact_descriptor(staged.stage_fd)
        stage_after_link = os.fstat(staged.stage_fd)
        installed = os.stat(basename, dir_fd=parent_fd,
                            follow_symlinks=False)
        if (not stat.S_ISREG(installed.st_mode) or
                (installed.st_dev, installed.st_ino) !=
                (staged.stage_dev, staged.stage_ino) or
                (stage_after_link.st_dev, stage_after_link.st_ino,
                 stage_after_link.st_mode) !=
                (staged.stage_dev, staged.stage_ino, staged.stage_mode) or
                stage_after_link.st_nlink != 2 or
                stage_data_after_link != page.after_data):
            raise OSError(errno.EAGAIN,
                          "installed page differs from staged after-image",
                          page.relative)
        os.unlink(staged.temporary_name, dir_fd=staged.parent_fd)
        staged.temporary_name = None
        os.fsync(parent_fd)
        held_data = _read_exact_descriptor(target_fd)
        held = os.fstat(target_fd)
        if (held.st_dev, held.st_ino) != (page.snapshot.dev,
                                         page.snapshot.ino) or \
                held_data != page.snapshot.data:
            raise OSError(errno.EAGAIN,
                          "rollback image changed during publication",
                          page.relative)
    finally:
        if target_fd is not None:
            os.close(target_fd)
        os.close(parent_fd)


def _restore_staged(root, staged):
    """Restore one claimed original inode without overwriting a new target."""
    if not staged.claimed or staged.backup_name is None:
        return
    parent_fd, basename = _open_parent(root, staged.projection.relative)
    try:
        if staged.published:
            current = kblib.repository_target_snapshot(
                root, staged.projection.relative, suffixes=".md",
                singly_linked=False)
            if (not current.exists or
                    current.dev != staged.stage_dev or
                    current.ino != staged.stage_ino or
                    current.mode != staged.stage_mode or
                    current.data != staged.projection.after_data):
                raise OSError(errno.EAGAIN,
                              "published page identity or bytes changed before "
                              "rollback",
                              staged.projection.relative)
            named = os.stat(basename, dir_fd=parent_fd,
                            follow_symlinks=False)
            if (named.st_dev, named.st_ino) != (current.dev, current.ino):
                raise OSError(errno.EAGAIN,
                              "published page identity changed before rollback",
                              staged.projection.relative)
            # Claim the exact installed inode before removing its canonical
            # name.  A same-path substitution after the snapshot gets EEXIST
            # here or fails the descriptor-bound identity check below.
            rollback_after = TEMP_PREFIX + "rollback-after-" + uuid.uuid4().hex
            os.link(basename, rollback_after,
                    src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                    follow_symlinks=False)
            held_after_fd = os.open(
                rollback_after,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd)
            try:
                held_after = os.fstat(held_after_fd)
                held_after_data = _read_exact_descriptor(held_after_fd)
                named_after = os.stat(basename, dir_fd=parent_fd,
                                      follow_symlinks=False)
                if ((held_after.st_dev, held_after.st_ino) !=
                        (staged.stage_dev, staged.stage_ino) or
                        (named_after.st_dev, named_after.st_ino) !=
                        (held_after.st_dev, held_after.st_ino) or
                        held_after_data != staged.projection.after_data):
                    raise OSError(
                        errno.EAGAIN,
                        "published page identity or bytes changed during "
                        "rollback claim",
                        staged.projection.relative)
                os.unlink(basename, dir_fd=parent_fd)
            finally:
                os.close(held_after_fd)
                try:
                    os.unlink(rollback_after, dir_fd=parent_fd)
                except OSError:
                    pass
            staged.published = False
            if staged.temporary_name is not None:
                named_stage = os.stat(staged.temporary_name,
                                      dir_fd=staged.parent_fd,
                                      follow_symlinks=False)
                if (named_stage.st_dev, named_stage.st_ino) != \
                        (staged.stage_dev, staged.stage_ino):
                    raise OSError(
                        errno.EAGAIN,
                        "staged recovery name changed before rollback",
                        staged.projection.relative)
                os.unlink(staged.temporary_name, dir_fd=staged.parent_fd)
                staged.temporary_name = None

        # Atomic no-clobber restoration.  A foreign replacement keeps the
        # original backup and recovery lock instead of being overwritten.
        backup_fd = os.open(
            staged.backup_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
            getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd)
        try:
            backup_data = _read_exact_descriptor(backup_fd)
            backup_descriptor = os.fstat(backup_fd)
            named_backup = os.stat(staged.backup_name, dir_fd=parent_fd,
                                   follow_symlinks=False)
            if ((backup_descriptor.st_dev, backup_descriptor.st_ino) !=
                    (staged.projection.snapshot.dev,
                     staged.projection.snapshot.ino) or
                    (named_backup.st_dev, named_backup.st_ino) !=
                    (backup_descriptor.st_dev, backup_descriptor.st_ino) or
                    backup_data != staged.projection.snapshot.data):
                raise OSError(errno.EAGAIN,
                              "rollback image changed before restoration",
                              staged.projection.relative)
        finally:
            os.close(backup_fd)
        os.link(staged.backup_name, basename,
                src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                follow_symlinks=False)
        os.unlink(staged.backup_name, dir_fd=parent_fd)
        staged.backup_name = None
        staged.claimed = False
        os.fsync(parent_fd)
        restored = kblib.repository_target_snapshot(
            root, staged.projection.relative, suffixes=".md",
            singly_linked=True)
        if not _restored_before_image(staged.projection.snapshot, restored):
            raise OSError(errno.EIO, "page before-image was not restored",
                          staged.projection.relative)
    finally:
        os.close(parent_fd)


def _cleanup_stage(staged, remove_backup=False, close_parent=True):
    failures = []
    if staged.temporary_name is not None:
        try:
            os.unlink(staged.temporary_name, dir_fd=staged.parent_fd)
            staged.temporary_name = None
        except FileNotFoundError:
            staged.temporary_name = None
        except OSError as exc:
            failures.append("%s staged after-image: %s" %
                            (staged.projection.relative, exc))
    if remove_backup and staged.backup_name is not None:
        try:
            os.unlink(staged.backup_name, dir_fd=staged.parent_fd)
            staged.backup_name = None
            staged.claimed = False
        except FileNotFoundError:
            staged.backup_name = None
            staged.claimed = False
        except OSError as exc:
            failures.append("%s rollback image: %s" %
                            (staged.projection.relative, exc))
    if staged.stage_fd is not None:
        try:
            os.close(staged.stage_fd)
            staged.stage_fd = None
        except OSError as exc:
            failures.append("%s staged descriptor: %s" %
                            (staged.projection.relative, exc))
    if close_parent:
        try:
            os.fsync(staged.parent_fd)
        except OSError as exc:
            failures.append("%s parent fsync: %s" %
                            (staged.projection.relative, exc))
        try:
            os.close(staged.parent_fd)
        except OSError as exc:
            failures.append("%s parent close: %s" %
                            (staged.projection.relative, exc))
    return failures


def _snapshot_evidence(snapshot):
    if snapshot.exists:
        return {
            "exists": True, "sha256": snapshot.sha256,
            "device": snapshot.dev, "inode": snapshot.ino,
        }
    return {
        "exists": False,
        "missing_components": list(snapshot.missing_components),
        "parent": snapshot.parent_repository_path,
        "parent_device": snapshot.parent_dev,
        "parent_inode": snapshot.parent_ino,
    }


def _operation_evidence(transaction_id, plan, status):
    return {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "action": "apply-page-state-projection",
        "transaction_id": transaction_id,
        "status": status,
        "metadata_execution_rule_fingerprint":
            plan.contract_rule_fingerprint,
        "coverage_ledger": {
            "path": metadata_page_state_contract.COVERAGE_LEDGER_PATH,
            "before": _snapshot_evidence(plan.ledger),
        },
        "pages": [
            {
                "path": page.relative,
                "before": _snapshot_evidence(page.snapshot),
                "after": ({"sha256": kblib.sha256_bytes(page.after_data)}
                          if page.after_data is not None else
                          {"exists": False}),
                "changed": page.changed,
            }
            for page in plan.pages
        ],
    }


def _refresh_artifact_evidence(operation, staged):
    """Bind each temporary/rollback inode name to its canonical page."""
    operation["artifacts"] = [
        _staged_artifact_descriptor(item) for item in staged
    ]


def _write_recovery_evidence(lease, operation):
    """Durably update lock ownership and the transaction journal."""
    lock_path = os.fspath(lease)
    owner_path = os.path.join(lock_path, "owner.json")
    with open(owner_path, encoding="utf-8") as handle:
        owner = json.load(handle)
    outer = owner.get("operation")
    if (isinstance(outer, dict) and
            outer.get("tool") != TOOL and
            operation.get("tool") == TOOL):
        # A composite Integrator owns the lock and the state transaction.
        # Preserve its recovery identity and nest this page subtransaction;
        # replacing the outer operation would orphan Coverage/Queue rollback
        # evidence the moment page staging begins.
        outer = dict(outer)
        outer["page_projection_transaction"] = operation
        owner["operation"] = outer
    else:
        owner["operation"] = operation
    kblib.atomic_write_text(
        owner_path, json.dumps(owner, sort_keys=True) + "\n",
        validator=json.loads)
    kblib.atomic_write_text(
        os.path.join(lock_path, JOURNAL_NAME),
        json.dumps(operation, sort_keys=True) + "\n",
        validator=json.loads)


def _remove_recovery_journal(lease):
    path = os.path.join(os.fspath(lease), JOURNAL_NAME)
    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    fd = os.open(os.fspath(lease), os.O_RDONLY |
                 getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _revalidate_plan_inputs(root, plan, include_ledger=True):
    if plan.revalidate_contract:
        current_rules = _projection_rules(root)
        current_fingerprint = metadata_page_state_contract.rules_fingerprint(
            current_rules)
        if current_fingerprint != plan.contract_rule_fingerprint:
            raise OSError(
                errno.EAGAIN,
                "metadata execution contract changed during projection")
    if include_ledger:
        current_ledger = \
            metadata_page_state_contract.coverage_ledger_snapshot(root)
        if not repository.same_existing_target_snapshot(
                plan.ledger, current_ledger):
            raise OSError(errno.EAGAIN,
                          "Coverage Ledger changed during projection",
                          metadata_page_state_contract.COVERAGE_LEDGER_PATH)
    for page in plan.pages:
        if page.snapshot.exists:
            continue
        current = _page_snapshot(root, page.relative)
        if not repository.same_missing_target_snapshot(
                page.snapshot, current):
            raise OSError(errno.EAGAIN,
                          "unmaterialized page changed during projection",
                          page.relative)


def _verify_published_after_image(root, staged):
    """Prove one live page still belongs exactly to this transaction."""
    if not staged.published:
        raise ValueError(
            "%s has not been published" % staged.projection.relative)
    parent_fd, basename = _open_parent(root, staged.projection.relative)
    try:
        named = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
        stage_data = _read_exact_descriptor(staged.stage_fd)
        descriptor = os.fstat(staged.stage_fd)
        if (not stat.S_ISREG(named.st_mode) or named.st_nlink != 1 or
                (named.st_dev, named.st_ino, named.st_mode) !=
                (staged.stage_dev, staged.stage_ino, staged.stage_mode) or
                (descriptor.st_dev, descriptor.st_ino,
                 descriptor.st_mode) !=
                (staged.stage_dev, staged.stage_ino, staged.stage_mode) or
                descriptor.st_nlink != 1 or
                stage_data != staged.projection.after_data):
            raise OSError(
                errno.EAGAIN,
                "published page no longer matches the transaction after-image",
                staged.projection.relative)
    finally:
        os.close(parent_fd)


class ProjectionTransaction:
    """Prepared page subtransaction owned by an outer writer lock.

    ``publish`` deliberately retains every original inode.  The outer
    Integrator may therefore write/validate Coverage, Queue and receipts in
    one recovery window, then call ``commit`` to discard the page backups or
    ``rollback`` to restore them.  This object never acquires the lock and
    never marks it reconciled; the outer transaction owns that decision.
    """

    __slots__ = (
        "root", "plan", "lease", "transaction_id", "staged",
        "operation", "state",
    )

    def __init__(self, root, plan, lease, transaction_id, staged, operation):
        self.root = root
        self.plan = plan
        self.lease = lease
        self.transaction_id = transaction_id
        self.staged = staged
        self.operation = operation
        self.state = "staged"

    def _record(self, status):
        self.operation["status"] = status
        self.operation["published"] = [
            item.projection.relative for item in self.staged
            if item.published
        ]
        _refresh_artifact_evidence(self.operation, self.staged)
        _write_recovery_evidence(self.lease, self.operation)

    def publish(self):
        """Publish all page after-images, retaining rollback images.

        The live Ledger may already be the outer transaction's proposed
        after-image, so this phase revalidates the contract and page namespace
        but leaves owner-state revalidation to that outer transaction.
        """
        if self.state != "staged":
            raise ValueError(
                "projection transaction cannot publish from %s" % self.state)
        try:
            _revalidate_plan_inputs(
                self.root, self.plan, include_ledger=False)
            self.state = "publishing"
            for item in self.staged:
                _publish_staged(self.root, item)
                self._record("publishing")
            _revalidate_plan_inputs(
                self.root, self.plan, include_ledger=False)
            self.state = "published"
            self._record("published-awaiting-outer-commit")
        except Exception as exc:
            self.state = "publish-failed"
            self.operation["failure"] = str(exc)
            try:
                self._record("rollback-required")
            except Exception as evidence_error:
                self.operation["recovery_evidence_failure"] = str(
                    evidence_error)
            raise

    def rollback(self):
        """Restore exact page before-images; never mark the outer lock clean."""
        if self.state in (
                "rolled-back", "committed", "commit-cleanup-failed"):
            raise ValueError(
                "projection transaction cannot rollback from %s" % self.state)
        failures = []
        claimed_ids = set()
        for item in reversed(self.staged):
            if not item.claimed:
                continue
            claimed_ids.add(id(item))
            try:
                _restore_staged(self.root, item)
            except Exception as exc:
                failures.append(
                    "%s: %s" % (item.projection.relative, exc))
            finally:
                failures.extend(_cleanup_stage(
                    item, remove_backup=not item.claimed,
                    close_parent=True))
        for item in self.staged:
            if id(item) in claimed_ids:
                continue
            failures.extend(_cleanup_stage(
                item, remove_backup=False, close_parent=True))
        if failures:
            self.state = "rollback-failed"
            self.operation["rollback_failures"] = failures
            try:
                self._record("rollback-required")
            except Exception as evidence_error:
                failures.append("recovery evidence: %s" % evidence_error)
            raise ValueError(
                "page projection rollback is incomplete: %s" %
                "; ".join(failures))
        _remove_recovery_journal(self.lease)
        self.state = "rolled-back"

    def commit(self):
        """Prove all after-images, then discard retained rollback images."""
        if self.state != "published":
            raise ValueError(
                "projection transaction cannot commit from %s" % self.state)
        try:
            _revalidate_plan_inputs(
                self.root, self.plan, include_ledger=False)
            for item in self.staged:
                _verify_published_after_image(self.root, item)
        except Exception as exc:
            self.operation["failure"] = str(exc)
            self._record("rollback-required")
            raise
        self._record("committed-cleanup")
        failures = []
        for item in self.staged:
            failures.extend(_cleanup_stage(item, remove_backup=True))
        if failures:
            self.state = "commit-cleanup-failed"
            self.operation["cleanup_failures"] = failures
            self._record("committed-cleanup-required")
            raise ValueError(
                "page projection committed but cleanup is incomplete: %s" %
                "; ".join(failures))
        _remove_recovery_journal(self.lease)
        self.state = "committed"


def stage_projection_plan(root, plan, lease, transaction_id=None):
    """Stage a plan under an existing lease and return its transaction."""
    transaction_id = transaction_id or (
        "page-state-" + uuid.uuid4().hex)
    journal_path = os.path.join(os.fspath(lease), JOURNAL_NAME)
    if os.path.lexists(journal_path):
        raise ValueError(
            "page projection recovery journal already exists")
    changed = [page for page in plan.pages if page.changed]
    staged = []
    operation = _operation_evidence(
        transaction_id, plan, "planned")
    try:
        _write_recovery_evidence(lease, operation)
        for page in changed:
            staged.append(_stage_page(root, page))
            operation["status"] = "staging"
            _refresh_artifact_evidence(operation, staged)
            _write_recovery_evidence(lease, operation)
        _revalidate_plan_inputs(root, plan, include_ledger=True)
        operation["status"] = "staged"
        _refresh_artifact_evidence(operation, staged)
        _write_recovery_evidence(lease, operation)
        return ProjectionTransaction(
            root, plan, lease, transaction_id, staged, operation)
    except Exception as original:
        failures = []
        for item in staged:
            failures.extend(_cleanup_stage(
                item, remove_backup=False, close_parent=True))
        if failures:
            operation["status"] = "rollback-required"
            operation["failure"] = str(original)
            operation["rollback_failures"] = failures
            _refresh_artifact_evidence(operation, staged)
            try:
                _write_recovery_evidence(lease, operation)
            except Exception as evidence_error:
                failures.append("recovery evidence: %s" % evidence_error)
            raise ValueError(
                "page projection staging failed and cleanup is incomplete: "
                "%s; %s" % (original, "; ".join(failures)))
        try:
            _remove_recovery_journal(lease)
        except Exception as cleanup_error:
            operation["status"] = "rollback-required"
            operation["failure"] = str(original)
            operation["rollback_failures"] = [
                "journal cleanup: %s" % cleanup_error]
            _write_recovery_evidence(lease, operation)
            raise ValueError(
                "page projection staging failed and journal cleanup is "
                "incomplete: %s; %s" % (original, cleanup_error))
        raise


def _apply_plan(root, plan, lease, transaction_id):
    """CLI wrapper over the same subtransaction the Integrator composes."""
    transaction = None
    try:
        transaction = stage_projection_plan(
            root, plan, lease, transaction_id)
        transaction.publish()
        # Standalone projection keeps Coverage unchanged.  Re-prove that owner
        # snapshot after page publication and before the commit point; the
        # composite Integrator performs this check inside its broader state
        # validation instead.
        _revalidate_plan_inputs(root, plan, include_ledger=True)
        transaction.commit()
    except Exception as original:
        if transaction is None:
            # Staging removes its journal only after proving that every staged
            # artifact was cleaned.  Absence therefore authorizes the outer
            # lock cleanup; presence deliberately retains recovery state.
            if not os.path.exists(os.path.join(
                    os.fspath(lease), JOURNAL_NAME)):
                lease.mark_reconciled()
            raise
        if transaction.state == "commit-cleanup-failed":
            raise ValueError(
                "projection committed but recovery cleanup is incomplete: "
                "%s; inspect journal" % original)
        try:
            transaction.rollback()
        except Exception as rollback_error:
            raise ValueError(
                "projection failed and rollback is incomplete: %s; %s" %
                (original, rollback_error)) from original
        lease.mark_reconciled()
        raise


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Project metadata-contract owner state onto page "
                    "frontmatter")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--page", action="append", default=None,
                        help="limit to these repository-relative pages "
                             "(repeatable); default is every Ledger page")
    parser.add_argument("--apply", action="store_true",
                        help="take the runtime writer lock and publish the "
                             "projection; omit for a dry run")
    args = parser.parse_args(argv)
    root = os.path.realpath(os.path.abspath(args.root))

    if not args.apply:
        try:
            plan = _build_plan(root, args.page)
            touched, planned = _report_plan(plan, False)
        except (OSError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            print("[FAIL] page-state projection input is unsafe or invalid: %s" %
                  exc)
            return 1
        print("%s: pages=%d field_changes=%d (dry run; add --apply)" %
              (TOOL, touched, planned))
        return 0

    transaction_id = "page-state-" + uuid.uuid4().hex
    owner_metadata = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "action": "apply-page-state-projection",
        "transaction_id": transaction_id,
    }
    try:
        with kblib.runtime_write_lock(
                root, owner_metadata=owner_metadata) as lease:
            try:
                plan = _build_plan(root, args.page)
                touched, planned = _report_plan(plan, True)
                _apply_plan(root, plan, lease, transaction_id)
            except Exception:
                # _apply_plan owns reconciliation after evidence exists.  A
                # plan/report failure happens before any authoritative write.
                if not os.path.exists(os.path.join(
                        os.fspath(lease), JOURNAL_NAME)):
                    lease.mark_reconciled()
                raise
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError,
            kblib.RuntimeStateLockedError) as exc:
        print("[FAIL] page-state projection input is unsafe or invalid, or "
              "the write was rejected; restoration attempted: %s" % exc)
        return 1
    print("%s: pages=%d field_changes=%d" % (TOOL, touched, planned))
    return 0


if __name__ == "__main__":
    sys.exit(main())
