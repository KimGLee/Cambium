#!/usr/bin/env python3
"""Changed-path to required-verification impact contracts.

This suite owns the planner's path classification, matrix presentation, and affected Tool test
closure. Test discovery/catalog correctness, test execution, Git transport,
repository-layout inspection, and shard balancing
have separate owners and are not replayed here. The CI execution adapter is
tested only for delegation to that shared runner.
"""

import importlib.util
import copy
import io
import json
from types import SimpleNamespace
import zipfile
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
            "Tools/tests/test_readme_examples.py": (
                "def test_examples(): pass\n"),
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

        examples = self.plan(("M", "Tools/README.md", ""))
        self.assertEqual("selective", examples["mode"])
        self.assertEqual(
            ["test_readme_examples.py"],
            examples["selected_tests"])
        self.assertEqual(["3.14"], examples["check_versions"])

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


class CiMatrixPresentationContractTests(unittest.TestCase):

    def test_required_budget_uses_the_whole_attempt_and_exact_job_closure(self):
        run = {"id": 17, "run_attempt": 1,
               "created_at": "2026-09-10T00:00:00Z",
               "run_started_at": "2026-09-10T00:00:10Z"}
        plan = {"run_tests": True,
                "check_matrix": {"include": [{"python-version": "3.14"}]},
                "test_matrix": {"include": [{"python-version": "3.14", "test-label": "Lifecycle A"}]}}
        names = ci_impact.required_job_names(plan)
        self.assertEqual(["Contracts · Py3.14", "Impact plan", "Lifecycle A · Py3.14", "ci-required"], names)
        jobs = [{"id": index, "run_id": 17, "run_attempt": 1, "name": name,
                 "started_at": "2026-09-10T00:00:20Z", "status": "completed",
                 "conclusion": "success", "completed_at": "2026-09-10T00:04:50Z"}
                for index, name in enumerate(names, 1)]
        gate = jobs[-1]
        gate.update(status="in_progress", conclusion=None, completed_at=None)
        for observed, expected_seconds, expected_result in (
                ("2026-09-10T00:05:00Z", 300, "passed"),
                ("2026-09-10T00:06:00Z", 360, "passed"),
                ("2026-09-10T00:06:01Z", 361, "budget-exceeded")):
            with self.subTest(observed=observed):
                result = ci_impact.required_budget_verdict(
                    run, jobs, names, run_id=17, attempt=1, observed_at=observed)
                self.assertEqual(expected_seconds, result["elapsed_seconds"])
                self.assertEqual(expected_result, result["result"])
                self.assertEqual(10, result["run_start_delay_seconds"])
                self.assertIsNone(result["job_start_delay_seconds"]["Impact plan"])
                self.assertEqual(1788998760, result["deadline"])
                self.assertFalse(result["final"])
        # The gate's final cost includes its own post-observation work.
        gate.update(status="completed", conclusion="success", completed_at="2026-09-10T00:06:01Z")
        result = ci_impact.required_budget_verdict(
            run, jobs, names, run_id=17, attempt=1,
            observed_at="2026-09-10T00:06:10Z", final=True)
        self.assertEqual("budget-exceeded", result["result"])
        self.assertEqual(361, result["elapsed_seconds"])
        rerun = dict(run, run_attempt=2, run_started_at="2026-09-10T01:00:00Z")
        result = ci_impact.run_budget(rerun, run_id=17, attempt=2,
                                     observed_at="2026-09-10T01:05:00Z")
        self.assertEqual((300, 3900), (result["elapsed_seconds"], result["since_creation_seconds"]))

    def test_required_budget_refuses_missing_failed_or_mixed_attempt_evidence(self):
        run = {"id": 17, "run_attempt": 1,
               "created_at": "2026-09-10T00:00:00Z",
               "run_started_at": "2026-09-10T00:00:10Z"}
        names = ci_impact.required_job_names({"run_tests": False,
            "check_matrix": {"include": [{"python-version": "3.14"}]}})
        jobs = [{"id": index, "run_id": 17, "run_attempt": 1, "name": name,
                 "started_at": "2026-09-10T00:00:20Z", "status": "completed",
                 "conclusion": "success", "completed_at": "2026-09-10T00:00:40Z"}
                for index, name in enumerate(names, 1)]
        def check(candidate, candidate_run=run, candidate_names=names):
            return ci_impact.required_budget_verdict(candidate_run, candidate, candidate_names,
                run_id=17, attempt=1, observed_at="2026-09-10T00:01:00Z", final=True)
        self.assertEqual("passed", check(jobs)["result"])
        for field, value in (("run_attempt", 2), ("conclusion", "failure"),
                             ("conclusion", "skipped"), ("status", "queued"),
                             ("started_at", "not-a-time"), ("completed_at", None),
                             ("completed_at", "2026-09-10T00:02:00Z")):
            candidate = copy.deepcopy(jobs)
            candidate[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                check(candidate)
        for candidate in (jobs[:-1], jobs + [jobs[0]], jobs + [dict(jobs[0], id=99, name="unexpected")]):
            with self.assertRaises(ValueError):
                check(candidate)
        for field, value in (("id", 18), ("run_attempt", 2),
                             ("created_at", "2026-09-10T00:00:30Z")):
            with self.assertRaises(ValueError):
                check(jobs, dict(run, **{field: value}))
        with self.assertRaises(ValueError):
            check(jobs, candidate_names=names + [names[0]])

    def test_member_labels_preserve_exact_selection_and_version_order(self):
        facts = {
            "test_lifecycle.py": {"seconds": 600, "e2e": True, "parallel_safe": False, "samples": 4},
            "test_owner.py": {"seconds": 50, "e2e": False, "parallel_safe": True, "samples": 2},
            "test_consumer.py": {"seconds": 30, "e2e": False, "parallel_safe": False, "samples": 2},
            "test_transport.py": {"seconds": 10, "e2e": False, "parallel_safe": True, "samples": 0},
        }
        for prefix in ("full", "affected"):
            with mock.patch.object(ci_impact, "_scheduling_facts", return_value=facts), \
                    mock.patch.object(ci_impact, "FULL_SHARD_COUNT", 3):
                matrix = ci_impact._matrix(ROOT, ("3.10", "3.14"), list(reversed(facts)), prefix)
            self.assertEqual(["3.10"] * 3 + ["3.14"] * 3, [row["python-version"] for row in matrix["include"]])
            for version in ("3.10", "3.14"):
                rows = [row for row in matrix["include"] if row["python-version"] == version]
                assigned = [name for row in rows for name in row["test-files"].split(",")]
                self.assertEqual(sorted(facts), sorted(assigned))
                self.assertEqual("test_lifecycle.py", rows[0]["test-files"])
                self.assertEqual(["Lifecycle A", "Tools A", "Tools B"], [row["test-label"] for row in rows])
                self.assertEqual(600, rows[0]["estimated-seconds"])
            self.assertEqual(80, ci_impact._estimated_makespan(
                ["test_owner.py", "test_consumer.py", "test_transport.py"], facts))

    def test_cost_samples_are_advisory_medians_and_never_zero_for_unknowns(self):
        samples = {"test_ci_impact.py": [
            {"seconds": 2}, {"seconds": 1000}, {"seconds": 4},
            {"seconds": float("nan")}, {"seconds": -1}]}
        facts = ci_impact._scheduling_facts(ROOT, ["test_ci_impact.py", "test_unknown.py"], samples)
        self.assertEqual(4, facts["test_ci_impact.py"]["seconds"])
        self.assertEqual(3, facts["test_ci_impact.py"]["samples"])
        self.assertGreater(facts["test_unknown.py"]["seconds"], 0)
        self.assertEqual("source-size-fallback", facts["test_unknown.py"]["cost_basis"])

    def test_history_is_bounded_main_only_and_network_failure_falls_back(self):
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w") as archive:
            archive.writestr("job.txt",
                "Successfully set up CPython (3.14.7)\\n"
                "test runner: suite=full module=1/1 path=Tools/tests/test_alpha.py "
                "cases=2 mode=serial elapsed=4.000s exit=0\\n")
        runs = {"workflow_runs": [{"id": 1, "event": "push", "head_branch": "main",
                "conclusion": "success", "head_sha": "a" * 40}]}
        with mock.patch.object(ci_impact.subprocess, "run", side_effect=[
                SimpleNamespace(stdout=json.dumps(runs).encode()), SimpleNamespace(stdout=memory.getvalue())]) as api:
            result = ci_impact._historical_costs("owner/repo")
        self.assertEqual(2, api.call_count)
        self.assertEqual(4, result["samples"]["test_alpha.py"][0]["seconds"])
        self.assertEqual("3.14.7", result["samples"]["test_alpha.py"][0]["python"])
        with mock.patch.object(ci_impact.subprocess, "run", side_effect=OSError("offline")):
            self.assertEqual("unavailable", ci_impact._historical_costs("owner/repo")["status"])
        with mock.patch.object(ci_impact.time, "monotonic", side_effect=[100, 101, 106]), \
                mock.patch.object(ci_impact.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(runs).encode())) as api:
            self.assertEqual("unavailable", ci_impact._historical_costs("owner/repo")["status"])
        self.assertEqual(1, api.call_count)

    def test_budget_metadata_reads_complete_attempt_pages_and_rejects_partial_results(self):
        run = {"id": 17, "run_attempt": 2}
        pages = [{"total_count": 2, "jobs": [{"id": 1}]},
                 {"total_count": 2, "jobs": [{"id": 2}]}]
        with mock.patch.object(ci_impact.subprocess, "run", side_effect=[
                SimpleNamespace(stdout=json.dumps(run).encode()),
                SimpleNamespace(stdout=json.dumps(pages).encode())]) as api:
            self.assertEqual((run, [{"id": 1}, {"id": 2}]), ci_impact._run_metadata(
                "owner/repo", 17, 2, include_jobs=True))
        self.assertIn("repos/owner/repo/actions/runs/17/attempts/2/jobs?per_page=100", api.call_args.args[0])
        self.assertEqual(["--paginate", "--slurp"], api.call_args.args[0][-2:])
        for incomplete in ([], pages[:1], [pages[0], dict(pages[1], total_count=3)]):
            with mock.patch.object(ci_impact.subprocess, "run", side_effect=[
                    SimpleNamespace(stdout=json.dumps(run).encode()),
                    SimpleNamespace(stdout=json.dumps(incomplete).encode())]), self.assertRaises(ValueError):
                ci_impact._run_metadata("owner/repo", 17, 2, include_jobs=True)
        with mock.patch.object(ci_impact.time, "time", return_value=100), \
                mock.patch.object(ci_impact.os, "execvp") as execute:
            self.assertEqual(0, ci_impact.main(["run-step", "--deadline", "110", "--", "make", "check"]))
            execute.assert_called_once_with("timeout", ["timeout", "--kill-after=1s", "--", "10.0", "make", "check"])
            execute.reset_mock()
            self.assertEqual(124, ci_impact.main(["run-step", "--deadline", "99", "--", "make", "check"]))
            execute.assert_not_called()


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
        run.assert_called_once_with(ROOT, "test_alpha.py", 1, None, None)
        with mock.patch.object(ci_impact, "validate_selected_tests", return_value=["test_alpha.py"]), \
                mock.patch.object(ci_impact.test_runner, "main", return_value=124) as dispatch:
            self.assertEqual(124, ci_impact.run_selected_tests(ROOT, "test_alpha.py", deadline=1788998760))
        self.assertEqual(["--deadline", "1788998760"], dispatch.call_args.args[0][-2:])


if __name__ == "__main__":
    unittest.main()
