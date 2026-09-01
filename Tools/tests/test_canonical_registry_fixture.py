"""Coverage and isolation tests for the canonical registry fixture bundle."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from Tools.platform.distribution import module_boundary_facts
from Tools.tests.support.canonical_registry_fixture import (
    COMPONENT_MACHINE_REGISTRY_PATHS,
    ISOLATED_TOOL_REGISTRY_PATHS,
    KERNEL_MACHINE_REGISTRY_PATHS,
    contract_exception_owner_paths,
    install_isolated_tool_registry_bundle,
)


REPOSITORY = Path(__file__).resolve().parents[2]


class CanonicalRegistryFixtureTests(unittest.TestCase):

    def test_manifest_covers_every_kernel_machine_registry(self):
        actual = tuple(sorted(
            path.relative_to(REPOSITORY).as_posix()
            for path in (REPOSITORY / "kernel").rglob("*")
            if path.is_file() and path.suffix in (".json", ".yaml", ".yml")))
        self.assertEqual(
            actual, tuple(sorted(KERNEL_MACHINE_REGISTRY_PATHS)),
            "a Kernel machine authority was added or removed without updating "
            "the single isolated-fixture bundle manifest")

    def test_manifest_covers_card_and_read_set_machine_registries(self):
        actual = tuple(sorted(
            path.relative_to(REPOSITORY).as_posix()
            for directory in (REPOSITORY / "Card", REPOSITORY / "Read Set")
            for path in directory.rglob("*")
            if path.is_file() and path.suffix in (".json", ".yaml", ".yml")))
        self.assertEqual(
            actual, tuple(sorted(COMPONENT_MACHINE_REGISTRY_PATHS)),
            "a Card or Read Set machine contract was added or removed without "
            "updating the single isolated-fixture bundle manifest")

    def test_installer_copies_registry_and_declared_owner_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = install_isolated_tool_registry_bundle(root)
            expected = (ISOLATED_TOOL_REGISTRY_PATHS +
                        contract_exception_owner_paths())
            self.assertEqual(expected, installed)
            for relative in installed:
                with self.subTest(relative=relative):
                    self.assertEqual(
                        (REPOSITORY / relative).read_bytes(),
                        (root / relative).read_bytes())

    def test_representative_isolated_import_closure_uses_the_bundle(self):
        """Every newly registry-backed Tool family imports from scratch."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module_boundary_facts.stage_shipped_modules(
                str(REPOSITORY), str(root), [
                    "check_profile",       # Profile/control/audit/corpus/policy
                    "check_batch_close",   # batch-close/policy/corpus/runtime
                    "check_queue",         # control/runtime
                    "execution.planning.apply_task_plan",  # Task Plan owner
                ])
            install_isolated_tool_registry_bundle(root)
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(root / "Tools")
            completed = subprocess.run(
                [sys.executable, "-c",
                 "import check_profile, check_batch_close, check_queue, "
                 "execution.planning.apply_task_plan"],
                cwd=str(root), env=environment, capture_output=True,
                text=True, check=False)
            self.assertEqual(
                0, completed.returncode,
                completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
