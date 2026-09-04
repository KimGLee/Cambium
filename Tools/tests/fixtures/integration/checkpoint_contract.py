"""Mechanical manifest contract shared by current runtime checkpoints."""

import hashlib
import json
import shutil


PERSISTED_PATHS = (".cambium", "Topics")
PROFILE_DEPENDENCY_BUILDER = (
    "Tools.tests.support.profile_fixture.install_loadable_profile"
)
FIXTURE_EXCLUDED_NAMES = ("__pycache__", ".DS_Store")


def copy_checkpoint_seed(source, destination):
    """Copy one source fixture without host-local or generated noise."""
    return shutil.copytree(
        source, destination,
        ignore=shutil.ignore_patterns(*FIXTURE_EXCLUDED_NAMES),
    )


def file_records(root):
    """Project inspectable checkpoint bytes into one canonical file list."""
    records = []
    for source in sorted(path for path in root.rglob("*") if path.is_file()):
        if any(part in FIXTURE_EXCLUDED_NAMES for part in source.parts):
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
    "FIXTURE_EXCLUDED_NAMES",
    "PERSISTED_PATHS",
    "PROFILE_DEPENDENCY_BUILDER",
    "copy_checkpoint_seed",
    "file_records",
    "tree_sha256",
]
