"""The Tool catalog is a generated view, never a second boundary owner."""

import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.fspath(TOOLS))

import Tools.platform.distribution.tool_catalog as tool_catalog  # noqa: E402
import generate_tool_catalog  # noqa: E402


TAXONOMY = """\
schema_version: 1
areas:
  - area_id: platform
    purpose: Shared implementation mechanics.
    domains: [common]
  - area_id: execution
    purpose: Execute current contracts.
    domains: [evidence]
layers:
  - layer_id: contract
    purpose: Parse and project machine contracts.
  - layer_id: application
    purpose: Own executable Tool behaviour.
  - layer_id: entrypoint
    purpose: Expose a stable command surface.
"""

BOUNDARIES = """\
schema_version: 3
modules:
  - module: platform.common.alpha
    path: Tools/platform/common/alpha.py
    area: platform
    domain: common
    layer: contract
    public: [current_receipt_errors, public_api, unused_api]
    exceptions:
      - consumer: platform.common.beta
        symbol: _private_api
        necessity: fixture-bound private read
        retires_when: beta stops consuming it
  - module: beta
    path: Tools/beta.py
    area: platform
    domain: common
    layer: entrypoint
    public: []
  - module: platform.common.beta
    path: Tools/platform/common/beta.py
    area: platform
    domain: common
    layer: application
    public: [main]
  - module: gone
    path: Tools/gone.py
    area: platform
    domain: common
    layer: contract
    public: []
  - module: mcp_server
    path: Tools/mcp_server.py
    area: platform
    domain: common
    layer: entrypoint
    public: []
  - module: execution.evidence.receipt_type_contract
    path: Tools/execution/evidence/receipt_type_contract.py
    area: execution
    domain: evidence
    layer: contract
    public: []
"""

POLICY = """\
schema_version: 6
artifact: agent-interface-policy
host_transports:
  - transport_id: fixture-mcp-stdio
    protocol: mcp
    mode: stdio
    host_exposure: shared-bridge
    module: mcp_server
    path: Tools/mcp_server.py
    server_name: fixture
    command: python3
consumption_defaults:
  read: snapshot
  write: replace
  read-write: transaction
path_defaults: []
path_overrides: []
path_activation_overrides: []
tools:
  - tool: beta
    exposure: mcp
    workspace_argument: root
    workspace_access: read
    value_arguments: []
    read_paths: []
    write_paths: []
    read_write_paths: []
    external_write: none
"""

CAPABILITIES = """\
schema_version: 3
capabilities:
  - capability_id: alpha-producer-v1
    kind: producer
    capability_version: 1.0.0
    implementation_owner: Tools/platform/common/alpha.py
    invocation_owner: Tools/beta.py
    writers: []
    checkers: []
    consumers: [Tools/platform/common/beta.py]
    operations: []
    receipt_contracts:
      - receipt_type_id: fixture-receipt-v1
        validator_owner: Tools.platform.common.alpha:current_receipt_errors
        catalog_lifecycle: [hot, historical, cold]
        reference_source_kind: none
"""

ALPHA = """\
def public_api():
    return 1


def unused_api():
    return 2


def _private_api():
    return 3


def current_receipt_errors(record, *, root=None):
    return []
"""

BETA = """\
from Tools.platform.common.beta import main as _main

IMPLEMENTATION_MODULE = "Tools.platform.common.beta"


def main(argv=None):
    return _main(argv)
"""

BETA_IMPLEMENTATION = """\
import argparse
from Tools.platform.common.alpha import _private_api, public_api


def main_value():
    return public_api() + _private_api()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    return parser.parse_args(argv)
"""

MCP_SERVER = "VALUE = 'fixture transport'\n"


class CatalogFixture:
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        (self.root / "Tools/compiled").mkdir(parents=True)
        (self.root / "Tools/tool-taxonomy.yaml").write_text(
            TAXONOMY, encoding="utf-8")
        (self.root / "Tools/module-boundaries.yaml").write_text(
            BOUNDARIES, encoding="utf-8")
        (self.root / "Tools/agent-interface-policy.yaml").write_text(
            POLICY, encoding="utf-8")
        (self.root / "Tools/operation-capabilities.yaml").write_text(
            CAPABILITIES, encoding="utf-8")
        (self.root / "Tools/platform/common").mkdir(parents=True)
        (self.root / "Tools/execution/evidence").mkdir(parents=True)
        (self.root / "Tools/platform/common/alpha.py").write_text(
            ALPHA, encoding="utf-8")
        (self.root / "Tools/beta.py").write_text(BETA, encoding="utf-8")
        (self.root / "Tools/platform/common/beta.py").write_text(
            BETA_IMPLEMENTATION, encoding="utf-8")
        (self.root / "Tools/mcp_server.py").write_text(
            MCP_SERVER, encoding="utf-8")
        (self.root / "Tools/execution/evidence/receipt_type_contract.py").write_text(
            "# Registry-driven dispatcher fixture.\n", encoding="utf-8")
        # This file is intentionally absent from module-boundaries.yaml.
        (self.root / "Tools/loose.py").write_text(
            "VALUE = 1\n", encoding="utf-8")

    def tearDown(self):
        self._temporary.cleanup()


class ToolCatalogProjection(CatalogFixture, unittest.TestCase):
    def test_joins_declared_classification_with_actual_source_consumers(self):
        catalog = tool_catalog.build_catalog(self.root)

        modules = {row["module"]: row for row in catalog["modules"]}
        self.assertEqual(
            {"area": "platform", "domain": "common", "layer": "contract",
             "resolved": True, "problems": []},
            modules["platform.common.alpha"]["classification"])
        self.assertEqual(2, modules["platform.common.alpha"]["interface"][
            "static_internal_symbol_count"])
        self.assertEqual(1, modules["platform.common.alpha"]["interface"][
            "static_internal_consumer_count"])
        self.assertTrue(modules["platform.common.alpha"]["interface"][
            "registered_internal"])
        self.assertEqual(
            "python-module", modules["platform.common.alpha"]["type"])

        public = {
            (row["module"], row["symbol"]): row
            for row in catalog["static_public_interfaces"]
        }
        self.assertEqual(
            ["platform.common.beta"],
            public[("platform.common.alpha", "public_api")]["consumers"])
        self.assertEqual(
            "declared-unused",
            public[("platform.common.alpha", "unused_api")]["status"])
        self.assertEqual(
            [
                {"module": "platform.common.alpha",
                 "symbol": "current_receipt_errors"},
                {"module": "platform.common.alpha", "symbol": "unused_api"},
            ],
            catalog["declared_unused_static_public_apis"])
        observed = {
            (row["module"], row["symbol"]): row
            for row in catalog["public_interfaces"]
        }
        self.assertEqual(
            ["execution.evidence.receipt_type_contract"],
            observed[("platform.common.alpha", "current_receipt_errors")][
                "registered_consumers"])
        self.assertEqual(
            ["beta"], observed[("platform.common.beta", "main")][
                "registered_consumers"])
        self.assertEqual(
            [{"module": "platform.common.alpha", "symbol": "unused_api"}],
            catalog["declared_public_apis_without_observed_consumers"])

        symbol_relationships = {
            (row["relationship"], row["identity"]): row
            for row in catalog["registered_symbol_relationships"]
        }
        self.assertEqual(
            "platform.common.beta",
            symbol_relationships[("entrypoint-main", "alpha-producer-v1")][
                "owner_module"])
        self.assertEqual(
            "platform.common.alpha",
            symbol_relationships[(
                "receipt-validator", "fixture-receipt-v1")]["owner_module"])

        private = catalog["private_consumption"]["actual"]
        self.assertEqual(1, len(private))
        self.assertEqual("platform.common.alpha", private[0]["module"])
        self.assertEqual("_private_api", private[0]["symbol"])
        self.assertEqual("platform.common.beta", private[0]["consumer"])
        self.assertTrue(private[0]["declaration_present"])

        relationships = catalog["registered_capability_relationships"]
        self.assertEqual(
            {"consumer", "invocation-owner"},
            {row["relationship"] for row in relationships})
        self.assertTrue(all(row["owner_module"] == "platform.common.alpha"
                            for row in relationships))
        by_role = {row["relationship"]: row for row in relationships}
        self.assertEqual(
            "platform.common.beta", by_role["consumer"]["consumer_module"])
        self.assertEqual(
            "beta", by_role["invocation-owner"]["consumer_module"])

    def test_reports_exposure_and_integrity_gaps_without_reclassifying_them(self):
        catalog = tool_catalog.build_catalog(self.root)

        interface = catalog["external_interfaces"]
        self.assertEqual(1, len(interface))
        self.assertTrue(interface[0]["cli"])
        self.assertTrue(interface[0]["mcp"])
        self.assertEqual("via:fixture-mcp-stdio", interface[0]["host"])
        self.assertEqual("read", interface[0]["workspace_access"])

        transport, = catalog["host_transports"]
        self.assertEqual("mcp_server", transport["module"])
        self.assertEqual("shared-bridge", transport["host_exposure"])
        self.assertTrue(transport["path_matches_module"])
        transport_module = next(
            row for row in catalog["modules"]
            if row["module"] == "mcp_server")
        self.assertTrue(transport_module["interface"]["mcp_transport"])
        self.assertEqual(
            "shared-bridge:fixture-mcp-stdio",
            transport_module["interface"]["host"])

        self.assertEqual(
            ["loose"], catalog["integrity"]["manifest_missing_modules"])
        self.assertEqual(
            ["gone"], catalog["integrity"]["manifest_stale_modules"])
        self.assertEqual("loose", catalog["unclassified_modules"][0]["module"])
        self.assertFalse(
            next(row for row in catalog["modules"]
                 if row["module"] == "loose")["classification"]["resolved"])

        self.assertEqual(
            [
                {"kind": "manifest_missing_modules", "count": 1},
                {"kind": "manifest_stale_modules", "count": 1},
                {"kind": "unclassified_modules", "count": 1},
            ],
            tool_catalog.correctness_integrity_findings(catalog))

    def test_source_export_list_cannot_create_a_second_public_surface(self):
        path = self.root / "Tools/platform/common/alpha.py"
        path.write_text(
            ALPHA + "\n\ndef unowned_export():\n    return 4\n"
            "\n\n__all__ = ['public_api', 'unowned_export']\n",
            encoding="utf-8")

        catalog = tool_catalog.build_catalog(self.root)

        self.assertEqual([
            {"module": "platform.common.alpha",
             "symbol": "unowned_export"},
        ], catalog["integrity"]["source_public_exports_undeclared"])
        exported = {
            (row["module"], row["symbol"]): row
            for row in catalog["source_public_exports"]
        }
        self.assertTrue(exported[(
            "platform.common.alpha", "public_api")]["boundary_declared"])
        self.assertFalse(exported[(
            "platform.common.alpha", "unowned_export")][
                "boundary_declared"])
        self.assertIn(
            {"kind": "source_public_exports_undeclared", "count": 1},
            tool_catalog.correctness_integrity_findings(catalog))

    def test_nonliteral_source_export_list_is_an_integrity_defect(self):
        path = self.root / "Tools/platform/common/alpha.py"
        path.write_text(
            ALPHA + "\n\n__all__ = build_exports()\n",
            encoding="utf-8")

        catalog = tool_catalog.build_catalog(self.root)

        self.assertEqual(
            "platform.common.alpha",
            catalog["integrity"]["invalid_source_public_exports"][0][
                "module"])
        self.assertIn(
            {"kind": "invalid_source_public_exports", "count": 1},
            tool_catalog.correctness_integrity_findings(catalog))

    def test_current_projection_with_integrity_defects_is_not_a_green_check(self):
        self.assertEqual(0, tool_catalog.project_catalog(self.root)[0])

        code, statuses = tool_catalog.project_catalog(self.root, check=True)

        self.assertEqual(3, code)
        self.assertTrue(all(
            row["status"] == "current" for row in statuses[:2]))
        self.assertEqual(
            {"path": "<tool-boundary-integrity>", "status": "invalid",
             "findings": [
                 {"kind": "manifest_missing_modules", "count": 1},
                 {"kind": "manifest_stale_modules", "count": 1},
                 {"kind": "unclassified_modules", "count": 1},
             ]},
            statuses[2])

    def test_markdown_and_json_are_stable_views_of_the_same_value(self):
        catalog = tool_catalog.build_catalog(self.root)
        markdown = tool_catalog.render_markdown(catalog)
        machine = tool_catalog.render_json(catalog)

        self.assertEqual(markdown, tool_catalog.render_markdown(catalog))
        self.assertEqual(machine, tool_catalog.render_json(catalog))
        self.assertIn("does not define module responsibilities", markdown)
        self.assertIn("## Area → Domain → Layer → Module", markdown)
        self.assertIn("## Static Python symbol consumption", markdown)
        self.assertIn("## Registered Python symbol consumption", markdown)
        self.assertIn("## Registered capability relationships", markdown)
        self.assertIn("## Host transports", markdown)
        self.assertIn("## CLI, MCP, and Host exposure", markdown)
        self.assertIn("## Private consumption and exceptions", markdown)
        self.assertIn("## Unclassified modules", markdown)
        self.assertIn("## Circular dependencies", markdown)
        self.assertIn('"artifact":"tool-catalog-projection"', machine)
        self.assertIn("| undeclared public consumption | — |", markdown)

    def test_dependency_cycles_reuse_the_boundary_fact_graph(self):
        (self.root / "Tools/platform/common/alpha.py").write_text(
            "import Tools.platform.common.beta as beta\n\n"
            "def public_api():\n    return beta.main_value()\n"
            "\ndef unused_api():\n    return 2\n"
            "\ndef _private_api():\n    return 3\n",
            encoding="utf-8")
        (self.root / "Tools/platform/common/beta.py").write_text(
            "import argparse\n"
            "import Tools.platform.common.alpha as alpha\n\n"
            "def main_value():\n    return alpha.public_api()\n\n"
            "def main(argv=None):\n"
            "    parser = argparse.ArgumentParser()\n"
            "    parser.add_argument('root')\n"
            "    return parser.parse_args(argv)\n",
            encoding="utf-8")

        catalog = tool_catalog.build_catalog(self.root)

        self.assertEqual(
            [["platform.common.alpha", "platform.common.beta"]],
            catalog["cycles"]["module_cycles"])

    def test_manifest_path_mismatch_is_reported_without_hiding_actual_path(self):
        boundary = self.root / "Tools/module-boundaries.yaml"
        boundary.write_text(
            BOUNDARIES.replace(
                "path: Tools/platform/common/alpha.py",
                "path: Tools/wrong/alpha.py"),
            encoding="utf-8")

        catalog = tool_catalog.build_catalog(self.root)

        self.assertEqual([{
            "module": "platform.common.alpha",
            "declared_path": "Tools/wrong/alpha.py",
            "observed_path": "Tools/platform/common/alpha.py",
        }], catalog["integrity"]["manifest_path_mismatches"])
        alpha = next(row for row in catalog["modules"]
                     if row["module"] == "platform.common.alpha")
        self.assertEqual("Tools/platform/common/alpha.py", alpha["path"])

    def test_declared_transport_without_source_is_an_integrity_gap(self):
        policy = self.root / "Tools/agent-interface-policy.yaml"
        policy.write_text(
            POLICY.replace("module: mcp_server", "module: absent_server")
            .replace("path: Tools/mcp_server.py",
                     "path: Tools/absent_server.py"),
            encoding="utf-8")

        catalog = tool_catalog.build_catalog(self.root)

        self.assertEqual(1, len(catalog["integrity"][
            "invalid_host_transports"]))
        transport = catalog["integrity"]["invalid_host_transports"][0]
        self.assertFalse(transport["module_present"])
        self.assertFalse(transport["path_matches_module"])

    def test_host_transport_shape_is_validated_by_its_source_contract(self):
        policy = self.root / "Tools/agent-interface-policy.yaml"
        policy.write_text(
            POLICY.replace("path: Tools/mcp_server.py",
                           "path: Tools/not-the-module.py"),
            encoding="utf-8")

        with self.assertRaisesRegex(
                tool_catalog.ToolCatalogError,
                r"path must be Tools/mcp_server\.py"):
            tool_catalog.build_catalog(self.root)

    def test_source_parse_failure_is_a_catalog_error(self):
        (self.root / "Tools/platform/common/alpha.py").write_text(
            "def broken(:\n", encoding="utf-8")

        with self.assertRaisesRegex(
                tool_catalog.ToolCatalogError,
                "cannot validate Tool catalog sources"):
            tool_catalog.build_catalog(self.root)

    def test_shared_host_transport_cannot_have_two_machine_owners(self):
        policy = self.root / "Tools/agent-interface-policy.yaml"
        duplicate = """\
  - transport_id: fixture-second-mcp-stdio
    protocol: mcp
    mode: stdio
    host_exposure: shared-bridge
    module: mcp_server
    path: Tools/mcp_server.py
    server_name: fixture
    command: python3
"""
        policy.write_text(
            POLICY.replace("consumption_defaults:",
                           duplicate + "\nconsumption_defaults:"),
            encoding="utf-8")

        with self.assertRaisesRegex(
                tool_catalog.ToolCatalogError,
                "exactly one supported shared Host transport"):
            tool_catalog.build_catalog(self.root)

    def test_unsupported_source_contract_version_fails_closed(self):
        taxonomy = self.root / "Tools/tool-taxonomy.yaml"
        taxonomy.write_text(
            TAXONOMY.replace("schema_version: 1", "schema_version: 99"),
            encoding="utf-8")

        with self.assertRaisesRegex(
                tool_catalog.ToolCatalogError, "schema_version must be 1"):
            tool_catalog.build_catalog(self.root)


class ToolCatalogDriftCheck(CatalogFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # Drift/freshness tests need a conformant source graph.  The projection
        # tests above deliberately retain a missing/stale pair to prove the
        # diagnostic view, but a current invalid view must now fail closed.
        (self.root / "Tools/loose.py").unlink()
        (self.root / "Tools/gone.py").write_text(
            "VALUE = 1\n", encoding="utf-8")

    def test_public_command_generates_then_checks_both_outputs(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, generate_tool_catalog.main([os.fspath(
                self.root)]))
            self.assertEqual(0, generate_tool_catalog.main([
                os.fspath(self.root), "--check"]))
        self.assertIn("written: Tools/TOOL_CATALOG.md", output.getvalue())
        self.assertIn(
            "current: Tools/compiled/tool-catalog.json", output.getvalue())

    def test_generate_then_check_and_refuse_manual_drift(self):
        code, written = tool_catalog.project_catalog(self.root)
        self.assertEqual(0, code)
        self.assertEqual(
            [
                {"path": "Tools/TOOL_CATALOG.md", "status": "written"},
                {"path": "Tools/compiled/tool-catalog.json",
                 "status": "written"},
            ],
            written)
        markdown = self.root / tool_catalog.MARKDOWN_OUTPUT
        machine = self.root / tool_catalog.JSON_OUTPUT
        self.assertTrue(markdown.is_file())
        self.assertTrue(machine.is_file())

        code, current = tool_catalog.project_catalog(self.root, check=True)
        self.assertEqual(0, code)
        self.assertTrue(all(row["status"] == "current" for row in current))

        markdown.write_text(
            markdown.read_text(encoding="utf-8") + "manual edit\n",
            encoding="utf-8")
        code, drift = tool_catalog.project_catalog(self.root, check=True)
        self.assertEqual(2, code)
        self.assertEqual("drift", drift[0]["status"])
        self.assertEqual("current", drift[1]["status"])

    def test_source_consumer_change_makes_both_projections_stale(self):
        tool_catalog.project_catalog(self.root)
        implementation = self.root / "Tools/platform/common/beta.py"
        implementation.write_text(
            BETA_IMPLEMENTATION.replace(
                "public_api()", "public_api() + public_api()"),
            encoding="utf-8")
        # Repeating the same consumption does not change the set projection.
        code, statuses = tool_catalog.project_catalog(self.root, check=True)
        self.assertEqual(0, code)
        self.assertTrue(all(row["status"] == "current" for row in statuses))

        implementation.write_text(
            BETA_IMPLEMENTATION +
            "\nfrom Tools.platform.common.alpha import unused_api\n"
            "OTHER = unused_api()\n",
            encoding="utf-8")
        code, statuses = tool_catalog.project_catalog(self.root, check=True)
        self.assertEqual(2, code)
        self.assertTrue(all(row["status"] == "drift" for row in statuses))


if __name__ == "__main__":
    unittest.main()
