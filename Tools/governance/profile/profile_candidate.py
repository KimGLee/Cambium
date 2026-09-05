#!/usr/bin/env python3
"""Read, review, and explicitly edit one interview candidate, never adopt it.

Edits are structured data, not code. The Tool checks the after-image against
the same draft contract, preserves unanswered fields, and never writes runtime
selection or evidence. A package snapshot is an optimistic precondition, not
a user approval. Creation remains the existing scaffold_profile capability.
"""

from collections.abc import Mapping
from contextlib import contextmanager
import copy
import json
import os
import re

from Tools.governance.profile import profile_codec, profile_contract, profile_layout_contract
from Tools.platform.common import kblib


class CandidateError(ValueError):
    """An explicit candidate operation cannot be safely performed."""


def _json_data(text):
    def unique_fields(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise CandidateError("duplicate JSON input field: %s" % name)
            result[name] = value
        return result
    return json.loads(text, object_pairs_hook=unique_fields)


def _key(container, component, *, creating=False):
    if isinstance(container, Mapping) and isinstance(component, str) and component:
        if not creating and component not in container:
            raise CandidateError("field is absent: %s" % component)
        return component
    if isinstance(container, (list, tuple)) and isinstance(component, dict) and component:
        if not all(isinstance(key, str) and isinstance(value, (str, int))
                   and not isinstance(value, bool) for key, value in component.items()):
            raise CandidateError("record selector must contain explicit string/integer identity values")
        matches = [index for index, row in enumerate(container)
                   if isinstance(row, Mapping) and all(
                       type(row.get(key)) is type(value) and row[key] == value
                       for key, value in component.items())]
        if len(matches) != 1:
            raise CandidateError("record selector must resolve exactly once, found %d" % len(matches))
        return matches[0]
    raise CandidateError("path needs field names or an unambiguous record selector; indices are not identities")


def read_value(document, path):
    """Read by fields and stable record selectors, without I/O or validation."""
    if not isinstance(path, list):
        raise CandidateError("selector must be a JSON path array")
    current = document
    for component in path:
        current = current[_key(current, component)]
    return copy.deepcopy(current)


def apply_edits(document, edits):
    """Pure edit plan; field semantics are checked by the owner after editing."""
    if not isinstance(edits, list) or not edits:
        raise CandidateError("edits must be a nonempty array")
    result = copy.deepcopy(document)
    for edit in edits:
        if not isinstance(edit, dict) or edit.get("op") not in ("set", "append", "remove"):
            raise CandidateError("edit operation must be set, append, or remove")
        expected = {"op", "path"} | ({"value"} if edit["op"] != "remove" else set())
        if set(edit) != expected:
            raise CandidateError("edit fields must be exactly %s" % sorted(expected))
        path = edit["path"]
        if (not isinstance(path, list) or not path or not isinstance(path[0], str)
                or path[0] not in ("slots", "execution_default_overrides")):
            raise CandidateError("edit only explicit slot answers or execution overrides; identity is immutable")
        parent = result
        for component in path[:-1]:
            parent = parent[_key(parent, component)]
        key = _key(parent, path[-1], creating=edit["op"] == "set")
        if edit["op"] == "remove":
            del parent[key]
        elif edit["op"] == "set":
            parent[key] = copy.deepcopy(edit["value"])
        else:
            if not isinstance(parent[key], list):
                raise CandidateError("append requires an existing list")
            parent[key].append(copy.deepcopy(edit["value"]))
    # Validate representability without inventing defaults or policy choices.
    return profile_codec.loads_profile(profile_codec.dumps_profile(result))


def _location(profile_id):
    path = profile_layout_contract.profile_relative(profile_id) + "/" + profile_layout_contract.PROFILE_MANIFEST_NAME
    return profile_layout_contract.validate_selectable_profile_manifest_path(path)


def _snapshot(root, location):
    snapshot = kblib.repository_tree_snapshot(root, location.directory)
    document = profile_codec.loads_profile(snapshot.read_bytes(location.path))
    profile_layout_contract.validate_manifest_identity(document, location)
    return snapshot, document


def _after_snapshot(before, path, encoded):
    files = dict(before.files)
    files[path] = encoded
    # project computes the shared tree digest; no second framing algorithm.
    return kblib.RepositoryTreeSnapshot(
        before.root, before.relative_directory, "", files).project(files)


@contextmanager
def _candidate_lock(root, location):
    """Serialize cooperating candidate writers without creating runtime state.

    The directory inode is the lock target; no lock artifact is inserted in
    the Profile snapshot. Hosts without directory advisory locks refuse edit
    publication but can still inspect candidates.
    """
    try:
        import fcntl
    except ImportError as exc:
        raise CandidateError("candidate editing requires a Host with directory advisory locks") from exc
    parent = kblib.repository_path(root, location.directory, must_exist=True, reject_symlink=True)
    descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    locked = False
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        observed = os.fstat(descriptor)
        current = os.stat(kblib.repository_path(root, location.directory, must_exist=True, reject_symlink=True))
        if (observed.st_dev, observed.st_ino) != (current.st_dev, current.st_ino):
            raise CandidateError("candidate directory changed before edit admission")
        yield
    except BlockingIOError as exc:
        raise CandidateError("another candidate edit holds this Profile") from exc
    finally:
        if locked:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def edit_candidate(root, profile_id, edits, expected_snapshot_sha256, *, apply=False):
    """Validate one declared edit and optionally publish its single after-image."""
    location = _location(profile_id)
    with _candidate_lock(root, location):
        before, document = _snapshot(root, location)
        if expected_snapshot_sha256 != before.sha256:
            raise CandidateError("candidate snapshot changed; read it again before editing")
        after = apply_edits(document, edits)
        encoded = profile_codec.dumps_profile(after)
        candidate = _after_snapshot(before, location.path, encoded)
        inputs = profile_contract.profile_draft_inputs(root)
        draft = profile_contract.load_profile_draft(
            root, location.path, profile_snapshot=candidate, root_input_snapshots=inputs)
        if draft.diagnostics:
            raise CandidateError(profile_contract.format_diagnostics(draft.diagnostics))
        report = {
            "kind": "profile-candidate", "profile_id": profile_id, "manifest": location.path,
            "result": "dry-run", "changed": False, "resulting_state_verified": False,
            "snapshot_before": before.sha256, "snapshot_after": candidate.sha256,
            "edits": edits, "ready": draft.ready,
            "unresolved_items": list(draft.unresolved_items),
            "next_action": "review-profile-answers", "adoption_performed": False,
        }
        if not apply:
            return report
        current, _document = _snapshot(root, location)
        if current.sha256 != before.sha256 or any(
                kblib.repository_file_snapshot(root, path, singly_linked=True).sha256 != item.sha256
                for path, item in inputs.items()):
            raise CandidateError("Profile or owner inputs changed before publication")
        try:
            kblib.atomic_write_text(os.path.join(root, location.path), encoded.decode("utf-8"))
            current, _document = _snapshot(root, location)
            if current.sha256 != candidate.sha256:
                raise CandidateError("resulting candidate differs from the validated after-image")
        except (OSError, ValueError) as exc:
            # A failed fsync/read-back can occur after publication. Never
            # claim a refusal with no writes, and never delete user bytes.
            report.update(result="uncertain", changed=None, error=str(exc),
                          next_action="inspect-candidate-before-retry")
            return report
        report.update(result="updated", changed=before.sha256 != current.sha256,
                      resulting_state_verified=True)
        return report


def main(argv=None):
    parser = kblib.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="repository root; no adoption or runtime writes")
    parser.add_argument("--profile-id", required=True, help="existing non-template candidate identity")
    parser.add_argument("--mode", choices=("read", "edit", "render"), default="read")
    parser.add_argument("--selector", default="[]", help="JSON array of fields and stable record selectors")
    parser.add_argument("--edits", help="JSON file containing explicit set/append/remove edits")
    parser.add_argument("--expected-snapshot-sha256", help="candidate snapshot returned by read; required for edit")
    parser.add_argument("--apply", action="store_true", help="publish an edit; otherwise preview only")
    parser.add_argument("--json", action="store_true", help="emit machine result, including a rendered view when requested")
    args = parser.parse_args(argv)
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        if args.mode == "edit":
            if not args.edits or not args.expected_snapshot_sha256 or args.selector != "[]":
                raise CandidateError("edit requires --edits and --expected-snapshot-sha256, not --selector")
            edits = _json_data(kblib.read_text(args.edits))
            report = edit_candidate(root, args.profile_id, edits,
                                    args.expected_snapshot_sha256, apply=args.apply)
        else:
            if args.apply or args.edits or args.expected_snapshot_sha256:
                raise CandidateError("read/render do not accept edit parameters")
            location = _location(args.profile_id)
            before, document = _snapshot(root, location)
            value = read_value(document, _json_data(args.selector))
            report = {"kind": "profile-candidate", "result": "read", "profile_id": args.profile_id,
                      "manifest": location.path, "snapshot_sha256": before.sha256,
                      "value": value, "adoption_performed": False}
            if args.mode == "render":
                text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
                fence = "`" * max(3, max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
                report["rendered"] = "# Profile candidate: %s\n\nNon-authoritative review view; not a confirmation or adoption.\n\n%sjson\n%s\n%s\n" % (
                    args.profile_id, fence, text, fence)
        code = 1 if report["result"] == "uncertain" else 0
    except (OSError, ValueError, TypeError) as exc:
        report = {"kind": "profile-candidate", "result": "refused", "changed": False,
                  "adoption_performed": False, "error": str(exc)}
        code = 1
    if args.mode == "render" and not args.json and "rendered" in report:
        print(report["rendered"], end="")
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
