"""Mechanical manifest contract shared by current runtime checkpoints."""

import hashlib
import json
import shutil
from Tools.execution.task_runtime import runtime_validation
from Tools.platform.distribution.test_runner import measured, measure_scope


PERSISTED_PATHS = (".cambium", "Topics")
PROFILE_DEPENDENCY_BUILDER = (
    "Tools.tests.support.profile_fixture.install_loadable_profile"
)
FIXTURE_EXCLUDED_NAMES = ("__pycache__", ".DS_Store")


@measured("checkpoint", "copy-seed")
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


@measured("checkpoint", "validate-manifest")
def validate_checkpoint_manifest(root, manifest_path, expected):
    """Validate one static checkpoint from its declared scenario identity."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise AssertionError("checkpoint has stale %s" % field)
    records = file_records(root)
    if manifest.get("files") != records or manifest.get("tree_sha256") != tree_sha256(records):
        raise AssertionError("checkpoint file manifest or tree fingerprint is stale")
    return manifest


@measured("checkpoint", "reconstruct")
def reconstruct_checkpoint(source, destination, manifest, installer):
    """Install and verify a local after-image without replaying its producer."""
    copy_checkpoint_seed(source, destination)
    with measure_scope("checkpoint", "install-dependencies"):
        installer(destination)
    if manifest.get("validated_tree_sha256") != tree_sha256(file_records(destination)):
        raise AssertionError("checkpoint dependencies changed; regenerate it")
    with measure_scope("checkpoint", "validate-runtime"):
        result = runtime_validation.validate_runtime(destination)
    if result["errors"]:
        raise AssertionError("checkpoint fails current runtime contract: %s" % result["errors"])
    return result


__all__ = [
    "FIXTURE_EXCLUDED_NAMES",
    "PERSISTED_PATHS",
    "PROFILE_DEPENDENCY_BUILDER",
    "copy_checkpoint_seed",
    "file_records",
    "tree_sha256",
    "validate_checkpoint_manifest",
    "reconstruct_checkpoint",
]
