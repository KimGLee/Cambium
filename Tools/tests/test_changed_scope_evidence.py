"""Changed-scope evidence owner contract and adjacent consumer seams.

The Kernel registry owns the obligation set. Producer/capability closure,
individual pure checks, generic attempt history, and final reconciliation have
their own primary tests. This file owns only the three current changed-scope
evidence shapes and their exact binding to one frozen AuditPlan row.
"""

import copy
import os
import sys
import types
import unittest
from unittest import mock


TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(TOOLS)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_obligation_projection as obligation_projection
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.audit.changed_scope_evidence_contract as contract
import Tools.execution.audit.changed_scope_runtime_checks as runtime_checks
import Tools.execution.audit.complete_audit_receipt as complete_audit_receipt
import Tools.execution.audit.record_changed_scope_evidence as producer
from Tools.execution.task_runtime.queue_runtime import profile_view
import Tools.execution.evidence.metadata_gate_runtime as metadata_gate_runtime
import Tools.governance.profile.profile_contract as profile_contract
import Tools.knowledge.content.check_links as check_links
import Tools.knowledge.metadata.check_page_contract as check_page_contract
import Tools.knowledge.metadata.check_vocab as check_vocab
import Tools.platform.common.kblib as kblib
from Tools.tests.support.profile_contract_fixture import CurrentProfileContractFixture


def digest(label):
    return kblib.sha256_bytes(label)


class ChangedScopeEvidenceFixtures:

    @classmethod
    def setUpClass(cls):
        cls.registry = contract.load_registry(ROOT)
        cls.control = contract.load_control_registry(ROOT)
        cls.rules = tuple(contract.normalized_base_rules(
            cls.registry, ROOT))
        cls.trace = tuple(producer.producer_trace(
            ROOT, cls.registry, cls.control))

    def row_for_rule(self, rule_id):
        matches = [row for row in self.rules if row["rule_id"] == rule_id]
        self.assertEqual(1, len(matches), rule_id)
        return matches[0]

    def row_for_gate(self, gate_id):
        matches = [row for row in self.rules
                   if row.get("producer_gate_id") == gate_id]
        self.assertEqual(1, len(matches), gate_id)
        return matches[0]

    def trace_for_rule(self, rule_id):
        matches = [row for row in self.trace if row["rule_id"] == rule_id]
        self.assertEqual(1, len(matches), rule_id)
        return matches[0]

    def obligation_for_rule(self, rule_id, target):
        spec = obligation_projection.obligation_spec_for_rule(rule_id, ROOT)
        return {
            "obligation_id": "obligation-%s" % rule_id,
            **obligation_projection.resolve_obligation_definition(
                spec, target),
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }

    def plan_for(self, obligation, *, plan_id="audit-plan-test"):
        return {
            "plan_id": plan_id,
            "task_id": "T-1",
            "batch_id": "B-1",
            "opening_transition_receipt": "open-1",
            "upstream_revision_id": "K-1",
            "active_standards_sha256": digest("standards"),
            "selected_profile_manifest":
                "profiles/test-profile/profile.toml",
            "profile_snapshot_sha256": digest("profile"),
            "profile_contract_fingerprint": digest("profile-contract"),
            "obligations": [obligation],
        }

    def direct_case(self, gate_id, result="pass", source_exit_code=0):
        row = self.row_for_gate(gate_id)
        trace = self.trace_for_rule(row["rule_id"])
        target = "README.md"
        obligation = self.obligation_for_rule(row["rule_id"], target)
        plan = self.plan_for(obligation)
        predicate = self.control[gate_id]
        source = {
            "receipt_id": "raw-%s" % gate_id,
            "tool": predicate["tool"],
            "tool_version": predicate["tool_version"],
            "gate_id": gate_id,
            "check": predicate["check"],
            "target": "page-contract"
                if gate_id == check_page_contract.GATE_ID else target,
            "result": result,
            "details": (
                "pages=1 checked=1 fail=0 candidate=0 mode=advisory"
                if gate_id == check_page_contract.GATE_ID
                else "raw exact Gate result"),
            "checked_at": "2026-08-28T00:00:00Z",
            "invalidated_by": None,
            "task_id": plan["task_id"],
            "upstream_revision_id": plan["upstream_revision_id"],
            "selected_profile_manifest": plan[
                "selected_profile_manifest"],
            "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
            "profile_contract_fingerprint": plan[
                "profile_contract_fingerprint"],
            "profile_load_inputs_sha256": digest("profile-load-inputs"),
            ("compiled_page_contract_sha256"
             if gate_id == check_page_contract.GATE_ID
             else "compiled_vocab_sha256"): digest("compiled-contract"),
        }
        snapshot = kblib.repository_target_snapshot(
            ROOT, target, suffixes=(".md", ".MD"), singly_linked=True)
        frozen = (types.SimpleNamespace(
            path=target,
            page_sha256=snapshot.sha256,
            semantic_content_fingerprint=digest("page"),
            snapshot=snapshot),)
        plan_sha256 = digest("plan")
        record = producer.build_direct_record(
            root=ROOT, plan=plan, plan_sha256=plan_sha256,
            obligation=obligation, row=row, trace=trace,
            registry=self.registry, control_registry=self.control,
            frozen=frozen, source_exit_code=source_exit_code,
            source_receipts=[source])
        return {
            "record": record,
            "plan": plan,
            "plan_sha256": plan_sha256,
            "obligation": obligation,
            "artifact_fingerprint":
                audit_producer_runtime.page_artifact_fingerprint(frozen[0]),
            "frozen": frozen,
        }

    def audit_precursor_case(self):
        rule_id = runtime_checks.GUIDANCE_RULE_ID
        row = self.row_for_rule(rule_id)
        trace = self.trace_for_rule(rule_id)
        obligation = self.obligation_for_rule(
            rule_id, "Progress.guidance_queue")
        plan = self.plan_for(obligation)
        frozen = (types.SimpleNamespace(
            path="Topics/Changed.md",
            page_sha256=digest("page-bytes"),
            semantic_content_fingerprint=digest("page"),
            snapshot=types.SimpleNamespace(
                read_text=lambda: "# Changed\n\nBody.\n")),)
        result = {
            "root": ROOT,
            "progress": {"guidance_queue": [{
                "guidance_id": "G-1",
                "disposition": "apply-to-current-batch",
                "status": "verified",
            }]},
            "coverage": {"pages": [{
                "path": "Topics/Changed.md",
                "coverage_disposition": "required",
                "authoring_status": "drafted",
                "batch": "B-1",
                "next_batch": "B-1",
                "deferred_reason": None,
            }]},
            "queue": {
                "task_id": "T-1",
                "required_queue": [{"id": "B-1", "state": "open"}],
            },
            "progress_sha256": digest("progress"),
            "coverage_sha256": digest("coverage"),
            "queue_sha256": digest("queue"),
        }
        item = {"id": "B-1", "state": "open",
                "manifest": ["Topics/Changed.md"]}
        result["items_by_id"] = {item["id"]: item}
        context = {
            "root": ROOT,
            "result": result,
            "item": item,
            "plan": plan,
            "plan_sha256": digest("plan"),
            "registry": self.registry,
            "control_registry": self.control,
            "obligation": obligation,
            "row": row,
            "trace": trace,
            "frozen": frozen,
        }
        check_result = producer._runtime_check_result(context)
        record = producer.build_audit_producer_record(
            context=context, check_result=check_result)
        return {**context, "record": record}

    def candidate_set_case(self):
        scan = types.SimpleNamespace(
            scan_id="fixture-profile-scan",
            required_for_k12_item_6=False,
            judgment_item_id="fixture-profile-judgment",
            candidate_predicate="fixture candidate boundary",
            verifier_capability_id="fixture-scan-capability",
            script_repo_path=(
                "Tools/execution/task_runtime/candidate_delta_runtime.py"),
            script_absolute_path=os.path.join(
                ROOT,
                "Tools/execution/task_runtime/candidate_delta_runtime.py"),
            config_dependency=None,
        )
        profile = types.SimpleNamespace(
            valid=True,
            manifest_repo_path="profiles/test-profile/profile.toml",
            profile_contract_fingerprint=digest("profile-contract"),
            scan_registry_path="profiles/test-profile/registered-scans.md",
            registered_scans=(scan,),
            judgment_items=(types.SimpleNamespace(
                judgment_item_id=scan.judgment_item_id,
                dimension_id="source_and_currentness",
                evidence_role="triggers"),),
            extension_dimensions=(),
        )
        spec = obligation_projection.profile_registered_scan_spec(
            profile, scan, root=ROOT, registry=self.registry)
        obligation = {
            "obligation_id": "obligation-fixture-profile-scan",
            **obligation_projection.resolve_obligation_definition(spec, "."),
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }
        plan = self.plan_for(
            obligation, plan_id="audit-plan-profile-scan")
        plan["selected_profile_manifest"] = profile.manifest_repo_path
        plan["profile_contract_fingerprint"] = \
            profile.profile_contract_fingerprint
        # This suite owns record acceptance, not the Profile Gate. The real
        # admission and compilation-vs-authorization seam is tested by the
        # Profile owner suites; bind a local admitted input at that boundary.
        from Tools.governance.profile import profile_admission
        evaluation = object()
        admitted = types.SimpleNamespace(
            contract=profile, evaluation=evaluation,
            profile_snapshot_sha256=plan["profile_snapshot_sha256"])
        boundary = mock.patch.object(profile_admission, "admit_profile_manifest",
                                     return_value=(admitted, []))
        boundary.start()
        self.addCleanup(boundary.stop)
        owner_obligation, owner, trace = producer.resolve_obligation(
            ROOT, plan, obligation["obligation_id"], self.registry,
            self.control, evaluation)
        self.assertEqual(obligation, owner_obligation)
        self.assertIs(scan, owner)
        entrypoint = profile_contract.registered_scan_entrypoint(ROOT, scan)
        source = {
            "receipt_id": "raw-profile-scan-summary",
            "scan_id": scan.scan_id,
            "tool": entrypoint.tool,
            "result": "candidate",
            "checked_at": "2026-08-28T00:00:00Z",
            "invalidated_by": None,
        }
        records = [source]
        scan_result = {
            "scan": scan,
            "summary": source,
            "records": records,
            "exit_code": 2,
            "summary_sha256": digest("scan-summary"),
            "receipt_set_sha256": kblib.sha256_bytes(
                kblib.canonical_json_bytes(records)),
            "receipt_count": len(records),
            "command_sha256": digest("scan-command"),
            "invocation_tool": entrypoint.tool,
            "invocation_path": entrypoint.invocation_path,
            "invocation_sha256": digest("scan-invocation"),
            "tool_sha256": digest("scan-tool"),
            "config_sha256": None,
            "python_runtime_sha256": digest("scan-runtime"),
            "execution_input_sha256": digest("scan-input"),
            "repository_snapshot_sha256": digest("repository"),
            "output": "",
        }
        profile_view = {"_contract": profile, "_evaluation": evaluation}
        context = {
            "root": ROOT,
            "result": {
                "root": ROOT,
                "_profile_authorized_view": profile_view,
            },
            "plan": plan,
            "plan_sha256": digest("plan"),
            "registry": self.registry,
            "control_registry": self.control,
            "obligation": obligation,
            "row": scan,
            "trace": trace,
            "profile_view": profile_view,
            "profile_contract": profile,
            "profile_evaluation": evaluation,
            "scan": scan,
        }
        with mock.patch.object(
                metadata_gate_runtime,
                "validate_registered_scan_input_binding",
                return_value=None):
            record = producer.build_candidate_set_record(
                context=context, scan_result=scan_result)
        return {**context, "record": record}


class ChangedScopeEvidenceContractTests(
        ChangedScopeEvidenceFixtures, unittest.TestCase):

    def test_registry_rows_have_one_exact_current_producer_trace(self):
        rows = {row["rule_id"]: row for row in self.rules}
        traces = {row["rule_id"]: row for row in self.trace}
        self.assertEqual(len(self.rules), len(rows))
        self.assertEqual(len(self.trace), len(traces))
        self.assertEqual(set(rows), set(traces))
        for rule_id, row in rows.items():
            with self.subTest(rule_id=rule_id):
                observed = traces[rule_id]
                self.assertEqual("available", observed["status"])
                self.assertEqual(row["producer_check"],
                                 observed["existing_check"])
                self.assertEqual(row["evidence_kind"],
                                 observed["evidence_kind"])

    def test_registered_gate_matrix_builds_exact_dimensionless_evidence(self):
        for gate_id, result, source_exit_code in (
                (check_page_contract.GATE_ID, "candidate", 2),
                (check_vocab.GATE_ID, "pass", 0),
                (check_links.GATE_ID, "pass", 0)):
            with self.subTest(gate_id=gate_id):
                case = self.direct_case(gate_id, result, source_exit_code)
                record = case["record"]
                self.assertEqual(gate_id, record["source_gate_id"])
                self.assertEqual("gate-receipt", record["record_kind"])
                self.assertIsNone(record["dimension"])
                self.assertIsNotNone(case["obligation"]["dimension"])
                self.assertEqual(result, record["result"])

    def test_current_record_kind_matrix_is_closed_and_plan_bound(self):
        direct = self.direct_case(
            check_page_contract.GATE_ID, "candidate", 2)
        precursor = self.audit_precursor_case()
        candidate = self.candidate_set_case()
        cases = (
            ("direct", direct, direct["artifact_fingerprint"], None),
            ("audit-precursor", precursor, None, None),
            ("profile-candidate", candidate, None,
             candidate["profile_evaluation"]),
        )
        for label, case, artifact, profile in cases:
            with self.subTest(kind=label):
                observed = contract.validate_record_for_plan(
                    case["record"], case["plan"], case["plan_sha256"],
                    case["obligation"], self.registry, self.control,
                    root=ROOT, artifact_fingerprint=artifact,
                    evaluation=profile)
                self.assertIs(case["record"], observed)

    def test_record_identity_and_content_drift_matrix_fails_closed(self):
        direct = self.direct_case(check_vocab.GATE_ID)
        precursor = self.audit_precursor_case()
        candidate = self.candidate_set_case()

        forged_direct = copy.deepcopy(direct["record"])
        forged_direct["dimension"] = "structure_and_links"
        forged_precursor = copy.deepcopy(precursor["record"])
        forged_precursor["check_owner_tool"] = "nearby-check-owner"
        forged_candidate = copy.deepcopy(candidate["record"])
        forged_candidate["source_receipts"][0]["scan_id"] = "other-scan"
        forged_candidate["source_receipt_set_sha256"] = kblib.sha256_bytes(
            kblib.canonical_json_bytes(forged_candidate["source_receipts"]))

        cases = (
            ("direct-dimension", forged_direct,
             lambda value: contract.validate_direct_record(
                 value, self.registry, self.control, ROOT)),
            ("precursor-owner", forged_precursor,
             lambda value: contract.validate_audit_producer_record(
                 value, self.registry, self.control, ROOT)),
            ("candidate-source", forged_candidate,
             lambda value: contract.validate_candidate_set_record(
                 value, self.registry, ROOT,
                 candidate["profile_evaluation"])),
        )
        for label, record, validate in cases:
            with self.subTest(case=label), self.assertRaises(
                    contract.ChangedScopeEvidenceContractError):
                validate(record)

    def test_frozen_plan_drift_is_rejected_for_every_record_kind(self):
        direct = self.direct_case(check_vocab.GATE_ID)
        precursor = self.audit_precursor_case()
        candidate = self.candidate_set_case()
        cases = (
            ("direct", direct, direct["artifact_fingerprint"], None),
            ("audit-precursor", precursor, None, None),
            ("profile-candidate", candidate, None,
             candidate["profile_evaluation"]),
        )
        for label, case, artifact, profile in cases:
            changed = copy.deepcopy(case["obligation"])
            changed["acceptance_predicate"] = "invented-weaker-predicate"
            with self.subTest(kind=label), self.assertRaises(
                    contract.ChangedScopeEvidenceContractError):
                contract.validate_record_for_plan(
                    case["record"], case["plan"], case["plan_sha256"],
                    changed, self.registry, self.control, root=ROOT,
                    artifact_fingerprint=artifact, evaluation=profile)

    def test_gate_adapter_selects_one_scoped_registered_gate(self):
        case = self.direct_case(check_vocab.GATE_ID)
        trace = self.trace_for_rule(case["obligation"]["owner_rule_id"])
        command = producer.gate_command(
            ROOT, case["plan"], case["obligation"]["target"], trace)
        self.assertEqual(
            case["obligation"]["target"],
            command[command.index("--scope") + 1])
        self.assertIn("--json", command)
        self.assertNotIn("--receipts", command)

        expected = case["record"]["source_receipts"]
        sibling = copy.deepcopy(expected[0])
        sibling.update({
            "receipt_id": "raw-priority-distribution",
            "gate_id": "priority-quota-distribution",
            "check": "priority-quota-distribution",
        })
        exit_code, selected = producer.select_source_gate_receipts(
            expected + [sibling], check_vocab.GATE_ID)
        self.assertEqual(0, exit_code)
        self.assertEqual(expected, selected)
        with self.assertRaisesRegex(
                producer.ChangedScopeProducerError,
                "no receipt for Gate frontmatter-vocabulary"):
            producer.select_source_gate_receipts(
                [sibling], check_vocab.GATE_ID)


class ChangedScopeEvidenceIntegrationTests(
        ChangedScopeEvidenceFixtures, unittest.TestCase):

    def test_current_record_kinds_cross_registered_consumer_boundaries(self):
        direct = self.direct_case(
            check_page_contract.GATE_ID, "candidate", 2)
        self.assertEqual([], audit_evidence_runtime._direct_binding_errors(
            ROOT, direct["plan"], direct["plan_sha256"],
            direct["obligation"], direct["record"]))

        precursor = self.audit_precursor_case()
        catalog = {precursor["record"]["receipt_id"]: precursor["record"]}
        precursor["result"]["current_receipt_catalog"] = catalog
        observed = complete_audit_receipt._producer_evidence(
            ROOT, precursor["result"],
            precursor["record"]["receipt_id"], precursor["plan"],
            precursor["plan_sha256"], precursor["obligation"],
            precursor["frozen"])
        self.assertIs(precursor["record"], observed)

        candidate = self.candidate_set_case()
        with mock.patch.object(
                metadata_gate_runtime,
                "validate_registered_scan_input_binding",
                return_value=None):
            self.assertEqual([], audit_evidence_runtime._direct_binding_errors(
                ROOT, candidate["plan"], candidate["plan_sha256"],
                candidate["obligation"], candidate["record"],
                candidate["result"]))

    def current_input_case(self, rule_id):
        """Bind an isolated real page and Profile without replaying a task."""
        fixture = CurrentProfileContractFixture(self)
        root = str(fixture.root)
        target = "Topics/Changed.md"
        page = fixture.root / target
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# Changed\n\nBody.\n", encoding="utf-8")
        view, errors = profile_view.profile_load_authorized_view(
            root, fixture.manifest.relative_to(fixture.root).as_posix())
        self.assertEqual([], errors)
        item = {"id": "B-1", "state": "open", "manifest": [target]}
        obligation = self.obligation_for_rule(
            rule_id, item["id"] if rule_id == runtime_checks.TASK_CONTRACT_RULE_ID
            else target)
        plan = self.plan_for(obligation)
        plan.update({field: view[field]
                     for field in profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS
                     if field in plan})
        result = {
            "root": root,
            "_profile_authorized_view": view,
            "items_by_id": {item["id"]: item},
            "current_receipt_catalog": {},
            "progress": {"contract": {}},
            "coverage": {"pages": [{
                "path": target, "coverage_disposition": "required",
                "authoring_status": "drafted", "batch": item["id"],
                "next_batch": item["id"], "deferred_reason": None,
            }]},
            "queue": {
                "task_id": plan["task_id"], "queue_revision": 1,
                "state_revision": 1, "required_queue": [item],
            },
        }
        self.refresh_runtime_fingerprints(result)
        frozen = audit_producer_runtime.freeze_manifest_pages(root, result, item)
        return {
            "root": root, "result": result, "item": item,
            "plan": plan, "plan_sha256": digest("plan"),
            "obligation": obligation, "frozen": frozen,
            "registry": self.registry, "control_registry": self.control,
            "row": self.row_for_rule(rule_id),
            "trace": self.trace_for_rule(rule_id), "fixture": fixture,
        }

    @staticmethod
    def refresh_runtime_fingerprints(result):
        for name in ("progress", "coverage", "queue"):
            result[name + "_sha256"] = kblib.sha256_bytes(
                kblib.canonical_json_bytes(result[name]))

    def assert_input_change_allows_successor(self, case, change_input,
                                           changed_binding_field):
        """Exercise one append-only producer/completer/consumer checkpoint."""
        result = case["result"]
        catalog = result["current_receipt_catalog"]
        plan, plan_sha256, obligation = (
            case["plan"], case["plan_sha256"], case["obligation"])

        def current_final():
            return complete_audit_receipt.current_audit_receipt_attempt(
                result, plan, plan_sha256, obligation, case["frozen"],
                case["root"])

        def resolution():
            return audit_evidence_runtime._required_obligation_resolution(
                result, case["item"], plan, plan_sha256, catalog, obligation,
                require_current=True)

        def precursor(seq):
            record = producer.build_audit_producer_record(
                context=case, check_result=producer._runtime_check_result(case),
                seq=seq)
            catalog[record["receipt_id"]] = record
            return record

        def finalize(record, seq):
            evidence = complete_audit_receipt._producer_evidence(
                case["root"], result, record["receipt_id"], plan,
                plan_sha256, obligation, case["frozen"])
            completed = complete_audit_receipt.build_audit_receipt(
                plan=plan, plan_sha256=plan_sha256,
                obligation=obligation, evidence=evidence, seq=seq)
            catalog[completed["receipt_id"]] = completed
            return completed

        old = precursor(1)
        old_final = finalize(old, 1)
        before_records = kblib.canonical_json_bytes([old, old_final])
        before_plan = kblib.canonical_json_bytes(plan)
        page_artifact = audit_producer_runtime.page_artifact_fingerprint(
            case["frozen"][0])
        self.assertIs(old, producer.existing_audit_producer_record(case))
        self.assertIs(old_final, current_final())
        self.assertEqual("satisfied", resolution()["status"])

        change_input()
        self.assertIsNone(producer.existing_audit_producer_record(case))
        stale_resolution = resolution()
        self.assertEqual("missing", stale_resolution["status"])
        self.assertEqual({"stale"}, {
            attempt["state"] for attempt in stale_resolution["attempts"]})
        # This is the regression: a stale final must not reserve completion.
        self.assertIsNone(current_final())
        with self.assertRaises(audit_producer_runtime.AuditProducerError):
            complete_audit_receipt._producer_evidence(
                case["root"], result, old["receipt_id"], plan,
                plan_sha256, obligation, case["frozen"])

        new = precursor(2)
        self.assertEqual(old["artifact_fingerprint"], new["artifact_fingerprint"])
        self.assertEqual(old["check_result"], new["check_result"])
        self.assertNotEqual(old["dependency_fingerprint"],
                            new["dependency_fingerprint"])
        for field in old["input_binding"]:
            assertion = (self.assertNotEqual if field == changed_binding_field
                         else self.assertEqual)
            assertion(old["input_binding"][field], new["input_binding"][field])
        self.assertIs(new, producer.existing_audit_producer_record(case))
        ready = resolution()
        self.assertEqual("ready-for-completion", ready["status"])
        self.assertIs(new, ready["record"])
        self.assertIsNone(current_final())

        new_final = finalize(new, 2)
        for _ in range(2):
            self.assertIs(new, producer.existing_audit_producer_record(case))
            self.assertIs(new_final, current_final())
            satisfied = resolution()
            self.assertEqual("satisfied", satisfied["status"])
            self.assertIs(new_final, satisfied["record"])
        self.assertEqual(4, len(catalog))
        self.assertEqual(before_records,
                         kblib.canonical_json_bytes([old, old_final]))
        self.assertEqual(before_plan, kblib.canonical_json_bytes(plan))
        current_pages = audit_producer_runtime.freeze_manifest_pages(
            case["root"], result, case["item"])
        self.assertEqual(page_artifact,
                         audit_producer_runtime.page_artifact_fingerprint(
                             current_pages[0]))

    def test_repository_change_retries_batch_target_without_artifact_drift(self):
        # Card delivery and Read Set parsing have their own owner tests. Keep
        # those inputs valid while exercising their real changed-scope wrapper.
        with mock.patch.object(
                runtime_checks.card_activation, "build_activation_context",
                return_value={"activation_protocol": "current"}), \
                mock.patch.object(
                    runtime_checks.card_activation, "activation_context_errors",
                    return_value=[]), \
                mock.patch.object(
                    runtime_checks, "live_read_set_load_findings",
                    return_value=([], [])):
            case = self.current_input_case(runtime_checks.TASK_CONTRACT_RULE_ID)
            dependency = case["fixture"].root / "Topics/Dependency.md"
            dependency.write_text("# Dependency\n\nBefore.\n", encoding="utf-8")
            self.assert_input_change_allows_successor(
                case, lambda: dependency.write_text(
                    "# Dependency\n\nAfter.\n", encoding="utf-8"),
                "repository_snapshot_sha256")

    def test_runtime_change_retries_page_target_without_artifact_drift(self):
        case = self.current_input_case(runtime_checks.COVERAGE_RULE_ID)

        def change_routing_inputs():
            result = case["result"]
            result["coverage"]["pages"][0]["authoring_status"] = "reviewed"
            result["queue"]["queue_revision"] += 1
            self.refresh_runtime_fingerprints(result)

        self.assert_input_change_allows_successor(
            case, change_routing_inputs, "runtime_input_sha256")


if __name__ == "__main__":
    unittest.main()
