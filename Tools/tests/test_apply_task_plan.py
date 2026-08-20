"""The one writer that turns an empty runtime skeleton into a planned task.

`init_state.py` publishes a namespace and infers nothing: the Contract's five
loaded-set fields are empty, Coverage holds no pages, the Queue is empty. No
writer owned the edge that fills them, so the documented path was to hand-edit
canonical runtime state, which R01 forbids and which records nothing about what
was confirmed. This module pins the writer that closes that edge and, just as
importantly, the refusals that keep it from becoming a way around governance.

Where the transaction stops is as load-bearing as what it writes. It fills the
two adopter inputs -- the Task Contract and the Coverage inventory -- and stops
at the Queue. `check_queue._coverage_provenance_errors` treats both as adopter
inputs until the first Queue materialization and demands a qualified writer
receipt for every canonical write after it; materializing the Queue here would
cross that line and force a new entry into that closed set for no gain, since
`compile_queue --apply` already owns the edge and is already in the set. The
state left in between is not an inconsistent window: it is the unmaterialized
runtime, which `validate_runtime` names with `allow_unmaterialized_queue` and
which `compile_queue.main` sets that same flag to read. Both halves are pinned
below, in sequence, because the claim is about the handoff and not about either
tool alone.

The refusals matter more than the happy path. A tool that can write a Contract
and a Coverage inventory can rewrite a task's scope; the only thing separating
"materialize the plan once" from "change the scope whenever" is that it refuses
a second, different plan. `check_queue._contract_sha256` already freezes the
Contract fingerprint at Queue materialization, so the refusal here agrees with
the machine rather than adding a policy on top of it.
"""

import contextlib
import copy
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
REPOSITORY = TOOLS.parent

for path in (str(TOOLS), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import check_queue  # noqa: E402
import compile_queue  # noqa: E402
import kblib  # noqa: E402
from profile_fixture import install_loadable_profile  # noqa: E402


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "_apply_task_plan_under_test", TOOLS / "apply_task_plan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


apply_task_plan = _load_tool()

TASK_ID = "new-task"
PROFILE = "profiles/sample/profile.md"
PLAN_RELATIVE = ".cambium/deltas/task-plans/TP-001.yaml"

MODULE = "kernel/K00 Standards Control/03 Standards Governance.md"
READ_SET = "kernel/Read Sets/R02 Sample Read Set.md"
CARD = "kernel/Cards/R02 Sample Card.md"
OTHER_CARD = "kernel/Cards/R03 Unselected Card.md"
CARD_INDEX = "kernel/Cards/Card Index.md"
READ_SET_INDEX = "kernel/Read Sets/Read Sets Index.md"

# A real Read Set, not a placeholder string: the contract's load closure is
# resolved by reading these bytes, so a fictional path would make the test
# assert on a declaration the machine never checked.
READ_SET_TEXT = """---
type: read-set
route_id: R02
---

# R02 Sample Read Set

## Purpose

Exercise the load closure with one boundary.

## Load

- [[kernel/K00 Standards Control/03 Standards Governance]]
"""

CARD_TEXT = """# R02 Sample Card

## Purpose

Stand in for a route Card the plan selects.
"""

# The two canonical indexes the derivation reads through check_proof's own
# loader, which requires the registry to cover exactly R01-R13. Only the
# selected route's Read Set is written to disk: the derivation traverses what
# the plan selects and never opens the rest.
ROUTES = ["R%02d" % number for number in range(1, 14)]


def _route_paths(route_id):
    if route_id == "R02":
        return CARD, READ_SET
    if route_id == "R03":
        return OTHER_CARD, "kernel/Read Sets/R03 Unselected Read Set.md"
    return ("kernel/Cards/%s Fixture Card.md" % route_id,
            "kernel/Read Sets/%s Fixture Read Set.md" % route_id)


def _index_text(document_type, with_read_set):
    rows = []
    for route_id in ROUTES:
        card, read_set = _route_paths(route_id)
        rows.append('  - route_id: %s\n    path: "%s"'
                    % (route_id, card if with_read_set else read_set))
        if with_read_set:
            rows.append('    read_set: "%s"' % read_set)
    return ("---\ntype: %s\nregistry_id: kernel-runtime-routes\n"
            "route_registry:\n%s\n---\n\n# Index\n"
            % (document_type, "\n".join(rows)))


CARD_INDEX_TEXT = _index_text("card-index", True)
READ_SET_INDEX_TEXT = _index_text("route-index", False)

PAGE = {
    "path": "Notes/First Owner.md",
    "canonical_owner": "Notes/First Owner.md",
    "type": "concept",
    "tier": "M",
    "priority": "P1",
    "coverage_disposition": "required",
    "authoring_status": "unassessed",
    "prerequisites": [],
    "batch": None,
    "next_batch": "%s-B0" % TASK_ID,
    "gate_receipts": [],
    "property_state": {},
    "deferred_reason": None,
    "reentry_condition": None,
}

BATCH_SPEC = {
    "id": "%s-B0" % TASK_ID,
    "family": "founding",
    "order_hint": 1,
    "source_route": "R02",
    "execution_mode": "serial-integrator",
    "depends_on": [],
    "confirmation_required": False,
    "work_spec_path": None,
    "work_spec_sha256": None,
}


class TaskPlanTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # macOS spells tempfile roots through /var while resolved children use
        # /private/var.  Keep the fixture root in the same canonical namespace
        # as the repository paths resolved by the production loaders.
        self.root = Path(self.tmp.name).resolve() / "repo"
        install_loadable_profile(self.root, profile_id="sample")
        for relative, text in ((READ_SET, READ_SET_TEXT), (CARD, CARD_TEXT),
                               (OTHER_CARD, CARD_TEXT),
                               (CARD_INDEX, CARD_INDEX_TEXT),
                               (READ_SET_INDEX, READ_SET_INDEX_TEXT)):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(TOOLS / "init_state.py"), str(self.root),
             "--task-id", TASK_ID, "--objective", "Exercise task planning",
             "--scope-version", "s1", "--completion-semantics", "build",
             "--standards-version", "3.0.0", "--profile-manifest", PROFILE,
             "--at", "2026-08-04T00:00:00Z", "--apply"],
            text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)

    # ---- helpers -------------------------------------------------------

    def state_sha(self, relative):
        return kblib.sha256_bytes((self.root / relative).read_bytes())

    def document(self, relative):
        return kblib.parse_yaml_subset(
            (self.root / relative).read_text(encoding="utf-8"))

    def compile_the_queue(self, prepared):
        """Run the compiler exactly as the transaction told the operator to."""
        command = apply_task_plan._compile_command(prepared).split()
        self.assertEqual(
            ["python3", "Tools/compile_queue.py", "."], command[:3],
            "the printed command is the handoff; if its shape drifts the "
            "operator is following instructions the test never ran")
        result = subprocess.run(
            [sys.executable, str(TOOLS / "compile_queue.py"), str(self.root)]
            + command[3:],
            text=True, capture_output=True, check=False)
        self.assertEqual(
            0, result.returncode,
            "the writer that owns the Queue must accept the state this "
            "transaction leaves, using the compare-and-swap values it "
            "printed; if it does not, the split between them is wrong:\n"
            + result.stdout + result.stderr)
        return result

    def plan(self, **overrides):
        plan = {
            "schema_version": 1,
            "plan_id": "TP-001",
            "task_id": TASK_ID,
            "approval_reference": "operator confirmation 2026-08-04",
            "before": {
                "coverage_sha256": self.state_sha(check_queue.COVERAGE_PATH),
                "queue_sha256": self.state_sha(check_queue.QUEUE_PATH),
                "progress_sha256": self.state_sha(check_queue.PROGRESS_PATH),
            },
            "contract_after": {
                "contract_version": "c1",
                "completion_semantics": "build",
                "objective": "Exercise task planning",
                "exclusions": [],
                "scope_version": "s1",
                "concurrency_cap": 1,
                "standards_version": "3.0.0",
                "selected_profile_manifest": PROFILE,
                "selected_route_ids": ["R02"],
                "selected_card_paths": [],
                "selected_profile_route_ids": [],
                "selected_read_sets": [],
                "loaded_module_paths": [],
                "minimum_run_until": "",
                "checkpoint_at": "",
                "hard_stop_at": "",
                "completion_gate": "required-queue-complete",
            },
            "coverage_after": {
                "pages": [copy.deepcopy(PAGE)],
                "batch_specs": [copy.deepcopy(BATCH_SPEC)],
            },
        }
        plan.update(overrides)
        return plan

    def write_plan(self, plan, relative=PLAN_RELATIVE):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
        return relative

    def run_tool(self, relative=PLAN_RELATIVE, apply=False):
        command = [str(self.root), "--plan", relative]
        if apply:
            command.append("--apply")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = apply_task_plan.main(command)
        self.printed = buffer.getvalue()
        return code

    def prepare_error(self, plan):
        relative = self.write_plan(plan)
        with self.assertRaises(apply_task_plan.Refusal) as caught:
            apply_task_plan.prepare(str(self.root), relative)
        return str(caught.exception)

    # ---- the edge it closes --------------------------------------------

    def test_a_dry_run_writes_nothing(self):
        before = {name: self.state_sha(path) for name, path in (
            ("coverage", check_queue.COVERAGE_PATH),
            ("queue", check_queue.QUEUE_PATH),
            ("progress", check_queue.PROGRESS_PATH))}
        self.write_plan(self.plan())
        self.assertEqual(0, self.run_tool())
        for name, path in (("coverage", check_queue.COVERAGE_PATH),
                           ("queue", check_queue.QUEUE_PATH),
                           ("progress", check_queue.PROGRESS_PATH)):
            self.assertEqual(before[name], self.state_sha(path), name)

    def test_initial_plan_can_freeze_safe_amendment_authority(self):
        plan = self.plan()
        plan["contract_after"]["amendment_authority"] = {
            "schema_version": 1,
            "authority_id": "AUTH-INITIAL",
            "mode": "user-only",
            "allowed_change_classes": [],
        }
        self.write_plan(plan)

        self.assertEqual(0, self.run_tool(apply=True), self.printed)

        contract = self.document(check_queue.PROGRESS_PATH)["contract"]
        self.assertEqual(plan["contract_after"]["amendment_authority"],
                         contract["amendment_authority"])
        self.assertEqual([], check_queue.validate_runtime(
            str(self.root), allow_unmaterialized_queue=True)["errors"])

    def test_initial_plan_rejects_malformed_amendment_authority(self):
        plan = self.plan()
        plan["contract_after"]["amendment_authority"] = {
            "schema_version": 1,
            "authority_id": "AUTH-INITIAL",
            "mode": "delegated-integrator",
            "allowed_change_classes": ["future-class"],
        }

        message = self.prepare_error(plan)

        self.assertIn("amendment authority", message)
        self.assertIn("future-class", message)

    def test_apply_fills_what_init_state_left_empty(self):
        self.write_plan(self.plan())
        self.assertEqual(0, self.run_tool(apply=True))

        contract = self.document(check_queue.PROGRESS_PATH)["contract"]
        for field in ("selected_route_ids", "selected_card_paths",
                      "selected_read_sets", "loaded_module_paths"):
            with self.subTest(field=field):
                self.assertTrue(
                    contract[field],
                    "%s is what init_state cannot fill and nothing else "
                    "could; if it is still empty the edge is not closed"
                    % field)

        pages = self.document(check_queue.COVERAGE_PATH)["pages"]
        self.assertEqual([PAGE["path"]], [page["path"] for page in pages])
        self.assertFalse(
            (self.root / PAGE["path"]).exists(),
            "the object is Required and recorded before it exists; K02/01 "
            "requires exactly that, and a writer that demanded the file first "
            "could never plan work that has not been done")

    def test_the_load_sets_are_resolved_from_the_routes_not_typed_by_hand(self):
        """The plan answers 'which routes'; the machine answers 'so what loads'.

        This is the derivation that makes the plan writable at all. On the real
        kernel, selecting R01 alone closes over every other Read Set and well
        past a hundred modules, so a transaction that demanded those lists by
        hand would collect a declaration nobody had checked. The plan below
        names one route and no paths.
        """
        plan = self.plan()
        self.assertEqual([], plan["contract_after"]["selected_card_paths"])
        self.assertEqual([], plan["contract_after"]["selected_read_sets"])
        self.assertEqual([], plan["contract_after"]["loaded_module_paths"])

        self.write_plan(plan)
        self.assertEqual(0, self.run_tool(apply=True))
        contract = self.document(check_queue.PROGRESS_PATH)["contract"]
        self.assertEqual([CARD], contract["selected_card_paths"])
        self.assertEqual([READ_SET], contract["selected_read_sets"])
        self.assertEqual(
            [MODULE], contract["loaded_module_paths"],
            "the module comes from the Read Set's own loading boundary, so the "
            "declaration is derived from repository bytes rather than asserted")

    def test_a_card_belonging_to_an_unselected_route_is_refused(self):
        plan = self.plan()
        plan["contract_after"]["selected_card_paths"] = [OTHER_CARD]
        message = self.prepare_error(plan)
        self.assertIn("not in selected_route_ids", message)
        self.assertIn(OTHER_CARD, message)

    def test_an_unregistered_route_is_refused(self):
        """A mistyped route names nothing, and says so instead of resolving."""
        plan = self.plan()
        plan["contract_after"]["selected_route_ids"] = ["R02", "R14"]
        self.assertIn("unregistered route(s): R14", self.prepare_error(plan))

    def test_the_recorded_coverage_is_the_plan_s_own(self):
        self.write_plan(self.plan())
        self.assertEqual(0, self.run_tool(apply=True))
        pages = self.document(check_queue.COVERAGE_PATH)["pages"]
        self.assertEqual([PAGE["path"]], [page["path"] for page in pages])
        self.assertFalse(
            (self.root / PAGE["path"]).exists(),
            "the object is Required and recorded before it exists; K02/01 "
            "requires exactly that, and a writer that demanded the file first "
            "could never plan work that has not been done")

    def test_the_queue_is_left_to_the_writer_that_owns_it(self):
        before = self.state_sha(check_queue.QUEUE_PATH)
        self.write_plan(self.plan())
        prepared = apply_task_plan.prepare(str(self.root), PLAN_RELATIVE)
        self.assertNotIn(
            "queue", prepared["after_text"],
            "the transaction stages no Queue bytes; staging them would put a "
            "second writer on the far side of the materialization line that "
            "_coverage_provenance_errors draws")
        self.assertEqual(0, self.run_tool(apply=True))
        self.assertEqual(
            before, self.state_sha(check_queue.QUEUE_PATH),
            "the Queue file is byte-identical after the transaction")
        self.assertEqual([], self.document(
            check_queue.QUEUE_PATH)["required_queue"])

    def test_what_it_compiles_in_memory_is_the_compiler_s_own_output(self):
        """It proves a Queue is derivable without becoming a second compiler."""
        self.write_plan(self.plan())
        prepared = apply_task_plan.prepare(str(self.root), PLAN_RELATIVE)
        expected, _changed = compile_queue.compile_document(
            self.document(check_queue.QUEUE_PATH),
            {**self.document(check_queue.COVERAGE_PATH),
             "pages": [copy.deepcopy(PAGE)],
             "batch_specs": [copy.deepcopy(BATCH_SPEC)]})
        self.assertEqual(
            kblib.canonical_yaml(expected),
            kblib.canonical_yaml(prepared["queue"]),
            "the plan carries no Queue body precisely so that the Queue has "
            "one authority; the transaction compiles only to refuse a plan "
            "that yields none, and must agree with the real compiler")

    def test_the_state_it_leaves_is_the_unmaterialized_one(self):
        """The whole claim of the split, in the order the two writers run."""
        self.write_plan(self.plan())
        prepared = apply_task_plan.prepare(str(self.root), PLAN_RELATIVE)
        self.assertEqual(0, self.run_tool(apply=True))

        self.assertEqual(
            [], check_queue.validate_runtime(
                str(self.root), allow_unmaterialized_queue=True)["errors"],
            "Coverage naming a batch the Queue does not carry is the "
            "unmaterialized runtime, not a broken one; this is the flag "
            "compile_queue itself sets to read this state")

        self.assertIn(
            apply_task_plan._compile_command(prepared), self.printed,
            "a transaction that stops halfway must say so and name the "
            "command that finishes it; an operator who is not told will read "
            "'committed' as 'done' and leave the Queue unmaterialized")

        self.compile_the_queue(prepared)
        self.assertEqual(
            [BATCH_SPEC["id"]],
            [item["id"] for item in
             self.document(check_queue.QUEUE_PATH)["required_queue"]])
        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"],
            "after the compiler runs the runtime validates with no allowance "
            "at all; if it does not, the transaction left work undone")

    def test_an_unschedulable_plan_is_refused_in_the_compiler_s_own_words(self):
        """This tool states no Queue rule of its own, and needs none.

        Both ways a plan can fail to yield a Queue -- a Required object with
        no batch, and a Coverage inventory with no Required object at all --
        are already refused by the compiler that owns the Queue. Surfacing its
        message verbatim keeps one statement of the rule; adding a parallel
        check here would be exactly the accretion K00/03 asks about.
        """
        no_batch = self.plan()
        no_batch["coverage_after"]["pages"][0]["next_batch"] = None
        message = self.prepare_error(no_batch)
        self.assertIn("the Queue compiler rejects", message)
        self.assertIn("no explicit batch/next_batch", message)

        nothing_required = self.plan()
        nothing_required["coverage_after"]["pages"][0].update(
            {"coverage_disposition": "deferred",
             "next_batch": None,
             "deferred_reason": "not in this task",
             "reentry_condition": "operator revisits scope"})
        nothing_required["coverage_after"]["batch_specs"] = []
        message = self.prepare_error(nothing_required)
        self.assertIn("the Queue compiler rejects", message)
        self.assertIn("no Required objects to compile", message)

    def test_a_receipt_records_the_exact_plan_bytes(self):
        self.write_plan(self.plan())
        self.assertEqual(0, self.run_tool(apply=True))
        receipts = (self.root / apply_task_plan.RECEIPT_PATH).read_text(
            encoding="utf-8").strip().splitlines()
        self.assertTrue(receipts)
        import json
        record = json.loads(receipts[-1])
        self.assertEqual("pass", record["result"])
        self.assertEqual("commit", record["transaction_phase"])
        self.assertNotIn(
            "gate_id", record,
            "this proves a transaction happened, not that a lifecycle "
            "boundary may be crossed; the state it writes is consumed by "
            "gates that already exist")
        self.assertEqual(TASK_ID, record["task_id"])

    def test_existing_page_properties_are_derived_as_legacy_not_asserted(self):
        page_path = self.root / PAGE["path"]
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            "---\ntitle: First\nlast_reviewed: 2026-07-31\n---\nBody\n",
            encoding="utf-8")
        self.write_plan(self.plan())

        prepared = apply_task_plan.prepare(str(self.root), PLAN_RELATIVE)
        coverage = kblib.parse_yaml_subset(
            prepared["after_text"]["coverage"])
        row = coverage["pages"][0]
        self.assertEqual({}, row["property_state"])
        self.assertEqual({
            "last_reviewed": {
                "status": "legacy-unverified",
                "value": "2026-07-31",
            },
        }, row["legacy_property_state"])
        adoption = prepared["property_adoption"]
        self.assertEqual(1, adoption["count"])
        self.assertEqual(
            kblib.sha256_file(page_path),
            adoption["records"][0]["before_page_sha256"])

        self.assertEqual(0, self.run_tool(apply=True), self.printed)
        receipt = json.loads((
            self.root / apply_task_plan.RECEIPT_PATH).read_text(
                encoding="utf-8").splitlines()[-1])
        self.assertEqual(
            adoption["records"], receipt["property_state_adoption_records"])
        self.assertEqual(
            adoption["set_sha256"],
            receipt["property_state_adoption_set_sha256"])
        self.assertEqual(
            adoption["metadata_execution_contract_fingerprint"],
            receipt["metadata_execution_contract_fingerprint"])
        self.assertNotIn(
            "last_reviewed",
            kblib.parse_yaml_subset(kblib.extract_frontmatter(
                page_path.read_text(encoding="utf-8"))),
            "initial adoption must retire the unowned page-side copy in the "
            "same transaction that records the legacy observation")

    def test_property_adoption_page_snapshot_is_rechecked_under_lock(self):
        page_path = self.root / PAGE["path"]
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            "---\nlast_reviewed: 2026-07-31\n---\nBody\n",
            encoding="utf-8")
        self.write_plan(self.plan())
        prepared = apply_task_plan.prepare(str(self.root), PLAN_RELATIVE)
        before = {
            relative: self.state_sha(relative)
            for relative in (
                check_queue.COVERAGE_PATH, check_queue.PROGRESS_PATH)
        }
        page_path.write_text(
            "---\nlast_reviewed: 2026-08-01\n---\nBody\n",
            encoding="utf-8")

        with self.assertRaisesRegex(
                apply_task_plan.Refusal,
                "changed between planning and commit"):
            apply_task_plan.commit(
                prepared, self.root / apply_task_plan.RECEIPT_PATH)
        for relative, fingerprint in before.items():
            self.assertEqual(fingerprint, self.state_sha(relative))

    def test_plan_cannot_supply_its_own_legacy_marker(self):
        plan = self.plan()
        plan["coverage_after"]["pages"][0]["legacy_property_state"] = {
            "last_reviewed": {
                "status": "legacy-unverified",
                "value": "2026-07-31",
            },
        }
        self.assertIn(
            "may not claim legacy property observations",
            self.prepare_error(plan))

    # ---- the refusals that keep it from becoming a back door ------------

    def test_a_second_different_plan_is_refused_after_materialization(self):
        self.write_plan(self.plan())
        self.assertEqual(0, self.run_tool(apply=True))

        second = self.plan()
        second["plan_id"] = "TP-002"
        second["coverage_after"]["pages"][0]["path"] = "Notes/Rewritten.md"
        message = self.prepare_error(second)
        self.assertTrue(
            "Coverage already holds page records" in message
            or "already materialized" in message
            or "prepared against" in message,
            "re-applying a different plan over a materialized runtime would "
            "route a scope change around replan and Amendment: " + message)

    def test_a_moved_runtime_is_refused_rather_than_merged(self):
        plan = self.plan()
        plan["before"]["coverage_sha256"] = "sha256:" + "0" * 64
        self.assertIn("prepared against", self.prepare_error(plan))

    def test_an_unknown_plan_field_fails_closed(self):
        plan = self.plan()
        plan["queue_after"] = {"required_queue": []}
        message = self.prepare_error(plan)
        self.assertIn("unsupported field", message)
        self.assertIn("queue_after", message)

    def test_a_plan_with_no_required_object_is_refused(self):
        plan = self.plan()
        plan["coverage_after"]["pages"] = []
        self.assertIn("pages is empty", self.prepare_error(plan))

    def test_an_unfilled_template_sentinel_is_refused(self):
        plan = self.plan()
        plan["approval_reference"] = apply_task_plan.SENTINEL
        self.assertIn("sentinel", self.prepare_error(plan))

    def test_a_plan_for_another_task_is_refused(self):
        plan = self.plan()
        plan["task_id"] = "some-other-task"
        self.assertIn("records task_id", self.prepare_error(plan))

    def test_a_contract_missing_a_closed_field_is_refused(self):
        plan = self.plan()
        del plan["contract_after"]["selected_read_sets"]
        message = self.prepare_error(plan)
        self.assertIn("missing field", message)
        self.assertIn("selected_read_sets", message)


if __name__ == "__main__":
    unittest.main()
