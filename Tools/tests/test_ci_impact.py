#!/usr/bin/env python3
import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ci_impact", ROOT / ".github/scripts/ci_impact.py")
ci_impact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci_impact)


class CiImpactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "Tools/tests/fixtures").mkdir(parents=True)
        (self.root / "Tools/compiled").mkdir()
        (self.root / "Tools/schemas").mkdir()
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / "kernel").mkdir()
        (self.root / "Card").mkdir()
        (self.root / "Read Set").mkdir()
        (self.root / "profiles").mkdir()
        shutil.copy(
            ROOT / "Card/card.schema.yaml",
            self.root / "Card/card.schema.yaml",
        )
        shutil.copy(
            ROOT / "Read Set/read-set.schema.yaml",
            self.root / "Read Set/read-set.schema.yaml",
        )
        self._write("Tools/alpha.py", "VALUE = 1\n")
        self._write("Tools/beta.py", "import alpha\n")
        self._write("Tools/orphan.py", "VALUE = 2\n")
        self._write("Tools/tests/test_alpha.py", "import alpha\n")
        self._write("Tools/tests/test_beta.py", "import beta\n")
        self._write(
            "Tools/tests/test_charlie.py",
            "import unittest\n\n"
            "class CharlieTests(unittest.TestCase):\n"
            "    def test_charlie(self):\n"
            "        self.assertTrue(True)\n",
        )
        self._write("Tools/tests/test_november.py", "pass\n")
        self._write("Tools/tests/test_sierra.py", "pass\n")
        self._write("Tools/tests/test_tools_readme_inventory.py", "pass\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def _plan(self, *changes, event="pull_request"):
        return ci_impact.plan_changes(
            self.root,
            [ci_impact.Change(status, path) for status, path in changes],
            event=event,
        )

    def test_markdown_only_change_runs_checks_only_on_ceiling(self):
        for path in (
                "README.md",
                "README.zh-CN.md",
                "ROADMAP.md",
                "ROADMAP.zh-CN.md",
                "kernel/K00 Standards Control/README.md",
                "Card/R01 Core Bootstrap Card.md",
                "Read Set/R01 Core Bootstrap Read Set.md"):
            with self.subTest(path=path):
                plan = self._plan(("M", path))
                self.assertEqual("checks-only", plan["mode"])
                self.assertEqual(["3.14"], plan["check_versions"])
                self.assertFalse(plan["run_tests"])

    def test_markdown_roots_follow_component_schema_prefixes(self):
        cases = (
            ("Card/card.schema.yaml", "Card/", "Flight-Cards/"),
            ("Read Set/read-set.schema.yaml", "Read Set/", "Reading/"),
        )
        for schema_relative, old_prefix, new_prefix in cases:
            with self.subTest(schema=schema_relative):
                schema_path = self.root / schema_relative
                source = schema_path.read_text(encoding="utf-8")
                schema_path.write_text(
                    source.replace(
                        'path_prefix: "%s"' % old_prefix,
                        'path_prefix: "%s"' % new_prefix,
                    ),
                    encoding="utf-8",
                )

                projected = self._plan(("M", new_prefix + "R01.md"))
                stale = self._plan(("M", old_prefix + "R01.md"))

                self.assertEqual("checks-only", projected["mode"])
                self.assertEqual("full", stale["mode"])

    def test_readme_assets_are_checks_only_but_local_docs_fail_closed(self):
        allowed = self._plan(("A", "assets/readme/diagram.png"))
        forbidden = self._plan(("A", "docs/private.md"))
        self.assertEqual("checks-only", allowed["mode"])
        self.assertEqual("full", forbidden["mode"])

    def test_forbidden_tracked_paths_are_exactly_local_only_roots(self):
        self.assertEqual(
            ["_to_delete/old.md", "docs/private.md"],
            ci_impact.forbidden_tracked_paths([
                "README.md",
                "assets/readme/diagram.png",
                "docs/private.md",
                "_to_delete/old.md",
            ]),
        )

    def test_repository_layout_catches_force_added_ignored_file(self):
        repo = self.root / "layout-repository"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        self._write("layout-repository/.gitignore", "docs/\n")
        self._write("layout-repository/docs/private.md", "private\n")
        subprocess.run(
            ["git", "add", ".gitignore"], cwd=repo, check=True)
        subprocess.run(
            ["git", "add", "-f", "docs/private.md"],
            cwd=repo, check=True,
        )
        with self.assertRaisesRegex(ValueError, "docs/private.md"):
            ci_impact.validate_repository_layout(repo)

    def test_direct_test_change_selects_only_that_module_on_both_versions(self):
        plan = self._plan(("M", "Tools/tests/test_charlie.py"))
        self.assertEqual("selective", plan["mode"])
        self.assertEqual(["test_charlie.py"], plan["selected_tests"])
        self.assertEqual(["3.10", "3.14"], plan["check_versions"])

    def test_changed_tool_selects_reverse_dependency_closure(self):
        plan = self._plan(("M", "Tools/alpha.py"))
        self.assertEqual("selective", plan["mode"])
        self.assertEqual(
            ["test_alpha.py", "test_beta.py"], plan["selected_tests"])

    def test_tool_without_a_reachable_test_falls_back_to_full(self):
        plan = self._plan(("M", "Tools/orphan.py"))
        self.assertEqual("full", plan["mode"])

    def test_tools_readme_runs_its_inventory_contract(self):
        plan = self._plan(("M", "Tools/README.md"))
        self.assertEqual("selective", plan["mode"])
        self.assertEqual(
            ["test_tools_readme_inventory.py"], plan["selected_tests"])
        self.assertEqual(["3.14"], plan["check_versions"])

    def test_shared_ci_authority_falls_back_to_full(self):
        for path in (
                ".github/workflows/verify.yml",
                "Makefile",
                ".github/scripts/ci_impact.py",
                "Tools/kblib.py",
                "Tools/schemas/example.yaml",
                "Tools/tests/fixtures/state.json",
                "Tools/tests/profile_fixture.py"):
            with self.subTest(path=path):
                self.assertEqual("full", self._plan(("M", path))["mode"])

    def test_a_compiled_projection_is_checked_rather_than_re_tested(self):
        """The artifact is derived, so its sources decide the mode, not it.

        While this path forced the full suite it also fired on every Tool
        change -- the artifact is regenerated alongside one -- and the
        selective branch went unreached in 22 consecutive runs.  What
        protected the artifact was never the test suite: `make check` runs
        `metadata_execution_contract --check` in every mode, including this
        one, and a tampered artifact exits non-zero there.
        """
        plan = self._plan(("M", "Tools/compiled/example.json"))
        self.assertEqual("checks-only", plan["mode"])

    def test_the_sources_of_a_compiled_projection_still_force_full(self):
        """The reason the projection may be demoted: its inputs are not."""
        for path in ("kernel/K08 Metadata and Status/authority.yaml",
                     "Tools/operation-capabilities.yaml"):
            with self.subTest(path=path):
                self.assertEqual("full", self._plan(("M", path))["mode"])

    def test_a_selective_plan_is_sharded_like_a_full_one(self):
        """A narrow plan in one job was slower than the matrix it replaced.

        Nine modules measured 451-525s on a runner in a single unsharded
        job, and the widest closure projects past the job timeout outright.
        """
        plan = self._plan(("M", "Tools/alpha.py"))
        self.assertEqual("selective", plan["mode"])
        shards = {entry["shard"] for entry in plan["test_matrix"]["include"]}
        # An inequality here would pass on a single unsharded job, which is
        # the regression this test exists to catch.
        self.assertEqual(
            min(len(plan["selected_tests"]), len(ci_impact.FULL_SHARD_RANGES)),
            len(shards))
        version = ci_impact.PYTHON_VERSIONS[0]
        packed = [name
                  for entry in plan["test_matrix"]["include"]
                  if entry["python-version"] == version
                  for name in entry["test-files"].split(",")]
        self.assertEqual(sorted(packed), sorted(plan["selected_tests"]))
        self.assertEqual(len(packed), len(set(packed)))

    def test_the_cli_surface_test_joins_every_closure(self):
        """mcp_server reaches tools by command line, never by import.

        No reverse-import closure can reach it, so the edge is declared
        rather than discovered -- the remedy the Tool module boundary names
        for this blind spot.
        """
        self._write("Tools/tests/test_mcp_server.py", "pass\n")
        plan = self._plan(("M", "Tools/alpha.py"))
        self.assertEqual("selective", plan["mode"])
        self.assertIn("test_mcp_server.py", plan["selected_tests"])

    def test_authoritative_non_markdown_and_unknown_paths_fail_closed(self):
        for path in (
                "kernel/example.yaml",
                "profiles/example/profile.yaml",
                "misc/notes.md",
                "unexpected.bin"):
            with self.subTest(path=path):
                self.assertEqual("full", self._plan(("M", path))["mode"])

    def test_delete_and_rename_fail_closed(self):
        deleted = ci_impact.plan_changes(
            self.root, [ci_impact.Change("D", "Tools/alpha.py")])
        renamed = ci_impact.plan_changes(
            self.root,
            [ci_impact.Change("R", "Tools/new.py", "Tools/alpha.py")],
        )
        self.assertEqual("full", deleted["mode"])
        self.assertEqual("full", renamed["mode"])

    def test_non_pull_request_event_is_always_full(self):
        plan = self._plan(("M", "README.md"), event="push")
        self.assertEqual("full", plan["mode"])

    def test_empty_diff_fails_closed(self):
        self.assertEqual("full", ci_impact.plan_changes(
            self.root, [], event="pull_request")["mode"])

    def test_full_matrix_covers_every_test_once_per_python(self):
        plan = self._plan(("M", "Makefile"))
        expected = ci_impact.discover_tests(self.root)
        for version in ci_impact.PYTHON_VERSIONS:
            selected = []
            for item in plan["test_matrix"]["include"]:
                if item["python-version"] == version:
                    selected.extend(item["test-files"].split(","))
            self.assertEqual(expected, sorted(selected))

    def test_selected_test_validation_rejects_unknown_and_duplicates(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            ci_impact.validate_selected_tests(
                self.root, "../../test_escape.py")
        with self.assertRaisesRegex(ValueError, "duplicates"):
            ci_impact.validate_selected_tests(
                self.root, "test_alpha.py,test_alpha.py")

    def test_selected_test_runner_executes_real_tests_and_rejects_zero(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), \
                contextlib.redirect_stderr(output):
            self.assertEqual(
                0, ci_impact.run_selected_tests(
                    self.root, "test_charlie.py"))
            self.assertEqual(
                1, ci_impact.run_selected_tests(self.root, "test_alpha.py"))

    def test_name_status_parser_includes_rename_boundaries(self):
        changes = ci_impact.parse_name_status(
            b"M\0README.md\0R100\0old.py\0new.py\0D\0gone.py\0")
        self.assertEqual([
            ci_impact.Change("M", "README.md"),
            ci_impact.Change("R", "new.py", "old.py"),
            ci_impact.Change("D", "gone.py"),
        ], changes)

    def test_path_normalization_rejects_repository_escape(self):
        with self.assertRaisesRegex(ValueError, "repository-relative"):
            ci_impact.parse_name_status(b"M\0../outside.py\0")


if __name__ == "__main__":
    unittest.main()
