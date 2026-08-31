"""Ownership closure for the current Contract Amendment transaction.

Pure plan, state, projection, receipt-selection, policy-binding, and image
predicates run on in-memory objects. Repository-backed coverage starts from
one already-materialized current-runtime checkpoint: one public CLI/JSON
commit connects the writer to its runtime consumer, and two bounded commit
tests cover the locked CAS and rollback edges. Only the durable-receipt
interruption crosses into the slow recovery layer.
"""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
FIXTURE = TESTS / "fixtures" / "runtime_state" / "valid"

for path in (str(TOOLS), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import Tools.execution.task_runtime.apply_contract_amendment as apply_contract_amendment  # noqa: E402
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract  # noqa: E402
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
from Tools.execution.task_runtime import queue_runtime  # noqa: E402
import Tools.governance.control.contract_exception_policy as contract_exception_policy  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
from Tools.tests.support.profile_fixture import install_loadable_profile  # noqa: E402


AMENDMENT_RELATIVE = \
    ".cambium/deltas/contract-amendments/CA-CONTRACT.yaml"
DIGEST = "sha256:" + "1" * 64
NONE_RUBRIC = "## Priority Quota\n\n- Registration: None\n"


def _user_only_authority():
    return {
        "schema_version": 1,
        "authority_id": "AUTH-CONTRACT",
        "mode": "user-only",
        "allowed_change_classes": [],
    }


def _delegated_authority():
    return {
        "schema_version": 1,
        "authority_id": "AUTH-DELEGATED",
        "mode": "delegated-integrator",
        "allowed_change_classes": [
            "batch-add",
            "queued-batch-update",
            "required-object-add",
            "required-object-promote",
            "required-object-reroute",
        ],
    }


def _policy_exception(fingerprint=DIGEST):
    return {
        "decision_id": "PE-CONTRACT",
        "policy_id": "priority_quota.P0",
        "baseline_policy_fingerprint": fingerprint,
        "limit": 18,
        "scope_kind": "task",
        "scope_ref": "fixture-task",
        "rationale": "one bounded quota decision for this task",
        "approval_reference": "operator approval 2026-08-31",
    }


def _current_plan(**overrides):
    plan = {
        "schema_version": 2,
        "amendment_id": "CA-CONTRACT",
        "task_id": "fixture-task",
        "date": "2026-08-31",
        "summary": "amend the two current allowlisted contract fields",
        "approval_reference": "operator approval 2026-08-31",
        "before": {
            field: DIGEST
            for field in (
                runtime_state_contract.RUNTIME_LEDGER_FINGERPRINT_FIELDS)
        },
        "contract_version_after": "c2",
        "policy_exceptions_after": [_policy_exception()],
        "amendment_authority_after": _delegated_authority(),
    }
    plan.update(overrides)
    return plan


def _runtime_documents(task_state="paused"):
    return {
        "coverage": {
            "task_id": "fixture-task",
            "scope_version": "s1",
        },
        "queue": {
            "task_id": "fixture-task",
            "scope_version": "s1",
            "queue_revision": 4,
            "state_revision": 2,
            "required_queue": [{"id": "B1", "state": "queued"}],
        },
        "progress": {
            "task_id": "fixture-task",
            "task_state": task_state,
            "contract": {
                "contract_version": "c1",
                "scope_version": "s1",
                "policy_exceptions": [],
                "amendment_authority": _user_only_authority(),
            },
            "amendments": [],
        },
    }


class ContractAmendmentPlanContractTests(unittest.TestCase):

    def test_current_plan_is_one_closed_schema(self):
        apply_contract_amendment._validate_plan_shape(_current_plan())

        cases = (
            ("wrong-schema", {"schema_version": 3},
             "schema_version must be 2"),
            ("unknown-field", {"unexpected_field": "unsupported"},
             "unsupported field.*unexpected_field"),
            ("unanswered-template", {
                "approval_reference": apply_contract_amendment.SENTINEL,
            }, "template.*sentinel"),
        )
        for label, changes, expected in cases:
            with self.subTest(case=label):
                candidate = _current_plan()
                candidate.update(changes)
                with self.assertRaisesRegex(
                        apply_contract_amendment.Refusal, expected):
                    apply_contract_amendment._validate_plan_shape(candidate)


class ContractAmendmentRuntimeContractTests(unittest.TestCase):

    def test_only_one_materialized_nonterminal_runtime_edge_is_amendable(self):
        plan = _current_plan()
        for state in ("planned", "active", "paused"):
            with self.subTest(accepted_state=state):
                apply_contract_amendment._require_amendable_runtime(
                    _runtime_documents(state), plan)

        cases = {}
        unmaterialized = _runtime_documents()
        unmaterialized["queue"]["required_queue"] = []
        cases["unmaterialized"] = (unmaterialized, "not materialized")
        merge_ready = _runtime_documents()
        merge_ready["queue"]["required_queue"][0]["state"] = "merge-ready"
        cases["merge-ready"] = (merge_ready, "merge-ready")
        terminal = _runtime_documents("complete")
        cases["terminal"] = (terminal, "terminal task")
        wrong_identity = _runtime_documents()
        wrong_identity["coverage"]["task_id"] = "another-task"
        cases["identity"] = (wrong_identity, "coverage records task_id")
        duplicate = _runtime_documents()
        duplicate["progress"]["amendments"] = [{"id": "CA-CONTRACT"}]
        cases["duplicate"] = (duplicate, "already contains Amendment")

        same_version = _current_plan(contract_version_after="c1")
        with self.assertRaisesRegex(
                apply_contract_amendment.Refusal,
                "equals the live contract_version"):
            apply_contract_amendment._require_amendable_runtime(
                _runtime_documents(), same_version)
        for label, (documents, expected) in cases.items():
            with self.subTest(refused_edge=label), self.assertRaisesRegex(
                    apply_contract_amendment.Refusal, expected):
                apply_contract_amendment._require_amendable_runtime(
                    documents, plan)


class ContractAmendmentProjectionUnitTests(unittest.TestCase):

    def test_projection_changes_only_the_allowlist_and_exact_anchor_edge(self):
        documents = _runtime_documents()
        before = copy.deepcopy(documents)
        plan = _current_plan()
        queue, queue_text, progress, contract_before, row = \
            apply_contract_amendment._build_after(
                documents, plan, "R-CONTRACT", "2026-08-31T00:00:00Z")

        self.assertEqual(before, documents)
        self.assertEqual(before["progress"]["contract"], contract_before)
        self.assertEqual(5, queue["queue_revision"])
        self.assertEqual(2, queue["state_revision"])
        self.assertEqual("s1", queue["scope_version"])
        self.assertEqual(5, progress["queue_revision"])
        self.assertEqual(kblib.sha256_bytes(queue_text),
                         progress["required_queue_sha256"])
        contract = progress["contract"]
        self.assertEqual("c2", contract["contract_version"])
        self.assertEqual([_policy_exception()],
                         contract["policy_exceptions"])
        self.assertEqual(_delegated_authority(),
                         contract["amendment_authority"])
        self.assertEqual("verified", row["status"])
        self.assertIs(row["writeback_done"], True)
        self.assertEqual("R-CONTRACT", row["verification_receipt"])
        self.assertEqual(row["scope_version_before"],
                         row["scope_version_after"])
        self.assertEqual(row["state_revision_before"],
                         row["state_revision_after"])


class ContractAmendmentPolicyConnectionTests(unittest.TestCase):

    def test_writer_accepts_only_the_registrys_current_policy_fingerprint(self):
        policy, fingerprint, errors = \
            contract_exception_policy.effective_priority_policy(NONE_RUBRIC)
        self.assertEqual([], errors)
        apply_contract_amendment._require_policy_authorization(
            policy, fingerprint, [_policy_exception(fingerprint)])

        with self.assertRaisesRegex(
                apply_contract_amendment.Refusal,
                "does not match the current effective policy"):
            apply_contract_amendment._require_policy_authorization(
                policy, fingerprint, [_policy_exception(DIGEST)])


class ContractAmendmentReceiptContractTests(unittest.TestCase):

    def test_receipt_selector_accepts_only_this_current_writer_identity(self):
        receipt = kblib.make_receipt(
            apply_contract_amendment.TOOL,
            apply_contract_amendment.TOOL_VERSION,
            apply_contract_amendment.CHECK,
            "CA-CONTRACT",
            "pass",
            "current contract amendment",
            1,
            receipt_type_id=apply_contract_amendment.RECEIPT_TYPE_ID,
        )
        self.assertEqual(
            [], apply_contract_amendment.current_receipt_errors(receipt))

        wrong_writer = copy.deepcopy(receipt)
        wrong_writer["tool"] = "another_writer"
        self.assertTrue(
            apply_contract_amendment.current_receipt_errors(wrong_writer))


class ContractAmendmentPredicateUnitTests(unittest.TestCase):

    def test_state_image_predicate_accepts_only_the_exact_three_ledger_image(self):
        paths = {name: "%s-path" % name
                 for name in apply_contract_amendment.STATE_NAMES}
        expected = {name: "sha256:" + str(index + 1) * 64
                    for index, name in enumerate(
                        apply_contract_amendment.STATE_NAMES)}
        live = {path: expected[name] for name, path in paths.items()}

        with mock.patch.object(
                apply_contract_amendment.kblib, "sha256_file",
                side_effect=lambda path: live[path]):
            self.assertEqual([], apply_contract_amendment._state_image_errors(
                paths, expected, "accepted image"))
            live[paths["queue"]] = "sha256:" + "9" * 64
            errors = apply_contract_amendment._state_image_errors(
                paths, expected, "rejected image")
        self.assertEqual(1, len(errors))
        self.assertIn("rejected image queue read-back", errors[0])


def _build_materialized(root):
    """Install the one static checkpoint used by repository-backed cases."""
    shutil.copytree(FIXTURE, root)
    install_loadable_profile(root)
    (root / AMENDMENT_RELATIVE).parent.mkdir(parents=True, exist_ok=True)


class ContractAmendmentFixture:
    """Repository helpers starting at one legal materialized checkpoint."""

    def load(self, relative):
        return kblib.load_yaml_file(self.root / relative)

    def state_shas(self):
        return {
            name: kblib.sha256_file(self.root / relative)
            for name, relative in (
                ("coverage", queue_runtime.COVERAGE_PATH),
                ("queue", queue_runtime.QUEUE_PATH),
                ("progress", queue_runtime.PROGRESS_PATH),
            )
        }

    def state_bytes(self):
        return {
            relative: (self.root / relative).read_bytes()
            for relative in (
                queue_runtime.COVERAGE_PATH,
                queue_runtime.QUEUE_PATH,
                queue_runtime.PROGRESS_PATH,
            )
        }

    def receipt_rows(self):
        path = self.root / apply_contract_amendment.RECEIPT_PATH
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(
            encoding="utf-8").splitlines() if line.strip()]

    def amendment_plan(self, **overrides):
        shas = self.state_shas()
        plan = _current_plan(
            before={
                field: shas[name]
                for name, field in (
                    runtime_state_contract.
                    RUNTIME_LEDGER_FINGERPRINT_BY_ID.items())
            },
            # The quota-exception lifecycle owns the file-backed grant and
            # revoke matrix.  This adjacent transaction instead connects the
            # other current allowlisted field to the real writer/consumer.
            policy_exceptions_after=[],
        )
        plan.update(overrides)
        return plan

    def write_amendment(self, plan=None):
        path = self.root / AMENDMENT_RELATIVE
        path.write_text(
            kblib.canonical_yaml(plan or self.amendment_plan()),
            encoding="utf-8")
        return AMENDMENT_RELATIVE

    def prepared(self):
        relative = self.write_amendment()
        return apply_contract_amendment.prepare(str(self.root), relative)


_TEMPLATES = {}


def _template(name):
    """Build the static materialized runtime once per test process."""
    if name != "materialized":
        raise KeyError(name)
    if name not in _TEMPLATES:
        holder = tempfile.TemporaryDirectory()
        root = (Path(holder.name) / "repo").resolve()
        _build_materialized(root)
        _TEMPLATES[name] = holder, root
    return _TEMPLATES[name][1]


class _TemplateBackedCase(ContractAmendmentFixture, unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = (Path(self.tmp.name) / "repo").resolve()
        shutil.copytree(_template("materialized"), self.root)


class ContractAmendmentCliIntegrationTests(_TemplateBackedCase):

    def test_cli_json_commit_is_consumed_as_one_current_anchor_edge(self):
        before_revision = self.load(
            queue_runtime.QUEUE_PATH)["queue_revision"]
        self.write_amendment()
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "apply_contract_amendment.py"),
                str(self.root),
                "--plan", AMENDMENT_RELATIVE,
                "--actor-role", "integrator",
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
        self.assertEqual([], apply_contract_amendment.current_receipt_errors(
            emitted[0]))

        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(before_revision + 1,
                         result["queue"]["queue_revision"])
        contract = result["progress"]["contract"]
        self.assertEqual("c2", contract["contract_version"])
        self.assertEqual([], contract["policy_exceptions"])
        self.assertEqual("AUTH-DELEGATED",
                         contract["amendment_authority"]["authority_id"])
        amendment = result["progress"]["amendments"][-1]
        self.assertEqual("verified", amendment["status"])
        self.assertEqual(emitted[0]["receipt_id"],
                         amendment["verification_receipt"])


class ContractAmendmentCommitIntegrationTests(_TemplateBackedCase):

    def test_compare_and_swap_refuses_a_moved_runtime_without_mutation(self):
        prepared = self.prepared()
        receipt_path = self.root / apply_contract_amendment.RECEIPT_PATH
        before = self.state_bytes()
        queue_path = self.root / queue_runtime.QUEUE_PATH
        queue_path.write_bytes(before[queue_runtime.QUEUE_PATH] + b"\n")
        moved = self.state_bytes()

        with self.assertRaisesRegex(
                apply_contract_amendment.Refusal,
                "runtime changed before contract amendment write"):
            apply_contract_amendment.commit(prepared, receipt_path)

        self.assertEqual(moved, self.state_bytes())
        self.assertEqual([], self.receipt_rows())
        self.assertFalse((
            self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_partial_write_rolls_back_without_receipt_or_false_lock(self):
        prepared = self.prepared()
        before = self.state_bytes()
        receipt_path = self.root / apply_contract_amendment.RECEIPT_PATH
        real_write = kblib.atomic_write_text
        calls = {"count": 0}

        def fail_second_replace(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("injected second-ledger failure")
            return real_write(*args, **kwargs)

        with mock.patch.object(
                apply_contract_amendment.kblib, "atomic_write_text",
                side_effect=fail_second_replace):
            with self.assertRaisesRegex(
                    OSError, "injected second-ledger"):
                apply_contract_amendment.commit(prepared, receipt_path)

        self.assertEqual(before, self.state_bytes())
        self.assertEqual([], self.receipt_rows())
        self.assertFalse((
            self.root / ".cambium/tmp/state-writer.lock").exists())
        self.assertEqual([], runtime_validation.validate_runtime(
            self.root)["errors"])


class ContractAmendmentRecoverySlowTests(_TemplateBackedCase):

    def test_durable_receipt_interruption_keeps_exact_recovery_evidence(self):
        prepared = self.prepared()
        receipt_path = self.root / apply_contract_amendment.RECEIPT_PATH
        real_append = kblib.write_receipts_observed

        def append_then_interrupt(*args, **kwargs):
            outcome = real_append(*args, **kwargs)
            self.assertEqual("present", outcome[0])
            raise KeyboardInterrupt("injected after durable receipt")

        with mock.patch.object(
                apply_contract_amendment.kblib,
                "write_receipts_observed",
                side_effect=append_then_interrupt):
            with self.assertRaisesRegex(
                    KeyboardInterrupt, "after durable receipt"):
                apply_contract_amendment.commit(prepared, receipt_path)

        self.assertEqual(prepared["after_sha"], self.state_shas())
        self.assertEqual(
            [prepared["receipt"]["receipt_id"]],
            [row["receipt_id"] for row in self.receipt_rows()],
        )
        self.assertTrue((
            self.root /
            ".cambium/tmp/state-writer.lock/owner.json").is_file())
        recovery = runtime_validation.validate_runtime(self.root)
        self.assertEqual(1, len(recovery["_writer_locks"]))
        lock = recovery["_writer_locks"][0]
        self.assertEqual("matching",
                         lock["operation_receipt"]["status"])
        self.assertTrue(lock["operation_receipt"]["matching_receipt"])
        self.assertEqual("planned-after",
                         lock["state_phases"]["queue"]["phase"])
        self.assertEqual("planned-after",
                         lock["state_phases"]["progress"]["phase"])


if __name__ == "__main__":
    unittest.main()
