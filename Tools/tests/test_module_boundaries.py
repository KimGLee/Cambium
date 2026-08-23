"""Enforce the tool module boundary contract owned by K00/18.

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

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import kblib  # noqa: E402
import module_boundary_facts as boundary_facts  # noqa: E402


MANIFEST = os.path.join(TOOLS, "module-boundaries.yaml")


def load_manifest():
    with open(MANIFEST, encoding="utf-8") as handle:
        return kblib.parse_yaml_subset(handle.read())


class ManifestShape(unittest.TestCase):
    """The declaration itself must be well formed before it can bind."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest()
        cls.facts = boundary_facts.collect(REPO)

    def test_schema_version_is_current(self):
        self.assertEqual(1, self.manifest.get("schema_version"))

    def test_every_entry_names_a_module_once(self):
        names = [row.get("module") for row in self.manifest["modules"]]
        self.assertEqual(sorted(names), sorted(set(names)),
                         "a module is declared more than once")
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
                         "shipped modules absent from the manifest: %s"
                         % ", ".join(missing))

    def test_every_entry_has_a_shipped_module(self):
        declared = {row["module"] for row in self.manifest["modules"]}
        stale = sorted(declared - set(self.facts))
        self.assertEqual([], stale,
                         "manifest entries with no shipped module: %s"
                         % ", ".join(stale))


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
        self.assertEqual([], sorted(undeclared),
                         "consumption outside the declared public surface")

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
        self.assertEqual([], sorted(drifted),
                         "excepted definitions changed; re-argue the entry")

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
                         "exceptions with no remaining consumer; retire them")


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

    def test_import_graph_is_acyclic(self):
        graph = boundary_facts.import_graph(self.facts)
        cycles = boundary_facts.strongly_connected(graph)
        self.assertEqual(
            [], cycles,
            "static import cycles (no exception is available): %s" % cycles)

    def test_gate_runtime_does_not_depend_on_the_cli_facade(self):
        """The one direction K00/18 freezes by name.

        Pinned separately from the generic cycle rule: this edge is the
        defect the contract was written for, and a generic check would let it
        return as one half of a longer ring without naming it.
        """
        entry = self.facts.get("metadata_gate_runtime")
        if entry is None:
            self.skipTest("metadata_gate_runtime is not shipped")
        self.assertNotIn(
            "check_queue", entry["imports"],
            "metadata_gate_runtime must not depend on check_queue")


if __name__ == "__main__":
    unittest.main()
