"""Generate validated Integration checkpoints from real Queue lifecycles.

Only this E2E fixture producer may replay the expensive AuditPlan and Receipt
chain.  Integration tests consume the persisted after-image through the
current runtime validator instead of rebuilding that history in every test
process.
"""

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import Tools.execution.task_runtime.runtime_validation as runtime_validation
from Tools.tests.fixtures.integration.checkpoint_contract import (
    PERSISTED_PATHS,
    PROFILE_DEPENDENCY_BUILDER as BASE_PROFILE_DEPENDENCY_BUILDER,
    file_records,
    tree_sha256,
)
from Tools.tests.support.update_queue_fixture import (
    FIXTURE as UPDATE_QUEUE_BASE_FIXTURE,
    UpdateQueueFixture,
)
from Tools.tests.fixtures.integration.update_queue_checkpoints import (
    PROFILE_DEPENDENCY_BUILDER,
    install_update_queue_profile,
)


SUPPORTED_SCENARIOS = frozenset((
    "open-b1",
    "planning-ready",
    "merge-admission-b1",
    "merged-b1",
))
ARTIFACT_KEYS = {
    "open-b1": (),
    "planning-ready": ("ready_gate",),
    "merge-admission-b1": ("delta_path", "batch_receipt"),
    "merged-b1": (),
}


class _ScenarioWalker(UpdateQueueFixture, unittest.TestCase):
    """Assertion-capable E2E producer with no discoverable test methods."""

    def _walk(self):
        raise NotImplementedError("never scheduled as a test")

    @classmethod
    def at(cls, root):
        walker = cls("_walk")
        walker.root = root
        return walker


def _build_base(walker, inherited):
    shutil.copytree(UPDATE_QUEUE_BASE_FIXTURE, walker.root)
    install_update_queue_profile(walker.root, "merged-b1")
    for name in ("deltas", "receipts", "reports"):
        (walker.root / ".cambium" / name).mkdir(exist_ok=True)
    walker.install_plain_s_audit_fixture()


def _build_planning_ready(walker, inherited):
    return {"ready_gate": walker.queue_gate("--require-ready", "B1")}


def _build_open_b1(walker, inherited):
    completed = walker.open_b1()
    return {"open_code": completed.returncode,
            "open_stdout": completed.stdout}


def _build_merge_admission_b1(walker, inherited):
    closure = walker.prepare_merge_ready_closure("B1", "Topics/A.md")
    return {
        "delta_path": closure["delta_path"],
        "batch_receipt": closure["batch_receipt"],
    }


def _build_merged_b1(walker, inherited):
    revision, fingerprint = walker.expected()
    completed = walker.command(
        "--id", "B1", "--transition", "merge-ready",
        "--delta-path", inherited["delta_path"],
        "--batch-receipt", inherited["batch_receipt"],
        "--expected-state-revision", revision,
        "--expected-sha256", fingerprint,
        "--actor-role", "integrator", "--apply")
    walker.assertEqual(0, completed.returncode, completed.stdout)
    return {"merge_code": completed.returncode,
            "merge_stdout": completed.stdout}


_TEMPLATE_PARENTS = {
    "base": None,
    "planning-ready": "base",
    "open-b1": "base",
    "merge-admission-b1": "open-b1",
    "merged-b1": "merge-admission-b1",
}
_TEMPLATE_BUILDERS = {
    "base": _build_base,
    "planning-ready": _build_planning_ready,
    "open-b1": _build_open_b1,
    "merge-admission-b1": _build_merge_admission_b1,
    "merged-b1": _build_merged_b1,
}
_TEMPLATES = {}


def _dynamic_template(name):
    """Build one E2E checkpoint from real producers once per process."""
    if name not in _TEMPLATES:
        holder = tempfile.TemporaryDirectory()
        root = Path(holder.name) / "repo"
        artifacts = {}
        parent = _TEMPLATE_PARENTS[name]
        if parent is not None:
            parent_root, parent_artifacts = _dynamic_template(parent)
            artifacts.update(parent_artifacts)
            shutil.copytree(parent_root, root)
        walker = _ScenarioWalker.at(root)
        artifacts.update(_TEMPLATE_BUILDERS[name](walker, artifacts) or {})
        _TEMPLATES[name] = (holder, root, artifacts)
    _holder, root, artifacts = _TEMPLATES[name]
    return root, artifacts


def generate_update_queue_checkpoint(
        scenario, destination, manifest_path):
    """Replay one named E2E prologue and persist its validated after-image."""
    if scenario not in SUPPORTED_SCENARIOS:
        raise ValueError("unsupported update_queue checkpoint scenario")
    root, artifacts = _dynamic_template(scenario)
    result = runtime_validation.validate_runtime(root)
    if result["errors"]:
        raise AssertionError(
            "cannot materialize invalid update_queue checkpoint: %s" %
            result["errors"])

    destination = Path(destination)
    manifest_path = Path(manifest_path)
    if destination.exists() or manifest_path.exists():
        raise FileExistsError(
            "checkpoint output already exists; generate into an empty path")
    destination.mkdir(parents=True)
    for relative in PERSISTED_PATHS:
        source = root / relative
        target = destination / relative
        if source.is_dir():
            shutil.copytree(
                source, target,
                ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        else:
            raise AssertionError(
                "checkpoint persisted path is missing: %s" % relative)

    files = file_records(destination)
    selected_artifacts = {
        key: artifacts[key] for key in ARTIFACT_KEYS[scenario]
    }
    manifest = {
        "schema_version": 1,
        "checkpoint_id": "update-queue-%s-current" % scenario,
        "scenario": scenario,
        "current_contract_owner": (
            "Tools.execution.task_runtime.runtime_validation."
            "validate_runtime"),
        "generator": (
            "Tools.tests.fixtures.e2e.update_queue_scenarios."
            "generate_update_queue_checkpoint"),
        "generator_command": (
            "python3 -m Tools.tests.fixtures.e2e.update_queue_scenarios "
            "--scenario %s --output <checkpoint-dir> "
            "--manifest <manifest.json>" % scenario),
        "persisted_paths": list(PERSISTED_PATHS),
        "dependency_builder": BASE_PROFILE_DEPENDENCY_BUILDER,
        "scenario_dependency_builder": PROFILE_DEPENDENCY_BUILDER,
        "tree_sha256": tree_sha256(files),
        "validated_tree_sha256": tree_sha256(file_records(root)),
        "files": files,
        "artifacts": selected_artifacts,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True,
                        choices=tuple(sorted(SUPPORTED_SCENARIOS)))
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    generate_update_queue_checkpoint(
        args.scenario, args.output, args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
