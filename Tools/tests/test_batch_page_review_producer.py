"""Independent K12/14 registry, sampling, and producer-chain tests."""

import copy
from math import ceil
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import audit_plan_contract  # noqa: E402
import audit_obligation_projection  # noqa: E402
import audit_evidence_runtime  # noqa: E402
import audit_producer_runtime  # noqa: E402
import batch_review_obligation_contract as contract  # noqa: E402
import kblib  # noqa: E402
import record_batch_page_review as producer  # noqa: E402
import runtime_paths  # noqa: E402


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
PAGE_TEXT = "# Page\n\nMechanism and boundary.\n\n## Sources\n\n- source\n"


class BatchPageReviewProducerTests(unittest.TestCase):

    def setUp(self):
        self.registry = kblib.load_yaml_file(
            REPOSITORY /
            "kernel/K12 Quality Assurance/"
            "batch-review-obligation-registry.yaml")
        contract.validate_registry(self.registry)

    def test_producer_page_must_be_the_frozen_obligation_target(self):
        plan, _manifest, _tiers, _selection = self.full_plan(s_count=2)
        obligation = next(
            row for row in plan["obligations"]
            if row["obligation_id"].startswith("m-"))

        with self.assertRaisesRegex(
                audit_producer_runtime.AuditProducerError,
                "targets a different page"):
            producer._required_obligation(
                plan, obligation["obligation_id"], "Other.md",
                "m-atomic-item", self.registry)
        with self.assertRaisesRegex(
                audit_producer_runtime.AuditProducerError,
                "not exactly one frozen manifest member"):
            producer._frozen_page(
                [self.frozen(obligation["target"])], "Other.md")

    def plan_header(self, obligations):
        plan = {
            "schema_version": 1,
            "plan_id": "audit-plan-test",
            "task_id": "task-test",
            "batch_id": "B001",
            "generated_at": "2020-01-01T00:00:00Z",
            "queue_revision": 1,
            "queue_state_revision": 2,
            "required_queue_sha256": SHA_A,
            "standards_version": "standards-test",
            "active_standards_sha256": SHA_A,
            "selected_profile_manifest": "profiles/test/profile.md",
            "profile_snapshot_sha256": SHA_B,
            "profile_contract_fingerprint": SHA_C,
            "opening_transition_receipt": "audit-update_queue-open-1",
            "artifact_snapshot_sha256": SHA_A,
            "contract_snapshot_sha256": SHA_B,
            "accepted_baseline_sha256": SHA_C,
            "obligations": sorted(
                obligations, key=lambda row: row["obligation_id"]),
        }
        audit_plan_contract.validate_plan(plan)
        return plan

    def m_obligation(self, item, page, position):
        projection = self.registry["audit_plan_projection"]
        partition = item["trigger_partition_mappings"][0]["partition"]
        return {
            "obligation_id": "m-%04d" % position,
            "owner_kind": projection["owner_kind"],
            "owner_rule_id": item["rule_id"],
            "kernel_extension_point": projection["kernel_extension_point"],
            "partition": partition,
            "due_stage": item["due_stage"],
            "target": page,
            "applicability": item["applicability"],
            "evidence_role": item["evidence_role"],
            "evidence_kind": item["evidence_kind"],
            "dimension": item["dimension"],
            "acceptance_predicate":
                item["acceptance_contract"]["contract_id"],
            "producer_check": item["producer_check"],
            "producer_capability": item["producer_capability"],
            "producer_gate_id": None,
            "consumer_gate_id": item["consumer_gate_id"],
            "fingerprint_binding": projection["fingerprint_binding"],
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }

    def s_obligation(self, page, position):
        projection = self.registry["audit_plan_projection"]
        sampling = self.registry["s_tier_sampling"]
        item = sampling["sampled_review_obligation"]
        return {
            "obligation_id": "s-%04d" % position,
            "owner_kind": projection["owner_kind"],
            "owner_rule_id": sampling["rule_id"],
            "kernel_extension_point": projection["kernel_extension_point"],
            "partition": item["partition"],
            "due_stage": item["due_stage"],
            "target": page,
            "applicability": item["applicability"],
            "evidence_role": item["evidence_role"],
            "evidence_kind": item["evidence_kind"],
            "dimension": item["dimension"],
            "acceptance_predicate":
                item["acceptance_contract"]["contract_id"],
            "producer_check": item["producer_check"],
            "producer_capability": item["producer_capability"],
            "producer_gate_id": None,
            "consumer_gate_id": item["consumer_gate_id"],
            "fingerprint_binding": item["fingerprint_binding"],
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }

    def full_plan(self, s_count=11):
        m_page = "M.md"
        s_pages = ["S-%03d.md" % index for index in range(s_count)]
        manifest = sorted([m_page] + s_pages)
        tiers = {m_page: "M"}
        tiers.update({path: "S" for path in s_pages})
        obligations = [
            self.m_obligation(item, m_page, index)
            for index, item in enumerate(
                self.registry["m_tier_atomic_items"], 1)
        ]
        selection = contract.select_s_targets(
            s_pages, task_id="task-test", batch_id="B001",
            opening_transition_receipt="audit-update_queue-open-1",
            registry=self.registry)
        obligations.extend(
            self.s_obligation(page, index)
            for index, page in enumerate(
                selection["sample_selected_targets"], 1)
        )
        return self.plan_header(obligations), manifest, tiers, selection

    def with_same_page_changed_scope(self, plan, page, count=2,
                                     rule_ids=None):
        available = [
            row for row in audit_obligation_projection.base_obligation_specs(
                str(REPOSITORY))
            if row["partition"] == "changed-scope-deterministic" and
            row["evidence_role"] == "emits"
        ]
        if rule_ids is None:
            specs = [row for row in available
                     if row["evidence_kind"] == "audit-receipt"][:count]
            self.assertEqual(count, len(specs))
        else:
            by_rule = {row["owner_rule_id"]: row for row in available}
            self.assertEqual(set(rule_ids), set(rule_ids).intersection(by_rule))
            specs = [by_rule[rule_id] for rule_id in rule_ids]
        changed = copy.deepcopy(plan)
        obligations = []
        for index, spec in enumerate(specs, 1):
            definition = audit_obligation_projection.\
                resolve_obligation_definition(spec, page)
            definition.update({
                "obligation_id": "changed-%04d" % index,
                "review_due": None,
                "status": "required",
                "evidence_ref": None,
                "reused_receipt_id": None,
                "reuse_reason": None,
            })
            obligations.append(definition)
        changed["obligations"].extend(obligations)
        changed["obligations"].sort(key=lambda row: row["obligation_id"])
        audit_plan_contract.validate_plan(changed)
        return changed, obligations

    @staticmethod
    def passing_evidence(plan, obligation, index):
        return {
            "receipt_id": "audit-changed-%04d" % index,
            "record_kind": obligation["evidence_kind"],
            "plan_id": plan["plan_id"],
            "audit_plan_sha256": audit_plan_contract.plan_sha256(plan),
            "obligation_id": obligation["obligation_id"],
            "owner_kind": obligation["owner_kind"],
            "owner_rule_id": obligation["owner_rule_id"],
            "target": obligation["target"],
            "partition": obligation["partition"],
            "due_stage": obligation["due_stage"],
            "evidence_role": obligation["evidence_role"],
            "evidence_kind": obligation["evidence_kind"],
            "dimension": (
                obligation["dimension"]
                if obligation["evidence_kind"] == "audit-receipt"
                else None),
            "acceptance_predicate": obligation["acceptance_predicate"],
            "producer_check": obligation["producer_check"],
            "consumer_gate_id": obligation["consumer_gate_id"],
            "result": "passed",
            "invalidated_by": None,
        }

    @staticmethod
    def frozen(path):
        return audit_producer_runtime.FrozenPage(
            path=path, page_sha256=SHA_A,
            semantic_content_fingerprint=SHA_B,
            snapshot=SimpleNamespace(read_text=lambda: PAGE_TEXT),
        )

    def test_expected_sets_are_derived_from_kernel_registry(self):
        source = (
            REPOSITORY /
            "kernel/K12 Quality Assurance/"
            "01 Quality Dimensions and Single Note Review.md").read_text()
        section = source.split(
            "## M-tier Gate Checklist", 1)[1].split("### Structure", 1)[0]
        displayed = [line[2:] for line in section.splitlines()
                     if line.startswith("- ")]
        registered_groups = [
            row["source_text"]
            for row in self.registry["m_tier_source_groups"]]
        raw_items = self.registry["m_tier_atomic_items"]
        raw_rules = [row["rule_id"] for row in raw_items]
        raw_rules.append(self.registry["s_tier_sampling"]["rule_id"])

        self.assertEqual(displayed, registered_groups)
        self.assertEqual(
            tuple(row["item_id"] for row in raw_items),
            contract.M_ATOMIC_ITEM_IDS)
        self.assertEqual(
            raw_rules,
            [row["rule_id"] for row in
             contract.base_obligation_specs(self.registry)])
        self.assertEqual(
            {row["group_id"]
             for row in self.registry["m_tier_source_groups"]},
            {row["source_group"] for row in raw_items})

    def test_registry_is_strict_and_rejects_semantic_drift(self):
        changed = copy.deepcopy(self.registry)
        changed["m_tier_atomic_items"][0]["unregistered"] = True
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_registry(changed)

        changed = copy.deepcopy(self.registry)
        changed["m_tier_atomic_items"][0]["dimension"] = "made_up"
        with self.assertRaisesRegex(ValueError, "base dimension"):
            contract.validate_registry(changed)

        changed = copy.deepcopy(self.registry)
        changed["s_tier_sampling"]["sample_count"]["rounding"] = "floor"
        with self.assertRaisesRegex(ValueError, "ceiling"):
            contract.validate_registry(changed)

    def test_m_evidence_roles_preserve_the_existing_checklist_boundary(self):
        values = contract.validate_registry(self.registry)
        items = {row["item_id"]: row for row in values["m_items"]}
        direct_profile_application = {
            "m06-language-contract-applied",
            "m06-triggered-source-obligations-applied",
            "m06-triggered-terminology-obligations-applied",
            "m06-triggered-propagation-obligations-applied",
        }
        self.assertTrue(all(
            items[item_id]["evidence_role"] == "emits"
            for item_id in direct_profile_application))

        for item_id in (
                "m05-no-required-link-missing",
                "m05-no-required-link-ambiguous"):
            selector = values["m_consumption_by_item_id"][item_id][
                "selector"]
            self.assertEqual(
                ("k12-02-level0-wiki-link-resolution",),
                selector["owner_rule_ids"])
            self.assertEqual("exactly-one", selector["match_cardinality"])

        deterministic = values["m_consumption_by_item_id"][
            "m07-applicable-deterministic-checks-pass"]["selector"]
        self.assertIsNone(deterministic["owner_rule_ids"])
        self.assertEqual(
            "one-or-more-all-matching-required",
            deterministic["match_cardinality"])

        rendering = values["m_consumption_by_item_id"][
            "m06-triggered-rendering-obligations-applied"]
        self.assertEqual("hold", rendering["resolution"])

    def test_ceiling_count_is_independently_derived_from_parameters(self):
        values = self.registry["s_tier_sampling"]["sample_count"]
        minimum = values["minimum_count"]
        numerator = values["percentage_numerator"]
        denominator = values["percentage_denominator"]
        for population in range(251):
            expected = population if population < minimum else max(
                minimum, ceil(population * numerator / denominator))
            self.assertEqual(
                expected, contract.s_sample_count(population, self.registry),
                population)

    def test_s_selection_is_stable_order_independent_and_context_bound(self):
        population = ["S-%03d.md" % index for index in range(200)]
        first = contract.select_s_targets(
            population, task_id="task", batch_id="B1",
            opening_transition_receipt="open-1", registry=self.registry)
        repeated = contract.select_s_targets(
            list(reversed(population)), task_id="task", batch_id="B1",
            opening_transition_receipt="open-1", registry=self.registry)
        next_batch = contract.select_s_targets(
            population, task_id="task", batch_id="B2",
            opening_transition_receipt="open-2", registry=self.registry)

        self.assertEqual(first, repeated)
        self.assertEqual(
            first["sample_required_count"],
            len(first["sample_selected_targets"]))
        self.assertEqual(
            contract.S_SELECTION_ALGORITHM_ID,
            first["selection_algorithm_id"])
        self.assertNotEqual(
            first["sample_selected_targets"],
            next_batch["sample_selected_targets"])

    def test_plan_closure_requires_every_registry_atom_and_exact_s_sample(self):
        plan, manifest, tiers, selection = self.full_plan()
        result = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        self.assertEqual(selection, result["s_selection"])
        raw_expected = {
            ("M.md", row["rule_id"])
            for row in self.registry["m_tier_atomic_items"]}
        raw_expected.update(
            (page, self.registry["s_tier_sampling"]["rule_id"])
            for page in selection["sample_selected_targets"])
        self.assertEqual(
            raw_expected,
            set(result["obligations_by_target_rule"]))

        incomplete = copy.deepcopy(plan)
        incomplete["obligations"].pop(0)
        audit_plan_contract.validate_plan(incomplete)
        with self.assertRaisesRegex(ValueError, "closure differs"):
            contract.validate_plan_base_closure(
                incomplete, manifest, tiers, self.registry)

    def test_m_producer_freezes_three_fingerprints_and_closed_fields(self):
        plan, manifest, tiers, _selection = self.full_plan()
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        emitting = next(
            row for row in self.registry["m_tier_atomic_items"]
            if row["evidence_role"] == "emits")
        obligation = closure["obligations_by_target_rule"][
            ("M.md", emitting["rule_id"])]
        spec = contract.obligation_spec_for_rule(
            emitting["rule_id"], self.registry)
        receipt = producer.build_review_receipt(
            root=str(REPOSITORY), plan=plan,
            plan_sha256=audit_plan_contract.plan_sha256(plan),
            obligation=obligation, spec=spec,
            page_snapshot=self.frozen("M.md"),
            reviewer_context_id="review-context",
            reviewer_role="batch-reviewer", verdict="passed",
            statement="acceptance contract satisfied",
            applicability_disposition="applicable",
            registry=self.registry, identity={})

        self.assertIs(
            receipt,
            contract.validate_producer_receipt(receipt, self.registry))
        self.assertEqual(
            audit_producer_runtime.page_artifact_fingerprint(
                self.frozen("M.md")),
            receipt["artifact_fingerprint"])
        self.assertEqual(
            SHA_B, receipt["semantic_content_fingerprint"])
        self.assertEqual(
            contract.dependency_fingerprint(
                audit_producer_runtime.sources_sha256(PAGE_TEXT)),
            receipt["dependency_fingerprint"])
        self.assertEqual(
            contract.contract_fingerprint(spec, plan, self.registry),
            receipt["contract_fingerprint"])
        expected_fields = set(
            contract.validate_registry(self.registry)["producer"]
            ["variants"]["m-atomic-item"]["instance_fields"])
        self.assertEqual(expected_fields, set(receipt))

        changed = copy.deepcopy(receipt)
        changed["dimension"] = None
        with self.assertRaisesRegex(ValueError, "drifts"):
            contract.validate_producer_receipt(changed, self.registry)
        changed = copy.deepcopy(receipt)
        changed["extra"] = "not allowed"
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_producer_receipt(changed, self.registry)

    def test_consumes_role_uses_exact_plan_selector_not_any_pass(self):
        plan, manifest, tiers, _selection = self.full_plan()
        plan, source_obligations = self.with_same_page_changed_scope(
            plan, "M.md")
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        consuming = next(
            row for row in self.registry["m_tier_atomic_items"]
            if row["item_id"] ==
            "m07-applicable-deterministic-checks-pass")
        obligation = closure["obligations_by_target_rule"][
            ("M.md", consuming["rule_id"])]
        spec = contract.obligation_spec_for_rule(
            consuming["rule_id"], self.registry)
        plan_sha256 = audit_plan_contract.plan_sha256(plan)
        dependencies = tuple(
            self.passing_evidence(plan, row, index)
            for index, row in enumerate(source_obligations, 1))
        kwargs = {
            "root": str(REPOSITORY), "plan": plan,
            "plan_sha256": plan_sha256,
            "obligation": obligation, "spec": spec,
            "page_snapshot": self.frozen("M.md"),
            "reviewer_context_id": "review-context",
            "reviewer_role": "batch-reviewer", "verdict": "passed",
            "statement": "canonical deterministic evidence consumed",
            "applicability_disposition": "applicable",
            "registry": self.registry, "identity": {},
        }
        with self.assertRaisesRegex(ValueError, "exactly one current"):
            producer.build_review_receipt(**kwargs)

        arbitrary = {
            "receipt_id": "audit-unrelated-pass",
            "result": "pass",
            "invalidated_by": None,
        }
        with self.assertRaisesRegex(ValueError, "exactly one current"):
            producer.build_review_receipt(
                **kwargs, consumed_records=(arbitrary,))
        with self.assertRaisesRegex(ValueError, "exactly one current"):
            producer.build_review_receipt(
                **kwargs, consumed_records=dependencies[:-1])

        receipt = producer.build_review_receipt(
            **kwargs, consumed_records=dependencies)
        self.assertEqual(
            sorted(row["receipt_id"] for row in dependencies),
            receipt["consumed_evidence_refs"])
        self.assertEqual(
            contract.dependency_fingerprint(
                audit_producer_runtime.sources_sha256(PAGE_TEXT),
                dependencies),
            receipt["dependency_fingerprint"])
        catalog = {row["receipt_id"]: row for row in dependencies}
        self.assertEqual(
            tuple(sorted(dependencies, key=lambda row: row["receipt_id"])),
            contract.validate_receipt_consumption(
                plan, plan_sha256, receipt, catalog, self.registry))

    def test_m05_consumes_only_the_exact_premerge_wiki_link_gate(self):
        plan, manifest, tiers, _selection = self.full_plan(s_count=0)
        plan, source_obligations = self.with_same_page_changed_scope(
            plan, "M.md", rule_ids=(
                "k12-02-level0-wiki-link-resolution",
                "k12-02-level0-fence-closure",
            ))
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        by_rule = {row["owner_rule_id"]: row for row in source_obligations}
        wiki = self.passing_evidence(
            plan, by_rule["k12-02-level0-wiki-link-resolution"], 1)
        unrelated = self.passing_evidence(
            plan, by_rule["k12-02-level0-fence-closure"], 2)
        item = next(
            row for row in self.registry["m_tier_atomic_items"]
            if row["item_id"] == "m05-no-required-link-missing")
        obligation = closure["obligations_by_target_rule"][
            ("M.md", item["rule_id"])]
        spec = contract.obligation_spec_for_rule(
            item["rule_id"], self.registry)
        kwargs = {
            "root": str(REPOSITORY), "plan": plan,
            "plan_sha256": audit_plan_contract.plan_sha256(plan),
            "obligation": obligation, "spec": spec,
            "page_snapshot": self.frozen("M.md"),
            "reviewer_context_id": "review-context",
            "reviewer_role": "batch-reviewer", "verdict": "passed",
            "statement": "the exact wiki-link Gate evidence passes",
            "applicability_disposition": "applicable",
            "registry": self.registry, "identity": {},
        }
        with self.assertRaisesRegex(ValueError, "references differ"):
            producer.build_review_receipt(
                **kwargs, consumed_records=(wiki, unrelated))
        receipt = producer.build_review_receipt(
            **kwargs, consumed_records=(wiki,))
        self.assertEqual([wiki["receipt_id"]],
                         receipt["consumed_evidence_refs"])

    def test_complete_plain_m_page_chain_has_one_record_per_atom(self):
        plan, manifest, tiers, _selection = self.full_plan(s_count=0)
        plan, source_obligations = self.with_same_page_changed_scope(
            plan, "M.md",
            rule_ids=("k12-02-level0-wiki-link-resolution",))
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        plan_sha256 = audit_plan_contract.plan_sha256(plan)
        wiki = self.passing_evidence(plan, source_obligations[0], 1)
        records = []
        for seq, item in enumerate(
                self.registry["m_tier_atomic_items"], 1):
            spec = contract.obligation_spec_for_rule(
                item["rule_id"], self.registry)
            obligation = closure["obligations_by_target_rule"][
                ("M.md", item["rule_id"])]
            not_applicable = (
                item["item_id"] ==
                "m06-triggered-rendering-obligations-applied")
            consumed = (wiki,) if (
                item["evidence_role"] == "consumes" and
                not not_applicable) else ()
            records.append(producer.build_review_receipt(
                root=str(REPOSITORY), plan=plan,
                plan_sha256=plan_sha256,
                obligation=obligation, spec=spec,
                page_snapshot=self.frozen("M.md"),
                reviewer_context_id="review-context",
                reviewer_role="batch-reviewer", verdict="passed",
                statement=(
                    "no Profile rendering obligation is triggered"
                    if not_applicable else
                    "the existing M checklist acceptance item is satisfied"),
                consumed_records=consumed,
                applicability_disposition=(
                    "not-applicable" if not_applicable else "applicable"),
                applicability_reason=(
                    "The plain page triggers no Profile rendering rule."
                    if not_applicable else None),
                registry=self.registry, identity={}, seq=seq))

        self.assertEqual(
            len(self.registry["m_tier_atomic_items"]), len(records))
        self.assertEqual(
            {row["rule_id"]
             for row in self.registry["m_tier_atomic_items"]},
            {row["rule_id"] for row in records})
        catalog = {wiki["receipt_id"]: wiki}
        catalog.update({row["receipt_id"]: row for row in records})
        result = {
            "root": str(REPOSITORY),
            "_profile_authorized_view": {},
        }
        current_snapshot = SimpleNamespace(read_text=lambda: PAGE_TEXT)
        patches = (
            mock.patch.object(
                audit_evidence_runtime.metadata_property_state,
                "authorized_profile_projection_rules",
                return_value=(None, {})),
            mock.patch.object(
                audit_evidence_runtime.metadata_property_state,
                "semantic_page_snapshot",
                return_value=(current_snapshot, SHA_B)),
        )
        with patches[0], patches[1]:
            for record in records:
                obligation = closure["obligations_by_target_rule"][
                    ("M.md", record["rule_id"])]
                self.assertEqual(
                    [], audit_evidence_runtime._batch_page_binding_errors(
                        result, catalog, str(REPOSITORY), plan, plan_sha256,
                        obligation, record),
                    record["item_id"])
            with mock.patch.object(
                    audit_evidence_runtime, "_direct_binding_errors",
                    return_value=[]):
                selected = audit_evidence_runtime._required_stage_records(
                    result, {"id": "B001"}, plan, plan_sha256, catalog,
                    "pre-merge")
        self.assertEqual(len(plan["obligations"]), len(selected))
        self.assertEqual(
            {row["obligation_id"] for row in plan["obligations"]},
            {row[0]["obligation_id"] for row in selected})

    def test_central_consumer_rechecks_selector_and_page_fingerprints(self):
        plan, manifest, tiers, _selection = self.full_plan()
        plan, source_obligations = self.with_same_page_changed_scope(
            plan, "M.md")
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        consuming = next(
            row for row in self.registry["m_tier_atomic_items"]
            if row["item_id"] ==
            "m07-applicable-deterministic-checks-pass")
        obligation = closure["obligations_by_target_rule"][
            ("M.md", consuming["rule_id"])]
        spec = contract.obligation_spec_for_rule(
            consuming["rule_id"], self.registry)
        plan_sha256 = audit_plan_contract.plan_sha256(plan)
        dependencies = tuple(
            self.passing_evidence(plan, row, index)
            for index, row in enumerate(source_obligations, 1))
        receipt = producer.build_review_receipt(
            root=str(REPOSITORY), plan=plan, plan_sha256=plan_sha256,
            obligation=obligation, spec=spec,
            page_snapshot=self.frozen("M.md"),
            reviewer_context_id="review-context",
            reviewer_role="batch-reviewer", verdict="passed",
            statement="central closure rechecks exact dependencies",
            consumed_records=dependencies,
            applicability_disposition="applicable",
            registry=self.registry, identity={})
        catalog = {row["receipt_id"]: row for row in dependencies}
        result = {"_profile_authorized_view": {}}
        current_snapshot = SimpleNamespace(read_text=lambda: PAGE_TEXT)
        patches = (
            mock.patch.object(
                audit_evidence_runtime.metadata_property_state,
                "authorized_profile_projection_rules",
                return_value=(None, {})),
            mock.patch.object(
                audit_evidence_runtime.metadata_property_state,
                "semantic_page_snapshot",
                return_value=(current_snapshot, SHA_B)),
        )
        with patches[0], patches[1]:
            self.assertEqual(
                [], audit_evidence_runtime._batch_page_binding_errors(
                    result, catalog, str(REPOSITORY), plan, plan_sha256,
                    obligation, receipt))

            selector_drift = copy.deepcopy(catalog)
            changed_id = dependencies[0]["receipt_id"]
            selector_drift[changed_id]["owner_rule_id"] = "unrelated-pass"
            errors = audit_evidence_runtime._batch_page_binding_errors(
                result, selector_drift, str(REPOSITORY), plan, plan_sha256,
                obligation, receipt)
            self.assertTrue(any("exactly one current" in row
                                for row in errors), errors)

            fingerprint_drift = copy.deepcopy(receipt)
            fingerprint_drift["artifact_fingerprint"] = SHA_A
            errors = audit_evidence_runtime._batch_page_binding_errors(
                result, catalog, str(REPOSITORY), plan, plan_sha256,
                obligation, fingerprint_drift)
            self.assertTrue(any("artifact fingerprint" in row
                                for row in errors), errors)

    def test_consumption_contract_inventory_is_closed_and_gap_is_conditional(self):
        values = contract.validate_registry(self.registry)
        consumes = {
            row["item_id"] for row in self.registry["m_tier_atomic_items"]
            if row["evidence_role"] == "consumes"
        }
        self.assertEqual(
            consumes, set(values["m_consumption_by_item_id"]))
        for item_id, row in values["m_consumption_by_item_id"].items():
            if row["resolution"] == "hold":
                self.assertIsNone(row["selector"], item_id)
                self.assertTrue(row["hold_reason"], item_id)
            else:
                self.assertIsNone(row["hold_reason"], item_id)
                self.assertIsInstance(row["selector"], dict, item_id)

        plan, manifest, tiers, _selection = self.full_plan()
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        held_rows = [
            row for row in self.registry["m_tier_atomic_items"]
            if (row["item_id"] in values["m_consumption_by_item_id"] and
                values["m_consumption_by_item_id"][row["item_id"]]
                ["resolution"] == "hold")]
        self.assertEqual(
            ["m06-triggered-rendering-obligations-applied"],
            [row["item_id"] for row in held_rows])
        self.assertTrue(all(
            row["applicability"] != "always" for row in held_rows))
        held = held_rows[0]
        spec = contract.obligation_spec_for_rule(
            held["rule_id"], self.registry)
        obligation = closure["obligations_by_target_rule"][
            ("M.md", held["rule_id"])]
        with self.assertRaisesRegex(ValueError, "selector is HOLD"):
            producer.build_review_receipt(
                root=str(REPOSITORY), plan=plan,
                plan_sha256=audit_plan_contract.plan_sha256(plan),
                obligation=obligation, spec=spec,
                page_snapshot=self.frozen("M.md"),
                reviewer_context_id="review-context",
                reviewer_role="batch-reviewer", verdict="passed",
                statement="must not accept an arbitrary pass",
                applicability_disposition="applicable",
                registry=self.registry, identity={})

        receipt = producer.build_review_receipt(
            root=str(REPOSITORY), plan=plan,
            plan_sha256=audit_plan_contract.plan_sha256(plan),
            obligation=obligation, spec=spec,
            page_snapshot=self.frozen("M.md"),
            reviewer_context_id="review-context",
            reviewer_role="batch-reviewer", verdict="passed",
            statement="no Profile rendering obligation is triggered",
            applicability_disposition="not-applicable",
            applicability_reason="The page triggers no Profile rendering rule.",
            registry=self.registry, identity={})
        self.assertEqual("not-applicable", receipt["applicability_disposition"])

    def test_conditional_atoms_record_explicit_not_applicable_reason(self):
        plan, manifest, tiers, _selection = self.full_plan()
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        conditional = next(
            row for row in self.registry["m_tier_atomic_items"]
            if (row["applicability"] != "always" and
                row["evidence_role"] == "emits"))
        spec = contract.obligation_spec_for_rule(
            conditional["rule_id"], self.registry)
        obligation = closure["obligations_by_target_rule"][
            ("M.md", conditional["rule_id"])]
        kwargs = {
            "root": str(REPOSITORY), "plan": plan,
            "plan_sha256": audit_plan_contract.plan_sha256(plan),
            "obligation": obligation, "spec": spec,
            "page_snapshot": self.frozen("M.md"),
            "reviewer_context_id": "review-context",
            "reviewer_role": "batch-reviewer", "verdict": "passed",
            "statement": "condition does not occur on this page",
            "applicability_disposition": "not-applicable",
            "registry": self.registry, "identity": {},
        }
        with self.assertRaisesRegex(ValueError, "reason"):
            producer.build_review_receipt(**kwargs)
        receipt = producer.build_review_receipt(
            **kwargs, applicability_reason="The governed condition is absent.")
        self.assertEqual(
            "not-applicable", receipt["applicability_disposition"])
        self.assertEqual([], receipt["consumed_evidence_refs"])
        self.assertEqual(
            "The governed condition is absent.",
            receipt["applicability_reason"])

        unconditional = next(
            row for row in self.registry["m_tier_atomic_items"]
            if row["applicability"] == "always" and
            row["evidence_role"] == "emits")
        unconditional_spec = contract.obligation_spec_for_rule(
            unconditional["rule_id"], self.registry)
        with self.assertRaisesRegex(ValueError, "always-applicable"):
            contract.validate_applicability_disposition(
                unconditional_spec, "not-applicable", "not present",
                self.registry)

        conditional_consumes = next(
            row for row in self.registry["m_tier_atomic_items"]
            if row["applicability"] != "always" and
            row["evidence_role"] == "consumes")
        consumes_spec = contract.obligation_spec_for_rule(
            conditional_consumes["rule_id"], self.registry)
        consumes_obligation = closure["obligations_by_target_rule"][
            ("M.md", conditional_consumes["rule_id"])]
        n_a = producer.build_review_receipt(
            root=str(REPOSITORY), plan=plan,
            plan_sha256=audit_plan_contract.plan_sha256(plan),
            obligation=consumes_obligation, spec=consumes_spec,
            page_snapshot=self.frozen("M.md"),
            reviewer_context_id="review-context",
            reviewer_role="batch-reviewer", verdict="passed",
            statement="profile trigger is absent",
            applicability_disposition="not-applicable",
            applicability_reason="No matching Profile trigger is active.",
            registry=self.registry, identity={})
        self.assertEqual([], n_a["consumed_evidence_refs"])

    def test_sampled_s_record_stays_dimensionless_and_binds_selection(self):
        plan, manifest, tiers, selection = self.full_plan()
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        page = selection["sample_selected_targets"][0]
        rule_id = self.registry["s_tier_sampling"]["rule_id"]
        obligation = closure["obligations_by_target_rule"][(page, rule_id)]
        spec = contract.obligation_spec_for_rule(rule_id, self.registry)
        receipt = producer.build_review_receipt(
            root=str(REPOSITORY), plan=plan,
            plan_sha256=audit_plan_contract.plan_sha256(plan),
            obligation=obligation, spec=spec,
            page_snapshot=self.frozen(page),
            reviewer_context_id="review-context",
            reviewer_role="batch-reviewer", verdict="passed",
            statement="sampled page reviewed",
            selection=selection, registry=self.registry, identity={})

        contract.validate_producer_receipt(receipt, self.registry)
        self.assertIsNone(receipt["dimension"])
        self.assertEqual(
            "batch-page-review-record", receipt["evidence_kind"])
        self.assertEqual(
            plan["generated_at"], receipt["selection_frozen_at"])
        self.assertIn(page, receipt["sample_selected_targets"])

    def test_runtime_path_is_dedicated_registered_evidence(self):
        self.assertEqual(
            ".cambium/receipts/batch-page-reviews.jsonl",
            runtime_paths.BATCH_PAGE_REVIEW_RECEIPT_PATH)
        self.assertEqual(
            runtime_paths.EVIDENCE,
            runtime_paths.category_for("batch-page-review-receipts"))

    def test_append_preserves_prior_rows_and_exact_readback_is_mandatory(self):
        plan, manifest, tiers, _selection = self.full_plan()
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        emitting = next(
            row for row in self.registry["m_tier_atomic_items"]
            if row["evidence_role"] == "emits")
        obligation = closure["obligations_by_target_rule"][
            ("M.md", emitting["rule_id"])]
        spec = contract.obligation_spec_for_rule(
            emitting["rule_id"], self.registry)
        receipt = producer.build_review_receipt(
            root=str(REPOSITORY), plan=plan,
            plan_sha256=audit_plan_contract.plan_sha256(plan),
            obligation=obligation, spec=spec,
            page_snapshot=self.frozen("M.md"),
            reviewer_context_id="review-context",
            reviewer_role="batch-reviewer", verdict="passed",
            statement="append and read back",
            applicability_disposition="applicable",
            registry=self.registry, identity={})
        prior = {
            "receipt_id": "audit-prior-row",
            "check": "prior",
            "target": "prior",
            "result": "pass",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "receipts.jsonl")
            before = kblib.receipt_append_observation(str(path), [prior])
            outcome, error, _ = kblib.write_receipts_observed(
                str(path), [prior], before=before)
            self.assertEqual(("present", None), (outcome, error))
            before = kblib.receipt_append_observation(str(path), [receipt])
            outcome, error, _ = kblib.write_receipts_observed(
                str(path), [receipt], before=before)
            self.assertEqual(("present", None), (outcome, error))
            self.assertEqual(
                receipt,
                producer.require_exact_readback(
                    str(path), receipt, self.registry))
            rows = audit_producer_runtime.read_receipt_records(str(path))
            self.assertEqual(prior, rows[0])
            self.assertEqual(receipt, rows[1])

            with path.open("a", encoding="utf-8") as handle:
                handle.write(
                    kblib.canonical_json_bytes(receipt).decode("utf-8") +
                    "\n")
            with self.assertRaisesRegex(ValueError, "did not read back exactly"):
                producer.require_exact_readback(
                    str(path), receipt, self.registry)


if __name__ == "__main__":
    unittest.main()
