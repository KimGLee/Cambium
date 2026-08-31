"""Generate batch-close Integration checkpoints from real E2E prologues."""

import argparse
import json
from pathlib import Path
import shutil
import tempfile

from Tools.execution.task_runtime import runtime_validation
from Tools.tests.fixtures.integration.batch_close_checkpoints import (
    CHECKPOINTS,
    DEPENDENCY_BUILDER,
    GENERATOR,
)
from Tools.tests.fixtures.integration.checkpoint_contract import (
    PERSISTED_PATHS,
    file_records,
    tree_sha256,
)
from Tools.tests.support.batch_close_fixture import CheckBatchCloseFixture
from Tools.tests.support.profile_fixture import (
    install_current_adoption_fixture,
)


def _build_scenario(scenario):
    holder = tempfile.TemporaryDirectory()
    root = Path(holder.name) / "repo"
    driver = CheckBatchCloseFixture("runTest")
    driver.root = root
    driver.build_repository_fixture()
    if scenario == "applied-state-mutating":
        script = root / "Tools/fixture_residual.py"
        script.write_text(
            script.read_text(encoding="utf-8") +
            "with open(os.path.join(a.root,'.cambium/state/"
            "coverage_ledger.yaml'),'a',encoding='utf-8') as fh:\n"
            "    fh.write('\\n')\n",
            encoding="utf-8",
        )
        install_current_adoption_fixture(
            root, root / "profiles/test-profile", replace_current=True)
    driver.prepare_applied_batch()
    return holder, root, {
        "delta_apply_receipt": driver.delta_apply_receipt,
    }


def generate_batch_close_checkpoint(scenario, destination, manifest_path):
    """Replay one prologue once and persist its validated applied after-image."""
    if scenario not in CHECKPOINTS:
        raise ValueError("unsupported batch-close checkpoint scenario")
    holder, root, artifacts = _build_scenario(scenario)
    try:
        result = runtime_validation.validate_runtime(root)
        if result["errors"]:
            raise AssertionError(
                "cannot materialize invalid batch-close checkpoint: %s" %
                result["errors"])

        destination = Path(destination)
        manifest_path = Path(manifest_path)
        if destination.exists() or manifest_path.exists():
            raise FileExistsError(
                "checkpoint output already exists; use an empty path")
        destination.mkdir(parents=True)
        for relative in PERSISTED_PATHS:
            source = root / relative
            target = destination / relative
            if source.is_dir():
                shutil.copytree(
                    source, target,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", ".DS_Store"),
                )
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

        files = file_records(destination)
        manifest = {
            "schema_version": 1,
            "checkpoint_id": "batch-close-%s-current" % scenario,
            "scenario": scenario,
            "current_contract_owner": (
                "Tools.execution.task_runtime.runtime_validation."
                "validate_runtime"
            ),
            "generator": GENERATOR,
            "generator_command": (
                "python3 -m Tools.tests.fixtures.e2e."
                "batch_close_scenarios --scenario %s --output "
                "<checkpoint-dir> --manifest <manifest.json>" % scenario
            ),
            "persisted_paths": list(PERSISTED_PATHS),
            "dependency_builder": DEPENDENCY_BUILDER,
            "tree_sha256": tree_sha256(files),
            "validated_tree_sha256": tree_sha256(file_records(root)),
            "files": files,
            "artifacts": artifacts,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        holder.cleanup()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario", required=True, choices=tuple(sorted(CHECKPOINTS)))
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    generate_batch_close_checkpoint(
        args.scenario, args.output, args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
