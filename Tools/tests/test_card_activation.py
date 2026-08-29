import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
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
import read_set_contract
import stamp_cards
from profile_fixture import install_loadable_profile


class CardActivationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)

    def progress(self):
        return kblib.load_yaml_file(self.root / check_queue.PROGRESS_PATH)

    def queue(self):
        return kblib.load_yaml_file(self.root / check_queue.QUEUE_PATH)

    def item(self, batch="B1"):
        return next(item for item in self.queue()["required_queue"]
                    if item["id"] == batch)

    def runtime(self):
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"], result["errors"])
        return result

    def context(self, execution_context_id=None):
        runtime = self.runtime()
        return card_activation.build_activation_context(
            self.root, runtime["progress"], runtime["items_by_id"]["B1"],
            runtime_state=runtime,
            execution_context_id=execution_context_id)

    def run_tool(self, name, *arguments, context_id=None):
        environ = dict(os.environ)
        if context_id is not None:
            environ[card_activation.EXECUTION_CONTEXT_ENV] = context_id
        return subprocess.run(
            [sys.executable, str(TOOLS / name), str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environ, check=False)

    def pieces(self, context):
        return context["activation_bundle_manifest"]["pieces"]

    def acknowledge_fixture_card_body(self, relative):
        """Bind a deliberate fixture edit as reviewed for non-review tests.

        Production currentness must continue to fail closed on an unreviewed
        body.  These callers exercise a later activation invariant, so the
        fixture explicitly records the synthetic review before continuing.
        """
        path = self.root / relative
        text = path.read_text(encoding="utf-8")
        path.write_text(
            stamp_cards.replace_frontmatter_scalar(
                text, "reviewed_card_hash",
                stamp_cards.card_body_digest(text)),
            encoding="utf-8")

    def test_registry_comes_from_entity_declarations_not_indexes(self):
        (self.root / "Card/Card Index.md").write_text(
            "not authoritative\n", encoding="utf-8")
        (self.root / "Read Set/Read Sets Index.md").write_text(
            "not authoritative\n", encoding="utf-8")

        registry, fingerprint = card_activation._route_registry(self.root)

        self.assertEqual(13, len(registry))
        self.assertTrue(fingerprint.startswith("sha256:"))

    def test_phase_projection_comes_from_read_set_machine_contract(self):
        schema = read_set_contract.load_schema(TOOLS.parent)
        phases = schema["phases"]

        self.assertEqual(
            tuple(row["phase_id"] for row in phases),
            card_activation.PHASE_ORDER)
        self.assertEqual(
            {row["phase_id"] for row in phases if row["conditional"]},
            set(card_activation.CONDITIONAL_PHASES))
        self.assertEqual(
            {row["phase_id"] for row in phases if row["standard"]},
            set(card_activation.STANDARD_PHASES))
        self.assertEqual(
            {row["phase_id"]: row["trigger"] for row in phases},
            card_activation.PHASE_TRIGGERS)

    def test_card_readback_hooks_come_from_the_paired_read_set(self):
        registry, _fingerprint = card_activation._route_registry(self.root)

        card = card_activation._card_record(
            self.root, "R03", registry["R03"], registry["R03"]["path"])

        self.assertEqual(["R03:conditional"],
                         [edge["edge_id"] for edge in card["readback_edges"]])
        self.assertNotIn("readback_sources", card)
        self.assertNotIn("readback_policy", card)

    def test_admission_freezes_pieces_and_embeds_no_content(self):
        context = self.context()

        self.assertEqual([], card_activation.activation_context_errors(context))
        self.assertEqual("prepared", context["delivery_assurance"])
        self.assertNotIn("activation_delivery_payload", context)
        manifest = context["activation_bundle_manifest"]
        self.assertNotIn("cards", manifest)
        self.assertNotIn("startup_readbacks", manifest)
        self.assertEqual(
            ["R01", "R03", "R07"],
            [row["route_id"] for row in self.pieces(context)
             if row["kind"] == "card"])
        self.assertNotIn("content", json.dumps(manifest, sort_keys=True))
        self.assertEqual(1, len(manifest["readback_plan"]))

    def test_admission_result_stays_far_inside_the_piece_budget(self):
        context = self.context()

        envelope = len(kblib.canonical_json_bytes(context))

        self.assertLess(
            envelope, card_activation.MAX_ACTIVATION_PIECE_ENVELOPE_BYTES)

    def test_every_frozen_piece_delivers_within_the_budget(self):
        context = self.context()

        for record in self.pieces(context):
            delivery = card_activation.build_activation_piece(
                self.root, context, record["piece_id"])
            payload = delivery["activation_piece_payload"]
            self.assertEqual(record["sha256"],
                             kblib.sha256_bytes(payload["content"]))
            self.assertEqual(
                (self.root / record["path"]).read_text(encoding="utf-8"),
                payload["content"])
            self.assertLessEqual(
                delivery["piece_envelope_bytes"],
                card_activation.MAX_ACTIVATION_PIECE_ENVELOPE_BYTES)

    def test_frozen_piece_ids_are_the_exact_delivery_obligation(self):
        context = self.context()

        identifiers = card_activation.frozen_piece_ids(context)

        self.assertEqual(sorted(identifiers), identifiers)
        self.assertEqual(
            sorted(row["piece_id"] for row in self.pieces(context)),
            identifiers)
        # Every named piece must actually deliver, or the set the delivery
        # gate compares against would be unsatisfiable by construction.
        for piece_id in identifiers:
            card_activation.build_activation_piece(
                self.root, context, piece_id)

    def test_admission_budget_check_measures_the_real_envelope(self):
        # A piece measured without its bundle hash, nonce and attempt id would
        # be under-reported at admission and refused later at delivery.
        context = self.context()
        for record in self.pieces(context):
            delivery = card_activation.build_activation_piece(
                self.root, context, record["piece_id"])
            self.assertLessEqual(
                delivery["piece_envelope_bytes"],
                card_activation.MAX_ACTIVATION_PIECE_ENVELOPE_BYTES)

    def test_oversized_leaf_fails_closed_at_admission(self):
        card = self.root / "Card/R03 Module Build Card.md"
        text = card.read_text(encoding="utf-8")
        card.write_text(
            text + ("\nfiller " * 12000), encoding="utf-8")
        self.acknowledge_fixture_card_body(
            "Card/R03 Module Build Card.md")

        with self.assertRaisesRegex(ValueError, "delivery budget"):
            self.context()

    def test_piece_delivery_refuses_a_source_that_drifted(self):
        context = self.context()
        card = self.root / "Card/R01 Core Bootstrap Card.md"
        card.write_text(card.read_text(encoding="utf-8") + "\nDrift.\n",
                        encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "drifted since admission"):
            card_activation.build_activation_piece(
                self.root, context, "card:R01")

    def test_piece_ack_binds_the_delivering_context_and_nonce(self):
        context = self.context("mcp:ack")
        delivery = card_activation.build_activation_piece(
            self.root, context, "card:R01", execution_context_id="mcp:ack")
        delivery["receipt_id"] = "audit-check_queue-fixture-0001"

        ack = card_activation.build_piece_ack(
            delivery, delivery["delivery_nonce"],
            execution_context_id="mcp:ack")

        self.assertEqual("card:R01", ack["piece_id"])
        self.assertEqual(delivery["delivery_attempt_id"],
                         ack["delivery_attempt_id"])
        self.assertEqual("audit-check_queue-fixture-0001",
                         ack["delivery_receipt_id"])
        with self.assertRaisesRegex(ValueError, "nonce does not match"):
            card_activation.build_piece_ack(
                delivery, "0" * 32, execution_context_id="mcp:ack")
        with self.assertRaisesRegex(ValueError, "delivering execution context"):
            card_activation.build_piece_ack(
                delivery, delivery["delivery_nonce"],
                execution_context_id="mcp:other")

    def test_navigation_index_cannot_enter_the_activation_contract(self):
        progress = self.progress()
        progress["contract"]["selected_card_paths"].append(
            "Card/Card Index.md")
        progress["contract"]["selected_card_paths"].sort()
        runtime = self.runtime()
        runtime["progress"] = progress
        runtime["progress_sha256"] = kblib.sha256_bytes(
            kblib.canonical_yaml(progress))

        with self.assertRaisesRegex(ValueError, "Card Index.md"):
            card_activation.build_activation_context(
                self.root, progress, runtime["items_by_id"]["B1"],
                runtime_state=runtime)

    def test_unregistered_extra_selected_card_path_is_rejected(self):
        progress = self.progress()
        progress["contract"]["selected_card_paths"].append(
            "Card/Unregistered.md")
        runtime = self.runtime()
        runtime["progress"] = progress
        runtime["progress_sha256"] = kblib.sha256_bytes(
            kblib.canonical_yaml(progress))

        with self.assertRaisesRegex(ValueError, "Unregistered.md"):
            card_activation.build_activation_context(
                self.root, progress, runtime["items_by_id"]["B1"],
                runtime_state=runtime)

    def test_batch_provenance_does_not_select_runtime_cards(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        coverage["batch_specs"][0]["source_route"] = (
            "SOURCE-AUDIT-001-S001")
        coverage_path.write_text(kblib.canonical_yaml(coverage), encoding="utf-8")

        queue_path = self.root / check_queue.QUEUE_PATH
        queue = kblib.load_yaml_file(queue_path)
        queue["required_queue"][0]["source_route"] = (
            "SOURCE-AUDIT-001-S001")
        queue_path.write_text(kblib.canonical_yaml(queue), encoding="utf-8")

        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = kblib.load_yaml_file(progress_path)
        progress["required_queue_sha256"] = kblib.sha256_file(queue_path)
        progress_path.write_text(kblib.canonical_yaml(progress), encoding="utf-8")

        receipt_path = (
            self.root / ".cambium/receipts/task-transitions.jsonl")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["before_coverage_sha256"] = kblib.sha256_file(coverage_path)
        receipt["after_coverage_sha256"] = kblib.sha256_file(coverage_path)
        receipt["after_required_queue_sha256"] = kblib.sha256_file(queue_path)
        receipt["after_progress_sha256"] = kblib.sha256_file(progress_path)
        receipt_path.write_text(
            json.dumps(receipt, separators=(",", ":")) + "\n",
            encoding="utf-8")

        context = self.context()

        self.assertEqual([], card_activation.activation_context_errors(context))
        self.assertEqual(
            ["R01", "R03", "R07"],
            [row["route_id"] for row in self.pieces(context)
             if row["kind"] == "card"])

    def test_admission_records_host_binding_not_delivery(self):
        context = self.context("mcp:fixture-context")

        self.assertEqual("host-bound", context["delivery_assurance"])
        self.assertEqual("host-context-injection", context["delivery_mode"])
        self.assertEqual("mcp:fixture-context",
                         context["execution_context_id"])
        self.assertEqual([], card_activation.activation_context_errors(context))

    def test_r01_and_semantic_card_currency_fail_closed(self):
        progress = self.progress()
        progress["contract"]["selected_route_ids"].remove("R01")
        progress["contract"]["selected_card_paths"] = [
            path for path in progress["contract"]["selected_card_paths"]
            if "/R01 " not in path]
        runtime = self.runtime()
        runtime["progress"] = progress
        runtime["progress_sha256"] = kblib.sha256_bytes(
            kblib.canonical_yaml(progress))
        with self.assertRaisesRegex(ValueError, "include R01"):
            card_activation.build_activation_context(
                self.root, progress, runtime["items_by_id"]["B1"],
                runtime_state=runtime)

        card_path = self.root / "Card/R03 Module Build Card.md"
        text = card_path.read_text(encoding="utf-8")
        data = kblib.parse_yaml_subset(kblib.extract_frontmatter(text))
        card_path.write_text(text.replace(
            "reviewed_source_hash: %s" % data["reviewed_source_hash"],
            "reviewed_source_hash: abcdefabcdef"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unreviewed source drift"):
            self.context()

    def test_an_admission_that_embeds_a_payload_is_rejected(self):
        context = self.context()
        context["activation_delivery_payload"] = {"cards": []}

        errors = card_activation.activation_context_errors(context)

        self.assertTrue(any("embedded delivery payload" in error
                            for error in errors), errors)

    def test_declared_readback_is_one_parent_bound_addendum(self):
        context = self.context("mcp:readback")
        rule = context["activation_bundle_manifest"]["readback_plan"][0]

        addendum = card_activation.build_readback_addendum(
            self.root, context, rule["rule_id"],
            execution_context_id="mcp:readback")

        self.assertEqual(context["card_bundle_sha256"],
                         addendum["parent_card_bundle_sha256"])
        self.assertEqual(rule["rule_id"], addendum["readback_rule_id"])
        self.assertIn("Conditional Review",
                      addendum["readback_delivery_payload"][
                          "sources"][0]["content"])

    def _persist_machine_gate(self, context_id="mcp:activation-a"):
        relative = ".cambium/receipts/card-ready.jsonl"
        result = self.run_tool(
            "check_queue.py", "--require-ready", "B1",
            "--receipts", relative, "--json", context_id=context_id)
        self.assertEqual(0, result.returncode, result.stderr)
        receipt = json.loads(result.stdout)[0]
        self.assertEqual("host-bound", receipt["delivery_assurance"])
        self.assertNotIn("activation_delivery_payload", receipt)
        self.assertTrue(
            receipt["activation_bundle_manifest"]["pieces"])
        persisted = json.loads(
            (self.root / relative).read_text(encoding="utf-8").splitlines()[0])
        self.assertNotIn("activation_delivery_payload", persisted)
        self.assertNotIn("content", json.dumps(
            persisted["activation_bundle_manifest"], sort_keys=True))
        return relative, receipt

    def _open_command(self, receipt, context_id):
        queue = self.queue()
        return self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "open",
            "--gate-receipt", receipt["receipt_id"],
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at",
            "2026-08-21T00:00:00Z", "--apply", context_id=context_id)

    def test_open_binds_the_bundle_and_no_longer_binds_the_session(self):
        # v1/v2 refused an admission consumed by a second host session.  A v3
        # admission asserts no delivery, so `open` is admission only and the
        # context binding moves to the Assignment delivery gate.
        _relative, receipt = self._persist_machine_gate()

        opened = self._open_command(receipt, "mcp:activation-b")

        self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"], runtime["errors"])
        transition = runtime["receipt_catalog"][
            self.item()["transition_receipts"][0]][1]
        self.assertEqual(receipt["card_bundle_sha256"],
                         transition["card_bundle_sha256"])

    def test_open_still_refuses_a_bundle_whose_bytes_drifted(self):
        _relative, receipt = self._persist_machine_gate()
        card = self.root / "Card/R01 Core Bootstrap Card.md"
        card.write_text(card.read_text(encoding="utf-8") + "\nDrift.\n",
                        encoding="utf-8")
        self.acknowledge_fixture_card_body(
            "Card/R01 Core Bootstrap Card.md")

        refused = self._open_command(receipt, "mcp:activation-a")

        self.assertEqual(1, refused.returncode)
        self.assertIn("invalid Card activation delivery", refused.stdout)

    def test_piece_delivery_and_ack_round_trip_through_the_cli(self):
        _relative, receipt = self._persist_machine_gate("mcp:pieces")
        opened = self._open_command(receipt, "mcp:pieces")
        self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)

        delivered = self.run_tool(
            "check_queue.py", "--deliver-activation-piece", "B1",
            "--piece", "card:R01",
            "--receipts", ".cambium/receipts/piece.jsonl", "--json",
            context_id="mcp:pieces")
        self.assertEqual(0, delivered.returncode, delivered.stderr)
        delivery = json.loads(delivered.stdout)[0]
        payload = delivery["activation_piece_payload"]
        self.assertEqual(
            (self.root / "Card/R01 Core Bootstrap Card.md").read_text(
                encoding="utf-8"),
            payload["content"])
        self.assertEqual(payload["delivery_nonce"],
                         delivery["delivery_nonce"])
        persisted = json.loads((
            self.root / ".cambium/receipts/piece.jsonl"
        ).read_text(encoding="utf-8").splitlines()[0])
        self.assertNotIn("activation_piece_payload", persisted)
        self.assertNotIn("content", json.dumps(persisted, sort_keys=True))

        acked = self.run_tool(
            "check_queue.py", "--ack-activation-piece", "B1",
            "--piece", "card:R01",
            "--piece-nonce", delivery["delivery_nonce"],
            "--piece-delivery-receipt", delivery["receipt_id"],
            "--receipts", ".cambium/receipts/ack.jsonl", "--json",
            context_id="mcp:pieces")
        self.assertEqual(0, acked.returncode, acked.stderr)
        ack = json.loads(acked.stdout)[0]
        self.assertEqual("card:R01", ack["piece_id"])
        self.assertEqual(delivery["receipt_id"], ack["delivery_receipt_id"])

        wrong = self.run_tool(
            "check_queue.py", "--ack-activation-piece", "B1",
            "--piece", "card:R01", "--piece-nonce", "0" * 32,
            "--piece-delivery-receipt", delivery["receipt_id"],
            "--receipts", ".cambium/receipts/ack.jsonl", "--json",
            context_id="mcp:pieces")
        self.assertEqual(1, wrong.returncode)
        self.assertIn("nonce does not match", wrong.stdout + wrong.stderr)

    def test_public_readback_mode_returns_exact_source_content(self):
        _relative, receipt = self._persist_machine_gate("mcp:readback")
        opened = self._open_command(receipt, "mcp:readback")
        self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)
        rule_id = receipt["activation_bundle_manifest"][
            "readback_plan"][0]["rule_id"]

        delivered = self.run_tool(
            "check_queue.py", "--deliver-readback", "B1",
            "--readback-rule", rule_id,
            "--receipts", ".cambium/receipts/readback.jsonl", "--json",
            context_id="mcp:readback")

        self.assertEqual(0, delivered.returncode, delivered.stderr)
        addendum = json.loads(delivered.stdout)[0]
        self.assertEqual(receipt["card_bundle_sha256"],
                         addendum["parent_card_bundle_sha256"])
        self.assertIn("Conditional Review",
                      addendum["readback_delivery_payload"][
                          "sources"][0]["content"])
        persisted = json.loads((
            self.root / ".cambium/receipts/readback.jsonl"
        ).read_text(encoding="utf-8").splitlines()[0])
        self.assertNotIn("readback_delivery_payload", persisted)
        self.assertNotIn("content", json.dumps(
            persisted["readback_addendum_manifest"], sort_keys=True))

    def test_resume_reinjects_the_bundle_into_the_new_context(self):
        _relative, receipt = self._persist_machine_gate("mcp:original")
        opened = self._open_command(receipt, "mcp:original")
        self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)

        resumed = self.run_tool(
            "check_queue.py", "--resume-status", "--json",
            context_id="mcp:replacement")

        self.assertEqual(2, resumed.returncode, resumed.stderr)
        status = json.loads(resumed.stdout)[0]
        delivery = status["active_card_context_deliveries"][0]
        self.assertEqual("B1", delivery["batch_id"])
        self.assertEqual("mcp:replacement", delivery["execution_context_id"])
        self.assertEqual("host-bound", delivery["delivery_assurance"])
        self.assertNotIn("activation_delivery_payload", delivery)
        self.assertTrue(
            delivery["activation_bundle_manifest"]["pieces"])

    def test_resume_refuses_card_bytes_that_drifted_after_open(self):
        _relative, receipt = self._persist_machine_gate("mcp:original")
        opened = self._open_command(receipt, "mcp:original")
        self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)
        card = self.root / "Card/R01 Core Bootstrap Card.md"
        card.write_text(
            card.read_text(encoding="utf-8") + "\nDrift.\n",
            encoding="utf-8")
        self.acknowledge_fixture_card_body(
            "Card/R01 Core Bootstrap Card.md")

        resumed = self.run_tool(
            "check_queue.py", "--resume-status", "--json",
            context_id="mcp:replacement")

        self.assertEqual(1, resumed.returncode)
        self.assertIn("activation Bundle differs", resumed.stderr)


if __name__ == "__main__":
    unittest.main()
