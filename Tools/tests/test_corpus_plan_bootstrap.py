"""When the Corpus Planning gate is owed, and why an empty corpus still cannot.

Two gates read the Corpus Planning choice at different moments, and conflating
them is what made the cold-start ordering hard to state. Admission (K00/13)
requires a configured plan before large-scale work; batch close requires one
when the task selected R13 or when the batch's manifest touches a bound
planning artifact. Nothing derives the requirement from the work merely being
multi-batch, and an unrelated batch acquires no gate because the repository
happens to hold a plan.

A corpus whose layer directories hold no canonical owner cannot supply a Global
Map, because the Map names owners that exist. That ordering gap is open in this
revision, and one wrong way to close it is pinned here so it is not tried
again: the three planning artifacts cannot ride the initial batch's manifest.
A Queue manifest equals the Coverage projection, and `check_batch_close`
requires every member to be a Markdown knowledge object -- the artifacts are
restricted YAML validated by a different gate with a different receipt
dimension, so putting them there would subject a control-plane artifact to
content review and give it a status vocabulary that means nothing for it.

What the manifest trigger does reach is the Markdown the plan names: Global Map
entry paths, Matrix canonical and evidence paths, Gap promoted and evidence
paths. Those are pages, and a batch that touches one owes the gate.

Also pinned: `check_profile` authorizes a `configured` slot whose artifacts do
not exist yet. The planning artifacts are corpus state, not Profile
dependencies, so profile-load must not resolve them; a change that made it do
so would close a door the eventual fix will need.

These are regression tests, not gates. They record no receipt and claim no Gate
ID, and they check machine behavior rather than whether any prose describes it
correctly.
"""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
TESTS = TOOLS / "tests"
EXAMPLE = REPOSITORY / "profiles" / "examples" / "minimal-notes"

if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import test_profile_onboarding_status as tpos  # noqa: E402
import corpus_planning_contract  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(
        "_%s_under_test" % name, TOOLS / ("%s.py" % name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_corpus_plan = _load("check_corpus_plan")

GLOBAL_MAP = "planning/global-map.yaml"
CAPABILITY_MATRIX = "planning/capability-matrix.yaml"
GAP_REGISTER = "planning/gap-register.yaml"

CONFIGURED_SLOT = """schema_version: 1

applicability:
  state: configured
  reason: null

artifact_bindings:
  global_map: %s
  capability_matrix: %s
  gap_register: %s

capability_scale:
  - rank: 0
    value: Missing
    predicate: "No canonical owner exists for the capability."
    target_eligible: false
  - rank: 1
    value: Covered
    predicate: "A canonical owner exists and states its responsibility."
    target_eligible: true

pass_authority:
  role_id: Corpus maintainer
  decision_scope_id: corpus-plan-semantic-acceptance
""" % (GLOBAL_MAP, CAPABILITY_MATRIX, GAP_REGISTER)


def contract(routes):
    return {"progress": {"contract": {"selected_route_ids": list(routes)}}}


class WhenTheCloseGateIsOwed(unittest.TestCase):
    """The predicate the bootstrap deferral is built on."""

    def setUp(self):
        # Shaped as the validator emits it, and keyed through the tool's own
        # role names so a rename cannot leave this fixture quietly stale.
        self.result = {
            "applicability": "configured",
            "slot": {"bindings": dict(zip(
                corpus_planning_contract.ARTIFACT_ROLES,
                (GLOBAL_MAP, CAPABILITY_MATRIX, GAP_REGISTER)))},
        }
        self.paths = list(check_corpus_plan.planning_artifact_paths(
            self.result))

    def test_the_bindings_are_the_paths_a_manifest_can_intersect(self):
        self.assertTrue(
            self.paths,
            "with no derivable artifact paths a batch manifest could never "
            "make this gate applicable, and the bootstrap deferral would have "
            "no mechanism behind it")

    def test_a_batch_touching_a_page_the_plan_names_owes_the_gate(self):
        """The reachable half: Map entries and Matrix paths are Markdown."""
        page = "Notes/Mapped Owner.md"
        result = dict(self.result)
        result["global_map"] = {"entries": [{"path": page}]}
        required, triggers = check_corpus_plan.close_requirement(
            contract([]), {"manifest": [page]}, result)
        self.assertTrue(
            required,
            "a batch that edits a page the plan names must reconcile the plan "
            "at close; this is what manifest applicability is for")
        self.assertIn("manifest", triggers)

    def test_the_three_artifacts_can_never_be_manifest_members(self):
        """The unreachable half, pinned so it is not designed around again."""
        bindings = self.result["slot"]["bindings"]
        for role, path in bindings.items():
            with self.subTest(role=role):
                self.assertFalse(
                    path.lower().endswith(".md"),
                    "the planning artifacts are restricted YAML; a Queue "
                    "manifest equals the Coverage projection and check_batch_"
                    "close requires every member to be a Markdown knowledge "
                    "object, so no batch can carry %s as a manifest entry and "
                    "no ordering may be built on the idea that it can" % role)

    def test_an_unrelated_batch_owes_nothing(self):
        required, triggers = check_corpus_plan.close_requirement(
            contract([]), {"manifest": ["Notes/Some Page.md"]}, self.result)
        self.assertFalse(
            required,
            "a batch acquires no planning gate merely because the repository "
            "holds a plan; the admission condition is not a corpus-wide mode")
        self.assertEqual([], triggers)

    def test_multi_batch_work_alone_does_not_owe_the_gate(self):
        """The prose says MUST configure; the machine asks a narrower question."""
        required, _ = check_corpus_plan.close_requirement(
            contract(["R07", "R02"]), {"manifest": ["Notes/A.md"]},
            self.result)
        self.assertFalse(
            required,
            "nothing derives this gate from the work being long or "
            "multi-batch. Reading the prose as if it did is what made the "
            "cold-start ordering look like a deadlock in the main path")

    def test_r13_selection_owes_the_gate(self):
        required, triggers = check_corpus_plan.close_requirement(
            contract(["R13"]), {"manifest": ["Notes/A.md"]}, self.result)
        self.assertTrue(required)
        self.assertIn("R13", triggers)


class ProfileLoadDoesNotResolveThePlanningArtifacts(unittest.TestCase):
    """A profile must be adoptable before the corpus it plans exists."""

    def test_configured_is_authorized_with_no_artifacts_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            tpos.copy_profile_load_fixture(root)
            # Same relative location: the example materializes its own
            # self-paths, and profile-load fails closed on a foreign one.
            profile = root / "profiles" / "examples" / "minimal-notes"
            shutil.copytree(EXAMPLE, profile)
            (profile / "README.md").unlink(missing_ok=True)
            (profile / "corpus-planning.yaml").write_text(
                CONFIGURED_SLOT, encoding="utf-8")

            self.assertFalse((root / GLOBAL_MAP).exists())
            result = subprocess.run(
                [sys.executable, str(TOOLS / "check_profile.py"),
                 "profiles/examples/minimal-notes", "--root", str(root)],
                cwd=str(root), text=True, capture_output=True, check=False)
            self.assertEqual(
                0, result.returncode,
                "the three planning artifacts are corpus state, not Profile "
                "dependencies; if profile-load starts resolving them, no "
                "corpus can adopt a profile before it has been built:\n"
                + result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
