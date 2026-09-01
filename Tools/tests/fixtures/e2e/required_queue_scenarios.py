"""Required Queue E2E scenario base and checkpoint materializer.

This is the only fixture layer in this hierarchy allowed to start a test that
will execute a complete lifecycle.  It copies its declared starting scenario
once; unlike the former E2E ``setUp`` it never creates a disposable base tree
and then immediately replaces it with a second scenario copy.
"""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

import Tools.execution.task_runtime.runtime_validation as runtime_validation
from Tools.tests.fixtures.integration.checkpoint_contract import (
    PERSISTED_PATHS,
    PROFILE_DEPENDENCY_BUILDER,
    file_records,
    tree_sha256,
)
from Tools.tests.fixtures.integration.required_queue_checkpoints import (
    TERMINAL_CHECKPOINT_DEPENDENCY_BUILDER,
)
from Tools.tests.support.required_queue_fixture import (
    RequiredQueueFixture,
    RequiredQueueLifecycleDriver,
    _template,
)


def write_validated_checkpoint_directory(
        root, destination, manifest_path, *, checkpoint_id, scenario,
        dependency_builder=PROFILE_DEPENDENCY_BUILDER):
    """Copy E2E-produced bytes and write their reproducible manifest."""
    result = runtime_validation.validate_runtime(root)
    if result["errors"]:
        raise AssertionError(
            "cannot materialize invalid checkpoint: %s" % result["errors"])
    if destination.exists():
        raise FileExistsError(
            "checkpoint destination already exists: %s" % destination)
    destination.mkdir(parents=True)
    for relative in PERSISTED_PATHS:
        source = root / relative
        target = destination / relative
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(
                "__pycache__", ".DS_Store"))
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        else:
            raise AssertionError(
                "checkpoint persisted path is missing: %s" % relative)
    files = file_records(destination)
    validated_files = file_records(root)
    manifest = {
        "schema_version": 1,
        "checkpoint_id": checkpoint_id,
        "scenario": scenario,
        "current_contract_owner": (
            "Tools.execution.task_runtime.runtime_validation."
            "validate_runtime"),
        "generator": (
            "Tools.tests.fixtures.e2e.required_queue_scenarios."
            "generate_required_queue_checkpoint"),
        "generator_command": (
            "python3 -m Tools.tests.fixtures.e2e."
            "generate_required_queue_checkpoint "
            "--scenario %s --output <checkpoint-dir> "
            "--manifest <manifest.json>" % scenario),
        "persisted_paths": list(PERSISTED_PATHS),
        "dependency_builder": dependency_builder,
        "tree_sha256": tree_sha256(files),
        "validated_tree_sha256": tree_sha256(validated_files),
        "files": files,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def generate_required_queue_checkpoint(scenario, destination, manifest_path):
    """Run one named E2E prologue and materialize its validated checkpoint."""
    if scenario not in (
            "maintenance-closed", "closed-both", "terminal-closed"):
        raise ValueError("unsupported Required Queue checkpoint scenario")
    driver = None
    try:
        if scenario == "terminal-closed":
            driver = RequiredQueueLifecycleDriver(methodName="runTest")
            driver.setUp()
            driver.install_terminal_proof_environment()
            driver.merge_and_close("B1", "Topics/A.md")
            driver.merge_and_close("B2", "Topics/B.md")
            root = driver.root
        else:
            root, _artifacts = _template(scenario)
        write_validated_checkpoint_directory(
            root, Path(destination), Path(manifest_path),
            checkpoint_id="%s-current" % scenario,
            scenario=scenario,
            dependency_builder=(
                TERMINAL_CHECKPOINT_DEPENDENCY_BUILDER
                if scenario == "terminal-closed"
                else PROFILE_DEPENDENCY_BUILDER),
        )
    finally:
        if driver is not None:
            driver.tearDown()


def generate_maintenance_closed_checkpoint(destination, manifest_path):
    """Stable convenience name for this round's one generated artifact."""
    generate_required_queue_checkpoint(
        "maintenance-closed", destination, manifest_path)


class RequiredQueueE2EScenarioCase(RequiredQueueFixture,
                                   unittest.TestCase):
    """A private starting tree for one representative complete lifecycle."""

    START_SCENARIO = "base"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        start_root, self.scenario = _template(self.START_SCENARIO)
        shutil.copytree(start_root, self.root)
