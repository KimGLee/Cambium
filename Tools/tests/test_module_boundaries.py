"""Enforce the Tool-owned module boundary engineering contract.

This suite is the machine consumer the contract names.  It runs in the
distribution's own CI and registers no Gate ID, for the reason the
Distribution Boundary already gives about the unit suite: an adopter carries
`Tools/` but cannot reorganize it, so an obligation about this
distribution's internal structure must not be projected onto adopters as
something they are asked to resolve.

What it checks is the declared contract, not a size policy.  Every finding
below is either "the tree does something the manifest does not declare" or
"the manifest declares something the tree does not do".  Line counts live in
the advisory report next door and never reach an assertion here.
"""

import ast
import os
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TOOLS)
for import_root in (REPO, TOOLS):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.platform.common.implementation_marker as implementation_marker  # noqa: E402
import Tools.execution.audit.audit_reconciliation_contract as audit_reconciliation_contract  # noqa: E402
import Tools.platform.distribution.module_boundary_facts as boundary_facts  # noqa: E402
import Tools.platform.distribution.module_boundary_report as module_boundary_report  # noqa: E402


MANIFEST = os.path.join(TOOLS, "module-boundaries.yaml")
TAXONOMY = os.path.join(TOOLS, "tool-taxonomy.yaml")


class ImportAttributionProbes(unittest.TestCase):
    KNOWN = {"consumer", "pkg", "rootmod", "area.domain.owner"}
    KNOWN_FULL = {
        "consumer", "pkg", "pkg.sub", "rootmod", "area.domain.owner",
    }

    def facts(self, source):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "consumer.py"
            path.write_text(source, encoding="utf-8")
            return boundary_facts.module_facts(
                temp, "consumer.py", self.KNOWN, self.KNOWN_FULL)

    def test_from_package_import_submodule_credits_the_submodule(self):
        facts = self.facts(
            "from pkg import sub\n"
            "answer = sub.public_call()\n")

        self.assertIn(("pkg.sub", "public_call"), facts["consumes"])
        self.assertNotIn(("pkg", "public_call"), facts["consumes"])

    def test_from_package_import_submodule_alias_keeps_full_identity(self):
        facts = self.facts(
            "from pkg import sub as selected\n"
            "answer = selected.public_call()\n")

        self.assertIn(("pkg.sub", "public_call"), facts["consumes"])
        self.assertNotIn(("pkg", "public_call"), facts["consumes"])

    def test_import_package_submodule_forms_keep_python_bindings(self):
        direct = self.facts(
            "import pkg.sub\n"
            "answer = pkg.sub.public_call()\n")
        aliased = self.facts(
            "import pkg.sub as selected\n"
            "answer = selected.public_call()\n")

        self.assertIn(("pkg.sub", "public_call"), direct["consumes"])
        self.assertIn(("pkg.sub", "public_call"), aliased["consumes"])

    def test_root_import_and_direct_symbol_import_are_unchanged(self):
        root = self.facts(
            "import pkg\n"
            "answer = pkg.public_call()\n")
        symbol = self.facts(
            "from rootmod import exported\n"
            "answer = exported()\n")

        self.assertIn(("pkg", "public_call"), root["consumes"])
        self.assertIn(("rootmod", "exported"), symbol["consumes"])

    def test_tools_prefix_is_removed_without_collapsing_the_module(self):
        facts = self.facts(
            "import Tools.area.domain.owner as owner\n"
            "answer = owner.public_call()\n")

        self.assertEqual(["area.domain.owner"], facts["imports"])
        self.assertIn(
            ("area.domain.owner", "public_call"), facts["consumes"])

    def test_function_argument_shadowing_does_not_widen_module_surface(self):
        facts = self.facts(
            "import Tools.area.domain.owner as contract\n"
            "def read(contract):\n"
            "    return contract.root\n")

        self.assertNotIn(
            ("area.domain.owner", "root"), facts["consumes"])

    def test_lazy_import_is_local_to_the_function_that_declares_it(self):
        facts = self.facts(
            "def producing():\n"
            "    import Tools.area.domain.owner as selected\n"
            "    return selected.public_call()\n"
            "def unrelated(selected):\n"
            "    return selected.not_a_module_export\n")

        self.assertIn(
            ("area.domain.owner", "public_call"), facts["consumes"])
        self.assertNotIn(
            ("area.domain.owner", "not_a_module_export"), facts["consumes"])

    def test_function_defaults_use_enclosing_not_function_local_scope(self):
        facts = self.facts(
            "import Tools.area.domain.owner as contract\n"
            "def read(contract=contract.default_value()):\n"
            "    return contract.local_value\n")

        self.assertIn(
            ("area.domain.owner", "default_value"), facts["consumes"])
        self.assertNotIn(
            ("area.domain.owner", "local_value"), facts["consumes"])

    def test_unaliased_tools_import_resolves_an_arbitrarily_deep_chain(self):
        facts = self.facts(
            "import Tools.area.domain.owner\n"
            "answer = Tools.area.domain.owner.public_call()\n")

        self.assertEqual(["area.domain.owner"], facts["imports"])
        self.assertIn(
            ("area.domain.owner", "public_call"), facts["consumes"])

    def test_a_qualified_marker_is_a_wrapper_and_absence_is_ordinary(self):
        self.assertTrue(boundary_facts.is_cli_module(
            "IMPLEMENTATION_MODULE = 'Tools.area.domain.owner'\n"
            "def main(argv=None):\n"
            "    return 0\n"))
        self.assertIsNone(boundary_facts.implementation_module(
            "VALUE = 1\n"))
        self.assertFalse(boundary_facts.is_cli_module(
            "def main(argv=None):\n"
            "    return 0\n"))
        self.assertTrue(boundary_facts.is_cli_module(
            "import argparse\n"
            "def main(argv=None):\n"
            "    return argparse.ArgumentParser().parse_args(argv)\n"))
        self.assertFalse(boundary_facts.is_cli_module(
            "IMPLEMENTATION_MODULE = 'Tools.area.domain.owner'\n"))

    def test_malformed_marker_never_degrades_to_not_a_wrapper(self):
        cases = (
            "IMPLEMENTATION_MODULE = 'Tools.a.b'\n"
            "IMPLEMENTATION_MODULE = 'Tools.a.c'\n",
            "IMPLEMENTATION_MODULE = choose_owner()\n",
            "IMPLEMENTATION_MODULE = 'elsewhere.owner'\n",
        )
        for source in cases:
            with self.subTest(source=source), self.assertRaises(
                    implementation_marker.ImplementationMarkerError):
                boundary_facts.is_cli_module(source)

# Every refusal below names the command that answers it.  A contract whose
# failures a reader cannot act on becomes a contract people route around, and
# routine kernel work reaches these checks often enough -- a new governance
# capability is usually a new leaf and new tool code together -- that the cost
# of not saying so compounds.
REGENERATE = ("python3 Tools/module_boundary_report.py --emit-manifest"
              " --output Tools/module-boundaries.yaml")


def load_manifest():
    with open(MANIFEST, encoding="utf-8") as handle:
        return kblib.parse_yaml_subset(handle.read())


def load_taxonomy():
    with open(TAXONOMY, encoding="utf-8") as handle:
        return kblib.parse_yaml_subset(handle.read())


class ManifestShape(unittest.TestCase):
    """The declaration itself must be well formed before it can bind."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest()
        cls.taxonomy = load_taxonomy()
        cls.facts = boundary_facts.collect(REPO)

    def test_schema_version_is_current(self):
        self.assertEqual(
            module_boundary_report.MANIFEST_SCHEMA_VERSION,
            self.manifest.get("schema_version"))
        self.assertEqual(1, self.taxonomy.get("schema_version"))
        self.assertEqual([], module_boundary_report.manifest_errors(
            self.manifest))

    def test_retired_migration_fields_are_not_part_of_the_current_schema(self):
        candidate = dict(self.manifest)
        candidate["modules"] = [dict(row)
                                for row in self.manifest["modules"]]
        candidate["modules"][0]["provisional"] = True

        errors = module_boundary_report.manifest_errors(candidate)

        self.assertTrue(any("fields are not closed" in error
                            for error in errors), errors)

    def test_every_module_has_one_resolved_hierarchical_classification(self):
        area_domains = {}
        for area in self.taxonomy.get("areas") or ():
            area_id = area.get("area_id")
            self.assertIsInstance(area_id, str)
            self.assertTrue(area_id)
            self.assertNotIn(area_id, area_domains)
            area_domains[area_id] = set(area.get("domains") or ())
        layers = {row.get("layer_id")
                  for row in self.taxonomy.get("layers") or ()}
        self.assertNotIn(None, layers)
        errors = []
        for row in self.manifest.get("modules") or ():
            module = row.get("module")
            area = row.get("area")
            domain = row.get("domain")
            layer = row.get("layer")
            if area not in area_domains:
                errors.append("%s has unknown area %r" % (module, area))
            elif domain not in area_domains[area]:
                errors.append("%s has unknown %s domain %r" %
                              (module, area, domain))
            if layer not in layers:
                errors.append("%s has unknown layer %r" % (module, layer))
        self.assertEqual([], errors)

    def test_manifest_regeneration_preserves_reviewed_classification(self):
        rendered = module_boundary_report._emit_manifest(
            REPO, manifest_path=MANIFEST)
        regenerated = kblib.parse_yaml_subset(rendered)
        before = {
            row["module"]: (row["area"], row["domain"], row["layer"])
            for row in self.manifest["modules"]
        }
        after = {
            row["module"]: (row["area"], row["domain"], row["layer"])
            for row in regenerated["modules"]
        }
        self.assertEqual(before, after)

    def test_manifest_regeneration_preserves_current_public_surface_and_adds_consumers(
            self):
        """Reviewed current exports are not derivable from imports alone."""
        rendered = module_boundary_report._emit_manifest(
            REPO, manifest_path=MANIFEST)
        regenerated = kblib.parse_yaml_subset(rendered)
        before = {
            row["module"]: set(row.get("public") or ())
            for row in self.manifest["modules"]
        }
        after = {
            row["module"]: set(row.get("public") or ())
            for row in regenerated["modules"]
        }
        for module, promised in before.items():
            with self.subTest(module=module, source="recorded"):
                self.assertLessEqual(promised, after[module])
        for _consumer, target, symbol in boundary_facts.consumption_pairs(
                self.facts):
            if symbol.startswith("_") or target not in after:
                continue
            with self.subTest(module=target, symbol=symbol,
                              source="observed"):
                self.assertIn(symbol, after[target])

    def test_hierarchy_projection_lists_every_module_once(self):
        rendered = module_boundary_report.render_hierarchy(
            module_boundary_report.build_report(REPO))
        for row in self.manifest["modules"]:
            marker = "      %s  [%s]\n" % (
                row["module"], row["path"].removeprefix("Tools/"))
            self.assertEqual(1, rendered.count(marker), row["module"])

    def test_every_entry_names_a_module_once(self):
        names = [row.get("module") for row in self.manifest["modules"]]
        paths = [row.get("path") for row in self.manifest["modules"]]
        self.assertEqual(sorted(names), sorted(set(names)),
                         "a module is declared more than once")
        self.assertEqual(sorted(paths), sorted(set(paths)),
                         "a shipped path is declared more than once")
        for row in self.manifest["modules"]:
            self.assertTrue(row.get("path", "").startswith("Tools/"),
                            "%s declares no shipped path" % row.get("module"))


class Completeness(unittest.TestCase):
    """A contract with holes in its membership is a suggestion.

    Both directions fail: an undeclared module is how absorption relocates
    out of sight, and an entry whose file is gone is how a register rots into
    a description of a tree that no longer exists.
    """

    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest()
        cls.facts = boundary_facts.collect(REPO)

    def test_every_shipped_module_is_declared(self):
        declared = {row["module"] for row in self.manifest["modules"]}
        missing = sorted(set(self.facts) - declared)
        self.assertEqual([], missing,
                         "shipped modules absent from the manifest: %s\n"
                         "A new module joins the contract by regenerating:\n"
                         "  %s" % (", ".join(missing), REGENERATE))

    def test_every_entry_has_a_shipped_module(self):
        declared = {row["module"] for row in self.manifest["modules"]}
        stale = sorted(declared - set(self.facts))
        self.assertEqual([], stale,
                         "manifest entries with no shipped module: %s\n"
                         "A removed module leaves the contract the same way:\n"
                         "  %s" % (", ".join(stale), REGENERATE))


class ProcessBoundaries(unittest.TestCase):
    """Cambium children must inherit the stable path-capability chain."""

    def test_tool_modules_do_not_bypass_the_shared_subprocess_boundary(self):
        import ast

        # mcp_server brokers the original descriptors; kblib owns the one
        # wrapper that merges them into subsequent Cambium process launches.
        owners = {
            "platform/common/kblib.py",
            "platform/agent_interface/mcp_server.py",
        }
        bypasses = []
        for relative in boundary_facts.shipped_modules(TOOLS):
            if relative in owners:
                continue
            path = os.path.join(TOOLS, relative)
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and \
                        node.module == "subprocess" and any(
                            alias.name in ("run", "Popen")
                            for alias in node.names):
                    bypasses.append("%s:%d imports subprocess.%s" % (
                        relative, node.lineno,
                        "/".join(alias.name for alias in node.names)))
                if not isinstance(node, ast.Call) or \
                        not isinstance(node.func, ast.Attribute) or \
                        not isinstance(node.func.value, ast.Name) or \
                        node.func.value.id != "subprocess" or \
                        node.func.attr not in ("run", "Popen"):
                    continue
                bypasses.append("%s:%d calls subprocess.%s" % (
                    relative, node.lineno, node.func.attr))
        self.assertEqual(
            [], bypasses,
            "Cambium child processes must use "
            "kblib.run_cambium_subprocess so retained descriptors and the "
            "ACK channel survive: %s" % "; ".join(bypasses))


class PublicSurface(unittest.TestCase):
    """Cross-module consumption stays inside what the owner declared."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest()
        cls.facts = boundary_facts.collect(REPO)
        cls.by_module = {row["module"]: row
                         for row in cls.manifest["modules"]}

    def _excepted(self, target, consumer, symbol):
        row = self.by_module.get(target) or {}
        for entry in row.get("exceptions") or ():
            if entry.get("consumer") == consumer and \
                    entry.get("symbol") == symbol:
                return entry
        return None

    def test_consumption_is_declared_or_excepted(self):
        undeclared = []
        for consumer, target, symbol in \
                boundary_facts.consumption_pairs(self.facts):
            row = self.by_module.get(target)
            if row is None:
                continue  # Completeness owns this failure.
            if symbol in (row.get("public") or ()):
                continue
            if self._excepted(target, consumer, symbol):
                continue
            undeclared.append("%s -> %s.%s" % (consumer, target, symbol))
        self.assertEqual(
            [], sorted(undeclared),
            "consumption outside the declared public surface: %s\n"
            "Offer the symbol deliberately, or -- if this reads a name its "
            "owner marked internal -- record why with a retirement condition. "
            "Regenerating stages it as an exception for you to annotate:\n"
            "  %s" % (", ".join(sorted(undeclared)), REGENERATE))

    def test_every_declared_public_symbol_exists_in_its_owner(self):
        missing = []
        for module, row in sorted(self.by_module.items()):
            available = set(self.facts.get(module, {}).get(
                "top_level_symbols") or ())
            for symbol in row.get("public") or ():
                if symbol not in available:
                    missing.append("%s.%s" % (module, symbol))
        self.assertEqual(
            [], missing,
            "declared public symbols absent from their machine owner: %s; "
            "retire the stale declaration or restore the actual current "
            "owner before regenerating interface projections" %
            ", ".join(missing))

    def test_source_export_lists_cannot_widen_the_boundary_contract(self):
        invalid = []
        undeclared = []
        for module, facts in sorted(self.facts.items()):
            for error in facts.get("source_public_export_errors") or ():
                invalid.append("%s: %s" % (module, error))
            declared = set(
                (self.by_module.get(module) or {}).get("public") or ())
            for symbol in facts.get("source_public_exports") or ():
                if symbol not in declared:
                    undeclared.append("%s.%s" % (module, symbol))
        self.assertEqual(
            [], invalid,
            "invalid source __all__ declarations: %s" %
            "; ".join(invalid))
        self.assertEqual(
            [], undeclared,
            "source __all__ creates a second public surface outside "
            "module-boundaries.yaml: %s" % ", ".join(undeclared))

    def test_reconciliation_projection_field_consumers_are_closed(self):
        """Runtime and transports read one lower-level field owner."""
        actual = {
            consumer
            for consumer, target, symbol in
            boundary_facts.consumption_pairs(self.facts)
            if target == "execution.audit.audit_reconciliation_contract" and
            symbol == "projection_fields"
        }
        self.assertEqual({
            "execution.audit.audit_evidence_runtime",
            "execution.audit.check_batch_close",
            "execution.audit.record_batch_review",
            "execution.task_runtime.queue_runtime.close_gate",
        }, actual)

    def test_reconciliation_projection_fields_have_one_literal_owner(self):
        """No production module restates the closed transport field set."""
        import ast

        expected = set(audit_reconciliation_contract.projection_fields())
        owners = set()
        for row in self.manifest["modules"]:
            path = os.path.join(REPO, row["path"])
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
            for node in ast.walk(tree):
                values = None
                if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
                    values = [getattr(value, "value", None)
                              for value in node.elts]
                elif isinstance(node, ast.Dict):
                    values = [getattr(value, "value", None)
                              for value in node.keys]
                if values is not None and len(values) == len(expected) and \
                        set(values) == expected:
                    owners.add(row["module"])
        self.assertEqual(
            {"execution.audit.audit_reconciliation_contract"}, owners)

    def test_exception_content_bindings_still_match(self):
        """An excepted private symbol that was rewritten must be re-argued.

        The exception recorded a judgment about a specific piece of code.  If
        that code changes the judgment was made about something else, and the
        entry has to be re-earned rather than inherited.
        """
        drifted = []
        for target, row in self.by_module.items():
            for entry in row.get("exceptions") or ():
                recorded = entry.get("content_sha256")
                if not recorded:
                    continue
                current = boundary_facts.def_span_sha256(
                    REPO, target, entry["symbol"])
                if current != recorded:
                    drifted.append("%s.%s" % (target, entry["symbol"]))
        self.assertEqual(
            [], sorted(drifted),
            "excepted definitions changed: %s\n"
            "The exception was a judgment about the old code, so it does not "
            "carry over on its own. Re-read the consumption, and when it "
            "still holds say so explicitly:\n"
            "  python3 Tools/module_boundary_report.py "
            "--emit-manifest --acknowledge-drift "
            "--output Tools/module-boundaries.yaml"
            % ", ".join(sorted(drifted)))

    def test_every_exception_carries_a_judgment(self):
        """An exception without a reason is an inventory, not a decision.

        The register exists so that a reading outside a declared surface is a
        recorded judgment rather than an accident nobody looked at. A row
        naming only the consumer and the symbol records that the coupling
        exists -- which the guard could already see -- and says nothing about
        whether it should. The two annotated fields are the judgment: why this
        is acceptable, and what would end it.
        """
        bare = []
        for target, row in self.by_module.items():
            for entry in row.get("exceptions") or ():
                if not entry.get("necessity") or not entry.get("retires_when"):
                    bare.append("%s.%s <- %s" % (target, entry.get("symbol"),
                                                 entry.get("consumer")))
        self.assertEqual(
            [], sorted(bare),
            "exceptions with no recorded judgment: %s\n"
            "Add `necessity:` and `retires_when:` to each entry in "
            "Tools/module-boundaries.yaml. Both survive regeneration; the "
            "machine never writes them because it cannot know either."
            % "; ".join(sorted(bare)))

    def test_no_exception_outlives_its_consumer(self):
        """A register that keeps retired entries stops describing anything."""
        live = {(c, m, s) for c, m, s
                in boundary_facts.consumption_pairs(self.facts)}
        unused = []
        for target, row in self.by_module.items():
            for entry in row.get("exceptions") or ():
                key = (entry.get("consumer"), target, entry.get("symbol"))
                if key not in live:
                    unused.append("%s -> %s.%s" % key)
        self.assertEqual([], sorted(unused),
                         "exceptions with no remaining consumer: %s\n"
                         "The debt is paid; drop the entry:\n"
                         "  %s" % (", ".join(sorted(unused)), REGENERATE))


class StagedTreesAreDerived(unittest.TestCase):
    """No test may hand-keep an inventory of shipped modules.

    A staged partial tree that names its dependencies by hand records what the
    tree needed on the day it was written, and nothing re-derives it. Two such
    lists existed here, and extracting one capability into a new module broke
    a test that mentioned neither module. Kernel work routinely adds and moves
    tool code, so the cost of a hand-kept list is paid again every time.
    """

    def test_no_test_hard_codes_a_module_inventory(self):
        import re

        # Three or more shipped module filenames in one literal sequence: one
        # or two is a specific reference, a run of them is an inventory.
        shipped = {os.path.basename(path) for path
                   in boundary_facts.shipped_modules(TOOLS)}
        offenders = []
        for name in sorted(os.listdir(os.path.dirname(os.path.abspath(__file__)))):
            if not name.startswith("test_") or not name.endswith(".py"):
                continue
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for run in re.finditer(r'(?:"[A-Za-z_][A-Za-z0-9_]*\.py",\s*){2,}'
                                   r'"[A-Za-z_][A-Za-z0-9_]*\.py"', text):
                found = re.findall(r'"([A-Za-z_][A-Za-z0-9_]*\.py)"', run.group(0))
                if len({f for f in found} & shipped) >= 3:
                    offenders.append("%s: %s" % (name, ", ".join(found[:4])))
        self.assertEqual(
            [], sorted(offenders),
            "hard-coded shipped-module inventories: %s\n"
            "Derive the set instead, so adding a module cannot break an "
            "unrelated test:\n"
            "  module_boundary_facts.stage_shipped_modules(repo, dest, roots)"
            % "; ".join(sorted(offenders)))


class CompleteModuleGraphProbes(unittest.TestCase):
    """The one graph sees Area, Domain, package, and wrapper boundaries."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, source):
        path = self.root / "Tools" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def test_full_graph_detects_a_cycle_inside_one_domain_package(self):
        self.write(
            "execution/task_runtime/runtime/left.py",
            "import Tools.execution.task_runtime.runtime.right as right\n")
        self.write(
            "execution/task_runtime/runtime/right.py",
            "import Tools.execution.task_runtime.runtime.left as left\n")

        facts = boundary_facts.collect(self.root)
        graph = boundary_facts.import_graph(facts)

        self.assertEqual(
            ["execution.task_runtime.runtime.right"],
            graph["execution.task_runtime.runtime.left"])
        self.assertEqual([[
            "execution.task_runtime.runtime.left",
            "execution.task_runtime.runtime.right",
        ]], boundary_facts.strongly_connected(graph))
        self.assertNotIn("execution", graph)

    def test_standard_wrapper_is_the_only_external_cli_node(self):
        self.write(
            "run_alpha.py",
            "from Tools.execution.audit.alpha import main as _main\n"
            "IMPLEMENTATION_MODULE = 'Tools.execution.audit.alpha'\n"
            "def main(argv=None):\n"
            "    return _main(argv)\n")
        self.write(
            "execution/audit/alpha.py",
            "import argparse\n"
            "def main(argv=None):\n"
            "    return argparse.ArgumentParser().parse_args(argv)\n")

        facts = boundary_facts.collect(self.root)
        graph = boundary_facts.import_graph(facts)

        self.assertEqual(["run_alpha"], boundary_facts.cli_modules(facts))
        self.assertEqual(
            "execution.audit.alpha",
            facts["run_alpha"]["implementation_module"])
        self.assertEqual(
            ["execution.audit.alpha"], graph["run_alpha"])
        self.assertFalse(facts["execution.audit.alpha"]["cli_entrypoint"])


class SuiteCollectsEachTestOnce(unittest.TestCase):
    """No test file may re-collect another file's tests.

    A test class that subclasses, or imports the name of, a TestCase defined
    elsewhere makes unittest discovery collect that whole suite a second time
    inside the borrowing file. Four files did this and it cost 299 duplicate
    executions per run for zero additional coverage -- one of them had even
    neutralised the duplicates with a skip loop whose own comment said "zero
    new coverage", which fixed the reporting and left the collection.

    Borrowing fixtures is fine and common here. What is not fine is letting
    the borrowed tests run again, so a file that inherits a foreign TestCase
    must exclude the inherited entries in `load_tests`.
    """

    def test_no_file_collects_another_files_tests(self):
        import unittest.loader

        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        loader = unittest.TestLoader()
        owners = {}
        duplicated = []
        for name in sorted(os.listdir(here)):
            if not name.startswith("test_") or not name.endswith(".py"):
                continue
            module = name[:-3]
            try:
                suite = loader.discover(here, pattern=name, top_level_dir=here)
            except Exception:  # a file that cannot load is another test's job
                continue
            seen = []

            def walk(node):
                if isinstance(node, unittest.TestSuite):
                    for child in node:
                        walk(child)
                elif isinstance(node, unittest.TestCase):
                    seen.append(node)

            walk(suite)
            for case in seen:
                defining = type(case).__module__
                key = "%s.%s" % (defining, case.id().split(".")[-1])
                if defining != module and defining.startswith("test_"):
                    duplicated.append("%s re-collects %s" % (module, key))
                owners.setdefault(key, set()).add(module)

        self.assertEqual(
            [], sorted(set(duplicated)),
            "test files collecting tests defined elsewhere:\n  %s\n"
            "Borrow the fixture, not the suite: exclude inherited entries in "
            "the borrowing file's `load_tests`."
            % "\n  ".join(sorted(set(duplicated))[:12]))


    def test_no_fixture_base_runs_its_own_tests_again(self):
        """A fixture base that declares tests runs them under every subclass.

        The check above keys on the defining module, so it is blind to this
        one: when the base and its subclasses share a file, the tests that
        run four times are defined exactly where they are collected, and
        nothing is borrowed across a file line.  Keying on the function
        object catches it.

        The sameness clause keeps a genuine parametrise-by-subclass base
        legal.  A base whose subclasses each build different state is asking
        for its assertions to run against each of them, and gets them; a base
        whose subclasses differ in nothing the test can observe is not
        parametrising anything, it is just running the same test again.
        """
        import unittest.loader

        here = os.path.dirname(os.path.abspath(__file__))
        for entry in (here, TOOLS, REPO):
            if entry not in sys.path:
                sys.path.insert(0, entry)

        def hook(cls, name):
            """The implementation a class would actually run for a hook."""
            found = getattr(cls, name, None)
            return getattr(found, "__func__", found)

        loader = unittest.TestLoader()
        suite = loader.discover(here, pattern="test_*.py", top_level_dir=here)
        cases = []

        def walk(node):
            if isinstance(node, unittest.TestSuite):
                for child in node:
                    walk(child)
            elif isinstance(node, unittest.TestCase):
                cases.append(node)

        walk(suite)

        bodies = {}
        for case in cases:
            cls = type(case)
            method = getattr(cls, case._testMethodName, None)
            code = getattr(method, "__code__", None)
            if code is None:  # a _FailedTest placeholder has no body to key on
                continue
            key = (code.co_filename, code.co_firstlineno)
            bodies.setdefault(key, {})[cls] = case.id()

        repeated = []
        for (path, line), owners in sorted(bodies.items()):
            if len(owners) < 2:
                continue
            hooks = {
                tuple(hook(cls, name)
                      for name in ("setUp", "setUpClass", "tearDown"))
                for cls in owners
            }
            if len(hooks) > 1:  # the subclasses really do build different state
                continue
            repeated.append(
                "%s:%d runs %d times, under %s"
                % (os.path.basename(path), line, len(owners),
                   ", ".join(sorted(cls.__name__ for cls in owners))))

        self.assertEqual(
            [], repeated,
            "one test body collected under several classes that build the "
            "same state:\n  %s\n"
            "Move the tests off the fixture base onto a leaf class that "
            "subclasses it.  A base that declares tests runs them again "
            "under every subclass, for no coverage a subclass can observe."
            % "\n  ".join(repeated[:12]))

    def test_every_test_file_is_actually_inspected(self):
        """A file that cannot import must fail loudly, not vanish quietly.

        Discovery does not raise on an unimportable file -- it substitutes a
        `_FailedTest` whose module is `unittest.loader`, which both checks
        above skip because it is not a `test_` module.  The file then
        contributes nothing and reads exactly like a file with no findings.
        """
        here = os.path.dirname(os.path.abspath(__file__))
        for entry in (here, TOOLS, REPO):
            if entry not in sys.path:
                sys.path.insert(0, entry)

        loader = unittest.TestLoader()
        suite = loader.discover(here, pattern="test_*.py", top_level_dir=here)
        failed = []

        def walk(node):
            if isinstance(node, unittest.TestSuite):
                for child in node:
                    walk(child)
            elif isinstance(node, unittest.TestCase):
                if type(node).__module__ == "unittest.loader":
                    failed.append(node.id())

        walk(suite)

        self.assertEqual(
            [], sorted(failed),
            "test files that discovery could not import:\n  %s\n"
            "These contribute no cases and no complaint, so every check in "
            "this file silently stops covering them."
            % "\n  ".join(sorted(failed)[:12]))

class DependencyDirection(unittest.TestCase):
    """No static import cycle, with no exception available.

    The contract grants exceptions for symbols because a symbol consumption
    can be a bounded, dated compromise.  A cycle cannot: it makes the
    direction question unanswerable for every symbol at once, which is the
    property the contract exists to keep decidable.
    """

    @classmethod
    def setUpClass(cls):
        cls.facts = boundary_facts.collect(REPO)
        cls.manifest = load_manifest()

    def test_import_graph_is_acyclic(self):
        graph = boundary_facts.import_graph(self.facts)
        cycles = boundary_facts.strongly_connected(graph)
        self.assertEqual(
            [], cycles,
            "static import cycles (no exception is available): %s" % cycles)

    def test_entrypoints_are_not_imported_as_production_libraries(self):
        """A true adapter may be invoked, but never imported as an owner.

        An imported command module is not actually a thin entry point: some
        callable, constant, or contract inside it is serving production code.
        Such a module must be classified by that defining responsibility until
        the adapter is physically split, so the hierarchy never labels a live
        library dependency as presentation-only.
        """
        layers = {
            row["module"]: row["layer"]
            for row in self.manifest.get("modules") or ()
        }
        violations = []
        for consumer, facts in sorted(self.facts.items()):
            for target in facts.get("imported_modules") or ():
                if target != consumer and layers.get(target) == "entrypoint":
                    violations.append("%s -> %s" % (consumer, target))
        self.assertEqual(
            [], violations,
            "production modules import modules classified as entrypoints; "
            "move the shared owner to contract/application or classify the "
            "hybrid module by its present defining responsibility: %s" %
            ", ".join(violations))

    def test_cli_discovery_is_exactly_the_top_level_adapter_surface(self):
        graph = boundary_facts.import_graph(self.facts)
        problems = []
        for module in boundary_facts.cli_modules(self.facts):
            row = self.facts[module]
            if "/" in row["path"]:
                problems.append("%s is not top-level" % module)
            implementation = row.get("implementation_module")
            if implementation and implementation not in graph.get(module, ()):
                problems.append(
                    "%s does not depend on %s" % (module, implementation))
        self.assertEqual([], problems)

    def test_top_level_cli_wrappers_define_only_main_and_entry_metadata(self):
        """A command adapter must never become a compatibility Python API."""
        problems = []
        allowed = {"IMPLEMENTATION_MODULE", "main"}
        for module in boundary_facts.cli_modules(self.facts):
            path = Path(TOOLS, self.facts[module]["path"])
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            defined = set()
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                    if not node.name.startswith("_"):
                        defined.add(node.name)
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(
                        node, ast.Assign) else (node.target,)
                    for target in targets:
                        if (isinstance(target, ast.Name) and
                                not target.id.startswith("_")):
                            defined.add(target.id)
            unexpected = sorted(defined - allowed)
            if unexpected:
                problems.append("%s: %s" % (
                    module, ", ".join(unexpected)))
        self.assertEqual(
            [], problems,
            "top-level CLI wrappers expose a Python compatibility surface: "
            "%s" % "; ".join(problems))

    def test_gate_runtime_does_not_depend_on_the_cli_facade(self):
        """The one direction the Tool boundary freezes by name.

        Pinned separately from the generic cycle rule: this edge is the
        defect the contract was written for, and a generic check would let it
        return as one half of a longer ring without naming it.
        """
        entry = self.facts.get("execution.evidence.metadata_gate_runtime")
        if entry is None:
            self.skipTest("metadata_gate_runtime is not shipped")
        self.assertNotIn(
            "check_queue", entry["imports"],
            "metadata_gate_runtime must not depend on check_queue")
        self.assertNotIn(
            "execution.task_runtime.check_queue", entry["imports"],
            "metadata_gate_runtime must not depend on the check_queue owner")

    def test_coverage_delta_uses_platform_not_queue_runtime_primitives(self):
        """Coverage planning must not point back into its Queue consumer."""
        entry = self.facts.get("execution.planning.coverage_delta")
        if entry is None:
            self.skipTest("coverage_delta is not shipped")
        self.assertIn("platform.common.primitives", entry["imports"])
        self.assertNotIn(
            "execution.task_runtime.queue_runtime.primitives",
            entry["imports"])


if __name__ == "__main__":
    unittest.main()
