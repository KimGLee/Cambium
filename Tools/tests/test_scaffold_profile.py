"""Primary owner tests for the current candidate Profile scaffolder.

The scaffolder owns only the mechanical ``profiles/_template`` to candidate
projection, its parameters, and safe publication.  Template answer quality,
filled-template validation, examples, onboarding, and adoption are verified by
their own primary suites and are deliberately absent here.
"""

import json
from pathlib import Path
import unittest
from unittest import mock

import Tools.governance.profile.scaffold_profile as scaffold_profile
from Tools.tests.support.scaffold_profile_fixture import (
    ScaffoldProfileFixture,
)


PROFILE_ID = "candidate"


class ScaffoldPredicateUnitTests(unittest.TestCase):
    def test_profile_id_acceptance_reuses_the_current_namespace_boundary(self):
        for profile_id in ("candidate", "candidate-1", "candidate_1"):
            with self.subTest(profile_id=profile_id, result="accepted"):
                self.assertIsNone(
                    scaffold_profile.validate_profile_id(profile_id))
        rejected = (
            "", "Upper", "-leading", "a/b", "a b", "café",
            *sorted(scaffold_profile.profile_layout_contract.
                    RESERVED_PROFILE_IDS),
        )
        for profile_id in rejected:
            with self.subTest(profile_id=profile_id, result="rejected"):
                with self.assertRaises(scaffold_profile.ScaffoldRefusal):
                    scaffold_profile.validate_profile_id(profile_id)

    def test_manifest_entries_accept_only_canonical_relative_paths(self):
        self.assertEqual(
            "registries/roles.md",
            scaffold_profile._canonical_manifest_entry(
                "registries/roles.md", "copy"))
        for value in (
                "", " /absolute", "/absolute", "../outside.md",
                "a/../b.md", "a//b.md", "a\\b.md", "a.md ", None):
            with self.subTest(value=value):
                with self.assertRaises(scaffold_profile.ScaffoldRefusal):
                    scaffold_profile._canonical_manifest_entry(value, "copy")


class ScaffoldManifestContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ScaffoldProfileFixture(self, PROFILE_ID)

    def test_manifest_classifies_current_template_and_rewrites_once(self):
        copy, orientation = scaffold_profile.load_manifest(self.fixture.root)
        self.assertFalse(set(copy) & set(orientation))
        actual = sorted(
            path.relative_to(self.fixture.template).as_posix()
            for path in self.fixture.template.rglob("*") if path.is_file())
        self.assertEqual(actual, sorted(copy + orientation))

        plan = scaffold_profile.build_plan(self.fixture.root, PROFILE_ID)
        self.assertEqual(copy, plan["copy"])
        self.assertEqual(orientation, plan["orientation_not_copied"])
        self.assertEqual(
            list(scaffold_profile.derived_rewrites(PROFILE_ID)),
            [(row["file"], row["old"], row["new"])
             for row in plan["rewrites"]])
        for row in plan["rewrites"]:
            source = (self.fixture.template / row["file"]).read_text(
                encoding="utf-8")
            after = plan["files"][row["file"]].decode("utf-8")
            self.assertEqual(1, source.count(row["old"]))
            self.assertNotIn(row["old"], after)
            self.assertIn(row["new"], after)
        self.assertTrue(any(
            scaffold_profile.SENTINEL.encode("utf-8") in body
            for body in plan["files"].values()))

    def test_manifest_shape_and_unlisted_files_are_fail_closed(self):
        manifest = self.fixture.root / scaffold_profile.MANIFEST_RELATIVE
        original = manifest.read_text(encoding="utf-8")
        invalid_documents = (
            original + "\nunknown_field: true\n",
            original.replace(
                "copy:\n", "copy:\n  - corpus-planning.yaml\n", 1),
            original.replace(
                "source: profiles/_template",
                "source: profiles/another-template", 1),
        )
        for document in invalid_documents:
            with self.subTest(document=document[-60:]):
                manifest.write_text(document, encoding="utf-8")
                with self.assertRaises(scaffold_profile.ScaffoldRefusal):
                    scaffold_profile.load_manifest(self.fixture.root)
        manifest.write_text(original, encoding="utf-8")

        junk = self.fixture.template / "unlisted-editor-file.md"
        junk.write_text("must not enter the plan\n", encoding="utf-8")
        plan = scaffold_profile.build_plan(self.fixture.root, PROFILE_ID)
        self.assertNotIn(junk.name, plan["copy"])
        self.assertNotIn(junk.name, plan["files"])

    def test_destination_conflict_classifies_every_existing_path_kind(self):
        destination = self.fixture.destination
        self.assertIsNone(scaffold_profile.destination_conflict(destination))

        destination.mkdir()
        self.assertIn(
            "directory", scaffold_profile.destination_conflict(destination))
        destination.rmdir()

        destination.write_text("existing file\n", encoding="utf-8")
        self.assertIn(
            "file", scaffold_profile.destination_conflict(destination))
        destination.unlink()

        destination.symlink_to("does-not-exist")
        self.assertIn(
            "symlink", scaffold_profile.destination_conflict(destination))


class ScaffoldWriterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ScaffoldProfileFixture(self, PROFILE_ID)

    def test_dry_run_projects_the_plan_without_writing(self):
        before = self.fixture.tree_state(self.fixture.root)
        code, output = self.fixture.run("--json")
        report = json.loads(output)
        plan = scaffold_profile.build_plan(self.fixture.root, PROFILE_ID)

        self.assertEqual(0, code)
        self.assertEqual(before, self.fixture.tree_state(self.fixture.root))
        self.assertEqual("dry-run", report["result"])
        self.assertFalse(report["created"])
        self.assertEqual(
            ["profiles/%s/%s" % (PROFILE_ID, item)
             for item in plan["copy"]],
            report["files"])
        self.assertEqual(
            plan["orientation_not_copied"],
            report["orientation_not_copied"])

    def test_apply_publishes_exactly_one_mechanical_candidate(self):
        plan = scaffold_profile.build_plan(self.fixture.root, PROFILE_ID)
        marker = self.fixture.outside_marker.read_bytes()
        code, output = self.fixture.run("--apply")

        self.assertEqual(0, code, output)
        self.assertEqual(plan["copy"], self.fixture.candidate_files())
        for relative, expected in plan["files"].items():
            self.assertEqual(
                expected,
                (self.fixture.destination / relative).read_bytes(),
                relative)
        for relative in plan["orientation_not_copied"]:
            self.assertFalse((self.fixture.destination / relative).exists())
        self.assertTrue(any(
            scaffold_profile.SENTINEL in path.read_text(encoding="utf-8")
            for path in self.fixture.destination.rglob("*")
            if path.is_file()))
        self.assertEqual(marker, self.fixture.outside_marker.read_bytes())
        self.assertFalse((self.fixture.root / ".cambium").exists())
        self.assertEqual([], self.fixture.staging_paths())


class ScaffoldWriterSlowTests(unittest.TestCase):
    def assert_no_published_residue(self, fixture):
        self.assertFalse(fixture.destination.exists())
        self.assertEqual([], fixture.staging_paths())

    def test_missing_or_symlinked_whitelist_source_never_publishes(self):
        for kind in ("missing", "symlink"):
            with self.subTest(kind=kind):
                fixture = ScaffoldProfileFixture(self, PROFILE_ID)
                target = fixture.template / "priority-rubric.md"
                if kind == "missing":
                    target.unlink()
                else:
                    body = target.read_bytes()
                    target.unlink()
                    aside = fixture.template / "aside.bin"
                    aside.write_bytes(body)
                    target.symlink_to("aside.bin")
                code, _output = fixture.run("--apply")
                self.assertEqual(1, code)
                self.assert_no_published_residue(fixture)

    def test_race_failure_and_interruption_share_one_cleanup_boundary(self):
        original_stage = scaffold_profile.stage_candidate

        raced = ScaffoldProfileFixture(self, PROFILE_ID)

        def stage_then_race(staging, plan):
            original_stage(staging, plan)
            raced.destination.mkdir()

        with mock.patch.object(
                scaffold_profile, "stage_candidate", stage_then_race):
            code, _output = raced.run("--apply")
        self.assertEqual(1, code)
        self.assertEqual([], list(raced.destination.iterdir()))
        self.assertEqual([], raced.staging_paths())

        failed = ScaffoldProfileFixture(self, PROFILE_ID)

        def partial_then_fail(staging, _plan):
            Path(staging, "partial").write_text("partial", encoding="utf-8")
            raise OSError("injected staging failure")

        with mock.patch.object(
                scaffold_profile, "stage_candidate", partial_then_fail):
            code, _output = failed.run("--apply")
        self.assertEqual(1, code)
        self.assert_no_published_residue(failed)

        interrupted = ScaffoldProfileFixture(self, PROFILE_ID)
        with mock.patch.object(
                scaffold_profile, "publish_candidate",
                side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                interrupted.run("--apply")
        self.assert_no_published_residue(interrupted)


class ScaffoldCliTransportTests(unittest.TestCase):
    def test_json_cli_reports_one_created_candidate(self):
        fixture = ScaffoldProfileFixture(self, PROFILE_ID)
        completed = fixture.run_cli("--apply", "--json")
        report = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("scaffold_profile", report["tool"])
        self.assertEqual("created", report["result"])
        self.assertTrue(report["created"])
        self.assertTrue(fixture.destination.is_dir())


if __name__ == "__main__":
    unittest.main()
