#!/usr/bin/env python3
"""Changed-path to required-verification impact contracts.

This suite owns only the planner's path classification and affected Tool test
closure. Test discovery/catalog correctness, test execution, Git transport,
repository-layout inspection, workflow output rendering, and shard balancing
have separate owners and are not replayed here. The CI execution adapter is
tested only for delegation to that shared runner.
"""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ci_impact", ROOT / ".github/scripts/ci_impact.py")
ci_impact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci_impact)

MARKDOWN_PREFIXES = ("kernel/", "Card/", "Read Set/", "profiles/")


class CiImpactFixture(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        sources = {
            "Tools/alpha.py": "VALUE = 1\n",
            "Tools/beta.py": "import alpha\n",
            "Tools/orphan.py": "VALUE = 2\n",
            "Tools/execution/audit/leaf.py": (
                "def main(argv=None):\n"
                "    return 0\n"),
            "Tools/execution/audit/consumer.py": (
                "import Tools.execution.audit.leaf as leaf\n"
                "VALUE = leaf.main([])\n"),
            "Tools/run_leaf.py": (
                "from Tools.execution.audit.leaf import main as _main\n"
                "IMPLEMENTATION_MODULE = 'Tools.execution.audit.leaf'\n"
                "def main(argv=None):\n"
                "    return _main(argv)\n"),
            "Tools/tests/test_alpha.py": "import alpha\n",
            "Tools/tests/test_beta.py": "import beta\n",
            "Tools/tests/test_consumer.py": (
                "import Tools.execution.audit.consumer\n"),
            "Tools/tests/test_leaf.py": (
                "from Tools.execution.audit import leaf\n"),
            "Tools/tests/test_run_leaf.py": "import run_leaf\n",
            "Tools/tests/test_charlie.py": "def test_charlie(): pass\n",
            "Tools/tests/test_mcp_server.py": "def test_transport(): pass\n",
            "Tools/tests/test_tools_readme_inventory.py": (
                "def test_inventory(): pass\n"),
        }
        for relative, text in sources.items():
            path = cls.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def plan(self, *changes, event="pull_request"):
        with mock.patch.object(
                ci_impact, "check_only_markdown_prefixes",
                return_value=MARKDOWN_PREFIXES):
            return ci_impact.plan_changes(
                self.root,
                [ci_impact.Change(status, path, old_path)
                 for status, path, old_path in changes],
                event=event)


class ChangedPathImpactContractTests(CiImpactFixture):

    def test_check_only_classes_use_the_ceiling_required_check(self):
        paths = (
            "README.md",
            "ROADMAP.zh-CN.md",
            "assets/readme/diagram.png",
            "Tools/compiled/example.json",
            "kernel/K00 Standards Control/README.md",
            "Card/R01 Core Bootstrap Card.md",
            "Read Set/R01 Core Bootstrap Read Set.md",
            "profiles/example/README.md",
        )
        for path in paths:
            with self.subTest(path=path):
                plan = self.plan(("M", path, ""))
                self.assertEqual("checks-only", plan["mode"])
                self.assertEqual(["3.14"], plan["check_versions"])
                self.assertEqual([], plan["selected_tests"])
                self.assertFalse(plan["run_tests"])

    def test_direct_test_and_tools_readme_select_owned_tests(self):
        direct = self.plan(("M", "Tools/tests/test_charlie.py", ""))
        self.assertEqual("selective", direct["mode"])
        self.assertEqual(["test_charlie.py"], direct["selected_tests"])
        self.assertEqual(["3.10", "3.14"], direct["check_versions"])

        inventory = self.plan(("M", "Tools/README.md", ""))
        self.assertEqual("selective", inventory["mode"])
        self.assertEqual(
            ["test_tools_readme_inventory.py"],
            inventory["selected_tests"])
        self.assertEqual(["3.14"], inventory["check_versions"])

    def test_shared_authority_and_unclassified_paths_require_full(self):
        paths = (
            ".github/workflows/verify.yml",
            "Makefile",
            ".github/scripts/ci_impact.py",
            "Tools/platform/common/kblib.py",
            "Tools/platform/distribution/module_boundary_facts.py",
            "Tools/schemas/example.yaml",
            "Tools/tests/fixtures/state.json",
            "Tools/tests/support/profile_fixture.py",
            "kernel/example.yaml",
            "profiles/example/profile.yaml",
            "docs/private.md",
            "misc/notes.md",
            "unexpected.bin",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(
                    "full", self.plan(("M", path, ""))["mode"])

    def test_event_and_change_boundaries_fail_closed(self):
        self.assertEqual("full", self.plan(event="pull_request")["mode"])
        self.assertEqual(
            "full",
            self.plan(("M", "README.md", ""), event="push")["mode"])
        self.assertEqual(
            "full", self.plan(("D", "Tools/alpha.py", ""))["mode"])
        self.assertEqual(
            "full",
            self.plan(("R", "Tools/new.py", "Tools/alpha.py"))["mode"])

    def test_combined_paths_select_the_strictest_required_mode(self):
        selective = self.plan(
            ("M", "README.md", ""),
            ("M", "Tools/tests/test_charlie.py", ""))
        self.assertEqual("selective", selective["mode"])
        self.assertEqual(["test_charlie.py"],
                         selective["selected_tests"])

        full = self.plan(
            ("M", "Tools/tests/test_charlie.py", ""),
            ("M", "Makefile", ""))
        self.assertEqual("full", full["mode"])


class ToolDependencyImpactContractTests(CiImpactFixture):

    def test_changed_tool_selects_reverse_closure_and_cli_surface(self):
        plan = self.plan(("M", "Tools/alpha.py", ""))

        self.assertEqual("selective", plan["mode"])
        self.assertEqual(
            ["test_alpha.py", "test_beta.py", "test_mcp_server.py"],
            plan["selected_tests"])

    def test_recursive_leaf_and_wrapper_preserve_dependency_direction(self):
        leaf = self.plan(
            ("M", "Tools/execution/audit/leaf.py", ""))
        self.assertEqual("selective", leaf["mode"])
        self.assertEqual(
            [
                "test_consumer.py",
                "test_leaf.py",
                "test_mcp_server.py",
                "test_run_leaf.py",
            ],
            leaf["selected_tests"])

        wrapper = self.plan(("M", "Tools/run_leaf.py", ""))
        self.assertEqual("selective", wrapper["mode"])
        self.assertEqual(
            ["test_mcp_server.py", "test_run_leaf.py"],
            wrapper["selected_tests"])

    def test_uncovered_or_overwide_tool_closure_requires_full(self):
        orphan = self.plan(("M", "Tools/orphan.py", ""))
        self.assertEqual("full", orphan["mode"])

        with mock.patch.object(ci_impact, "MAX_SELECTIVE_TESTS", 1):
            overwide = self.plan(("M", "Tools/alpha.py", ""))
        self.assertEqual("full", overwide["mode"])


class SelectedTestRunnerDelegationContractTests(unittest.TestCase):

    def test_ci_delegates_exact_files_and_failure_to_catalog_runner(self):
        names = ["test_alpha.py", "test_beta.py"]
        with mock.patch.object(ci_impact, "validate_selected_tests", return_value=names), \
                mock.patch.object(ci_impact.test_runner, "main", return_value=7) as dispatch:
            result = ci_impact.run_selected_tests(ROOT, ",".join(names))
        self.assertEqual(7, result)
        self.assertEqual([
            "full", "--root", str(ROOT), "--python", ci_impact.sys.executable,
            "--test-files", ",".join(names), "--jobs", "2",
        ], dispatch.call_args.args[0])

    def test_ci_exposes_explicit_jobs_without_changing_selection(self):
        with mock.patch.object(ci_impact, "run_selected_tests", return_value=0) as run:
            result = ci_impact.main([
                "run-tests", "--root", str(ROOT), "--tests", "test_alpha.py",
                "--jobs", "1"])
        self.assertEqual(0, result)
        run.assert_called_once_with(ROOT, "test_alpha.py", 1)


if __name__ == "__main__":
    unittest.main()
