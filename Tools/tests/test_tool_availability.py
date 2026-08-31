"""Source-distribution and carried-runtime availability contracts.

Tool availability owns one deterministic boundary: which top-level Tool
modules a declared projection target may lack. Interface compilation,
rendering, transport, and complete distribution assembly have separate test
owners and are intentionally not replayed here.
"""

import tempfile
import unittest
from pathlib import Path

import Tools.platform.agent_interface.tool_availability as tool_availability
import Tools.platform.common.kblib as kblib


BOUNDARY_TEXT = (
    "distribution_only:\n"
    "  - path: Tools/source_only.py\n"
    "  - path: Tools/internal/package.py\n"
    "  - path: kernel/K00.md\n"
)


class BoundaryDeclarationContractTests(unittest.TestCase):

    def test_only_top_level_tool_modules_enter_the_excluded_set(self):
        document = {
            "distribution_only": [
                {"path": "Tools/source_only.py"},
                "Tools/second_source_only.py",
                {"path": r"Tools\windows_spelling.py"},
                {"path": "Tools/internal/package.py"},
                {"path": "kernel/K00.md"},
                {"path": "Tools/not_python.txt"},
            ],
        }

        self.assertEqual(
            {"second_source_only", "source_only", "windows_spelling"},
            tool_availability.excluded_tool_modules(document))

    def test_missing_boundary_list_is_refused(self):
        with self.assertRaisesRegex(
                tool_availability.AvailabilityError,
                "no distribution_only list"):
            tool_availability.excluded_tool_modules({})


class AvailabilityPartitionContractTests(unittest.TestCase):

    def test_target_permission_and_missing_module_partition_are_distinct(self):
        source = tool_availability.ToolAvailability(
            tool_availability.SOURCE_DISTRIBUTION,
            "sha256:" + "a" * 64, frozenset(),
            tool_availability.DEFAULT_BOUNDARY_PATH)
        carried = tool_availability.ToolAvailability(
            tool_availability.CARRIED_RUNTIME,
            "sha256:" + "a" * 64, {"source_only"},
            tool_availability.DEFAULT_BOUNDARY_PATH)
        declared = ["missing", "carried", "source_only", "carried"]
        present = ["carried"]

        self.assertEqual(
            (["carried"], [], ["missing", "source_only"]),
            source.partition(declared, present))
        self.assertEqual(
            (["carried"], ["source_only"], ["missing"]),
            carried.partition(declared, present))
        self.assertFalse(source.permits_missing("source_only"))
        self.assertTrue(carried.permits_missing("source_only"))

    def test_unknown_projection_target_is_refused_before_resolution(self):
        with self.assertRaisesRegex(
                tool_availability.AvailabilityError,
                "unknown projection target"):
            tool_availability.resolve("unused", "whatever-is-on-disk")


class BoundaryResolutionIntegrationTests(unittest.TestCase):

    def test_one_small_boundary_resolves_both_targets_and_binds_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            boundary = root / tool_availability.DEFAULT_BOUNDARY_PATH
            boundary.write_text(BOUNDARY_TEXT, encoding="utf-8")
            expected_sha = kblib.sha256_bytes(BOUNDARY_TEXT.encode("utf-8"))

            source = tool_availability.resolve(
                root, tool_availability.SOURCE_DISTRIBUTION)
            carried = tool_availability.resolve(
                root, tool_availability.CARRIED_RUNTIME)

            self.assertEqual(tool_availability.SOURCE_DISTRIBUTION,
                             source.target)
            self.assertEqual(frozenset(), source.excluded)
            self.assertEqual(tool_availability.CARRIED_RUNTIME,
                             carried.target)
            self.assertEqual(frozenset({"source_only"}), carried.excluded)
            self.assertEqual(expected_sha, source.boundary_sha256)
            self.assertEqual(expected_sha, carried.boundary_sha256)
            self.assertEqual(expected_sha,
                             tool_availability.boundary_sha256(root))
            self.assertEqual(tool_availability.DEFAULT_BOUNDARY_PATH,
                             carried.boundary_path)

            boundary.write_text(BOUNDARY_TEXT + "# drift\n",
                                encoding="utf-8")
            self.assertNotEqual(
                expected_sha, tool_availability.boundary_sha256(root))


if __name__ == "__main__":
    unittest.main()
