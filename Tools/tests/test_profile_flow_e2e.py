"""End-to-end regression for the improved profile onboarding flow.

The branch closed the operator-side gaps between "a directory that contains
Cambium" and "a governed corpus doing routine work": a whitelist scaffolder
(`scaffold_profile.py` + `profiles/template-files.yaml`), a machine-readable
interview contract (`profiles/interview.yaml` v7), a read-only status
projector (`profile_onboarding_status.py`), the no-runtime R09 adoption
transaction (`apply_profile_adoption.py`), and the K02/03 candidate-
preparation branch that lets an empty corpus be founded before Corpus
Planning is configured.  Each piece has its own module; what none of them
pins is the seam BETWEEN them — that the whole flow composes, in order, with
no step inventing state another step owns.  This module locks that seam:

A. Flow behavior over scratch roots (scaffold -> interview fill ->
   check_profile -> R09 initial adoption -> bounded founding -> candidate
   preparation -> R09 revision -> init_state -> apply_task_plan ->
   compile_queue), asserting at every stage which writer owns which bytes
   and that founding/adoption create governance state but no task runtime,
   Coverage, or Queue.
B. Lifecycle text pins across the English and Chinese READMEs, the profiles
   docs, and the kernel — the anti-drift net for the flow's load-bearing
   sentences (no `cp -R` teaching, no "first batch" language, candidate
   preparation taught in all three owners, the witness/owner merge rule,
   scaffold-first with manual copy only as fallback).

Regression tests, not gates: no receipt, no Gate ID, no answer-quality call.
Nothing here is skipped silently — a fixture step that cannot run fails the
whole class loudly through its setUpClass assertion.
"""

import contextlib
import copy
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
REPOSITORY = TOOLS.parent
INTERVIEW = REPOSITORY / "profiles" / "interview.yaml"
CHECK_PROFILE = TOOLS / "check_profile.py"
TEMPLATE = REPOSITORY / "profiles" / "_template"

for path in (str(TESTS), str(TOOLS), str(REPOSITORY)):
    if path not in sys.path:
        sys.path.insert(0, path)

import check_corpus_plan  # noqa: E402
import check_queue  # noqa: E402
import kblib  # noqa: E402
import scaffold_profile  # noqa: E402
import test_apply_profile_adoption as tap  # noqa: E402 (adoption fixtures)
import test_apply_task_plan as ttp  # noqa: E402 (task-plan fixtures)
import test_check_corpus_plan as tccp  # noqa: E402 (configured-slot fixture)
import test_profile_onboarding_status as tpos  # noqa: E402 (status fixtures)
import test_template_fill  # noqa: E402 (reused semantic fill + scan config)
from profile_fixture import (  # noqa: E402
    FIXTURE_UPSTREAM_REVISION,
    install_loadable_profile,
)

PROFILE_ID = tap.PROFILE_ID  # "cand": lets tap's plan helpers be reused
MANIFEST = tap.MANIFEST
RUNTIME_STATE_FILES = frozenset((
    "coverage_ledger.yaml", "required_queue.yaml", "progress_ledger.yaml",
))

_MODULE_TMP = None
_FOUNDING_BASE = None  # kernel + Tools + template + one scaffolded, filled,
#                        NOT-yet-adopted candidate (pre-adoption state)


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def run_scaffold(root, profile_id, *extra):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = scaffold_profile.main(
            [str(root), "--profile-id=%s" % profile_id, *extra])
    return code, buffer.getvalue()


def manifest_lists():
    data = kblib.parse_yaml_subset(
        (REPOSITORY / "profiles" / "template-files.yaml").read_text(
            encoding="utf-8"))
    return data["copy"], data["orientation_not_copied"]


def candidate_files(destination):
    return sorted(
        path.relative_to(destination).as_posix()
        for path in Path(destination).rglob("*") if path.is_file())


def fill_scaffolded_candidate(root, profile_id):
    """Answer only the remaining semantic decisions of a scaffolded candidate.

    Mirrors `test_scaffold_profile.SemanticFillEndToEnd`: the shared
    `test_template_fill.FILL` covers every anchor the scaffolder left
    untouched, and the anchors the scaffolder already materialized (identity,
    the `--config` path, the two predicate-owner cells) are answered through
    their post-scaffold forms.  A template wording change fails here loudly
    instead of producing a candidate nobody could have filled.
    """
    candidate = Path(root) / "profiles" / profile_id
    skipped = []
    for relative, old, new in test_template_fill.FILL:
        path = candidate / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            skipped.append((relative, old))
            continue
        path.write_text(
            text.replace(old, new.replace("fill-e2e", profile_id), 1),
            encoding="utf-8")
    assert sorted({relative for relative, _old in skipped}) == [
        "profile.md", "registries/audit-dimensions.md",
        "registries/registered-scans.md"] and len(skipped) == 4, (
        "the set of anchors the scaffolder materializes drifted; the "
        "interview fill and the scaffolder no longer agree on who owns "
        "which cells: %r" % skipped)

    config_reference = (
        "`profiles/%s/scan-configs/residual-scan.yaml`" % profile_id)
    post_fill = (
        ("registries/audit-dimensions.md",
         "| TODO(profile) | `coverage_and_integration`",
         "| `%s-residual-disposition` | `coverage_and_integration`"
         % profile_id),
        ("registries/registered-scans.md",
         "| TODO(profile) | `K12/09 item 6 — residual-content scan` "
         "| TODO(profile) | `residual-content-scan-v1` | %s "
         "| TODO(profile) | TODO(profile) |" % config_reference,
         "| `{pid}-scratch-residuals` | `K12/09 item 6 — "
         "residual-content scan` | Run from the vault root; the "
         "profile-owned configuration accepts "
         "`Notes/Daily Log` as the only root where dated-scratch "
         "structure belongs. | `residual-content-scan-v1` | "
         "{config_reference} | A Markdown file outside "
         "`Notes/Daily Log` is a candidate when it declares "
         "`type: daily-log`, carries a `Daily Log Entry` heading, "
         "or carries at least two distinct dated-scratch sorting "
         "headings. Candidate-only; adjudication belongs to "
         "`{pid}-residual-disposition`. "
         "| `{pid}-residual-disposition` |".format(
             pid=profile_id,
             config_reference=config_reference)),
    )
    for relative, old, new in post_fill:
        path = candidate / relative
        text = path.read_text(encoding="utf-8")
        assert old in text, (
            "post-scaffold anchor drifted in %s; the interview can no "
            "longer name the cells a scaffolded candidate leaves open"
            % relative)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    (candidate / "scan-configs" / "residual-scan.yaml").write_text(
        test_template_fill.SCAN_CONFIG.replace("fill-e2e", profile_id),
        encoding="utf-8")
    return candidate


def run_check_profile(root, profile_id):
    return subprocess.run(
        [sys.executable, str(CHECK_PROFILE), "profiles/%s" % profile_id,
         "--root", str(root)],
        cwd=str(root), text=True, capture_output=True, check=False)


def runtime_offenders(root):
    """Every task-runtime directory or canonical task-state file anywhere."""
    offenders = []
    for path in sorted(Path(root).rglob("*")):
        if (path.name == "state" and path.is_dir() and
                path.parent.name == ".cambium"):
            offenders.append(path.relative_to(root).as_posix())
        elif path.is_file() and path.name in RUNTIME_STATE_FILES:
            offenders.append(path.relative_to(root).as_posix())
    return offenders


def founding_pages(root):
    """One canonical owner for the filled Profile Scope's single layer plus
    the residual witness carrying `SCAN_CONFIG`'s declared structure."""
    owner = Path(root) / "Notes" / "Home Lab Services.md"
    owner.parent.mkdir(parents=True, exist_ok=True)
    owner.write_text(
        "# Home Lab Services\n\nCanonical owner page for the `Notes` layer: "
        "one entry per service the maintainer must restore.\n",
        encoding="utf-8")
    witness = Path(root) / "Notes" / "Daily Log" / "2026-08-13.md"
    witness.parent.mkdir(parents=True, exist_ok=True)
    witness.write_text(
        "---\ntype: daily-log\n---\n\n# 2026-08-13\n\n"
        "## Daily Log Entry\n\nfounding seed\n\n"
        "## Scratch\n\n-\n\n## To Sort\n\n-\n\n## Loose Ends\n\n-\n",
        encoding="utf-8")
    return owner, witness


def production_scan(root, profile_id):
    """The registered production scan, exactly as the registry row runs it."""
    return subprocess.run(
        [sys.executable, "Tools/check_residual_content.py", ".",
         "--scan-id", "%s-scratch-residuals" % profile_id,
         "--config", "profiles/%s/scan-configs/residual-scan.yaml"
         % profile_id, "--time-limit", "55"],
        cwd=str(root), text=True, capture_output=True, check=False)


def filled_template(template_relative, fills):
    """Instantiate one `Tools/schemas/` planning template as a document.

    Loads the real shipped template, replaces its example records with the
    given ones, and refuses a template whose top-level shape drifted — so the
    documents this module validates are the documents an adopter is told to
    copy, not a parallel schema.
    """
    template = kblib.parse_yaml_subset(
        (TOOLS / "schemas" / template_relative).read_text(encoding="utf-8"))
    assert sorted(template) == sorted(
        ["schema_version"] + sorted(fills)), (
        "planning template %s grew or lost a top-level field; the flow "
        "test would validate a shape adopters are no longer given"
        % template_relative)
    document = {"schema_version": template["schema_version"]}
    document.update(fills)
    return document


def write_planning_artifacts(root, owner_relative, witness_relative,
                             owner_path="Notes/Home Lab Services.md"):
    planning = Path(root) / "planning"
    planning.mkdir(exist_ok=True)
    global_map = filled_template("global_map.template.yaml", {
        "entries": [
            {"entry_id": "E-OWNER", "layer_id": "L-MAIN",
             "canonical_markdown_path": owner_path,
             "single_responsibility":
                 "Own the canonical service notes of the lab."},
            {"entry_id": "E-WITNESS", "layer_id": "L-MAIN",
             "canonical_markdown_path": witness_relative,
             "single_responsibility":
                 "Own the dated-scratch witness structure."},
        ],
        "typed_dependencies": [
            {"edge_id": "D-1", "upstream_entry_id": "E-OWNER",
             "downstream_entry_id": "E-WITNESS",
             "relation_type": "prerequisite-for"},
        ],
    })
    matrix = filled_template("capability_matrix.template.yaml", {
        "capabilities": [{
            "capability_id": "C-1",
            "capability": "Restore any lab service from its canonical note.",
            "priority": "P0",
            "map_entry_ids": ["E-OWNER", "E-WITNESS"],
            "canonical_markdown_paths": [owner_relative, witness_relative],
            "current_level": "Core",
            "target_level": "Defensible",
            "evidence_paths": [owner_relative],
            "gap_ids": ["G-1"],
        }],
    })
    gaps = filled_template("gap_register.template.yaml", {
        "gaps": [{
            "gap_id": "G-1",
            "gap_statement": "Defensible restore evidence is still missing.",
            "capability_ids": ["C-1"],
            "candidate_owner_entry_id": "E-OWNER",
            "status": "confirmed",
            "close_condition":
                "The owner page records a verified restore drill.",
            "evidence_paths": [],
            "promoted_coverage_path": None,
            "rationale": "Founding created the owner; depth work remains.",
        }],
    })
    for name, document in (("global-map.yaml", global_map),
                           ("capability-matrix.yaml", matrix),
                           ("gap-register.yaml", gaps)):
        (planning / name).write_text(
            kblib.canonical_yaml(document), encoding="utf-8")


def interview_block(text, start_marker, end_marker):
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def readme_adoption_section(path, heading):
    text = path.read_text(encoding="utf-8")
    start = text.index("\n%s\n" % heading)
    end = text.index("\n## ", start + 1)
    return text[start:end]


def collapse_ws(text):
    return " ".join(text.split())


def setUpModule():
    global _MODULE_TMP, _FOUNDING_BASE
    _MODULE_TMP = tempfile.TemporaryDirectory()
    _FOUNDING_BASE = Path(_MODULE_TMP.name) / "founding-base"
    # tap._build_base supplies the adoption environment (full kernel, all
    # Tools scripts, schemas, K00/03 size-register headroom) and a candidate
    # copied from the template; the flow under test replaces that candidate
    # with a scaffolder-created one so the whole path stays cp-free.
    tap._build_base(_FOUNDING_BASE)
    # Keep tap's specialized adoption fixture, but complete its profile-load
    # producer inputs from the producer-owned registry.  A hand-maintained
    # fixture subset used to omit newly registered metadata contract assets,
    # causing exact-spelling admission to fail before this E2E reached the
    # semantic interview it is intended to exercise.
    tpos.copy_profile_load_fixture(_FOUNDING_BASE)
    shutil.rmtree(_FOUNDING_BASE / "profiles" / PROFILE_ID)
    shutil.copyfile(REPOSITORY / "profiles" / "template-files.yaml",
                    _FOUNDING_BASE / "profiles" / "template-files.yaml")
    shutil.copytree(TEMPLATE, _FOUNDING_BASE / "profiles" / "_template")
    code, out = run_scaffold(_FOUNDING_BASE, PROFILE_ID, "--apply")
    assert code == 0, out
    fill_scaffolded_candidate(_FOUNDING_BASE, PROFILE_ID)
    completed = run_check_profile(_FOUNDING_BASE, PROFILE_ID)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def tearDownModule():
    _MODULE_TMP.cleanup()


# ===========================================================================
# A. Flow behavior
# ===========================================================================

class ScaffoldOnboardingTests(unittest.TestCase):
    """Items 1-3: candidate creation is scaffolded, junk-safe, and refusing."""

    def scratch_root(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return tpos.make_root(tmp.name)

    def test_no_cp_onboarding_scaffold_fill_check_passes(self):
        root = self.scratch_root()
        code, out = run_scaffold(root, PROFILE_ID, "--apply")
        self.assertEqual(0, code, out)
        candidate = root / "profiles" / PROFILE_ID
        copy_list, orientation = manifest_lists()
        self.assertEqual(
            sorted(copy_list), candidate_files(candidate),
            "the candidate must hold exactly the whitelist — a raw "
            "directory copy would have brought orientation files and "
            "template junk along, which is the drift the scaffolder ended")
        for name in orientation:
            self.assertFalse(
                (candidate / name).exists(),
                "orientation file %s reached the candidate; the operator "
                "path regressed to copying the template wholesale" % name)
        fill_scaffolded_candidate(root, PROFILE_ID)
        completed = run_check_profile(root, PROFILE_ID)
        self.assertEqual(
            0, completed.returncode,
            "answering only the open interview decisions must yield a "
            "passing profile; a failure means the scaffolder's derived "
            "cells and the interview fill no longer compose:\n"
            + completed.stdout + completed.stderr)
        self.assertIn("sentinel_hits(fail)=0", completed.stdout)

    def test_junk_planted_in_template_never_reaches_the_candidate(self):
        root = self.scratch_root()
        (root / "profiles" / "_template" / ".DS_Store").write_bytes(b"\x00j")
        code, out = run_scaffold(root, PROFILE_ID, "--apply")
        self.assertEqual(0, code, out)
        copy_list, _ = manifest_lists()
        self.assertEqual(
            sorted(copy_list),
            candidate_files(root / "profiles" / PROFILE_ID),
            "junk planted in _template reached a scaffolded candidate; the "
            "whitelist is no longer authoritative and the cp-era failure "
            "mode is back")

    def test_scaffold_onto_an_existing_directory_refuses_unchanged(self):
        root = self.scratch_root()
        destination = root / "profiles" / PROFILE_ID
        destination.mkdir(parents=True)
        (destination / "profile.md").write_text("mine", encoding="utf-8")
        before = tpos.tree_state(root)
        for extra in ((), ("--apply",)):
            code, out = run_scaffold(root, PROFILE_ID, *extra)
            self.assertEqual(1, code, out)
            self.assertIn("nothing was written", out)
        self.assertEqual(
            before, tpos.tree_state(root),
            "a refused scaffold modified the tree; refusal must be a "
            "no-op or an operator retry can destroy a half-filled "
            "candidate")


class InterviewContractTests(unittest.TestCase):
    """Items 4-6: the machine fields of profiles/interview.yaml.

    These are the fields conducting agents and the status tool consume; a
    broken reference silently disables 'a changed Q0/Q4 answer forces
    recomputation', which no runtime check can catch later.
    """

    @classmethod
    def setUpClass(cls):
        cls.text = INTERVIEW.read_text(encoding="utf-8")
        cls.data = kblib.parse_yaml_subset(cls.text)
        cls.entries = list(cls.data["setup"]) + list(cls.data["core_pack"])
        cls.by_id = {entry["id"]: entry for entry in cls.entries}
        cls.c1_block = interview_block(cls.text, "- id: C1", "- id: C2")

    def test_c1_reconfirms_on_q0_q4_and_q10(self):
        c1 = self.by_id["C1"]
        self.assertIn(
            "Q4", c1["reconfirm_if"],
            "C1.reconfirm_if lost Q4: a changed layer answer would no "
            "longer void the derived scan roots, so a stale scan config "
            "could survive an architecture change unchallenged")
        self.assertIn("Q0", c1["reconfirm_if"])
        self.assertEqual(
            ["existing-corpus", "empty-corpus"], c1["branches"],
            "C1 must distinguish observing real strings from declaring "
            "designed ones; collapsing the branches is what left an empty "
            "corpus with no honest answer")

    def test_q0_derives_declare_their_owners(self):
        q0_block = interview_block(self.text, "- id: Q0", "- id: Q1")
        derives = re.findall(
            r'\{what:\s*"([^"]+)",\s*owner:\s*([a-z-]+)\}', q0_block)
        self.assertTrue(derives, "Q0 declares no derives; the contract no "
                                 "longer says who materializes identity")
        owners = {what: owner for what, owner in derives}

        def owner_of(fragment):
            matches = [owner for what, owner in owners.items()
                       if fragment in what]
            self.assertEqual(1, len(matches),
                             "Q0 derive %r missing or ambiguous" % fragment)
            return matches[0]

        self.assertEqual(
            "scaffolder", owner_of("profile_id"),
            "the manifest identity cell must stay scaffolder-owned; a "
            "conducting agent that re-asks it can diverge from the "
            "directory name the scaffolder already fixed")
        self.assertEqual(
            "scaffolder", owner_of("self_path_rewrites"),
            "the self-path cells must stay scaffolder-owned or a manual "
            "interview would re-derive paths the tool already wrote")
        self.assertEqual(
            "conducting-agent", owner_of("judgment item IDs"),
            "the judgment-item IDs are interview-projected; handing them "
            "to the scaffolder would make a pure-mechanical tool invent "
            "semantic identifiers")

    def test_every_dependency_reference_names_an_existing_item(self):
        ids = set(self.by_id)
        for entry in self.entries:
            for field in ("depends_on", "reconfirm_if"):
                for reference in entry.get(field) or []:
                    self.assertIn(
                        reference, ids,
                        "%s.%s references %r, which no interview item "
                        "declares; the reconfirmation contract silently "
                        "stops being enforceable exactly where it points "
                        "at nothing" % (entry["id"], field, reference))

    def test_c1_existing_corpus_branch_mandates_observed_strings(self):
        self.assertIn(
            "Existing corpus:", self.c1_block,
            "C1 lost its existing-corpus branch marker; the conducting "
            "agent can no longer name which situation applies")
        self.assertIn(
            "real strings only", self.c1_block,
            "the existing-corpus branch must mandate observed strings; "
            "without this sentence an agent may fabricate matchers that "
            "no page carries and the scan becomes fiction")

    def test_c1_empty_corpus_branch_pins_the_founding_witness(self):
        self.assertIn(
            "Empty corpus:", self.c1_block,
            "C1 lost its empty-corpus branch marker")
        self.assertIn(
            "designed rather than observed", self.c1_block,
            "the empty-corpus branch must record that the class is "
            "designed, not observed; dropping this hides the honesty "
            "distinction the two branches exist for")
        self.assertIn(
            "bounded founding MUST materialize the declared class",
            self.c1_block,
            "the witness obligation is stated nowhere else in the flow; "
            "losing it leaves the production scan with no legal way to "
            "ever pass on a founded corpus")
        self.assertIn(
            "no `.cambium/`, no Coverage, no Queue, no batch",
            self.c1_block,
            "founding must stay bounded authoring; without this sentence "
            "the witness obligation reads as a first batch and drags "
            "runtime state into pre-task founding")
        self.assertNotIn(
            "first batch", self.c1_block,
            "'first batch' language returned to C1; founding is not a "
            "batch and there is no Queue to put one in")


class ResidualScanHonestyTests(unittest.TestCase):
    """Item 5 (behavior): observed matchers pass the production scan."""

    def test_matchers_matching_a_real_page_pass_the_production_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            config = vault / "residual-scan.yaml"
            config.write_text(test_template_fill.SCAN_CONFIG,
                              encoding="utf-8")
            ordinary = vault / "Notes" / "Postgres.md"
            ordinary.parent.mkdir(parents=True)
            ordinary.write_text(
                "---\ntype: note\n---\n\n# Postgres\n\nbody\n",
                encoding="utf-8")
            page = vault / "Notes" / "Daily Log" / "2026-01-01.md"
            page.parent.mkdir(parents=True)
            page.write_text(
                "---\ntype: daily-log\n---\n\n# 2026-01-01\n\n"
                "## Daily Log Entry\n\nseed\n\n## Scratch\n\n-\n\n"
                "## To Sort\n\n-\n\n## Loose Ends\n\n-\n",
                encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOLS / "check_residual_content.py"),
                 str(vault), "--scan-id", "flow-e2e-observed",
                 "--config", str(config), "--time-limit", "55"],
                text=True, capture_output=True, check=False)
            self.assertEqual(
                0, result.returncode,
                "a scan config derived from strings a real page carries "
                "must pass the production scan on the corpus holding that "
                "page; if it does not, the existing-corpus C1 branch "
                "teaches a fill with no legal ending:\n"
                + result.stdout + result.stderr)
            self.assertIn("candidates=0", result.stdout)


class FoundingFlowTests(unittest.TestCase):
    """Items 7-11a: adoption, bounded founding, candidate preparation, and
    the second R09 revision — the whole empty-corpus lifecycle in order.

    The sequence runs once in setUpClass (any failed step fails the class
    loudly); each test asserts one recorded stage.
    """

    OWNER_RELATIVE = "Notes/Home Lab Services.md"
    WITNESS_RELATIVE = "Notes/Daily Log/2026-08-13.md"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "repo"
        shutil.copytree(_FOUNDING_BASE, cls.root)
        root = cls.root

        # ---- initial adoption: empty corpus, Corpus Planning inactive ----
        tap.write_plan(root, tap.initial_plan(root))
        code, out = tap.run_tool(root, "--apply")
        assert code == 0, out
        cls.offenders_after_initial = runtime_offenders(root)
        code, cls.status_before_founding, _ = tpos.run_status_json(root)
        assert code == 0

        # ---- bounded founding: owner + witness, plain authoring ----------
        founding_pages(root)
        cls.scan_after_founding = production_scan(root, PROFILE_ID)
        code, cls.status_after_founding, _ = tpos.run_status_json(root)
        assert code == 0
        cls.offenders_after_founding = runtime_offenders(root)

        # ---- planning artifacts exist, slot still not-applicable ---------
        write_planning_artifacts(
            root, cls.OWNER_RELATIVE, cls.WITNESS_RELATIVE)
        cls.active_manifest = tap.governance_state(
            root)["selected_profile_manifest"]
        cls.na_unselected = check_corpus_plan.validate_corpus_plan(
            str(root), None)
        cls.na_result = check_corpus_plan.validate_corpus_plan(
            str(root), cls.active_manifest)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cls.na_cli_code = check_corpus_plan.main(
                [str(root), "--profile", cls.active_manifest])
        cls.na_cli_out = buffer.getvalue()

        # ---- candidate preparation: configure the slot in place ----------
        (root / "profiles" / PROFILE_ID / "corpus-planning.yaml").write_text(
            tccp.CONFIGURED_SLOT, encoding="utf-8")

        # item 8: a Global Map naming a nonexistent owner fails
        write_planning_artifacts(
            root, cls.OWNER_RELATIVE, cls.WITNESS_RELATIVE,
            owner_path="Notes/Not Yet Founded.md")
        cls.bad_owner_result = check_corpus_plan.validate_corpus_plan(
            str(root), cls.active_manifest)
        write_planning_artifacts(
            root, cls.OWNER_RELATIVE, cls.WITNESS_RELATIVE)
        cls.candidate_result = check_corpus_plan.validate_corpus_plan(
            str(root), cls.active_manifest)

        # ---- the revision closes through apply_profile_adoption ----------
        plan = tap.revision_plan(
            root, change_summary="Profile revision inside %s: Corpus "
            "Planning configured for the large-scale build" % MANIFEST)
        relative = tap.write_plan(root, plan, "adoption-plans/PA-002.yaml")
        cls.revision_code, cls.revision_out = tap.run_tool(
            root, "--apply", plan=relative)
        cls.governance_after_revision = (
            tap.governance_state(root)
            if cls.revision_code == 0 else None)
        cls.post_close_result = check_corpus_plan.validate_corpus_plan(
            str(root), cls.active_manifest)
        cls.offenders_after_revision = runtime_offenders(root)
        code, cls.status_after_revision, _ = tpos.run_status_json(root)
        assert code == 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # ---- item 7 ----------------------------------------------------------

    def test_initial_adoption_creates_no_runtime_and_no_coverage(self):
        self.assertEqual(
            [], self.offenders_after_initial,
            "R09 initial adoption wrote task-runtime state; governance state "
            "and history may precede a Task Plan, but Coverage and Queue may "
            "not")
        self.assertEqual("found-empty-corpus",
                         self.status_before_founding["next_action"])
        self.assertEqual("adopted",
                         self.status_before_founding["standards_state"])

    def test_production_scan_recognises_the_founding_witness(self):
        result = self.scan_after_founding
        self.assertEqual(
            0, result.returncode,
            "after founding, the registered production scan must pass: "
            "zero candidates outside the accepted roots AND at least one "
            "recognised page inside them; a failure means the declared "
            "class never reached the repository and founding is fiction:\n"
            + result.stdout + result.stderr)
        self.assertIn("candidates=0", result.stdout)

    def test_founding_leaves_no_runtime_and_completes_onboarding(self):
        self.assertEqual(
            [], self.offenders_after_founding,
            "bounded founding created runtime state; founding is ordinary "
            "authoring and must stay invisible to the task runtime")
        view = self.status_after_founding
        self.assertEqual("existing", view["corpus_state"])
        self.assertEqual("not-applicable", view["corpus_planning_state"])
        self.assertEqual(
            "onboarding-complete", view["next_action"],
            "the decision table for adopted + existing corpus + "
            "not-applicable planning must land on onboarding-complete; "
            "anything else sends the operator back into a flow that has "
            "already finished")

    # ---- item 9 ----------------------------------------------------------

    def test_not_applicable_selection_accepts_no_planning_artifacts(self):
        # Without an explicit --profile and with no runtime, selection
        # cannot be resolved at all: the tool refuses instead of guessing.
        messages = [error["details"] for error in
                    self.na_unselected["errors"]]
        self.assertTrue(
            any("--profile was omitted and selected Profile could not be "
                "read" in message for message in messages),
            "with no runtime and no --profile the validator must refuse "
            "to pick a Profile by itself: %s" % messages)
        # Against the active selection whose slot is not-applicable, the
        # artifacts on disk are never read: the na result carries no
        # entries, no capabilities, and a not-applicable acceptance status.
        result = self.na_result
        self.assertEqual([], result["errors"])
        self.assertEqual("not-applicable", result["applicability"])
        self.assertEqual(
            [], result["global_map"]["entries"],
            "a not-applicable slot accepted Global Map entries; planning "
            "artifacts would become authoritative without the R09 "
            "revision that is supposed to admit them")
        self.assertEqual([], result["matrix"]["capabilities"])
        self.assertEqual(
            "not-applicable",
            check_corpus_plan.semantic_acceptance_status(result)["status"])
        self.assertEqual(0, self.na_cli_code, self.na_cli_out)
        self.assertIn(
            "[PASS] Corpus Planning structure: not applicable:",
            self.na_cli_out,
            "the CLI must state the na outcome explicitly so an operator "
            "cannot read the exit code as 'the plan was validated'")

    # ---- item 8 ----------------------------------------------------------

    def test_global_map_naming_a_nonexistent_owner_fails(self):
        messages = [error["details"] for error in
                    self.bad_owner_result["errors"]]
        self.assertTrue(
            any("path does not exist: Notes/Not Yet Founded.md" in message
                for message in messages),
            "a Global Map entry naming a page founding never created must "
            "fail; a plan over invented owners is exactly what the "
            "founding-first sequence exists to prevent: %s" % messages)

    def test_planning_passes_structurally_with_the_real_founding_owners(
            self):
        result = self.candidate_result
        self.assertEqual(
            [], result["errors"],
            "the three artifacts built from the shipped Tools/schemas/ "
            "templates over the real founding pages must validate; the "
            "candidate-preparation path otherwise has no passing state")
        self.assertEqual("configured", result["applicability"])
        self.assertEqual(2, len(result["global_map"]["entries"]))
        self.assertEqual(1, len(result["matrix"]["capabilities"]))

    # ---- item 10 ---------------------------------------------------------

    def test_revision_closes_and_the_active_selection_then_passes(self):
        self.assertEqual(0, self.revision_code, self.revision_out)
        state = self.governance_after_revision
        self.assertEqual(tap.UPSTREAM_REVISION, state["standards_version"])
        self.assertEqual(MANIFEST, state["selected_profile_manifest"])
        result = self.post_close_result
        self.assertEqual([], result["errors"])
        self.assertEqual(
            "configured", result["applicability"],
            "after the profile-revision closes, the active selection must "
            "expose the configured slot; if it does not, candidate "
            "preparation never became authoritative and the K02/03 "
            "lifecycle is broken")
        self.assertEqual(
            "prepare-task-plan", self.status_after_revision["next_action"],
            "adopted + existing corpus + configured planning and no "
            "runtime must hand off to task planning; the flow's next "
            "writer is init_state/apply_task_plan, not another revision")

    # ---- item 11 (adoption half) -----------------------------------------

    def test_no_coverage_exists_after_either_adoption_branch(self):
        self.assertEqual(
            [], self.offenders_after_revision,
            "an adoption branch (initial or profile-revision) produced "
            "task-runtime state or a Coverage/Queue file; Coverage rows may "
            "appear only through init_state + apply_task_plan with a "
            "user-confirmed Task Plan")


class RuntimeCreationTests(unittest.TestCase):
    """Items 11b-12: Coverage rows and the Queue each have one writer.

    Reuses test_apply_task_plan's fixtures: a loadable profile, the route
    registries, init_state, a minimal user-confirmed Task Plan, and the real
    Queue compiler.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "repo"
        root = cls.root
        # The shared Profile fixture installs the complete schema-valid
        # Card/Read Set registry.  Rewriting a private R01/R02 subset here
        # previously created duplicate route identities and stale Card bytes.
        install_loadable_profile(root, profile_id="sample")
        result = subprocess.run(
            [sys.executable, str(TOOLS / "init_state.py"), str(root),
             "--task-id", ttp.TASK_ID,
             "--objective", "Exercise task planning",
             "--scope-version", "s1", "--completion-semantics", "build",
             "--standards-version", FIXTURE_UPSTREAM_REVISION,
             "--profile-manifest", ttp.PROFILE,
             "--at", "2026-08-13T00:00:00Z", "--apply"],
            text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr

        cls.coverage_after_init = cls.load(check_queue.COVERAGE_PATH)
        cls.queue_after_init = cls.load(check_queue.QUEUE_PATH)
        cls.contract_after_init = cls.load(
            check_queue.PROGRESS_PATH)["contract"]

        plan = cls.task_plan()
        plan_path = root / ttp.PLAN_RELATIVE
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
        queue_bytes_before = (root / check_queue.QUEUE_PATH).read_bytes()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = ttp.apply_task_plan.main(
                [str(root), "--plan", ttp.PLAN_RELATIVE, "--apply"])
        assert code == 0, buffer.getvalue()

        cls.queue_bytes_unchanged = (
            queue_bytes_before ==
            (root / check_queue.QUEUE_PATH).read_bytes())
        cls.coverage_after_plan = cls.load(check_queue.COVERAGE_PATH)
        cls.queue_after_plan = cls.load(check_queue.QUEUE_PATH)
        cls.contract_after_plan = cls.load(
            check_queue.PROGRESS_PATH)["contract"]

        queue = cls.queue_after_plan
        compiled = subprocess.run(
            [sys.executable, str(TOOLS / "compile_queue.py"), str(root),
             "--apply", "--expected-queue-revision",
             str(queue["queue_revision"]), "--expected-sha256",
             kblib.sha256_file(root / check_queue.QUEUE_PATH),
             "--actor-role", "integrator"],
            text=True, capture_output=True, check=False)
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr
        cls.queue_after_compile = cls.load(check_queue.QUEUE_PATH)
        cls.runtime_errors_after_compile = check_queue.validate_runtime(
            str(root))["errors"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def load(cls, relative):
        return kblib.load_yaml_file(cls.root / relative)

    @classmethod
    def task_plan(cls):
        def sha(relative):
            return kblib.sha256_file(cls.root / relative)
        return {
            "schema_version": 1,
            "plan_id": "TP-001",
            "task_id": ttp.TASK_ID,
            "approval_reference": "operator confirmation 2026-08-13",
            "before": {
                "coverage_sha256": sha(check_queue.COVERAGE_PATH),
                "queue_sha256": sha(check_queue.QUEUE_PATH),
                "progress_sha256": sha(check_queue.PROGRESS_PATH),
            },
            "contract_after": {
                "contract_version": "c1",
                "completion_semantics": "build",
                "objective": "Exercise task planning",
                "exclusions": [],
                "scope_version": "s1",
                "concurrency_cap": 1,
                "standards_version": FIXTURE_UPSTREAM_REVISION,
                "selected_profile_manifest": ttp.PROFILE,
                "selected_route_ids": ["R02"],
                "selected_card_paths": [],
                "selected_profile_route_ids": [],
                "selected_read_sets": [],
                "loaded_module_paths": [],
                "minimum_run_until": "",
                "checkpoint_at": "",
                "hard_stop_at": "",
                "completion_gate": "required-queue-complete",
            },
            "coverage_after": {
                "pages": [copy.deepcopy(ttp.PAGE)],
                "batch_specs": [copy.deepcopy(ttp.BATCH_SPEC)],
            },
        }

    def test_profile_and_adoption_never_generated_coverage_rows(self):
        self.assertEqual(
            [], self.coverage_after_init["pages"],
            "Coverage held rows straight after init_state; some writer "
            "other than the user-confirmed Task Plan invented Required "
            "work, which is the inference the flow forbids")
        for field in ("selected_route_ids", "selected_card_paths",
                      "selected_read_sets", "loaded_module_paths"):
            self.assertEqual([], self.contract_after_init[field], field)

    def test_apply_task_plan_writes_contract_and_coverage_but_no_queue(self):
        self.assertEqual(
            [ttp.PAGE["path"]],
            [page["path"] for page in self.coverage_after_plan["pages"]],
            "Coverage rows must be exactly the confirmed plan's own")
        self.assertEqual([ttp.R01_CARD, ttp.CARD],
                         self.contract_after_plan["selected_card_paths"])
        self.assertEqual([ttp.R01_READ_SET, ttp.READ_SET],
                         self.contract_after_plan["selected_read_sets"])
        self.assertTrue(self.contract_after_plan["loaded_module_paths"])
        self.assertEqual(
            [], self.queue_after_plan["required_queue"],
            "apply_task_plan materialized Queue items; the Queue has one "
            "writer and a second one would bypass the provenance line "
            "check_queue draws at materialization")
        self.assertTrue(
            self.queue_bytes_unchanged,
            "apply_task_plan changed the Queue file's bytes; even a "
            "no-op rewrite would blur which writer owns the Queue")

    def test_compile_queue_is_the_sole_queue_materializer(self):
        self.assertEqual(
            [ttp.BATCH_SPEC["id"]],
            [item["id"] for item in
             self.queue_after_compile["required_queue"]],
            "compile_queue --apply must be the step that makes Queue "
            "items appear; if they are missing the handoff between the "
            "two writers is broken")
        self.assertEqual(
            [], self.runtime_errors_after_compile,
            "after the compiler runs, the runtime must validate with no "
            "allowance; leftover errors mean the split transaction left "
            "work undone")


class RecoveryPrecedenceTests(unittest.TestCase):
    """Item 13: existing-task recovery beats fresh onboarding everywhere."""

    def test_status_prefers_resume_over_a_fresh_passing_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tpos.make_root(tmp)
            tpos.fill_candidate(root)
            (root / ".cambium" / "state").mkdir(parents=True)
            code, view, _ = tpos.run_status_json(
                root, "--profile-id", tpos.FILLED_ID)
            self.assertEqual(0, code)
            entry = next(item for item in view["candidates"]
                         if item["targeted"])
            self.assertEqual(
                "pass", entry["profile_load"]["result"],
                "fixture defect: the candidate was meant to pass so the "
                "precedence claim is actually exercised")
            self.assertEqual(
                "resume-existing-task", view["next_action"],
                "a passing candidate must not outrank .cambium/state/; "
                "onboarding over live runtime state is how a half-done "
                "task gets silently orphaned")

    def test_apply_profile_adoption_refuses_over_existing_runtime(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "repo"
        shutil.copytree(_FOUNDING_BASE, root)
        tap.write_plan(root, tap.initial_plan(root))
        (root / ".cambium" / "state").mkdir(parents=True)
        before = tap.tree_state(root)
        code, out = tap.run_tool(root, "--apply")
        self.assertEqual(1, code, out)
        self.assertIn(
            "adopt_standards.py", out,
            "the refusal must route an active task to the runtime-aware "
            "adopter instead of merely saying no")
        self.assertEqual(
            before, tap.tree_state(root),
            "a refused adoption modified the tree; the refusal is only "
            "safe if it is a strict no-op")


# ===========================================================================
# B. Lifecycle consistency regressions (text pins)
# ===========================================================================

class LifecycleTextPinTests(unittest.TestCase):
    README_EN = REPOSITORY / "README.md"
    README_ZH = REPOSITORY / "README.zh-CN.md"
    PROFILES_README = REPOSITORY / "profiles" / "README.md"
    TEMPLATE_README = TEMPLATE / "README.md"

    def test_no_document_teaches_the_raw_template_copy(self):
        for path in (self.README_EN, self.README_ZH,
                     self.PROFILES_README, self.TEMPLATE_README):
            self.assertNotIn(
                "cp -R profiles/_template",
                path.read_text(encoding="utf-8"),
                "%s resurrected the raw `cp -R` instruction; that path "
                "bypasses the whitelist, copies template junk and the "
                "orientation README, and skips the derived identity "
                "cells the scaffolder owns" % path.name)

    def test_first_batch_language_is_gone_from_the_flow_surfaces(self):
        surfaces = {
            "profiles/interview.yaml": INTERVIEW.read_text(encoding="utf-8"),
            "profiles/answer-patterns.md":
                (REPOSITORY / "profiles" / "answer-patterns.md").read_text(
                    encoding="utf-8"),
            "_template/registries/registered-scans.md":
                (TEMPLATE / "registries" / "registered-scans.md").read_text(
                    encoding="utf-8"),
            "_template/scan-configs/residual-scan.yaml":
                (TEMPLATE / "scan-configs" / "residual-scan.yaml").read_text(
                    encoding="utf-8"),
            "README.md#Adopt Cambium":
                readme_adoption_section(self.README_EN, "## Adopt Cambium"),
            "README.zh-CN.md#采用 Cambium":
                readme_adoption_section(self.README_ZH, "## 采用 Cambium"),
        }
        for name, text in surfaces.items():
            self.assertNotIn(
                "first batch", text,
                "%s speaks of a 'first batch' again; the witness is owed "
                "by bounded founding — before any batch, Queue, or "
                "Coverage exists — and batch language re-smuggles runtime "
                "state into pre-task founding" % name)

    def test_both_readmes_name_the_flow_writers_and_the_second_revision(
            self):
        en = collapse_ws(self.README_EN.read_text(encoding="utf-8"))
        zh = self.README_ZH.read_text(encoding="utf-8")
        zh_dense = "".join(zh.split())
        for fragment in ("scaffold_profile.py", "apply_profile_adoption.py"):
            self.assertIn(
                fragment, en,
                "README.md no longer names %s; adopters would fall back "
                "to hand-run steps the tools exist to replace" % fragment)
            self.assertIn(fragment, zh, "README.zh-CN.md no longer names "
                                        "%s" % fragment)
        self.assertIn(
            "second R09 revision", en,
            "README.md dropped the second R09 revision from the founding "
            "sequence; without it the configured slot has no documented "
            "path from not-applicable")
        self.assertIn(
            "第二次R09修订", zh_dense,
            "README.zh-CN.md dropped 第二次 R09 修订; the two languages "
            "would teach different founding sequences")

    def test_candidate_preparation_resolves_to_one_kernel_owner(self):
        k02_relative = (
            "kernel/K02 Knowledge Work Construction/"
            "03 Corpus Planning Applicability and Lifecycle.md")
        k02_03 = (REPOSITORY / k02_relative).read_text(encoding="utf-8")
        r13 = (REPOSITORY / "Read Set" /
               "R13 Corpus Planning Read Set.md").read_text(encoding="utf-8")
        interview = INTERVIEW.read_text(encoding="utf-8")
        c3_block = interview_block(
            interview, "- id: C3", "\nself_path_rewrites:")
        self.assertIn(
            "Candidate artifacts acquire no authority before that adoption "
            "commits.", collapse_ws(k02_03),
            "K02/03 lost the authority boundary for planning candidates")
        declaration = kblib.parse_yaml_subset(kblib.extract_frontmatter(r13))
        targets = {
            target
            for edge in declaration["load_edges"]
            for target in edge["targets"]
        }
        self.assertIn(
            k02_relative, targets,
            "R13 no longer resolves to the canonical lifecycle owner")
        self.assertNotIn(
            "candidate preparation", r13,
            "Read Set prose became a second owner of the lifecycle rule; "
            "R13 should declare only the loading edge")
        self.assertIn(
            "a second R09 revision configures the slot", c3_block,
            "the interview's closing review no longer tells an "
            "empty-corpus operator that a second R09 revision configures "
            "Corpus Planning; the three owners of this statement must "
            "agree or the empty-corpus branch dead-ends")
        self.assertIn("K02/03", c3_block)

    def test_both_readmes_state_the_witness_owner_merge_rule(self):
        en = collapse_ws(readme_adoption_section(
            self.README_EN, "## Adopt Cambium"))
        zh = "".join(readme_adoption_section(
            self.README_ZH, "## 采用 Cambium").split())
        self.assertIn(
            "never merged only to save files", en,
            "README.md lost the merge rule; without it 'one page may "
            "serve as both owner and witness' reads as an invitation to "
            "collapse founding into one artificial page")
        self.assertIn(
            "为了少建文件而强行合并", zh,
            "README.zh-CN.md lost the merge rule; the two languages "
            "would then disagree on whether founding pages may be "
            "collapsed to save files")

    def test_scaffold_is_the_creation_path_and_fallback_has_one_owner(
            self):
        interview = INTERVIEW.read_text(encoding="utf-8")
        profiles_readme = self.PROFILES_README.read_text(encoding="utf-8")
        template_readme = self.TEMPLATE_README.read_text(encoding="utf-8")
        self.assertIn(
            "manual whitelist copy is the no-agent fallback", interview,
            "profiles/interview.yaml no longer subordinates manual "
            "copying to the scaffolder; conducting agents would treat "
            "copy and scaffold as equal peers and the junk/derivation "
            "guarantees quietly stop applying")
        for name, text in (("profiles/README.md", profiles_readme),
                           ("profiles/_template/README.md",
                            template_readme)):
            self.assertIn(
                "scaffold_profile.py", text,
                "%s no longer names the scaffolder as the creation path"
                % name)
            self.assertIn(
                "template-files.yaml", text,
                "%s no longer names the whitelist that bounds the "
                "scaffolder's copy" % name)
            self.assertNotIn(
                "no-agent fallback", text,
                "%s duplicated the interview's fallback instruction; "
                "documentation should link the whitelist, not maintain a "
                "second procedure" % name)


if __name__ == "__main__":
    unittest.main()
