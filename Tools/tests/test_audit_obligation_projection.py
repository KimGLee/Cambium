"""Registry-derived tests for the Kernel base AuditPlan obligation set."""

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
K12 = REPOSITORY / "kernel/K12 Quality Assurance"
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_obligation_projection as projection  # noqa: E402
import Tools.execution.audit.batch_review_obligation_contract as batch_review_obligation_contract  # noqa: E402
import Tools.execution.audit.batch_close_contract as batch_close_contract  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402


def raw(name):
    return kblib.parse_yaml_subset((K12 / name).read_text(encoding="utf-8"))


class BaseProjectionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rows = projection.base_obligation_specs()
        cls.batch_review = raw("batch-review-obligation-registry.yaml")
        cls.changed_scope = raw("changed-scope-check-registry.yaml")
        cls.batch_close = raw("batch-close-closed-list.yaml")
        cls.substantive = raw("substantive-review-contract.yaml")
        cls.deterministic_rendering = raw(
            "deterministic-rendering-contract.yaml")

    def rows_from(self, path):
        return [row for row in self.rows if row["source_registry"] == path]

    def test_m_expected_set_comes_from_registry_and_is_not_substantive(self):
        expected = tuple(
            (row["item_id"], row["rule_id"])
            for row in self.batch_review["m_tier_atomic_items"])
        actual_rows = [row for row in self.rows_from(
            projection.BATCH_REVIEW_REGISTRY_PATH) if row["tier"] == "M"]
        actual = tuple(
            (row["source_entry_id"], row["owner_rule_id"])
            for row in actual_rows)

        self.assertEqual(expected, actual)
        substantive_route = self.substantive[
            "obligation_projection"]["producer_capability"]
        self.assertTrue(actual_rows)
        self.assertTrue(all(
            row["producer_capability"] != substantive_route
            for row in actual_rows))
        self.assertTrue(all(
            row["evidence_kind"] == source["evidence_kind"]
            for row, source in zip(
                actual_rows, self.batch_review["m_tier_atomic_items"])))

    def test_k12_09_projection_is_exactly_the_registry_eight(self):
        expected = tuple(
            row["member_id"] for row in self.batch_close["members"])
        actual_rows = self.rows_from(projection.BATCH_CLOSE_REGISTRY_PATH)
        actual = tuple(row["source_entry_id"] for row in actual_rows)

        self.assertEqual(8, len(expected))
        self.assertEqual(expected, actual)
        self.assertEqual(
            tuple(row["rule_id"] for row in self.batch_close["members"]),
            tuple(row["owner_rule_id"] for row in actual_rows))

    def test_s_count_uses_registry_parameters_and_ceiling(self):
        count = self.batch_review["s_tier_sampling"]["sample_count"]
        minimum = count["minimum_count"]
        numerator = count["percentage_numerator"]
        denominator = count["percentage_denominator"]

        for population in (0, 1, 2, 3, 10, 11, 99, 100, 101):
            with self.subTest(population=population):
                expected = population if population < minimum else max(
                    minimum,
                    (population * numerator + denominator - 1) // denominator)
                self.assertEqual(expected,
                                 batch_review_obligation_contract.
                                 s_sample_count(
                                     population,
                                     batch_review_obligation_contract.
                                     load_registry()))
        self.assertEqual("ceiling", count["rounding"])

    def test_every_base_spec_binds_exactly_one_producer(self):
        for row in self.rows:
            with self.subTest(spec=row["spec_id"]):
                self.assertNotEqual(
                    row["producer_capability"] is None,
                    row["producer_gate_id"] is None)

        invalid = copy.deepcopy(self.changed_scope)
        invalid["base_rules"][0]["producer_gate_id"] = "second-producer"
        with self.assertRaisesRegex(ValueError, "exactly one|fields are not"):
            projection.validate_changed_scope_registry(invalid)

    def test_item_eight_directly_consumes_dimensionless_page_contract_gate(self):
        source = self.batch_close["members"][-1]
        self.assertEqual("manifest_page_contract", source["member_id"])
        row = self.rows_from(projection.BATCH_CLOSE_REGISTRY_PATH)[-1]

        self.assertEqual(source["rule_id"], row["owner_rule_id"])
        self.assertEqual(source["producer_gate_id"], row["producer_gate_id"])
        self.assertIsNone(row["producer_capability"])
        self.assertEqual("gate-receipt", row["evidence_kind"])
        self.assertEqual("consumes", row["evidence_role"])
        self.assertIsNone(row["dimension"])
        resolved = projection.resolve_obligation_definition(
            row, "post-delta-after-image")
        self.assertIsNone(resolved["dimension"])
        self.assertEqual("page-contract", resolved["producer_gate_id"])

    def test_profile_extension_templates_never_enter_the_base_set(self):
        extension_ids = {
            row["extension_point_id"]
            for row in self.changed_scope["extension_points"]}
        self.assertTrue(extension_ids)
        self.assertTrue(all(row["owner_kind"] == "kernel" for row in self.rows))
        self.assertTrue(all(
            row["kernel_extension_point"] is None for row in self.rows))

        profile = copy.deepcopy(self.rows_from(
            projection.CHANGED_SCOPE_REGISTRY_PATH)[0])
        extension_point = next(iter(extension_ids))
        profile.update({
            "spec_id": "profile:registered-example",
            "source_registry": "profiles/example/registration.yaml",
            "source_entry_id": "registered-example",
            "owner_kind": "profile-extension",
            "owner_rule_id": "profile-example-registered-rule",
            "kernel_extension_point": extension_point,
            "dimension": "profile_registered_dimension",
        })
        registered_dimensions = {
            row["dimension"] for row in self.rows
            if row["dimension"] is not None}
        registered_dimensions.add("profile_registered_dimension")
        composed = projection.compose_profile_extensions(
            self.rows, [profile],
            registered_dimensions=registered_dimensions)
        self.assertEqual(len(self.rows) + 1, len(composed))
        self.assertEqual("profile-extension", composed[-1]["owner_kind"])
        self.assertNotIn(profile, self.rows)

    def test_registry_shapes_fail_closed_without_repeating_expected_members(self):
        changed = copy.deepcopy(self.changed_scope)
        changed["base_rules"][0]["unregistered"] = True
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            projection.validate_changed_scope_registry(changed)

        close = copy.deepcopy(self.batch_close)
        close["members"][0]["unregistered"] = True
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            batch_close_contract.validate_batch_close_closed_list(close)

    @staticmethod
    def snapshot(document):
        return SimpleNamespace(
            read_text=lambda: kblib.canonical_yaml(document))

    def test_global_base_projection_rejects_rendering_gap_identity(self):
        gap_id = self.deterministic_rendering["contract_gaps"][0]["gap_id"]
        changed = copy.deepcopy(self.batch_review)
        changed["m_tier_atomic_items"][0]["rule_id"] = gap_id
        snapshots = {
            projection.BATCH_REVIEW_REGISTRY_PATH: self.snapshot(changed),
        }

        with self.assertRaisesRegex(
                ValueError, "promotes K12/02 contract gap"):
            projection.base_obligation_specs(REPOSITORY, snapshots)

    def test_global_base_projection_rejects_unadmitted_k12_02_owner(self):
        changed = copy.deepcopy(self.batch_review)
        changed["m_tier_atomic_items"][0]["rule_id"] = \
            "k12-02-nearby-invented-predicate"
        snapshots = {
            projection.BATCH_REVIEW_REGISTRY_PATH: self.snapshot(changed),
        }

        with self.assertRaisesRegex(
                ValueError, "unadmitted K12/02 owner"):
            projection.base_obligation_specs(REPOSITORY, snapshots)

    def test_profile_composition_rejects_gap_owner_or_acceptance(self):
        gap_id = self.deterministic_rendering["contract_gaps"][0]["gap_id"]
        extension_point = self.changed_scope[
            "extension_points"][0]["extension_point_id"]
        registered_dimensions = {
            row["dimension"] for row in self.rows
            if row["dimension"] is not None}
        registered_dimensions.add("profile_registered_dimension")

        for field in ("owner_rule_id", "acceptance_predicate"):
            with self.subTest(field=field):
                profile = copy.deepcopy(self.rows_from(
                    projection.CHANGED_SCOPE_REGISTRY_PATH)[0])
                profile.update({
                    "spec_id": "profile:rendering-gap-%s" % field,
                    "source_registry": "profiles/example/registration.yaml",
                    "source_entry_id": "profile-rendering-gap-%s" % field,
                    "owner_kind": "profile-extension",
                    "owner_rule_id": "profile-rendering-gap-%s" % field,
                    "kernel_extension_point": extension_point,
                    "dimension": "profile_registered_dimension",
                })
                profile[field] = gap_id

                with self.assertRaisesRegex(
                        ValueError, "promotes K12/02 contract gap"):
                    projection.compose_profile_extensions(
                        self.rows, [profile],
                        registered_dimensions=registered_dimensions,
                        root=REPOSITORY)

    def test_projection_cache_is_bound_to_exact_sources_and_returns_copies(self):
        first = projection.base_obligation_specs(REPOSITORY)
        second = projection.base_obligation_specs(REPOSITORY)
        self.assertEqual(first, second)
        first[0]["owner_rule_id"] = "consumer-mutation"
        self.assertNotEqual(
            first[0]["owner_rule_id"],
            projection.base_obligation_specs(REPOSITORY)[0]["owner_rule_id"])

        changed = copy.deepcopy(self.batch_review)
        changed["m_tier_atomic_items"][0]["rule_id"] = \
            "k12-02-exact-source-cache-probe"
        snapshots = {
            projection.BATCH_REVIEW_REGISTRY_PATH: self.snapshot(changed),
        }
        with self.assertRaisesRegex(ValueError, "unadmitted K12/02 owner"):
            projection.base_obligation_specs(REPOSITORY, snapshots)


if __name__ == "__main__":
    unittest.main()
