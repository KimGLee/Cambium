import unittest

import Tools.execution.task_runtime.amendment_plan as amendment_plan
import Tools.execution.task_runtime.apply_amendment as apply_amendment
import Tools.execution.task_runtime.apply_contract_amendment as \
    apply_contract_amendment
import Tools.execution.task_runtime.apply_delta as apply_delta
import Tools.execution.task_runtime.batch_settlement as batch_settlement
import Tools.execution.task_runtime.queue_runtime.amendments as amendments
import Tools.execution.task_runtime.queue_runtime.canon as canon
import Tools.execution.task_runtime.queue_runtime.delta as delta_runtime
import Tools.execution.task_runtime.register_amendment as register_amendment


class TaskRuntimeIdentityFieldContractTests(unittest.TestCase):
    def test_current_producers_and_consumers_share_canon_identity(self):
        pairs = (
            (register_amendment.TOOL, register_amendment.TOOL_VERSION,
             canon.REGISTER_AMENDMENT_TOOL,
             canon.REGISTER_AMENDMENT_TOOL_VERSION),
            (apply_amendment.TOOL, apply_amendment.TOOL_VERSION,
             canon.APPLY_AMENDMENT_TOOL,
             canon.APPLY_AMENDMENT_TOOL_VERSION),
            (apply_contract_amendment.TOOL,
             apply_contract_amendment.TOOL_VERSION,
             canon.CONTRACT_AMENDMENT_TOOL,
             canon.CONTRACT_AMENDMENT_TOOL_VERSION),
            (apply_delta.TOOL, apply_delta.TOOL_VERSION,
             canon.APPLY_DELTA_TOOL, canon.APPLY_DELTA_TOOL_VERSION),
        )
        for producer_tool, producer_version, owner_tool, owner_version in pairs:
            self.assertEqual(owner_tool, producer_tool)
            self.assertEqual(owner_version, producer_version)

        self.assertEqual(canon.APPLY_AMENDMENT_TOOL,
                         amendments.APPLY_AMENDMENT_TOOL)
        self.assertEqual(canon.CONTRACT_AMENDMENT_TOOL,
                         amendments.CONTRACT_AMENDMENT_TOOL)
        self.assertEqual(canon.APPLY_DELTA_TOOL, delta_runtime.APPLY_DELTA_TOOL)

    def test_amendment_bindings_are_derived_from_plan_contract(self):
        expected = {
            field: field for field in amendment_plan.PLAN_FIELDS
            if field not in ("schema_version", "amendment_id")
        }
        self.assertEqual(expected, amendment_plan.AMENDMENT_BINDINGS)

    def test_delta_consumer_uses_settlement_projection_fields(self):
        report = {
            source: index
            for index, (_output, source) in enumerate(
                batch_settlement.TRANSITION_BINDING_SOURCES)
        }
        projected = batch_settlement.transition_binding(report)
        self.assertEqual(tuple(projected),
                         batch_settlement.TRANSITION_BINDING_FIELDS)
        self.assertEqual(
            tuple(field for field in projected
                  if field != "settlement_protocol"),
            delta_runtime.SETTLEMENT_BINDING_FIELDS,
        )


if __name__ == "__main__":
    unittest.main()
