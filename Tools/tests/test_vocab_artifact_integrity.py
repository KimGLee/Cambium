"""The composed vocabulary artifact is a gate input, so it fails closed.

`check_vocab` decides whether a frontmatter value is legal by looking it up in
`Tools/vocab.yaml`. An artifact with no fields makes *every* value legal, so a
truncated or half-written file does not make the gate noisy -- it makes the
gate silently pass. Two halves are covered here:

- the producer (`compose_vocab.py`) publishes the artifact atomically and only
  after it satisfies the same predicate the consumer applies, so an
  interrupted run cannot leave a readable-but-empty artifact behind;
- the consumer (`check_vocab.py`) refuses an artifact that is not a
  composition instead of scanning against an empty vocabulary.

Rule owner: "kernel/K12 Quality Assurance/05 Automated and Manual Checks.md"
requires this check's input to be "composed from the kernel base vocabulary and
the selected profile's `Vocabulary Extensions`"; "kernel/K00 Standards
Control/03 Standards Governance.md" keeps the artifact absent in a distribution
that has selected no profile, and that legal state is asserted here too.

Only set/existence/equality/byte judgments are made; nothing restates a rule.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent

sys.path.insert(0, str(TOOLS))
import kblib  # noqa: E402
from Tools.tests.profile_fixture import install_loadable_profile

ACTIVE_STATE = "kernel/K00 Standards Control/03 Standards Governance.md"
VOCABULARY_BASE = "kernel/K08 Metadata and Status/vocabulary-base.yaml"
PROFILE_ID = "agent-atlas"


def build_composable_tree(destination):
    """Lay out the smallest tree `compose_vocab.py` will compose from.

    `compose_vocab` resolves the active selection against the repository root
    it derives from its own location, so the tool has to be copied in rather
    than pointed at this tree.
    """
    tools = destination / "Tools"
    tools.mkdir(parents=True)
    for name in (
            "compose_vocab.py", "kblib.py", "check_vocab.py",
            "check_freshness.py", "freshness_engine.py",
            "maintenance_candidates.py",
            "profile_admission.py", "check_profile.py",
            "profile_contract.py"):
        shutil.copy2(TOOLS / name, tools / name)

    install_loadable_profile(destination)

    (destination / VOCABULARY_BASE).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPOSITORY / VOCABULARY_BASE, destination / VOCABULARY_BASE)
    shutil.copytree(REPOSITORY / "profiles" / "examples" / PROFILE_ID,
                    destination / "profiles" / "examples" / PROFILE_ID)

    state = destination / ACTIVE_STATE
    state.parent.mkdir(parents=True, exist_ok=True)
    text = (REPOSITORY / ACTIVE_STATE).read_text(encoding="utf-8")
    for placeholder, value in (
            ("{{ standards_version }}", "1.0.0"),
            ("{{ standards_status }}", "approved"),
            ("{{ standards_effective_date }}", "2026-01-01"),
            ("{{ selected_profile_manifest }}",
             "profiles/examples/%s/profile.md" % PROFILE_ID)):
        text = text.replace(placeholder, value)
    state.write_text(text, encoding="utf-8")
    return destination


def compose(tree, *arguments):
    return subprocess.run(
        [sys.executable, str(tree / "Tools" / "compose_vocab.py"), *arguments],
        cwd=str(tree), capture_output=True, text=True, check=False)


class VocabularyArtifactPredicate(unittest.TestCase):
    """`fields` is what separates a vocabulary from a file."""

    def test_a_composed_artifact_parses(self):
        data = kblib.parse_vocabulary_artifact(
            "fields:\n  priority:\n    values:\n      - P0\n")
        self.assertEqual(["P0"], data["fields"]["priority"]["values"])

    def test_empty_bytes_are_refused(self):
        # The restricted-subset parser maps empty input to `{}`, so without
        # this predicate a truncated artifact is indistinguishable from a
        # vocabulary that happens to control nothing.
        self.assertEqual({}, kblib.parse_yaml_subset(""))
        for text in ("", "\n", "# only a comment\n"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    kblib.parse_vocabulary_artifact(text)

    def test_an_artifact_without_fields_is_refused(self):
        with self.assertRaises(ValueError):
            kblib.parse_vocabulary_artifact("schema_version: 1\n")

    def test_an_empty_field_set_is_refused(self):
        with self.assertRaises(ValueError):
            kblib.parse_vocabulary_artifact("fields: []\n")

    def test_unparseable_bytes_are_refused(self):
        with self.assertRaises(kblib.YamlSubsetError):
            kblib.parse_vocabulary_artifact("fields:\n  not a mapping line\n")


class ConsumerFailsClosed(unittest.TestCase):
    """`check_vocab` must not scan against a vocabulary it never loaded."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.tree = Path(self.temporary.name)
        corpus = self.tree / "corpus"
        corpus.mkdir()
        # `priority` carries a value no kernel base vocabulary allows, so a
        # loaded vocabulary must report exit 1 for this page.
        (corpus / "page.md").write_text(
            "---\npriority: P9-NOT-A-REAL-PRIORITY\n---\n\n# Page\n",
            encoding="utf-8")
        self.vocabulary = self.tree / "vocab.yaml"

    def run_check(self):
        return subprocess.run(
            [sys.executable, str(TOOLS / "check_vocab.py"), str(self.tree),
             "--scope", "corpus", "--vocab", str(self.vocabulary)],
            capture_output=True, text=True, check=False)

    def test_a_real_vocabulary_reports_the_illegal_value(self):
        self.vocabulary.write_text(
            "fields:\n  priority:\n    owner: K08/02\n    values:\n"
            "      - P0\n      - P1\n      - P2\n", encoding="utf-8")
        completed = self.run_check()
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("P9-NOT-A-REAL-PRIORITY", completed.stdout)

    def test_a_truncated_vocabulary_does_not_pass_the_same_page(self):
        """The defect: 0 bytes turned a hard fail into a silent exit 0."""
        self.vocabulary.write_text("", encoding="utf-8")
        completed = self.run_check()
        self.assertNotEqual(
            0, completed.returncode,
            "a zero-byte vocabulary made every controlled value legal and the "
            "gate reported a pass it never checked:\n" + completed.stdout)
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("not usable", completed.stdout)

    def test_an_unparseable_vocabulary_fails_without_a_traceback(self):
        self.vocabulary.write_text("fields:\n  not a mapping line\n",
                                   encoding="utf-8")
        completed = self.run_check()
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertNotIn("Traceback", completed.stderr)

    def test_a_refusal_still_emits_a_receipt(self):
        self.vocabulary.write_text("", encoding="utf-8")
        receipts = self.tree / "receipts.jsonl"
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "check_vocab.py"), str(self.tree),
             "--scope", "corpus", "--vocab", str(self.vocabulary),
             "--receipts", str(receipts)],
            capture_output=True, text=True, check=False)
        self.assertEqual(1, completed.returncode, completed.stdout)
        rows = [line for line in
                receipts.read_text(encoding="utf-8").splitlines() if line]
        self.assertTrue(rows, "an evidence-production failure must be visible "
                              "to a gate consumer, not only on stdout")
        self.assertIn("vocab-artifact-invalid", rows[-1])
        self.assertIn('"result": "fail"', rows[-1])


class ProducerPublishesAtomically(unittest.TestCase):
    """An interrupted compose must not leave a readable empty artifact."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.tree = build_composable_tree(Path(self.temporary.name))
        self.artifact = self.tree / "Tools" / "vocab.yaml"

    def test_compose_writes_a_usable_artifact(self):
        completed = compose(self.tree)
        self.assertEqual(0, completed.returncode,
                         completed.stdout + completed.stderr)
        data = kblib.parse_vocabulary_artifact(
            self.artifact.read_text(encoding="utf-8"))
        self.assertTrue(data["fields"])

    def test_recompose_is_byte_identical(self):
        self.assertEqual(0, compose(self.tree).returncode)
        first = self.artifact.read_bytes()
        self.assertEqual(0, compose(self.tree).returncode)
        self.assertEqual(first, self.artifact.read_bytes())

    def test_kernel_base_byte_change_makes_vocabulary_stale(self):
        self.assertEqual(0, compose(self.tree).returncode)
        base = self.tree / VOCABULARY_BASE
        base.write_text(
            base.read_text(encoding="utf-8") + "\n# revision B\n",
            encoding="utf-8")

        completed = compose(self.tree, "--check")

        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("MISMATCH", completed.stdout)

    def test_unrelated_unloadable_slot_blocks_vocabulary_publication(self):
        manifest = self.tree / "profiles" / "examples" / PROFILE_ID / \
            "profile.md"
        manifest_text = manifest.read_text(encoding="utf-8")
        bindings = kblib.profile_slot_bindings(manifest_text)
        kind, priority_path = kblib.resolve_profile_binding(
            bindings["Priority Rubric"], self.tree.resolve(),
            manifest.parent.resolve())
        self.assertEqual("path", kind)
        Path(priority_path).write_text("TODO(profile)\n", encoding="utf-8")
        completed = compose(self.tree)
        self.assertEqual(1, completed.returncode,
                         completed.stdout + completed.stderr)
        self.assertIn("profile-load", completed.stdout)
        self.assertFalse(self.artifact.exists())

    def test_consumer_rejects_artifact_from_previous_profile_revision(self):
        """A valid Profile B must not be checked with Profile A vocabulary."""
        self.assertEqual(0, compose(self.tree).returncode)
        corpus = self.tree / "corpus"
        corpus.mkdir()
        (corpus / "page.md").write_text(
            "---\ntype: interview-card\n---\n\n# Interview card\n",
            encoding="utf-8")
        extension = self.tree / "profiles/examples" / PROFILE_ID / \
            "vocabulary-extensions.yaml"
        extension.write_text(
            extension.read_text(encoding="utf-8").replace(
                "      - interview-card\n", ""),
            encoding="utf-8")

        completed = subprocess.run(
            [sys.executable, str(self.tree / "Tools/check_vocab.py"),
             str(self.tree), "--scope", "corpus"],
            cwd=str(self.tree), capture_output=True, text=True, check=False)

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("composed vocabulary is not current", completed.stdout)
        self.assertIn("does not match the selected Profile", completed.stdout)

    def test_freshness_rejects_canonical_defaults_from_previous_profile(self):
        self.assertEqual(0, compose(self.tree).returncode)
        corpus = self.tree / "corpus"
        corpus.mkdir()
        (corpus / "page.md").write_text(
            "---\ndomain: interview\nlast_verified: 2026-01-01\n---\n# Page\n",
            encoding="utf-8")
        extension = self.tree / "profiles/examples" / PROFILE_ID / \
            "vocabulary-extensions.yaml"
        extension.write_text(
            extension.read_text(encoding="utf-8").replace(
                "  interview: slow\n", "  interview: fast\n"),
            encoding="utf-8")

        completed = subprocess.run(
            [sys.executable, str(self.tree / "Tools/check_freshness.py"),
             str(self.tree), "--scope", "corpus", "--as-of", "2026-08-01",
             "--defaults", str(self.artifact)],
            cwd=str(self.tree), capture_output=True, text=True, check=False)

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("canonical Tools/vocab.yaml is not current",
                      completed.stdout)

    def test_freshness_consumes_current_canonical_defaults(self):
        self.assertEqual(0, compose(self.tree).returncode)
        corpus = self.tree / "corpus"
        corpus.mkdir()
        (corpus / "page.md").write_text(
            "---\ndomain: interview\nlast_verified: 2026-01-01\n---\n# Page\n",
            encoding="utf-8")

        completed = subprocess.run(
            [sys.executable, str(self.tree / "Tools/check_freshness.py"),
             str(self.tree), "--scope", "corpus", "--as-of", "2026-08-01",
             "--defaults", str(self.artifact)],
            cwd=str(self.tree), capture_output=True, text=True, check=False)

        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("fresh=1", completed.stdout)

    def test_check_mode_never_writes(self):
        self.assertEqual(0, compose(self.tree).returncode)
        before = (self.artifact.read_bytes(),
                  self.artifact.stat().st_mtime_ns)
        completed = compose(self.tree, "--check")
        self.assertEqual(0, completed.returncode,
                         completed.stdout + completed.stderr)
        self.assertEqual(
            before, (self.artifact.read_bytes(),
                     self.artifact.stat().st_mtime_ns),
            "--check is a read-only mode; it must not republish the artifact")

    def test_no_scratch_file_survives_a_successful_compose(self):
        self.assertEqual(0, compose(self.tree).returncode)
        leftovers = [entry.name for entry in (self.tree / "Tools").iterdir()
                     if entry.name.startswith(".cambium-write-")]
        self.assertEqual([], leftovers)

    def test_a_failed_publish_keeps_the_previous_artifact(self):
        """The defect this replaces: `open(path, "w")` truncates first.

        A bare truncating write leaves a zero-byte artifact behind whenever the
        process dies before the bytes are flushed, and a zero-byte artifact is
        the one state that makes the consuming gate pass unconditionally.
        """
        self.assertEqual(0, compose(self.tree).returncode)
        good = self.artifact.read_bytes()
        self.assertTrue(good)

        def die(*_arguments, **_keywords):
            raise KeyboardInterrupt("interrupted mid-publish")

        original = kblib.tempfile.mkstemp
        kblib.tempfile.mkstemp = die
        try:
            with self.assertRaises(KeyboardInterrupt):
                kblib.atomic_write_text(
                    str(self.artifact), "fields:\n  a:\n    values:\n      - x\n",
                    validator=kblib.parse_vocabulary_artifact)
        finally:
            kblib.tempfile.mkstemp = original
        self.assertEqual(
            good, self.artifact.read_bytes(),
            "the previous artifact must survive an interrupted publish")

    def test_a_rejected_document_is_never_published(self):
        self.assertEqual(0, compose(self.tree).returncode)
        good = self.artifact.read_bytes()
        with self.assertRaises(ValueError):
            kblib.atomic_write_text(str(self.artifact), "",
                                    validator=kblib.parse_vocabulary_artifact)
        self.assertEqual(
            good, self.artifact.read_bytes(),
            "the validator runs before any byte reaches the artifact path")


class UnselectedProfileStaysLegal(unittest.TestCase):
    """K00/03: a distribution with no selected profile carries no artifact."""

    def test_compose_refuses_without_selecting_one_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = build_composable_tree(Path(temporary))
            state = tree / ACTIVE_STATE
            state.write_text(
                state.read_text(encoding="utf-8").replace(
                    "`profiles/examples/%s/profile.md`" % PROFILE_ID,
                    "`{{ selected_profile_manifest }}`"),
                encoding="utf-8")
            completed = compose(tree)
            self.assertEqual(1, completed.returncode, completed.stdout)
            self.assertFalse(
                (tree / "Tools" / "vocab.yaml").exists(),
                "the generic distribution carries no composed vocabulary; "
                "refusing to select one must not create an empty artifact")

    def test_check_vocab_reports_the_unconfigured_tree_rather_than_passing(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary)
            (tree / "corpus").mkdir()
            (tree / "corpus" / "page.md").write_text(
                "---\npriority: P0\n---\n\n# Page\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(TOOLS / "check_vocab.py"), str(tree),
                 "--scope", "corpus", "--vocab", str(tree / "missing.yaml")],
                capture_output=True, text=True, check=False)
            self.assertEqual(1, completed.returncode, completed.stdout)
            self.assertIn("no composed vocabulary", completed.stdout)


if __name__ == "__main__":
    unittest.main()
