"""Required Queue Integration checkpoint cases.

The base checkpoint remains suitable for tests that need to exercise one
adjacent transition.  The maintenance checkpoint is a materialized result of
the real E2E builder: tests decode its bytes and validate them against the
current runtime contract, but never replay the batches that produced it.
"""

from pathlib import Path
import shutil
import tempfile
import unittest

from Tools.execution.task_runtime import queue_runtime
from Tools.tests.support.required_queue_fixture import (
    RequiredQueueFixture,
    _template,
    install_terminal_checkpoint_dependencies,
)
from Tools.tests.support.profile_fixture import install_loadable_profile
from Tools.platform.distribution.test_runner import measure_scope
from Tools.tests.fixtures.integration.checkpoint_contract import (
    PERSISTED_PATHS,
    PROFILE_DEPENDENCY_BUILDER,
    validate_checkpoint_manifest,
    reconstruct_checkpoint,
)


MAINTENANCE_CLOSED_CHECKPOINT = Path(__file__).with_name(
    "maintenance_closed_checkpoint")
MAINTENANCE_CLOSED_MANIFEST = Path(__file__).with_name(
    "maintenance_closed_checkpoint.manifest.json")
TERMINAL_CLOSED_CHECKPOINT = Path(__file__).with_name(
    "terminal_closed_checkpoint")
TERMINAL_CLOSED_MANIFEST = Path(__file__).with_name(
    "terminal_closed_checkpoint.manifest.json")
TERMINAL_CHECKPOINT_DEPENDENCY_BUILDER = (
    "Tools.tests.support.required_queue_fixture."
    "install_terminal_checkpoint_dependencies")


def validate_checkpoint(
        checkpoint_root, manifest_path, *, checkpoint_id, scenario,
        dependency_builder=PROFILE_DEPENDENCY_BUILDER):
    """Verify generated provenance and every inspectable source file."""
    manifest = validate_checkpoint_manifest(checkpoint_root, manifest_path, {
        "schema_version": 1,
        "checkpoint_id": checkpoint_id,
        "scenario": scenario,
        "current_contract_owner": "Tools.execution.task_runtime.runtime_validation.validate_runtime",
        "generator": "Tools.tests.fixtures.e2e.required_queue_scenarios.generate_required_queue_checkpoint",
        "persisted_paths": list(PERSISTED_PATHS),
        "dependency_builder": dependency_builder,
    })
    command = manifest.get("generator_command")
    if (not isinstance(command, str) or
            "--scenario %s" % scenario not in command):
        raise AssertionError("checkpoint regeneration command is missing")
    return manifest


def _maintenance_evidence_artifacts(result):
    """Derive evidence identities from their current machine-owned checks."""
    expected = {
        "maintenance_budget_manifest": "budget_receipt",
        "maintenance_ledger_advanced": "ledger_receipt",
        "maintenance_watermark_advanced": "watermark_receipt",
    }
    artifacts = {}
    catalog = queue_runtime.current_receipt_catalog(result)
    for receipt_id, (_path, receipt) in catalog.items():
        key = expected.get(receipt.get("check"))
        if key is not None:
            if key in artifacts:
                raise AssertionError(
                    "checkpoint contains duplicate %s" % receipt.get("check"))
            artifacts[key] = receipt_id
    missing = sorted(set(expected.values()) - set(artifacts))
    if missing:
        raise AssertionError(
            "checkpoint lacks maintenance evidence: %s" % ", ".join(missing))
    return artifacts


class RequiredQueueBaseCheckpointCase(RequiredQueueFixture,
                                      unittest.TestCase):
    """Private copy of the validated base checkpoint for one Integration."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        base_root, self.scenario = _template("base")
        with measure_scope("checkpoint", "copy-private"):
            shutil.copytree(base_root, self.root)


class GeneratedRequiredQueueCheckpointCase(RequiredQueueFixture,
                                           unittest.TestCase):
    """Base for current-contract checkpoints produced by the E2E builder."""

    CHECKPOINT_ROOT = None
    CHECKPOINT_MANIFEST = None
    CHECKPOINT_ID = None
    SCENARIO = None
    DEPENDENCY_BUILDER = PROFILE_DEPENDENCY_BUILDER
    DEPENDENCY_INSTALLER = staticmethod(install_loadable_profile)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._checkpoint_temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._checkpoint_temporary.cleanup)
        cls._validated_checkpoint_root = Path(
            cls._checkpoint_temporary.name) / "repo"
        manifest = validate_checkpoint(
            cls.CHECKPOINT_ROOT, cls.CHECKPOINT_MANIFEST,
            checkpoint_id=cls.CHECKPOINT_ID, scenario=cls.SCENARIO,
            dependency_builder=cls.DEPENDENCY_BUILDER)
        cls._validated_checkpoint_runtime = reconstruct_checkpoint(
            cls.CHECKPOINT_ROOT, cls._validated_checkpoint_root,
            manifest, cls.DEPENDENCY_INSTALLER)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        with measure_scope("checkpoint", "copy-private"):
            shutil.copytree(self._validated_checkpoint_root, self.root)


class MaintenanceClosedCheckpointCase(GeneratedRequiredQueueCheckpointCase):
    """One legal post-batch checkpoint for maintenance gate integrations."""

    CHECKPOINT_ROOT = MAINTENANCE_CLOSED_CHECKPOINT
    CHECKPOINT_MANIFEST = MAINTENANCE_CLOSED_MANIFEST
    CHECKPOINT_ID = "maintenance-closed-current"
    SCENARIO = "maintenance-closed"

    def setUp(self):
        super().setUp()
        self.scenario = _maintenance_evidence_artifacts(
            self._validated_checkpoint_runtime)

    def maintenance_evidence_ids(self):
        return (
            self.scenario["budget_receipt"],
            self.scenario["ledger_receipt"],
            self.scenario["watermark_receipt"],
        )


class TerminalClosedCheckpointCase(GeneratedRequiredQueueCheckpointCase):
    """One legal terminal-profile checkpoint with both batches closed."""

    CHECKPOINT_ROOT = TERMINAL_CLOSED_CHECKPOINT
    CHECKPOINT_MANIFEST = TERMINAL_CLOSED_MANIFEST
    CHECKPOINT_ID = "terminal-closed-current"
    SCENARIO = "terminal-closed"
    DEPENDENCY_BUILDER = TERMINAL_CHECKPOINT_DEPENDENCY_BUILDER
    DEPENDENCY_INSTALLER = staticmethod(
        install_terminal_checkpoint_dependencies)
