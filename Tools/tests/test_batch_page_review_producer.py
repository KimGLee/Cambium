"""Independent K12/14 registry, sampling, and producer-chain tests."""

import copy
from contextlib import ExitStack, nullcontext, redirect_stdout
import io
import json
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

import Tools.execution.audit.audit_plan_contract as audit_plan_contract  # noqa: E402
import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection  # noqa: E402
import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime  # noqa: E402
import Tools.execution.audit.audit_lifecycle_contract as audit_lifecycle_contract
import Tools.execution.audit.audit_fingerprint as audit_fingerprint
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime  # noqa: E402
import Tools.execution.audit.changed_scope_evidence_contract as changed_scope_contract
import Tools.execution.audit.batch_review_obligation_contract as contract  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.execution.audit.record_batch_page_review as producer  # noqa: E402
import Tools.execution.task_runtime.runtime_paths as runtime_paths  # noqa: E402


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
                "M", self.registry)
        self.assertIsNone(audit_producer_runtime.frozen_manifest_page(
            [self.frozen(obligation["target"])], "Other.md"))

    def plan_header(self, obligations):
        plan = {
            "schema_version": audit_plan_contract.load_contract(
                str(REPOSITORY))["schema_version"],
            "plan_id": "audit-plan-test",
            "task_id": "task-test",
            "batch_id": "B001",
            "generated_at": "2020-01-01T00:00:00Z",
            "queue_revision": 1,
            "queue_state_revision": 2,
            "required_queue_sha256": SHA_A,
            "upstream_revision_id": "standards-test",
            "active_standards_sha256": SHA_A,
            "selected_profile_manifest": "profiles/test/profile.toml",
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
            if item["evidence_role"] == "emits"
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
        plan, _ = self.with_same_page_changed_scope(
            self.plan_header(obligations), m_page,
            rule_ids=("k12-02-level0-wiki-link-resolution",))
        plan, _ = self.with_same_page_changed_scope(
            plan, plan["batch_id"],
            rule_ids=("k12-02-rendering-verification-record",))
        return plan, manifest, tiers, selection

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
                     if row["evidence_kind"] ==
                     audit_lifecycle_contract.CHANGED_SCOPE_RECORD_KIND][:count]
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
                "obligation_id": "changed-%04d" % (len(plan["obligations"]) + index),
                "review_due": None,
                "status": "required",
                "evidence_ref": None,
                "reused_receipt_id": None,
                "reuse_reason": None,
            })
            obligations.append(definition)
        replaced = {(row["owner_rule_id"], row["target"]) for row in obligations}
        changed["obligations"] = [row for row in changed["obligations"]
                                  if (row["owner_rule_id"], row["target"]) not in replaced]
        changed["obligations"].extend(obligations)
        changed["obligations"].sort(key=lambda row: row["obligation_id"])
        audit_plan_contract.validate_plan(changed)
        return changed, obligations

    def with_profile_rendering(self, plan, page):
        changed = copy.deepcopy(plan)
        extension = next(row for row in changed_scope_contract.load_registry(
            str(REPOSITORY))["extension_points"]
            if row["extension_point_id"] == "k12-02-profile-rendering")
        obligation = {
            "obligation_id": "profile-rendering-0001",
            "owner_kind": "profile-extension",
            "owner_rule_id": "test-table-rendering",
            "kernel_extension_point": "k12-02-profile-rendering",
            "partition": "changed-scope-deterministic",
            "due_stage": "pre-merge",
            "target": page,
            "applicability": "outer-pipe-markdown-table",
            "evidence_role": "emits",
            "evidence_kind": extension["evidence_kind"],
            "dimension": "rendering",
            "acceptance_predicate": "test-table-rendering",
            "producer_check": "profile_rendering",
            "producer_capability": "profile-rendering-evidence-v1",
            "producer_gate_id": None,
            "consumer_gate_id": "batch-review",
            "fingerprint_binding": "evidence-time",
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }
        changed["obligations"].append(obligation)
        changed["obligations"].sort(key=lambda row: row["obligation_id"])
        audit_plan_contract.validate_plan(changed)
        return changed, obligation

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
            [row["rule_id"] for row in raw_items if row["evidence_role"] == "emits"] +
            [self.registry["s_tier_sampling"]["rule_id"]],
            [row["rule_id"] for row in
             contract.base_obligation_specs(self.registry)])
        self.assertEqual(
            {row["group_id"]
             for row in self.registry["m_tier_source_groups"]},
            {row["source_group"] for row in raw_items})

        # Repeated downstream lookups use this observation's complete owner
        # validation, and copy only the selected atom. A fresh observation
        # must validate anew; neither an explicit input nor corruption hides.
        with mock.patch.object(contract, "_validate_registry", wraps=contract._validate_registry) as validate:
            with contract.registry_observation(REPOSITORY):
                captured = contract.load_registry(REPOSITORY, cache_projection=True)
                before_queries = validate.call_count
                for rule in raw_rules:
                    self.assertEqual(rule, contract.obligation_spec_for_rule(rule)["rule_id"])
                first = contract.obligation_spec_for_rule(raw_rules[0])
                first["rule_id"] = "not-an-owner"
                self.assertEqual(raw_rules[0], contract.obligation_spec_for_rule(raw_rules[0])["rule_id"])
                self.assertEqual(before_queries, validate.call_count)
                with self.assertRaises(ValueError):
                    contract.obligation_spec_for_rule(raw_rules[0], {})
                captured["m_tier_atomic_items"][-1]["dimension"] = "not-registered"
                with self.assertRaisesRegex(ValueError, "base dimension"):
                    contract.obligation_spec_for_rule(raw_rules[0])
            before = validate.call_count
            with contract.registry_observation(REPOSITORY):
                self.assertEqual(raw_rules[0], contract.obligation_spec_for_rule(raw_rules[0])["rule_id"])
            self.assertEqual(before + 1, validate.call_count)

            # Exact bytes, not path/mtime or scope membership, qualify reuse.
            original_read = contract.kblib.read_text
            dependency = audit_plan_contract.AUDIT_PLAN_CONTRACT_PATH
            with contract.registry_observation(REPOSITORY):
                contract.load_registry(REPOSITORY, cache_projection=True)
                before = validate.call_count
                def changed_dependency(path, *args, **kwargs):
                    text = original_read(path, *args, **kwargs)
                    return text + "\n" if str(path).endswith(dependency) else text
                with mock.patch.object(contract.kblib, "read_text", side_effect=changed_dependency):
                    contract.load_registry(REPOSITORY, cache_projection=True)
                self.assertEqual(before + 1, validate.call_count)

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

        changed = copy.deepcopy(self.registry)
        rendering = next(
            row for row in changed["m_consumption_contracts"]
            if row["item_id"] ==
            "m06-triggered-rendering-obligations-applied")
        rendering["selector"]["kernel_extension_point"] = "made-up-extension"
        with self.assertRaisesRegex(ValueError, "admitted exact"):
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
        self.assertEqual("resolved", rendering["resolution"])
        self.assertEqual(
            "profile-extension", rendering["selector"]["owner_kind"])
        self.assertEqual(
            "k12-02-profile-rendering",
            rendering["selector"]["kernel_extension_point"])
        self.assertIsNone(rendering["selector"]["owner_rule_ids"])
        self.assertEqual(
            "one-or-more-all-matching-required",
            rendering["selector"]["match_cardinality"])

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

    def test_plan_closure_requires_emitting_atoms_and_exact_s_sample(self):
        plan, manifest, tiers, selection = self.full_plan()
        result = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        self.assertEqual(selection, result["s_selection"])
        raw_expected = {
            ("M.md", row["rule_id"])
            for row in self.registry["m_tier_atomic_items"] if row["evidence_role"] == "emits"}
        raw_expected.update(
            (page, self.registry["s_tier_sampling"]["rule_id"])
            for page in selection["sample_selected_targets"])
        self.assertEqual(
            raw_expected,
            set(result["obligations_by_target_rule"]))

        incomplete = copy.deepcopy(plan)
        incomplete["obligations"] = [row for row in incomplete["obligations"]
                                     if row["obligation_id"] != "m-0001"]
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
                audit_fingerprint.sources_sha256(PAGE_TEXT)),
            receipt["dependency_fingerprint"])
        self.assertEqual(
            contract.contract_fingerprint(spec, plan, self.registry),
            receipt["contract_fingerprint"])
        expected_fields = set(
            contract.validate_registry(self.registry)["producer"]
            ["variants"]["m-atomic-item"]["instance_fields"])
        self.assertEqual(expected_fields, set(receipt))

        # The immutable obligation supplies the definition; there is no
        # copied dimension/predicate to compare with another copied value.
        forbidden = next(row["forbidden_fields"] for row in
            self.registry["producer_evidence_contract"]["variants"]
            if row["review_variant"] == "m-atomic-item")
        self.assertTrue(set(forbidden).isdisjoint(receipt))
        for field in ("owner_rule_id", "dimension", "due_stage", "acceptance_predicate"):
            with self.subTest(field=field):
                changed_obligation = dict(obligation, **{field: "foreign"})
                with self.assertRaisesRegex(ValueError, field):
                    contract.validate_record_plan_binding(
                        receipt, plan, audit_plan_contract.plan_sha256(plan),
                        changed_obligation, self.registry)
        changed = copy.deepcopy(receipt)
        changed["extra"] = "not allowed"
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_producer_receipt(changed, self.registry)

    def test_direct_consumption_has_exact_plan_edges_without_new_declarations(self):
        plan, manifest, tiers, _ = self.full_plan(s_count=0)
        closure = contract.validate_plan_base_closure(plan, manifest, tiers, self.registry)
        consumed = closure["consumed_obligations_by_target_rule"]
        raw = self.registry["m_tier_atomic_items"]
        consumers = [row for row in raw if row["evidence_role"] == "consumes"]
        self.assertEqual({("M.md", row["rule_id"]) for row in consumers}, set(consumed))
        produced = {row["owner_rule_id"] for row in plan["obligations"]}
        for item in consumers:
            self.assertNotIn(item["rule_id"], produced)
            for field in ("evidence_kind", "producer_check", "producer_capability"):
                self.assertIsNone(item[field])
        by_item = {row["item_id"]: consumed[("M.md", row["rule_id"])] for row in consumers}
        self.assertEqual(by_item["m05-no-required-link-missing"],
                         by_item["m05-no-required-link-ambiguous"])
        rendering = next(row for row in plan["obligations"]
                         if row["owner_rule_id"] == "k12-02-rendering-verification-record")
        self.assertEqual((rendering["obligation_id"],),
                         by_item["m07-rendering-level-or-exception"])
        # The same frozen source is accepted by its original stage consumer;
        # no M producer can counterfeit that source with another declaration.
        for source in ("k12-02-level0-wiki-link-resolution",
                       "k12-02-rendering-verification-record"):
            for mutation in ("absent", "wrong-target", "wrong-stage", "duplicate"):
                changed = copy.deepcopy(plan)
                row = next(row for row in changed["obligations"] if row["owner_rule_id"] == source)
                if mutation == "absent":
                    changed["obligations"].remove(row)
                elif mutation == "wrong-target":
                    row["target"] = "Other.md"
                elif mutation == "wrong-stage":
                    row["due_stage"] = "post-delta"
                else:
                    changed["obligations"].append(dict(row, obligation_id=row["obligation_id"] + "-copy"))
                    changed["obligations"].sort(key=lambda row: row["obligation_id"])
                with self.subTest(source=source, mutation=mutation), self.assertRaises(ValueError):
                    contract.validate_plan_base_closure(changed, manifest, tiers, self.registry)
        changed_registry = copy.deepcopy(self.registry)
        changed_registry["m_tier_atomic_items"][-1]["producer_capability"] = "batch-page-review-attestation-v1"
        with self.assertRaisesRegex(ValueError, "second producer"):
            contract.validate_registry(changed_registry)

    def test_producer_attempt_selector_allows_stale_and_rejects_ambiguity(self):
        plan, manifest, tiers, _selection = self.full_plan(s_count=0)
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        item_spec = self.registry["m_tier_atomic_items"][0]
        spec = contract.obligation_spec_for_rule(
            item_spec["rule_id"], self.registry)
        obligation = closure["obligations_by_target_rule"][
            ("M.md", item_spec["rule_id"])]
        page = self.frozen("M.md")
        receipt = producer.build_review_receipt(
            root=str(REPOSITORY), plan=plan,
            plan_sha256=audit_plan_contract.plan_sha256(plan),
            obligation=obligation, spec=spec, page_snapshot=page,
            reviewer_context_id="review-context",
            reviewer_role="batch-reviewer", verdict="passed",
            statement="the registered M atom is satisfied",
            applicability_disposition="applicable",
            registry=self.registry, identity={})
        result = {
            "root": str(REPOSITORY),
            "current_receipt_catalog": {receipt["receipt_id"]: receipt},
        }
        queue_item = {"id": "B001"}
        plan_sha256 = audit_plan_contract.plan_sha256(plan)
        with mock.patch.object(contract, "validate_producer_receipt",
                               wraps=contract.validate_producer_receipt) as stable:
            self.assertIs(
                receipt, producer.current_review_attempt(
                    result, queue_item, plan, plan_sha256, obligation, spec,
                    page, self.registry))
            stable.assert_called_once()

        changed_text = PAGE_TEXT.replace("Mechanism", "Changed mechanism")
        changed_page = audit_producer_runtime.FrozenPage(
            path="M.md", page_sha256=SHA_C,
            semantic_content_fingerprint=SHA_C,
            snapshot=SimpleNamespace(read_text=lambda: changed_text))
        self.assertIsNone(producer.current_review_attempt(
            result, queue_item, plan, plan_sha256, obligation, spec,
            changed_page, self.registry))

        sibling = copy.deepcopy(receipt)
        sibling["receipt_id"] = "second-current-batch-page-review"
        result["current_receipt_catalog"][sibling["receipt_id"]] = sibling
        with self.assertRaisesRegex(ValueError, "multiple current attempts"):
            producer.current_review_attempt(
                result, queue_item, plan, plan_sha256, obligation, spec,
                page, self.registry)

    def test_producer_attempt_selector_fails_closed_on_invalid_stable_row(self):
        plan, manifest, tiers, _selection = self.full_plan(s_count=0)
        closure = contract.validate_plan_base_closure(
            plan, manifest, tiers, self.registry)
        item_spec = self.registry["m_tier_atomic_items"][0]
        spec = contract.obligation_spec_for_rule(
            item_spec["rule_id"], self.registry)
        obligation = closure["obligations_by_target_rule"][
            ("M.md", item_spec["rule_id"])]
        page = self.frozen("M.md")
        receipt = producer.build_review_receipt(
            root=str(REPOSITORY), plan=plan,
            plan_sha256=audit_plan_contract.plan_sha256(plan),
            obligation=obligation, spec=spec, page_snapshot=page,
            reviewer_context_id="review-context",
            reviewer_role="batch-reviewer", verdict="passed",
            statement="the registered M atom is satisfied",
            applicability_disposition="applicable",
            registry=self.registry, identity={})
        receipt["tool_version"] = "forged"
        result = {"current_receipt_catalog": {
            receipt["receipt_id"]: receipt,
        }}
        with self.assertRaisesRegex(ValueError, "invalid stable attempt"):
            producer.current_review_attempt(
                result, {"id": "B001"}, plan,
                audit_plan_contract.plan_sha256(plan), obligation, spec,
                page, self.registry)

    def test_semantic_records_cover_only_emitting_requirements(self):
        plan, manifest, tiers, _ = self.full_plan(s_count=0)
        closure = contract.validate_plan_base_closure(plan, manifest, tiers, self.registry)
        digest = audit_plan_contract.plan_sha256(plan)
        records = []
        emitting = [row for row in self.registry["m_tier_atomic_items"]
                    if row["evidence_role"] == "emits"]
        shared = self.registry["m_shared_applicability"]
        emitting.sort(key=lambda row: row["item_id"] != shared["condition_item_id"])
        for seq, item in enumerate(emitting, 1):
            spec = contract.obligation_spec_for_rule(item["rule_id"], self.registry)
            condition = item["item_id"] == shared["condition_item_id"]
            dependent = item["applicability"] == shared["dependent_predicate"]
            records.append(producer.build_review_receipt(
                root=str(REPOSITORY), plan=plan, plan_sha256=digest,
                obligation=closure["obligations_by_target_rule"][("M.md", item["rule_id"])],
                spec=spec, page_snapshot=self.frozen("M.md"),
                reviewer_context_id="review-context", reviewer_role="batch-reviewer",
                verdict="passed", statement="The stated semantic criterion is met.",
                applicability_disposition="not-applicable" if condition else "applicable",
                applicability_reason="Failure behavior is present." if condition else None,
                consumed_records=(records[0],) if dependent else (), registry=self.registry,
                identity={}, seq=seq))
        self.assertEqual({row["rule_id"] for row in emitting},
                         {row["rule_id"] for row in records})
        # Body admission shares the source interpretation, not a prior body's
        # verdict. Keep this original owner test, not another whole runtime.
        with mock.patch.object(contract, "_validate_registry", wraps=contract._validate_registry) as validate:
            with contract.registry_observation(REPOSITORY):
                for record in records:
                    self.assertEqual([], contract.current_receipt_errors(record, root=str(REPOSITORY)))
                self.assertEqual(1, validate.call_count)
                corrupt = dict(records[0], dimension="unknown-dimension")
                self.assertTrue(contract.current_receipt_errors(corrupt, root=str(REPOSITORY)))
                self.assertEqual(1, validate.call_count)
            with contract.registry_observation(REPOSITORY):
                self.assertEqual([], contract.current_receipt_errors(records[0], root=str(REPOSITORY)))
            self.assertEqual(2, validate.call_count)

    def test_consumption_contract_inventory_and_profile_rendering_edge(self):
        values = contract.validate_registry(self.registry)
        consumes = {row["item_id"] for row in self.registry["m_tier_atomic_items"]
                    if row["evidence_role"] == "consumes"}
        self.assertEqual(consumes, set(values["m_consumption_by_item_id"]))
        plan, manifest, tiers, _ = self.full_plan(s_count=0)
        item = next(row for row in self.registry["m_tier_atomic_items"]
                    if row["item_id"] == "m06-triggered-rendering-obligations-applied")
        key = ("M.md", item["rule_id"])
        self.assertEqual((), contract.consumption_coverage(plan, ["M.md"], self.registry)[key])
        plan, required = self.with_profile_rendering(plan, "M.md")
        self.assertEqual((required["obligation_id"],),
                         contract.validate_plan_base_closure(plan, manifest, tiers, self.registry)[
                             "consumed_obligations_by_target_rule"][key])
        # Another page's proof never discharges this page. Whether a construct
        # requires a contract remains with the Profile-rendering closure owner.
        required["target"] = "Other.md"
        self.assertEqual((), contract.consumption_coverage(plan, ["M.md"], self.registry)[key])
        held = copy.deepcopy(self.registry)
        row = next(row for row in held["m_consumption_contracts"] if row["item_id"] == item["item_id"])
        row.update(resolution="hold", selector=None, hold_reason="No accepted selector.")
        with self.assertRaisesRegex(ValueError, "HOLD"):
            contract.consumption_coverage(plan, ["M.md"], held)

    def test_common_condition_covers_na_items_and_retains_exact_correction_boundary(self):
        plan, manifest, tiers, _ = self.full_plan(s_count=0)
        closure = contract.validate_plan_base_closure(plan, manifest, tiers, self.registry)
        digest = audit_plan_contract.plan_sha256(plan)
        shared = self.registry["m_shared_applicability"]
        condition = next(row for row in self.registry["m_tier_atomic_items"]
                         if row["item_id"] == shared["condition_item_id"])
        spec = contract.obligation_spec_for_rule(condition["rule_id"], self.registry)
        primary = closure["obligations_by_target_rule"][("M.md", spec["rule_id"])]
        dependent = [row for row in plan["obligations"]
                     if row["applicability"] == shared["dependent_predicate"]]
        common = producer.build_review_receipt(
            root=str(REPOSITORY), plan=plan, plan_sha256=digest, obligation=primary,
            spec=spec, page_snapshot=self.frozen("M.md"), reviewer_context_id="reviewer",
            reviewer_role="batch-reviewer", verdict="passed",
            statement="The page explicitly explains why failure behavior is not applicable.",
            applicability_disposition=shared["condition_covers_dependents_when"],
            registry=self.registry, identity={})
        self.assertEqual(sorted(row["obligation_id"] for row in dependent), common["covered_obligation_ids"])
        catalog = {common["receipt_id"]: common}
        item = {"id": "B001", "state": "open"}
        result = {"root": str(REPOSITORY), "items_by_id": {"B001": item},
                  "current_receipt_catalog": catalog}
        facts = audit_evidence_runtime._EvidenceFacts(result)
        result["_audit_evidence_facts"] = facts
        snapshot = SimpleNamespace(read_text=lambda: PAGE_TEXT)
        with mock.patch.object(facts, "page_artifact", return_value=common["artifact_fingerprint"]), \
                mock.patch.object(facts, "metadata_page", return_value=(snapshot, common["semantic_content_fingerprint"])):
            for obligation in [primary] + dependent:
                resolution = audit_evidence_runtime._required_obligation_resolution(
                    result, item, plan, digest, catalog, obligation, require_current=True)
                self.assertEqual("satisfied", resolution["status"], resolution)
                self.assertEqual(common["receipt_id"], resolution["record"]["receipt_id"])
                # Closed-stage revalidation accepts that same fact, without
                # manufacturing one new record per covered obligation.
                self.assertEqual([], audit_evidence_runtime._batch_page_binding_errors(
                    result, catalog, str(REPOSITORY), plan, digest, obligation, common,
                    require_current=False))
            withdrawn = dict(result, invalidated_evidence_receipt_ids=[common["receipt_id"]])
            for obligation in [primary] + dependent:
                resolution = audit_evidence_runtime._required_obligation_resolution(
                    withdrawn, item, plan, digest, catalog, obligation, require_current=False)
                self.assertNotEqual("satisfied", resolution["status"])
        forged = dict(common, covered_obligation_ids=common["covered_obligation_ids"] + ["m-0001"])
        with self.assertRaisesRegex(ValueError, "covered_obligation_ids"):
            contract.validate_record_plan_binding(forged, plan, digest, primary, self.registry)
        # A dependent cannot add a redundant N/A or independent pass while the
        # already-accepted common fact covers it.
        target = dependent[0]
        target_spec = contract.obligation_spec_for_rule(target["owner_rule_id"], self.registry)
        with self.assertRaisesRegex(ValueError, "already covers"):
            contract.resolve_consumed_evidence(plan, digest, target_spec, "M.md", catalog,
                [common["receipt_id"]], "applicable", self.registry)

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

        result = {
            "root": str(REPOSITORY),
            "_profile_authorized_view": {},
        }
        current_snapshot = SimpleNamespace(read_text=lambda: PAGE_TEXT)
        with mock.patch.object(
                audit_evidence_runtime.metadata_property_state,
                "authorized_profile_projection_rules",
                return_value=(None, {})), mock.patch.object(
                audit_evidence_runtime.metadata_property_state,
                "semantic_page_snapshot",
                return_value=(current_snapshot, SHA_B)), mock.patch.object(
                audit_evidence_runtime,
                "current_consumption_evidence_ids",
                side_effect=AssertionError(
                    "sampled S evidence has no consumption edge")):
            self.assertEqual(
                [], audit_evidence_runtime._batch_page_binding_errors(
                    result, {receipt["receipt_id"]: receipt},
                    str(REPOSITORY), plan,
                    audit_plan_contract.plan_sha256(plan), obligation,
                    receipt))
            for field, expected_error in (
                    ("dependency_fingerprint", "dependency fingerprint"),
                    ("selection_fingerprint", "selection binding")):
                corrupt = copy.deepcopy(receipt)
                corrupt[field] = SHA_C
                errors = audit_evidence_runtime._batch_page_binding_errors(
                    result, {receipt["receipt_id"]: corrupt},
                    str(REPOSITORY), plan,
                    audit_plan_contract.plan_sha256(plan), obligation,
                    corrupt)
                self.assertTrue(any(expected_error in row for row in errors),
                                errors)

    def test_runtime_path_is_dedicated_registered_evidence(self):
        self.assertEqual(
            ".cambium/receipts/batch-page-reviews.jsonl",
            runtime_paths.BATCH_PAGE_REVIEW_RECEIPT_PATH)
        self.assertEqual(
            runtime_paths.EVIDENCE,
            runtime_paths.RUNTIME_OBJECTS[
                "batch-page-review-receipts"].category)

    def test_collection_preserves_individual_publication_and_readback(self):
        # This producer seam starts with an admitted in-memory Plan. No Task,
        # Queue, repository copy, CLI subprocess or E2E fixture is constructed.
        plan, manifest, tiers, _ = self.full_plan(s_count=0)
        closure = contract.validate_plan_base_closure(plan, manifest, tiers, self.registry)
        rules = [item["rule_id"] for item in self.registry["m_tier_atomic_items"]
                 if item["evidence_role"] == "emits" and item["applicability"] == "always"][:3]
        obligations = [closure["obligations_by_target_rule"][("M.md", rule)] for rule in rules]
        answers = [{"obligation_id": row["obligation_id"], "input": {
            "reviewer_context_id": "review-context", "reviewer_role": "reviewer",
            "verdict": "passed", "statement": "This particular semantic criterion is satisfied.",
            "applicability_disposition": "applicable", "applicability_reason": None,
        }} for row in obligations]
        digest = audit_plan_contract.plan_sha256(plan)
        item = {"id": "B001", "manifest": manifest}
        state = {"root": str(REPOSITORY), "current_receipt_catalog": {},
                 "coverage": {"pages": [{"path": path, "tier": tier} for path, tier in tiers.items()]}}
        for failure in (None, "changes-required", "invalid-answer", "readback"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                path = str(Path(directory, "reviews.jsonl"))
                supplied = copy.deepcopy(answers)
                if failure == "changes-required":
                    supplied[1]["input"]["verdict"] = "changes-required"
                elif failure == "invalid-answer":
                    supplied[1]["input"]["verdict"] = "unregistered"
                patch = lambda owner, name, **kw: stack.enter_context(mock.patch.object(owner, name, **kw))
                patch(audit_producer_runtime, "admitted_runtime", return_value=(str(REPOSITORY), state, {}))
                patch(audit_producer_runtime, "open_batch", return_value=(item, {}))
                load = patch(producer, "load_current_plan", return_value=(
                    None, plan, digest, (self.frozen("M.md"),), tiers, self.registry, closure, None))
                patch(producer, "_resolve_current_plan", return_value=(None, plan, digest, None))
                patch(producer, "_require_plan_bytes_current")
                current = patch(audit_producer_runtime, "require_runtime_current", return_value=state)
                pages = patch(audit_producer_runtime, "require_pages_current")
                patch(audit_producer_runtime, "managed_receipt_path", return_value=path)
                patch(audit_producer_runtime, "runtime_lock_metadata", return_value={})
                patch(kblib, "runtime_receipt_identity", return_value={})
                lock = patch(kblib, "runtime_write_lock", side_effect=lambda *a, **k: nullcontext(mock.Mock()))
                patch(kblib, "no_authoritative_write_guard", side_effect=lambda lease: nullcontext())
                exact = producer.require_exact_readback
                seen = []
                def readback(absolute, receipt, registry, **kwargs):
                    seen.append(receipt["receipt_id"])
                    # Exact observed bytes are consumed without a second scan.
                    with mock.patch.object(kblib, "read_receipt_bytes",
                            side_effect=AssertionError("do not rescan observed publication")):
                        result = exact(absolute, receipt, registry, **kwargs)
                    if failure == "readback" and len(seen) == 2:
                        raise ValueError("resulting-state verification failed")
                    return result
                patch(producer, "require_exact_readback", side_effect=readback)
                args = [str(REPOSITORY), "--batch", "B001", "--plan", "plan.yaml", "--page", "M.md", "--apply"]
                for row in supplied:
                    args.extend(("--review", json.dumps(row)))
                output = stack.enter_context(redirect_stdout(io.StringIO()))
                code = producer.main(args)
                results = json.loads(output.getvalue())
                self.assertEqual(0 if failure is None else 1, code, results)
                rows = audit_producer_runtime.read_receipt_records(path)
                expected = 3 if failure is None else 1 if failure == "invalid-answer" else 2
                self.assertEqual(expected, len(rows), results)
                self.assertEqual([row["obligation_id"] for row in obligations[:expected]],
                                 [row["obligation_id"] for row in rows])
                load.assert_called_once()
                attempts = 3 if failure is None else 2
                self.assertEqual(attempts, current.call_count)
                self.assertEqual(attempts, pages.call_count)
                self.assertEqual(attempts, lock.call_count)
                self.assertEqual(expected, len(seen))
                if failure is None:
                    self.assertEqual([], results[-1]["remaining_input_ids"])
                else:
                    self.assertEqual([obligations[2]["obligation_id"]], results[-1]["remaining_input_ids"])
                for row in rows:
                    contract.validate_producer_receipt(row, self.registry)
                if failure == "changes-required":
                    self.assertEqual("fail", rows[1]["result"])
                if failure == "readback":
                    self.assertEqual("unconfirmed", results[-1]["publication"]["record_confirmation"])


if __name__ == "__main__":
    unittest.main()
