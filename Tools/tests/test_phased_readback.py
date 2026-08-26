"""Acceptance for `card-first-phased-readback-v4`.

The protocol's whole claim is that moving *when* frozen bytes travel costs
nothing in what can be proved.  These tests therefore pair every capability
with the negative control that would make it hollow: a phase that packs is
matched by a phase that must not be split, an ack that satisfies a gate is
matched by a stale-but-complete ack chain that must not, and an actor's own
evidence is matched by somebody else's evidence being refused.
"""

import copy
import json
import os
import subprocess
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import card_activation
import check_queue
import kblib
from profile_fixture import install_loadable_profile


CONTEXT = "mcp:1111111111111111111111111111aaaa"
OTHER_CONTEXT = "mcp:2222222222222222222222222222bbbb"


def add_conditional_routes(root, routes=("R09", "R12")):
    """Select already declared conditional routes in the shared fixture."""
    progress_path = root / ".cambium/state/progress_ledger.yaml"
    progress = kblib.load_yaml_file(progress_path)
    contract = progress["contract"]
    contract["selected_route_ids"] = sorted(
        set(contract["selected_route_ids"]) | set(routes))
    contract["selected_card_paths"] = sorted(
        set(contract["selected_card_paths"]) |
        {"Card/%s Fixture Card.md" % route for route in routes})
    contract["selected_read_sets"] = sorted(
        set(contract["selected_read_sets"]) |
        {"Read Set/%s Fixture Read Set.md" % route
         for route in routes})
    progress_path.write_text(kblib.canonical_yaml(progress), encoding="utf-8")
    # The contract is anchored by the initial task transition; widening the
    # route set without moving that anchor would leave the fixture claiming
    # a contract it no longer holds.
    receipt_path = root / ".cambium/receipts/task-transitions.jsonl"
    records = [json.loads(line) for line
               in receipt_path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    for record in records:
        if record.get("receipt_id") == "audit-fixture-initial-queue":
            record["contract_sha256"] = kblib.sha256_bytes(
                kblib.canonical_yaml(contract))
            record["after_progress_sha256"] = kblib.sha256_file(progress_path)
    receipt_path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n"
                for record in records), encoding="utf-8")


class PhasedActivationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        add_conditional_routes(self.root)

    def runtime(self):
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"], result["errors"])
        return result

    def context(self, execution_context_id=CONTEXT, batch="B1"):
        runtime = self.runtime()
        return card_activation.build_activation_context(
            self.root, runtime["progress"], runtime["items_by_id"][batch],
            runtime_state=runtime,
            execution_context_id=execution_context_id)

    def plan(self, context=None):
        context = context or self.context()
        return context["activation_bundle_manifest"]["phase_plan"]

    def registry(self):
        return card_activation._route_registry(self.root)[0]

    # ---- the plan itself ------------------------------------------------

    def test_every_frozen_piece_belongs_to_exactly_one_phase(self):
        context = self.context()
        pieces = context["activation_bundle_manifest"]["pieces"]
        planned = []
        for phase in self.plan(context)["phases"]:
            planned.extend(phase["piece_ids"])
        self.assertEqual(sorted(row["piece_id"] for row in pieces),
                         sorted(planned))
        self.assertEqual(len(planned), len(set(planned)))
        for row in pieces:
            self.assertIn(row["phase"], card_activation.PHASES)

    def test_the_phase_set_is_closed_and_ordered(self):
        self.assertEqual(
            list(card_activation.PHASE_ORDER),
            [phase["phase_id"] for phase in self.plan()["phases"]])

    def test_conditional_phases_are_frozen_but_not_in_preflight(self):
        # The point of freezing a phase nobody may enter is that entering it
        # later proves what it always was, instead of resolving it afresh
        # under whatever the repository looks like by then.
        by_id = {phase["phase_id"]: phase for phase in self.plan()["phases"]}
        preflight = set(by_id[card_activation.PHASE_BATCH_PREFLIGHT]
                        ["piece_ids"])
        for phase_id in card_activation.CONDITIONAL_PHASES:
            self.assertTrue(by_id[phase_id]["conditional"])
            self.assertEqual(
                set(), preflight & set(by_id[phase_id]["piece_ids"]))

    def test_governance_routes_leave_the_preflight_phase(self):
        context = self.context()
        by_id = {row["piece_id"]: row
                 for row in context["activation_bundle_manifest"]["pieces"]}
        governance = [row for row in by_id.values()
                      if row.get("route_id") == "R09"]
        if not governance:
            self.skipTest("fixture contract selects no governance route")
        for row in governance:
            self.assertEqual(card_activation.PHASE_GOVERNANCE, row["phase"])

    def test_the_plan_freezes_what_resolved_it(self):
        environment = self.plan()["environment"]
        for field in ("standards_version", "selected_profile_manifest",
                      "profile_snapshot_sha256",
                      "profile_contract_fingerprint", "resolver_version",
                      "card_index_sha256", "task_contract_sha256"):
            self.assertTrue(environment.get(field), field)
        self.assertEqual(card_activation.PHASE_RESOLVER_VERSION,
                         environment["resolver_version"])

    def test_the_plan_hash_binds_the_plan(self):
        context = self.context()
        self.assertEqual([], card_activation.activation_context_errors(context))
        broken = copy.deepcopy(context)
        broken["activation_bundle_manifest"]["phase_plan"]["phases"][0][
            "piece_ids"] = []
        self.assertTrue(card_activation.activation_context_errors(broken))

    def test_a_standard_phase_must_fit_one_part(self):
        for phase in self.plan()["phases"]:
            if phase["phase_id"] in card_activation.STANDARD_PHASES:
                self.assertLessEqual(
                    phase["part_count"], 1,
                    "%s was cut too wide" % phase["phase_id"])

    def test_every_part_fits_the_delivery_budget(self):
        for phase in self.plan()["phases"]:
            for part in phase["parts"]:
                self.assertLessEqual(
                    part["envelope_bytes"],
                    card_activation.MAX_ACTIVATION_PIECE_ENVELOPE_BYTES)

    # ---- narrowing ------------------------------------------------------

    def test_work_spec_narrowing_moves_unused_routes_out_of_preflight(self):
        routes = ["R01", "R05", "R09"]
        assignment = card_activation.resolve_route_phases(
            routes, self.registry(), narrowing=["R01"])
        self.assertEqual(card_activation.PHASE_BATCH_PREFLIGHT,
                         assignment["R01"])
        # A narrowed-away route is still reachable, just not at startup.
        self.assertEqual(card_activation.PHASE_BATCH_RUNNING,
                         assignment["R05"])
        # An override is not a work route and narrowing cannot move it.
        self.assertEqual(card_activation.PHASE_GOVERNANCE, assignment["R09"])

    def test_silence_is_not_a_narrowing_claim(self):
        assignment = card_activation.resolve_route_phases(
            ["R01", "R05"], self.registry(), narrowing=None)
        self.assertEqual(card_activation.PHASE_BATCH_PREFLIGHT,
                         assignment["R05"])

    def test_a_batch_that_is_not_a_targeted_audit_does_not_owe_r12(self):
        # R12's Card states scenarios and the Work Spec is where a batch says
        # which one it is.  Without this, selecting R12 once at task level
        # charges every batch for an audit almost none of them run -- the
        # exact waste this protocol exists to remove.
        assignment = card_activation.resolve_route_phases(
            ["R01", "R05", "R12"], self.registry(),
            narrowing=["R01", "R05"])
        self.assertEqual(card_activation.PHASE_BATCH_RUNNING,
                         assignment["R12"])

    def test_a_batch_that_names_r12_owes_the_gate_phase(self):
        assignment = card_activation.resolve_route_phases(
            ["R01", "R05", "R12"], self.registry(),
            narrowing=["R01", "R12"])
        self.assertEqual(card_activation.PHASE_BATCH_GATE, assignment["R12"])
        self.assertEqual(card_activation.PHASE_BATCH_RUNNING,
                         assignment["R05"])

    def test_narrowing_cannot_waive_a_task_level_obligation(self):
        # R08/R09 are entered by a transition no Work Spec decides, and R01
        # is presumed by every phase.  A batch may narrow what it is doing,
        # never what the task may do.
        assignment = card_activation.resolve_route_phases(
            ["R01", "R08", "R09", "R12"], self.registry(),
            narrowing=["R05"])
        self.assertEqual(card_activation.PHASE_BATCH_PREFLIGHT,
                         assignment["R01"])
        self.assertEqual(card_activation.PHASE_TASK_COMPLETION,
                         assignment["R08"])
        self.assertEqual(card_activation.PHASE_GOVERNANCE, assignment["R09"])
        self.assertEqual(card_activation.PHASE_BATCH_RUNNING,
                         assignment["R12"])
        self.assertTrue(self.registry()["R12"][
            "read_set_declaration"]["narrowable"])

    def test_an_unrevised_work_spec_still_owes_r12(self):
        assignment = card_activation.resolve_route_phases(
            ["R01", "R12"], self.registry(), narrowing=None)
        self.assertEqual(card_activation.PHASE_BATCH_GATE, assignment["R12"])

    # ---- delivery and ack ----------------------------------------------

    def deliver(self, phase_id, part=0, context=None,
                execution_context_id=CONTEXT):
        context = context or self.context(execution_context_id)
        return card_activation.build_phase_delivery(
            self.root, context, phase_id, part,
            execution_context_id=execution_context_id)

    def test_a_part_carries_whole_files_and_a_trailing_nonce(self):
        delivery = self.deliver(card_activation.PHASE_BATCH_PREFLIGHT)
        payload = delivery["activation_phase_payload"]
        self.assertEqual(card_activation.PHASE_DELIVERY_PROTOCOL,
                         payload["phase_protocol"])
        self.assertEqual(list(payload)[-1], "delivery_nonce")
        for piece in payload["pieces"]:
            self.assertEqual(
                piece["sha256"],
                kblib.sha256_bytes(piece["content"].encode("utf-8")))

    def test_ack_returns_to_the_delivering_context_only(self):
        delivery = self.deliver(card_activation.PHASE_BATCH_PREFLIGHT)
        ack = card_activation.build_phase_ack(
            delivery, delivery["delivery_nonce"],
            execution_context_id=CONTEXT)
        self.assertEqual(card_activation.PHASE_ACK_PROTOCOL,
                         ack["phase_ack_protocol"])
        with self.assertRaisesRegex(ValueError, "delivering execution"):
            card_activation.build_phase_ack(
                delivery, delivery["delivery_nonce"],
                execution_context_id=OTHER_CONTEXT)

    def test_a_wrong_nonce_is_refused(self):
        delivery = self.deliver(card_activation.PHASE_BATCH_PREFLIGHT)
        with self.assertRaisesRegex(ValueError, "nonce"):
            card_activation.build_phase_ack(
                delivery, "0" * 32, execution_context_id=CONTEXT)

    def test_delivery_refuses_a_part_that_does_not_exist(self):
        with self.assertRaisesRegex(ValueError, "part"):
            self.deliver(card_activation.PHASE_BATCH_PREFLIGHT, part=99)

    def test_delivery_refuses_an_unregistered_phase(self):
        with self.assertRaisesRegex(ValueError, "registered phase"):
            self.deliver("batch-whenever")

    def test_a_source_that_drifts_after_admission_is_refused(self):
        context = self.context()
        record = card_activation.phase_record(
            context, card_activation.PHASE_BATCH_PREFLIGHT)
        piece_id = record["parts"][0]["piece_ids"][0]
        frozen = next(row for row
                      in context["activation_bundle_manifest"]["pieces"]
                      if row["piece_id"] == piece_id)
        target = self.root / frozen["path"]
        target.write_text(target.read_text(encoding="utf-8") + "\ndrift\n",
                          encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "drifted"):
            self.deliver(card_activation.PHASE_BATCH_PREFLIGHT,
                         context=context)

    # ---- the authoritative pointer --------------------------------------

    def test_the_attempt_id_is_derived_from_bundle_and_context(self):
        context = self.context()
        delivery = self.deliver(card_activation.PHASE_BATCH_PREFLIGHT,
                                context=context)
        self.assertEqual(
            card_activation.expected_delivery_attempt_id(
                context["card_bundle_sha256"], CONTEXT),
            delivery["delivery_attempt_id"])

    def test_another_context_derives_another_attempt(self):
        context = self.context()
        self.assertNotEqual(
            card_activation.expected_delivery_attempt_id(
                context["card_bundle_sha256"], CONTEXT),
            card_activation.expected_delivery_attempt_id(
                context["card_bundle_sha256"], OTHER_CONTEXT))

    def test_a_superseded_bundle_derives_another_attempt(self):
        # This is what makes a complete-but-stale ack chain fail: the chain
        # stays internally consistent and simply stops matching the pointer.
        context = self.context()
        self.assertNotEqual(
            card_activation.expected_delivery_attempt_id(
                context["card_bundle_sha256"], CONTEXT),
            card_activation.expected_delivery_attempt_id(
                "sha256:" + ("0" * 64), CONTEXT))


class PhaseGateConsumerTests(unittest.TestCase):
    """The gate predicate itself, exercised without a live receipt store."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        add_conditional_routes(self.root)
        self.result = check_queue.validate_runtime(self.root)
        self.assertEqual([], self.result["errors"], self.result["errors"])
        self.item = self.result["items_by_id"]["B1"]
        self.context = card_activation.build_activation_context(
            self.root, self.result["progress"], self.item,
            runtime_state=self.result, execution_context_id=CONTEXT)

    def catalog_with(self, *receipts):
        catalog = dict(check_queue.current_receipt_catalog(self.result))
        activation = dict(
            card_activation.activation_receipt_binding(self.context),
            tool=check_queue.TOOL, tool_version=check_queue.TOOL_VERSION,
            receipt_id="audit-activation-1")
        catalog["audit-activation-1"] = ("x", activation)
        for index, receipt in enumerate(receipts):
            catalog["audit-ack-%d" % index] = ("x", receipt)
        view = dict(self.result)
        view["current_receipt_catalog"] = catalog
        view["receipt_catalog"] = catalog
        return view, dict(self.item, activation_receipt="audit-activation-1")

    def ack_for(self, phase_id, part=0, context_id=CONTEXT,
                bundle_sha=None):
        delivery = card_activation.build_phase_delivery(
            self.root, self.context, phase_id, part,
            execution_context_id=context_id)
        ack = card_activation.build_phase_ack(
            delivery, delivery["delivery_nonce"],
            execution_context_id=context_id)
        if bundle_sha is not None:
            ack = dict(ack, card_bundle_sha256=bundle_sha)
        return dict(card_activation.phase_ack_receipt_binding(ack),
                    result="pass", invalidated_by=None)

    def test_an_undelivered_phase_blocks_the_actor(self):
        view, item = self.catalog_with()
        errors = check_queue.activation_phase_delivery_errors(
            view, item, card_activation.PHASE_BATCH_GATE,
            actor_context_id=CONTEXT)
        gate = card_activation.phase_piece_ids(
            self.context, card_activation.PHASE_BATCH_GATE)
        if not gate:
            self.skipTest("fixture gate phase is empty")
        self.assertTrue(errors)

    def test_a_delivered_phase_admits_the_actor(self):
        gate = card_activation.phase_record(
            self.context, card_activation.PHASE_BATCH_GATE)
        if not gate["piece_ids"]:
            self.skipTest("fixture gate phase is empty")
        acks = [self.ack_for(card_activation.PHASE_BATCH_GATE, index)
                for index in range(gate["part_count"])]
        view, item = self.catalog_with(*acks)
        self.assertEqual([], check_queue.activation_phase_delivery_errors(
            view, item, card_activation.PHASE_BATCH_GATE,
            actor_context_id=CONTEXT))

    def test_another_actors_complete_chain_is_refused(self):
        gate = card_activation.phase_record(
            self.context, card_activation.PHASE_BATCH_GATE)
        if not gate["piece_ids"]:
            self.skipTest("fixture gate phase is empty")
        acks = [self.ack_for(card_activation.PHASE_BATCH_GATE, index,
                             context_id=OTHER_CONTEXT)
                for index in range(gate["part_count"])]
        view, item = self.catalog_with(*acks)
        errors = check_queue.activation_phase_delivery_errors(
            view, item, card_activation.PHASE_BATCH_GATE,
            actor_context_id=CONTEXT)
        self.assertTrue(errors)
        self.assertIn("not delivered to this actor", errors[0])
        # The same chain is still valid history for an integrator, which
        # checks that the phase was earned, not that it earned it.
        self.assertEqual([], check_queue.activation_phase_delivery_errors(
            view, item, card_activation.PHASE_BATCH_GATE))

    def test_two_complete_chains_do_not_block_each_other(self):
        # A bound edge asks whether THIS actor read the Card, which another
        # context's chain cannot answer either way.  Reading foreignness as
        # the fault rather than one's own absence wedged both contexts at
        # once, and wedged the integrator on top of them.
        gate = card_activation.phase_record(
            self.context, card_activation.PHASE_BATCH_GATE)
        if not gate["piece_ids"]:
            self.skipTest("fixture gate phase is empty")
        acks = []
        for context_id in (CONTEXT, OTHER_CONTEXT):
            acks.extend(
                self.ack_for(card_activation.PHASE_BATCH_GATE, index,
                             context_id=context_id)
                for index in range(gate["part_count"]))
        view, item = self.catalog_with(*acks)
        for context_id in (CONTEXT, OTHER_CONTEXT):
            self.assertEqual(
                [], check_queue.activation_phase_delivery_errors(
                    view, item, card_activation.PHASE_BATCH_GATE,
                    actor_context_id=context_id),
                "%s earned the phase and must not be refused for the "
                "existence of the other chain" % context_id)
        self.assertEqual([], check_queue.activation_phase_delivery_errors(
            view, item, card_activation.PHASE_BATCH_GATE))

    def test_a_union_of_two_partial_chains_is_not_a_delivery(self):
        # Completeness is per attempt.  Two half-deliveries to two contexts
        # leave neither able to say it read the phase, and unioning them
        # manufactures a reader that never existed.
        # Preflight is the phase the fixture gives more than one piece, so it
        # is the one that can be halved at all.
        phase_id = card_activation.PHASE_BATCH_PREFLIGHT
        record = card_activation.phase_record(self.context, phase_id)
        pieces = list(record["piece_ids"])
        self.assertGreaterEqual(
            len(pieces), 2,
            "this test needs a phase with something to split; if the fixture "
            "shrank, move it to one that still has two pieces rather than "
            "letting it skip")
        cut = len(pieces) // 2
        halves = (pieces[:cut], pieces[cut:])
        acks = []
        for context_id, half in zip((CONTEXT, OTHER_CONTEXT), halves):
            for index in range(record["part_count"]):
                ack = self.ack_for(phase_id, index, context_id=context_id)
                acks.append(dict(ack, phase_piece_ids=list(half)))
        view, item = self.catalog_with(*acks)
        for actor in (CONTEXT, OTHER_CONTEXT, None):
            errors = check_queue.activation_phase_delivery_errors(
                view, item, phase_id, actor_context_id=actor)
            self.assertTrue(
                errors, "a union across attempts must not read as delivered "
                        "(actor=%s)" % actor)

    def test_a_prepared_activation_is_exempt(self):
        prepared = card_activation.build_activation_context(
            self.root, self.result["progress"], self.item,
            runtime_state=self.result, execution_context_id=None)
        self.assertEqual("prepared", prepared["delivery_assurance"])
        catalog = dict(check_queue.current_receipt_catalog(self.result))
        catalog["audit-activation-1"] = ("x", dict(
            card_activation.activation_receipt_binding(prepared),
            tool=check_queue.TOOL, tool_version=check_queue.TOOL_VERSION))
        view = dict(self.result, current_receipt_catalog=catalog,
                    receipt_catalog=catalog)
        item = dict(self.item, activation_receipt="audit-activation-1")
        self.assertEqual([], check_queue.activation_phase_delivery_errors(
            view, item, card_activation.PHASE_BATCH_GATE,
            actor_context_id=CONTEXT))

    def test_native_read_channel_may_not_mint_transport_assurance(self):
        # The ceiling itself is the assertion.  Testing only that a missing
        # ack fails would leave the channel free to claim transport once an
        # ack arrives, which is precisely the conflation this registry was
        # restructured to prevent.
        registry = kblib.parse_yaml_subset(
            (TOOLS / "host-conformance.yaml").read_text(encoding="utf-8"))
        self.assertEqual(2, registry["schema_version"])
        channels = {row["channel_id"]: row for row in registry["channels"]}
        native = channels["agent-native-file-read"]
        self.assertFalse(native["proves_transport"])
        self.assertTrue(native["proves_identity"])
        self.assertTrue(native["proves_acknowledgement"])
        for channel_id in ("inline-mcp", "remote-bundle"):
            self.assertTrue(channels[channel_id]["proves_transport"])
            self.assertEqual(
                card_activation.MAX_ACTIVATION_PIECE_ENVELOPE_BYTES,
                channels[channel_id]["minimum_bytes"])

    def test_control_plane_predicate_is_about_the_manifest(self):
        self.assertFalse(check_queue.batch_touches_control_plane(
            {"manifest": ["Topics/A.md"]}))
        self.assertTrue(check_queue.batch_touches_control_plane(
            {"manifest": ["Topics/A.md", "kernel/K00 Standards Overview.md"]}))
        self.assertTrue(check_queue.batch_touches_control_plane(
            {"manifest": ["profiles/some-adopter/profile.md"]}))


class PhaseCliTests(unittest.TestCase):
    """The CLI round trip, because the library round trip is not the same one.

    The first phase delivery through the CLI produced a receipt with every
    phase field missing: the library call was correct and the tool simply
    never handed its result to the receipt writer.  A library-only suite
    cannot see that, so this exercises the actual command.
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        add_conditional_routes(self.root)

    def run_tool(self, name, *arguments, context_id=CONTEXT):
        environ = dict(os.environ)
        environ[card_activation.EXECUTION_CONTEXT_ENV] = context_id
        return subprocess.run(
            [sys.executable, str(TOOLS / name), str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environ, check=False)

    def open_b1(self):
        ready = self.run_tool(
            "check_queue.py", "--require-ready", "B1",
            "--receipts", ".cambium/receipts/ready.jsonl", "--json")
        self.assertEqual(0, ready.returncode, ready.stderr)
        receipt = json.loads(ready.stdout)[0]
        self.assertEqual("host-bound", receipt["delivery_assurance"])
        self.assertIn("phase_plan_sha256", receipt)
        queue = kblib.load_yaml_file(self.root / check_queue.QUEUE_PATH)
        opened = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "open",
            "--gate-receipt", receipt["receipt_id"],
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--apply")
        self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)
        return receipt

    def test_phase_delivery_and_ack_round_trip_through_the_cli(self):
        self.open_b1()
        delivered = self.run_tool(
            "check_queue.py", "--deliver-phase", "B1",
            "--phase", card_activation.PHASE_BATCH_PREFLIGHT,
            "--receipts", ".cambium/receipts/phase.jsonl", "--json")
        self.assertEqual(0, delivered.returncode, delivered.stderr)
        delivery = json.loads(delivered.stdout)[0]
        # The regression this pins: the tool result and the receipt both
        # have to carry the phase, not just the library return value.
        self.assertEqual(card_activation.PHASE_BATCH_PREFLIGHT,
                         delivery["phase_id"])
        self.assertEqual(0, delivery["part_index"])
        self.assertTrue(delivery["phase_piece_ids"])
        self.assertTrue(delivery["delivery_nonce"])
        payload = delivery["activation_phase_payload"]
        self.assertEqual(len(delivery["phase_piece_ids"]),
                         len(payload["pieces"]))

        persisted = json.loads((
            self.root / ".cambium/receipts/phase.jsonl"
        ).read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(card_activation.PHASE_BATCH_PREFLIGHT,
                         persisted["phase_id"])
        # Bytes ride the tool result; the register keeps identities only.
        self.assertNotIn("activation_phase_payload", persisted)
        self.assertNotIn("content", json.dumps(persisted, sort_keys=True))

        acked = self.run_tool(
            "check_queue.py", "--ack-activation-phase", "B1",
            "--phase", card_activation.PHASE_BATCH_PREFLIGHT,
            "--phase-nonce", delivery["delivery_nonce"],
            "--phase-delivery-receipt", delivery["receipt_id"],
            "--receipts", ".cambium/receipts/phase-ack.jsonl", "--json")
        self.assertEqual(0, acked.returncode, acked.stderr)
        ack = json.loads(acked.stdout)[0]
        self.assertEqual(card_activation.PHASE_ACK_PROTOCOL,
                         ack["phase_ack_protocol"])
        self.assertEqual(delivery["delivery_attempt_id"],
                         ack["delivery_attempt_id"])
        self.assertEqual(sorted(delivery["phase_piece_ids"]),
                         sorted(ack["phase_piece_ids"]))

    def test_the_cli_refuses_an_ack_from_another_context(self):
        self.open_b1()
        delivered = self.run_tool(
            "check_queue.py", "--deliver-phase", "B1",
            "--phase", card_activation.PHASE_BATCH_PREFLIGHT,
            "--receipts", ".cambium/receipts/phase.jsonl", "--json")
        self.assertEqual(0, delivered.returncode, delivered.stderr)
        delivery = json.loads(delivered.stdout)[0]
        refused = self.run_tool(
            "check_queue.py", "--ack-activation-phase", "B1",
            "--phase", card_activation.PHASE_BATCH_PREFLIGHT,
            "--phase-nonce", delivery["delivery_nonce"],
            "--phase-delivery-receipt", delivery["receipt_id"],
            "--receipts", ".cambium/receipts/phase-ack.jsonl",
            context_id=OTHER_CONTEXT)
        self.assertEqual(1, refused.returncode)
        self.assertIn("delivering execution context", refused.stdout)


class ProducerEraReplayTests(unittest.TestCase):
    """A sealed receipt is judged by the rules of the era that wrote it.

    The v4 constant rename made this concrete: two era checks compared
    against "the current protocol" rather than against the shape they meant,
    so shipping v4 silently re-filed every sealed v3 receipt under the
    embedded-payload rules of v1.  These tests pin the shapes themselves.
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        add_conditional_routes(self.root)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"], result["errors"])
        self.current = card_activation.build_activation_context(
            self.root, result["progress"], result["items_by_id"]["B1"],
            runtime_state=result, execution_context_id=CONTEXT)

    def as_v3(self):
        """Rebuild the v3 shape: pieces without phases, no phase plan."""
        context = copy.deepcopy(self.current)
        manifest = context["activation_bundle_manifest"]
        manifest["activation_protocol"] = card_activation.\
            V3_ACTIVATION_PROTOCOL
        manifest.pop("phase_plan", None)
        manifest.pop("phase_plan_sha256", None)
        for piece in manifest["pieces"]:
            piece.pop("phase", None)
        context["activation_protocol"] = card_activation.\
            V3_ACTIVATION_PROTOCOL
        context.pop("phase_plan_sha256", None)
        context["card_bundle_sha256"] = kblib.sha256_bytes(
            kblib.canonical_json_bytes(manifest))
        return context

    def test_a_sealed_v3_context_still_validates(self):
        self.assertEqual(
            [], card_activation.activation_context_errors(self.as_v3()))

    def test_a_sealed_v3_context_keeps_its_own_field_set(self):
        v3 = self.as_v3()
        self.assertEqual(card_activation.ACTIVATION_CONTEXT_FIELDS,
                         card_activation.activation_context_fields(v3))
        self.assertNotIn(
            "phase_plan_sha256",
            card_activation.activation_receipt_binding(v3))
        self.assertIn("phase_plan_sha256",
                      card_activation.activation_receipt_binding(self.current))

    def test_v3_may_still_deliver_single_pieces(self):
        v3 = self.as_v3()
        piece_id = v3["activation_bundle_manifest"]["pieces"][0]["piece_id"]
        delivery = card_activation.build_activation_piece(
            self.root, v3, piece_id, execution_context_id=CONTEXT)
        self.assertEqual(card_activation.PIECE_PROTOCOL,
                         delivery["piece_protocol"])

    def test_v3_has_no_phases_to_deliver(self):
        with self.assertRaisesRegex(ValueError, "phase delivery requires"):
            card_activation.build_phase_delivery(
                self.root, self.as_v3(),
                card_activation.PHASE_BATCH_PREFLIGHT, 0,
                execution_context_id=CONTEXT)

    def test_a_pre_phase_era_must_not_carry_a_phase_plan(self):
        forged = self.as_v3()
        forged["phase_plan_sha256"] = "sha256:" + ("0" * 64)
        self.assertTrue(card_activation.activation_context_errors(forged))

    def test_a_pre_phase_era_gate_owes_nothing(self):
        # An old batch does not acquire a new obligation retroactively.
        result = check_queue.validate_runtime(self.root)
        catalog = dict(check_queue.current_receipt_catalog(result))
        catalog["audit-activation-v3"] = ("x", dict(
            card_activation.activation_receipt_binding(self.as_v3()),
            tool=check_queue.TOOL, tool_version=check_queue.TOOL_VERSION))
        view = dict(result, current_receipt_catalog=catalog,
                    receipt_catalog=catalog)
        item = dict(result["items_by_id"]["B1"],
                    activation_receipt="audit-activation-v3")
        self.assertEqual([], check_queue.activation_phase_delivery_errors(
            view, item, card_activation.PHASE_BATCH_GATE,
            actor_context_id=CONTEXT))


if __name__ == "__main__":
    unittest.main()
