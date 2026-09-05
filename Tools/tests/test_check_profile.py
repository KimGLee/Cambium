"""Owner tests for the formal Profile-load evaluator and JSON projection.

The model owns TOML/CUE parsing and dependency linking; admission owns runtime
selection. This suite verifies checker-owned semantic domains, diagnostic
classification, closure usage and formal evidence without subprocesses.
"""

import ast
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import re
import unittest

import Tools.governance.profile.check_profile as check_profile
import Tools.platform.common.kblib as kblib
from Tools.tests.support.profile_contract_fixture import CurrentProfileContractFixture
from Tools.tests.fixtures.contract.corpus_plan_objects import CONFIGURED_SLOT


REPOSITORY = Path(__file__).resolve().parents[2]
EXECUTION_DEFAULTS = (
    REPOSITORY / "kernel/K00 Standards Control/execution-defaults-base.yaml")


def evaluate(fixture):
    fixture.save()
    return check_profile.evaluate_profile_load(fixture.profile, root=fixture.root)


class ExecutionDefaultContractTests(unittest.TestCase):
    """The Kernel registry owns allowed override items and value domains."""

    def test_registered_value_domains_resolve_to_one_checker_predicate(self):
        registry = kblib.load_yaml_file(EXECUTION_DEFAULTS)
        entries = registry["overridable"] + registry["constitutional"]
        items = [entry["item"] for entry in entries]
        self.assertEqual(len(items), len(set(items)))
        domains = {entry["value_domain"] for entry in entries if "value_domain" in entry}
        self.assertTrue(domains)
        self.assertEqual(set(), domains - set(check_profile.VALUE_DOMAINS))
        for entry in entries:
            self.assertTrue((REPOSITORY / entry["owner"]).is_file(), entry)

    def test_value_domain_predicates_are_one_table_driven_contract(self):
        cases = (
            ("positive-integer", ("1", "999"), ("0", "-1", "+1", "2.5", "many")),
            ("percent-share-under-100", ("20", "20%", "0", "99.9%"),
             ("100", "120%", "-5", "a lot")),
        )
        for domain, accepted, rejected in cases:
            predicate = check_profile.VALUE_DOMAINS[domain]
            with self.subTest(domain=domain, result="accepted"):
                self.assertTrue(all(predicate(value) is None for value in accepted))
            with self.subTest(domain=domain, result="rejected"):
                self.assertTrue(all(predicate(value) is not None for value in rejected))

    def test_typed_override_values_keep_the_registry_boundary(self):
        fixture = CurrentProfileContractFixture(self)
        registry = kblib.load_yaml_file(EXECUTION_DEFAULTS)
        constitutional = registry["constitutional"][0]["item"]
        cases = (
            ({"concurrency_cap": 8}, None),
            ({"concurrency_cap": 0}, "override-value-domain"),
            ({"concurrency_cap": ""}, "override-choice-empty"),
            ({"concurrency_cap": "use-kernel-default"}, "override-redundant-default"),
            ({"unknown-override": 8}, "override-item-unknown"),
            ({constitutional: 8}, "override-constitutional-item"),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                fixture.document["execution_default_overrides"] = overrides
                evaluation = evaluate(fixture)
                if expected is None:
                    self.assertTrue(evaluation.authorized, evaluation.output)
                    self.assertEqual((("concurrency_cap", 8),),
                                     evaluation.execution_default_overrides)
                    self.assertIs(type(evaluation.execution_default_overrides[0][1]), int)
                else:
                    self.assertFalse(evaluation.authorized)
                    self.assertIn(expected, {row["check"] for row in evaluation.findings})


class ProfileClosureContractTests(unittest.TestCase):
    def test_unreferenced_support_text_is_not_an_answer_or_sentinel_authority(self):
        fixture = CurrentProfileContractFixture(self)
        scratch = fixture.profile / "unreferenced.md"
        scratch.write_text("# Scratch\n\nTODO(profile)\n", encoding="utf-8")
        evaluation = evaluate(fixture)
        self.assertTrue(evaluation.authorized, evaluation.output)
        self.assertNotIn(
            "profiles/test-profile/unreferenced.md",
            evaluation.contract.profile_snapshot_paths)
        fixture.slot("profile-scope")["goal"]["statement"] = "TODO(profile)"
        evaluation = evaluate(fixture)
        self.assertFalse(evaluation.authorized)
        self.assertIn("unfilled-placeholder",
                      {row["check"] for row in evaluation.findings})


class CorpusPlanningSlotContractTests(unittest.TestCase):
    def test_configured_bindings_are_validated_without_resolving_artifacts(self):
        fixture = CurrentProfileContractFixture(self)
        slot = deepcopy(CONFIGURED_SLOT)
        slot["artifact_bindings"] = {
            name: path.replace("planning/", "not-yet-created/")
            for name, path in slot["artifact_bindings"].items()}
        fixture.document["slots"]["corpus-planning"] = slot
        self.assertFalse((fixture.root / "not-yet-created").exists())
        evaluation = evaluate(fixture)
        self.assertTrue(evaluation.authorized, evaluation.output)
        self.assertFalse((fixture.root / "not-yet-created").exists())


class FindingClassificationContractTests(unittest.TestCase):
    """Classification must cover current emitted codes, not retired parsers."""

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
            emitter = (isinstance(func, ast.Name) or (
                isinstance(func, ast.Attribute) and
                isinstance(func.value, ast.Name) and
                func.value.id in ("builder", "self")))
            if (name == "add" and emitter and isinstance(first, ast.Constant)
                    and isinstance(first.value, str)):
                codes.add(first.value)
        return codes

    def _profile_contract_codes(self):
        tree = ast.parse((self.TOOLS / "governance/profile/profile_contract.py").read_text(
            encoding="utf-8"))
        codes = self._literal_add_codes(tree)
        suffixes, kinds = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "check"
                    for target in node.targets):
                branches = ((node.value.body, node.value.orelse)
                            if isinstance(node.value, ast.IfExp) else (node.value,))
                codes.update(branch.value for branch in branches
                             if isinstance(branch, ast.Constant) and isinstance(branch.value, str))
            if isinstance(node, ast.FunctionDef) and node.name == "_dependency":
                suffixes.update(
                    sub.right.value for sub in ast.walk(node)
                    if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Add)
                    and isinstance(sub.left, ast.Name) and sub.left.id == "kind"
                    and isinstance(sub.right, ast.Constant)
                    and isinstance(sub.right.value, str)
                    and sub.right.value.startswith("-"))
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("profile_dependency", "repository_dependency")
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                kinds.add(node.args[0].value)
        self.assertTrue(suffixes and kinds)
        codes.update(kind + suffix for kind in kinds for suffix in suffixes)
        return codes

    def _emittable_codes(self):
        checker = ast.parse((self.TOOLS / "governance/profile/check_profile.py").read_text(
            encoding="utf-8"))
        kblib_source = (self.TOOLS / "platform/common/kblib.py").read_text(encoding="utf-8")
        codes = self._literal_add_codes(checker)
        for node in ast.walk(checker):
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.IfExp)
                    and any(isinstance(target, ast.Name) and target.id == "check"
                            for target in node.targets)):
                codes.update(branch.value for branch in (node.value.body, node.value.orelse)
                             if isinstance(branch, ast.Constant) and isinstance(branch.value, str))
        codes.update(re.findall(
            r'"((?:structure-registry|metadata-contract)-[a-z][a-z-]*)"', kblib_source))
        codes.update(self._profile_contract_codes())
        codes.discard("profile-contract-sentinel")
        codes.discard(check_profile.GATE_CHECK)
        return codes

    def test_category_map_exactly_covers_the_emittable_closed_set(self):
        self.assertEqual(self._emittable_codes(), set(check_profile.FINDING_CATEGORIES))

    def test_categories_and_unknown_fallback_have_only_two_meanings(self):
        self.assertEqual(
            {check_profile.MECHANICAL, check_profile.SEMANTIC_UNRESOLVED},
            set(check_profile.FINDING_CATEGORIES.values()))
        self.assertEqual(check_profile.SEMANTIC_UNRESOLVED,
                         check_profile.finding_category("unfilled-placeholder"))
        self.assertEqual(check_profile.MECHANICAL,
                         check_profile.finding_category("profile-contract-schema"))
        self.assertEqual(check_profile.SEMANTIC_UNRESOLVED,
                         check_profile.finding_category("unknown_field"))


class ProfileReportContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)

    def report(self):
        self.fixture.save()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = check_profile.main([
                str(self.fixture.profile), "--root", str(self.fixture.root), "--json"])
        return code, json.loads(buffer.getvalue())

    def test_json_projects_one_categorized_failure_and_exit_code(self):
        del self.fixture.document["slots"]["priority-rubric"]
        code, report = self.report()
        self.assertEqual(1, code)
        self.assertEqual("check_profile", report["tool"])
        self.assertEqual("fail", report["result"])
        self.assertTrue(report["findings"])
        self.assertTrue(all(
            set(finding) == {"check", "target", "details", "category"}
            for finding in report["findings"]))
        self.assertNotEqual("pass", report.get("profile_load", {}).get("result"))

    def test_profile_load_reports_typed_shape_drift_as_mechanical(self):
        self.fixture.slot("profile-scope")["goal"]["statement"] = 42
        code, report = self.report()
        self.assertEqual(1, code)
        schema_findings = [
            row for row in report["findings"] if row["check"] == "profile-contract-schema"]
        self.assertTrue(schema_findings, report)
        self.assertTrue(all(row["category"] == check_profile.MECHANICAL
                            for row in schema_findings))


if __name__ == "__main__":
    unittest.main()
