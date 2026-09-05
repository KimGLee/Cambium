"""Mechanical candidate creation, closed inputs and no-replace publication.

Contract tests invoke the real in-process entrypoint. One CLI seam proves the
public transport; adoption and semantic answer quality have separate owners.
"""

import json
import os
from pathlib import Path
import unittest
from unittest import mock

import Tools.governance.profile.profile_codec as profile_codec
import Tools.governance.profile.scaffold_profile as scaffold_profile
import Tools.platform.common.kblib as kblib
from Tools.tests.support.scaffold_profile_fixture import ScaffoldProfileFixture


PROFILE_ID = "candidate"
MANIFEST_NAME = scaffold_profile.profile_layout_contract.PROFILE_MANIFEST_NAME


class ScaffoldPredicateUnitTests(unittest.TestCase):
    def test_profile_id_acceptance_reuses_the_current_namespace_boundary(self):
        for profile_id in ("candidate", "candidate-1", "candidate_1"):
            with self.subTest(profile_id=profile_id, result="accepted"):
                self.assertIsNone(scaffold_profile.validate_profile_id(profile_id))
        rejected = (
            "", "Upper", "-leading", "a/b", "a b", "café",
            *sorted(scaffold_profile.profile_layout_contract.RESERVED_PROFILE_IDS),
        )
        for profile_id in rejected:
            with self.subTest(profile_id=profile_id, result="rejected"):
                with self.assertRaises(scaffold_profile.ScaffoldRefusal):
                    scaffold_profile.validate_profile_id(profile_id)

    def test_manifest_entries_accept_only_canonical_relative_paths(self):
        self.assertEqual("policies/residual-disposition.md",
                         scaffold_profile._relative("policies/residual-disposition.md"))
        for value in (
                "", " /absolute", "/absolute", "../outside.md",
                "a/../b.md", "a//b.md", "a\\b.md", "a.md ", None):
            with self.subTest(value=value):
                with self.assertRaises(scaffold_profile.ScaffoldRefusal):
                    scaffold_profile._relative(value)


class ScaffoldManifestContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ScaffoldProfileFixture(self, PROFILE_ID)

    def test_manifest_classifies_template_and_binds_only_confirmed_identity(self):
        copied, orientation = scaffold_profile.load_manifest(self.fixture.root)
        actual = sorted(path.relative_to(self.fixture.template).as_posix()
                        for path in self.fixture.template.rglob("*") if path.is_file())
        self.assertFalse(set(copied) & set(orientation))
        self.assertEqual(actual, sorted(copied + orientation))
        plan = scaffold_profile.build_plan(self.fixture.root, PROFILE_ID)
        self.assertEqual(copied, plan["copy"])
        self.assertEqual(orientation, plan["orientation_not_copied"])
        self.assertEqual(PROFILE_ID, plan["derived_identity"])
        self.assertEqual(
            {"schema_version": 1, "profile_id": PROFILE_ID, "slots": {}},
            profile_codec.loads_profile(plan["files"][MANIFEST_NAME]))
        for relative in copied:
            if relative != MANIFEST_NAME:
                self.assertEqual((self.fixture.template / relative).read_bytes(),
                                 plan["files"][relative])
        self.assertNotIn("rewrites", plan)

    def test_manifest_shape_and_unlisted_files_are_fail_closed(self):
        manifest = self.fixture.root / scaffold_profile.MANIFEST_RELATIVE
        original = manifest.read_bytes()
        document = kblib.parse_yaml_subset(original.decode("utf-8"))
        invalid = (
            dict(document, unknown_field=True),
            dict(document, copy=document["copy"] + [document["copy"][0]]),
            dict(document, source="profiles/another-template"),
            dict(document, copy=[value for value in document["copy"] if value != MANIFEST_NAME]),
        )
        for value in invalid:
            with self.subTest(document=value):
                manifest.write_text(kblib.canonical_yaml(value), encoding="utf-8")
                with self.assertRaises(scaffold_profile.ScaffoldRefusal):
                    scaffold_profile.load_manifest(self.fixture.root)
        manifest.write_bytes(original)
        junk = self.fixture.template / "unlisted-editor-file.md"
        junk.write_text("must not enter the plan\n", encoding="utf-8")
        plan = scaffold_profile.build_plan(self.fixture.root, PROFILE_ID)
        self.assertNotIn(junk.name, plan["copy"])
        self.assertNotIn(junk.name, plan["files"])

    def test_template_cannot_prefill_policy_or_smuggle_unknown_root_state(self):
        manifest = self.fixture.template / MANIFEST_NAME
        cases = (
            {"schema_version": 1, "slots": {}, "confirmed": True},
            {"schema_version": True, "slots": {}},
            {"schema_version": 2, "slots": {}},
            {"schema_version": 1, "profile_id": "preselected", "slots": {}},
            {"schema_version": 1, "slots": {"priority-rubric": {}}},
            {"schema_version": 1, "slots": {}, "execution_default_overrides": {"concurrency_cap": 1}},
            {"schema_version": 1},
        )
        for document in cases:
            with self.subTest(document=document):
                manifest.write_bytes(profile_codec.dumps_profile(document))
                before = self.fixture.tree_state(self.fixture.root)
                code, output = self.fixture.run("--apply", "--json")
                self.assertEqual(1, code, output)
                report = json.loads(output)
                self.assertEqual("refused", report["result"])
                self.assertFalse(report["created"])
                self.assertEqual(before, self.fixture.tree_state(self.fixture.root))

    def test_destination_conflict_preserves_every_existing_path_kind(self):
        destination = self.fixture.destination
        self.assertIsNone(scaffold_profile.destination_conflict(destination))
        for kind in ("directory", "file", "symlink"):
            with self.subTest(kind=kind):
                if kind == "directory":
                    destination.mkdir()
                elif kind == "file":
                    destination.write_text("existing file\n", encoding="utf-8")
                else:
                    destination.symlink_to("does-not-exist")
                before = self.fixture.tree_state(self.fixture.root)
                code, output = self.fixture.run("--apply", "--json")
                self.assertEqual(1, code, output)
                self.assertEqual("refused", json.loads(output)["result"])
                self.assertEqual(before, self.fixture.tree_state(self.fixture.root))
                if kind == "directory":
                    destination.rmdir()
                else:
                    destination.unlink()


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
        self.assertFalse(report["resulting_state_verified"])
        self.assertEqual(["profiles/%s/%s" % (PROFILE_ID, item) for item in plan["copy"]],
                         report["files"])
        self.assertEqual(plan["orientation_not_copied"], report["orientation_not_copied"])

    def test_apply_publishes_exactly_one_mechanical_candidate(self):
        plan = scaffold_profile.build_plan(self.fixture.root, PROFILE_ID)
        marker = self.fixture.outside_marker.read_bytes()
        code, output = self.fixture.run("--apply", "--json")
        self.assertEqual(0, code, output)
        report = json.loads(output)
        self.assertTrue(report["created"] and report["resulting_state_verified"])
        self.assertEqual(sorted(plan["copy"]), self.fixture.candidate_files())
        for relative, expected in plan["files"].items():
            self.assertEqual(expected, (self.fixture.destination / relative).read_bytes())
        for relative in plan["orientation_not_copied"]:
            self.assertFalse((self.fixture.destination / relative).exists())
        self.assertEqual(
            {"schema_version": 1, "profile_id": PROFILE_ID, "slots": {}},
            self.fixture.candidate_document())
        self.assertEqual(marker, self.fixture.outside_marker.read_bytes())
        self.assertFalse((self.fixture.root / ".cambium").exists())
        self.assertEqual([], self.fixture.staging_paths())


class ScaffoldPublicationContractTests(unittest.TestCase):
    def assert_no_published_residue(self, fixture):
        self.assertFalse(fixture.destination.exists())
        self.assertEqual([], fixture.staging_paths())

    def test_missing_symlinked_or_hardlinked_whitelist_source_never_publishes(self):
        for kind in ("missing", "symlink", "hardlink"):
            with self.subTest(kind=kind):
                fixture = ScaffoldProfileFixture(self, PROFILE_ID)
                target = fixture.template / MANIFEST_NAME
                body = target.read_bytes()
                target.unlink()
                if kind != "missing":
                    aside = fixture.root / "outside-source.toml"
                    aside.write_bytes(body)
                    if kind == "symlink":
                        target.symlink_to(aside)
                    else:
                        os.link(aside, target)
                code, output = fixture.run("--apply", "--json")
                self.assertEqual(1, code, output)
                self.assert_no_published_residue(fixture)

    def test_race_failure_and_interruption_share_one_prepublication_cleanup_boundary(self):
        original_publish = scaffold_profile._publish_directory
        raced = ScaffoldProfileFixture(self, PROFILE_ID)

        def race(staging, destination):
            Path(destination).mkdir()
            original_publish(staging, destination)

        with mock.patch.object(scaffold_profile, "_publish_directory", side_effect=race):
            code, output = raced.run("--apply", "--json")
        self.assertEqual(1, code, output)
        self.assertFalse(json.loads(output)["created"])
        self.assertEqual([], list(raced.destination.iterdir()))
        self.assertEqual([], raced.staging_paths())

        failed = ScaffoldProfileFixture(self, PROFILE_ID)
        with mock.patch.object(scaffold_profile.os, "fsync",
                               side_effect=OSError("injected staging flush failure")):
            code, output = failed.run("--apply", "--json")
        self.assertEqual(1, code, output)
        self.assert_no_published_residue(failed)

        interrupted = ScaffoldProfileFixture(self, PROFILE_ID)
        with mock.patch.object(scaffold_profile, "_publish_directory",
                               side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                interrupted.run("--apply")
        self.assert_no_published_residue(interrupted)

    def test_postpublication_readback_failure_reports_uncertain_created_state(self):
        fixture = ScaffoldProfileFixture(self, PROFILE_ID)
        original_publish = scaffold_profile._publish_directory

        def publish_then_mutate(staging, destination):
            original_publish(staging, destination)
            (Path(destination) / MANIFEST_NAME).write_bytes(b"changed = true\n")

        with mock.patch.object(scaffold_profile, "_publish_directory",
                               side_effect=publish_then_mutate):
            code, output = fixture.run("--apply", "--json")
        report = json.loads(output)
        self.assertEqual(1, code)
        self.assertEqual("uncertain", report["result"])
        self.assertTrue(report["created"])
        self.assertFalse(report["resulting_state_verified"])
        self.assertEqual("inspect-published-candidate", report["next_action"])
        self.assertTrue(fixture.destination.is_dir())
        self.assertEqual(b"changed = true\n", (fixture.destination / MANIFEST_NAME).read_bytes())
        self.assertEqual([], fixture.staging_paths())


class ScaffoldCliTransportTests(unittest.TestCase):
    def test_json_cli_reports_one_created_candidate(self):
        fixture = ScaffoldProfileFixture(self, PROFILE_ID)
        completed = fixture.run_cli("--apply", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("scaffold_profile", report["tool"])
        self.assertEqual("created", report["result"])
        self.assertTrue(report["created"] and report["resulting_state_verified"])
        self.assertEqual({}, fixture.candidate_document()["slots"])


if __name__ == "__main__":
    unittest.main()
