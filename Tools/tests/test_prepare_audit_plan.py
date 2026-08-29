"""Registry-oracle tests for the complete AuditPlan exporter."""

from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import copy
import sys
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
K12 = REPOSITORY / "kernel/K12 Quality Assurance"
sys.path.insert(0, str(TOOLS))

import audit_obligation_projection
import audit_producer_runtime
import batch_review_obligation_contract
import kblib
import prepare_audit_plan


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64
SHA_E = "sha256:" + "e" * 64
GENERATED = "2026-08-28T00:00:00Z"


def raw(name):
    return kblib.parse_yaml_subset((K12 / name).read_text(encoding="utf-8"))


class AuditPlanExporterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.batch_registry = raw("batch-review-obligation-registry.yaml")
        cls.changed_registry = raw("changed-scope-check-registry.yaml")
        cls.close_registry = raw("batch-close-closed-list.yaml")
        cls.substantive_contract = raw("substantive-review-contract.yaml")

    def frozen(self, path, marker="a", text="# Page\n"):
        digest = "sha256:" + marker * 64
        return audit_producer_runtime.FrozenPage(
            path=path,
            page_sha256=digest,
            semantic_content_fingerprint=digest,
            snapshot=SimpleNamespace(read_text=lambda: text),
        )

    def judgment(self, item_id, dimension="content_and_depth",
                 evidence_role="emits"):
        return SimpleNamespace(
            judgment_item_id=item_id,
            dimension_id=dimension,
            evidence_role=evidence_role,
            predicate_owner=None,
        )

    def contract(self, *, extra_scan=False, review_requirement=False):
        residual = SimpleNamespace(
            scan_id="fixture-residual",
            required_for_k12_item_6=True,
            judgment_item_id="fixture-residual-judgment",
            candidate_predicate="fixture residual predicate",
        )
        scans = [residual]
        judgments = [self.judgment(
            "fixture-residual-judgment", "coverage_and_integration")]
        if extra_scan:
            scans.append(SimpleNamespace(
                scan_id="fixture-extra-scan",
                required_for_k12_item_6=False,
                judgment_item_id="fixture-extra-judgment",
                candidate_predicate="fixture extra candidate boundary",
            ))
            judgments.append(self.judgment(
                "fixture-extra-judgment", "source_and_currentness",
                "triggers"))
        requirements = []
        if review_requirement:
            judgments.append(self.judgment(
                "fixture-page-judgment", "content_and_depth", "emits"))
            requirements.append(SimpleNamespace(
                judgment_item_id="fixture-page-judgment",
                target_selector="each-manifest-page",
                trigger="before-merge-ready",
                producer_kind="manual-attestation",
                receipt_schema="page-batch-judgment-v1",
                pass_authority_role_id="executor",
            ))
        return SimpleNamespace(
            authorized=True,
            manifest_repo_path="profiles/fixture/profile.md",
            profile_contract_fingerprint=SHA_C,
            scan_registry_path="profiles/fixture/registered-scans.md",
            routing_registry_path="profiles/fixture/routing-and-gates.md",
            extension_dimensions=(),
            judgment_items=tuple(judgments),
            registered_scans=tuple(scans),
            required_scan=residual,
            batch_review_requirements=tuple(requirements),
        )

    def inputs(self, tiers, contract=None):
        contract = contract or self.contract()
        paths = sorted(tiers)
        frozen = tuple(self.frozen(path) for path in paths)
        result = {
            "coverage": {"pages": [
                {"path": path, "tier": tiers[path],
                 "authoring_status": "drafted"}
                for path in paths
            ]},
            "_profile_authorized_view": {"_contract": contract},
        }
        item = {"id": "B001", "manifest": paths, "state": "open"}
        state = {
            "task_id": "task-fixture",
            "queue_revision": 4,
            "queue_state_revision": 8,
            "required_queue_sha256": SHA_A,
            "coverage_ledger_sha256": SHA_B,
            "progress_ledger_sha256": SHA_D,
        }
        profile = {
            "selected_profile_manifest": "profiles/fixture/profile.md",
            "profile_snapshot_sha256": SHA_B,
            "profile_contract_fingerprint": SHA_C,
        }
        standards = {
            "standards_version": "fixture-standards",
            "active_standards_sha256": SHA_D,
        }
        opening = {
            "opening_transition_receipt": "opening-fixture",
            "manifest_semantic_before_set_sha256": SHA_E,
        }
        return result, item, frozen, state, profile, standards, opening

    def build_values(self, values):
        result, item, frozen, state, profile, standards, opening = values
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                audit_producer_runtime, "freeze_manifest_pages",
                return_value=frozen))
            stack.enter_context(mock.patch.object(
                audit_producer_runtime, "runtime_state_bindings",
                return_value=state))
            stack.enter_context(mock.patch.object(
                audit_producer_runtime, "profile_bindings",
                return_value=profile))
            stack.enter_context(mock.patch.object(
                audit_producer_runtime, "standards_bindings",
                return_value=standards))
            stack.enter_context(mock.patch.object(
                prepare_audit_plan, "check_queue_opening_context",
                return_value=opening))
            plan, actual_frozen = prepare_audit_plan.build_plan(
                str(REPOSITORY), result, item, {}, generated_at=GENERATED)
        return plan, actual_frozen

    def build(self, tiers, contract=None):
        values = self.inputs(tiers, contract)
        plan, actual_frozen = self.build_values(values)
        return plan, actual_frozen, values

    @staticmethod
    def property_record(value, marker="9"):
        return {
            "value": value,
            "evidence_receipt": "event-%s" % marker,
            "content_fingerprint": "sha256:" + marker * 64,
        }

    @staticmethod
    def policy_page(path):
        return """---
domain: general
type: concept
volatility:
---
# %s
""" % path

    def changed_scope_oracle(self, manifest):
        """Interpret only the selectors admitted by the Kernel registry."""
        targets_by_applicability = {
            "every-batch-close": ("Progress.guidance_queue",),
            "changed-scope-includes-coverage-or-required-routing-state":
                tuple(sorted(manifest)),
            "changed-scope-includes-page-contract-applicable-markdown":
                tuple(sorted(manifest)),
            # This fixture's frozen Markdown starts directly with an H1.
            "changed-scope-includes-frontmatter": (),
            "batch-contract-freezes-machine-checkable-component-references":
                ("B001",),
            "every-changed-markdown-page": tuple(sorted(manifest)),
            # This fixture carries no Mermaid fence or Markdown table.
            "changed-scope-includes-mermaid-fence": (),
            "changed-scope-includes-markdown-table": (),
            "every-batch": ("B001",),
        }
        unknown = sorted({
            row["applicability"]
            for row in self.changed_registry["base_rules"]
            if row["applicability"] not in targets_by_applicability
        })
        self.assertEqual([], unknown)
        return {
            (target, row["rule_id"])
            for row in self.changed_registry["base_rules"]
            for target in targets_by_applicability[row["applicability"]]
        }

    def test_complete_base_plan_is_registry_derived(self):
        tiers = {"L.md": "L", "M.md": "M"}
        tiers.update({"S%02d.md" % index: "S" for index in range(11)})
        plan, _, _ = self.build(tiers)
        rows = plan["obligations"]

        m_rules = {row["rule_id"]
                   for row in self.batch_registry["m_tier_atomic_items"]}
        m_rows = [row for row in rows if row["target"] == "M.md" and
                  row["owner_rule_id"] in m_rules]
        self.assertEqual(m_rules, {row["owner_rule_id"] for row in m_rows})
        substantive = self.substantive_contract[
            "obligation_projection"]["owner_rule_id"]
        self.assertFalse(any(
            row["target"] == "M.md" and
            row["owner_rule_id"] == substantive for row in rows))
        self.assertEqual(1, sum(
            row["target"] == "L.md" and
            row["owner_rule_id"] == substantive for row in rows))

        count = self.batch_registry["s_tier_sampling"]["sample_count"]
        population = [path for path, tier in tiers.items() if tier == "S"]
        expected_s = max(
            count["minimum_count"],
            (len(population) * count["percentage_numerator"] +
             count["percentage_denominator"] - 1) //
            count["percentage_denominator"],
        )
        s_rule = self.batch_registry["s_tier_sampling"]["rule_id"]
        s_rows = [row for row in rows if row["owner_rule_id"] == s_rule]
        self.assertEqual(expected_s, len(s_rows))
        self.assertEqual("ceiling", count["rounding"])

        changed_rules = {row["rule_id"]
                         for row in self.changed_registry["base_rules"]}
        expected_changed = self.changed_scope_oracle(tiers)
        actual_changed = {
            (row["target"], row["owner_rule_id"])
            for row in rows if row["owner_rule_id"] in changed_rules
        }
        self.assertEqual(expected_changed, actual_changed)

        close_rules = [row["rule_id"]
                       for row in self.close_registry["members"]]
        close_rows = [row for row in rows
                      if row["owner_rule_id"] in set(close_rules)]
        self.assertEqual(close_rules, [
            source["rule_id"] for source in self.close_registry["members"]
            if source["rule_id"] in {
                row["owner_rule_id"] for row in close_rows}])
        self.assertEqual(len(close_rules), len(close_rows))
        self.assertEqual({_BATCH_SCOPE_TARGET}, {
            row["target"] for row in close_rows})
        by_rule = {row["owner_rule_id"]: row for row in close_rows}
        item6 = self.close_registry["members"][5]
        item8 = self.close_registry["members"][7]
        self.assertEqual(
            "coverage_and_integration",
            by_rule[item6["rule_id"]]["dimension"])
        self.assertIsNone(by_rule[item8["rule_id"]]["dimension"])
        self.assertEqual(
            "page-contract", by_rule[item8["rule_id"]]["producer_gate_id"])

        expected_total = (
            1 + len(m_rules) + expected_s + len(expected_changed) +
            len(close_rules))
        self.assertEqual(expected_total, len(rows))
        self.assertNotIn("card_bundle_sha256", plan)
        for row in rows:
            self.assertFalse({
                "artifact_fingerprint", "dependency_fingerprint",
                "contract_fingerprint"}.intersection(row))
        self.assertEqual(
            sorted(row["obligation_id"] for row in rows),
            [row["obligation_id"] for row in rows])

    def test_l_obligations_follow_only_the_three_existing_triggers(self):
        tiers = {
            "Fresh.md": "L",
            "New.md": "L",
            "Overdue.md": "L",
            "Rereview.md": "L",
        }
        values = self.inputs(tiers)
        result, _item, _frozen, _state, _profile, _standards, _opening = \
            values
        by_path = {row["path"]: row
                   for row in result["coverage"]["pages"]}
        by_path["Fresh.md"].update({
            "authoring_status": "reviewed",
            "property_state": {
                "last_reviewed": self.property_record("2026-01-01", "1"),
            },
        })
        by_path["New.md"]["property_state"] = {}
        by_path["Overdue.md"].update({
            "authoring_status": "reviewed",
            "property_state": {
                "last_reviewed": self.property_record("2025-08-28", "2"),
            },
        })
        by_path["Rereview.md"].update({
            "authoring_status": "drafted",
            "property_state": {
                "last_reviewed": self.property_record(None, "3"),
                "last_content_modified":
                    self.property_record("2026-08-20", "4"),
            },
        })
        values = (
            result, values[1],
            tuple(self.frozen(
                path, text=self.policy_page(path)) for path in sorted(tiers)),
            *values[3:],
        )
        with mock.patch.object(
                prepare_audit_plan, "_profile_volatility_defaults",
                return_value={"general": "slow"}):
            plan, _ = self.build_values(values)

        rule_id = self.substantive_contract[
            "obligation_projection"]["owner_rule_id"]
        actual = {
            row["target"]: row["partition"]
            for row in plan["obligations"]
            if row["owner_rule_id"] == rule_id
        }
        self.assertEqual({
            "New.md": "initial-semantic-review",
            "Overdue.md": "overdue-targeted-review",
            "Rereview.md": "invalidated-semantic-review",
        }, actual)
        self.assertNotIn("Fresh.md", actual)

    def test_new_m_page_uses_initial_partition_not_page_frontmatter(self):
        values = self.inputs({"M.md": "M"})
        legacy_frontmatter = """---
last_reviewed: 2025-01-01
---
# M
"""
        values = (
            values[0], values[1],
            (self.frozen("M.md", text=legacy_frontmatter),),
            *values[3:],
        )
        plan, _ = self.build_values(values)

        m_rules = {row["rule_id"]
                   for row in self.batch_registry["m_tier_atomic_items"]}
        matches = [row for row in plan["obligations"]
                   if row["target"] == "M.md" and
                   row["owner_rule_id"] in m_rules]
        self.assertEqual(len(m_rules), len(matches))
        self.assertEqual(
            {"initial-semantic-review"},
            {row["partition"] for row in matches})

    def test_current_m_review_is_targeted_again_not_initial(self):
        values = self.inputs({"M.md": "M"})
        values[0]["coverage"]["pages"][0].update({
            "authoring_status": "reviewed",
            "property_state": {
                "last_reviewed": self.property_record(
                    "2026-01-01", "a"),
            },
        })
        plan, _ = self.build_values(values)

        m_rules = {row["rule_id"]
                   for row in self.batch_registry["m_tier_atomic_items"]}
        matches = [row for row in plan["obligations"]
                   if row["target"] == "M.md" and
                   row["owner_rule_id"] in m_rules]
        self.assertEqual(len(m_rules), len(matches))
        self.assertEqual(
            {"invalidated-semantic-review"},
            {row["partition"] for row in matches})

    def test_invalidated_m_review_is_not_reclassified_as_initial(self):
        values = self.inputs({"M.md": "M"})
        values[0]["coverage"]["pages"][0].update({
            "authoring_status": "drafted",
            "property_state": {
                "last_reviewed": self.property_record(None, "a"),
                "last_content_modified": self.property_record(
                    "2026-08-20", "a"),
            },
        })
        plan, _ = self.build_values(values)

        m_rules = {row["rule_id"]
                   for row in self.batch_registry["m_tier_atomic_items"]}
        matches = [row for row in plan["obligations"]
                   if row["target"] == "M.md" and
                   row["owner_rule_id"] in m_rules]
        self.assertEqual(len(m_rules), len(matches))
        self.assertEqual(
            {"invalidated-semantic-review"},
            {row["partition"] for row in matches})

    def test_governed_rereview_gap_overrides_unexpired_review(self):
        values = self.inputs({"L.md": "L"})
        result = values[0]
        row = result["coverage"]["pages"][0]
        row.update({
            "authoring_status": "reviewed",
            "property_state": {
                "last_reviewed": self.property_record("2026-01-01"),
            },
        })
        result["coverage"]["open_gaps"] = [{
            "page": "L.md",
            "type": "rereview",
            "note": "accepted semantic evidence was invalidated",
        }]
        values = (
            result, values[1],
            (self.frozen("L.md", text=self.policy_page("L.md")),),
            *values[3:],
        )
        plan, _ = self.build_values(values)
        rule_id = self.substantive_contract[
            "obligation_projection"]["owner_rule_id"]
        matches = [row for row in plan["obligations"]
                   if row["owner_rule_id"] == rule_id]
        self.assertEqual(1, len(matches))
        self.assertEqual("invalidated-semantic-review",
                         matches[0]["partition"])

    def test_illegal_needs_rereview_authoring_status_holds(self):
        values = self.inputs({"L.md": "L"})
        values[0]["coverage"]["pages"][0][
            "authoring_status"] = "needs_rereview"
        with self.assertRaisesRegex(
                ValueError, "trigger HOLD.*authoring_status"):
            self.build_values(values)

    def test_existing_l_with_unresolved_policy_holds_instead_of_reopening(self):
        values = self.inputs({"L.md": "L"})
        result = values[0]
        result["coverage"]["pages"][0].update({
            "authoring_status": "reviewed",
            "property_state": {
                "last_reviewed": self.property_record("2026-01-01"),
            },
        })
        unresolved_page = """---
domain: unmapped
type: concept
---
# L
"""
        values = (
            result, values[1],
            (self.frozen("L.md", text=unresolved_page),),
            *values[3:],
        )
        with mock.patch.object(
                prepare_audit_plan, "_profile_volatility_defaults",
                return_value={"general": "slow"}):
            with self.assertRaisesRegex(
                    ValueError, "trigger HOLD.*unresolved_volatility"):
                self.build_values(values)

    def test_profile_volatility_defaults_come_from_authorized_snapshot(self):
        path = "profiles/fixture/vocabulary-extensions.yaml"
        snapshot = SimpleNamespace(read_text=lambda selected: (
            "schema_version: 1\nvolatility_defaults:\n"
            "  general: slow\n" if selected == path else None))
        result = {"_profile_authorized_view": {
            "_manifest_slot_paths": (
                ("Vocabulary Extensions", path),
            ),
            "_profile_snapshot": snapshot,
        }}
        self.assertEqual(
            {"general": "slow"},
            prepare_audit_plan._profile_volatility_defaults(result))

    def test_s_selection_and_plan_ids_are_deterministic(self):
        tiers = {"L.md": "L", "M.md": "M"}
        tiers.update({"S%02d.md" % index: "S" for index in range(11)})
        first, _, _ = self.build(tiers)
        second, _, _ = self.build(tiers)
        self.assertEqual(first, second)

        s_rule = self.batch_registry["s_tier_sampling"]["rule_id"]
        actual = sorted(row["target"] for row in first["obligations"]
                        if row["owner_rule_id"] == s_rule)
        population = sorted(path for path, tier in tiers.items()
                            if tier == "S")
        expected = batch_review_obligation_contract.select_s_targets(
            population, task_id=first["task_id"],
            batch_id=first["batch_id"],
            opening_transition_receipt=first[
                "opening_transition_receipt"],
            registry=self.batch_registry)["sample_selected_targets"]
        self.assertEqual(expected, actual)

    def test_authorized_profile_extensions_stay_separate(self):
        contract = self.contract(extra_scan=True, review_requirement=True)
        tiers = {"L.md": "L", "M.md": "M", "S.md": "S"}
        plan, _, _ = self.build(tiers, contract)
        extension_rows = [row for row in plan["obligations"]
                          if row["owner_kind"] == "profile-extension"]

        scan = [row for row in extension_rows
                if row["owner_rule_id"] == "fixture-extra-scan"]
        self.assertEqual(1, len(scan))
        self.assertEqual(_BATCH_SCOPE_TARGET, scan[0]["target"])
        self.assertEqual(
            "k12-05-registered-scan", scan[0]["kernel_extension_point"])
        review = [row for row in extension_rows
                  if row["owner_rule_id"] == "fixture-page-judgment"]
        self.assertEqual(set(tiers), {row["target"] for row in review})
        self.assertTrue(all(
            row["partition"] == "profile-registered-review" and
            row["evidence_kind"] == "page-batch-judgment-v1" and
            row["producer_check"] == "profile_batch_judgment" and
            row["consumer_gate_id"] == "batch-review"
            for row in review))
        base = audit_obligation_projection.base_obligation_specs(
            str(REPOSITORY))
        self.assertTrue(all(row["owner_kind"] == "kernel" for row in base))

    def test_missing_profile_rendering_contract_holds_only_triggered_pages(self):
        plain = self.frozen("Plain.md")
        table = audit_producer_runtime.FrozenPage(
            path="Table.md", page_sha256=SHA_A,
            semantic_content_fingerprint=SHA_B,
            snapshot=SimpleNamespace(read_text=lambda: (
                "# Table\n\n| A |\n|---|\n| x |\n")),
        )
        self.assertEqual(
            (), prepare_audit_plan._profile_rendering_contract_gap_targets(
                (plain,)))
        self.assertEqual(
            (("Table.md", ("outer-pipe-markdown-table",)),),
            prepare_audit_plan._profile_rendering_contract_gap_targets(
                (plain, table)))

    def test_profile_rendering_gap_is_typed_and_carries_exact_targets(self):
        tiers = {"AMermaid.md": "M", "ZTable.md": "M"}
        result, item, _frozen, state, profile, standards, opening = \
            self.inputs(tiers)
        frozen = (
            self.frozen(
                "AMermaid.md", text=(
                    "# Mermaid\n\n```mermaid\ngraph LR\n```\n")),
            self.frozen(
                "ZTable.md", text=(
                    "# Table\n\n| A |\n|---|\n| x |\n")),
        )

        with self.assertRaises(
                prepare_audit_plan.ProfileRenderingContractGap) as caught:
            self.build_values((
                result, item, frozen, state, profile, standards, opening))

        self.assertEqual((
            {"target": "AMermaid.md", "constructs": ["mermaid-fence"]},
            {"target": "ZTable.md",
             "constructs": ["outer-pipe-markdown-table"]},
        ), caught.exception.targets)

    def test_main_exposes_contract_gap_as_hold_before_path_or_write(self):
        gap = prepare_audit_plan.ProfileRenderingContractGap((
            ("ZTable.md", ("outer-pipe-markdown-table",)),
            ("AMermaid.md", ("mermaid-fence",)),
        ))
        output = io.StringIO()

        with mock.patch.object(
                audit_producer_runtime, "admitted_runtime",
                return_value=("/fixture", {}, object())), mock.patch.object(
                    audit_producer_runtime, "open_batch",
                    return_value=({"id": "B001"}, {})), mock.patch.object(
                        prepare_audit_plan, "build_plan",
                        side_effect=gap), mock.patch.object(
                            audit_producer_runtime, "managed_plan_path") as \
                            managed_path, mock.patch.object(
                                kblib, "atomic_write_text") as write, \
                redirect_stdout(output):
            code = prepare_audit_plan.main([
                "/fixture", "--batch", "B001", "--at", GENERATED,
                "--apply",
            ])

        self.assertEqual(2, code)
        self.assertEqual({
            "applied": False,
            "contract_owner": "profile-rendering-contract",
            "errors": [],
            "hold_reason": "contract-gap",
            "status": "hold",
            "targets": [
                {"target": "AMermaid.md",
                 "constructs": ["mermaid-fence"]},
                {"target": "ZTable.md",
                 "constructs": ["outer-pipe-markdown-table"]},
            ],
        }, json.loads(output.getvalue()))
        managed_path.assert_not_called()
        write.assert_not_called()

    def test_currentness_ignores_normal_queue_and_page_evolution(self):
        tiers = {"L.md": "L", "M.md": "M", "S.md": "S"}
        plan, _, values = self.build(tiers)
        result, item, _old_frozen, state, profile, standards, opening = values
        advanced = dict(state)
        advanced.update({
            "queue_revision": state["queue_revision"] + 9,
            "queue_state_revision": state["queue_state_revision"] + 5,
            "required_queue_sha256": SHA_E,
        })
        current = tuple(self.frozen(path, "f") for path in sorted(tiers))
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                audit_producer_runtime, "runtime_state_bindings",
                return_value=advanced))
            stack.enter_context(mock.patch.object(
                audit_producer_runtime, "profile_bindings",
                return_value=profile))
            stack.enter_context(mock.patch.object(
                audit_producer_runtime, "standards_bindings",
                return_value=standards))
            stack.enter_context(mock.patch.object(
                audit_producer_runtime, "freeze_manifest_pages",
                return_value=current))
            stack.enter_context(mock.patch.object(
                prepare_audit_plan, "check_queue_opening_context",
                return_value=opening))
            actual = prepare_audit_plan.require_plan_current(
                plan, str(REPOSITORY), result, item, {})
        self.assertEqual(current, actual)

        stale_opening = copy.deepcopy(opening)
        stale_opening["opening_transition_receipt"] = "reopened-fixture"
        with mock.patch.object(
                audit_producer_runtime, "runtime_state_bindings",
                return_value=advanced), mock.patch.object(
                    audit_producer_runtime, "profile_bindings",
                    return_value=profile), mock.patch.object(
                        audit_producer_runtime, "standards_bindings",
                        return_value=standards), mock.patch.object(
                            prepare_audit_plan,
                            "check_queue_opening_context",
                            return_value=stale_opening):
            with self.assertRaisesRegex(ValueError, "opening_transition"):
                prepare_audit_plan.require_plan_current(
                    plan, str(REPOSITORY), result, item, {}, frozen=current)

    def test_currentness_rechecks_rendering_contract_gap_after_open(self):
        tiers = {"L.md": "L", "M.md": "M", "S.md": "S"}
        plan, _, values = self.build(tiers)
        result, item, _old_frozen, state, profile, standards, opening = values
        current = (
            self.frozen(
                "L.md", "a", "# L\n\n| A |\n|---|\n| x |\n"),
            self.frozen("M.md", "b"),
            self.frozen("S.md", "c"),
        )
        with mock.patch.object(
                audit_producer_runtime, "runtime_state_bindings",
                return_value=state), mock.patch.object(
                    audit_producer_runtime, "profile_bindings",
                    return_value=profile), mock.patch.object(
                        audit_producer_runtime, "standards_bindings",
                        return_value=standards), mock.patch.object(
                            prepare_audit_plan,
                            "check_queue_opening_context",
                            return_value=opening):
            with self.assertRaisesRegex(
                    prepare_audit_plan.ProfileRenderingContractGap,
                    "contract-gap/HOLD"):
                prepare_audit_plan.require_plan_current(
                    plan, str(REPOSITORY), result, item, {}, frozen=current)


_BATCH_SCOPE_TARGET = "."


if __name__ == "__main__":
    unittest.main()
