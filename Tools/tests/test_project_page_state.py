"""Owned tests for the K08/07 page-state projection consumer.

Metadata value shapes, property-event production, and repository path
primitives have their own test owners.  This module tests only the page
projector's deterministic projection, planning connection, publication
transaction, and current machine-contract connection.
"""

import functools
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Tools"))

import Tools.governance.control.metadata_execution_contract as metadata_contract
import Tools.knowledge.metadata.project_page_state as project_page_state


PROFILE_RULE = metadata_contract.profile_extension_enum_projection_rule(
    "review_state", ("ready",),
    writer_capability=project_page_state.WRITER_CAPABILITY)
PROJECTOR_CONTRACT_RULES = metadata_contract.AuthorizedProjectionRules(
    (PROFILE_RULE,), "sha256:" + "1" * 64,
    "sha256:" + "2" * 64)


@functools.lru_cache(maxsize=1)
def _current_profile_rules():
    """Compile the live owner only for integration and slow boundaries."""
    contract = metadata_contract.compile_metadata_execution_contract(REPO)
    core = tuple(metadata_contract.rules_for_capability(
        contract, project_page_state.WRITER_CAPABILITY))
    return metadata_contract.AuthorizedProjectionRules(
        core + (PROFILE_RULE,), contract.contract_fingerprint,
        "sha256:" + "2" * 64)

PAGE = """---
type: concept
authoring_status: drafted
---
# Page
"""


def _write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _checkpoint(root, pages=("Domain/A.md",), statuses=None):
    """Create the smallest locally valid page-projection checkpoint."""
    root = pathlib.Path(root)
    pathlib.Path(root, ".cambium/tmp").mkdir(parents=True, exist_ok=True)
    statuses = statuses or {}
    rows = []
    for relative in pages:
        rows.extend((
            "  - path: %s" % relative,
            "    coverage_disposition: required",
            "    authoring_status: %s" % statuses.get(relative, "reviewed"),
            "    next_batch:",
        ))
        _write(root / relative, PAGE)
    _write(
        root / ".cambium/state/coverage_ledger.yaml",
        "schema_version: 1\npages:\n" + "\n".join(rows) + "\n")
    return root


def _plan(root, *, rules, pages=None, ledger_override=None):
    return project_page_state.build_projection_plan(
        os.fspath(root), selected_pages=pages,
        ledger_override=ledger_override, rules=rules)


def _run_main(root, *arguments):
    output = io.StringIO()
    with redirect_stdout(output):
        code = project_page_state.main([os.fspath(root), *arguments])
    return code, output.getvalue()


@contextmanager
def _temporary_root():
    root = pathlib.Path(tempfile.mkdtemp())
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


class ProjectPageStateUnitTests(unittest.TestCase):
    """Pure projector behavior; no filesystem, subprocess, or runtime."""

    def test_semantic_fingerprint_excludes_only_contract_managed_copies(self):
        original = project_page_state.semantic_content_fingerprint(
            "Domain/A.md", PAGE, PROJECTOR_CONTRACT_RULES)
        projected = PAGE.replace(
            "authoring_status: drafted",
            "authoring_status: drafted\nreview_state: ready")
        self.assertEqual(
            original,
            project_page_state.semantic_content_fingerprint(
                "Domain/A.md", projected, PROJECTOR_CONTRACT_RULES))
        self.assertNotEqual(
            original,
            project_page_state.semantic_content_fingerprint(
                "Domain/A.md", projected.replace("# Page", "# Changed"),
                PROJECTOR_CONTRACT_RULES))


class ProjectPageStateContractTests(unittest.TestCase):
    """The writer's projection contract over already-authorized rules."""

    def test_property_owner_value_projects_without_changing_page_semantics(self):
        fingerprint = project_page_state.semantic_content_fingerprint(
            "Domain/A.md", PAGE, PROJECTOR_CONTRACT_RULES)
        row = {
            "path": "Domain/A.md",
            "property_state": {
                "review_state": {
                    "value": "ready",
                    "evidence_receipt": "audit-review-current",
                    "content_fingerprint": fingerprint,
                },
            },
        }

        projected, changes = project_page_state.project_page(
            PAGE, row, PROJECTOR_CONTRACT_RULES)

        self.assertIn("authoring_status: drafted", projected)
        self.assertIn("review_state: ready", projected)
        self.assertEqual(
            [("review_state", None, "ready")], changes)
        self.assertEqual(
            fingerprint,
            project_page_state.semantic_content_fingerprint(
                "Domain/A.md", projected, PROJECTOR_CONTRACT_RULES))

    def test_ownerless_copy_requires_explicit_contract_authorized_removal(self):
        text = PAGE.replace(
            "authoring_status: drafted",
            "authoring_status: drafted\nreview_state: ready")
        row = {"path": "Domain/A.md"}

        with self.assertRaisesRegex(ValueError, "no evidence-backed owner"):
            project_page_state.project_page(
                text, row, PROJECTOR_CONTRACT_RULES)

        projected, changes = project_page_state.project_page(
            text, row, PROJECTOR_CONTRACT_RULES,
            authorized_owner_removals=("review_state",))
        self.assertNotIn("review_state:", projected)
        self.assertEqual(
            [("review_state", "ready", None)], changes)


class ProjectPageStateIntegrationTests(unittest.TestCase):
    """Local planning and transaction seams from legal checkpoints."""

    @classmethod
    def setUpClass(cls):
        cls.rules = _current_profile_rules()

    def test_proposed_coverage_builds_after_image_without_writing_owner(self):
        with _temporary_root() as root:
            _checkpoint(root)
            ledger = root / ".cambium/state/coverage_ledger.yaml"
            before = ledger.read_bytes()
            proposed = {
                "schema_version": 1,
                "pages": [{
                    "path": "Domain/A.md",
                    "coverage_disposition": "required",
                    "authoring_status": "needs_rereview",
                    "next_batch": None,
                }],
            }

            plan = _plan(
                root, rules=self.rules, ledger_override=proposed)

            self.assertEqual(before, ledger.read_bytes())
            self.assertEqual(1, len(plan.pages))
            self.assertIn(
                b"authoring_status: needs_rereview",
                plan.pages[0].after_data)
            self.assertFalse(plan.revalidate_contract)

    def test_current_contract_main_apply_is_idempotent(self):
        with _temporary_root() as root:
            _checkpoint(root)
            page = root / "Domain/A.md"
            with mock.patch.object(
                    project_page_state, "_projection_rules",
                    return_value=self.rules):
                first_code, first_output = _run_main(root, "--apply")
                second_code, second_output = _run_main(root, "--apply")

            self.assertEqual(0, first_code, first_output)
            self.assertEqual(0, second_code, second_output)
            self.assertIn(
                "authoring_status: reviewed",
                page.read_text(encoding="utf-8"))
            self.assertIn(
                "coverage_disposition: required",
                page.read_text(encoding="utf-8"))
            self.assertIn("field_changes=0", second_output)
            self.assertFalse(pathlib.Path(
                root, ".cambium/tmp/state-writer.lock").exists())

    def test_outer_transaction_can_rollback_one_staged_plan(self):
        with _temporary_root() as root:
            _checkpoint(root)
            page = root / "Domain/A.md"
            plan = _plan(root, rules=self.rules)
            with project_page_state.kblib.runtime_write_lock(
                    os.fspath(root),
                    owner_metadata={"tool": "test-integrator"}) as lease:
                transaction = project_page_state.stage_projection_plan(
                    os.fspath(root), plan, lease, "page-projection-rollback")
                transaction.publish()
                transaction.rollback()
                lease.mark_reconciled()

            self.assertEqual(PAGE, page.read_text(encoding="utf-8"))
            self.assertFalse(pathlib.Path(
                root, ".cambium/tmp/state-writer.lock").exists())

    def test_missing_target_materialized_after_plan_is_rejected(self):
        with _temporary_root() as root:
            _checkpoint(root)
            ledger = root / ".cambium/state/coverage_ledger.yaml"
            ledger.write_text(
                "schema_version: 1\npages:\n"
                "  - path: Domain/Missing.md\n"
                "    authoring_status: reviewed\n",
                encoding="utf-8")
            plan = _plan(root, rules=self.rules)
            _write(root / "Domain/Missing.md", PAGE)

            with self.assertRaisesRegex(OSError, "unmaterialized page changed"):
                project_page_state._revalidate_plan_inputs(
                    os.fspath(root), plan)
            self.assertEqual(PAGE, (root / "Domain/Missing.md").read_text(
                encoding="utf-8"))


class ProjectPageStateSlowTests(unittest.TestCase):
    """Projection-specific currentness and recovery boundaries."""

    def test_staged_after_image_name_drift_is_rejected_before_publication(self):
        with _temporary_root() as root:
            _checkpoint(root)
            page = root / "Domain/A.md"
            original_stage = project_page_state._stage_page
            rules = _current_profile_rules()

            def replace_stage(root_path, projection):
                staged = original_stage(root_path, projection)
                staged_path = page.parent / staged.temporary_name
                staged_path.unlink()
                staged_path.write_text("foreign staged bytes\n", encoding="utf-8")
                return staged

            with mock.patch.object(
                    project_page_state, "_stage_page",
                    side_effect=replace_stage), \
                    mock.patch.object(
                        project_page_state, "_projection_rules",
                        return_value=rules):
                code, output = _run_main(root, "--apply")

            self.assertEqual(1, code, output)
            self.assertEqual(PAGE, page.read_text(encoding="utf-8"))

    def test_later_page_failure_rolls_back_earlier_publication(self):
        with _temporary_root() as root:
            _checkpoint(root, pages=("Domain/A.md", "Domain/B.md"))
            original_publish = project_page_state._publish_staged
            publications = 0
            rules = _current_profile_rules()

            def fail_second(root_path, staged):
                nonlocal publications
                publications += 1
                if publications == 2:
                    raise OSError("injected second-page failure")
                return original_publish(root_path, staged)

            with mock.patch.object(
                    project_page_state, "_publish_staged",
                    side_effect=fail_second), \
                    mock.patch.object(
                        project_page_state, "_projection_rules",
                        return_value=rules):
                code, output = _run_main(root, "--apply")

            self.assertEqual(1, code, output)
            self.assertEqual(2, publications)
            self.assertEqual(PAGE, (root / "Domain/A.md").read_text(
                encoding="utf-8"))
            self.assertEqual(PAGE, (root / "Domain/B.md").read_text(
                encoding="utf-8"))
            self.assertFalse(pathlib.Path(
                root, ".cambium/tmp/state-writer.lock").exists())

    def test_foreign_published_edit_is_preserved_with_recovery_evidence(self):
        with _temporary_root() as root:
            _checkpoint(root)
            page = root / "Domain/A.md"
            concurrent = PAGE.replace("# Page", "# Concurrent")
            plan = _plan(root, rules=_current_profile_rules())

            with self.assertRaisesRegex(ValueError, "rollback is incomplete"):
                with project_page_state.kblib.runtime_write_lock(
                        os.fspath(root),
                        owner_metadata={"tool": "test-integrator"}) as lease:
                    transaction = project_page_state.stage_projection_plan(
                        os.fspath(root), plan, lease, "foreign-edit")
                    transaction.publish()
                    page.write_text(concurrent, encoding="utf-8")
                    transaction.rollback()

            self.assertEqual(concurrent, page.read_text(encoding="utf-8"))
            lock = root / ".cambium/tmp/state-writer.lock"
            self.assertTrue(lock.is_dir())
            journal = json.loads((
                lock / project_page_state.JOURNAL_NAME).read_text(
                    encoding="utf-8"))
            self.assertEqual("rollback-required", journal["status"])


if __name__ == "__main__":
    unittest.main()
