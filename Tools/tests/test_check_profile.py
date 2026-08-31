"""Primary owner tests for the current ``profile-load`` CLI consumer.

This suite owns only the checker's parser predicates, finding classification,
and one representative CLI transport over an already-current typed Profile.
``profile_contract`` owns the typed dependency graph and snapshot;
``profile_admission`` owns selection/currentness; the sole template and the
Profile-flow E2E own candidate creation and adoption.
"""

import ast
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

import Tools.governance.profile.check_profile as check_profile
import Tools.platform.common.kblib as kblib
from Tools.tests.support.profile_contract_fixture import (
    CurrentProfileContractFixture,
)
from Tools.tests.fixtures.contract.corpus_plan_objects import CONFIGURED_SLOT


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "Tools/check_profile.py"
EXECUTION_DEFAULTS = (
    REPOSITORY / "kernel/K00 Standards Control/execution-defaults-base.yaml")


class ExecutionDefaultContractTests(unittest.TestCase):
    """Checker-owned parser and value-domain implementations."""

    def test_registered_value_domains_resolve_to_one_checker_predicate(self):
        registry = kblib.load_yaml_file(EXECUTION_DEFAULTS)
        entries = registry["overridable"] + registry["constitutional"]
        items = [entry["item"] for entry in entries]
        self.assertEqual(len(items), len(set(items)))
        domains = {
            entry["value_domain"] for entry in entries
            if "value_domain" in entry
        }
        self.assertTrue(domains)
        self.assertEqual(set(), domains - set(check_profile.VALUE_DOMAINS))
        for entry in entries:
            self.assertTrue((REPOSITORY / entry["owner"]).is_file(), entry)

    def test_value_domain_predicates_are_one_table_driven_contract(self):
        cases = (
            ("positive-integer", ("1", "999"),
             ("0", "-1", "+1", "2.5", "many")),
            ("percent-share-under-100", ("20", "20%", "0", "99.9%"),
             ("100", "120%", "-5", "a lot")),
        )
        for domain, accepted, rejected in cases:
            predicate = check_profile.VALUE_DOMAINS[domain]
            with self.subTest(domain=domain, result="accepted"):
                self.assertTrue(all(
                    predicate(value) is None for value in accepted))
            with self.subTest(domain=domain, result="rejected"):
                self.assertTrue(all(
                    predicate(value) is not None for value in rejected))

    def test_override_table_parser_preserves_shape_and_empty_cells(self):
        text = (
            "## Execution Default Overrides\n\n"
            "| Override item ID from the registry | Non-default value |\n"
            "|---|---|\n"
            "| `concurrency_cap` | `8` |\n"
            "| | `9` |\n"
            "| `batch_size.S` | |\n")
        rows = check_profile.table_rows(check_profile.section_lines(
            text, check_profile.OVERRIDES_SECTION))
        self.assertEqual([
            ["Override item ID from the registry", "Non-default value"],
            ["`concurrency_cap`", "`8`"],
            ["", "`9`"],
            ["`batch_size.S`", ""],
        ], list(rows))


class ProfileParserUnitTests(unittest.TestCase):
    """Pure parser behavior owned by check_profile, without filesystem IO."""

    def test_binding_section_obeys_markdown_authority_boundaries(self):
        cases = (
            ("## Implemented Slots\n```text\n"
             "- `Hidden`: `hidden.md`\n```\n", {}),
            ("## Implemented Slots#\n"
             "- `Outside`: `outside.md`\n", {}),
            ("## Implemented Slots\n"
             "- `Visible`: `visible.md`\n"
             " # Outside\n- `Outside`: `outside.md`\n",
             {"Visible": "`visible.md`"}),
        )
        for text, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual((expected, []),
                                 check_profile.parse_bindings(text))

    def test_declarations_consume_only_supplied_snapshot_bytes(self):
        snapshot = kblib.RepositoryTreeSnapshot(
            "/repo", "profiles/sample", "sha256:" + "0" * 64, {
                "profiles/sample/slot.md": (
                    b"# Slot\n\n## Policy\n\n"
                    b"- Registration: Configured\n\n"
                    b"| ID | Value |\n|---|---|\n| x | y |\n"),
                "profiles/sample/opaque.bin": b"ignored",
                "profiles/other/outside.md": (
                    b"## Policy\n- Registration: Configured\n"),
            })
        declarations = list(check_profile.profile_declarations(snapshot))
        self.assertEqual(1, len(declarations))
        self.assertEqual(
            ("slot.md", "Policy", "Registration", "Configured"),
            declarations[0][:4])

    def test_sentinel_scan_reads_only_the_supplied_closure(self):
        snapshot = kblib.RepositoryTreeSnapshot(
            "/repo", "profiles/sample", "sha256:" + "0" * 64, {
                "profiles/sample/slot.bin": b"TODO(profile)\n",
                "profiles/sample/clean.md": b"# Clean\n",
                "profiles/other/outside.md": b"TODO(profile)\n",
            })
        self.assertEqual(
            ([("slot.bin", 1)], 2, 1),
            check_profile.scan_sentinel(snapshot, "TODO(profile)"))


class CorpusPlanningSlotContractTests(unittest.TestCase):
    """Profile load owns the slot envelope, not the bound corpus state."""

    def test_configured_bindings_are_validated_without_resolving_artifacts(self):
        findings = []

        def add(check, target, result, details):
            findings.append((check, target, result, details))

        # These paths deliberately identify corpus state that has not been
        # materialized.  The Profile producer validates the K02-owned slot
        # envelope only; check_corpus_plan owns resolution after Profile load.
        slot = CONFIGURED_SLOT.replace("planning/", "not-yet-created/")
        check_profile.validate_corpus_planning_slot(
            Path("/absent/profile/corpus-planning.yaml"),
            "profiles/test-profile/corpus-planning.yaml",
            add,
            text=slot,
        )

        self.assertEqual([], findings)


class FindingClassificationContractTests(unittest.TestCase):
    """The checker owns one closed classification for emitted findings."""

    TOOLS = REPOSITORY / "Tools"

    @staticmethod
    def _literal_add_codes(tree):
        codes = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = (func.attr if isinstance(func, ast.Attribute)
                    else func.id if isinstance(func, ast.Name) else None)
            first = node.args[0]
            if (name == "add" and isinstance(first, ast.Constant) and
                    isinstance(first.value, str)):
                codes.add(first.value)
        return codes

    def _profile_contract_codes(self):
        tree = ast.parse(
            (self.TOOLS / "governance/profile/profile_contract.py").read_text(
                encoding="utf-8"))
        codes = self._literal_add_codes(tree)
        table_templates, dependency_templates = set(), set()
        prefixes, kinds = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "check"
                    for target in node.targets):
                branches = ((node.value.body, node.value.orelse)
                            if isinstance(node.value, ast.IfExp)
                            else (node.value,))
                codes.update(
                    branch.value for branch in branches
                    if isinstance(branch, ast.Constant) and
                    isinstance(branch.value, str))
            if isinstance(node, ast.FunctionDef):
                target = (table_templates if node.name in
                          ("section", "table", "cells")
                          else dependency_templates if
                          node.name == "profile_dependency" else None)
                if target is not None:
                    target.update(
                        sub.value[3:] for sub in ast.walk(node)
                        if isinstance(sub, ast.Constant) and
                        isinstance(sub.value, str) and
                        sub.value.startswith("%s-"))
            if (isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Attribute) and node.args):
                if node.func.attr in ("section", "table", "cells"):
                    last = node.args[-1]
                    if isinstance(last, ast.Constant) and isinstance(
                            last.value, str):
                        prefixes.add(last.value)
                if node.func.attr == "profile_dependency":
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(
                            first.value, str):
                        kinds.add(first.value)
        self.assertTrue(table_templates and dependency_templates)
        self.assertTrue(prefixes and kinds)
        codes.update("%s-%s" % (prefix, template)
                     for prefix in prefixes for template in table_templates)
        codes.update("%s-%s" % (kind, template)
                     for kind in kinds for template in dependency_templates)
        return codes

    def _emittable_codes(self):
        checker_tree = ast.parse(
            (self.TOOLS / "governance/profile/check_profile.py").read_text(
                encoding="utf-8"))
        kblib_source = (
            self.TOOLS / "platform/common/kblib.py").read_text(
                encoding="utf-8")
        codes = self._literal_add_codes(checker_tree)
        codes.update(re.findall(
            r'"((?:profile-id|structure-registry|metadata-contract)'
            r'-[a-z][a-z-]*)"', kblib_source))
        codes.update(self._profile_contract_codes())
        codes.discard("profile-contract-sentinel")
        codes.discard(check_profile.GATE_CHECK)
        return codes

    def test_category_map_exactly_covers_the_emittable_closed_set(self):
        emittable = self._emittable_codes()
        classified = set(check_profile.FINDING_CATEGORIES)
        self.assertEqual(set(), emittable - classified)
        self.assertEqual(set(), classified - emittable)

    def test_categories_and_unknown_fallback_have_only_two_meanings(self):
        self.assertEqual(
            {check_profile.MECHANICAL,
             check_profile.SEMANTIC_UNRESOLVED},
            set(check_profile.FINDING_CATEGORIES.values()))
        self.assertEqual(
            check_profile.SEMANTIC_UNRESOLVED,
            check_profile.FINDING_CATEGORIES["unfilled-placeholder"])
        self.assertEqual(
            check_profile.MECHANICAL,
            check_profile.FINDING_CATEGORIES["slot-binding-unresolved"])
        self.assertEqual(
            check_profile.SEMANTIC_UNRESOLVED,
            check_profile.finding_category("unknown_field"))


class ProfileCliTransportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)
        self.fixture.install_profile_load_inputs()

    def test_json_cli_projects_one_categorized_failure_and_exit_code(self):
        CurrentProfileContractFixture.replace(
            self.fixture.manifest,
            "- `Priority Rubric`: `slots.md`\n", "")
        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPT),
             str(self.fixture.profile),
             "--root", str(self.fixture.root), "--json"],
            text=True, capture_output=True, check=False)
        report = json.loads(completed.stdout)
        self.assertEqual(1, completed.returncode, completed.stderr)
        self.assertEqual("check_profile", report["tool"])
        self.assertEqual("fail", report["result"])
        self.assertTrue(report["findings"])
        self.assertTrue(all(
            set(finding) == {"check", "target", "details", "category"}
            for finding in report["findings"]))


if __name__ == "__main__":
    unittest.main()
