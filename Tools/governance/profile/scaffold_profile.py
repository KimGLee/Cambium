#!/usr/bin/env python3
"""Create a non-authorizing structured Profile candidate for an interview.

The only semantic input is the explicitly supplied Profile identity. The
current template supplies allowed support files and an empty TOML skeleton;
no unanswered field is filled with a policy, inactive choice, or placeholder.
Creation does not select a Profile, create runtime state, or issue a Receipt.
"""

import ctypes
import errno
import json
import os
import shutil
import sys
import tempfile

import Tools.platform.common.kblib as kblib
import Tools.governance.profile.profile_codec as profile_codec
import Tools.governance.profile.profile_layout_contract as profile_layout_contract

TOOL = "scaffold_profile"
TOOL_VERSION = "2.0.0"
MANIFEST_RELATIVE = "profiles/template-files.yaml"
TEMPLATE_RELATIVE = profile_layout_contract.profile_relative(
    profile_layout_contract.TEMPLATE_PROFILE_ID)


class ScaffoldRefusal(ValueError):
    """Candidate creation was refused without selecting any Profile."""


class ScaffoldPublicationUncertain(OSError):
    """Publication happened, but the resulting candidate was not verified."""


def _relative(value):
    if (not isinstance(value, str) or value != value.strip() or
            "\\" in value or "\x00" in value or
            any(part in ("", ".", "..") for part in value.split("/"))):
        raise ScaffoldRefusal("template entries must be canonical relative file paths")
    return value


def load_manifest(root):
    snapshot = kblib.repository_file_snapshot(root, MANIFEST_RELATIVE, singly_linked=True)
    document = kblib.parse_yaml_subset(snapshot.read_text())
    expected = {"template_manifest_version", "source", "copy", "orientation_not_copied"}
    if (not isinstance(document, dict) or set(document) != expected or
            document["template_manifest_version"] != 2 or
            document["source"] != TEMPLATE_RELATIVE):
        raise ScaffoldRefusal("template-files must use the current structured candidate contract")
    for name in ("copy", "orientation_not_copied"):
        if not isinstance(document[name], list):
            raise ScaffoldRefusal("template %s must be a list" % name)
    copied = [_relative(value) for value in document["copy"]]
    orientation = [_relative(value) for value in document["orientation_not_copied"]]
    if len(set(copied + orientation)) != len(copied + orientation):
        raise ScaffoldRefusal("template paths cannot be duplicated across classifications")
    if profile_layout_contract.PROFILE_MANIFEST_NAME not in copied:
        raise ScaffoldRefusal("template must include the unique Profile TOML entry")
    return copied, orientation


def validate_profile_id(profile_id):
    relative = profile_layout_contract.profile_relative(profile_id)
    try:
        profile_layout_contract.validate_selectable_profile_manifest_path(
            relative + "/" + profile_layout_contract.PROFILE_MANIFEST_NAME)
    except profile_layout_contract.ProfileLayoutError as exc:
        raise ScaffoldRefusal(str(exc)) from exc


def destination_conflict(destination):
    if os.path.lexists(destination):
        return "candidate destination already exists; it will not be merged or overwritten"
    return None


def build_plan(root, profile_id):
    validate_profile_id(profile_id)
    copied, orientation = load_manifest(root)
    files = {}
    for relative in copied:
        snapshot = kblib.repository_file_snapshot(
            root, TEMPLATE_RELATIVE + "/" + relative, singly_linked=True)
        files[relative] = snapshot.data
    manifest = profile_layout_contract.PROFILE_MANIFEST_NAME
    skeleton = profile_codec.loads_profile(files[manifest])
    # A candidate skeleton must not smuggle example/default policy choices
    # into an interview. Support files remain unreferenced until explicitly
    # selected by the user's answers.
    if (set(skeleton) - {"schema_version", "profile_id", "slots", "execution_default_overrides"}
            or type(skeleton.get("schema_version")) is not int
            or skeleton["schema_version"] != 1
            or skeleton.get("profile_id") not in (None, profile_layout_contract.TEMPLATE_PROFILE_ID)):
        raise ScaffoldRefusal("candidate template has an invalid identity or encoding envelope")
    if skeleton.get("slots") != {} or skeleton.get(
            "execution_default_overrides") not in ({}, None):
        raise ScaffoldRefusal("candidate template must not prefill semantic slot answers")
    candidate = {"schema_version": 1, "profile_id": profile_id, "slots": {}}
    files[manifest] = profile_codec.dumps_profile(candidate)
    return {"copy": copied, "orientation_not_copied": orientation,
            "files": files, "derived_identity": profile_id}


def _publish_directory(staging, destination):
    """Publish once without replacing a concurrent directory or symlink."""
    if sys.platform == "win32":
        os.rename(staging, destination)  # Windows refuses an existing target.
        return
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        operation = library.renamex_np
        operation.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        operation.restype = ctypes.c_int
        result = operation(os.fsencode(staging), os.fsencode(destination), 4)
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        operation = library.renameat2
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_uint]
        operation.restype = ctypes.c_int
        result = operation(-100, os.fsencode(staging), -100,
                           os.fsencode(destination), 1)
    else:
        raise ScaffoldRefusal("this host lacks no-replace directory publication")
    if result:
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise ScaffoldRefusal("candidate destination appeared before publication")
        raise OSError(error, os.strerror(error), destination)


def apply_plan(root, profile_id, plan):
    directory = os.path.join(root, profile_layout_contract.PROFILES_DIRECTORY)
    # Bind the existing parent to the declared repository, not a symlink.
    kblib.repository_path(root, profile_layout_contract.PROFILES_DIRECTORY,
                          must_exist=True, reject_symlink=True)
    destination = os.path.join(directory, profile_id)
    conflict = destination_conflict(destination)
    if conflict:
        raise ScaffoldRefusal(conflict)
    staging = tempfile.mkdtemp(prefix=".profile-candidate-", dir=directory)
    published = False
    try:
        for relative, data in plan["files"].items():
            target = os.path.join(staging, *relative.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        _publish_directory(staging, destination)
        published = True
        for relative, expected in plan["files"].items():
            actual = kblib.repository_file_snapshot(
                root, profile_layout_contract.profile_relative(profile_id) + "/" + relative,
                singly_linked=True)
            if actual.data != expected:
                raise ScaffoldRefusal("published candidate changed before resulting-state verification")
    except (OSError, ValueError) as exc:
        if published:
            raise ScaffoldPublicationUncertain(
                "candidate was published but its resulting state is unverified: %s" % exc) from exc
        raise
    finally:
        if not published:
            shutil.rmtree(staging)


def main(argv=None):
    parser = kblib.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="repository root containing the unique Profile template")
    parser.add_argument("--profile-id", required=True, help="explicitly confirmed candidate identity")
    parser.add_argument("--apply", action="store_true", help="create the candidate; otherwise report only")
    parser.add_argument("--json", action="store_true", help="emit the structured result")
    args = parser.parse_args(argv)
    root = os.path.realpath(os.path.abspath(args.root))
    report = {"tool": TOOL, "tool_version": TOOL_VERSION, "profile_id": args.profile_id,
              "destination": profile_layout_contract.profile_relative(args.profile_id),
              "apply": args.apply, "created": False, "resulting_state_verified": False,
              "files": [], "result": "refused", "error": None}
    try:
        if not os.path.isdir(root):
            raise ScaffoldRefusal("root is not an existing repository directory")
        plan = build_plan(root, args.profile_id)
        report["files"] = [report["destination"] + "/" + name for name in plan["copy"]]
        report["orientation_not_copied"] = plan["orientation_not_copied"]
        conflict = destination_conflict(os.path.join(root, report["destination"]))
        if conflict:
            raise ScaffoldRefusal(conflict)
        if args.apply:
            apply_plan(root, args.profile_id, plan)
        report.update(result="created" if args.apply else "dry-run", created=args.apply,
                      resulting_state_verified=args.apply,
                      next_action="complete-profile-interview")
        code = 0
    except ScaffoldPublicationUncertain as exc:
        report.update(result="uncertain", created=True, error=str(exc),
                      next_action="inspect-published-candidate")
        code = 1
    except (OSError, ValueError, UnicodeError) as exc:
        report["error"] = str(exc)
        code = 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print("%s: %s" % (TOOL, report["result"]))
        print(report["error"] or "Candidate is not adopted; continue the Profile interview.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
