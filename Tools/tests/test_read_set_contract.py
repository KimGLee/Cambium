"""Owned tests for Read Set declarations and their runtime load closure.

Generated navigation, Card schema, curated Card content, review currentness,
and Card budgets have separate owners. These tests use one declaration object
and one small directory; no Card tree or Kernel tree is copied.
"""

import contextlib
from pathlib import Path
import tempfile
import unittest

from Tools.execution.context_delivery import read_set_contract
from Tools.execution.task_runtime.queue_runtime import task_contract
from Tools.platform.common import kblib


REPOSITORY = Path(__file__).resolve().parents[2]
TARGET = "kernel/K00 Fixture.md"


def _declaration(route_id="R01", *, dependencies=None):
    return {
        "type": "read-set",
        "schema_version": 1,
        "route_id": route_id,
        "activation_phase": "batch-preflight",
        "narrowable": False,
        "load_edges": [{
            "edge_id": "%s:start" % route_id,
            "kind": "required",
            "phase_id": "batch-preflight",
            "trigger_id": "route-selected",
            "targets": [TARGET],
            "read_sets": list(dependencies or ()),
        }],
    }


def _document(declaration, *, prose_link="kernel/Prose Only.md"):
    return (
        "---\n%s---\n"
        "# Fixture Read Set\n\n"
        "## Purpose\n\n"
        "Fixture loading boundary.\n\n"
        "## Non-deterministic triggers\n\n"
        "[[%s]]\n"
    ) % (kblib.canonical_yaml(declaration), prose_link)


@contextlib.contextmanager
def _minimal_root():
    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace)
        schema = root / read_set_contract.SCHEMA_PATH
        schema.parent.mkdir(parents=True)
        schema.write_text(
            (REPOSITORY / read_set_contract.SCHEMA_PATH).read_text(
                encoding="utf-8"),
            encoding="utf-8",
        )
        target = root / TARGET
        target.parent.mkdir(parents=True)
        target.write_text("# Fixture\n", encoding="utf-8")
        read_set = root / "Read Set/R01 Fixture Read Set.md"
        read_set.write_text(_document(_declaration()), encoding="utf-8")
        yield root, read_set


class ReadSetDeclarationContractTests(unittest.TestCase):
    def test_frontmatter_is_the_closed_loading_owner_for_shipped_routes(self):
        schema = read_set_contract.load_schema(REPOSITORY)
        records = read_set_contract.discover(REPOSITORY, schema=schema)
        self.assertEqual(
            ["R%02d" % number for number in range(1, 14)],
            sorted(records),
        )

        record = records["R01"]
        before = read_set_contract.targets(record["declaration"])
        prose_changed = record["text"] + "\n[[kernel/Not A Target]]\n"
        parsed = read_set_contract.parse_declaration(
            prose_changed, record["path"], schema)
        self.assertEqual(before, read_set_contract.targets(parsed))

        mutations = {
            "body-shape": (
                record["text"].replace(
                    "## Non-deterministic triggers",
                    "## Loading Rules\n\nSecond authority.\n\n"
                    "## Non-deterministic triggers"),
                "body sections",
            ),
            "activation-edge": (
                record["text"].replace(
                    "activation_phase: batch-preflight",
                    "activation_phase: governance"),
                "has no required load edge",
            ),
        }
        for label, (text, expected) in mutations.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                        read_set_contract.ReadSetContractError, expected):
                    read_set_contract.parse_declaration(
                        text, record["path"], schema)

    def test_registry_ignores_generated_navigation_and_rejects_unknown_edges(self):
        with _minimal_root() as (root, read_set):
            index = root / "Read Set/Read Sets Index.md"
            index.write_text(
                "not YAML and not authoritative\n", encoding="utf-8")
            self.assertEqual({"R01"}, set(read_set_contract.discover(root)))

            read_set.write_text(
                _document(_declaration(dependencies=["R99"])),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                    read_set_contract.ReadSetContractError,
                    "unknown Read Set"):
                read_set_contract.discover(root)


class ReadSetLoadClosureIntegrationTests(unittest.TestCase):
    def test_top_level_and_profile_routes_consume_only_machine_load_edges(self):
        with _minimal_root() as (root, read_set):
            selected = [read_set.relative_to(root).as_posix()]
            before = task_contract.read_set_load_closure(root, selected)
            read_set.write_text(
                read_set.read_text(encoding="utf-8") +
                "\n[[kernel/Another Prose Link.md]]\n",
                encoding="utf-8",
            )
            after = task_contract.read_set_load_closure(root, selected)
            self.assertEqual(before, after)
            self.assertEqual({TARGET}, before[1])
            self.assertEqual([], before[3])

            profile = root / "profiles/test"
            profile.mkdir(parents=True)
            manifest = profile / "profile.md"
            manifest.write_text(
                "# Test Profile\n\n## Profile Identity\n\n"
                "- `profile_id`: `test`\n",
                encoding="utf-8",
            )
            supplemental = profile / "P Supplemental Read Set.md"
            declaration = _declaration("R01")
            declaration.update({
                "type": "profile-read-set",
                "route_id": "P:test:supplemental",
            })
            declaration["load_edges"][0]["edge_id"] = (
                "P:test:supplemental:start")
            supplemental.write_text(
                _document(declaration), encoding="utf-8")

            read_sets, modules, invalid, errors = (
                task_contract.read_set_load_closure(
                    root, [], "profiles/test/profile.md",
                    ["P:test:supplemental"]))
            self.assertEqual(
                {"profiles/test/P Supplemental Read Set.md"}, read_sets)
            self.assertEqual({TARGET}, modules)
            self.assertEqual(set(), invalid)
            self.assertEqual([], errors)

            supplemental.write_text(
                "---\ntype: profile-read-set\n"
                "route_id: P:test:supplemental\n---\n\n"
                "## Purpose\n\nFixture.\n\n"
                "## Non-deterministic triggers\n\n"
                "[[kernel/Prose Only.md]]\n",
                encoding="utf-8",
            )
            _read_sets, _modules, _invalid, errors = (
                task_contract.read_set_load_closure(
                    root, [], "profiles/test/profile.md",
                    ["P:test:supplemental"]))
            self.assertTrue(
                any("declaration fields differ" in error for error in errors),
                errors,
            )


if __name__ == "__main__":
    unittest.main()
