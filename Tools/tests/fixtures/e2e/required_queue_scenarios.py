"""Required Queue E2E scenario base and checkpoint materializer.

This is the only fixture layer in this hierarchy allowed to start a test that
will execute a complete lifecycle.  It copies its declared starting scenario
once; unlike the former E2E ``setUp`` it never creates a disposable base tree
and then immediately replaces it with a second scenario copy.
"""

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import Tools.execution.task_runtime.runtime_validation as runtime_validation
from Tools.execution.task_runtime import runtime_paths
from Tools.platform.common import kblib
from Tools.tests.support.initial_task_plan_fixture import confirmed_initial_task_plan
from Tools.tests.support.profile_fixture import (
    FIXTURE_UPSTREAM_REVISION, install_loadable_profile,
)
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
    install_terminal_proof_dependencies,
)


def initialize_task_plan_scenario(walker):
    """Publish real initial planning and Queue transactions in an empty root.

    Only Profile/Standards adoption uses its existing fixture owner. Task,
    Coverage, Queue and their Receipts do not exist until their actual writer
    runs. This prologue belongs exclusively to the representative E2E.
    """
    walker.root.mkdir(parents=True)
    install_loadable_profile(walker.root, before_adoption=lambda root, _profile:
                             install_terminal_proof_dependencies(root))
    walker.write_plain_s_audit_pages()
    plan = confirmed_initial_task_plan(
        upstream_revision_id=FIXTURE_UPSTREAM_REVISION,
        profile_manifest="profiles/test-profile/profile.toml",
        task_id="fixture-task", plan_id="TP-e2e-initial",
        objective="Complete fixture Required Queue batches with durable evidence.",
        exclusions=["Do not modify profile policy."])
    plan["contract_after"]["selected_route_ids"] = ["R01", "R03", "R08", "R12"]
    page_base = plan["planned_work"]["pages"][0]
    batch_base = plan["planned_work"]["batch_specs"][0]
    plan["planned_work"] = {"pages": [], "batch_specs": []}
    for order, name in enumerate(("A", "B"), 1):
        path, batch_id = "Topics/%s.md" % name, "B%d" % order
        plan["planned_work"]["pages"].append({
            **copy.deepcopy(page_base), "path": path, "canonical_owner": path,
            "tier": "S", "priority": "P2", "next_batch": batch_id,
            "prerequisites": [] if order == 1 else ["Topics/A.md"],
        })
        plan["planned_work"]["batch_specs"].append({
            **copy.deepcopy(batch_base), "id": batch_id, "family": "Core",
            "order_hint": order, "source_route": "R03",
            "depends_on": [] if order == 1 else ["B1"],
        })
    plan_path = runtime_paths.TASK_PLAN_DELTA_ROOT + "/" + plan["plan_id"] + ".yaml"
    absolute = walker.root / plan_path
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
    for path in (runtime_paths.QUEUE_PATH, runtime_paths.COVERAGE_PATH,
                 runtime_paths.PROGRESS_PATH):
        walker.assertFalse((walker.root / path).exists(), path)
    initialized = walker.run_tool("init_state.py", "--plan", plan_path, "--apply", "--json")
    walker.assertEqual(0, initialized.returncode, initialized.stdout)
    queue = kblib.load_yaml_file(walker.root / runtime_paths.QUEUE_PATH)
    progress = kblib.load_yaml_file(walker.root / runtime_paths.PROGRESS_PATH)
    planning_receipt = progress["initial_task_plan_receipt"]
    walker.assertEqual([], queue["required_queue"])
    materialized = walker.run_tool(
        "compile_queue.py", "--apply", "--actor-role", "integrator", "--json",
        "--expected-queue-revision", str(queue["queue_revision"]),
        "--expected-state-revision", str(queue["state_revision"]),
        "--expected-sha256", kblib.sha256_file(walker.root / runtime_paths.QUEUE_PATH),
        "--expected-coverage-sha256", kblib.sha256_file(walker.root / runtime_paths.COVERAGE_PATH),
        "--expected-progress-sha256", kblib.sha256_file(walker.root / runtime_paths.PROGRESS_PATH))
    walker.assertEqual(0, materialized.returncode, materialized.stdout)
    result = runtime_validation.validate_runtime(walker.root)
    walker.assertEqual([], result["errors"])
    walker.assertEqual(planning_receipt, result["progress"]["initial_task_plan_receipt"])
    walker.assertEqual([("B1", "queued"), ("B2", "queued")],
        [(row["id"], row["state"]) for row in result["queue"]["required_queue"]])
    walker.compose_page_inputs()
    return {"initial_task_plan_receipt": planning_receipt, "initial_task_plan_path": plan_path}


def _portable_receipt_diagnostics(root):
    """Project optional Host diagnostics, not evidence, in generated test data.

    The production member contract does not consume source_command. Keep its
    diagnostic presence without publishing a developer's interpreter, checkout
    or temporary directory. This function never operates on adopter history;
    the E2E generator invokes it only on its disposable fixture after-image.
    """
    from Tools.execution.audit.batch_close_contract import (
        MEMBER_RECEIPT_TYPE_ID, current_receipt_errors,
    )

    for path in sorted((root / ".cambium/receipts").rglob("*.jsonl")):
        changed = False
        output = []
        for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
            if not line.strip():
                output.append(line)
                continue
            record = json.loads(line)
            if "source_command" in record:
                if record.get("receipt_type_id") != MEMBER_RECEIPT_TYPE_ID or current_receipt_errors(record):
                    raise AssertionError("unexpected source_command owner in generated checkpoint")
                record["source_command"] = ["<host-execution-command>"]
                output.append(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                changed = True
            else:
                output.append(line)
        if changed:
            path.write_text("".join(output), encoding="utf-8")


def write_validated_checkpoint_directory(
        root, destination, manifest_path, *, checkpoint_id, scenario,
        dependency_builder=PROFILE_DEPENDENCY_BUILDER):
    """Copy E2E-produced bytes and write their reproducible manifest."""
    _portable_receipt_diagnostics(root)
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
            driver.START_SCENARIO = "terminal-base"
            driver.setUp()
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


class RequiredQueueE2EScenarioCase(RequiredQueueFixture,
                                   unittest.TestCase):
    """A private starting tree for one representative complete lifecycle."""

    START_SCENARIO = "base"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        if self.START_SCENARIO == "initial-plan":
            self.scenario = initialize_task_plan_scenario(self)
            return
        start_root, self.scenario = _template(self.START_SCENARIO)
        shutil.copytree(start_root, self.root)
