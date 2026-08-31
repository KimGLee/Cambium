"""Static current-contract checkpoints for batch-close integrations.

The expensive Task/Queue/AuditPlan/Delta prologue is owned by the E2E
scenario generator.  Integration and recovery tests only reconstruct the
fixture's deterministic Profile/Tool dependency bundle, validate the stored
after-image, and copy that legal applied checkpoint per method.
"""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from Tools.execution.task_runtime import runtime_validation
from Tools.tests.fixtures.integration.checkpoint_contract import (
    PERSISTED_PATHS,
    file_records,
    tree_sha256,
)
from Tools.tests.support.batch_close_fixture import (
    BatchCloseRuntimeActions,
    CheckBatchCloseFixture,
)


CHECKPOINTS = {
    "applied": (
        Path(__file__).with_name("batch_close_applied_checkpoint"),
        Path(__file__).with_name(
            "batch_close_applied_checkpoint.manifest.json"),
    ),
    "applied-state-mutating": (
        Path(__file__).with_name(
            "batch_close_state_mutating_checkpoint"),
        Path(__file__).with_name(
            "batch_close_state_mutating_checkpoint.manifest.json"),
    ),
}
DEPENDENCY_BUILDER = (
    "Tools.tests.fixtures.integration.batch_close_checkpoints."
    "install_batch_close_dependencies"
)
GENERATOR = (
    "Tools.tests.fixtures.e2e.batch_close_scenarios."
    "generate_batch_close_checkpoint"
)
_DEPENDENCY_TEMPLATE = None
_VALIDATED_TEMPLATES = {}


def _dependency_template():
    """Build current deterministic dependencies once, without runtime use."""
    global _DEPENDENCY_TEMPLATE
    if _DEPENDENCY_TEMPLATE is None:
        holder = tempfile.TemporaryDirectory()
        root = Path(holder.name) / "repo"
        driver = CheckBatchCloseFixture("runTest")
        driver.root = root
        driver.build_repository_fixture()
        _DEPENDENCY_TEMPLATE = (holder, root)
    return _DEPENDENCY_TEMPLATE[1]


def install_batch_close_dependencies(destination, scenario="applied"):
    """Rebuild non-runtime dependencies for a stored adopter after-image."""
    destination = Path(destination)
    source_root = _dependency_template()
    for source in sorted(source_root.iterdir()):
        if source.name in PERSISTED_PATHS:
            continue
        target = destination / source.name
        if source.is_dir():
            shutil.copytree(
                source, target,
                ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"),
            )
        else:
            shutil.copy2(source, target)
    if scenario == "applied-state-mutating":
        script = destination / "Tools/fixture_residual.py"
        script.write_text(
            script.read_text(encoding="utf-8") +
            "with open(os.path.join(a.root,'.cambium/state/"
            "coverage_ledger.yaml'),'a',encoding='utf-8') as fh:\n"
            "    fh.write('\\n')\n",
            encoding="utf-8",
        )


def _validate_manifest(scenario):
    checkpoint_root, manifest_path = CHECKPOINTS[scenario]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": 1,
        "checkpoint_id": "batch-close-%s-current" % scenario,
        "scenario": scenario,
        "current_contract_owner": (
            "Tools.execution.task_runtime.runtime_validation."
            "validate_runtime"
        ),
        "generator": GENERATOR,
        "persisted_paths": list(PERSISTED_PATHS),
        "dependency_builder": DEPENDENCY_BUILDER,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise AssertionError(
                "batch-close checkpoint %s has stale %s" %
                (scenario, field))
    records = file_records(checkpoint_root)
    if manifest.get("files") != records:
        raise AssertionError(
            "batch-close checkpoint %s file manifest is stale" % scenario)
    if manifest.get("tree_sha256") != tree_sha256(records):
        raise AssertionError(
            "batch-close checkpoint %s tree fingerprint is stale" %
            scenario)
    return checkpoint_root, manifest


def _validated_checkpoint_template(scenario):
    """Reconstruct and validate one applied checkpoint once per process."""
    if scenario not in CHECKPOINTS:
        raise ValueError("unknown batch-close checkpoint scenario")
    if scenario in _VALIDATED_TEMPLATES:
        _holder, root, artifacts = _VALIDATED_TEMPLATES[scenario]
        return root, artifacts
    checkpoint_root, manifest = _validate_manifest(scenario)
    holder = tempfile.TemporaryDirectory()
    root = Path(holder.name) / "repo"
    shutil.copytree(checkpoint_root, root)
    install_batch_close_dependencies(root, scenario)
    reconstructed = file_records(root)
    if manifest.get("validated_tree_sha256") != \
            tree_sha256(reconstructed):
        raise AssertionError(
            "batch-close checkpoint dependencies changed; regenerate it")
    result = runtime_validation.validate_runtime(root)
    if result["errors"]:
        raise AssertionError(
            "batch-close checkpoint fails the current runtime contract: %s" %
            result["errors"])
    artifacts = dict(manifest.get("artifacts") or {})
    _VALIDATED_TEMPLATES[scenario] = (holder, root, artifacts)
    return root, dict(artifacts)


def install_batch_close_checkpoint(destination, scenario="applied"):
    """Give one test a private copy of a validated applied checkpoint."""
    source, artifacts = _validated_checkpoint_template(scenario)
    shutil.copytree(source, Path(destination))
    return dict(artifacts)


class BatchCloseCheckpointCase(BatchCloseRuntimeActions, unittest.TestCase):
    """Private per-method copy of one validated static applied checkpoint."""

    SCENARIO = "applied"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.scenario = install_batch_close_checkpoint(
            self.root, self.SCENARIO)
        self.delta_apply_receipt = self.scenario["delta_apply_receipt"]


class StateMutatingBatchCloseCheckpointCase(BatchCloseCheckpointCase):
    """Applied checkpoint whose registered verifier mutates runtime state."""

    SCENARIO = "applied-state-mutating"


__all__ = [
    "BatchCloseCheckpointCase",
    "CHECKPOINTS",
    "DEPENDENCY_BUILDER",
    "GENERATOR",
    "StateMutatingBatchCloseCheckpointCase",
    "install_batch_close_checkpoint",
    "install_batch_close_dependencies",
]
