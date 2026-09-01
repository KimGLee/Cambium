"""Ownership-focused tests for current phased Card delivery.

``card-first-phased-readback-v4`` and its phase-plan/delivery/ack records are
current contracts. This suite owns only the producer-to-ack-to-Queue-consumer
seam. Card composition, host conformance, Queue opening, CLI transport, and
Runner orchestration keep their own primary tests and are not replayed here.
"""

import copy
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(ROOT))

import Tools.execution.context_delivery.card_activation as card_activation
from Tools.execution.task_runtime import queue_runtime
from Tools.execution.task_runtime.queue_check_receipt import make_check_receipt
import Tools.platform.common.kblib as kblib
from Tools.tests.fixtures.contract.card_activation_objects import (
    current_activation_context,
    phase_delivery_context,
    rebind_activation_manifest,
    sha256_fixture,
)


CONTEXT = "mcp:1111111111111111111111111111aaaa"
OTHER_CONTEXT = "mcp:2222222222222222222222222222bbbb"


def _runtime_result(context):
    manifest = context["activation_bundle_manifest"]
    return {
        "root": ROOT,
        "queue_sha256": manifest["required_queue_sha256"],
        "coverage_sha256": manifest["coverage_ledger_sha256"],
        "progress_sha256": manifest["progress_ledger_sha256"],
        "remaining": 1,
        "queue": {
            "task_id": manifest["task_id"],
            "upstream_revision_id": manifest["upstream_revision_id"],
            "selected_profile_manifest":
                manifest["selected_profile_manifest"],
            "queue_revision": manifest["queue_revision"],
            "state_revision": manifest["queue_state_revision"],
        },
    }


def _phase_chain(context, *, execution_context_id=CONTEXT):
    result = _runtime_result(context)
    activation = make_check_receipt(
        result, "pass", "fixture activation", "require-ready:B1",
        activation_context=context)
    activation["receipt_id"] = "audit-activation-1"
    delivery_context = phase_delivery_context(
        context, execution_context_id=execution_context_id)
    delivery = make_check_receipt(
        result, "pass", "fixture delivery",
        "deliver-phase:B1:%s:0" % card_activation.PHASE_BATCH_PREFLIGHT,
        phase_context=delivery_context)
    delivery["receipt_id"] = "delivery-%s" % execution_context_id[-4:]
    ack_context = card_activation.build_phase_ack(
        delivery, delivery["delivery_nonce"],
        execution_context_id=execution_context_id)
    ack = make_check_receipt(
        result, "pass", "fixture ack",
        "ack-activation-phase:B1:%s:0" %
        card_activation.PHASE_BATCH_PREFLIGHT,
        phase_ack_context=ack_context)
    ack["receipt_id"] = "ack-%s" % execution_context_id[-4:]
    return result, activation, delivery, ack


def _consumer_view(context, *receipts):
    result, activation, _delivery, _ack = _phase_chain(context)
    catalog = {activation["receipt_id"]: ("fixture", activation)}
    for receipt in receipts:
        catalog[receipt["receipt_id"]] = ("fixture", receipt)
    result.update({
        "current_receipt_catalog": catalog,
        "receipt_catalog": catalog,
    })
    item = {"id": "B1", "activation_receipt": activation["receipt_id"]}
    return result, item


class PhasedReadbackUnitTests(unittest.TestCase):
    def test_attempt_identity_changes_with_bundle_or_context(self):
        current = card_activation.expected_delivery_attempt_id(
            sha256_fixture("1"), CONTEXT)

        self.assertNotEqual(
            current,
            card_activation.expected_delivery_attempt_id(
                sha256_fixture("1"), OTHER_CONTEXT))
        self.assertNotEqual(
            current,
            card_activation.expected_delivery_attempt_id(
                sha256_fixture("2"), CONTEXT))

    def test_control_plane_predicate_reads_only_the_manifest(self):
        self.assertFalse(queue_runtime.batch_touches_control_plane(
            {"manifest": ["Topics/A.md"]}))
        self.assertTrue(queue_runtime.batch_touches_control_plane(
            {"manifest": ["Topics/A.md", "kernel/K00 Standards.md"]}))
        self.assertTrue(queue_runtime.batch_touches_control_plane(
            {"manifest": ["profiles/adopter/profile.md"]}))


class PhasedReadbackContractTests(unittest.TestCase):
    def test_route_narrowing_consumes_current_read_set_declarations(self):
        registry, _fingerprint = card_activation._route_registry(ROOT)
        routes = sorted(registry)
        keep = {routes[0]}

        unchanged = card_activation.resolve_route_phases(
            routes, registry, narrowing=None)
        narrowed = card_activation.resolve_route_phases(
            routes, registry, narrowing=sorted(keep))

        for route_id in routes:
            declaration = registry[route_id]["read_set_declaration"]
            self.assertEqual(
                declaration["activation_phase"], unchanged[route_id])
            expected = (
                card_activation.PHASE_BATCH_RUNNING
                if route_id not in keep and declaration["narrowable"]
                else declaration["activation_phase"]
            )
            self.assertEqual(expected, narrowed[route_id], route_id)

    def test_ack_binds_exact_delivery_nonce_context_and_parent(self):
        context = current_activation_context(
            execution_context_id=CONTEXT)
        delivery = phase_delivery_context(
            context, execution_context_id=CONTEXT)
        delivery["receipt_id"] = "delivery-1"

        ack = card_activation.build_phase_ack(
            delivery, delivery["delivery_nonce"],
            execution_context_id=CONTEXT)

        self.assertEqual("delivery-1", ack["delivery_receipt_id"])
        self.assertEqual(delivery["delivery_attempt_id"],
                         ack["delivery_attempt_id"])
        with self.assertRaisesRegex(ValueError, "nonce"):
            card_activation.build_phase_ack(
                delivery, "0" * 32, execution_context_id=CONTEXT)
        with self.assertRaisesRegex(ValueError, "delivering execution"):
            card_activation.build_phase_ack(
                delivery, delivery["delivery_nonce"],
                execution_context_id=OTHER_CONTEXT)

    def test_queue_consumer_progresses_deliver_acknowledge_complete(self):
        context = current_activation_context(
            execution_context_id=CONTEXT)
        _base, _activation, delivery, ack = _phase_chain(context)
        phase_id = card_activation.PHASE_BATCH_PREFLIGHT

        view, item = _consumer_view(context)
        self.assertEqual(
            "deliver",
            queue_runtime.review.activation_phase_delivery_status(
                view, item, phase_id,
                actor_context_id=CONTEXT)["status"])

        view, item = _consumer_view(context, delivery)
        self.assertEqual(
            "acknowledge",
            queue_runtime.review.activation_phase_delivery_status(
                view, item, phase_id,
                actor_context_id=CONTEXT)["status"])

        view, item = _consumer_view(context, delivery, ack)
        self.assertEqual(
            "complete",
            queue_runtime.review.activation_phase_delivery_status(
                view, item, phase_id,
                actor_context_id=CONTEXT)["status"])
        self.assertEqual(
            [], queue_runtime.activation_phase_delivery_errors(
                view, item, phase_id, actor_context_id=CONTEXT))

    def test_queue_consumer_rejects_foreign_or_broken_ack_chains(self):
        context = current_activation_context(
            execution_context_id=CONTEXT)
        _base, _activation, foreign_delivery, foreign_ack = _phase_chain(
            context, execution_context_id=OTHER_CONTEXT)
        phase_id = card_activation.PHASE_BATCH_PREFLIGHT
        view, item = _consumer_view(
            context, foreign_delivery, foreign_ack)

        self.assertTrue(queue_runtime.activation_phase_delivery_errors(
            view, item, phase_id, actor_context_id=CONTEXT))
        self.assertEqual([], queue_runtime.activation_phase_delivery_errors(
            view, item, phase_id))

        broken = copy.deepcopy(foreign_ack)
        broken["delivery_receipt_id"] = "missing-delivery"
        view, item = _consumer_view(context, foreign_delivery, broken)
        resolved, errors = queue_runtime.resolve_activation_phase_receipt(
            view, item, broken["receipt_id"], receipt_kind="ack",
            phase_id=phase_id, part_index=0)
        self.assertIsNone(resolved)
        self.assertTrue(any("parent" in error for error in errors), errors)

    def test_prepared_activation_cannot_claim_machine_delivery(self):
        context = current_activation_context()
        view, item = _consumer_view(context)
        phase_id = card_activation.PHASE_BATCH_PREFLIGHT

        self.assertEqual(
            "not-applicable",
            queue_runtime.review.activation_phase_delivery_status(
                view, item, phase_id,
                actor_context_id=CONTEXT)["status"])
        self.assertEqual([], queue_runtime.activation_phase_delivery_errors(
            view, item, phase_id, actor_context_id=CONTEXT))

class PhasedReadbackIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        target = self.root / "Card/R01.md"
        target.parent.mkdir(parents=True)
        target.write_text("# R01\n", encoding="utf-8")
        self.context = current_activation_context(
            execution_context_id=CONTEXT)
        piece = self.context["activation_bundle_manifest"]["pieces"][0]
        piece["sha256"] = kblib.sha256_file(target)
        piece["bytes"] = target.stat().st_size
        rebind_activation_manifest(self.context)
        self.assertEqual(
            [], card_activation.activation_context_errors(self.context))

    def test_delivery_reproves_one_frozen_source_before_emission(self):
        phase_id = card_activation.PHASE_BATCH_PREFLIGHT
        delivery = card_activation.build_phase_delivery(
            self.root, self.context, phase_id,
            execution_context_id=CONTEXT)
        self.assertEqual(["card:R01"], delivery["phase_piece_ids"])

        record = card_activation.phase_record(self.context, phase_id)
        piece_id = record["parts"][0]["piece_ids"][0]
        frozen = next(
            row for row in
            self.context["activation_bundle_manifest"]["pieces"]
            if row["piece_id"] == piece_id)
        target = self.root / frozen["path"]
        target.write_text(
            target.read_text(encoding="utf-8") + "\ndrift\n",
            encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "drifted"):
            card_activation.build_phase_delivery(
                self.root, self.context, phase_id,
                execution_context_id=CONTEXT)


if __name__ == "__main__":
    unittest.main()
