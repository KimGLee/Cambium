"""Owner contracts for test discovery, classification, and projections."""

import hashlib
import io
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
from types import ModuleType
import unittest
from unittest import mock

import Tools.platform.common.kblib as kblib
from Tools.platform.distribution import test_catalog, test_runner


ROOT = Path(__file__).resolve().parents[2]


class TestRunnerSelectionContractTests(unittest.TestCase):
    """Exact CI/local selection and grouping over in-memory owner objects."""

    @staticmethod
    def catalog():
        return {"schema_version": 1, "modules": [
            {"path": "Tools/tests/test_alpha.py", "cases": [
                {"test_id": "test_alpha.Fast.test_value", "level": "unit",
                 "disposition": "keep", "parallel_safe": True},
                {"test_id": "test_alpha.Integration.test_seam", "level": "integration",
                 "disposition": "keep", "parallel_safe": False},
            ]},
            {"path": "Tools/tests/test_beta.py", "cases": [
                {"test_id": "test_beta.Contract.test_other", "level": "contract",
                 "disposition": "keep", "parallel_safe": True},
            ]},
        ]}

    def test_file_filter_keeps_all_requested_levels_and_rejects_invalid_files(self):
        catalog = self.catalog()
        expected = sorted(row["test_id"] for row in catalog["modules"][0]["cases"])
        self.assertEqual(expected, test_runner.select_test_ids(catalog, "full", "test_alpha.py"))
        self.assertEqual([expected[0]], test_runner.select_test_ids(catalog, "fast", "test_alpha.py"))
        for names in ("", "test_alpha.py,", "test_alpha.py,test_alpha.py",
                      "test_missing.py", "../test_alpha.py"):
            with self.subTest(names=names), self.assertRaises(test_runner.TestRunnerError):
                test_runner.select_test_ids(catalog, "full", names)

    def test_selected_module_stays_one_isolated_group_and_honors_parallel_safety(self):
        def child(group, **_kwargs):
            return test_runner.GroupResult(group, 0, "", "", 0.01)

        with mock.patch.object(test_runner, "_catalog", return_value=self.catalog()), \
                mock.patch.object(test_runner, "_run_child", side_effect=child) as run, \
                redirect_stdout(io.StringIO()) as output:
            code = test_runner.main([
                "full", "--root", str(ROOT), "--test-files", "test_alpha.py",
                "--jobs", "2"])
        self.assertEqual(0, code)
        run.assert_called_once()
        group = run.call_args.args[0]
        self.assertEqual("test_alpha", group.module)
        self.assertEqual(2, len(group.test_ids))
        self.assertFalse(group.parallel_safe)
        self.assertIn("mode=serial", output.getvalue())
        self.assertIn("selected=2 completed=2", output.getvalue())

    def test_deadline_admission_and_failure_do_not_report_unexecuted_cases(self):
        with mock.patch.object(test_runner, "_catalog") as catalog:
            for deadline in ("nan", "inf", "-1", "1"):
                with self.subTest(deadline=deadline):
                    self.assertNotEqual(0, test_runner.main(["full", "--deadline", deadline]))
            catalog.assert_not_called()
        groups = test_runner.module_groups(self.catalog(),
            test_runner.select_test_ids(self.catalog(), "full"))
        with mock.patch.object(test_runner.subprocess, "Popen") as launch, \
                redirect_stdout(io.StringIO()):
            result = test_runner._execute_suite("full", groups, jobs=1,
                run_child=lambda group: test_runner._run_child(
                    group, python=sys.executable, root=ROOT, env={}, deadline=time.monotonic() - 1))
        self.assertEqual((124, 0, 1), result)
        launch.assert_not_called()

    def test_cost_scopes_attribute_real_hooks_without_repeating_shared_fixtures(self):
        module = ModuleType("cost_probe")
        calls = []
        def setup_class(cls):
            calls.append("class")
            cls.addClassCleanup(lambda: calls.append("class-cleanup"))
        def method(case):
            with test_runner.measure_scope("checkpoint", "local-input") as counts:
                calls.append("method")
                counts["action:review"] = 2
                counts["child:producer"] = 3
        module.setUpModule = lambda: calls.append("module")
        module.tearDownModule = lambda: calls.append("module-cleanup")
        probe = type("Probe", (unittest.TestCase,), {
            "__module__": module.__name__, "setUpClass": classmethod(setup_class),
            "setUp": lambda self: calls.append("setup"),
            "test_first": method, "test_second": method})
        module.Probe = probe
        original = vars(probe)["setUpClass"]
        ids = ["cost_probe.Probe.test_first", "cost_probe.Probe.test_second"]
        outer_measurements = test_runner._MEASUREMENTS.get()
        with mock.patch.dict(sys.modules, {module.__name__: module}):
            report = test_runner.run_measured_tests(ids, stream=io.StringIO())
        self.assertTrue(report["successful"])
        self.assertEqual(2, report["tests_run"])
        self.assertEqual(1, calls.count("class"))
        self.assertEqual(1, calls.count("class-cleanup"))
        self.assertEqual(2, calls.count("setup"))
        self.assertIs(original, vars(probe)["setUpClass"])
        rows = report["scopes"]
        self.assertEqual(2, len([row for row in rows if row["kind"] == "case"]))
        self.assertEqual(2, len([row for row in rows if row["kind"] == "checkpoint"]))
        self.assertEqual([{"action:review": 2, "child:producer": 3}] * 2,
                         [row["counts"] for row in rows if row["kind"] == "checkpoint"])
        self.assertTrue(all("counts" not in row for row in rows if row["kind"] != "checkpoint"))
        self.assertTrue(all(0 <= row["exclusive"] <= row["elapsed"] for row in rows))
        # Root scopes partition wall time. Nested rows are not added again.
        roots = sum(row["elapsed"] for row in rows if row["parent"] is None)
        self.assertAlmostEqual(roots, sum(row["exclusive"] for row in rows))
        # The owner test is itself measured under the real test runner.
        # Nested collection must restore its caller, not clear that context.
        self.assertIs(outer_measurements, test_runner._MEASUREMENTS.get())

    def test_cost_collection_preserves_failures_skips_and_class_admission_errors(self):
        module = ModuleType("cost_outcomes")
        def bad_subtest(case):
            with case.subTest(value="invalid"):
                case.fail("expected probe failure")
        def bad_setup(cls):
            raise RuntimeError("fixture failed")
        module.Probe = type("Probe", (unittest.TestCase,), {
            "__module__": module.__name__, "test_failure": bad_subtest,
            "test_skipped": unittest.skip("not applicable")(lambda self: None)})
        module.Broken = type("Broken", (unittest.TestCase,), {
            "__module__": module.__name__, "setUpClass": classmethod(bad_setup),
            "test_never_run": lambda self: self.fail("must not run")})
        with mock.patch.dict(sys.modules, {module.__name__: module}):
            report = test_runner.run_measured_tests([
                "cost_outcomes.Probe", "cost_outcomes.Broken"], stream=io.StringIO())
        self.assertFalse(report["successful"])
        cases = {row["identity"]: row["status"] for row in report["scopes"] if row["kind"] == "case"}
        self.assertEqual({"cost_outcomes.Probe.test_failure": "failure",
                          "cost_outcomes.Probe.test_skipped": "skipped"}, cases)
        self.assertTrue(any(row["identity"].endswith("Broken:setUpClass") and
                            row["outcome"] == "raised" for row in report["scopes"]))
        self.assertNotIn("setUpClass", vars(module.Probe))

    def test_progress_survives_interruption_without_claiming_a_test_result(self):
        module = ModuleType("cost_interrupt")
        module.Probe = type("Probe", (unittest.TestCase,), {
            "__module__": module.__name__,
            "test_stop": lambda self: (_ for _ in ()).throw(KeyboardInterrupt())})
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.dict(sys.modules, {module.__name__: module}):
            report, progress = Path(temporary) / "final.json", Path(temporary) / "progress.jsonl"
            with self.assertRaises(KeyboardInterrupt):
                test_runner.child_main([str(report), str(progress), "cost_interrupt.Probe"])
            self.assertFalse(report.exists())
            rows = [json.loads(line) for line in progress.read_text().splitlines()]
            self.assertEqual("incomplete", rows[0]["state"])
            self.assertTrue(any(row.get("kind") == "discovery" for row in rows))
            self.assertFalse(any(row.get("successful") or row.get("status") == "passed"
                                 or row.get("kind") == "test-run-finished" for row in rows))
            self.assertTrue(any(row.get("outcome") == "raised" for row in rows))


class SyntheticCatalogWorkspace:
    """Write one minimal independent manifest and source graph."""

    @staticmethod
    def write(root, *, test_source, fixture_source, level="contract",
              overrides=None):
        test_path = root / "Tools/tests/test_sample.py"
        fixture_path = root / "Tools/tests/support/sample_fixture.py"
        owner_path = root / "owner.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(test_source, encoding="utf-8")
        fixture_path.write_text(fixture_source, encoding="utf-8")
        owner_path.write_text("OWNER = 'synthetic'\n", encoding="utf-8")

        row = {
            "path": "Tools/tests/test_sample.py",
            "owner": "owner.py",
            "level": level,
            "lifecycle": "current",
            "disposition": "keep",
            "semantics": "synthetic-owner-contract",
            "owner_contract_symbol": "synthetic-owner-contract",
            "parallel_safe": True,
        }
        if overrides is not None:
            row["overrides"] = overrides
        manifest = {
            "schema_version": 1,
            "level_policy": {
                name: "%s policy" % name for name in test_catalog.LEVELS
            },
            "baseline": {
                "test_modules": 1,
                "test_cases": 1,
                "process_calls": 0,
                "temp_resources": 0,
                "full_repository_copies": 0,
                "cross_test_import_sites": 0,
            },
            "tests": [row],
            "fixtures": [{
                "path": "Tools/tests/support/sample_fixture.py",
                "owner": "owner.py",
                "purpose": "synthetic fixture dependency",
                "lifecycle": "current",
            }],
            "fixture_bundles": [],
        }
        manifest_path = root / test_catalog.MANIFEST_PATH
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            kblib.canonical_yaml(manifest), encoding="utf-8")
        return manifest


class TestCatalogContractTests(unittest.TestCase):
    """Small source/manifest graphs independently exercise Catalog rules."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.synthetic_root = Path(cls.temporary.name)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def root(self):
        root = self.synthetic_root / self._testMethodName
        root.mkdir(parents=True, exist_ok=True)
        return root

    def test_minimal_manifest_discovers_and_classifies_its_exact_sources(self):
        root = self.root()
        SyntheticCatalogWorkspace.write(
            root,
            test_source=(
                "import unittest\n"
                "from Tools.tests.support.sample_fixture import value\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_value(self):\n"
                "        self.assertEqual(1, value())\n"
            ),
            fixture_source="def value():\n    return 1\n",
        )

        catalog, errors = test_catalog.build_catalog(root)

        self.assertEqual([], errors)
        self.assertEqual(1, catalog["summary"]["test_modules"])
        self.assertEqual(1, catalog["summary"]["test_cases"])
        self.assertEqual(1, catalog["summary"]["fixtures"])
        module = catalog["modules"][0]
        case = module["cases"][0]
        self.assertEqual("Tools/tests/test_sample.py", module["path"])
        self.assertEqual("contract", case["level"])
        self.assertEqual("declared", case["owner_reference"]["status"])
        self.assertEqual("invariant", case["owner_reference"]["kind"])
        self.assertEqual(
            ["Tools/tests/support/sample_fixture.py"],
            module["fixture_dependencies"])
        self.assertEqual(
            {"process_calls": 0, "temp_resources": 0,
             "file_copies": 0, "full_repository_copies": 0},
            case["execution"]["transitive_effects"])

    def test_owner_reference_resolution_does_not_promote_labels_to_symbols(self):
        root = self.root()
        for symbol, kind, status in (
                ("owner.OWNER", "symbol", "resolved"),
                ("owner.retired", "symbol", "unresolved"),
                ("synthetic-owner-contract", "invariant", "declared")):
            with self.subTest(symbol=symbol):
                SyntheticCatalogWorkspace.write(root,
                    test_source="import unittest\nclass Sample(unittest.TestCase):\n    def test_value(self):\n        pass\n",
                    fixture_source="VALUE = 1\n", overrides=[{
                        "selector": "Sample.test_value", "owner_contract_symbol": symbol,
                        "owner_reference_kind": kind}])
                catalog, errors = test_catalog.build_catalog(root)
                case = catalog["modules"][0]["cases"][0]
                self.assertEqual(status, case["owner_reference"]["status"])
                self.assertEqual(status == "unresolved", any(
                    "unresolved owner symbol" in error for error in errors), errors)

    def test_ephemeral_os_and_python_artifacts_are_not_fixtures(self):
        root = self.root()
        SyntheticCatalogWorkspace.write(
            root,
            test_source=(
                "import unittest\n"
                "from Tools.tests.support.sample_fixture import value\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_value(self):\n"
                "        self.assertEqual(1, value())\n"
            ),
            fixture_source="def value():\n    return 1\n",
        )
        fixture_root = root / "Tools/tests/fixtures"
        cache = fixture_root / "contract/__pycache__"
        cache.mkdir(parents=True)
        (fixture_root / ".DS_Store").write_bytes(b"Finder metadata")
        (cache / "objects.cpython-312.pyc").write_bytes(b"bytecode")
        (fixture_root / "stray.pyc").write_bytes(b"bytecode")

        catalog, errors = test_catalog.build_catalog(root)

        self.assertEqual([], errors)
        self.assertEqual(1, catalog["summary"]["fixtures"])

    def test_unknown_ordinary_fixture_still_fails_closed(self):
        root = self.root()
        SyntheticCatalogWorkspace.write(
            root,
            test_source=(
                "import unittest\n"
                "from Tools.tests.support.sample_fixture import value\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_value(self):\n"
                "        self.assertEqual(1, value())\n"
            ),
            fixture_source="def value():\n    return 1\n",
        )
        unknown = root / "Tools/tests/fixtures/unowned.json"
        unknown.parent.mkdir(parents=True)
        unknown.write_text("{}\n", encoding="utf-8")

        _catalog, errors = test_catalog.build_catalog(root)

        self.assertTrue(any(
            "unclassified fixtures: Tools/tests/fixtures/unowned.json" in error
            for error in errors
        ), errors)

    def test_transitive_lifecycle_and_scopes_reject_a_fast_classification(self):
        root = self.root()
        SyntheticCatalogWorkspace.write(
            root,
            level="unit",
            fixture_source=(
                "import shutil\n"
                "import subprocess\n"
                "import tempfile\n"
                "class FixtureCase:\n"
                "    def setUp(self):\n"
                "        self.temporary = tempfile.TemporaryDirectory()\n"
                "def build_lifecycle(walker):\n"
                "    shutil.copytree('/source', '/target')\n"
                "    subprocess.run(['true'])\n"
                "    walker.merge_and_close('B1')\n"
            ),
            test_source=(
                "import subprocess\n"
                "import unittest\n"
                "from Tools.tests.support.sample_fixture import "
                "FixtureCase, build_lifecycle\n"
                "def setUpModule():\n"
                "    subprocess.run(['true'])\n"
                "class SampleTests(FixtureCase, unittest.TestCase):\n"
                "    def test_value(self):\n"
                "        build_lifecycle(None)\n"
            ),
        )

        catalog, errors = test_catalog.build_catalog(root)
        case = catalog["modules"][0]["cases"][0]

        self.assertTrue(any(
            "method/class/process closure reaches" in error
            for error in errors), errors)
        self.assertEqual(
            1, case["execution"]["scopes"]["per_process"]["effects"][
                "process_calls"])
        self.assertEqual(
            1, case["execution"]["scopes"]["per_method"]["effects"][
                "temp_resources"])
        self.assertGreater(
            case["execution"]["transitive_effects"]["process_calls"], 0)
        self.assertGreater(
            case["execution"]["transitive_effects"][
                "full_repository_copies"], 0)
        # One merge/close call is a lifecycle signal, not evidence that the
        # fixture reconstructs the complete Task Plan-to-close lifecycle.
        self.assertFalse(case["execution"]["full_lifecycle"])
        self.assertIn(
            "merge_and_close:B1",
            case["execution"]["lifecycle_signals"])

    def test_overrides_and_suite_selection_form_one_closed_partition(self):
        root = self.root()
        test_source = (
            "import unittest\n"
            "from Tools.tests.support.sample_fixture import value\n"
            "class SampleTests(unittest.TestCase):\n"
            "    def test_fast(self):\n"
            "        self.assertEqual(1, value())\n"
            "    def test_integration(self):\n"
            "        self.assertEqual(1, value())\n"
        )
        fixture_source = "def value():\n    return 1\n"
        override = {
            "selector": "SampleTests.test_integration",
            "level": "integration",
            "semantics": "synthetic-integration-seam",
            "owner_contract_symbol": "synthetic-integration-seam",
            "parallel_safe": True,
        }
        SyntheticCatalogWorkspace.write(
            root, test_source=test_source, fixture_source=fixture_source,
            overrides=[override])

        catalog, errors = test_catalog.build_catalog(root)
        expected_fast = ["test_sample.SampleTests.test_fast"]
        expected_integration = [
            "test_sample.SampleTests.test_integration"]

        self.assertEqual([], errors)
        self.assertEqual(
            expected_fast, test_runner.select_test_ids(catalog, "fast"))
        self.assertEqual(
            expected_integration,
            test_runner.select_test_ids(catalog, "integration"))
        self.assertEqual(
            sorted(expected_fast + expected_integration),
            test_runner.select_test_ids(catalog, "full"))

        unmatched = dict(override, selector="MissingTests.*")
        SyntheticCatalogWorkspace.write(
            root, test_source=test_source, fixture_source=fixture_source,
            overrides=[unmatched])
        _catalog, errors = test_catalog.build_catalog(root)
        self.assertTrue(any(
            "unmatched overrides" in error for error in errors), errors)

    def test_source_annotation_exposes_effect_hidden_by_production_boundary(self):
        root = self.root()
        SyntheticCatalogWorkspace.write(
            root,
            test_source=(
                "import unittest\n"
                "from Tools.tests.support.test_effects import catalog_effects\n"
                "class SampleTests(unittest.TestCase):\n"
                "    @catalog_effects(process_calls=1)\n"
                "    def test_transport(self):\n"
                "        production_transport()\n"
            ),
            fixture_source="def value():\n    return 1\n",
            level="integration",
        )

        catalog, errors = test_catalog.build_catalog(root)

        self.assertEqual([], errors)
        case = catalog["modules"][0]["cases"][0]
        self.assertEqual(
            1, case["execution"]["scopes"]["direct_method"]["effects"][
                "process_calls"])
        self.assertEqual(
            1, catalog["summary"]["source_effects"]["process_calls"])

    def test_source_annotation_rejects_non_positive_declarations(self):
        root = self.root()
        SyntheticCatalogWorkspace.write(
            root,
            test_source=(
                "import unittest\n"
                "from Tools.tests.support.test_effects import catalog_effects\n"
                "class SampleTests(unittest.TestCase):\n"
                "    @catalog_effects(process_calls=0)\n"
                "    def test_transport(self):\n"
                "        pass\n"
            ),
            fixture_source="def value():\n    return 1\n",
            level="integration",
        )

        with self.assertRaisesRegex(
                test_catalog.TestCatalogError,
                "must declare a positive effect"):
            test_catalog.build_catalog(root)

    def test_complete_lifecycle_execution_belongs_only_to_e2e(self):
        root = self.root()
        SyntheticCatalogWorkspace.write(
            root,
            level="integration",
            fixture_source=(
                "_CACHE = {}\n"
                "def _closed():\n"
                "    walker.merge_and_close('B1')\n"
                "_BUILDERS = {'closed': _closed}\n"
                "_PARENTS = {'closed': None}\n"
                "def scenario(name):\n"
                "    if name not in _CACHE:\n"
                "        _BUILDERS[name]()\n"
                "        _CACHE[name] = name\n"
                "    return _CACHE[name]\n"
            ),
            test_source=(
                "import unittest\n"
                "from Tools.tests.support.sample_fixture import scenario\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_full_walk(self):\n"
                "        self.assertEqual('closed', scenario('closed'))\n"
            ),
        )

        catalog, errors = test_catalog.build_catalog(root)

        case = catalog["modules"][0]["cases"][0]
        self.assertTrue(case["execution"]["full_lifecycle"])
        self.assertTrue(any(
            "complete lifecycle execution belongs only to e2e" in error
            for error in errors
        ), errors)

    def test_fixture_bundle_identity_and_bytes_come_from_its_manifest(self):
        root = self.root()
        member = root / "bundle/item.txt"
        member.parent.mkdir(parents=True)
        member.write_text("current bytes\n", encoding="utf-8")
        owner = root / "Tools/tests/fixtures/e2e/builder.py"
        owner.parent.mkdir(parents=True)
        owner.write_text("def generate(): pass\n", encoding="utf-8")
        content = member.read_bytes()
        files = [{
            "path": "item.txt",
            "size": len(content),
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        }]
        tree_sha256 = "sha256:" + hashlib.sha256(json.dumps(
            files, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        manifest = root / "bundle.manifest.json"
        manifest.write_text(json.dumps({
            "schema_version": 1,
            "generator": "Tools.tests.fixtures.e2e.builder.generate",
            "tree_sha256": tree_sha256,
            "files": files,
        }), encoding="utf-8")
        row = {
            "path": "bundle",
            "manifest": "bundle.manifest.json",
            "owner": "Tools/tests/fixtures/e2e/builder.py",
        }

        errors = []
        facts = test_catalog._bundle_facts(root, row, errors)
        self.assertEqual([], errors)
        self.assertEqual((1, len(content)),
                         (facts["files"], facts["bytes"]))

        member.write_text("drifted bytes\n", encoding="utf-8")
        errors = []
        test_catalog._bundle_facts(root, row, errors)
        self.assertTrue(any(
            "differs from manifest" in error for error in errors), errors)

    def test_rendering_is_deterministic_from_one_valid_catalog(self):
        root = self.root()
        SyntheticCatalogWorkspace.write(
            root,
            test_source=(
                "import unittest\n"
                "from Tools.tests.support.sample_fixture import value\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_value(self):\n"
                "        self.assertEqual(1, value())\n"
            ),
            fixture_source="def value():\n    return 1\n",
        )
        catalog, errors = test_catalog.build_catalog(root)
        self.assertEqual([], errors)

        markdown = test_catalog.render_markdown(catalog)
        json_text = test_catalog.render_json(catalog)

        self.assertEqual(markdown, test_catalog.render_markdown(catalog))
        self.assertEqual(json_text, test_catalog.render_json(catalog))
        rendered = json.loads(json_text)
        self.assertEqual(catalog["schema_version"],
                         rendered["schema_version"])
        self.assertEqual(1, rendered["summary"]["test_cases"])


class TestRunnerDeadlineIntegrationTests(unittest.TestCase):
    """One bounded process seam; no governance repository or lifecycle."""

    @unittest.skipUnless(os.name == "posix", "CI deadline requires POSIX process isolation")
    def test_deadline_terminates_descendants_and_reclaims_private_fixture_space(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = '''import json, os, subprocess, sys, tempfile, time, unittest
from pathlib import Path
class Probe(unittest.TestCase):
    def test_timeout(self):
        child = subprocess.Popen([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        resource = tempfile.mkdtemp(prefix="owned-test-resource-")
        Path("probe.json").write_text(json.dumps({"pid": child.pid, "resource": resource, "tmpdir": os.environ["TMPDIR"]}))
        time.sleep(60)
'''
            (root / "deadline_probe.py").write_text(source, encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(ROOT), str(root))),
                   "PYTHONDONTWRITEBYTECODE": "1"}
            group = test_runner.TestGroup("deadline_probe", "deadline_probe.py",
                ("deadline_probe.Probe.test_timeout",), False)
            progress = root / "progress.jsonl"
            result = test_runner._run_child(group, python=sys.executable, root=root,
                env=env, progress_path=progress, deadline=time.monotonic() + 3)
            self.assertEqual(124, result.returncode)
            self.assertIsNone(result.measurement)
            self.assertIn("deadline exceeded", result.stderr)
            observed = json.loads((root / "probe.json").read_text())
            self.assertFalse(Path(observed["resource"]).exists())
            self.assertFalse(Path(observed["tmpdir"]).exists())
            status = subprocess.run(["ps", "-o", "stat=", "-p", str(observed["pid"])],
                text=True, capture_output=True, check=False).stdout.strip()
            self.assertTrue(not status or status.startswith("Z"), status)
            rows = [json.loads(line) for line in progress.read_text().splitlines()]
            self.assertEqual("incomplete", rows[0]["state"])
            self.assertFalse(any(row.get("kind") == "test-run-finished" for row in rows))


class TestCatalogProjectionIntegrationTests(unittest.TestCase):
    """The sole repository-wide projection freshness check."""

    def test_repository_manifest_and_both_projections_are_current(self):
        catalog, errors = test_catalog.build_catalog(ROOT)

        self.assertEqual([], errors)
        self.assertEqual(
            len(list((ROOT / "Tools/tests").glob("test_*.py"))),
            catalog["summary"]["test_modules"])
        self.assertEqual(0, catalog["summary"]["cross_test_imports"])
        self.assertEqual(
            (ROOT / test_catalog.MARKDOWN_OUTPUT).read_text(encoding="utf-8"),
            test_catalog.render_markdown(catalog))
        self.assertEqual(
            (ROOT / test_catalog.JSON_OUTPUT).read_text(encoding="utf-8"),
            test_catalog.render_json(catalog))


if __name__ == "__main__":
    unittest.main()
