from pathlib import Path
import copy
import os
import sys
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection
import Tools.knowledge.rendering.deterministic_rendering_contract as contract
import Tools.knowledge.rendering.static_render_runtime as static_runtime


class DeterministicRenderingContractTests(unittest.TestCase):
    def setUp(self):
        self.document = contract.load_contract(REPOSITORY)
        self.values = contract.validate_contract(self.document)
        self.registry = audit_obligation_projection.\
            load_changed_scope_registry(REPOSITORY)

    def test_admitted_predicates_are_exactly_projected_by_registry(self):
        self.assertTrue(contract.validate_registry_projection(
            self.registry, self.document, root=REPOSITORY))
        rows = {row["rule_id"]: row
                for row in self.registry["base_rules"]}
        for predicate in self.values["admitted_predicates"]:
            row = rows[predicate["predicate_id"]]
            self.assertEqual(predicate["dimension"], row["dimension"])
            self.assertEqual("pre-merge", row["due_stage"])
            self.assertEqual("batch-review", row["consumer_gate_id"])

    def test_contract_gaps_cannot_be_projected_as_runnable_passes(self):
        gap_ids = {row["gap_id"] for row in self.values["contract_gaps"]}
        active = {row["rule_id"] for row in self.registry["base_rules"]}
        self.assertTrue(gap_ids)
        self.assertEqual(set(), gap_ids & active)

        invalid = copy.deepcopy(self.registry)
        gap = self.values["contract_gaps"][0]
        invalid["base_rules"].append({
            "rule_id": gap["gap_id"],
            "applicability": "every-changed-markdown-page",
            "producer_capability":
                self.registry["base_rules"][0]["producer_capability"],
            "producer_check": "invented-gap-pass",
            "evidence_role": "emits",
            "evidence_kind": "audit-receipt",
            "dimension": gap["dimension"],
            "dimension_binding": "fixed",
            "consumer_gate_id": "batch-review",
            "due_stage": "pre-merge",
            "nonblocking": False,
        })
        with self.assertRaisesRegex(ValueError, "unresolved K12/02 gaps"):
            contract.validate_registry_projection(
                invalid, self.document, root=REPOSITORY)

    def test_unadmitted_k12_02_rule_cannot_bypass_the_gap_ids(self):
        invalid = copy.deepcopy(self.registry)
        row = copy.deepcopy(invalid["base_rules"][0])
        row.update({
            "rule_id": "k12-02-nearby-invented-pass",
            "producer_check": "nearby-invented-pass",
        })
        invalid["base_rules"].append(row)
        with self.assertRaisesRegex(ValueError, "unadmitted K12/02"):
            contract.validate_registry_projection(
                invalid, self.document, root=REPOSITORY)

    def test_contract_rejects_unregistered_dimension(self):
        invalid = copy.deepcopy(self.document)
        invalid["admitted_predicates"][0]["dimension"] = "layout-ish"
        with self.assertRaisesRegex(ValueError, "dimension is not registered"):
            contract.validate_contract(invalid)


class StaticRenderingRuntimeBoundaryTests(unittest.TestCase):
    def test_missing_host_binding_does_not_become_empty_applicability(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(static_runtime.StaticRenderRuntimeError,
                                        "CAMBIUM_RENDER_NODE"):
                static_runtime.select_constructs("$x$", root=REPOSITORY)

    def test_arbitrary_profile_renderer_flags_cannot_enter_runtime(self):
        report = static_runtime.render_page("$x$", target="A.md",
            bindings={"securityLevel": "loose"}, root=REPOSITORY)
        self.assertEqual("fail", report["result"])
        self.assertIn("registered acceptance IDs", " ".join(report["diagnostics"]))


@unittest.skipUnless(all(os.environ.get(name) for name in (
    "CAMBIUM_RENDER_NODE", "CAMBIUM_RENDER_BROWSER", "CAMBIUM_RENDER_NODE_MODULES")),
    "actual renderer tests require explicitly bound Host executables and pinned dependencies")
class StaticRenderingActualExecutionTests(unittest.TestCase):
    def bindings(self):
        return static_runtime._acceptances(REPOSITORY)

    def test_official_ast_distinguishes_math_from_code_frontmatter_and_escaped_dollars(self):
        source = ('---\nnote: "$not_math$"\n---\n'
                  '`$code$` and \\$literal and $x$.\n\n'
                  '```text\n$also_code$\n```\n\n'
                  '| A | B |\n|---|---|\n| a | [[Path\\|Alias]] |\n')
        self.assertEqual(("dollar-math", "outer-pipe-markdown-table"),
            static_runtime.select_constructs(source, root=REPOSITORY))
        inventory = static_runtime._select_inventory(source, root=REPOSITORY)
        self.assertEqual(2, len(inventory["instances"]))

    def test_actual_diagrams_math_table_and_unicode_offsets_preserve_coverage(self):
        source = ('# 中文 😀\n\n```mermaid\nflowchart LR\nA["Input"] --> B["Output"]\n```\n\n'
                  '```mermaid\nstateDiagram-v2\n[*] --> ACTIVE\nACTIVE --> [*]\n```\n\n'
                  '```mermaid\nsequenceDiagram\nA->>B: Work\nB-->>A: Result\n```\n\n'
                  '$x+1$\n\n$$\n\\frac{a}{b}\n$$\n\n'
                  '| Label | Value |\n|---|---|\n| 中文 | $x+2$ |\n')
        report = static_runtime.render_page(source, target="Actual.md",
            bindings=self.bindings(), root=REPOSITORY)
        self.assertEqual("pass", report["result"], report)
        self.assertEqual(7, len(report["constructs"]))
        self.assertEqual([], static_runtime.validate_render_result(
            report, source, self.bindings(), root=REPOSITORY))
        tampered = copy.deepcopy(report)
        tampered["artifacts"][0]["content"] += "tampered"
        self.assertIn("Rendering artifact digest differs",
            static_runtime.validate_render_result(tampered, source,
                self.bindings(), root=REPOSITORY))
        missing = copy.deepcopy(report)
        removed = missing["constructs"].pop(0)
        missing["artifacts"] = [artifact for artifact in missing["artifacts"]
                                if artifact["artifact_id"] not in removed["artifact_ids"]]
        missing["report_sha256"] = static_runtime._json_sha({key: value
            for key, value in missing.items() if key != "report_sha256"})
        self.assertIn("Rendering construct coverage differs",
            static_runtime.validate_render_result(missing, source,
                self.bindings(), root=REPOSITORY))

    def test_large_unicode_input_preserves_source_across_stdin_byte_chunks(self):
        source = '中文😀' * 20000 + '\n\n$x+1$\n'
        inventory = static_runtime._select_inventory(source, root=REPOSITORY)
        self.assertEqual(static_runtime._sha(source.encode('utf-8')),
                         inventory['source_sha256'])
        self.assertEqual(['dollar-math'], inventory['constructs'])
        self.assertEqual(1, len(inventory['instances']))

    def test_compile_errors_are_failures_not_red_source_artifacts(self):
        source = '```mermaid\nflowchart LR\nA --> [\n```\n\n$\\notARealKaTeXCommand{x}$\n'
        report = static_runtime.render_page(source, target="Broken.md",
            bindings=self.bindings(), root=REPOSITORY)
        self.assertEqual("fail", report["result"])
        self.assertEqual(["fail", "fail"], [row["result"] for row in report["constructs"]])
        self.assertEqual([], report["artifacts"])

    def test_gfm_row_normalization_does_not_hide_kernel_structure_failure(self):
        source = '| A | B |\n|---|---|\n| a | b | dropped |\n'
        report = static_runtime.render_page(source, target="Malformed.md",
            bindings=self.bindings(), root=REPOSITORY)
        self.assertEqual("fail", report["result"])
        self.assertIn("Kernel table structure failed", " ".join(report["diagnostics"]))

    def test_selector_cache_is_bound_to_input_and_runtime_identity(self):
        static_runtime._select_cached.cache_clear()
        with mock.patch.object(static_runtime, "_invoke", wraps=static_runtime._invoke) as invoke:
            static_runtime.select_constructs("$x$", root=REPOSITORY)
            static_runtime.select_constructs("$x$", root=REPOSITORY)
            self.assertEqual(1, invoke.call_count)
            with mock.patch.object(static_runtime, "_file_sha", return_value="sha256:" + "a" * 64):
                static_runtime.select_constructs("$x$", root=REPOSITORY)
            self.assertEqual(2, invoke.call_count)


if __name__ == "__main__":
    unittest.main()
