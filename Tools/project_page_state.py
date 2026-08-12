#!/usr/bin/env python3
"""Project Ledger-owned state fields onto page frontmatter (K08/07).

The Coverage Ledger owns ``coverage_disposition``, ``authoring_status`` and
``next_batch``.  A page MAY carry a copy of any of them, but only as a
tool-written projection.  This projector makes that sentence executable: for
every Ledger page whose file exists, each projection field already present in
the page's frontmatter is rewritten to the owner value, and removed when the
owner value is empty.  A field the page does not carry is never added --
whether to persist a projection stays a page-level choice.

The default is a dry run that prints the plan.  ``--apply`` validates every
selected path and planned after-image before it changes any page, then writes
with the same re-parse-then-atomic-write discipline K08/07 requires of every
writer.
"""

import argparse
import errno
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
    """Return (new_text, changes) for one page against its Ledger row."""
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


def _page_snapshot(root, relative):
    """Return stable bytes for one materialized canonical Markdown page.

    Coverage may inventory a prospective page that has not been materialized
    yet.  Such a row remains a no-op, but its spelling still passes through
    the repository-containment primitive before absence is accepted.
    """
    if not relative.lower().endswith(".md"):
        raise ValueError("page path must end with .md: %s" % relative)
    absolute = kblib.repository_path(
        root, relative, must_exist=False, reject_symlink=True)
    if not os.path.lexists(absolute):
        return None
    return kblib.repository_file_snapshot(
        root, relative, singly_linked=True)


def _publish_page(root, relative, snapshot, new_text):
    """Replace one already-validated page through its no-follow parent fd."""
    parent_parts = relative.split("/")[:-1]
    basename = relative.split("/")[-1]
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_only = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_only is None:
        raise OSError(errno.ENOTSUP,
                      "safe page projection requires O_NOFOLLOW and "
                      "O_DIRECTORY", relative)
    flags = os.O_RDONLY | nofollow | directory_only | \
        getattr(os, "O_CLOEXEC", 0)
    parent_fd = os.open(root, flags)
    temporary_name = None
    opened_fd = None
    try:
        for component in parent_parts:
            child_fd = os.open(component, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
        target_fd = os.open(
            basename, os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd)
        try:
            before = os.fstat(target_fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError(
                    "%s must remain a singly-linked regular file" % relative)
            chunks = []
            while True:
                chunk = os.read(target_fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(target_fd)
            before_identity = (
                before.st_dev, before.st_ino, before.st_size,
                getattr(before, "st_mtime_ns", int(before.st_mtime * 1e9)),
                getattr(before, "st_ctime_ns", int(before.st_ctime * 1e9)),
            )
            after_identity = (
                after.st_dev, after.st_ino, after.st_size,
                getattr(after, "st_mtime_ns", int(after.st_mtime * 1e9)),
                getattr(after, "st_ctime_ns", int(after.st_ctime * 1e9)),
            )
            if before_identity != after_identity or \
                    b"".join(chunks) != snapshot.data:
                raise OSError(errno.EAGAIN,
                              "page identity changed before publication",
                              relative)
        finally:
            os.close(target_fd)

        temporary_name = ".cambium-page-state-%s" % uuid.uuid4().hex
        create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow | \
            getattr(os, "O_CLOEXEC", 0)
        opened_fd = os.open(
            temporary_name, create_flags, 0o600, dir_fd=parent_fd)
        with os.fdopen(
                opened_fd, "w", encoding="utf-8", newline="\n") as handle:
            opened_fd = None
            handle.write(new_text)
            handle.flush()
            os.fsync(handle.fileno())
        named = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino):
            raise OSError(errno.EAGAIN,
                          "page identity changed before publication",
                          relative)
        os.replace(temporary_name, basename,
                   src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary_name = None
        os.fsync(parent_fd)
    finally:
        if opened_fd is not None:
            os.close(opened_fd)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError:
                pass
        os.close(parent_fd)


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

    try:
        ledger_snapshot = kblib.repository_file_snapshot(
            root, COVERAGE_LEDGER_PATH, singly_linked=True)
        rows = _ledger_rows(ledger_snapshot)
        selected = args.page if args.page else sorted(rows)
        unknown = [page for page in (args.page or []) if page not in rows]
        if unknown:
            raise ValueError(
                "not in the Coverage Ledger: %s" % ", ".join(unknown))
        if len(selected) != len(set(selected)):
            raise ValueError("selected pages must not contain duplicates")

        # Build the complete plan from immutable, contained file snapshots.
        # No page changes until every selected path and after-image is valid.
        plan = []
        for relative in selected:
            snapshot = _page_snapshot(root, relative)
            if snapshot is None:
                continue
            text = snapshot.read_text()
            new_text, changes = project_page(text, rows[relative])
            plan.append((relative, snapshot, new_text, changes))

        if args.apply:
            # Revalidate every input, including the Ledger, immediately before
            # the first write.  A stale plan fails without a partial update.
            current_ledger = kblib.repository_file_snapshot(
                root, COVERAGE_LEDGER_PATH, singly_linked=True)
            if current_ledger.data != ledger_snapshot.data:
                raise ValueError("Coverage Ledger changed during projection")
            for relative, snapshot, _new_text, _changes in plan:
                current = _page_snapshot(root, relative)
                if current is None or current.data != snapshot.data:
                    raise ValueError(
                        "%s changed during projection; re-run" % relative)
    except (OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] page-state projection input is unsafe or invalid: %s" %
              exc)
        return 1

    planned = 0
    touched = 0
    for rel, snapshot, new_text, changes in plan:
        if not changes:
            continue
        planned += len(changes)
        touched += 1
        for name, before, after in changes:
            print("  [%s] %s %s: %r -> %s" %
                   ("PROJECT" if args.apply else "PLAN", rel, name, before,
                   "removed (owner empty)" if after is None else repr(after)))
        if args.apply:
            # Re-resolve immediately before publication so a symlink or link
            # swap cannot redirect a previously approved Ledger spelling.
            try:
                current = _page_snapshot(root, rel)
                if current is None or current.data != snapshot.data:
                    raise ValueError("%s changed during projection; re-run" % rel)
                _frontmatter_mapping(new_text, rel)
                _publish_page(root, rel, current, new_text)
            except (OSError, UnicodeError, ValueError,
                    kblib.YamlSubsetError) as exc:
                print("[FAIL] page-state projection write rejected: %s" % exc)
                return 1
    print("%s: pages=%d field_changes=%d%s" %
          (TOOL, touched, planned,
           "" if args.apply else " (dry run; add --apply)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
