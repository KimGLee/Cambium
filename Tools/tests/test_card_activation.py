"""Owner-focused tests for the current phased Card activation contract.

The activation module owns the closed context and its composition from an
already-valid runtime checkpoint. Phase packing, delivery acknowledgement,
Queue routing, Runner orchestration, and Card registry projection have their
own primary suites and are not replayed here.
"""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS.parent))

import Tools.execution.context_delivery.card_activation as card_activation
import Tools.execution.context_delivery.read_set_contract as read_set_contract
from Tools.execution.task_runtime.queue_check_receipt import make_check_receipt
from Tools.tests.fixtures.contract.card_activation_objects import (
    current_activation_context,
    rebind_activation_manifest,
    sha256_fixture,
)
from Tools.tests.fixtures.integration.card_activation_checkpoint import (
    install_checkpoint,
)


class CardActivationUnitTests(unittest.TestCase):
    def test_transport_binding_never_claims_delivery(self):
        prepared = card_activation._delivery_binding("")
        bound = card_activation._delivery_binding("mcp:current-context")

        self.assertEqual({
            "delivery_mode": "cli-tool-result",
            "delivery_assurance": "prepared",
            "execution_context_id": None,
        }, prepared)
        self.assertEqual({
            "delivery_mode": "host-context-injection",
            "delivery_assurance": "host-bound",
            "execution_context_id": "mcp:current-context",
        }, bound)


class CardActivationContractTests(unittest.TestCase):
    def test_phase_projection_consumes_the_read_set_machine_contract(self):
        phases = read_set_contract.load_schema(TOOLS.parent)["phases"]

        self.assertEqual(
            tuple(row["phase_id"] for row in phases),
            card_activation.PHASE_ORDER)
        self.assertEqual(
            {row["phase_id"] for row in phases if row["conditional"]},
            set(card_activation.CONDITIONAL_PHASES))
        self.assertEqual(
            {row["phase_id"]: row["trigger"] for row in phases},
            card_activation.PHASE_TRIGGERS)

    def test_current_activation_context_is_closed_and_current(self):
        context = current_activation_context()
        self.assertEqual([], card_activation.activation_context_errors(context))

        foreign_protocol = copy.deepcopy(context)
        foreign_protocol["activation_protocol"] = "unregistered"
        self.assertEqual(
            ["activation_protocol must be %s" %
             card_activation.ACTIVATION_PROTOCOL],
            card_activation.activation_context_errors(foreign_protocol))

        open_shape = dict(context, unexpected_field=None)
        self.assertEqual(
            ["activation context fields do not match the current closed "
             "contract"],
            card_activation.activation_context_errors(open_shape))

    def test_receipt_and_exact_bundle_predicates_keep_one_current_boundary(self):
        context = current_activation_context()
        receipt = dict(context, receipt_id="receipt-1", tool="check_queue")

        self.assertEqual(
            context, card_activation.context_from_receipt(receipt))
        self.assertEqual(
            context, card_activation.activation_receipt_binding(context))

        runtime_revision = copy.deepcopy(context)
        manifest = runtime_revision["activation_bundle_manifest"]
        manifest["required_queue_sha256"] = sha256_fixture("c")
        manifest["queue_revision"] = 2
        manifest["queue_state_revision"] = 3
        rebind_activation_manifest(runtime_revision)
        self.assertEqual(
            [], card_activation.activation_context_errors(runtime_revision))
        self.assertEqual(
            [], card_activation.exact_bundle_errors(
                context, runtime_revision))

        changed_delivery = copy.deepcopy(context)
        changed_delivery["activation_bundle_manifest"]["task_id"] = "TASK-2"
        rebind_activation_manifest(changed_delivery)
        self.assertEqual(
            [], card_activation.activation_context_errors(changed_delivery))
        self.assertEqual(
            ["activation Bundle differs from current Card/Read Set bytes"],
            card_activation.exact_bundle_errors(context, changed_delivery))


class CardActivationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name).resolve() / "repo"
        progress, item, cls.runtime = install_checkpoint(cls.root)
        cls.context = card_activation.build_activation_context(
            cls.root,
            progress,
            item,
            runtime_state=cls.runtime)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_static_runtime_checkpoint_connects_activation_to_gate_receipt(self):
        receipt = make_check_receipt(
            self.runtime, "pass", "fixture activation", "require-ready:B1",
            activation_context=self.context)
        consumed = card_activation.context_from_receipt(receipt)

        self.assertEqual(
            card_activation.activation_receipt_binding(self.context),
            consumed)
        self.assertEqual(
            card_activation.ACTIVATION_PROTOCOL,
            receipt["activation_protocol"])
        self.assertEqual(
            self.context["phase_plan_sha256"],
            receipt["phase_plan_sha256"])
        self.assertTrue(card_activation.phase_piece_ids(
            consumed, card_activation.PHASE_BATCH_PREFLIGHT))
        self.assertNotIn(
            "content",
            json.dumps(receipt["activation_bundle_manifest"],
                       sort_keys=True))


if __name__ == "__main__":
    unittest.main()
