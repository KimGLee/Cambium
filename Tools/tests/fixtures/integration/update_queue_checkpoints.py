"""Static current-contract checkpoints for Queue writer integrations.

The E2E scenario producer owns the expensive Task/Queue/AuditPlan prologue.
Integration and Slow tests consume only its persisted adjacent after-images:
this module verifies the generated manifest, reconstructs the current Profile
dependency closure, validates the resulting runtime, and installs one private
copy for the caller.  It never executes an earlier lifecycle transition.
"""

import json
from pathlib import Path
import shutil
import tempfile

import Tools.execution.task_runtime.runtime_validation as runtime_validation
from Tools.tests.fixtures.integration.checkpoint_contract import (
    PERSISTED_PATHS,
    PROFILE_DEPENDENCY_BUILDER as BASE_PROFILE_DEPENDENCY_BUILDER,
    file_records,
    tree_sha256,
)
from Tools.tests.support.profile_fixture import install_loadable_profile


CHECKPOINTS = {
    "open-b1": (
        Path(__file__).with_name("update_queue_open_checkpoint"),
        Path(__file__).with_name(
            "update_queue_open_checkpoint.manifest.json"),
    ),
    "planning-ready": (
        Path(__file__).with_name("update_queue_planning_ready_checkpoint"),
        Path(__file__).with_name(
            "update_queue_planning_ready_checkpoint.manifest.json"),
    ),
    "merge-admission-b1": (
        Path(__file__).with_name(
            "update_queue_merge_admission_checkpoint"),
        Path(__file__).with_name(
            "update_queue_merge_admission_checkpoint.manifest.json"),
    ),
    "merged-b1": (
        Path(__file__).with_name("update_queue_merged_checkpoint"),
        Path(__file__).with_name(
            "update_queue_merged_checkpoint.manifest.json"),
    ),
}
GENERATOR = (
    "Tools.tests.fixtures.e2e.update_queue_scenarios."
    "generate_update_queue_checkpoint"
)
PROFILE_DEPENDENCY_BUILDER = (
    "Tools.tests.fixtures.integration.update_queue_checkpoints."
    "install_update_queue_profile"
)
_TEMPLATES = {}


def install_update_queue_profile(destination, scenario):
    """Rebuild the one current Profile dependency for a stored after-image."""
    if scenario not in CHECKPOINTS:
        raise ValueError("unknown update_queue checkpoint scenario")
    install_loadable_profile(destination)


def _validated_manifest(scenario):
    checkpoint_root, manifest_path = CHECKPOINTS[scenario]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": 1,
        "checkpoint_id": "update-queue-%s-current" % scenario,
        "scenario": scenario,
        "current_contract_owner": (
            "Tools.execution.task_runtime.runtime_validation."
            "validate_runtime"
        ),
        "generator": GENERATOR,
        "persisted_paths": list(PERSISTED_PATHS),
        "dependency_builder": BASE_PROFILE_DEPENDENCY_BUILDER,
        "scenario_dependency_builder": PROFILE_DEPENDENCY_BUILDER,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise AssertionError(
                "update_queue checkpoint %s has stale %s" %
                (scenario, field))
    records = file_records(checkpoint_root)
    if manifest.get("files") != records:
        raise AssertionError(
            "update_queue checkpoint %s file manifest is stale" % scenario)
    if manifest.get("tree_sha256") != tree_sha256(records):
        raise AssertionError(
            "update_queue checkpoint %s tree fingerprint is stale" %
            scenario)
    return checkpoint_root, manifest


def _validated_checkpoint_template(scenario):
    """Reconstruct and validate one static after-image once per process."""
    if scenario not in CHECKPOINTS:
        raise ValueError("unknown update_queue checkpoint scenario")
    if scenario in _TEMPLATES:
        _holder, root, artifacts = _TEMPLATES[scenario]
        return root, artifacts
    checkpoint_root, manifest = _validated_manifest(scenario)
    holder = tempfile.TemporaryDirectory()
    root = Path(holder.name) / "repo"
    shutil.copytree(checkpoint_root, root)
    install_update_queue_profile(root, scenario)
    reconstructed = file_records(root)
    if manifest.get("validated_tree_sha256") != \
            tree_sha256(reconstructed):
        raise AssertionError(
            "update_queue checkpoint dependencies changed; regenerate it")
    result = runtime_validation.validate_runtime(root)
    if result["errors"]:
        raise AssertionError(
            "update_queue checkpoint %s fails the current runtime contract: "
            "%s" % (scenario, result["errors"]))
    artifacts = manifest.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        raise AssertionError(
            "update_queue checkpoint artifacts must be a mapping")
    _TEMPLATES[scenario] = (holder, root, dict(artifacts))
    return root, dict(artifacts)


def install_update_queue_checkpoint(destination, scenario):
    """Give one test a private copy of a validated adjacent checkpoint."""
    source, artifacts = _validated_checkpoint_template(scenario)
    shutil.copytree(source, Path(destination))
    return dict(artifacts)


__all__ = [
    "CHECKPOINTS",
    "GENERATOR",
    "PROFILE_DEPENDENCY_BUILDER",
    "install_update_queue_checkpoint",
    "install_update_queue_profile",
]
