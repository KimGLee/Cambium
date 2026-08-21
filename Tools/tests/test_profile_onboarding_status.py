"""`Tools/profile_onboarding_status.py` — the read-only status projector.

The projector derives one onboarding view and exactly one `next_action`
token from bytes owned elsewhere (adopter Standards state, profiles/, the corpus tree,
`.cambium/`).  This module pins the full decision table over temp-root
fixtures, that the tool degrades gracefully off a Cambium root, that its
`--json` output is deterministic, and — because a status *projector* that
writes anything would be a second ledger — that a run leaves the tree
byte-identical.

Regression tests, not gates: no receipt, no Gate ID, no answer-quality call.
"""

import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
TEMPLATE = REPOSITORY / "profiles" / "_template"
K00_03_RELATIVE = ("kernel/K00 Standards Control/"
                   "03 Standards Governance.md")

sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))
import profile_onboarding_status  # noqa: E402
import check_profile  # noqa: E402
import kblib  # noqa: E402
import metadata_execution_contract  # noqa: E402
import scaffold_profile  # noqa: E402
import standards_state  # noqa: E402
import test_template_fill  # noqa: E402  (reused semantic fill + scan config)

# Extra root-owned inputs used by this onboarding fixture outside the
# canonical profile-load set.  The canonical set itself is derived below from
# the producer and its installed capability registry: copying a hand-written
# subset made this fixture report an open interview when profile-load had in
# fact stopped before semantic evaluation because a newly registered input
# was absent.
ONBOARDING_FIXTURE_FILES = (
    "Tools/schemas/residual_scan_config.template.yaml",
    "Tools/check_residual_content.py",
)

FILLED_ID = test_template_fill.PROFILE_ID  # the FILL text names this id


def profile_load_fixture_files():
    """Exact files one scratch-root profile-load must be able to snapshot."""
    capabilities = kblib.parse_yaml_subset(
        (REPOSITORY / check_profile.DEFAULT_OPERATION_CAPABILITIES).read_text(
            encoding="utf-8"))
    implementations = \
        metadata_execution_contract.capability_implementation_paths(
            capabilities)
    return tuple(sorted(set(
        check_profile.CANONICAL_PROFILE_LOAD_INPUTS +
        tuple(implementations) + ONBOARDING_FIXTURE_FILES)))


def copy_profile_load_fixture(root):
    """Copy the producer's closed input set into one minimal adopting root."""
    for relative in profile_load_fixture_files():
        target = Path(root) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY / relative, target)


def make_root(tmp):
    """A minimal adopting root the scaffolder and check_profile accept."""
    root = Path(tmp) / "repo"
    copy_profile_load_fixture(root)
    for relative in (K00_03_RELATIVE, "profiles/template-files.yaml"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY / relative, target)
    shutil.copytree(TEMPLATE, root / "profiles" / "_template")
    return root


def run_status(root, *extra):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = profile_onboarding_status.main([str(root), *extra])
    return code, buffer.getvalue()


def run_status_json(root, *extra):
    code, out = run_status(root, "--json", *extra)
    return code, json.loads(out), out


def scaffold(root, profile_id):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = scaffold_profile.main(
            [str(root), "--profile-id=%s" % profile_id, "--apply"])
    assert code == 0, buffer.getvalue()


def fill_candidate(root, profile_id=FILLED_ID):
    """A completely filled candidate, reusing the shared template fill."""
    profile = root / "profiles" / profile_id
    shutil.copytree(TEMPLATE, profile)
    (profile / "README.md").unlink()
    for relative, old, new in test_template_fill.FILL:
        path = profile / relative
        text = path.read_text(encoding="utf-8")
        assert old in text, (relative, old)
        path.write_text(
            text.replace(old, new.replace(FILLED_ID, profile_id), 1),
            encoding="utf-8")
    (profile / "scan-configs" / "residual-scan.yaml").write_text(
        test_template_fill.SCAN_CONFIG, encoding="utf-8")
    return profile


def adopt(root, manifest_relative, fields=None):
    """Materialize canonical state, optionally omitting fields for a fault."""
    values = {
        "schema_version": 1,
        "state_revision": 1,
        "standards_version": "adopt-v1",
        "status": "approved",
        "effective_date": "2026-08-13",
        "selected_profile_manifest": manifest_relative,
        "latest_adoption_receipt": "audit-fixture-adoption",
        "upstream_source_ref": None,
        "upstream_revision_id": None,
    }
    if fields is not None:
        values = {field: values[field] for field in fields}
    path = root / standards_state.STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(kblib.canonical_yaml(values), encoding="utf-8")


def tree_state(root):
    """Every path under ``root`` with a content/type fingerprint."""
    state = {}
    for path in sorted(Path(root).rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            state[relative] = "symlink:%s" % path.readlink()
        elif path.is_dir():
            state[relative] = "dir"
        else:
            state[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return state


class PreAdoptionTests(unittest.TestCase):
    def test_no_candidate_asks_to_confirm_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertTrue(view["adopting_root"])
            self.assertEqual("pre-adoption", view["standards_state"])
            self.assertIsNone(view["selected_profile"])
            self.assertIsNone(view["corpus_planning_state"])
            self.assertEqual([], view["candidates"])
            self.assertEqual("empty", view["corpus_state"])
            self.assertEqual(0, view["corpus_page_count"])
            self.assertFalse(view["cambium_runtime"]["present"])
            self.assertEqual("confirm-profile-identity", view["next_action"])
            self.assertTrue(any("scaffold_profile" in note
                                for note in view["notes"]))

    def test_scaffolded_candidate_needs_the_interview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            scaffold(root, "cand")
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual("complete-profile-interview",
                             view["next_action"])
            self.assertEqual(1, len(view["candidates"]))
            entry = view["candidates"][0]
            self.assertEqual("profiles/cand", entry["directory"])
            self.assertEqual("cand", entry["profile_id"])
            self.assertTrue(entry["targeted"])
            self.assertGreater(entry["sentinel_count"], 0)
            load = entry["profile_load"]
            self.assertEqual("fail", load["result"])
            self.assertGreater(load["semantic_unresolved"], 0)
            # A fresh scaffold fails only on its open semantic answers; a
            # mechanical finding would mean a derived rewrite is wrong.
            self.assertEqual(0, load["mechanical"])
            # The template's Corpus Planning slot resolves in its shipped
            # inactive branch even before the interview is complete.
            self.assertEqual("not-applicable", view["corpus_planning_state"])

    def test_filled_candidate_awaits_r09_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            fill_candidate(root)
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual("authorize-r09", view["next_action"])
            entry = view["candidates"][0]
            self.assertEqual(0, entry["sentinel_count"])
            self.assertEqual("pass", entry["profile_load"]["result"])
            self.assertEqual(0, entry["profile_load"]["mechanical"])
            self.assertEqual(
                0, entry["profile_load"]["semantic_unresolved"])
            self.assertTrue(any("R09" in note for note in view["notes"]))

    def test_multiple_candidates_require_explicit_targeting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            scaffold(root, "cand-a")
            scaffold(root, "cand-b")
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual("confirm-profile-identity", view["next_action"])
            self.assertTrue(any("cand-a" in note and "cand-b" in note
                                for note in view["notes"]))
            self.assertEqual(
                [None, None],
                [entry["profile_load"] for entry in view["candidates"]])

            code, view, _ = run_status_json(root, "--profile-id", "cand-a")
            self.assertEqual(0, code)
            self.assertEqual("complete-profile-interview",
                             view["next_action"])
            targeted = [entry["directory"] for entry in view["candidates"]
                        if entry["targeted"]]
            self.assertEqual(["profiles/cand-a"], targeted)

    def test_unknown_profile_id_reports_the_real_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            scaffold(root, "cand")
            code, view, _ = run_status_json(
                root, "--profile-id", "no-such-candidate")
            self.assertEqual(0, code)
            self.assertEqual("confirm-profile-identity", view["next_action"])
            self.assertTrue(any("no-such-candidate" in note
                                for note in view["notes"]))


class AdoptedTests(unittest.TestCase):
    def adopted_root(self, tmp):
        root = make_root(tmp)
        fill_candidate(root)
        adopt(root, "profiles/%s/profile.md" % FILLED_ID)
        return root

    def test_empty_corpus_asks_for_bounded_founding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.adopted_root(tmp)
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual("adopted", view["standards_state"])
            self.assertEqual(
                {"standards_version": "adopt-v1",
                 "status": "approved",
                 "effective_date": "2026-08-13",
                 "selected_profile_manifest":
                     "profiles/%s/profile.md" % FILLED_ID},
                view["standards_values"])
            self.assertEqual("profiles/%s/profile.md" % FILLED_ID,
                             view["selected_profile"])
            self.assertEqual("empty", view["corpus_state"])
            self.assertEqual("found-empty-corpus", view["next_action"])
            self.assertTrue(any(
                "one canonical owner" in note and "Corpus Planning" in note
                for note in view["notes"]))

    def test_existing_corpus_with_not_applicable_planning_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.adopted_root(tmp)
            (root / "Notes").mkdir()
            (root / "Notes" / "service.md").write_text(
                "# Service\n", encoding="utf-8")
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual("existing", view["corpus_state"])
            self.assertEqual(1, view["corpus_page_count"])
            self.assertEqual("not-applicable", view["corpus_planning_state"])
            self.assertEqual("onboarding-complete", view["next_action"])
            self.assertTrue(any(
                "bounded content routes are available now" in note and
                "Corpus Planning" in note and "R09" in note
                for note in view["notes"]))

    def test_existing_corpus_with_configured_planning_wants_a_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.adopted_root(tmp)
            (root / "Notes").mkdir()
            (root / "Notes" / "service.md").write_text(
                "# Service\n", encoding="utf-8")
            planning = (root / "profiles" / FILLED_ID /
                        "corpus-planning.yaml")
            planning.write_text(
                planning.read_text(encoding="utf-8").replace(
                    "state: not-applicable", "state: configured", 1),
                encoding="utf-8")
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual("configured", view["corpus_planning_state"])
            self.assertFalse(view["cambium_runtime"]["present"])
            self.assertEqual("prepare-task-plan", view["next_action"])

    def test_distribution_files_are_not_corpus_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.adopted_root(tmp)
            (root / "README.md").write_text("# Dist\n", encoding="utf-8")
            (root / "README.zh-CN.md").write_text("# Dist\n",
                                                  encoding="utf-8")
            (root / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text("# G\n",
                                                    encoding="utf-8")
            (root / ".obsidian").mkdir()
            (root / ".obsidian" / "note.md").write_text("# N\n",
                                                        encoding="utf-8")
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual(0, view["corpus_page_count"])
            self.assertEqual("found-empty-corpus", view["next_action"])


class RuntimeRecoveryTests(unittest.TestCase):
    def test_cambium_runtime_beats_every_other_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            fill_candidate(root)
            adopt(root, "profiles/%s/profile.md" % FILLED_ID)
            state = root / ".cambium" / "state"
            state.mkdir(parents=True)
            (state / "required_queue.yaml").write_text(
                "task_id: live\n", encoding="utf-8")
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual("resume-existing-task", view["next_action"])
            self.assertTrue(view["cambium_runtime"]["present"])
            self.assertTrue(view["cambium_runtime"]["state_has_content"])
            self.assertTrue(any("--resume-status" in note
                                for note in view["notes"]))

    def test_governance_only_namespace_is_not_a_task_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            (root / ".cambium").mkdir()
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual("confirm-profile-identity", view["next_action"])
            self.assertFalse(view["cambium_runtime"]["present"])
            self.assertFalse(view["cambium_runtime"]["state_has_content"])


class ControlStateTests(unittest.TestCase):
    def test_partial_instantiation_is_inconsistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            adopt(root, "profiles/x/profile.md",
                  fields=("schema_version", "standards_version"))
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual("inconsistent", view["standards_state"])
            self.assertEqual([], view["standards_uninstantiated"])
            self.assertEqual("repair-control-state", view["next_action"])
            self.assertTrue(any(
                "misses field(s)" in note and
                "selected_profile_manifest" in note
                for note in view["notes"]))

    def test_unreadable_control_file_is_inconsistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            path = root / standards_state.STATE_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            path.mkdir()
            code, view, _ = run_status_json(root)
            self.assertEqual(0, code)
            self.assertEqual("inconsistent", view["standards_state"])
            self.assertEqual("repair-control-state", view["next_action"])


class NonCambiumRootTests(unittest.TestCase):
    def test_plain_directory_degrades_to_its_own_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "plain"
            plain.mkdir()
            (plain / "notes.md").write_text("# n\n", encoding="utf-8")
            code, view, _ = run_status_json(plain)
            self.assertEqual(0, code)
            self.assertFalse(view["adopting_root"])
            self.assertEqual("not-a-cambium-root", view["next_action"])
            self.assertIsNone(view["standards_state"])
            self.assertEqual([], view["candidates"])

    def test_missing_root_is_an_invocation_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_status(Path(tmp) / "does-not-exist")
            self.assertEqual(1, code)
            self.assertIn("not an existing directory", out)


class DeterminismAndReadOnlyTests(unittest.TestCase):
    def test_json_is_deterministic_and_the_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            scaffold(root, "cand")
            before = tree_state(root)
            code_one, _, out_one = run_status_json(root)
            code_two, _, out_two = run_status_json(root)
            _human_code, _human_out = run_status(root)
            self.assertEqual(0, code_one)
            self.assertEqual(0, code_two)
            self.assertEqual(out_one, out_two,
                             "two --json runs must be byte-identical")
            self.assertEqual(
                before, tree_state(root),
                "a status projector must leave the tree byte-identical: "
                "no receipts, no state, no ledger")
            self.assertFalse((root / ".cambium").exists())


if __name__ == "__main__":
    unittest.main()
