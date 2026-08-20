"""`Tools/scaffold_profile.py` — the safe candidate-profile scaffolder.

The scaffolder copies exactly the whitelist in `profiles/template-files.yaml`
(never a directory walk), performs only the mechanical derivations that are
pure functions of the profile id, refuses any pre-existing destination, and
leaves every semantic ``TODO(profile)`` answer in place. This module pins:

1. dry-run writes nothing anywhere (no staging directory either);
2. the whitelist and the real template agree in both directions, so a new
   template file must be classified as copied or orientation to land;
3. apply creates exactly the whitelisted files — junk planted in the
   template is never copied, orientation files are never copied;
4. any existing destination (populated directory, EMPTY directory, regular
   file, symlink) refuses distinctly with no modification;
5. invalid or reserved slugs refuse;
6. an interruption (including KeyboardInterrupt) leaves no destination and
   no staging directory behind;
7. the three interview `self_path_rewrites` and the identity land, semantic
   sentinels survive unchanged, and `check_profile.py` on the fresh
   candidate fails with sentinel findings only — no path-resolution finding
   for the rewritten cells;
8. `kernel/` (including K00/03) is untouched and no `.cambium/` appears;
9. filling only the remaining semantic answers yields a profile
   `check_profile.py` accepts, proving the derived paths are exactly the
   ones a passing fill needs.

Regression tests, not gates: no receipt, no Gate ID, no answer-quality call.
"""

import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
TEMPLATE = REPOSITORY / "profiles" / "_template"
MANIFEST = REPOSITORY / "profiles" / "template-files.yaml"
CHECK_PROFILE = TOOLS / "check_profile.py"
K00_03 = REPOSITORY / "kernel" / "K00 Standards Control" / \
    "03 Standards Governance.md"
SENTINEL = "TODO(profile)"
PROFILE_ID = "cand"

sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))
import kblib  # noqa: E402
import scaffold_profile  # noqa: E402
import test_template_fill  # noqa: E402  (reused semantic fill + scan config)
import test_profile_onboarding_status as onboarding_fixture  # noqa: E402


def make_root(tmp):
    """A minimal repository the scaffolder and check_profile both accept."""
    root = Path(tmp).resolve() / "repo"
    onboarding_fixture.copy_profile_load_fixture(root)
    for relative in (
            "kernel/K00 Standards Control/03 Standards Governance.md",
            "profiles/template-files.yaml"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY / relative, target)
    shutil.copytree(TEMPLATE, root / "profiles" / "_template")
    return root


def run_scaffold(root, profile_id, *extra):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        # `--profile-id=<slug>` keeps a leading-dash slug a value, so the
        # tool's own validation refuses it instead of argparse exiting.
        code = scaffold_profile.main(
            [str(root), "--profile-id=%s" % profile_id, *extra])
    return code, buffer.getvalue()


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


def manifest_lists():
    data = kblib.parse_yaml_subset(MANIFEST.read_text(encoding="utf-8"))
    return data["copy"], data["orientation_not_copied"]


def template_files():
    return sorted(
        path.relative_to(TEMPLATE).as_posix()
        for path in TEMPLATE.rglob("*") if path.is_file())


def candidate_files(destination):
    return sorted(
        path.relative_to(destination).as_posix()
        for path in Path(destination).rglob("*") if path.is_file())


def sentinel_counts(base, names):
    return {name: (base / name).read_text(encoding="utf-8").count(SENTINEL)
            for name in names}


class WhitelistParity(unittest.TestCase):
    """profiles/template-files.yaml must classify every real template file."""

    def test_every_template_file_is_classified_exactly_once(self):
        copy, orientation = manifest_lists()
        self.assertEqual(
            [], sorted(set(copy) & set(orientation)),
            "a file cannot be both copied and orientation")
        self.assertEqual(
            template_files(), sorted(set(copy) | set(orientation)),
            "profiles/template-files.yaml and profiles/_template drifted; "
            "classify every template file as copy or orientation")

    def test_orientation_carries_at_least_the_readme(self):
        _copy, orientation = manifest_lists()
        self.assertIn("README.md", orientation)


class DryRun(unittest.TestCase):
    def test_dry_run_writes_nothing_and_reports_the_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            before = tree_state(root)
            code, out = run_scaffold(root, PROFILE_ID)
            self.assertEqual(0, code, out)
            self.assertEqual(before, tree_state(root),
                             "dry run must write nothing anywhere")
            self.assertIn("dry run", out)
            self.assertIn("profiles/%s/profile.md" % PROFILE_ID, out)
            self.assertIn("README.md", out)
            self.assertIn("--config profiles/%s/scan-configs" % PROFILE_ID,
                          out)

    def test_dry_run_json_reports_the_structured_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            code, out = run_scaffold(root, PROFILE_ID, "--json")
            self.assertEqual(0, code, out)
            report = json.loads(out)
            copy, orientation = manifest_lists()
            self.assertFalse(report["apply"])
            self.assertFalse(report["created"])
            self.assertEqual("dry-run", report["result"])
            self.assertIsNone(report["conflict"])
            self.assertEqual(
                ["profiles/%s/%s" % (PROFILE_ID, rel) for rel in copy],
                report["files"])
            self.assertEqual(orientation, report["orientation_not_copied"])
            self.assertEqual(4, len(report["rewrites"]))
            for rewrite in report["rewrites"]:
                self.assertIn(rewrite["old"],
                              (TEMPLATE / rewrite["file"]).read_text(
                                  encoding="utf-8"))


class Apply(unittest.TestCase):
    def test_apply_creates_exactly_the_whitelisted_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            code, out = run_scaffold(root, PROFILE_ID, "--apply")
            self.assertEqual(0, code, out)
            destination = root / "profiles" / PROFILE_ID
            copy, orientation = manifest_lists()
            self.assertEqual(sorted(copy), candidate_files(destination))
            for name in orientation:
                self.assertFalse((destination / name).exists(),
                                 "orientation file was copied: %s" % name)
            leftovers = [p.name for p in (root / "profiles").iterdir()
                         if p.name.startswith(".scaffold-")]
            self.assertEqual([], leftovers)
            self.assertIn("candidate created", out)
            self.assertIn("check_profile", out)
            self.assertNotIn("profile ready", out)

    def test_junk_in_the_template_is_never_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            template = root / "profiles" / "_template"
            (template / ".DS_Store").write_bytes(b"\x00junk")
            (template / "registries" / ".audit-dimensions.md.swp").write_bytes(
                b"swap")
            (template / "extra-unclassified.md").write_text(
                "not in the manifest", encoding="utf-8")
            code, out = run_scaffold(root, PROFILE_ID, "--apply")
            self.assertEqual(0, code, out)
            copy, _ = manifest_lists()
            self.assertEqual(sorted(copy),
                             candidate_files(root / "profiles" / PROFILE_ID))

    def test_unrewritten_files_are_byte_identical_to_the_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            code, _ = run_scaffold(root, PROFILE_ID, "--apply")
            self.assertEqual(0, code)
            destination = root / "profiles" / PROFILE_ID
            copy, _ = manifest_lists()
            rewritten = {relative for relative, _o, _n in
                         scaffold_profile.derived_rewrites(PROFILE_ID)}
            for relative in copy:
                if relative in rewritten:
                    continue
                self.assertEqual(
                    (TEMPLATE / relative).read_bytes(),
                    (destination / relative).read_bytes(), relative)

    def test_missing_whitelisted_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            (root / "profiles" / "_template" / "priority-rubric.md").unlink()
            code, out = run_scaffold(root, PROFILE_ID, "--apply")
            self.assertEqual(1, code)
            self.assertIn("manifest drift", out)
            self.assertFalse((root / "profiles" / PROFILE_ID).exists())

    def test_symlinked_whitelisted_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            target = root / "profiles" / "_template" / "priority-rubric.md"
            real = target.read_bytes()
            target.unlink()
            aside = root / "profiles" / "_template" / "aside.bin"
            aside.write_bytes(real)
            target.symlink_to("aside.bin")
            code, out = run_scaffold(root, PROFILE_ID, "--apply")
            self.assertEqual(1, code)
            self.assertIn("symlink", out)
            self.assertFalse((root / "profiles" / PROFILE_ID).exists())


class ExistingDestination(unittest.TestCase):
    def refuse_case(self, prepare, expected_phrase):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            destination = root / "profiles" / PROFILE_ID
            prepare(destination)
            before = tree_state(root)
            for extra in ((), ("--apply",)):
                code, out = run_scaffold(root, PROFILE_ID, *extra)
                self.assertEqual(1, code, out)
                self.assertIn(expected_phrase, out)
                self.assertIn("nothing was written", out)
            self.assertEqual(before, tree_state(root),
                             "a refusal must modify nothing")

    def test_existing_directory_with_content_refuses(self):
        def prepare(destination):
            destination.mkdir(parents=True)
            (destination / "profile.md").write_text("mine", encoding="utf-8")
        self.refuse_case(prepare, "as a directory")

    def test_existing_empty_directory_refuses(self):
        def prepare(destination):
            destination.mkdir(parents=True)
        self.refuse_case(prepare, "even an empty one is refused")

    def test_existing_regular_file_refuses(self):
        def prepare(destination):
            destination.write_text("a file, not a directory",
                                   encoding="utf-8")
        self.refuse_case(prepare, "as a file")

    def test_existing_symlink_refuses_even_when_dangling(self):
        def prepare(destination):
            destination.symlink_to("does-not-exist")
        self.refuse_case(prepare, "as a symlink")

    def test_destination_appearing_between_check_and_publish_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            destination = root / "profiles" / PROFILE_ID
            original = scaffold_profile.stage_candidate

            def stage_then_race(staging, plan):
                original(staging, plan)
                destination.mkdir()
            with mock.patch.object(
                    scaffold_profile, "stage_candidate", stage_then_race):
                code, out = run_scaffold(root, PROFILE_ID, "--apply")
            self.assertEqual(1, code, out)
            self.assertEqual([], list(destination.iterdir()),
                             "the raced destination must not be merged into")
            leftovers = [p.name for p in (root / "profiles").iterdir()
                         if p.name.startswith(".scaffold-")]
            self.assertEqual([], leftovers)


class SlugValidation(unittest.TestCase):
    def test_invalid_and_reserved_slugs_refuse(self):
        cases = ("Upper", "-leading-dash", "a/b", "a\\b", "a b", "",
                 "_template", "examples", "café")
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            before = tree_state(root)
            for slug in cases:
                with self.subTest(slug=slug):
                    code, out = run_scaffold(root, slug, "--apply")
                    self.assertEqual(1, code, out)
            self.assertEqual(before, tree_state(root))


class InterruptionSafety(unittest.TestCase):
    def assert_no_residue(self, root):
        self.assertFalse((root / "profiles" / PROFILE_ID).exists())
        leftovers = [p.name for p in (root / "profiles").iterdir()
                     if p.name.startswith(".scaffold-")]
        self.assertEqual([], leftovers, "staging directory leaked")

    def test_keyboard_interrupt_during_publish_leaves_no_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            with mock.patch.object(
                    scaffold_profile, "publish_candidate",
                    side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    run_scaffold(root, PROFILE_ID, "--apply")
            self.assert_no_residue(root)

    def test_failure_midway_through_staging_leaves_no_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            original = scaffold_profile.stage_candidate

            def stage_partially(staging, plan):
                partial = dict(plan)
                partial["copy"] = plan["copy"][:3]
                original(staging, partial)
                raise OSError("disk full after three files")
            with mock.patch.object(
                    scaffold_profile, "stage_candidate", stage_partially):
                code, out = run_scaffold(root, PROFILE_ID, "--apply")
            self.assertEqual(1, code, out)
            self.assertIn("no candidate was published", out)
            self.assert_no_residue(root)


class MechanicalRewrites(unittest.TestCase):
    def scaffolded(self, root):
        code, out = run_scaffold(root, PROFILE_ID, "--apply")
        self.assertEqual(0, code, out)
        return root / "profiles" / PROFILE_ID

    def test_identity_and_self_paths_landed(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = self.scaffolded(make_root(tmp))
            manifest = (candidate / "profile.md").read_text(encoding="utf-8")
            self.assertIn("- `profile_id`: `%s`" % PROFILE_ID, manifest)
            scans = (candidate / "registries" / "registered-scans.md"
                     ).read_text(encoding="utf-8")
            self.assertIn(
                "--config profiles/%s/scan-configs/residual-scan.yaml"
                % PROFILE_ID, scans)
            dimensions = (candidate / "registries" / "audit-dimensions.md"
                          ).read_text(encoding="utf-8")
            self.assertIn(
                "`profiles/%s/scope-and-architecture.md#Foundation Depth "
                "Requirements`" % PROFILE_ID, dimensions)
            self.assertIn(
                "`profiles/%s/registries/audit-dimensions.md#Residual "
                "Disposition`" % PROFILE_ID, dimensions)
            # The derived owner headings resolve inside the candidate itself.
            self.assertIn("## Foundation Depth Requirements",
                          (candidate / "scope-and-architecture.md"
                           ).read_text(encoding="utf-8"))
            self.assertIn("## Residual Disposition", dimensions)

    def test_semantic_sentinels_survive_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            candidate = self.scaffolded(root)
            copy, _ = manifest_lists()
            before = sentinel_counts(TEMPLATE, copy)
            after = sentinel_counts(candidate, copy)
            deltas = {name: before[name] - after[name]
                      for name in copy if before[name] != after[name]}
            # profile_id: -1.  audit-dimensions: the two predicate-owner
            # cells: -2.  registered-scans: three semantic cells stay, the
            # scan-id inside the derived command stays semantic: net 0.
            self.assertEqual(
                {"profile.md": 1, "registries/audit-dimensions.md": 2},
                deltas)

    def test_check_profile_fails_with_sentinel_findings_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            self.scaffolded(root)
            receipts = Path(tmp) / "receipts.jsonl"
            completed = subprocess.run(
                [sys.executable, str(CHECK_PROFILE),
                 "profiles/%s" % PROFILE_ID, "--root", str(root),
                 "--receipts", str(receipts)],
                cwd=str(root), text=True, capture_output=True, check=False)
            self.assertEqual(1, completed.returncode, completed.stdout)
            recorded = [json.loads(line) for line in
                        receipts.read_text(encoding="utf-8").splitlines()
                        if line.strip()]
            fail_checks = {r["check"] for r in recorded
                           if r["result"] == "fail"}
            self.assertEqual(
                {"unfilled-placeholder"}, fail_checks,
                "a fresh candidate must fail only on its open semantic "
                "answers; a path-resolution or structural finding means a "
                "mechanical rewrite is wrong: %s" % sorted(fail_checks))
            self.assertIn("profile_id=%s" % PROFILE_ID, completed.stdout)

    def test_kernel_and_runtime_state_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            kernel_before = tree_state(root / "kernel")
            self.scaffolded(root)
            self.assertEqual(kernel_before, tree_state(root / "kernel"))
            self.assertEqual(
                K00_03.read_bytes(),
                (root / "kernel" / "K00 Standards Control" /
                 "03 Standards Governance.md").read_bytes())
            self.assertFalse((root / ".cambium").exists())


class SemanticFillEndToEnd(unittest.TestCase):
    """Answering only the remaining semantic decisions must yield a pass.

    The fill reuses `test_template_fill.FILL` wherever the scaffolder left
    the anchor untouched, so a template wording change fails one place. The
    anchors the scaffolder already materialized are expected to be absent
    and are answered through their post-scaffold forms instead.
    """

    def test_semantic_fill_of_a_scaffold_passes_check_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            code, out = run_scaffold(root, PROFILE_ID, "--apply")
            self.assertEqual(0, code, out)
            candidate = root / "profiles" / PROFILE_ID

            skipped = []
            for relative, old, new in test_template_fill.FILL:
                path = candidate / relative
                text = path.read_text(encoding="utf-8")
                if old not in text:
                    skipped.append((relative, old))
                    continue
                path.write_text(
                    text.replace(
                        old, new.replace("fill-e2e", PROFILE_ID), 1),
                    encoding="utf-8")
            # Exactly the anchors the scaffolder itself already rewrote.
            self.assertEqual(
                sorted({relative for relative, _old in skipped}),
                ["profile.md", "registries/audit-dimensions.md",
                 "registries/registered-scans.md"], skipped)
            self.assertEqual(4, len(skipped), skipped)

            # Post-scaffold forms of the anchors skipped above: the two
            # judgment-item IDs and the scan row's remaining semantic cells.
            command = ("`python3 Tools/check_residual_content.py . "
                       "--scan-id TODO(profile) --config "
                       "profiles/%s/scan-configs/residual-scan.yaml "
                       "--time-limit 55`" % PROFILE_ID)
            post_fill = (
                ("registries/audit-dimensions.md",
                 "| TODO(profile) | `coverage_and_integration`",
                 "| `%s-residual-disposition` | `coverage_and_integration`"
                 % PROFILE_ID),
                ("registries/registered-scans.md",
                 "| TODO(profile) | `K12/09 item 6 — residual-content scan` "
                 "| TODO(profile) | %s | TODO(profile) | TODO(profile) |"
                 % command,
                 "| `{pid}-scratch-residuals` | `K12/09 item 6 — "
                 "residual-content scan` | Run from the vault root, passed "
                 "as `.`; the profile-owned configuration accepts "
                 "`Notes/Daily Log` as the only root where dated-scratch "
                 "structure belongs. | {command} | A Markdown file outside "
                 "`Notes/Daily Log` is a candidate when it declares "
                 "`type: daily-log`, carries a `Daily Log Entry` heading, "
                 "or carries at least two distinct dated-scratch sorting "
                 "headings. Candidate-only; adjudication belongs to "
                 "`{pid}-residual-disposition`. "
                 "| `{pid}-residual-disposition` |".format(
                     pid=PROFILE_ID,
                     command=command.replace(
                         "--scan-id TODO(profile)",
                         "--scan-id %s-scratch-residuals" % PROFILE_ID))),
            )
            for relative, old, new in post_fill:
                path = candidate / relative
                text = path.read_text(encoding="utf-8")
                self.assertIn(old, text,
                              "post-scaffold anchor drifted in %s" % relative)
                path.write_text(text.replace(old, new, 1), encoding="utf-8")
            (candidate / "scan-configs" / "residual-scan.yaml").write_text(
                test_template_fill.SCAN_CONFIG, encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(CHECK_PROFILE),
                 "profiles/%s" % PROFILE_ID, "--root", str(root)],
                cwd=str(root), text=True, capture_output=True, check=False)
            self.assertEqual(0, completed.returncode,
                             completed.stdout + completed.stderr)
            self.assertIn("sentinel_hits(fail)=0", completed.stdout)


if __name__ == "__main__":
    unittest.main()
