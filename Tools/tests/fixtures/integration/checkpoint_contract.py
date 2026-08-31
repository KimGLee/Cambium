"""Mechanical manifest contract shared by current runtime checkpoints."""

import hashlib
import json


PERSISTED_PATHS = (".cambium", "Topics")
PROFILE_DEPENDENCY_BUILDER = (
    "Tools.tests.support.profile_fixture.install_loadable_profile"
)


def file_records(root):
    """Project inspectable checkpoint bytes into one canonical file list."""
    records = []
    for source in sorted(path for path in root.rglob("*") if path.is_file()):
        if "__pycache__" in source.parts or source.name == ".DS_Store":
            continue
        content = source.read_bytes()
        records.append({
            "path": source.relative_to(root).as_posix(),
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size": len(content),
        })
    return records


def tree_sha256(records):
    """Hash one canonical checkpoint file list."""
    encoded = json.dumps(
        records, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


__all__ = [
    "PERSISTED_PATHS",
    "PROFILE_DEPENDENCY_BUILDER",
    "file_records",
    "tree_sha256",
]
