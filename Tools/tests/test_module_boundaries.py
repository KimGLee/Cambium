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

# Every refusal below names the command that answers it.  A contract whose
# failures a reader cannot act on becomes a contract people route around, and
# routine kernel work reaches these checks often enough -- a new governance
# capability is usually a new leaf and new tool code together -- that the cost
# of not saying so compounds.
REGENERATE = ("python3 Tools/tests/module_boundary_report.py --emit-manifest"
              " --output Tools/module-boundaries.yaml")


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
            "  python3 Tools/tests/module_boundary_report.py "
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


# The declared rank of every `queue_runtime` submodule, and the one rule that
# orders the package: an import may only run downward.  The ranks are not a
# preference about layering -- they are the acyclicity the contract already
# requires, written where a machine can read it, because `import_graph` keys
# every module by its first name segment and therefore sees a package as a
# single node.  A cycle entirely inside a package is invisible to the rule
# whose whole purpose is forbidding cycles; a deliberate one on a probe tree
# reported none.
#
# The package root sits above every submodule because `__init__.py` imports
# all of them to re-export the facade surface.  Nothing inside may import the
# root: that would be a submodule depending on the whole package.
QUEUE_RUNTIME_RANKS = {
    "queue_runtime.canon": 0,
    "queue_runtime.primitives": 0,
    "queue_runtime.repofs": 0,

    "queue_runtime.evidence_identity": 1,
    "queue_runtime.gate_registry": 1,
    "queue_runtime.locks": 1,
    "queue_runtime.policy_exceptions": 1,
    "queue_runtime.producer_era": 1,
    "queue_runtime.profile_view": 1,
    "queue_runtime.receipts": 1,
    "queue_runtime.task_contract": 1,
    "queue_runtime.work_spec": 1,

    "queue_runtime.amendments": 2,
    "queue_runtime.authority": 2,
    "queue_runtime.control_plane": 2,
    "queue_runtime.coverage": 2,
    "queue_runtime.item_history": 2,
    "queue_runtime.property_state": 2,
    "queue_runtime.review": 2,
    "queue_runtime.task_record": 2,

    "queue_runtime.adoption": 3,
    "queue_runtime.delta": 3,
    "queue_runtime.maintenance": 3,
    "queue_runtime.revalidation": 3,

    "queue_runtime.close_gate": 4,
    "queue_runtime.task_progress": 4,

    "queue_runtime.item_evidence": 5,
    "queue_runtime.resume": 5,

    "queue_runtime.runtime": 6,

    "queue_runtime": 7,
}


class IntraPackageDirection(unittest.TestCase):
    """A package must be ordered inside, where the module graph cannot look.

    Every finding here is about direction, never about size or membership for
    its own sake: an edge that runs upward, a submodule nobody ranked, or a
    rank naming a file that no longer ships.  The second and third matter
    because a rank table that has stopped describing the tree stops refusing
    anything, which is the same silence the contract was written against.
    """

    PACKAGE = "queue_runtime"

    @classmethod
    def setUpClass(cls):
        cls.facts = boundary_facts.collect(REPO)
        cls.edges = boundary_facts.package_layers(cls.facts, cls.PACKAGE)

    def test_the_rank_table_matches_the_shipped_package(self):
        if not self.edges:
            self.skipTest("queue_runtime is not shipped")
        shipped = set(self.edges)
        declared = set(QUEUE_RUNTIME_RANKS)
        unranked = sorted(shipped - declared)
        self.assertEqual(
            [], unranked,
            "submodules with no declared rank: %s\n"
            "Add each to QUEUE_RUNTIME_RANKS with the rank its imports allow. "
            "An unranked submodule sits outside the only rule that orders the "
            "package." % ", ".join(unranked))
        stale = sorted(declared - shipped)
        self.assertEqual(
            [], stale,
            "ranks naming modules that are not shipped: %s"
            % ", ".join(stale))

    def test_every_intra_package_import_runs_downward(self):
        if not self.edges:
            self.skipTest("queue_runtime is not shipped")
        upward = []
        for name, targets in sorted(self.edges.items()):
            source = QUEUE_RUNTIME_RANKS.get(name)
            if source is None:
                continue  # the rank-table test owns this failure
            for target in targets:
                rank = QUEUE_RUNTIME_RANKS.get(target)
                if rank is None or rank < source:
                    continue
                upward.append("%s (rank %s) -> %s (rank %s)"
                              % (name, source, target, rank))
        self.assertEqual(
            [], sorted(upward),
            "intra-package imports that do not run downward: %s\n"
            "Either the edge is wrong, or the two responsibilities are one "
            "and belong in the same file. Raising a rank to admit the edge is "
            "only honest when nothing below it still reaches back up."
            % "; ".join(sorted(upward)))


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
