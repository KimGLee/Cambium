from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection
import Tools.knowledge.rendering.changed_scope_rendering_checks as checks
import Tools.knowledge.structure.markdown_structure_checks as markdown_structure_checks


class KernelIdentityTests(unittest.TestCase):
    def test_check_identities_are_derived_from_active_kernel_rows(self):
        registry = audit_obligation_projection.load_changed_scope_registry(
            REPOSITORY)
        rows = audit_obligation_projection.validate_changed_scope_registry(
            registry)["base_rules"]
        expected = {
            row["rule_id"]: row["producer_check"]
            for row in rows if row["rule_id"] in checks.CHECKS_BY_RULE_ID
        }
        self.assertEqual(dict(checks.CHECKS_BY_RULE_ID), expected)
        self.assertEqual(3, len(expected))


class FenceChecks(unittest.TestCase):
    def test_level0_fence_closure_uses_shared_parser(self):
        text = "# Page\n\n```python\nprint('x')\n"
        result = checks.level0_fence_closure(text, "Page.md")
        self.assertEqual("fail", result["result"])
        self.assertEqual("markdown-fence-unclosed",
                         result["diagnostics"][0]["diagnostic_id"])
        self.assertEqual(((), {"line": 3, "marker": "```",
                               "language": "python"}),
                         markdown_structure_checks.fence_scan(text))

    def test_mermaid_rule_is_separate_rendering_predicate(self):
        text = "# Page\n\n```mermaid\ngraph LR\n```"
        result = checks.level0_mermaid_fence_closure(text, "Page.md")
        self.assertEqual("pass", result["result"])
        self.assertEqual(checks.MERMAID_RULE_ID, result["rule_id"])
        self.assertEqual(1, result["metrics"][
            "closed_mermaid_fence_count"])

        broken = checks.level0_mermaid_fence_closure(
            "```mermaid\ngraph LR\n", "Page.md")
        self.assertEqual("fail", broken["result"])
        self.assertEqual("mermaid-fence-unclosed",
                         broken["diagnostics"][0]["diagnostic_id"])


class TableChecks(unittest.TestCase):
    def test_valid_table_and_escaped_alias_pass(self):
        text = (
            "| Name | Target |\n"
            "|---|---|\n"
            "| A | [[Path\\|Alias]] |\n")
        result = checks.level1_markdown_table_static(text, "Page.md")
        self.assertEqual("pass", result["result"], result["diagnostics"])
        self.assertEqual(1, result["metrics"]["table_count"])

    def test_unescaped_alias_and_column_drift_fail(self):
        text = (
            "| Name | Target |\n"
            "|---|---|\n"
            "| A | [[Path|Alias]] |\n")
        result = checks.level1_markdown_table_static(text, "Page.md")
        self.assertEqual("fail", result["result"])
        self.assertEqual(
            {"table-column-count-mismatch",
             "table-wiki-alias-pipe-unescaped"},
            {row["diagnostic_id"] for row in result["diagnostics"]})

    def test_long_cell_has_no_invented_threshold(self):
        text = "| Value |\n|---|\n| %s |\n" % ("x" * 10000)
        result = checks.level1_markdown_table_static(text, "Page.md")
        self.assertEqual("pass", result["result"])
        self.assertNotIn("long", repr(result).lower())


class ResultContractTests(unittest.TestCase):
    def test_result_identity_drift_fails(self):
        value = checks.level0_fence_closure("# Page\n", "Page.md")
        value["check_id"] = checks.TABLE_CHECK_ID
        with self.assertRaisesRegex(ValueError, "identity differs"):
            checks.validate_check_result(value)


class ProfileRenderingRoutingTests(unittest.TestCase):
    def test_plain_page_is_not_applicable(self):
        decision = checks.selector_owned_profile_rendering_contract_state(
            "# Plain\n\nBody text.\n",
            contract_is_bound_and_valid=False)
        self.assertEqual({"state": "not-applicable", "constructs": []},
                         decision)

    def test_construct_without_typed_contract_is_gap_not_pass(self):
        decision = checks.selector_owned_profile_rendering_contract_state(
            "# Table\n\n| A |\n|---|\n| x |\n",
            contract_is_bound_and_valid=False)
        self.assertEqual("contract-gap", decision["state"])
        self.assertEqual(
            ["outer-pipe-markdown-table"], decision["constructs"])

    def test_unowned_formula_and_asset_syntax_is_not_a_tool_selector(self):
        decision = checks.selector_owned_profile_rendering_contract_state(
            "$100\n![figure][asset]\n![[diagram.svg]]\n"
            "<img src=\"diagram.svg\">\n",
            contract_is_bound_and_valid=False)
        self.assertEqual("not-applicable", decision["state"])
        self.assertEqual([], decision["constructs"])

    def test_future_valid_binding_routes_to_capability_without_attesting(self):
        decision = checks.selector_owned_profile_rendering_contract_state(
            "```mermaid\ngraph LR\n```\n",
            contract_is_bound_and_valid=True)
        self.assertEqual("ready", decision["state"])
        self.assertEqual(["mermaid-fence"], decision["constructs"])
        self.assertNotIn("pass", decision)

    def test_gap_inventory_is_structured_and_never_counts_as_evidence(self):
        pages = (
            ("Plain.md", "# Plain\n"),
            ("Table.md", "| A |\n|---|\n| x |\n"),
        )
        gaps = checks.profile_rendering_contract_gap_targets(
            pages, contract_is_bound_and_valid=False)
        self.assertEqual(
            (("Table.md", ("outer-pipe-markdown-table",)),), gaps)
        with self.assertRaises(checks.ProfileRenderingContractGap) as raised:
            checks.require_profile_rendering_contract_state(
                pages, contract_is_bound_and_valid=False)
        self.assertEqual(({
            "target": "Table.md",
            "constructs": ["outer-pipe-markdown-table"],
        },), raised.exception.targets)
        self.assertIn("contract-gap/HOLD", str(raised.exception))

    def test_valid_binding_removes_gap_but_does_not_record_pass(self):
        pages = (("Diagram.md", "```mermaid\ngraph LR\n```\n"),)
        self.assertTrue(checks.require_profile_rendering_contract_state(
            pages, contract_is_bound_and_valid=True))

    def test_unknown_fields_fail(self):
        value = checks.level0_fence_closure("# Page\n", "Page.md")
        value["semantic_guess"] = True
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            checks.validate_check_result(value)


if __name__ == "__main__":
    unittest.main()
