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
import subprocess
import sys
import tempfile
import unittest

import Tools.execution.task_runtime.runtime_validation as runtime_validation
from Tools.execution.task_runtime import runtime_paths
from Tools.platform.common import kblib
from Tools.platform.agent_interface import agent_interface_contract
from Tools.platform.distribution import upstream_component_boundary as component_boundary
from Tools.platform.distribution.test_runner import measured, measure_scope
from Tools.tests.support.initial_task_plan_fixture import confirmed_initial_task_plan
from Tools.tests.support.coverage_delta_fixture import premerge_delta_document
from Tools.tests.support.mcp_stdio_session import MCPStdioSession
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
)


@measured("e2e-phase", "task-plan-to-queue")
def initialize_task_plan_scenario(walker):
    """Publish real initial planning and Queue transactions in an empty root.

    Only Profile/Standards adoption uses its existing fixture owner. Task,
    Coverage, Queue and their Receipts do not exist until their actual writer
    runs. This prologue belongs exclusively to the representative E2E.
    """
    walker.root.mkdir(parents=True)
    def dependencies(root, _profile):
        # A Runner executes an adopter's carried Tools, not the source
        # distribution's MCP transport over an incomplete fixture workspace.
        # Stage this one E2E surface before adoption, deriving omissions from
        # the distribution owner; local checkpoint tests do not do this.
        repository = Path(__file__).resolve().parents[4]
        shutil.copytree(repository / "kernel", root / "kernel", dirs_exist_ok=True)
        boundary = (repository / "distribution-boundary.yaml").read_bytes()
        omitted = component_boundary._distribution_only_paths(boundary)
        tracked = subprocess.check_output(
            ["git", "ls-files", "-z", "--", "Tools"], cwd=repository).decode("utf-8").split("\0")
        for relative in filter(None, tracked):
            if component_boundary._may_be_omitted(relative, omitted):
                continue
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repository / relative, destination)
        (root / "distribution-boundary.yaml").write_bytes(boundary)
        for script, arguments in (
                ("compile_cli_contract.py", ["--projection-target", "carried-runtime"]),
                ("render_interface_projection.py", ["--projection-target", "carried-runtime"])):
            produced = subprocess.run(
                [sys.executable, "-B", str(root / "Tools" / script), str(root), *arguments],
                text=True, capture_output=True, check=False)
            walker.assertEqual(0, produced.returncode, (produced.stdout, produced.stderr))

    install_loadable_profile(walker.root, before_adoption=dependencies)
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
            "tier": getattr(walker, "TASK_PAGE_TIERS", {}).get(path, "S"),
            "priority": "P2", "next_batch": batch_id,
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
    walker.compile_profile_artifacts()
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

    def invoke_tool(self, name, *arguments):
        if not hasattr(self, "mcp_session"):
            server = self.root / "Tools/mcp_server.py"
            projection = self.root / runtime_paths.path_for("derived-mcp-tools")
            environment = {
                agent_interface_contract.INTERFACE_PROJECTION_ENV: str(projection.resolve()),
                agent_interface_contract.INTERFACE_SOURCE_HASH_ENV: kblib.sha256_file(projection),
            }
            self.mcp_session = MCPStdioSession(
                self.root, server=server,
                env_overrides=environment)
            self.mcp_session.__enter__()
            self.addCleanup(self.mcp_session.close)
            self.mcp_session.initialize()
        return self.mcp_session.run_cli(name, *arguments)

    def execute_runner(self, action, *, semantic_input=None, proposal=None):
        """Execute the observed action, with no direct producer fallback."""
        arguments = {"root": str(self.root), "execute": action["action_id"]}
        if semantic_input is not None:
            relative = runtime_paths.TRANSIENT_ROOT + "/e2e-action-input.json"
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(semantic_input), encoding="utf-8")
            arguments["input"] = relative
        if proposal is not None:
            arguments["proposal"] = proposal
        with measure_scope("runner-action", action["token"]):
            envelope = self.mcp_session.call_checked("run_task", arguments)
        execution = envelope["stdout_json"]
        self.assertEqual(0, execution["returncode"], execution)
        self.assertIsNone(execution["next_action_error"], execution)
        self.assertIsNotNone(execution["next_action"], execution)
        for child in execution["substeps"]:
            self.assertEqual([], child["invocation_errors"], child)
            self.assertTrue(child["observation"]["output_reliable"], child)
            self.assertTrue(child["observation"]["invocation_reliable"], child)
        self.runner_trace.append({
            "action": action["token"], "batch": action["target"].get("batch_id"),
            "substeps": [child["tool"] for child in execution["substeps"]],
        })
        return execution

    def proposal_path(self, batch_id, object_path):
        # Only authoring decisions: the producer resolves every evidence ID.
        proposal = premerge_delta_document(
            batch_id, object_path, [], generated_at="2026-08-04T00:00:00Z")
        proposal["pages"][0].pop("gate_receipts")
        relative = runtime_paths.TRANSIENT_ROOT + "/%s-proposal.yaml" % batch_id
        absolute = self.root / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_text(kblib.canonical_yaml(proposal), encoding="utf-8")
        return relative

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # Host binding and the carried compiler must share one root spelling,
        # including on macOS where /var is a symlink to /private/var.
        self.root = (Path(self.temporary.name) / "repo").resolve()
        self.scenario = initialize_task_plan_scenario(self)
