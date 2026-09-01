"""Owner contracts for test discovery, classification, and projections."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import Tools.platform.common.kblib as kblib
from Tools.platform.distribution import test_catalog, test_runner


ROOT = Path(__file__).resolve().parents[2]


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
        self.assertEqual(
            ["Tools/tests/support/sample_fixture.py"],
            module["fixture_dependencies"])
        self.assertEqual(
            {"process_calls": 0, "temp_resources": 0,
             "file_copies": 0, "full_repository_copies": 0},
            case["execution"]["transitive_effects"])

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
