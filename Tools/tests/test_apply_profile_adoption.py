"""`Tools/apply_profile_adoption.py` — the no-runtime R09 adoption writer.

The writer is the sibling of `adopt_standards.py` for the case where no
`.cambium/` runtime exists: initial adoption instantiates the four K00/03
Standards Control placeholders and creates the first Change Summary row; a
pre-runtime profile revision updates the cells and appends a second row.
Both branches then drive the existing producers (`compose_vocab`,
`compose_page_contract`, `stamp_cards --set-version`, `stamp_cards --check`)
against the new K00/03 state. This module pins the transaction's safety
contract:

1. dry-run writes nothing anywhere (tree byte-hash unchanged, no staging
   directory) and reports the complete planned change;
2. both happy paths leave the exact promised state: cells instantiated,
   Change Summary rows appended and preserved, vocab.yaml/page_contract.yaml
   composed, cards stamped, `stamp_cards --check` exit 0, two receipts
   appended (the canonical `profile-load` pass receipt plus the commit
   receipt, which registers no Gate ID of its own);
3. every refusal (existing `.cambium/` anywhere, K00/03 drift, candidate
   byte drift, failing profile-load, nonempty changed_predicates, branch /
   state mismatch) performs zero writes;
4. an injected mid-transaction failure restores every touched byte (tree
   byte-identical) and leaves the journal marked aborted;
5. an interruption is recoverable with the same plan and refused with a
   different one; the candidate Profile directory is read-only throughout.

Regression tests, not gates: no new Gate ID, no answer-quality call.
"""

import contextlib
import hashlib
import io
import json
import re
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
GOVERNANCE = "kernel/K00 Standards Control/03 Standards Governance.md"
SIZE_REGISTER = "kernel/K00 Standards Control/16 Leaf Module Size Register.md"
PROFILE_ID = "cand"
MANIFEST = "profiles/%s/profile.md" % PROFILE_ID
PLAN_RELATIVE = "adoption-plans/PA-001.yaml"

sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))
import apply_profile_adoption  # noqa: E402
import check_profile  # noqa: E402
import kblib  # noqa: E402
import test_profile_onboarding_status as tpos  # noqa: E402
import test_template_fill  # noqa: E402  (reused semantic fill + scan config)

_BASE = None  # pristine adopting root, built once
_ADOPTED = None  # the same root after one committed initial adoption
_MODULE_TMP = None


def _build_base(target):
    """A minimal adopting repository with one passing candidate Profile."""
    target.mkdir(parents=True)
    shutil.copytree(REPOSITORY / "kernel", target / "kernel")
    (target / "profiles").mkdir()
    shutil.copyfile(REPOSITORY / "profiles" / "README.md",
                    target / "profiles" / "README.md")
    (target / "Tools").mkdir()
    for script in (REPOSITORY / "Tools").glob("*.py"):
        shutil.copyfile(script, target / "Tools" / script.name)
    shutil.copytree(REPOSITORY / "Tools" / "schemas",
                    target / "Tools" / "schemas")
    # Complete the minimal adopter from profile-load's producer-owned input
    # and capability registry.  Keeping a second hand-written subset here
    # caused new metadata contract inputs to look like path-spelling drift
    # before the candidate Profile was evaluated.
    tpos.copy_profile_load_fixture(target)
    profile = target / "profiles" / PROFILE_ID
    shutil.copytree(TEMPLATE, profile)
    for name in test_template_fill.ORIENTATION:
        (profile / name).unlink()
    for rel, old, new in test_template_fill.FILL:
        old = old.replace("fill-e2e", PROFILE_ID)
        new = new.replace("fill-e2e", PROFILE_ID)
        path = profile / rel
        text = path.read_text(encoding="utf-8")
        assert old in text, (rel, old)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    (profile / "scan-configs" / "residual-scan.yaml").write_text(
        test_template_fill.SCAN_CONFIG.replace("fill-e2e", PROFILE_ID),
        encoding="utf-8")
    # This adopter's register grants K00/03 growth headroom for its Change
    # Summary rows (an adopter governance choice; the shipped 11.5KB cap
    # leaves only ~150 bytes over the shipped measured value).
    register = target / SIZE_REGISTER
    lines = register.read_text(encoding="utf-8").splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("| [[kernel/K00 Standards Control/"
                           "03 Standards Governance\\|"):
            assert "| 11.5KB |" in line
            lines[index] = line.replace("| 11.5KB |", "| 13KB |", 1)
    register.write_text("".join(lines), encoding="utf-8")


def setUpModule():
    global _BASE, _ADOPTED, _MODULE_TMP
    _MODULE_TMP = tempfile.TemporaryDirectory()
    temporary_root = Path(_MODULE_TMP.name).resolve()
    _BASE = temporary_root / "base"
    _build_base(_BASE)
    _ADOPTED = temporary_root / "adopted"
    shutil.copytree(_BASE, _ADOPTED)
    write_plan(_ADOPTED, initial_plan(_ADOPTED))
    code, out = run_tool(_ADOPTED, "--apply")
    assert code == 0, out


def tearDownModule():
    _MODULE_TMP.cleanup()


def evaluation_of(root):
    evaluation = check_profile.evaluate_profile_load(
        str(root / "profiles" / PROFILE_ID), root=str(root),
        receipt_identity={"selected_profile_manifest": MANIFEST})
    assert evaluation.authorized, evaluation.output
    return evaluation


def initial_plan(root, **overrides):
    evaluation = evaluation_of(root)
    plan = {
        "schema_version": 1,
        "plan_id": "PA-001",
        "branch": "initial-adoption",
        "standards_version_after": "1.0.0",
        "standards_status_after": "approved",
        "standards_effective_date_after": "2026-08-13",
        "selected_profile_manifest_after": MANIFEST,
        "standards_version_before": None,
        "selected_profile_manifest_before": None,
        "change_summary": "Initial adoption: selected %s; upstream "
                          "https://example.test/corpus.git @ "
                          "0123456789abcdef" % MANIFEST,
        "changed_predicates": [],
        "adoption_requirement": "none",
        "k00_03_sha256_before": kblib.sha256_file(root / GOVERNANCE),
        "profile_snapshot_sha256_after": evaluation.profile_snapshot_sha256,
        "profile_contract_fingerprint_after":
            evaluation.profile_contract_fingerprint,
        "profile_load_inputs_sha256_after":
            evaluation.profile_load_inputs_sha256,
    }
    plan.update(overrides)
    return plan


def revision_plan(root, **overrides):
    plan = initial_plan(root)
    plan.update({
        "plan_id": "PA-002",
        "branch": "profile-revision",
        "standards_version_after": "1.1.0",
        "standards_effective_date_after": "2026-08-14",
        "standards_version_before": "1.0.0",
        "selected_profile_manifest_before": MANIFEST,
        "change_summary": "Profile revision inside %s: corpus-planning "
                          "reason updated" % MANIFEST,
    })
    plan.update(overrides)
    return plan


def write_plan(root, plan, relative=PLAN_RELATIVE):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
    return relative


def run_tool(root, *extra, plan=PLAN_RELATIVE):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = apply_profile_adoption.main(
            [str(root), "--plan", plan, *extra])
    return code, buffer.getvalue()


def tree_state(root):
    """Every path under root with a content/type fingerprint.

    Staging directories are the transaction's own recovery evidence and are
    reported separately by `stagings()`, so they are excluded here; every
    other byte must be accounted for.
    """
    state = {}
    for path in sorted(Path(root).rglob("*")):
        relative = path.relative_to(root).as_posix()
        if any(part.startswith(apply_profile_adoption.STAGING_PREFIX)
               for part in relative.split("/")):
            continue
        if path.is_symlink():
            state[relative] = "symlink:%s" % path.readlink()
        elif path.is_dir():
            state[relative] = "dir"
        else:
            state[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return state


def stagings(root):
    return sorted(
        entry.name for entry in Path(root).iterdir()
        if entry.name.startswith(apply_profile_adoption.STAGING_PREFIX))


def journal_of(root, staging_name):
    return json.loads(
        (Path(root) / staging_name / "journal.json").read_text(
            encoding="utf-8"))


def governance_state(root):
    state, errors = kblib.active_standards_state(
        (root / GOVERNANCE).read_text(encoding="utf-8"))
    assert not errors, errors
    return state


def change_summary_rows(root):
    lines = (root / GOVERNANCE).read_text(encoding="utf-8").splitlines()
    index = lines.index(
        "| Version | Date | Change | Changed predicates "
        "| Adoption requirement |")
    rows = []
    for line in lines[index + 2:]:
        if not line.startswith("|"):
            break
        rows.append(line)
    return rows


def mutate_candidate(root):
    """Change candidate bytes without breaking profile-load."""
    path = root / "profiles" / PROFILE_ID / "corpus-planning.yaml"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"reason: (.+)", text)
    path.write_text(
        text.replace(
            match.group(0),
            'reason: "Corpus refounded; planning deferred to the 2027 '
            'review."', 1),
        encoding="utf-8")


class ApplyProfileAdoptionTests(unittest.TestCase):
    def clone(self, source=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "repo"
        shutil.copytree(source if source is not None else _BASE, root)
        return root

    # ---- dry run -----------------------------------------------------

    def test_dry_run_writes_nothing_and_reports_the_planned_change(self):
        root = self.clone()
        plan = initial_plan(root)
        write_plan(root, plan)
        before = tree_state(root)
        code, out = run_tool(root)
        self.assertEqual(0, code, out)
        self.assertEqual(before, tree_state(root))
        self.assertEqual([], stagings(root))
        for expected in (
                "initial-adoption", "1.0.0", MANIFEST,
                plan["k00_03_sha256_before"],
                plan["profile_snapshot_sha256_after"],
                plan["profile_contract_fingerprint_after"],
                plan["profile_load_inputs_sha256_after"],
                "Change Summary row:", "compose-vocab", "stamp-check",
                "dry run"):
            self.assertIn(expected, out)

    # ---- happy paths -------------------------------------------------

    def test_initial_adoption_happy_path(self):
        root = self.clone()
        plan = initial_plan(root)
        write_plan(root, plan)
        profile_before = tree_state(root / "profiles" / PROFILE_ID)
        code, out = run_tool(root, "--apply")
        self.assertEqual(0, code, out)

        state = governance_state(root)
        self.assertEqual("1.0.0", state["standards_version"])
        self.assertEqual("approved", state["standards_status"])
        self.assertEqual("2026-08-13", state["standards_effective_date"])
        self.assertEqual(MANIFEST, state["selected_profile_manifest"])
        rows = change_summary_rows(root)
        self.assertEqual(1, len(rows))
        self.assertIn("Initial adoption", rows[0])
        self.assertIn("| none | none |", rows[0])

        self.assertTrue((root / "Tools" / "vocab.yaml").is_file())
        self.assertTrue((root / "Tools" / "page_contract.yaml").is_file())
        card = (root / "kernel" / "Cards" /
                "R09 Standards Governance Card.md").read_text(
                    encoding="utf-8")
        self.assertIn("compiled_from: '1.0.0'", card)
        check = subprocess.run(
            [sys.executable, str(root / "Tools" / "stamp_cards.py"),
             str(root), "--check"],
            text=True, capture_output=True, check=False)
        self.assertEqual(0, check.returncode, check.stdout)

        receipts = [
            json.loads(line) for line in
            (root / "adoption-plans" / "PA-001.receipts.jsonl")
            .read_text(encoding="utf-8").splitlines()]
        self.assertEqual(2, len(receipts))
        gate, commit = receipts
        self.assertEqual("check_profile", gate["tool"])
        self.assertEqual(check_profile.TOOL_VERSION, gate["tool_version"])
        self.assertEqual("profile-load", gate["gate_id"])
        self.assertEqual(plan["profile_snapshot_sha256_after"],
                         gate["profile_snapshot_sha256"])
        self.assertEqual("apply_profile_adoption", commit["tool"])
        self.assertEqual(apply_profile_adoption.TOOL_VERSION,
                         commit["tool_version"])
        self.assertNotIn("gate_id", commit,
                         "the commit receipt must register no Gate ID")
        self.assertEqual("profile-load", commit["profile_load_gate_id"])
        self.assertEqual(gate["receipt_id"],
                         commit["profile_load_receipt_id"])
        self.assertEqual(PLAN_RELATIVE, commit["plan_path"])
        self.assertEqual(
            kblib.sha256_file(root / PLAN_RELATIVE), commit["plan_sha256"])
        self.assertEqual(plan["k00_03_sha256_before"],
                         commit["k00_03_sha256_before"])
        self.assertEqual(kblib.sha256_file(root / GOVERNANCE),
                         commit["k00_03_sha256_after"])
        for field in ("profile_snapshot_sha256_after",
                      "profile_contract_fingerprint_after",
                      "profile_load_inputs_sha256_after"):
            self.assertEqual(plan[field], commit[field])

        # Hard prohibitions: no runtime appears, the candidate Profile is
        # byte-untouched, and the staging directory is gone.
        self.assertFalse((root / ".cambium").exists())
        self.assertEqual(profile_before,
                         tree_state(root / "profiles" / PROFILE_ID))
        self.assertEqual([], stagings(root))

    def test_profile_revision_happy_path(self):
        root = self.clone(_ADOPTED)
        first_rows = change_summary_rows(root)
        mutate_candidate(root)
        plan = revision_plan(root)
        relative = write_plan(root, plan, "adoption-plans/PA-002.yaml")
        profile_before = tree_state(root / "profiles" / PROFILE_ID)
        code, out = run_tool(root, "--apply", plan=relative)
        self.assertEqual(0, code, out)

        state = governance_state(root)
        self.assertEqual("1.1.0", state["standards_version"])
        self.assertEqual("2026-08-14", state["standards_effective_date"])
        self.assertEqual(MANIFEST, state["selected_profile_manifest"])
        rows = change_summary_rows(root)
        self.assertEqual(2, len(rows))
        self.assertEqual(first_rows[0], rows[0],
                         "the first Change Summary row must be preserved")
        self.assertIn("Profile revision", rows[1])
        card = (root / "kernel" / "Cards" /
                "R09 Standards Governance Card.md").read_text(
                    encoding="utf-8")
        self.assertIn("compiled_from: '1.1.0'", card)
        check = subprocess.run(
            [sys.executable, str(root / "Tools" / "stamp_cards.py"),
             str(root), "--check"],
            text=True, capture_output=True, check=False)
        self.assertEqual(0, check.returncode, check.stdout)
        self.assertEqual(profile_before,
                         tree_state(root / "profiles" / PROFILE_ID))
        self.assertFalse((root / ".cambium").exists())

    # ---- refusals (zero writes) --------------------------------------

    def assert_refused(self, root, message_fragment, *extra,
                       plan=PLAN_RELATIVE):
        before = tree_state(root)
        code, out = run_tool(root, "--apply", *extra, plan=plan)
        self.assertEqual(1, code, out)
        self.assertIn(message_fragment, out)
        self.assertEqual(before, tree_state(root))
        self.assertEqual([], stagings(root))
        return out

    def test_existing_runtime_anywhere_is_refused_toward_adopt_standards(
            self):
        root = self.clone()
        (root / "corpus" / ".cambium" / "state").mkdir(parents=True)
        write_plan(root, initial_plan(root))
        out = self.assert_refused(root, "adopt_standards.py")
        self.assertIn("corpus/.cambium", out)

    def test_k00_03_drift_after_plan_prepared_is_refused(self):
        root = self.clone()
        write_plan(root, initial_plan(root))
        governance = root / GOVERNANCE
        governance.write_text(
            governance.read_text(encoding="utf-8") + "\n",
            encoding="utf-8")
        self.assert_refused(root, "k00_03_sha256_before")

    def test_candidate_byte_drift_after_plan_prepared_is_refused(self):
        root = self.clone()
        write_plan(root, initial_plan(root))
        mutate_candidate(root)
        self.assert_refused(root, "profile_snapshot_sha256_after")

    def test_candidate_failing_profile_load_is_refused(self):
        root = self.clone()
        plan = initial_plan(root)
        write_plan(root, plan)
        scope = root / "profiles" / PROFILE_ID / "scope-and-architecture.md"
        scope.write_text(
            scope.read_text(encoding="utf-8") + "\nTODO(profile)\n",
            encoding="utf-8")
        out = self.assert_refused(root, "profile-load")
        self.assertIn("unfilled-placeholder", out)

    def test_nonempty_changed_predicates_refused_toward_adopt_standards(
            self):
        root = self.clone()
        plan = initial_plan(root, changed_predicates=[
            {"predicate_id": "PRED-X", "change_kind": "modified"}])
        write_plan(root, plan)
        self.assert_refused(root, "adopt_standards.py")

    def test_branch_state_mismatch_is_refused_both_ways(self):
        adopted = self.clone(_ADOPTED)
        write_plan(adopted, initial_plan(adopted),
                   "adoption-plans/PA-003.yaml")
        self.assert_refused(adopted, "already instantiated",
                            plan="adoption-plans/PA-003.yaml")

        pristine = self.clone()
        plan = revision_plan(pristine)
        write_plan(pristine, plan, "adoption-plans/PA-004.yaml")
        self.assert_refused(pristine, "still placeholders",
                            plan="adoption-plans/PA-004.yaml")

    # ---- abort and recovery ------------------------------------------

    def test_injected_failure_mid_transaction_restores_everything(self):
        root = self.clone()
        write_plan(root, initial_plan(root))
        before = tree_state(root)
        original = apply_profile_adoption._run_step

        def failing(command, cwd):
            if any("stamp_cards.py" in str(part) for part in command):
                return 1, "injected stamp failure"
            return original(command, cwd)

        with mock.patch.object(
                apply_profile_adoption, "_run_step", failing):
            code, out = run_tool(root, "--apply")
        self.assertEqual(1, code, out)
        self.assertIn("restored", out)
        self.assertEqual(before, tree_state(root),
                         "abort must leave the repository byte-identical")
        names = stagings(root)
        self.assertEqual(1, len(names))
        journal = journal_of(root, names[0])
        self.assertEqual("aborted", journal["status"])
        self.assertTrue(journal["restore_verified"])
        self.assertIn("injected stamp failure", journal["failure"])
        step_status = {step["step"]: step["status"]
                       for step in journal["steps"]}
        self.assertEqual("failed", step_status["stamp-set-version"])

    def test_interruption_then_retry_with_same_plan_completes(self):
        root = self.clone()
        write_plan(root, initial_plan(root))
        original = apply_profile_adoption._run_step

        def interrupting(command, cwd):
            if any("compose_page_contract.py" in str(part)
                   for part in command):
                raise KeyboardInterrupt()
            return original(command, cwd)

        with mock.patch.object(
                apply_profile_adoption, "_run_step", interrupting):
            with self.assertRaises(KeyboardInterrupt):
                run_tool(root, "--apply")
        # The interruption left a half-written repository and a journal.
        names = stagings(root)
        self.assertEqual(1, len(names))
        self.assertEqual("writing", journal_of(root, names[0])["status"])
        self.assertEqual(
            "1.0.0", governance_state(root)["standards_version"])

        code, out = run_tool(root, "--apply")
        self.assertEqual(0, code, out)
        self.assertIn("restored", out)
        self.assertEqual([], stagings(root))
        self.assertEqual(
            "1.0.0", governance_state(root)["standards_version"])
        self.assertEqual(1, len(change_summary_rows(root)),
                         "recovery must never duplicate the adoption")
        check = subprocess.run(
            [sys.executable, str(root / "Tools" / "stamp_cards.py"),
             str(root), "--check"],
            text=True, capture_output=True, check=False)
        self.assertEqual(0, check.returncode, check.stdout)

    def test_retry_with_a_different_plan_while_journal_exists_is_refused(
            self):
        root = self.clone()
        write_plan(root, initial_plan(root))
        original = apply_profile_adoption._run_step

        def interrupting(command, cwd):
            if any("compose_vocab.py" in str(part) for part in command):
                raise KeyboardInterrupt()
            return original(command, cwd)

        with mock.patch.object(
                apply_profile_adoption, "_run_step", interrupting):
            with self.assertRaises(KeyboardInterrupt):
                run_tool(root, "--apply")
        self.assertEqual(1, len(stagings(root)))

        different = initial_plan(
            root, change_summary="A different revision record")
        write_plan(root, different, "adoption-plans/PA-005.yaml")
        interrupted = tree_state(root)
        code, out = run_tool(root, "--apply",
                             plan="adoption-plans/PA-005.yaml")
        self.assertEqual(1, code, out)
        self.assertIn("different plan bytes", out)
        self.assertEqual(interrupted, tree_state(root),
                         "a refused retry must not touch the repository")
        self.assertEqual(1, len(stagings(root)))


if __name__ == "__main__":
    unittest.main()
