"""Owner tests for the current AuditPlan evidence reconciliation boundary.

Producer record shapes, AuditPlan loading, catalog filtering and terminal
consumption have their own primary tests. This owner covers whole-obligation
currentness, legal retry/confirmation, completion admission, reconciliation,
and the adjacent stage to Batch Review hand-off without runtime replay.
"""

import copy
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]

import Tools.execution.audit.audit_evidence_runtime as runtime  # noqa: E402
import Tools.execution.audit.audit_obligation_projection as projection  # noqa: E402
import Tools.execution.audit.audit_plan_contract as plan_contract  # noqa: E402
import Tools.execution.audit.audit_producer_runtime as producer_runtime  # noqa: E402
import Tools.execution.audit.audit_fingerprint as receipt_contract  # noqa: E402
import Tools.execution.audit.batch_review_receipt_contract as wrapper_contract
import Tools.execution.audit.record_substantive_review as review_producer  # noqa: E402
import Tools.execution.audit.substantive_review_contract as review_contract  # noqa: E402
from Tools.execution.task_runtime.queue_runtime import profile_view
import Tools.platform.common.kblib as kblib  # noqa: E402
from Tools.tests.support.profile_fixture import (  # noqa: E402
    FIXTURE_UPSTREAM_REVISION,
)
from Tools.tests.support.profile_contract_fixture import (  # noqa: E402
    CurrentProfileContractFixture,
)


def digest(label):
    return kblib.sha256_bytes(label.encode("utf-8"))


class CurrentEvidenceCheckpoint:
    """Build one legal current-contract checkpoint without runtime replay."""

    @classmethod
    def setUpClass(cls):
        target = "README.md"
        text = (REPOSITORY / target).read_text(encoding="utf-8")
        snapshot = SimpleNamespace(read_text=lambda: text)
        frozen = (producer_runtime.FrozenPage(
            target,
            kblib.sha256_bytes(text.encode("utf-8")),
            digest("semantic-content"),
            snapshot,
        ),)

        spec = projection.obligation_spec_for_rule(
            "k12-12-substantive-correctness-review", REPOSITORY)
        obligation = projection.required_obligation(
            projection.resolve_obligation_definition(
                spec, target, trigger="needs_rereview"))
        plan = {
            "schema_version": plan_contract.load_contract(
                REPOSITORY)["schema_version"],
            "plan_id": "audit-plan-current-contract",
            "task_id": "task-current-contract",
            "batch_id": "B001",
            "generated_at": "2026-08-28T00:00:00Z",
            "queue_revision": 3,
            "queue_state_revision": 5,
            "required_queue_sha256": digest("required-queue"),
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": digest("active-standards"),
            "selected_profile_manifest": "profiles/test/profile.toml",
            "profile_snapshot_sha256": digest("profile"),
            "profile_contract_fingerprint": digest("profile-contract"),
            "opening_transition_receipt": "queue-open-current",
            "artifact_snapshot_sha256": digest("artifact-snapshot"),
            "contract_snapshot_sha256": digest("pending-contract"),
            "accepted_baseline_sha256": digest("accepted-baseline"),
            "obligations": [obligation],
        }
        plan["contract_snapshot_sha256"] = \
            plan_contract.plan_contract_snapshot_sha256(plan)
        plan_contract.validate_plan(plan)
        plan_sha256 = plan_contract.plan_sha256(plan)

        review = review_producer.build_review_receipt(
            root=str(REPOSITORY), result={}, plan=plan,
            plan_sha256=plan_sha256, obligation=obligation,
            page=target, frozen=frozen,
            authoring_context_id="author-context",
            reviewer_context_id="reviewer-context",
            reviewer_role="reviewer", round_number=1,
            verdict="passed", findings=[],
            statement="current content passes substantive review")
        review_contract.validate_review_receipt(review)

        cls.base_plan = plan
        cls.base_plan_sha256 = plan_sha256
        cls.base_obligation = obligation
        cls.base_review = review
        cls.base_item = {
            "id": "B001",
            "state": "open",
            "manifest": [target],
        }

    def setUp(self):
        self.plan = copy.deepcopy(self.base_plan)
        self.plan_sha256 = self.base_plan_sha256
        self.obligation = copy.deepcopy(self.base_obligation)
        self.review = copy.deepcopy(self.base_review)
        self.item = copy.deepcopy(self.base_item)
        self.catalog = {
            self.review["receipt_id"]: self.review,
        }
        self.result = {
            "root": str(REPOSITORY),
            "items_by_id": {self.item["id"]: self.item},
            "current_receipt_catalog": self.catalog,
            "receipt_catalog": {},
        }

    def resolution(self, *, catalog=None, obligation=None,
                   require_current=True):
        return runtime._required_obligation_resolution(
            self.result, self.item, self.plan, self.plan_sha256,
            self.catalog if catalog is None else catalog,
            self.obligation if obligation is None else obligation,
            require_current=require_current)

    @staticmethod
    def copy_with_id(record, receipt_id, *, invalidated_by=None):
        duplicate = copy.deepcopy(record)
        duplicate["receipt_id"] = receipt_id
        duplicate["invalidated_by"] = invalidated_by
        return duplicate

    def bind_review(self, closure):
        """Bind one real-shape wrapper, without replaying a batch."""
        from Tools.execution.task_runtime.queue_runtime import review as queue_review
        self.catalog["activation"] = {
            "receipt_id": "activation", "tool": queue_review.TOOL,
            "tool_version": queue_review.TOOL_VERSION, "check": queue_review.GATE_CHECK,
            "gate_id": "required-queue-admission", "queue_check_mode": "require-ready:B001",
            "target": queue_review.QUEUE_PATH, "task_id": self.plan["task_id"],
            "activation_protocol": queue_review.card_activation.ACTIVATION_PROTOCOL,
            "result": "pass", "invalidated_by": None,
            "review_requirement_set_sha256": digest("requirements"),
        }
        wrapper = {
            "receipt_id": "wrapper", "receipt_type_id": wrapper_contract.RECEIPT_TYPE_ID,
            "tool": wrapper_contract.PRODUCER_TOOL,
            "tool_version": wrapper_contract.PRODUCER_TOOL_VERSION,
            "check": wrapper_contract.PRODUCER_CHECK,
            "gate_id": wrapper_contract.GATE_ID, "target": self.item["id"],
            "batch_id": self.item["id"], "result": "pass", "invalidated_by": None,
            "details": "reviewed", "checked_at": self.plan["generated_at"],
            "actor_role": "integrator", "attestation_statement": "approved",
            "activation_receipt_id": "activation", "delta_path": "Delta.md",
            "delta_sha256": digest("delta"), "delta_page_receipt_ids": [],
            "review_requirement_set_sha256": digest("requirements"),
            **wrapper_contract.judgment_binding(()),
            **{key: self.plan[key] for key in (
                "task_id", "upstream_revision_id", "selected_profile_manifest")},
            **closure,
        }
        self.assertEqual([], wrapper_contract.current_receipt_errors(wrapper))
        self.catalog["wrapper"] = wrapper
        self.item.update(state="merge-ready", batch_receipts=["wrapper"],
                         activation_receipt="activation")
        return wrapper


    def review_record(self, identity, *, prior=None, blocking=False):
        record = self.copy_with_id(self.review, identity)
        if blocking:
            record.update({"result": "fail", "verdict": "changes-required",
                           "findings": [{"finding_id": "F1", "severity": "major",
                               "statement": "A qualification is missing",
                               "status": "open", "round_1_finding_id": None}]})
        if prior is not None:
            record.update({"round": 2, "round_1_receipt_id": prior["receipt_id"],
                           "findings": [{**row, "finding_id": "confirm-" + row["finding_id"],
                               "status": "closed", "round_1_finding_id": row["finding_id"]}
                               for row in prior["findings"]]})
        review_contract.validate_review_receipt(record)
        if prior is not None:
            review_contract.validate_review_pair(prior, record)
        return record


class AuditEvidenceReconciliationContractTests(CurrentEvidenceCheckpoint,
                                                unittest.TestCase):

    def test_direct_close_member_selection_uses_current_after_image_not_wrapper_history(self):
        from Tools.tests.fixtures.contract import post_delta_objects as objects
        rows = kblib.load_yaml_file(REPOSITORY /
            "kernel/K12 Quality Assurance/batch-close-closed-list.yaml")["members"]
        stage = objects.plan_stage(rows)
        obligation = stage["obligations"][0]
        old = objects.producer_evidence(stage, obligation, 1)
        after = digest("new-after-image")
        current = dict(old, receipt_id="current-member", merged_snapshot_sha256=after,
                       artifact_fingerprint=after)

        def resolve(records, invalidated=()):
            catalog = {record["receipt_id"]: record for record in records}
            view = runtime.evidence_evaluation({
                "root": str(REPOSITORY), "current_receipt_catalog": catalog,
                "receipt_catalog": catalog, "invalidated_evidence_receipt_ids": invalidated,
                "_profile_authorized_view": {"_contract": objects.profile_binding()}})
            with mock.patch.object(kblib, "repository_snapshot_sha256", return_value=after):
                return runtime._required_obligation_resolution(
                    view, {"id": "B1", "state": "merge-ready"}, stage["plan"],
                    stage["audit_plan_sha256"], catalog, obligation, require_current=True)

        selected = resolve([old, current])
        self.assertEqual("satisfied", selected["status"])
        self.assertEqual(current, selected["record"])
        self.assertEqual("missing", resolve([old])["status"])
        self.assertEqual("missing", resolve([current], [current["receipt_id"]])["status"])
        duplicate = dict(current, receipt_id="conflicting-member")
        self.assertEqual("ambiguous", resolve([current, duplicate])["status"])
        damaged = dict(current, contract_fingerprint=digest("foreign-contract"))
        self.assertEqual("invalid", resolve([damaged])["status"])

    def test_withdrawn_l_review_preserves_rounds_and_cannot_restart(self):
        first = self.review_record("review-first", blocking=True)
        second = self.review_record("review-confirmed", prior=first)
        for withdrawn in (first, second, self.review):
            with self.subTest(round=withdrawn["round"], verdict=withdrawn["verdict"]):
                history = {row["receipt_id"]: row for row in (first, second, self.review)}
                self.result["receipt_catalog"] = history
                self.result["evidence_invalidation_view"] = {
                    "affected": {withdrawn["receipt_id"]: ("correction",)}}
                self.result["invalidated_evidence_receipt_ids"] = [withdrawn["receipt_id"]]
                self.catalog.clear()
                self.assertEqual("escalated", self.resolution()["status"])
                with self.assertRaisesRegex(runtime.AuditEvidenceError, "escalated"):
                    runtime.require_substantive_review_attempt(
                        self.result, self.item, self.plan, self.plan_sha256,
                        self.obligation, round_number=1)

    def test_unreconciled_findings_cannot_be_hidden_by_a_new_first_round(self):
        first = self.review_record("review-first", blocking=True)
        first["artifact_fingerprint"] = digest("before-correction")
        restarted = self.review_record("review-restarted")
        self.catalog.clear()
        self.catalog[first["receipt_id"]] = first
        self.assertEqual("needs-confirmation", self.resolution()["status"])
        self.catalog[restarted["receipt_id"]] = restarted
        self.assertEqual("invalid", self.resolution()["status"])

    def test_confirmation_cannot_be_restarted_after_its_after_image_changes(self):
        first = self.review_record("review-first", blocking=True)
        second = self.review_record("review-confirmed", prior=first)
        for record in (first, second):
            record["artifact_fingerprint"] = digest("previous-image")
        restarted = self.review_record("review-restarted")
        self.catalog.clear()
        self.catalog.update({row["receipt_id"]: row for row in (first, second)})
        self.assertEqual("escalated", self.resolution()["status"])
        self.catalog[restarted["receipt_id"]] = restarted
        self.assertEqual("invalid", self.resolution()["status"])

    def test_public_producer_admission_uses_the_resolved_review_lifecycle(self):
        self.catalog.clear()
        admit = lambda number, reference=None: runtime.require_substantive_review_attempt(
            self.result, self.item, self.plan, self.plan_sha256, self.obligation,
            round_number=number, round_1_receipt_id=reference)
        self.assertIsNone(admit(1))
        first = self.review_record("review-first", blocking=True)
        self.catalog[first["receipt_id"]] = first
        with self.assertRaisesRegex(ValueError, "needs-correction"):
            admit(2, first["receipt_id"])
        first["artifact_fingerprint"] = digest("before-correction")
        self.assertIs(first, admit(2, first["receipt_id"]))
        for number, reference in ((1, None), (2, "different-first")):
            with self.subTest(number=number, reference=reference):
                with self.assertRaisesRegex(ValueError, "needs-confirmation"):
                    admit(number, reference)
        second = self.review_record("review-confirmed", prior=first)
        self.catalog[second["receipt_id"]] = second
        with self.assertRaisesRegex(ValueError, "satisfied"):
            admit(1)
        second["artifact_fingerprint"] = digest("after-second-changed")
        with self.assertRaisesRegex(ValueError, "escalated"):
            admit(2, first["receipt_id"])

    def test_direct_acceptance_requires_unique_review_and_complete_pair(self):
        first = self.review_record("review-first", blocking=True)
        first["artifact_fingerprint"] = digest("before-correction")
        second = self.review_record("review-confirmed", prior=first)
        wrong_ref = self.copy_with_id(second, "wrong-ref")
        wrong_ref["round_1_receipt_id"] = "absent-first"
        duplicate = self.copy_with_id(self.review, "another-current-review")
        cases = (
            ([self.review], self.review, None),
            ([self.review, duplicate], self.review, "ambiguous"),
            ([second], second, "invalid"),
            ([first, wrong_ref], wrong_ref, "invalid"),
            ([first, second], second, None),
        )
        for records, selected, expected_error in cases:
            with self.subTest(records=[row["receipt_id"] for row in records]):
                self.catalog.clear()
                self.catalog.update({row["receipt_id"]: row for row in records})
                resolution = self.resolution()
                self.assertEqual(expected_error or "satisfied", resolution["status"], resolution)
                if expected_error is None:
                    self.assertEqual(selected, resolution["record"])


    def test_currentness_uses_kernel_artifact_not_raw_reviewed_metadata_bytes(self):
        original = (REPOSITORY / self.obligation["target"]).read_text()
        after = "---\nreviewed: 2026-09-06\n---\n" + original
        before_artifact = producer_runtime.page_artifact_fingerprint(
            producer_runtime.FrozenPage(self.obligation["target"], digest(original),
                digest("semantic"), SimpleNamespace(read_text=lambda: original)))
        after_artifact = producer_runtime.page_artifact_fingerprint(
            producer_runtime.FrozenPage(self.obligation["target"], digest(after),
                digest("semantic"), SimpleNamespace(read_text=lambda: after)))
        self.assertEqual(before_artifact, after_artifact)
        self.assertNotEqual(digest(original), digest(after))
        with mock.patch.object(runtime, "_current_page_artifact_fingerprint",
                               return_value=after_artifact):
            with self.assertRaisesRegex(ValueError, "satisfied"):
                runtime.require_substantive_review_attempt(
                    self.result, self.item, self.plan, self.plan_sha256,
                    self.obligation, round_number=1)
            resolution = self.resolution()
            self.assertEqual("satisfied", resolution["status"], resolution)
            self.assertEqual(self.review, resolution["record"])

    def test_invalid_stable_precursor_is_not_reclassified_as_stale(self):
        self.review["tool_version"] = "forged"
        self.review["artifact_fingerprint"] = digest("obsolete-input")
        self.assertEqual("invalid", self.resolution()["status"])

    def test_evaluation_reuses_facts_without_caching_authority(self):
        counts = []
        outcomes = []
        for enabled in (False, True):
            result = {**self.result, "_audit_evidence_facts":
                      runtime._EvidenceFacts(self.result, enabled=enabled)}
            with mock.patch.object(review_contract, "load_contract",
                                   wraps=review_contract.load_contract) as load, \
                    mock.patch.object(review_contract, "validate_review_receipt",
                                      wraps=review_contract.validate_review_receipt) as validate, \
                    mock.patch.object(runtime, "_current_page_artifact_fingerprint",
                                      wraps=runtime._current_page_artifact_fingerprint) as artifact, \
                    mock.patch.object(review_contract, "_validate_contract",
                                      wraps=review_contract._validate_contract) as full_validation:
                outcomes.append(runtime._required_obligation_resolution(
                    result, self.item, self.plan, self.plan_sha256,
                    self.catalog, self.obligation, require_current=True))
                counts.append((load.call_count, validate.call_count,
                               artifact.call_count, full_validation.call_count))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual("satisfied", outcomes[1]["status"])
        self.assertEqual((1, 1, 1, 1), counts[1])
        self.assertTrue(all(old > new for old, new in zip(*counts)))
        self.assertNotIn("_audit_evidence_facts", self.result)

        # Recursive M dependency consumers and the surrounding stage can
        # ask for one obligation in the same explicit read-only observation.
        # The selected result is private, and a new catalog, live/frozen
        # mode or observation must still perform its own resolution.
        with mock.patch.object(
                runtime, "_required_obligation_resolution_unchecked",
                wraps=runtime._required_obligation_resolution_unchecked) as resolve:
            with runtime.evidence_observation(self.result) as observed:
                def query(catalog=self.catalog, *, require_current=True):
                    return runtime._required_obligation_resolution(
                        observed, self.item, self.plan, self.plan_sha256,
                        catalog, self.obligation,
                        require_current=require_current)

                selected = query()
                selected["attempts"].clear()
                self.assertEqual(outcomes[1], query())
                self.assertEqual(1, resolve.call_count)
                frozen = runtime._FrozenEvidenceView(self.result, self.catalog, [
                    runtime._reconciliation_row(self.result, self.plan,
                                                self.obligation, outcomes[1])])
                self.assertEqual("satisfied", query(frozen, require_current=False)["status"])
                self.assertEqual(2, resolve.call_count)
                candidate = self.copy_with_id(self.review, "competing-current-audit")
                replacement = {**self.catalog, candidate["receipt_id"]: candidate}
                self.assertEqual("ambiguous", query(replacement)["status"])
                self.assertEqual(3, resolve.call_count)
            with runtime.evidence_observation(self.result) as observed:
                self.assertEqual(outcomes[1], query())
            self.assertEqual(4, resolve.call_count)
        self.assertNotIn("_audit_stage_resolutions", self.result)

        # New public evaluations must observe changed bytes, even under the
        # same Receipt ID. A coherent but false Sources/dependency pair must
        # not be accepted merely because those two stored fields agree.
        self.review["dependency_fingerprint"] = digest("invented-sources")
        self.review["sources_sha256"] = digest("invented-sources")
        self.assertNotEqual("satisfied", self.resolution()["status"])

    def test_catalog_index_cost_tracks_unique_inputs_not_obligation_count(self):
        class ObservedCatalog(dict):
            scans = 0
            visited = 0
            def items(self):
                self.scans += 1
                for entry in super().items():
                    self.visited += 1
                    yield entry
        for count in (1, 8, 32):
            with self.subTest(obligations=count):
                catalog = ObservedCatalog({
                    "R%d" % i: {"receipt_id": "R%d" % i,
                                "plan_id": "P", "obligation_id": "O%d" % i}
                    for i in range(count)})
                outcomes = []
                for enabled in (False, True):
                    catalog.scans = catalog.visited = 0
                    facts = runtime._EvidenceFacts(self.result, enabled=enabled)
                    outcomes.append([facts.records(catalog, "P", "O%d" % i)
                                     for _ in range(2) for i in range(count)])
                    self.assertEqual(1 if enabled else 2 * count, catalog.scans)
                    self.assertEqual(count if enabled else 2 * count * count, catalog.visited)
                self.assertEqual(outcomes[0], outcomes[1])
                replacement = ObservedCatalog({**catalog,
                    "new": {"receipt_id": "new", "plan_id": "P", "obligation_id": "O0"}})
                self.assertEqual(2, len(facts.records(replacement, "P", "O0")))
                self.assertEqual(1, replacement.scans)

    def test_current_typed_chain_resolves_to_one_reconciliation_row(self):
        resolution = self.resolution()
        row = runtime._reconciliation_row(
            self.result, self.plan, self.obligation, resolution)

        self.assertEqual(review_contract.RECEIPT_TYPE_ID,
                         self.review["receipt_type_id"])
        self.assertEqual("satisfied", resolution["status"])
        self.assertEqual(self.review["receipt_id"],
                         resolution["record"]["receipt_id"])
        self.assertEqual(self.review["receipt_id"],
                         row["selected_evidence_ref"])
        self.assertEqual(
            [self.review["receipt_id"]],
            row["produced_evidence_refs"])
        self.assertFalse(row["unresolved"])

    def test_resolution_status_matrix_uses_current_typed_attempts(self):
        duplicate_review = self.copy_with_id(
            self.review, "audit-record_substantive_review-duplicate-0001")
        misbound_review = self.copy_with_id(
            self.review, "audit-record_substantive_review-misbound-0001")
        misbound_review["audit_plan_sha256"] = digest("different-plan")
        cases = (
            ("empty", {}, "missing"),
            ("complete", self.catalog, "satisfied"),
            ("two-terminals", {
                **self.catalog, duplicate_review["receipt_id"]: duplicate_review,
            }, "ambiguous"),
            ("misbound-terminal", {
                self.review["receipt_id"]: self.review,
                misbound_review["receipt_id"]: misbound_review,
            }, "invalid"),
        )

        for label, catalog, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(
                    expected,
                    self.resolution(catalog=catalog)["status"])

    def test_history_is_classified_but_never_reauthorizes_current_evidence(self):
        predecessor = self.copy_with_id(
            self.review, "audit-record_substantive_review-predecessor-0001",
            invalidated_by=self.review["receipt_id"])
        invalidated = self.copy_with_id(
            self.review, "audit-record_substantive_review-invalidated-0001",
            invalidated_by="standards-invalidation-event")
        self.result["receipt_catalog"] = {
            predecessor["receipt_id"]: predecessor,
            invalidated["receipt_id"]: invalidated,
        }

        resolution = self.resolution()
        row = runtime._reconciliation_row(
            self.result, self.plan, self.obligation, resolution)
        self.assertEqual([predecessor["receipt_id"]],
                         row["superseded_evidence_refs"])
        self.assertEqual([invalidated["receipt_id"]],
                         row["invalidated_evidence_refs"])
        self.assertFalse(row["unresolved"])

        unclassified = self.copy_with_id(
            self.review, "audit-record_substantive_review-unclassified-0001")
        self.result["receipt_catalog"][unclassified["receipt_id"]] = \
            unclassified
        row = runtime._reconciliation_row(
            self.result, self.plan, self.obligation, resolution)
        self.assertTrue(row["unresolved"])
        self.assertIn("absent from the current-use catalog",
                      row["unresolved_reason"])

    def test_terminal_reports_withdrawn_close_without_reauthorizing_history(self):
        row = runtime._reconciliation_row(
            self.result, self.plan, self.obligation, self.resolution())
        close = {"receipt_id": "closed", "reviewer_attestation_receipt": "attestation"}
        context = {"receipt_id": "attestation", "result": "pass", "invalidated_by": None,
                   "receipt_type_id": "batch-close-review-attestation-v1",
                   "check": "batch_global_review_attestation",
                   "audit_plan_id": self.plan["plan_id"],
                   **runtime._reconciliation_projection([row])}
        self.item.update(state="closed", close_gate_receipt="closed")
        self.result["receipt_catalog"] = {"closed": close, "attestation": context}
        self.result["current_receipt_catalog"] = {}
        with self.assertRaisesRegex(runtime.AuditEvidenceError, "no current close"):
            runtime.terminal_plan_reconciliation(self.result)
        self.result["invalidated_evidence_receipt_ids"] = [
            "closed", self.review["receipt_id"]]
        projection = runtime.terminal_plan_reconciliation(self.result)
        self.assertIn("closed", projection["invalidated_receipts"])
        self.assertGreater(projection["unresolved_invalidations"], 0)
        self.assertEqual("closed", self.item["state"])
        self.assertEqual(close, self.result["receipt_catalog"]["closed"])

    def test_reconciliation_projection_is_closed_disjoint_and_hash_bound(self):
        row = runtime._reconciliation_row(
            self.result, self.plan, self.obligation, self.resolution())
        projection_value = runtime._reconciliation_projection([row])
        self.assertEqual(
            projection_value,
            runtime.validate_plan_reconciliation(projection_value))

        overlapping = copy.deepcopy(projection_value)
        overlapping["audit_evidence_reconciliation"][0][
            "superseded_evidence_refs"] = [self.review["receipt_id"]]
        with self.assertRaisesRegex(runtime.AuditEvidenceError, "overlap"):
            runtime.validate_plan_reconciliation(overlapping)

        wrong_digest = copy.deepcopy(projection_value)
        wrong_digest["audit_evidence_reconciliation_sha256"] = \
            digest("wrong-reconciliation")
        with self.assertRaisesRegex(runtime.AuditEvidenceError, "sha256"):
            runtime.validate_plan_reconciliation(wrong_digest)


class BatchReviewPublicationIntegrationTests(CurrentEvidenceCheckpoint,
                                            unittest.TestCase):

    def test_wrapper_publication_reuses_exact_declaration_and_rechecks_under_lock(self):
        from Tools.execution.audit import record_batch_review as producer
        from Tools.execution.evidence import manual_attestation
        from Tools.execution.task_runtime import task_runtime_runner as runner
        from Tools.execution.task_runtime.queue_runtime import receipts as receipt_store

        relative = ".cambium/work_specs/audit-plans/current.yaml"
        delta = {"path": "Delta.md", "sha256": digest("delta"), "page_receipt_ids": []}
        with contextlib.ExitStack() as stack:
            root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            (root / ".cambium/tmp").mkdir(parents=True)
            # Install only the immutable contracts this local seam reads,
            # not a repository or an executable lifecycle fixture.
            for path in (*projection._BASE_PROJECTION_SOURCE_PATHS,
                         receipt_contract.AUDIT_FINGERPRINT_CONTRACT_PATH):
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((REPOSITORY / path).read_bytes())
            (root / self.obligation["target"]).write_bytes(
                (REPOSITORY / self.obligation["target"]).read_bytes())
            register = root / producer.DEFAULT_RECEIPTS
            register.parent.mkdir(parents=True)
            stack.enter_context(mock.patch.object(runtime, "_resolve_current_plan",
                return_value=(relative, self.plan, self.plan_sha256)))
            stack.enter_context(mock.patch.object(runtime, "_require_current_profile_rendering_contract_state"))
            # The admitted runtime uses this repository's installed producer
            # registry; do not copy every CLI merely to revalidate its source.
            registry = runtime.receipt_type_contract.load_receipt_type_registry(REPOSITORY)
            stack.enter_context(mock.patch.object(runtime.receipt_type_contract,
                "load_receipt_type_registry", return_value=registry))
            artifact = stack.enter_context(mock.patch.object(runtime._EvidenceFacts, "page_artifact",
                return_value=self.review["artifact_fingerprint"]))
            # Profile admission and candidate file resolution are independent
            # owners. The stage, wrapper selector, builder, validator, lock,
            # append and exact read-back below are real.
            stack.enter_context(mock.patch.object(producer.queue_review,
                "batch_review_judgment_errors", return_value=[]))
            stack.enter_context(mock.patch.object(producer, "_current_judgment_receipts", return_value=[]))
            stack.enter_context(mock.patch.object(producer, "_managed_candidate_delta", return_value=delta))
            self.bind_review(runtime.batch_review_evidence(self.result, self.item))
            del self.catalog["wrapper"]
            self.item.update(state="open", batch_receipts=[])

            def observed():
                records = dict(self.catalog)
                if register.exists():
                    records.update(receipt_store.read_receipt_register(root, producer.DEFAULT_RECEIPTS))
                return {**self.result, "root": str(root), "errors": [],
                        "queue": {"task_id": self.plan["task_id"]},
                        "current_receipt_catalog": receipt_store.Catalog({
                            identity: (producer.DEFAULT_RECEIPTS, row) for identity, row in records.items()})}

            def make_receipt(tool, version, check, target, result, details, seq, **kwargs):
                return {"receipt_id": "attempt-" + str(make.call_count),
                        "checked_at": self.plan["generated_at"], "tool": tool,
                        "tool_version": version, "check": check, "target": target,
                        "result": result, "details": details, "invalidated_by": None,
                        "receipt_type_id": kwargs["receipt_type_id"],
                        **{key: self.plan[key] for key in (
                            "task_id", "upstream_revision_id", "selected_profile_manifest")}}

            make = stack.enter_context(mock.patch.object(kblib, "make_receipt", side_effect=make_receipt))
            stack.enter_context(mock.patch.object(producer_runtime, "admitted_runtime",
                side_effect=lambda _root: (str(root), observed(), {})))
            stack.enter_context(mock.patch.object(producer_runtime, "runtime_lock_metadata",
                return_value={"tool": producer.CLI_TOOL, "action": "record-batch-review"}))
            fresh = stack.enter_context(mock.patch.object(manual_attestation.runtime_validation,
                "validate_runtime", side_effect=lambda *_args, **_kwargs: observed()))
            stack.enter_context(mock.patch.object(manual_attestation.queue_runtime,
                "runtime_authority_validation_kwargs", return_value={}))
            stack.enter_context(mock.patch.object(manual_attestation.queue_runtime,
                "require_runtime_authority_current"))

            def submit(statement="approved"):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = producer.main([str(root), "--batch", self.item["id"],
                        "--actor-role", "integrator", "--statement", statement, "--apply", "--json"])
                return code, json.loads(output.getvalue())

            code, first = submit()
            self.assertEqual(0, code, first)
            first_bytes = register.read_bytes()
            first_id = first["receipt_id"]
            self.assertEqual(2, fresh.call_count)  # locked admission and after-image
            code, retry = submit()
            self.assertEqual(0, code, retry)
            self.assertEqual(first_id, retry["receipt_id"])
            self.assertEqual(first_bytes, register.read_bytes())
            self.assertEqual(3, fresh.call_count)  # reuse still re-admits under lock
            code, changed = submit("a different declaration")
            self.assertEqual(1, code, changed)
            self.assertIn("different declaration", str(changed))
            self.assertEqual(first_bytes, register.read_bytes())

            revised = self.copy_with_id(self.review, "revised-review")
            revised["artifact_fingerprint"] = digest("revised-content")
            artifact.return_value = revised["artifact_fingerprint"]
            self.catalog[revised["receipt_id"]] = revised
            code, revised_result = submit()
            self.assertEqual(0, code, revised_result)
            self.assertNotEqual(first_id, revised_result["receipt_id"])
            self.assertTrue(register.read_bytes().startswith(first_bytes))
            rows = receipt_store.read_receipt_register(root, producer.DEFAULT_RECEIPTS)
            self.assertEqual(2, len(rows))
            self.assertEqual(revised_result["receipt_id"], runner._current_batch_review_wrapper(
                observed(), self.item, delta))

            def conflict_under_lock(*_args, **_kwargs):
                self.catalog["racing-wrapper"] = self.copy_with_id(
                    rows[revised_result["receipt_id"]], "racing-wrapper")
                return observed()
            fresh.side_effect = conflict_under_lock
            before_conflict = register.read_bytes()
            code, conflict = submit()
            self.assertEqual(1, code, conflict)
            self.assertIn("multiple current", str(conflict))
            self.assertEqual(before_conflict, register.read_bytes())
            self.assertFalse((root / ".cambium/tmp/state-writer.lock").exists())


class AuditEvidenceCheckpointIntegrationTests(CurrentEvidenceCheckpoint,
                                              unittest.TestCase):

    def test_wrapper_selection_allows_stale_history_but_rejects_conflict_and_corruption(self):
        from Tools.execution.task_runtime.queue_runtime import review as queue_review
        old_review = self.copy_with_id(self.review, "old-review")
        old_review["artifact_fingerprint"] = digest("previous-page")
        self.catalog.clear()
        self.catalog[old_review["receipt_id"]] = old_review
        relative = ".cambium/work_specs/audit-plans/current.yaml"
        delta = {"path": "Delta.md", "sha256": digest("delta"), "page_receipt_ids": []}
        def selected_wrapper():
            observed = {**self.result, "current_receipt_catalog": {
                identity: ("fixture.jsonl", record) for identity, record in self.catalog.items()}}
            return runtime.current_batch_review_receipt(observed, self.item, delta)
        with mock.patch.object(runtime, "_resolve_current_plan",
                               return_value=(relative, self.plan, self.plan_sha256)), \
                mock.patch.object(runtime, "_require_current_profile_rendering_contract_state"), \
                mock.patch.object(queue_review, "batch_review_judgment_errors", return_value=[]):
            with mock.patch.object(runtime._EvidenceFacts, "page_artifact",
                                   return_value=old_review["artifact_fingerprint"]):
                old = self.bind_review(runtime.batch_review_evidence(self.result, self.item))
                self.item.update(state="open", batch_receipts=[])
                self.assertIs(old, selected_wrapper())
            self.catalog[self.review["receipt_id"]] = self.review
            self.assertIsNone(selected_wrapper())
            new = self.bind_review(runtime.batch_review_evidence(self.result, self.item))
            new["receipt_id"] = "new-wrapper"
            self.catalog.update({"wrapper": old, "new-wrapper": new})
            self.item.update(state="open", batch_receipts=[])
            self.assertIs(new, selected_wrapper())
            self.catalog["duplicate"] = self.copy_with_id(new, "duplicate")
            with self.assertRaisesRegex(runtime.AuditEvidenceError, "multiple current"):
                selected_wrapper()
            del self.catalog["duplicate"]
            old["tool_version"] = "invalid"
            with self.assertRaisesRegex(runtime.AuditEvidenceError, "invalid stable"):
                selected_wrapper()

    def test_round_two_dependency_reaches_terminal_without_becoming_a_candidate(self):
        from Tools.execution.audit import batch_close_contract
        from Tools.execution.evidence import evidence_invalidation_contract as invalidation
        from Tools.execution.task_runtime.queue_runtime import receipts as receipt_store
        first = self.review_record("first", blocking=True)
        first["artifact_fingerprint"] = digest("before-correction")
        second = self.review_record("second", prior=first)
        self.catalog.clear()
        self.catalog.update({row["receipt_id"]: row for row in (first, second)})
        relative = ".cambium/work_specs/audit-plans/current.yaml"
        with mock.patch.object(runtime, "_resolve_current_plan",
                               return_value=(relative, self.plan, self.plan_sha256)), \
                mock.patch.object(runtime, "_require_current_profile_rendering_contract_state"):
            closure = runtime.batch_review_evidence(self.result, self.item)
            self.bind_review(closure)
            self.item.update(state="closed", close_gate_receipt="close")
            close = {"receipt_id": "close", "result": "pass", "invalidated_by": None,
                     "receipt_type_id": batch_close_contract.GATE_RECEIPT_TYPE_ID,
                     "reviewer_attestation_receipt": "attestation"}
            context = {"receipt_id": "attestation", "result": "pass", "invalidated_by": None,
                     "receipt_type_id": batch_close_contract.REVIEW_ATTESTATION_RECEIPT_TYPE_ID,
                     "check": "batch_global_review_attestation",
                     **{key: value for key, value in closure.items()
                        if key not in {"audit_evidence_bindings", "audit_evidence_set_sha256"}}}
            self.catalog["close"] = close
            self.catalog["attestation"] = context
            postdelta = {
                "stage_plan": {"audit_plan_path": relative, "plan": self.plan,
                               "audit_plan_sha256": self.plan_sha256},
                "reconciliation": runtime._reconciliation_projection([]),
                "final_by_obligation": {},
            }
            # Only the independent post-Delta owner is outside this L evidence
            # seam. The selected stage and real L/Receipt validators are not mocked.
            with mock.patch.object(runtime, "_post_delta_evidence_closure", return_value=postdelta):
                def terminal():
                    return runtime._closed_batch_dimension_evidence(
                        runtime.evidence_evaluation(self.result), self.item,
                        self.catalog, {self.obligation["dimension"]})
                self.assertEqual([second["receipt_id"]], [row["evidence_ref"] for row in terminal()])
                self.assertNotIn(first["receipt_id"], closure["audit_evidence_reconciliation"][0]["produced_evidence_refs"])
                for failure in ("missing", "withdrawn", "corrupt"):
                    with self.subTest(failure=failure):
                        if failure == "missing":
                            del self.catalog[first["receipt_id"]]
                        elif failure == "withdrawn":
                            self.result["invalidated_evidence_receipt_ids"] = [first["receipt_id"]]
                        else:
                            self.catalog[first["receipt_id"]] = {**first, "tool_version": "invalid"}
                        with self.assertRaises(runtime.AuditEvidenceError):
                            terminal()
                        self.catalog[first["receipt_id"]] = first
                        self.result["invalidated_evidence_receipt_ids"] = []
                self.assertEqual("closed", self.item["state"])
                self.assertEqual("fail", first["result"])

                # Feed an actual correction through the registered acceptance
                # graph, not just an injected invalidated-ID list. Activation
                # is an independent non-propagating admission boundary.
                history = receipt_store.HistoricalReceiptCatalog({
                    identity: ("fixture.jsonl", body) for identity, body in self.catalog.items()
                    if identity != "activation"})
                event = invalidation.build_event(
                    event_id="withdraw-round-one", reason="incorrect-result",
                    decision={"mode": "explicit-user", "actor_role": "user",
                              "reviewer_context_id": None, "authority_reference": "user-decision",
                              "statement": "Withdraw this exact declaration."},
                    subjects=[first], authority=self.plan,
                    checked_at=self.plan["generated_at"])
                history[event["receipt_id"]] = ("corrections.jsonl", event)
                before = copy.deepcopy(dict(history))
                view = invalidation.invalidation_view(history, root=REPOSITORY)
                self.assertEqual({first["receipt_id"], second["receipt_id"],
                                  "wrapper", "attestation", "close"}, set(view["affected"]))
                self.result.update(receipt_catalog=history,
                    current_receipt_catalog=receipt_store.adoption_filtered_catalog(history, view["affected"]),
                    invalidated_evidence_receipt_ids=list(view["affected"]),
                    evidence_invalidation_view=view)
                with self.assertRaises(runtime.AuditEvidenceError):
                    terminal()
                self.assertIn("close", runtime.terminal_plan_reconciliation(
                    self.result)["invalidated_receipts"])
                self.assertEqual("closed", self.item["state"])
                self.assertEqual(before, dict(history))

    def test_stage_and_batch_review_share_one_current_checkpoint(self):
        old_review = self.copy_with_id(self.review, "old-review")
        old_review["artifact_fingerprint"] = digest("before-revision")
        self.catalog[old_review["receipt_id"]] = old_review
        resolved = (
            ".cambium/work_specs/audit-plans/current.yaml",
            self.plan,
            self.plan_sha256,
        )
        with mock.patch.object(
                runtime, "_resolve_current_plan", return_value=resolved), \
                mock.patch.object(
                    runtime,
                    "_require_current_profile_rendering_contract_state",
                    return_value=None), \
                mock.patch.object(runtime, "_required_obligation_resolution",
                    wraps=runtime._required_obligation_resolution) as resolve, \
                mock.patch.object(runtime, "_reconciliation_row",
                    wraps=runtime._reconciliation_row) as reconcile, \
                runtime.evidence_observation(self.result) as observed:
            status = runtime.stage_evidence_status(
                observed, self.item, "pre-merge",
                required_state="open")
            reconcile.assert_not_called()
            closure = runtime.batch_review_evidence(
                observed, self.item, required_state="open")
            self.assertGreater(reconcile.call_count, 0)
            self.assertEqual(
                [], runtime.wrapper_binding_errors(
                    observed, self.item, copy.deepcopy(closure),
                    required_state="open"))
            self.assertEqual(1, resolve.call_count)
            with runtime.evidence_observation(observed) as fresh:
                runtime.batch_review_evidence(fresh, self.item, required_state="open")
            self.assertEqual(2, resolve.call_count)
        self.assertNotIn("_audit_stage_resolutions", observed)
        self.assertNotIn("_audit_evidence_facts", observed)

        self.assertEqual("satisfied", status["obligations"][0]["status"])
        self.assertEqual(status["audit_plan_id"], closure["audit_plan_id"])
        self.assertEqual(status["obligations"][0]["evidence_ref"],
                         closure["audit_evidence_bindings"][0]["evidence_ref"])
        runtime.validate_plan_reconciliation({
            field: closure[field]
            for field in runtime.audit_reconciliation_contract.projection_fields()})
        self.assertEqual(
            self.review["receipt_id"],
            closure["audit_evidence_bindings"][0]["evidence_ref"])

        # Closing uses the same pre-merge projection both to validate the
        # wrapper and to build reconciliation. The post-Delta owner is a
        # separate seam; stop there rather than constructing a full batch.
        frozen = self.bind_review(closure)
        with mock.patch.object(runtime, "_resolve_current_plan", return_value=resolved), \
                mock.patch.object(runtime, "_require_current_profile_rendering_contract_state"), \
                mock.patch.object(runtime, "_producer_record_errors",
                                  wraps=runtime._producer_record_errors) as final_check, \
                mock.patch.object(runtime, "batch_review_evidence",
                                  wraps=runtime.batch_review_evidence) as premerge, \
                mock.patch.object(runtime, "_post_delta_evidence_closure",
                                  side_effect=runtime.AuditEvidenceError(
                                      "post-Delta owner seam")):
            errors = runtime.closed_plan_closure_errors(self.result, self.item, {})
            after = runtime.batch_review_evidence(
                self.result, self.item, required_state="merge-ready")
        self.assertEqual(closure, after)
        self.assertEqual(closure, {key: frozen[key] for key in closure})
        self.assertEqual([old_review["receipt_id"]],
                         after["audit_evidence_reconciliation"][0]["invalidated_evidence_refs"])
        self.assertEqual(["closed AuditPlan evidence is invalid: post-Delta owner seam"], errors)
        self.assertEqual(2, premerge.call_count)
        self.assertEqual(2, final_check.call_count)
        self.assertTrue(all(call.args[-1]["receipt_id"] == self.review["receipt_id"]
                            and call.kwargs["require_current"] is False
                            for call in final_check.call_args_list))

    def test_frozen_stage_rejects_unbound_source_and_changed_selected_body(self):
        relative = ".cambium/work_specs/audit-plans/current.yaml"
        with mock.patch.object(runtime, "_resolve_current_plan",
                               return_value=(relative, self.plan, self.plan_sha256)), \
                mock.patch.object(runtime, "_require_current_profile_rendering_contract_state"):
            closure = runtime.batch_review_evidence(self.result, self.item)
            wrapper = self.bind_review(closure)
            cases = (
                ("source", lambda: self.item.update(batch_receipts=[])),
                ("activation", lambda: wrapper.update(activation_receipt_id="other")),
                ("unresolved", lambda: wrapper.update(audit_evidence_unresolved_count=1)),
                ("binding", lambda: wrapper["audit_evidence_bindings"][0].update(
                    evidence_sha256=digest("different body"))),
                ("selected-body", lambda: self.review.update(details="changed declaration")),
            )
            for label, mutate in cases:
                saved_wrapper, saved_review = copy.deepcopy(wrapper), copy.deepcopy(self.review)
                with self.subTest(label=label):
                    mutate()
                    with self.assertRaises(runtime.AuditEvidenceError):
                        runtime.batch_review_evidence(self.result, self.item, required_state="merge-ready")
                wrapper.clear()
                wrapper.update(saved_wrapper)
                self.review.clear()
                self.review.update(saved_review)
                self.item["batch_receipts"] = ["wrapper"]


class TerminalDimensionEvidenceProjectionTests(unittest.TestCase):
    """Own the closed-plan to Terminal dimension-evidence projection."""

    def setUp(self):
        self.profile_fixture = CurrentProfileContractFixture(self)
        self.profile_fixture.configure_extension_dimensions((
            {"dimension_id": "language_quality", "targets": ["receipt"],
             "meaning": "Language quality receipt."},
        ))
        self.profile_view = self.admit_dimensions()
        self.plan_sha256 = digest("terminal-plan")
        self.plan_path = \
            ".cambium/work_specs/audit-plans/audit-plan-B001.yaml"
        self.obligations = [
            {
                "obligation_id": "m-content",
                "due_stage": "pre-merge",
                "dimension": "content_and_depth",
                "evidence_kind": "batch-page-review-record",
            },
            {
                "obligation_id": "profile-language",
                "due_stage": "pre-merge",
                "dimension": "language_quality",
                "evidence_kind": "page-batch-judgment-v2",
            },
            {
                "obligation_id": "page-contract",
                "due_stage": "post-delta-close",
                "dimension": None,
                "evidence_kind": "gate-receipt",
            },
            {
                "obligation_id": "m-source-not-applicable",
                "due_stage": "pre-merge",
                "dimension": "source_and_currentness",
                "evidence_kind": "batch-page-review-record",
            },
        ]
        self.records = {
            "evidence-m-content": {
                "receipt_id": "evidence-m-content",
                "record_kind": "batch-page-review-record",
                "review_variant": "m-atomic-item",
                "applicability_disposition": "applicable",
            },
            "evidence-profile-language": {
                "receipt_id": "evidence-profile-language",
                "record_kind": "page-batch-judgment-v2",
            },
            "evidence-page-contract": {
                "receipt_id": "evidence-page-contract",
                "record_kind": "gate-receipt",
            },
            "evidence-m-source-na": {
                "receipt_id": "evidence-m-source-na",
                "record_kind": "batch-page-review-record",
                "review_variant": "m-atomic-item",
                "applicability_disposition": "not-applicable",
                "applicability_reason": "no source claim is present",
            },
        }
        self.refs = dict(zip(
            (row["obligation_id"] for row in self.obligations),
            self.records,
        ))
        reconciliation = runtime._reconciliation_projection([{
            "obligation_id": row["obligation_id"],
            "due_stage": row["due_stage"],
            "selected_evidence_ref": self.refs[row["obligation_id"]],
            "selected_disposition": "produced",
            "produced_evidence_refs": [self.refs[row["obligation_id"]]],
            "reused_reserved_evidence_ref": None,
            "superseded_evidence_refs": [],
            "invalidated_evidence_refs": [],
            "unresolved": False,
            "unresolved_reason": None,
        } for row in self.obligations])
        self.close = {
            "receipt_id": "close-B001",
            "result": "pass",
            "invalidated_by": None,
            "reviewer_attestation_receipt": "attestation-B001",
        }
        self.context = {
            "receipt_id": "attestation-B001", "result": "pass", "invalidated_by": None,
            "receipt_type_id": "batch-close-review-attestation-v1",
            "check": "batch_global_review_attestation",
            "audit_plan_id": "audit-plan-B001",
            "audit_plan_path": self.plan_path,
            "audit_plan_sha256": self.plan_sha256,
            **reconciliation,
        }
        self.item = {
            "id": "B001",
            "state": "closed",
            "close_gate_receipt": self.close["receipt_id"],
        }
        self.plan = {
            "plan_id": "audit-plan-B001",
            "obligations": copy.deepcopy(self.obligations),
        }
        self.result = {
            "root": str(self.profile_fixture.root),
            "errors": [],
            "items_by_id": {"B001": self.item},
            "current_receipt_catalog": {
                self.close["receipt_id"]: self.close,
                self.context["receipt_id"]: self.context,
                **self.records,
            },
            "invalidated_evidence_receipt_ids": [],
            "_profile_authorized_view": self.profile_view,
        }

    def admit_dimensions(self):
        view, errors = profile_view.profile_load_authorized_view(
            self.profile_fixture.root,
            self.profile_fixture.manifest.relative_to(self.profile_fixture.root).as_posix())
        self.assertEqual([], errors)
        return view

    def _premerge_closure(self):
        """Input from the independently tested frozen-stage owner."""
        rows = [row for row in self.context["audit_evidence_reconciliation"]
                if row["due_stage"] == "pre-merge"]
        return {
            "audit_plan_id": self.plan["plan_id"],
            "audit_plan_path": self.plan_path,
            "audit_plan_sha256": self.plan_sha256,
            "audit_evidence_bindings": [
                {"obligation_id": row["obligation_id"],
                 "evidence_ref": self.refs[row["obligation_id"]]}
                for row in rows],
            **runtime._reconciliation_projection(rows),
        }

    def _postdelta_closure(self):
        obligations = [
            row for row in self.obligations
            if row["due_stage"] == "post-delta-close"
        ]
        reconciliation = runtime._reconciliation_projection([{
            "obligation_id": row["obligation_id"],
            "due_stage": row["due_stage"],
            "selected_evidence_ref": self.refs[row["obligation_id"]],
            "selected_disposition": "produced",
            "produced_evidence_refs": [self.refs[row["obligation_id"]]],
            "reused_reserved_evidence_ref": None,
            "superseded_evidence_refs": [],
            "invalidated_evidence_refs": [],
            "unresolved": False,
            "unresolved_reason": None,
        } for row in obligations])
        return {
            "stage_plan": {
                "audit_plan_path": self.plan_path,
                "audit_plan_sha256": self.plan_sha256,
                "plan": self.plan,
            },
            "final_by_obligation": {
                row["obligation_id"]:
                    self.records[self.refs[row["obligation_id"]]]
                for row in obligations
            },
            "reconciliation": reconciliation,
        }

    def project(self):
        with mock.patch.object(
                runtime, "_post_delta_evidence_closure",
                return_value=self._postdelta_closure()), mock.patch.object(
                runtime, "batch_review_evidence",
                side_effect=lambda *_args, **_kwargs: self._premerge_closure()):
            return runtime.terminal_dimension_evidence(self.result)

    def test_m_and_profile_evidence_project_but_dimensionless_and_na_do_not(self):
        rows = self.project()
        self.assertEqual(
            [
                ("content_and_depth", "batch-page-review-record",
                 "evidence-m-content"),
                ("language_quality", "page-batch-judgment-v2",
                 "evidence-profile-language"),
            ],
            [(row["dimension"], row["evidence_kind"], row["evidence_ref"])
             for row in rows],
        )

        self.result["current_receipt_catalog"]["foreign-current"] = {
            "receipt_id": "foreign-current",
            "record_kind": "batch-page-review-record",
            "dimension": "content_and_depth",
        }
        self.assertEqual(rows, self.project())

    def test_invalidated_or_owner_rejected_selected_evidence_fails_closed(self):
        self.result["invalidated_evidence_receipt_ids"] = [
            "evidence-m-content"]
        with self.assertRaisesRegex(
                runtime.AuditEvidenceError, "invalidated evidence"):
            self.project()

        self.result["invalidated_evidence_receipt_ids"] = []
        with mock.patch.object(self, "_premerge_closure", side_effect=
                               runtime.AuditEvidenceError("owner rejected evidence")):
            with self.assertRaisesRegex(
                runtime.AuditEvidenceError,
                "owner rejected evidence"):
                self.project()

    def test_post_delta_reconciliation_must_equal_owner_closure(self):
        rows = copy.deepcopy(
            self.context["audit_evidence_reconciliation"])
        target = next(row for row in rows
                      if row["obligation_id"] == "page-contract")
        target["selected_evidence_ref"] = "foreign-page-contract"
        target["produced_evidence_refs"] = ["foreign-page-contract"]
        self.context.update(runtime._reconciliation_projection(rows))
        self.result["current_receipt_catalog"]["foreign-page-contract"] = {
            "receipt_id": "foreign-page-contract",
            "record_kind": "gate-receipt",
        }

        with self.assertRaisesRegex(
                runtime.AuditEvidenceError,
                "no current selected evidence matching"):
            self.project()

    def test_typed_profile_receipt_target_enters_but_review_only_stays_out(self):
        self.profile_fixture.configure_extension_dimensions((
            {"dimension_id": "language_quality", "targets": ["receipt"],
             "meaning": "Language quality receipt."},
            {"dimension_id": "review_only", "targets": ["review"],
             "meaning": "Review-only judgment."},
            {"dimension_id": "terminal_receipt", "targets": ["receipt"],
             "meaning": "Terminal receipt judgment."},
        ))
        self.result["_profile_authorized_view"] = self.admit_dimensions()

        additions = (
            ("profile-review-only", "review_only",
             "evidence-profile-review-only"),
            ("profile-terminal-receipt", "terminal_receipt",
             "evidence-profile-terminal-receipt"),
        )
        for obligation_id, dimension, evidence_ref in additions:
            self.obligations.append({
                "obligation_id": obligation_id,
                "due_stage": "pre-merge",
                "dimension": dimension,
                "evidence_kind": "page-batch-judgment-v2",
            })
            self.records[evidence_ref] = {
                "receipt_id": evidence_ref,
                "record_kind": "page-batch-judgment-v2",
            }
            self.refs[obligation_id] = evidence_ref
            self.result["current_receipt_catalog"][evidence_ref] = \
                self.records[evidence_ref]
        self.plan["obligations"] = copy.deepcopy(self.obligations)
        self.context.update(runtime._reconciliation_projection([{
            "obligation_id": row["obligation_id"],
            "due_stage": row["due_stage"],
            "selected_evidence_ref": self.refs[row["obligation_id"]],
            "selected_disposition": "produced",
            "produced_evidence_refs": [self.refs[row["obligation_id"]]],
            "reused_reserved_evidence_ref": None,
            "superseded_evidence_refs": [],
            "invalidated_evidence_refs": [],
            "unresolved": False,
            "unresolved_reason": None,
        } for row in self.obligations]))

        rows = self.project()
        projected = {
            row["obligation_id"]: row["dimension"] for row in rows
        }
        self.assertEqual(
            "terminal_receipt", projected["profile-terminal-receipt"])
        self.assertNotIn("profile-review-only", projected)


if __name__ == "__main__":
    unittest.main()
