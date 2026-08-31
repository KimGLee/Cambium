"""Required Queue Integration checkpoint cases.

The base checkpoint remains suitable for tests that need to exercise one
adjacent transition.  The maintenance checkpoint is a materialized result of
the real E2E builder: tests decode its bytes and validate them against the
current runtime contract, but never replay the batches that produced it.
"""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_validation as runtime_validation
from Tools.tests.support.required_queue_fixture import (
    RequiredQueueFixture,
    _template,
    install_terminal_checkpoint_dependencies,
)
from Tools.tests.support.profile_fixture import install_loadable_profile
from Tools.tests.fixtures.integration.checkpoint_contract import (
    PERSISTED_PATHS,
    PROFILE_DEPENDENCY_BUILDER,
    file_records,
    tree_sha256,
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
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise AssertionError("checkpoint bundle schema_version must be 1")
    if manifest.get("checkpoint_id") != checkpoint_id:
        raise AssertionError("unexpected checkpoint identity")
    if manifest.get("scenario") != scenario:
        raise AssertionError("unexpected checkpoint scenario")
    if manifest.get("current_contract_owner") != (
            "Tools.execution.task_runtime.runtime_validation."
            "validate_runtime"):
        raise AssertionError("unexpected checkpoint validator owner")
    if manifest.get("generator") != (
            "Tools.tests.fixtures.e2e.required_queue_scenarios."
            "generate_required_queue_checkpoint"):
        raise AssertionError("unexpected checkpoint generator owner")
    if manifest.get("persisted_paths") != list(PERSISTED_PATHS):
        raise AssertionError("unexpected checkpoint persisted boundary")
    if manifest.get("dependency_builder") != dependency_builder:
        raise AssertionError("unexpected checkpoint dependency builder")
    command = manifest.get("generator_command")
    if (not isinstance(command, str) or
            "--scenario %s" % scenario not in command):
        raise AssertionError("checkpoint regeneration command is missing")
    records = file_records(checkpoint_root)
    if manifest.get("files") != records:
        raise AssertionError("checkpoint file manifest is stale")
    if manifest.get("tree_sha256") != tree_sha256(records):
        raise AssertionError("checkpoint tree fingerprint is stale")
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
        validate_checkpoint(
            cls.CHECKPOINT_ROOT, cls.CHECKPOINT_MANIFEST,
            checkpoint_id=cls.CHECKPOINT_ID, scenario=cls.SCENARIO,
            dependency_builder=cls.DEPENDENCY_BUILDER)
        shutil.copytree(
            cls.CHECKPOINT_ROOT, cls._validated_checkpoint_root)
        cls.DEPENDENCY_INSTALLER(cls._validated_checkpoint_root)
        reconstructed = file_records(
            cls._validated_checkpoint_root)
        manifest = json.loads(
            cls.CHECKPOINT_MANIFEST.read_text(encoding="utf-8"))
        if manifest.get("validated_tree_sha256") != \
                tree_sha256(reconstructed):
            raise AssertionError(
                "checkpoint dependencies no longer reproduce the validated "
                "runtime tree; regenerate the checkpoint")
        cls._validated_checkpoint_runtime = \
            runtime_validation.validate_runtime(
                cls._validated_checkpoint_root)
        if cls._validated_checkpoint_runtime["errors"]:
            raise AssertionError(
                "checkpoint fails the current runtime contract: %s" %
                cls._validated_checkpoint_runtime["errors"])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
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
