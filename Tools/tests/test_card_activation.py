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

    def test_bundle_carries_r01_and_every_selected_card(self):
        context = self.context()

        self.assertEqual([], card_activation.activation_context_errors(context))
        self.assertEqual("degraded", context["delivery_assurance"])
        bundle = context["activation_delivery_payload"]
        self.assertEqual(
            ["R01", "R03", "R07"],
            [card["route_id"] for card in bundle["cards"]])
        self.assertTrue(all(card["content"] for card in bundle["cards"]))
        self.assertEqual(1, len(bundle["readback_plan"]))

    def test_frozen_card_index_is_delivered_as_startup_navigation(self):
        progress = self.progress()
        progress["contract"]["selected_card_paths"].append(
            card_activation.CARD_INDEX_PATH)
        progress["contract"]["selected_card_paths"].sort()
        runtime = self.runtime()
        runtime["progress"] = progress
        runtime["progress_sha256"] = kblib.sha256_bytes(
            kblib.canonical_yaml(progress))

        context = card_activation.build_activation_context(
            self.root, progress, runtime["items_by_id"]["B1"],
            runtime_state=runtime)

        self.assertEqual([], card_activation.activation_context_errors(context))
        startup = context["activation_delivery_payload"]["startup_readbacks"]
        index_rows = [row for row in startup
                      if row["path"] == card_activation.CARD_INDEX_PATH]
        self.assertEqual(1, len(index_rows))
        self.assertEqual("kernel-card-index", index_rows[0]["route_id"])
        self.assertEqual(
            (self.root / card_activation.CARD_INDEX_PATH).read_text(
                encoding="utf-8"),
            index_rows[0]["content"])

    def test_unregistered_extra_selected_card_path_is_rejected(self):
        progress = self.progress()
        progress["contract"]["selected_card_paths"].append(
            "kernel/Cards/Unregistered.md")
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
            [card["route_id"] for card in
             context["activation_delivery_payload"]["cards"]])

    def test_machine_delivery_is_bound_to_one_execution_context(self):
        context = self.context("mcp:fixture-context")

        self.assertEqual("machine-delivered", context["delivery_assurance"])
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

        card_path = self.root / "kernel/Cards/R03 Module Build Card.md"
        card_path.write_text(card_path.read_text(encoding="utf-8").replace(
            "compiled_source_hash: 0123456789ab",
            "compiled_source_hash: abcdefabcdef"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "semantic source drift"):
            self.context()

    def test_embedded_byte_tampering_is_detected(self):
        context = self.context()
        context["activation_delivery_payload"]["cards"][0]["content"] += "x"

        errors = card_activation.activation_context_errors(context)

        self.assertTrue(any("Card 0 bytes" in error for error in errors))

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
        self.assertEqual("machine-delivered", receipt["delivery_assurance"])
        self.assertTrue(receipt["activation_delivery_payload"]["cards"])
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

    def test_open_consumes_only_the_same_machine_delivery_context(self):
        _relative, receipt = self._persist_machine_gate()

        wrong = self._open_command(receipt, "mcp:activation-b")
        self.assertEqual(1, wrong.returncode, wrong.stdout + wrong.stderr)
        self.assertIn("invalid Card activation delivery", wrong.stdout)

        opened = self._open_command(receipt, "mcp:activation-a")
        self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"], runtime["errors"])
        transition = runtime["receipt_catalog"][
            self.item()["transition_receipts"][0]][1]
        self.assertEqual(receipt["card_bundle_sha256"],
                         transition["card_bundle_sha256"])
        self.assertEqual("mcp:activation-a",
                         transition["execution_context_id"])

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
        self.assertEqual("machine-delivered", delivery["delivery_assurance"])
        self.assertTrue(delivery["activation_delivery_payload"]["cards"])

    def test_resume_refuses_card_bytes_that_drifted_after_open(self):
        _relative, receipt = self._persist_machine_gate("mcp:original")
        opened = self._open_command(receipt, "mcp:original")
        self.assertEqual(0, opened.returncode, opened.stdout + opened.stderr)
        card = self.root / "kernel/Cards/R01 Core Bootstrap Card.md"
        card.write_text(
            card.read_text(encoding="utf-8") + "\nDrift.\n",
            encoding="utf-8")

        resumed = self.run_tool(
            "check_queue.py", "--resume-status", "--json",
            context_id="mcp:replacement")

        self.assertEqual(1, resumed.returncode)
        self.assertIn("activation Bundle differs", resumed.stderr)


if __name__ == "__main__":
    unittest.main()
