"""Ownership closure for the initial Task Plan producer boundary.

The semantic owner stops at planning-only Coverage, the frozen Task Contract,
an empty Queue image, and its publication Receipt. Pure shape, projection,
binding, override, and handoff predicates stay in memory. Repository-backed
coverage is limited to one public writer transport and one exact
plan-currentness boundary. The adjacent Queue materialization seam belongs to
``test_compile_queue`` and is not replayed here.
"""

import copy
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
REPOSITORY = TOOLS.parent

for path in (str(TOOLS), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import Tools.execution.planning.apply_task_plan as apply_task_plan  # noqa: E402
from Tools.execution.task_runtime import queue_runtime  # noqa: E402
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
from Tools.tests.support.initial_task_plan_fixture import (  # noqa: E402
    confirmed_initial_task_plan,
)
from Tools.tests.support.profile_fixture import (  # noqa: E402
    FIXTURE_UPSTREAM_REVISION,
    install_loadable_profile,
)


TASK_ID = "new-task"
PROFILE = "profiles/sample/profile.md"
PLAN_RELATIVE = ".cambium/deltas/task-plans/TP-001.yaml"
DIGEST = "sha256:" + "1" * 64
R01_CARD = "Card/R01 Core Bootstrap Card.md"
R02_CARD = "Card/R02 Fixture Card.md"
R01_READ_SET = "Read Set/R01 Core Bootstrap Read Set.md"
R02_READ_SET = "Read Set/R02 Fixture Read Set.md"
LOADED_MODULE = "kernel/K03 Fixture/01 Conditional Review.md"


def _current_plan(**overrides):
    plan = confirmed_initial_task_plan(
        upstream_revision_id=FIXTURE_UPSTREAM_REVISION,
        profile_manifest=PROFILE,
        task_id=TASK_ID,
        plan_id="TP-001",
        objective="Exercise task planning",
    )
    plan["approval_reference"] = "operator confirmation 2026-08-31"
    plan.update(overrides)
    return plan


class TaskPlanSchemaContractTests(unittest.TestCase):

    def test_current_plan_and_shipped_template_share_one_closed_schema(self):
        plan = _current_plan()
        apply_task_plan._validate_plan_shape(plan)

        template = kblib.load_yaml_file(
            REPOSITORY / "Tools/schemas/task_plan.template.yaml")
        self.assertEqual(plan["schema_version"], template["schema_version"])
        self.assertEqual(apply_task_plan.PLAN_FIELDS, set(template))
        self.assertEqual(apply_task_plan.PLANNED_WORK_FIELDS,
                         set(template["planned_work"]))
        for field in ("authoring_status", "gate_receipts", "property_state"):
            self.assertNotIn(field, template["planned_work"]["pages"][0])

        cases = []
        wrong_schema = _current_plan(schema_version=3)
        cases.append((wrong_schema, "schema_version must be 4"))
        unknown = _current_plan()
        unknown["unexpected_field"] = "unsupported"
        cases.append((unknown, "unsupported field.*unexpected_field"))
        unanswered = _current_plan(
            approval_reference=apply_task_plan.SENTINEL)
        cases.append((unanswered, "template.*sentinel"))
        current_page_state = _current_plan()
        current_page_state["planned_work"]["pages"][0][
            "authoring_status"] = "reviewed"
        cases.append((current_page_state, "materializes runtime state"))

        for candidate, expected in cases:
            with self.subTest(expected=expected), self.assertRaisesRegex(
                    apply_task_plan.Refusal, expected):
                apply_task_plan._validate_plan_shape(candidate)


class TaskPlanProjectionUnitTests(unittest.TestCase):

    def test_projection_stops_at_planning_coverage_and_an_empty_queue(self):
        plan = _current_plan()
        original = copy.deepcopy(plan)
        queue = apply_task_plan._empty_queue(plan)
        queue_text = kblib.canonical_yaml(queue)
        coverage = apply_task_plan._coverage(
            plan, "2026-08-31T00:00:00Z")
        progress = apply_task_plan._progress(
            plan, copy.deepcopy(plan["contract_after"]), queue_text,
            "R-TASK-PLAN")

        self.assertEqual(original, plan)
        self.assertEqual([], queue["required_queue"])
        self.assertEqual(1, queue["queue_revision"])
        self.assertEqual(0, queue["state_revision"])
        self.assertEqual(plan["planned_work"]["pages"], coverage["pages"])
        self.assertEqual(plan["planned_work"]["batch_specs"],
                         coverage["batch_specs"])
        self.assertEqual("planned", progress["task_state"])
        self.assertEqual("R-TASK-PLAN",
                         progress["initial_task_plan_receipt"])
        self.assertIsNone(progress["initial_queue_receipt"])
        self.assertEqual(kblib.sha256_bytes(queue_text),
                         progress["required_queue_sha256"])
        self.assertEqual(plan["contract_after"], progress["contract"])


class TaskPlanProfileOverrideContractTests(unittest.TestCase):

    def test_concurrency_cap_acceptance_has_one_explicit_source_contract(self):
        self.assertEqual(
            (3, "task-plan"),
            apply_task_plan._resolve_concurrency_cap_overrides({}, 3))
        self.assertEqual(
            (3, "task-plan+profile-manifest"),
            apply_task_plan._resolve_concurrency_cap_overrides(
                {"concurrency_cap": "3"}, 3))

        for overrides, expected in (
                ({"concurrency_cap": "4"}, "contradicts"),
                ({"concurrency_cap": "0"}, "malformed"),
                ({"concurrency_cap": "three"}, "malformed")):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(
                    apply_task_plan.Refusal, expected):
                apply_task_plan._resolve_concurrency_cap_overrides(
                    overrides, 3)


class TaskPlanBindingContractTests(unittest.TestCase):

    def test_receipt_and_queue_handoff_bind_one_exact_plan_after_image(self):
        plan = _current_plan()
        evidence = {
            "selected_profile_manifest": PROFILE,
            "profile_snapshot_sha256": "sha256:" + "2" * 64,
            "profile_contract_fingerprint": "sha256:" + "3" * 64,
            "profile_load_inputs_sha256": "sha256:" + "4" * 64,
        }
        receipt = apply_task_plan._receipt(
            plan, PLAN_RELATIVE, DIGEST, evidence)
        self.assertEqual([], apply_task_plan.current_receipt_errors(receipt))
        wrong_selector = copy.deepcopy(receipt)
        wrong_selector["check"] = "queue_structure"
        self.assertTrue(
            apply_task_plan.current_receipt_errors(wrong_selector))
        self.assertEqual(PLAN_RELATIVE, receipt["plan_path"])
        self.assertEqual(DIGEST, receipt["plan_sha256"])
        self.assertEqual(1, receipt["planning_record_count"])
        self.assertEqual(1, receipt["batch_spec_count"])

        queue = apply_task_plan._empty_queue(plan)
        command = shlex.split(apply_task_plan.compile_command({
            "state_documents": {"queue": queue},
            "state_sha": {"queue": DIGEST},
        }))
        self.assertEqual(
            ["python3", "Tools/compile_queue.py", "."], command[:3])
        self.assertEqual(
            ["--apply", "--actor-role", "integrator",
             "--expected-queue-revision", "1",
             "--expected-sha256", DIGEST],
            command[3:])


class TaskPlanLoadSetContractTests(unittest.TestCase):

    @staticmethod
    def _registry_patches():
        cards = {
            "R01": {"path": R01_CARD},
            "R02": {"path": R02_CARD},
            "R03": {"path": "Card/R03 Fixture Card.md"},
        }
        read_sets = {
            "R01": {"path": R01_READ_SET},
            "R02": {"path": R02_READ_SET},
            "R03": {"path": "Read Set/R03 Fixture Read Set.md"},
        }
        return (
            mock.patch.object(
                apply_task_plan.stamp_cards, "discover_cards",
                return_value=(cards, read_sets)),
            mock.patch.object(
                apply_task_plan.queue_runtime, "read_set_load_closure",
                return_value=(
                    {R01_READ_SET, R02_READ_SET},
                    {LOADED_MODULE}, [], [],
                )),
        )

    def test_routes_are_the_only_owner_of_derived_cards_and_read_sets(self):
        discover, closure = self._registry_patches()
        with discover, closure:
            contract = copy.deepcopy(_current_plan()["contract_after"])
            derived = apply_task_plan._derive_load_sets(".", contract)
            self.assertEqual(["R01", "R02"],
                             contract["selected_route_ids"])
            self.assertEqual([R01_CARD, R02_CARD],
                             contract["selected_card_paths"])
            self.assertEqual([R01_READ_SET, R02_READ_SET],
                             contract["selected_read_sets"])
            self.assertEqual([LOADED_MODULE],
                             contract["loaded_module_paths"])
            self.assertEqual(
                {"routes": 2, "read_sets": 2, "modules": 1}, derived)

            unknown = copy.deepcopy(_current_plan()["contract_after"])
            unknown["selected_route_ids"] = ["R99"]
            with self.assertRaisesRegex(
                    apply_task_plan.Refusal, "unregistered route.*R99"):
                apply_task_plan._derive_load_sets(".", unknown)

            foreign = copy.deepcopy(_current_plan()["contract_after"])
            foreign["selected_card_paths"] = [
                "Card/R03 Fixture Card.md"]
            with self.assertRaisesRegex(
                    apply_task_plan.Refusal,
                    "whose route is not in selected_route_ids"):
                apply_task_plan._derive_load_sets(".", foreign)


def _write_plan(root, plan):
    path = root / PLAN_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")


class TaskPlanPublicationIntegrationTests(unittest.TestCase):

    def test_cli_json_publishes_one_planning_state_and_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = (Path(temporary) / "repo").resolve()
            install_loadable_profile(root, profile_id="sample")
            plan = _current_plan()
            _write_plan(root, plan)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "init_state.py"),
                    str(root),
                    "--plan", PLAN_RELATIVE,
                    "--apply",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            emitted = json.loads(completed.stdout)
            self.assertEqual(1, len(emitted))
            self.assertEqual([], apply_task_plan.current_receipt_errors(
                emitted[0]))

            result = runtime_validation.validate_runtime(
                root, allow_unmaterialized_queue=True)
            self.assertEqual([], result["errors"])
            self.assertEqual([], result["queue"]["required_queue"])
            self.assertIsNone(result["progress"]["initial_queue_receipt"])
            self.assertEqual(
                emitted[0]["receipt_id"],
                result["progress"]["initial_task_plan_receipt"])
            self.assertEqual(
                plan["planned_work"]["pages"], result["coverage"]["pages"])
            contract = result["progress"]["contract"]
            self.assertEqual(["R01", "R02"], contract["selected_route_ids"])
            self.assertEqual([R01_CARD, R02_CARD],
                             contract["selected_card_paths"])
            self.assertEqual([R01_READ_SET, R02_READ_SET],
                             contract["selected_read_sets"])
            self.assertEqual([LOADED_MODULE], contract["loaded_module_paths"])
            persisted = [json.loads(line) for line in (
                root / apply_task_plan.RECEIPT_PATH
            ).read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual([emitted[0]], persisted)
            with self.assertRaisesRegex(
                    apply_task_plan.Refusal, "already exists"):
                apply_task_plan.prepare(str(root), PLAN_RELATIVE)


class TaskPlanCurrentnessIntegrationTests(unittest.TestCase):

    def test_changed_plan_bytes_fail_the_prepublication_cas(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = _current_plan()
            _write_plan(root, original)
            prepared = {
                "root": str(root),
                "plan_path": PLAN_RELATIVE,
                "plan_sha": kblib.sha256_file(root / PLAN_RELATIVE),
                "authority": {
                    "active_standards_view": {},
                    "profile_view": {},
                },
            }
            changed = copy.deepcopy(original)
            changed["approval_reference"] = "different confirmation"
            _write_plan(root, changed)

            with self.assertRaisesRegex(
                    apply_task_plan.Refusal, "confirmed Task Plan changed"):
                apply_task_plan.require_current(
                    prepared, "pre-publication")
            self.assertFalse((root / queue_runtime.COVERAGE_PATH).exists())
            self.assertFalse((root / apply_task_plan.RECEIPT_PATH).exists())


if __name__ == "__main__":
    unittest.main()
