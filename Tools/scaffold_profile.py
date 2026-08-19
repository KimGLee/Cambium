#!/usr/bin/env python3
"""Safe candidate-profile scaffolder.

Copy `profiles/_template` to `profiles/<profile-id>` using the exact
version-controlled whitelist in `profiles/template-files.yaml`, and perform
only the mechanical derivations that are pure functions of the profile id:

* `profile.md` — `profile_id` becomes the requested slug;
* `registries/registered-scans.md` — the verifier command cell is
  materialized with this candidate's own `--config` path
  (`profiles/<profile-id>/scan-configs/residual-scan.yaml`), leaving the
  Stable Scan ID and every other semantic answer as the unfilled sentinel;
* `registries/audit-dimensions.md` — both predicate-owner cells become this
  candidate's own repository-relative paths with their `#heading` fragments
  (`.../scope-and-architecture.md#Foundation Depth Requirements` and
  `.../registries/audit-dimensions.md#Residual Disposition`), exactly as the
  template README's materialization checklist and the `self_path_rewrites`
  block of `profiles/interview.yaml` derive them.

Every rewrite is anchored to the exact template text and fails closed when
the anchor is missing or ambiguous (template drift is an error, never a
silent skip). Semantic `TODO(profile)` sentinels are left untouched: the
scaffolded candidate is EXPECTED to still fail `check_profile.py` until the
interview answers are filled in.

The whitelist is authoritative: the tool never walks the template directory,
so junk files there are never copied; a whitelisted file that is missing or a
symlink in the template is an error. The destination must not exist in any
form — directory (even empty), regular file, or symlink each refuse
distinctly; nothing is ever merged or overwritten. Apply stages into a
dot-prefixed temporary directory inside `profiles/` and publishes with one
`os.rename`; any failure (including interruption) removes the staging tree.

This tool never touches `kernel/` (including `K00 Standards Control/03
Standards Governance.md`), never creates `.cambium/`, writes no receipt, and
never selects or adopts the candidate; selection remains R09 adoption.

Dry-run is the default; `--apply` performs the write. Exit codes follow the
writer-tool convention (`init_state.py`): 0 = success (dry-run or applied),
1 = refusal or failure.

Usage: python3 Tools/scaffold_profile.py <root> --profile-id <slug>
       [--apply] [--json]
"""

import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "scaffold_profile"
TOOL_VERSION = "1.0.0"

MANIFEST_RELATIVE = "profiles/template-files.yaml"
TEMPLATE_RELATIVE = "profiles/_template"
SENTINEL = "TODO(profile)"
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
RESERVED_PROFILE_IDS = ("_template", "examples")
MANIFEST_FIELDS = frozenset((
    "template_manifest_version", "source", "copy", "orientation_not_copied",
))

# Derived rewrite targets that must therefore be part of the copied package.
SCAN_CONFIG_RELATIVE = "scan-configs/residual-scan.yaml"
FOUNDATION_OWNER_FILE = "scope-and-architecture.md"
FOUNDATION_OWNER_HEADING = "Foundation Depth Requirements"
RESIDUAL_OWNER_FILE = "registries/audit-dimensions.md"
RESIDUAL_OWNER_HEADING = "Residual Disposition"


class ScaffoldRefusal(Exception):
    """A deterministic validation refusal; nothing was written."""


def derived_rewrites(profile_id):
    """The anchored mechanical substitutions for one candidate profile.

    Each entry is ``(template-relative file, exact old text, new text)``.
    The old text must occur exactly once in the copied file. Only values
    that are pure functions of the profile id are derived; every semantic
    ``TODO(profile)`` cell is preserved byte-for-byte.
    """
    profile_dir = "profiles/%s" % profile_id
    return (
        # Identity: the one TODO(profile) cell under `## Profile Identity`.
        ("profile.md",
         "- `profile_id`: `TODO(profile)`",
         "- `profile_id`: `%s`" % profile_id),
        # Registered scan row: materialize the verifier command's --config
        # path (interview self_path_rewrites: "verifier command --config
        # path"). The Stable Scan ID inside the command, and every other
        # cell, remain semantic sentinels for the interview to answer.
        ("registries/registered-scans.md",
         "| TODO(profile) | `K12/09 item 6 — residual-content scan` "
         "| TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) |",
         "| TODO(profile) | `K12/09 item 6 — residual-content scan` "
         "| TODO(profile) | `python3 Tools/check_residual_content.py . "
         "--scan-id TODO(profile) --config %s/%s --time-limit 55` "
         "| TODO(profile) | TODO(profile) |"
         % (profile_dir, SCAN_CONFIG_RELATIVE)),
        # Foundation judgment item: predicate-owner cell (interview
        # self_path_rewrites: "foundation item predicate owner"). The item
        # ID cell stays a semantic sentinel.
        ("registries/audit-dimensions.md",
         "| TODO(profile) | `content_and_depth` | `Single Note Review` "
         "| One page of the registered foundation class satisfies the "
         "registered foundation-depth predicate. | `emits` "
         "| TODO(profile) |",
         "| TODO(profile) | `content_and_depth` | `Single Note Review` "
         "| One page of the registered foundation class satisfies the "
         "registered foundation-depth predicate. | `emits` "
         "| `%s/%s#%s` |"
         % (profile_dir, FOUNDATION_OWNER_FILE, FOUNDATION_OWNER_HEADING)),
        # Residual judgment item: predicate-owner cell (interview
        # self_path_rewrites: "residual item predicate owner").
        ("registries/audit-dimensions.md",
         "| TODO(profile) | `coverage_and_integration` | `Batch Review` "
         "| Every candidate the registered residual scan reports outside "
         "its accepted roots has an accepted disposition. | `emits` "
         "| TODO(profile) |",
         "| TODO(profile) | `coverage_and_integration` | `Batch Review` "
         "| Every candidate the registered residual scan reports outside "
         "its accepted roots has an accepted disposition. | `emits` "
         "| `%s/%s#%s` |"
         % (profile_dir, RESIDUAL_OWNER_FILE, RESIDUAL_OWNER_HEADING)),
    )


def _canonical_manifest_entry(value, label):
    """One canonical template-relative file path from the copy manifest."""
    if not isinstance(value, str) or not value:
        raise ScaffoldRefusal(
            "%s entries must be non-empty strings; found %r" % (label, value))
    if value != value.strip():
        raise ScaffoldRefusal(
            "%s entry %r has leading or trailing whitespace" % (label, value))
    if "\\" in value or "\x00" in value:
        raise ScaffoldRefusal(
            "%s entry %r must use canonical `/` separators" % (label, value))
    if os.path.isabs(value):
        raise ScaffoldRefusal(
            "%s entry %r must be template-relative" % (label, value))
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise ScaffoldRefusal(
            "%s entry %r must not contain empty, `.` or `..` segments"
            % (label, value))
    return value


def load_manifest(root):
    """Parse and validate profiles/template-files.yaml; return the two lists."""
    path = os.path.join(root, *MANIFEST_RELATIVE.split("/"))
    if not os.path.isfile(path):
        raise ScaffoldRefusal(
            "root has no %s; the exact-copy whitelist is required"
            % MANIFEST_RELATIVE)
    try:
        with open(path, encoding="utf-8", errors="strict") as handle:
            data = kblib.parse_yaml_subset(handle.read())
    except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
        raise ScaffoldRefusal(
            "cannot read/parse %s: %s" % (MANIFEST_RELATIVE, exc))
    if not isinstance(data, dict):
        raise ScaffoldRefusal("%s must be a mapping" % MANIFEST_RELATIVE)
    missing = sorted(MANIFEST_FIELDS - set(data))
    extra = sorted(set(data) - MANIFEST_FIELDS)
    if missing or extra:
        raise ScaffoldRefusal(
            "%s must contain exactly %s; missing=%s extra=%s"
            % (MANIFEST_RELATIVE, sorted(MANIFEST_FIELDS), missing, extra))
    if data.get("template_manifest_version") != 1:
        raise ScaffoldRefusal(
            "%s template_manifest_version must be integer 1"
            % MANIFEST_RELATIVE)
    if data.get("source") != TEMPLATE_RELATIVE:
        raise ScaffoldRefusal(
            "%s source must be exactly %r" % (MANIFEST_RELATIVE,
                                              TEMPLATE_RELATIVE))
    lists = {}
    for key in ("copy", "orientation_not_copied"):
        value = data.get(key)
        if not isinstance(value, list) or not value:
            raise ScaffoldRefusal(
                "%s `%s` must be a non-empty list" % (MANIFEST_RELATIVE, key))
        lists[key] = [_canonical_manifest_entry(item, key) for item in value]
    combined = lists["copy"] + lists["orientation_not_copied"]
    duplicates = sorted({item for item in combined
                         if combined.count(item) > 1})
    if duplicates:
        raise ScaffoldRefusal(
            "%s lists a path more than once (a file is copied or "
            "orientation, never both): %s" % (MANIFEST_RELATIVE, duplicates))
    return lists["copy"], lists["orientation_not_copied"]


def validate_profile_id(profile_id):
    if not isinstance(profile_id, str) or not SLUG_RE.fullmatch(profile_id):
        raise ScaffoldRefusal(
            "--profile-id %r must fully match [a-z0-9][a-z0-9_-]*"
            % (profile_id,))
    if profile_id in RESERVED_PROFILE_IDS:
        raise ScaffoldRefusal(
            "--profile-id %r is reserved and cannot name a candidate profile"
            % profile_id)


def destination_conflict(destination):
    """A distinct refusal reason when the destination exists in any form."""
    if os.path.islink(destination):
        return ("destination %s already exists as a symlink; refusing to "
                "follow, merge, or overwrite it" % destination)
    if os.path.isdir(destination):
        return ("destination %s already exists as a directory (even an "
                "empty one is refused); never merged, never overwritten"
                % destination)
    if os.path.lexists(destination):
        return ("destination %s already exists as a file; a candidate "
                "profile must be a fresh directory" % destination)
    return None


def _heading_count(text, heading):
    needle = "## %s" % heading
    return sum(1 for line in text.splitlines() if line.strip() == needle)


def build_plan(root, profile_id):
    """Read the template through the whitelist and derive the rewrites.

    Read-only: returns the complete in-memory candidate. ``files`` maps each
    template-relative path to its final bytes; ``rewrites`` records each
    applied (file, old, new) anchor.
    """
    template_dir = os.path.join(root, *TEMPLATE_RELATIVE.split("/"))
    if not os.path.isdir(template_dir):
        raise ScaffoldRefusal(
            "root has no %s directory to scaffold from" % TEMPLATE_RELATIVE)
    copy_list, orientation = load_manifest(root)
    validate_profile_id(profile_id)

    rewrites = derived_rewrites(profile_id)
    rewrite_files = {relative for relative, _old, _new in rewrites}
    for relative in sorted(rewrite_files | {SCAN_CONFIG_RELATIVE,
                                            FOUNDATION_OWNER_FILE,
                                            RESIDUAL_OWNER_FILE}):
        if relative not in copy_list:
            raise ScaffoldRefusal(
                "manifest drift: derived rewrites require %r in the "
                "`copy:` whitelist of %s" % (relative, MANIFEST_RELATIVE))

    files = {}
    for relative in copy_list:
        source = os.path.join(template_dir, *relative.split("/"))
        if os.path.islink(source):
            raise ScaffoldRefusal(
                "whitelisted template file is a symlink and cannot be "
                "copied: %s/%s" % (TEMPLATE_RELATIVE, relative))
        if not os.path.isfile(source):
            raise ScaffoldRefusal(
                "manifest drift: whitelisted template file is missing: "
                "%s/%s" % (TEMPLATE_RELATIVE, relative))
        with open(source, "rb") as handle:
            files[relative] = handle.read()

    applied = []
    for relative, old, new in rewrites:
        try:
            text = files[relative].decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ScaffoldRefusal(
                "template drift: %s/%s is not strict UTF-8: %s"
                % (TEMPLATE_RELATIVE, relative, exc))
        count = text.count(old)
        if count != 1:
            raise ScaffoldRefusal(
                "template drift: rewrite anchor occurs %d time(s) instead "
                "of exactly once in %s/%s: %r"
                % (count, TEMPLATE_RELATIVE, relative, old))
        files[relative] = text.replace(old, new, 1).encode("utf-8")
        applied.append({"file": relative, "old": old, "new": new})

    # The derived predicate-owner paths carry `#heading` fragments; fail
    # closed now if the template no longer carries those headings exactly
    # once, rather than shipping a candidate whose mechanical paths dangle.
    for relative, heading in (
            (FOUNDATION_OWNER_FILE, FOUNDATION_OWNER_HEADING),
            (RESIDUAL_OWNER_FILE, RESIDUAL_OWNER_HEADING)):
        count = _heading_count(
            files[relative].decode("utf-8", errors="strict"), heading)
        if count != 1:
            raise ScaffoldRefusal(
                "template drift: `## %s` occurs %d time(s) instead of "
                "exactly once in %s/%s" % (heading, count,
                                           TEMPLATE_RELATIVE, relative))

    return {
        "copy": list(copy_list),
        "orientation_not_copied": list(orientation),
        "files": files,
        "rewrites": applied,
    }


def stage_candidate(staging, plan):
    """Write the complete candidate into a not-yet-public staging tree."""
    for relative in plan["copy"]:
        target = os.path.join(staging, *relative.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "xb") as handle:
            handle.write(plan["files"][relative])


def publish_candidate(staging, destination):
    """Existence re-check immediately followed by one rename; never merge."""
    conflict = destination_conflict(destination)
    if conflict is not None:
        raise ScaffoldRefusal(conflict)
    os.rename(staging, destination)


def apply_plan(root, profile_id, plan):
    """Stage inside profiles/ and publish; remove staging on any failure."""
    profiles_dir = os.path.join(root, "profiles")
    destination = os.path.join(profiles_dir, profile_id)
    staging = os.path.join(
        profiles_dir, ".scaffold-%s-%d" % (profile_id, os.getpid()))
    os.mkdir(staging)
    published = False
    try:
        stage_candidate(staging, plan)
        publish_candidate(staging, destination)
        published = True
    finally:
        if not published and os.path.lexists(staging):
            shutil.rmtree(staging)


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Scaffold a candidate profile from profiles/_template "
                    "using the exact-copy whitelist in %s" % MANIFEST_RELATIVE)
    parser.add_argument("root", help="repository root containing profiles/")
    parser.add_argument("--profile-id", required=True,
                        help="candidate profile slug matching "
                             "[a-z0-9][a-z0-9_-]* (equals the directory name)")
    parser.add_argument("--apply", action="store_true",
                        help="create the candidate; without it the plan is "
                             "reported and nothing is written")
    parser.add_argument("--json", action="store_true",
                        help="emit the plan/result as one JSON document")
    args = parser.parse_args(argv)

    report = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "profile_id": args.profile_id,
        "destination": "profiles/%s" % args.profile_id,
        "apply": bool(args.apply),
        "created": False,
        "result": None,
        "error": None,
        "files": [],
        "orientation_not_copied": [],
        "rewrites": [],
        "conflict": None,
    }

    def emit(exit_code):
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True,
                             indent=2))
        return exit_code

    def refuse(message):
        report["result"] = "refused"
        report["error"] = message
        if not args.json:
            print("[FAIL] %s; nothing was written" % message)
        return emit(1)

    root = os.path.realpath(os.path.abspath(args.root))
    if not os.path.isdir(root):
        return refuse("root is not an existing directory: %s" % args.root)

    try:
        plan = build_plan(root, args.profile_id)
    except ScaffoldRefusal as exc:
        return refuse(str(exc))

    destination = os.path.join(root, "profiles", args.profile_id)
    report["files"] = ["profiles/%s/%s" % (args.profile_id, relative)
                       for relative in plan["copy"]]
    report["orientation_not_copied"] = plan["orientation_not_copied"]
    report["rewrites"] = plan["rewrites"]
    report["conflict"] = destination_conflict(destination)

    if not args.json:
        print("scaffold plan for profiles/%s (from %s, whitelist %s):"
              % (args.profile_id, TEMPLATE_RELATIVE, MANIFEST_RELATIVE))
        for path in report["files"]:
            print("  create %s" % path)
        print("orientation files not copied (template documentation, "
              "never profile policy):")
        for relative in plan["orientation_not_copied"]:
            print("  %s/%s" % (TEMPLATE_RELATIVE, relative))
        print("derived mechanical rewrites (semantic %s answers are left "
              "in place):" % SENTINEL)
        for rewrite in plan["rewrites"]:
            print("  %s:" % rewrite["file"])
            print("    - %s" % rewrite["old"])
            print("    + %s" % rewrite["new"])

    if report["conflict"] is not None:
        return refuse(report["conflict"])

    if not args.apply:
        report["result"] = "dry-run"
        if not args.json:
            print("dry run; add --apply to create the candidate")
        return emit(0)

    try:
        apply_plan(root, args.profile_id, plan)
    except ScaffoldRefusal as exc:
        return refuse(str(exc))
    except (OSError, UnicodeError) as exc:
        report["result"] = "failed"
        report["error"] = str(exc)
        if not args.json:
            print("[FAIL] scaffolding stopped: %s; no candidate was "
                  "published" % exc)
        return emit(1)

    report["created"] = True
    report["result"] = "created"
    report["next"] = ("candidate created; complete the interview "
                      "(profiles/interview.yaml), then run check_profile")
    if not args.json:
        print("[PASS] candidate created at profiles/%s; complete the "
              "interview (profiles/interview.yaml), then run:"
              % args.profile_id)
        print("  python3 Tools/check_profile.py profiles/%s"
              % args.profile_id)
        print("The candidate still carries its semantic %s answers, so "
              "check_profile is EXPECTED to fail until the interview is "
              "complete. Scaffolding neither selects nor adopts a profile; "
              "selection remains R09 adoption." % SENTINEL)
    return emit(0)


if __name__ == "__main__":
    sys.exit(main())
