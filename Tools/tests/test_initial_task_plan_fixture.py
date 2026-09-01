"""One integrity seam for the shared initial Task Plan checkpoint.

Task Plan shape and projection belong to ``test_apply_task_plan``.  The
unmaterialized-plan to Queue handoff belongs to ``test_compile_queue``.  This
module proves only the remaining fixture-owned fact: the shared runtime seed
can be reconstructed as one valid current Task Plan -> Queue checkpoint whose
two retained transaction references bind its persisted after-image.
"""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests/fixtures/runtime_state/valid"
for path in (str(TOOLS), str(TOOLS / "tests")):
    if path not in sys.path:
        sys.path.insert(0, path)

from Tools.execution.task_runtime import queue_runtime  # noqa: E402
from Tools.execution.task_runtime.queue_runtime import task_contract  # noqa: E402
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
from Tools.platform.common import kblib  # noqa: E402
from Tools.tests.support.initial_task_plan_fixture import (  # noqa: E402
    FIXTURE_PLAN_RECEIPT_ID,
    FIXTURE_PLAN_RELATIVE,
    FIXTURE_QUEUE_RECEIPT_ID,
)
from Tools.tests.support.profile_fixture import install_loadable_profile  # noqa: E402


class InitialTaskPlanReferenceContractTests(unittest.TestCase):
    def test_progress_requires_one_initial_task_plan_receipt_reference(self):
        errors = task_contract.initial_task_plan_receipt_errors(
            ".", {}, None, {}, None, None, None)

        self.assertEqual(
            ["Progress initial_task_plan_receipt must identify a receipt"],
            errors)


class InitialTaskPlanFixtureIntegrationTests(unittest.TestCase):
    def test_fixture_reconstructs_one_current_plan_to_queue_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(FIXTURE, root)
            install_loadable_profile(root)
            result = runtime_validation.validate_runtime(root)

            self.assertEqual([], result["errors"], result["errors"])
            progress = result["progress"]
            self.assertEqual(
                FIXTURE_PLAN_RECEIPT_ID,
                progress["initial_task_plan_receipt"])
            self.assertEqual(
                FIXTURE_QUEUE_RECEIPT_ID,
                progress["initial_queue_receipt"])
            self.assertEqual(2, result["queue"]["queue_revision"])
            self.assertTrue(result["queue"]["required_queue"])
            for page in result["coverage"]["pages"]:
                self.assertNotIn("authoring_status", page)
                self.assertNotIn("gate_receipts", page)
                self.assertNotIn("property_state", page)

            plan_receipt = result["receipt_catalog"][
                FIXTURE_PLAN_RECEIPT_ID][1]
            self.assertEqual(
                kblib.sha256_file(root / FIXTURE_PLAN_RELATIVE),
                plan_receipt["plan_sha256"])
            self.assertEqual(
                queue_runtime.contract_sha256(progress),
                plan_receipt["contract_sha256"])
            queue_receipt = result["receipt_catalog"][
                FIXTURE_QUEUE_RECEIPT_ID][1]
            self.assertEqual(
                result["queue_sha256"],
                queue_receipt["after_required_queue_sha256"])
            self.assertEqual(
                result["coverage_sha256"],
                queue_receipt["after_coverage_sha256"])


if __name__ == "__main__":
    unittest.main()
