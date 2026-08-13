#!/usr/bin/env python3
"""Project Ledger-owned state fields onto page frontmatter (K08/07).

The Coverage Ledger owns ``coverage_disposition``, ``authoring_status`` and
``next_batch``.  Pages may carry those fields only as tool-written copies.

Dry runs build an immutable projection plan without taking the runtime writer
lock.  ``--apply`` builds that plan once while holding the shared writer lock,
stages every changed after-image, performs one exact final identity-and-bytes
descriptor open per changed page, and then publishes the batch.  Original page
inodes are retained as rollback images until the whole batch and its Ledger
binding have been revalidated.  Cooperating writers share the lock; unexpected
namespace drift still fails closed.  A fully restored failure clears the lock,
while an unproven rollback deliberately keeps its recovery journal.
"""

import argparse
import errno
import json
import os
import re
import stat
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "project_page_state"
TOOL_VERSION = "1.1.0"
COVERAGE_LEDGER_PATH = ".cambium/state/coverage_ledger.yaml"
PROJECTION_FIELDS = ("coverage_disposition", "authoring_status", "next_batch")
FRONTMATTER = re.compile(r"^(---\n)(.*?)(\n---\n)", re.S)
TEMP_PREFIX = ".cambium-page-state-"
JOURNAL_NAME = "page-state-transaction.json"


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

    __slots__ = ("ledger", "pages")

    def __init__(self, ledger, pages):
        self.ledger = ledger
        self.pages = tuple(pages)


class StagedProjection:
    """A staged after-image plus its exact original-inode rollback claim."""

    __slots__ = (
        "projection", "parent_fd", "temporary_name", "backup_name",
        "stage_artifact_name", "rollback_artifact_name", "stage_fd",
        "stage_dev", "stage_ino", "stage_mode", "claimed", "published",
        "after_image_verified", "published_size", "published_mtime_ns",
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
        self.after_image_verified = False
        self.published_size = None
        self.published_mtime_ns = None


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
        "after_image_verified": staged.after_image_verified,
        "published_size": staged.published_size,
        "published_mtime_ns": staged.published_mtime_ns,
    }


def _field_pattern(name):
    return re.compile(r"^%s:[ \t]*(.*)$" % re.escape(name), re.M)


def _frontmatter_mapping(text, relative):
    """Return one page's restricted-YAML frontmatter mapping."""
    raw = kblib.extract_frontmatter(text)
    if raw is None:
        raise ValueError("%s has no complete fenced frontmatter" % relative)
    fields = kblib.parse_yaml_subset(raw)
    if not isinstance(fields, dict):
        raise ValueError("%s frontmatter must be a mapping" % relative)
    return fields


def _render_scalar(value):
    """Render one scalar through the shared restricted-YAML serializer."""
    rendered = kblib.canonical_yaml({"value": value})
    return rendered[len("value: "):].rstrip("\n")


def project_page(text, row):
    """Return ``(new_text, changes)`` for one page against its Ledger row."""
    match = FRONTMATTER.match(text)
    if not match:
        return text, []
    frontmatter = match.group(2)
    fields = _frontmatter_mapping(text, str(row.get("path") or "<page>"))
    changes = []
    for name in PROJECTION_FIELDS:
        if name not in fields:
            continue
        pattern = _field_pattern(name)
        found = pattern.search(frontmatter)
        if not found:
            raise ValueError(
                "%s declares top-level %s but its source line cannot be "
                "located" % (row.get("path") or "<page>", name)
            )
        page_value = fields[name]
        owner_value = row.get(name)
        if owner_value is None or owner_value == "":
            frontmatter = re.sub(
                r"^%s:.*\n?" % re.escape(name), "", frontmatter, count=1,
                flags=re.M)
            changes.append((name, page_value, None))
        elif not isinstance(owner_value, str):
            raise ValueError(
                "Coverage %s for %s must be null or a string" %
                (name, row.get("path") or "<page>")
            )
        elif page_value != owner_value:
            frontmatter = pattern.sub(
                "%s: %s" % (name, _render_scalar(owner_value)),
                frontmatter, count=1)
            changes.append((name, page_value, owner_value))
    if not changes:
        return text, []
    projected = match.group(1) + frontmatter + match.group(3) + \
        text[match.end():]
    _frontmatter_mapping(projected, str(row.get("path") or "<page>"))
    return projected, changes


def _ledger_rows(snapshot):
    """Load the closed page-path projection needed by this writer."""
    ledger = kblib.parse_yaml_subset(snapshot.read_text())
    if not isinstance(ledger, dict):
        raise ValueError("Coverage Ledger must be a mapping")
    pages = ledger.get("pages")
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
        rows[relative] = row
    return rows


def _ledger_snapshot(root):
    snapshot = kblib.repository_target_snapshot(
        root, COVERAGE_LEDGER_PATH, suffixes=".yaml", singly_linked=True)
    if not snapshot.exists:
        raise ValueError("Coverage Ledger does not exist")
    return snapshot


def _page_snapshot(root, relative):
    """Return one existing or safely-missing canonical Markdown target."""
    return kblib.repository_target_snapshot(
        root, relative, suffixes=".md", singly_linked=True)


def _same_target(before, after):
    """Compare both namespace identity and exact bytes of two snapshots."""
    if before.exists != after.exists:
        return False
    if not before.exists:
        return (
            before.missing_components == after.missing_components and
            before.parent_repository_path == after.parent_repository_path and
            before.parent_dev == after.parent_dev and
            before.parent_ino == after.parent_ino
        )
    return (
        before.dev == after.dev and before.ino == after.ino and
        before.mode == after.mode and before.nlink == after.nlink and
        before.size == after.size and before.mtime_ns == after.mtime_ns and
        before.ctime_ns == after.ctime_ns and before.data == after.data
    )


def _restored_before_image(before, after):
    """Verify restored inode/bytes while allowing link-driven ctime changes."""
    return (
        before.exists and after.exists and before.dev == after.dev and
        before.ino == after.ino and before.mode == after.mode and
        after.nlink == 1 and before.size == after.size and
        before.mtime_ns == after.mtime_ns and before.data == after.data
    )


def _build_plan(root, selected_pages):
    """Read each authority exactly once and return one validated plan."""
    ledger = _ledger_snapshot(root)
    rows = _ledger_rows(ledger)
    selected = selected_pages if selected_pages else sorted(rows)
    unknown = [page for page in (selected_pages or []) if page not in rows]
    if unknown:
        raise ValueError("not in the Coverage Ledger: %s" % ", ".join(unknown))
    if len(selected) != len(set(selected)):
        raise ValueError("selected pages must not contain duplicates")

    pages = []
    for relative in selected:
        snapshot = _page_snapshot(root, relative)
        if not snapshot.exists:
            pages.append(PageProjection(relative, snapshot, None, ()))
            continue
        text = snapshot.read_text()
        new_text, changes = project_page(text, rows[relative])
        after_data = new_text.encode("utf-8")
        if changes:
            # The after-image must pass the same parser before staging.
            _frontmatter_mapping(new_text, relative)
        pages.append(PageProjection(relative, snapshot, after_data, changes))
    return ProjectionPlan(ledger, pages)


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


def _stat_identity(descriptor):
    return (
        descriptor.st_dev, descriptor.st_ino, descriptor.st_mode,
        descriptor.st_nlink, descriptor.st_size,
        getattr(descriptor, "st_mtime_ns",
                int(descriptor.st_mtime * 1e9)),
        getattr(descriptor, "st_ctime_ns",
                int(descriptor.st_ctime * 1e9)),
    )


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
        if (_stat_identity(before) != _stat_identity(after) or
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
        os.unlink(staged.stage_artifact_name, dir_fd=staged.parent_fd)
        # The installed name has been verified once as the exact planned
        # after-image and its staging alias is gone.  From this point onward a
        # byte change can only be a later writer, so rollback must preserve it
        # rather than treating it as corruption of an unpublished stage.
        staged.temporary_name = None
        os.fsync(parent_fd)
        verified_after = os.fstat(staged.stage_fd)
        named_verified_after = os.stat(
            basename, dir_fd=parent_fd, follow_symlinks=False)
        if ((verified_after.st_dev, verified_after.st_ino) !=
                (staged.stage_dev, staged.stage_ino) or
                (named_verified_after.st_dev, named_verified_after.st_ino) !=
                (verified_after.st_dev, verified_after.st_ino) or
                verified_after.st_nlink != 1 or
                _read_exact_descriptor(staged.stage_fd) != page.after_data):
            raise OSError(errno.EAGAIN,
                          "installed page changed after publication",
                          page.relative)
        # Closing the staging link changes ctime once more.  Capture the stable
        # single-name identity only after that descriptor is closed.
        os.close(staged.stage_fd)
        staged.stage_fd = None
        verified_after = os.stat(
            basename, dir_fd=parent_fd, follow_symlinks=False)
        staged.published_size = verified_after.st_size
        staged.published_mtime_ns = getattr(
            verified_after, "st_mtime_ns",
            int(verified_after.st_mtime * 1e9))
        staged.after_image_verified = True
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
            publication_complete = staged.after_image_verified
            current = kblib.repository_target_snapshot(
                root, staged.projection.relative, suffixes=".md",
                singly_linked=False)
            if (not current.exists or
                    current.dev != staged.stage_dev or
                    current.ino != staged.stage_ino or
                    current.mode != staged.stage_mode or
                    (publication_complete and current.nlink != 1) or
                    (not publication_complete and current.nlink not in (1, 2))):
                raise OSError(errno.EAGAIN,
                              "published page identity changed before rollback",
                              staged.projection.relative)
            if (publication_complete and
                    (current.size != staged.published_size or
                     current.mtime_ns != staged.published_mtime_ns or
                     current.data != staged.projection.after_data)):
                raise OSError(
                    errno.EAGAIN,
                    "published page bytes changed before rollback; "
                    "preserving the concurrent page and recovery evidence",
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
                named_after = os.stat(basename, dir_fd=parent_fd,
                                      follow_symlinks=False)
                identity_changed = (
                    (held_after.st_dev, held_after.st_ino) !=
                    (staged.stage_dev, staged.stage_ino) or
                    (named_after.st_dev, named_after.st_ino) !=
                    (held_after.st_dev, held_after.st_ino) or
                    held_after.st_mode != staged.stage_mode or
                    (publication_complete and
                     held_after.st_size != staged.published_size) or
                    (publication_complete and getattr(
                        held_after, "st_mtime_ns",
                        int(held_after.st_mtime * 1e9)) !=
                     staged.published_mtime_ns) or
                    (publication_complete and held_after.st_nlink != 2) or
                    (not publication_complete and held_after.st_nlink not in
                     (2, 3))
                )
                if identity_changed:
                    raise OSError(
                        errno.EAGAIN,
                        "published page identity changed before rollback",
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
        "coverage_ledger": {
            "path": COVERAGE_LEDGER_PATH,
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


def _revalidate_plan_inputs(root, plan):
    current_ledger = _ledger_snapshot(root)
    if not _same_target(plan.ledger, current_ledger):
        raise OSError(errno.EAGAIN,
                      "Coverage Ledger changed during projection",
                      COVERAGE_LEDGER_PATH)
    for page in plan.pages:
        if page.snapshot.exists:
            continue
        current = _page_snapshot(root, page.relative)
        if not _same_target(page.snapshot, current):
            raise OSError(errno.EAGAIN,
                          "unmaterialized page changed during projection",
                          page.relative)


def _publish_page(root, relative, snapshot, new_text):
    """Compatibility helper: stage, exact-CAS publish, then discard rollback."""
    projection = PageProjection(relative, snapshot,
                                new_text.encode("utf-8"), (("page", None, None),))
    staged = _stage_page(root, projection)
    try:
        _publish_staged(root, staged)
        cleanup = _cleanup_stage(staged, remove_backup=True)
        if cleanup:
            raise OSError(errno.EIO, "; ".join(cleanup), relative)
    except Exception:
        try:
            _restore_staged(root, staged)
        except Exception:
            pass
        _cleanup_stage(staged, remove_backup=False)
        raise


def _apply_plan(root, plan, lease, transaction_id):
    changed = [page for page in plan.pages if page.changed]
    staged = []
    publication_started = False
    committed = False
    operation = _operation_evidence(transaction_id, plan, "planned")
    try:
        _write_recovery_evidence(lease, operation)
        for page in changed:
            staged.append(_stage_page(root, page))
            # Persist each random artifact name before staging the next page.
            # A hard exit can therefore always map every durable temporary
            # inode that already exists back to its canonical page.
            operation["status"] = "staging"
            _refresh_artifact_evidence(operation, staged)
            _write_recovery_evidence(lease, operation)
        _revalidate_plan_inputs(root, plan)
        operation["status"] = "staged"
        _refresh_artifact_evidence(operation, staged)
        _write_recovery_evidence(lease, operation)

        for item in staged:
            publication_started = True
            _publish_staged(root, item)
            operation["status"] = "publishing"
            operation["published"] = [
                candidate.projection.relative for candidate in staged
                if candidate.published
            ]
            _refresh_artifact_evidence(operation, staged)
            _write_recovery_evidence(lease, operation)

        # A late Ledger or safely-missing target change invalidates the whole
        # projection and enters the same exact rollback path.
        _revalidate_plan_inputs(root, plan)
        operation["status"] = "committed-cleanup"
        _refresh_artifact_evidence(operation, staged)
        _write_recovery_evidence(lease, operation)
        committed = True
        cleanup_failures = []
        for item in staged:
            cleanup_failures.extend(_cleanup_stage(item, remove_backup=True))
        if cleanup_failures:
            raise OSError(errno.EIO, "; ".join(cleanup_failures))
        _remove_recovery_journal(lease)
        return
    except Exception as original:
        rollback_failures = []
        claimed = [item for item in staged if item.claimed]
        if publication_started and not committed:
            for item in reversed(claimed):
                if not item.claimed:
                    continue
                try:
                    _restore_staged(root, item)
                except Exception as exc:
                    rollback_failures.append(
                        "%s: %s" % (item.projection.relative, exc))
                finally:
                    rollback_failures.extend(_cleanup_stage(
                        item, remove_backup=not item.claimed,
                        close_parent=True))
        if not committed:
            claimed_ids = {id(item) for item in claimed}
            for item in staged:
                if id(item) in claimed_ids:
                    continue
                rollback_failures.extend(_cleanup_stage(
                    item, remove_backup=False))

        if committed:
            operation["status"] = "committed-cleanup-required"
            operation["failure"] = str(original)
            operation["cleanup_failures"] = rollback_failures
            try:
                _write_recovery_evidence(lease, operation)
            except Exception as evidence_error:
                rollback_failures.append(
                    "recovery evidence: %s" % evidence_error)
            raise ValueError(
                "projection committed but recovery cleanup is incomplete: "
                "%s; %s" %
                (original, "; ".join(rollback_failures) or "inspect journal"))

        if not rollback_failures:
            try:
                _remove_recovery_journal(lease)
            except Exception as exc:
                rollback_failures.append("journal cleanup: %s" % exc)
        if not rollback_failures:
            lease.mark_reconciled()
            raise

        operation["status"] = "rollback-required"
        operation["failure"] = str(original)
        operation["rollback_failures"] = rollback_failures
        _refresh_artifact_evidence(operation, staged)
        try:
            _write_recovery_evidence(lease, operation)
        except Exception as evidence_error:
            rollback_failures.append("recovery evidence: %s" % evidence_error)
        raise ValueError(
            "projection failed and rollback is incomplete: %s; %s" %
            (original, "; ".join(rollback_failures)))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Project Ledger-owned state onto page frontmatter")
    parser.add_argument("root")
    parser.add_argument("--page", action="append", default=None,
                        help="limit to these repository-relative pages "
                             "(repeatable); default is every Ledger page")
    parser.add_argument("--apply", action="store_true")
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
