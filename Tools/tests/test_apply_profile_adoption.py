"""Current-contract Profile adoption plan, writer, and recovery tests.

Profile shape and semantic admission belong to their dedicated contract and
admission suites. Adoption lineage owns Receipt relationships. This module
tests only the no-task-runtime plan boundary and the writer transaction that
publishes one already-authorized Profile selection. Minimal current-contract
writer checkpoints replace per-method full-repository construction.
"""

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import Tools.governance.profile.apply_profile_adoption as apply_profile_adoption
from Tools.tests.support.profile_adoption_fixture import (
    GOVERNANCE,
    MANIFEST,
    PLAN_RELATIVE,
    PROFILE_ID,
    UPSTREAM_REVISION,
    build_writer_checkpoint,
    clone_writer_checkpoint,
    governance_state,
    run_writer_tool,
    tree_state,
    writer_initial_plan,
    writer_revision_plan,
    writer_step,
    write_plan,
)


def contract_plan(branch=apply_profile_adoption.BRANCH_INITIAL):
    digest = "sha256:" + "1" * 64
    initial = branch == apply_profile_adoption.BRANCH_INITIAL
    return {
        "schema_version": 3,
        "plan_id": "PA-CONTRACT",
        "branch": branch,
        "upstream_revision_id_after": "a" * 40,
        "standards_status_after": "approved",
        "standards_effective_date_after": "2026-08-13",
        "selected_profile_manifest_after": "profiles/cand/profile.md",
        "upstream_revision_id_before": None if initial else "a" * 40,
        "selected_profile_manifest_before": (
            None if initial else "profiles/cand/profile.md"),
        "change_summary": "Adopt one confirmed Profile",
        "changed_predicates": [],
        "adoption_requirement": "none",
        "k00_03_sha256_before": digest,
        "standards_state_sha256_before": None if initial else digest,
        "upstream_source_ref": "https://example.test/corpus.git",
        "profile_snapshot_sha256_after": digest,
        "profile_contract_fingerprint_after": digest,
        "profile_load_inputs_sha256_after": digest,
    }


def stagings(root):
    return sorted(
        entry.name for entry in Path(root).iterdir()
        if entry.name.startswith(apply_profile_adoption.STAGING_PREFIX))


def journal_of(root, staging_name):
    return json.loads((
        Path(root) / staging_name / "journal.json"
    ).read_text(encoding="utf-8"))


def adoption_rows(root):
    path = Path(root) / ".cambium/receipts/standards-adoptions.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def commit_rows(root):
    return [row for row in adoption_rows(root)
            if row.get("tool") == "apply_profile_adoption"]


def mutate_candidate(root):
    """Change candidate bytes without making the Profile unloadable."""
    path = Path(root) / "profiles" / PROFILE_ID / "corpus-planning.yaml"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"reason: (.+)", text)
    path.write_text(
        text.replace(
            match.group(0),
            'reason: "Corpus refounded; planning deferred."', 1),
        encoding="utf-8",
    )


class ProfileAdoptionContractTests(unittest.TestCase):
    def test_plan_contract_separates_no_runtime_adoption_from_active_tasks(self):
        for branch in (
                apply_profile_adoption.BRANCH_INITIAL,
                apply_profile_adoption.BRANCH_REVISION):
            with self.subTest(branch=branch):
                apply_profile_adoption.validate_plan_values(
                    contract_plan(branch), "adoption-plans/PA-CONTRACT.yaml")

        for field, value, expected in (
                ("changed_predicates",
                 [{"predicate_id": "PRED-X", "change_kind": "modified"}],
                 "active-task adoption"),
                ("adoption_requirement", "required", "active-task")):
            with self.subTest(field=field):
                plan = contract_plan()
                plan[field] = value
                with self.assertRaisesRegex(
                        apply_profile_adoption.AdoptionRefusal, expected):
                    apply_profile_adoption.validate_plan_values(
                        plan, "adoption-plans/PA-CONTRACT.yaml")

    def test_branch_state_requires_the_exact_absent_or_present_identity(self):
        initial = contract_plan()
        apply_profile_adoption.check_branch_state(initial, None)
        with self.assertRaisesRegex(
                apply_profile_adoption.AdoptionRefusal,
                "current state already exists"):
            apply_profile_adoption.check_branch_state(initial, {})

        revision = contract_plan(apply_profile_adoption.BRANCH_REVISION)
        current = {
            "upstream_revision_id": revision["upstream_revision_id_before"],
            "selected_profile_manifest":
                revision["selected_profile_manifest_before"],
        }
        apply_profile_adoption.check_branch_state(revision, current)
        with self.assertRaisesRegex(
                apply_profile_adoption.AdoptionRefusal,
                "requires an existing"):
            apply_profile_adoption.check_branch_state(revision, None)
        with self.assertRaisesRegex(
                apply_profile_adoption.AdoptionRefusal,
                "does not match current"):
            apply_profile_adoption.check_branch_state(
                revision, dict(current, upstream_revision_id="b" * 40))

    def test_task_runtime_namespace_routes_to_the_active_task_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".cambium/governance").mkdir(parents=True)
            self.assertIsNone(
                apply_profile_adoption.find_runtime_namespace(str(root)))
            (root / "corpus/.cambium/state").mkdir(parents=True)
            self.assertEqual(
                "corpus/.cambium",
                apply_profile_adoption.find_runtime_namespace(str(root)),
            )


class ProfileAdoptionWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checkpoint_temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.checkpoint_temporary.cleanup)
        temporary = Path(cls.checkpoint_temporary.name).resolve()
        cls.base_root = temporary / "base"
        build_writer_checkpoint(cls.base_root)
        cls.adopted_root = temporary / "adopted"
        clone_writer_checkpoint(cls.base_root, cls.adopted_root)
        write_plan(
            cls.adopted_root, writer_initial_plan(cls.adopted_root))
        code, output = run_writer_tool(cls.adopted_root, "--apply")
        if code != 0:
            raise AssertionError(output)

    def clone(self, source=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve() / "repo"
        clone_writer_checkpoint(
            source if source is not None else self.base_root, root)
        return root

    def assert_refused_without_writes(self, root, fragment):
        before = tree_state(root)
        code, output = run_writer_tool(root, "--apply")
        self.assertEqual(1, code, output)
        self.assertIn(fragment, output)
        self.assertEqual(before, tree_state(root))
        self.assertEqual([], stagings(root))

    def test_initial_dry_run_then_commit_publishes_one_current_after_image(self):
        root = self.clone()
        plan = writer_initial_plan(root)
        write_plan(root, plan)
        profile_before = tree_state(root / "profiles" / PROFILE_ID)
        before = tree_state(root)

        code, output = run_writer_tool(root)
        self.assertEqual(0, code, output)
        self.assertEqual(before, tree_state(root))
        self.assertEqual([], stagings(root))

        code, output = run_writer_tool(root, "--apply")
        self.assertEqual(0, code, output)

        state = governance_state(root)
        rows = adoption_rows(root)
        gate, commit = rows
        self.assertEqual(UPSTREAM_REVISION, state["upstream_revision_id"])
        self.assertEqual(MANIFEST, state["selected_profile_manifest"])
        self.assertEqual(commit["receipt_id"],
                         state["latest_adoption_receipt"])
        self.assertEqual("profile-load", gate["gate_id"])
        self.assertEqual(gate["receipt_id"],
                         commit["profile_load_receipt_id"])
        self.assertEqual(plan["profile_snapshot_sha256_after"],
                         gate["profile_snapshot_sha256"])
        self.assertEqual(PLAN_RELATIVE, commit["plan_path"])
        self.assertTrue(
            (root / apply_profile_adoption.VOCAB_ARTIFACT).is_file())
        self.assertTrue(
            (root / apply_profile_adoption.PAGE_CONTRACT_ARTIFACT).is_file())
        self.assertFalse((root / ".cambium/state").exists())
        self.assertEqual(
            profile_before, tree_state(root / "profiles" / PROFILE_ID))
        self.assertEqual([], stagings(root))

    def test_profile_revision_appends_current_history_without_rewriting_profile(self):
        root = self.clone(self.adopted_root)
        first = commit_rows(root)[0]
        mutate_candidate(root)
        relative = write_plan(
            root, writer_revision_plan(root), "adoption-plans/PA-002.yaml")
        profile_before = tree_state(root / "profiles" / PROFILE_ID)
        code, output = run_writer_tool(root, "--apply", plan=relative)
        self.assertEqual(0, code, output)
        rows = commit_rows(root)
        self.assertEqual(2, len(rows))
        self.assertEqual(first["receipt_id"], rows[0]["receipt_id"])
        self.assertEqual(rows[-1]["receipt_id"],
                         governance_state(root)["latest_adoption_receipt"])
        self.assertEqual(
            profile_before, tree_state(root / "profiles" / PROFILE_ID))
        self.assertFalse((root / ".cambium/state").exists())

    def test_prewrite_currentness_rejects_governance_or_candidate_drift(self):
        for mutation, fragment in (
                ("governance", "k00_03_sha256_before"),
                ("candidate", "profile_snapshot_sha256_after")):
            with self.subTest(mutation=mutation):
                root = self.clone()
                write_plan(root, writer_initial_plan(root))
                if mutation == "governance":
                    path = root / GOVERNANCE
                    path.write_text(
                        path.read_text(encoding="utf-8") + "\n",
                        encoding="utf-8")
                else:
                    mutate_candidate(root)
                self.assert_refused_without_writes(root, fragment)

    def test_uncertain_receipt_publication_rolls_back_without_success(self):
        root = self.clone()
        write_plan(root, writer_initial_plan(root))
        before = tree_state(root)

        def uncertain(_path, _receipts, exclusive=False, before=None):
            return "uncertain", OSError("injected uncertain append"), before

        with mock.patch.object(
                apply_profile_adoption.kblib, "write_receipts_observed",
                uncertain):
            code, output = run_writer_tool(root, "--apply")
        self.assertEqual(1, code, output)
        self.assertIn("could not be proven durable", output)
        self.assertEqual(before, tree_state(root))
        journal = journal_of(root, stagings(root)[0])
        self.assertEqual("aborted", journal["status"])
        self.assertEqual("uncertain", journal["receipt_publication_outcome"])

    def test_result_readback_interruption_recovers_by_current_revalidation(self):
        root = self.clone()
        write_plan(root, writer_initial_plan(root))
        with mock.patch.object(
                apply_profile_adoption, "validate_resulting_state",
                side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                run_writer_tool(root, "--apply")
        self.assertEqual(
            "verifying", journal_of(root, stagings(root)[0])["status"])

        code, output = run_writer_tool(root, "--apply")
        self.assertEqual(0, code, output)
        self.assertEqual([], stagings(root))
        self.assertEqual(1, len(commit_rows(root)))

    def test_projection_failure_restores_every_authoritative_byte(self):
        root = self.clone()
        write_plan(root, writer_initial_plan(root))
        before = tree_state(root)

        def failing(command, cwd):
            if any("compose_page_contract.py" in str(part)
                   for part in command):
                return 1, "injected projection failure"
            return writer_step(command, cwd)

        code, output = run_writer_tool(
            root, "--apply", step_runner=failing)
        self.assertEqual(1, code, output)
        self.assertIn("restored", output)
        self.assertEqual(before, tree_state(root))
        self.assertFalse((root / ".cambium").exists())
        journal = journal_of(root, stagings(root)[0])
        self.assertEqual("aborted", journal["status"])
        self.assertTrue(journal["restore_verified"])

    def test_interrupted_write_accepts_only_the_same_current_plan_on_retry(self):
        root = self.clone()
        write_plan(root, writer_initial_plan(root))

        def interrupting(command, cwd):
            if any("compose_page_contract.py" in str(part)
                   for part in command):
                raise KeyboardInterrupt()
            return writer_step(command, cwd)

        with self.assertRaises(KeyboardInterrupt):
            run_writer_tool(root, "--apply", step_runner=interrupting)
        self.assertEqual("writing", journal_of(
            root, stagings(root)[0])["status"])

        different = writer_initial_plan(
            root, plan_id="PA-OTHER",
            change_summary="A different current plan")
        different_relative = write_plan(
            root, different, "adoption-plans/PA-OTHER.yaml")
        interrupted = tree_state(root)
        code, output = run_writer_tool(
            root, "--apply", plan=different_relative)
        self.assertEqual(1, code, output)
        self.assertIn("different plan bytes", output)
        self.assertEqual(interrupted, tree_state(root))

        code, output = run_writer_tool(root, "--apply")
        self.assertEqual(0, code, output)
        self.assertEqual([], stagings(root))
        self.assertEqual(1, len(commit_rows(root)))


if __name__ == "__main__":
    unittest.main()
