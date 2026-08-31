"""One representative current Profile lifecycle.

Field, slot, inactive-form, validation-error, writer-failure, and transport
branches belong to the template, ``check_profile``, scaffolder, and adoption
owner suites. This E2E proves only the cross-owner seam they cannot prove in
isolation:

current ``_template`` -> scaffold -> confirmed fill -> Profile load -> R09
initial adoption.
"""

from pathlib import Path
import tempfile
import unittest

from Tools.governance.standards import adoption_lineage_contract
import Tools.tests.support.profile_adoption_fixture as adoption_fixture


class ProfileFlowEndToEndTests(unittest.TestCase):
    def test_current_template_candidate_reaches_initial_adoption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root, evaluation = adoption_fixture.build_scaffolded_base(root)

            self.assertTrue(evaluation.authorized)
            self.assertEqual(adoption_fixture.PROFILE_ID,
                             evaluation.profile_id)
            plan = adoption_fixture.initial_plan(
                root, evaluation=evaluation)
            plan_relative = adoption_fixture.write_plan(root, plan)
            code, output = adoption_fixture.run_tool(
                root, "--apply", plan=plan_relative)

            self.assertEqual(0, code, output)
            state = adoption_fixture.governance_state(root)
            self.assertEqual(adoption_fixture.MANIFEST,
                             state["selected_profile_manifest"])
            self.assertEqual(adoption_fixture.UPSTREAM_REVISION,
                             state["upstream_revision_id"])
            self.assertEqual(1, state["state_revision"])
            receipt_path = root / adoption_lineage_contract.ADOPTION_RECEIPT_PATH
            self.assertTrue(receipt_path.is_file())
            self.assertIn(
                state["latest_adoption_receipt"],
                receipt_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
