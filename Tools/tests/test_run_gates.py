"""The adopter verification set is a derivation, not a checklist.

The incident this tool exists for: a prose list of nine commands, unranked,
was executed selectively -- the executor supplied the ranking the list
withheld, skipped two advisory checkers, and the list itself was wrong (it
named a lint that is not a gate and omitted a registered producer).  The
fix is structural: K00/12's Stable Gate ID Registry stays the ONE
enumeration, the runner derives the set from it, and a row the runner
cannot classify fails the run closed so the registry cannot grow past its
executor silently.

The full sweep's green path is exercised where a complete adopter runtime
exists -- that is what an adoption runs it on; here the derivation, the
boundary check, and the CLI's list mode are pinned.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
for path in (str(TOOLS), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import check_queue  # noqa: E402
import run_gates  # noqa: E402


class DerivationTests(unittest.TestCase):
    """The pure derivation, against the live registry of this repository."""

    ROOT = str(TOOLS.parent)

    def registry(self):
        registry, errors = check_queue.standards_gate_registry(self.ROOT)
        self.assertEqual([], errors)
        return registry

    def recipes(self):
        return run_gates._recipes(
            self.ROOT, "profiles/examples/agent-atlas/profile.md", [])

    def test_every_registry_row_is_classified_or_the_run_fails(self):
        registry = self.registry()
        derived, errors = run_gates.derive_verification_set(
            self.ROOT, registry, self.recipes())
        self.assertEqual([], errors)
        classified = {gate_id for gate_id, _kind, _cmd in derived}
        expected = {
            gate_id for gate_id, predicate in registry.items()
            if predicate["lifecycle_states"] == ("not-batch-scoped",)
        }
        self.assertEqual(expected, classified,
                         "every not-batch-scoped row is classified; a "
                         "missing one would be a silent narrowing")

    def test_batch_scoped_rows_are_not_in_the_sweep(self):
        derived, _ = run_gates.derive_verification_set(
            self.ROOT, self.registry(), self.recipes())
        gate_ids = {gate_id for gate_id, _kind, _cmd in derived}
        for batch_gate in ("batch-close", "batch-review",
                           "required-queue-admission",
                           "standards-revalidation"):
            self.assertNotIn(batch_gate, gate_ids)

    def test_transaction_writers_are_never_run(self):
        derived, _ = run_gates.derive_verification_set(
            self.ROOT, self.registry(), self.recipes())
        kinds = {gate_id: kind for gate_id, kind, _cmd in derived}
        self.assertEqual("transaction", kinds["standards-adoption"])
        self.assertEqual("transaction",
                         kinds["corpus-plan-semantic-acceptance"])
        for _gate_id, kind, command in derived:
            if kind == "transaction":
                self.assertIsNone(command)

    def test_an_unrecognized_producer_fails_the_derivation_closed(self):
        registry = self.registry()
        registry["future-gate"] = {
            "tool": "check_future", "tool_version": "1.0.0",
            "check": "future-summary", "mode": "*",
            "dimensions": ("*",),
            "lifecycle_states": ("not-batch-scoped",),
        }
        _derived, errors = run_gates.derive_verification_set(
            self.ROOT, registry, self.recipes())
        self.assertTrue(errors)
        self.assertIn("no recipe", errors[0])

    def test_one_vocab_run_serves_both_registered_gates(self):
        """check_vocab is a two-gate producer; the sweep runs it once."""
        derived, _ = run_gates.derive_verification_set(
            self.ROOT, self.registry(), self.recipes())
        commands = [tuple(command) for _gate, kind, command in derived
                    if kind == "run" and command and
                    any("check_vocab" in part for part in command)]
        self.assertEqual(2, len(commands))
        self.assertEqual(1, len(set(commands)))

    def test_the_vocab_sweep_measures_against_the_resolved_policy(self):
        """First-live-run defect, pinned: a sweep that hands check_vocab no
        quotas measures a Configured profile against kernel defaults and
        reports an excess nobody has.  The recipe must carry the resolver's
        values and fingerprint -- the same ones batch-close consumes."""
        import contract_exception_policy
        recipes = self.recipes()
        command = recipes[("check_vocab", "*")]
        rubric = (TOOLS.parent /
                  "profiles/examples/agent-atlas/priority-rubric.md")
        policy, fingerprint, errors = (
            contract_exception_policy.effective_priority_policy(
                rubric.read_text(encoding="utf-8")))
        self.assertEqual([], errors)
        self.assertIn("--quota-p0", command)
        self.assertIn(str(policy["resolved"]["priority_quota.P0"]),
                      command)
        self.assertIn("--policy-fingerprint", command)
        self.assertIn(fingerprint, command)

    def test_the_manual_card_synchronization_row_gets_its_machine_input(self):
        derived, _ = run_gates.derive_verification_set(
            self.ROOT, self.registry(), self.recipes())
        kinds = {gate_id: (kind, command)
                 for gate_id, kind, command in derived}
        kind, command = kinds["runtime-card-synchronization"]
        self.assertEqual("input", kind)
        self.assertTrue(any("stamp_cards" in part for part in command))


class BoundaryTests(unittest.TestCase):
    """The distribution boundary speaks only to adopters, and out loud."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = self.temporary.name

    def install_declaration(self):
        source = TOOLS.parent / run_gates.DISTRIBUTION_BOUNDARY_PATH
        target = Path(self.root) / run_gates.DISTRIBUTION_BOUNDARY_PATH
        target.write_text(source.read_text(encoding="utf-8"),
                          encoding="utf-8")

    def test_an_example_profile_selects_the_distribution_context(self):
        findings, errors = run_gates._boundary_findings(
            self.root, "profiles/examples/minimal-notes/profile.md")
        self.assertEqual(([], []), (findings, errors))

    def test_a_missing_declaration_is_a_failure_not_a_shrug(self):
        _findings, errors = run_gates._boundary_findings(
            self.root, "profiles/mine/profile.md")
        self.assertTrue(errors)
        self.assertIn("missing", errors[0])

    def test_a_carried_distribution_tree_is_a_candidate_with_its_reason(self):
        self.install_declaration()
        os.makedirs(os.path.join(self.root, "Tools", "tests"))
        findings, errors = run_gates._boundary_findings(
            self.root, "profiles/mine/profile.md")
        self.assertEqual([], errors)
        self.assertEqual(1, len(findings))
        self.assertIn("Tools/tests", findings[0])
        self.assertIn("distribution-only", findings[0])

    def test_a_declared_single_file_is_a_candidate_like_a_tree(self):
        """An entry may be one file, not only a directory.

        A file is declared when its whole reason to exist is a declared
        tree -- a manifest OF it, or a tool whose one job is to copy it --
        because retiring the tree and keeping the file leaves executable
        code that can never run.
        """
        self.install_declaration()
        os.makedirs(os.path.join(self.root, "Tools"))
        open(os.path.join(self.root, "Tools", "scaffold_profile.py"),
             "w").write("x\n")
        findings, errors = run_gates._boundary_findings(
            self.root, "profiles/mine/profile.md")
        self.assertEqual([], errors)
        self.assertEqual(1, len(findings))
        self.assertIn("Tools/scaffold_profile.py", findings[0])

    def test_the_profile_creation_kit_is_declared_whole(self):
        """The kit is one closure: template, whitelist, copier, guidance."""
        declaration, errors = run_gates._boundary_declaration(
            str(TOOLS.parent))
        self.assertEqual([], errors)
        declared = {entry["path"].rstrip("/") for entry in declaration}
        for member in ("profiles/_template", "profiles/template-files.yaml",
                       "Tools/scaffold_profile.py", "profiles/interview.yaml",
                       "profiles/answer-patterns.md"):
            self.assertIn(member, declared)

    def test_onboarding_tools_that_survive_adoption_are_not_declared(self):
        """The split the kit's closure stops at, pinned.

        `profile_onboarding_status.py` speaks to a live runtime -- its own
        precedence rule 2 is `resume-existing-task` -- and
        `apply_profile_adoption.py` is the adopter's own no-runtime R09
        writer, kept for the same reason an already-used `init_state.py` is.
        Sweeping either into the kit would retire a tool an adopter still
        reaches.
        """
        declaration, errors = run_gates._boundary_declaration(
            str(TOOLS.parent))
        self.assertEqual([], errors)
        declared = {entry["path"].rstrip("/") for entry in declaration}
        for survivor in ("Tools/profile_onboarding_status.py",
                         "Tools/apply_profile_adoption.py",
                         "Tools/init_state.py"):
            self.assertNotIn(survivor, declared)

    def test_an_adopter_without_the_trees_is_clean(self):
        self.install_declaration()
        findings, errors = run_gates._boundary_findings(
            self.root, "profiles/mine/profile.md")
        self.assertEqual(([], []), (findings, errors))


class CliListTests(unittest.TestCase):
    """--list derives and prints without running; the guard still runs."""

    def test_list_mode_names_every_derived_gate(self):
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "run_gates.py"),
             str(TOOLS.parent), "--profile", "profiles/examples/agent-atlas",
             "--list"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False)
        self.assertEqual(0, completed.returncode, completed.stdout)
        registry, errors = check_queue.standards_gate_registry(
            str(TOOLS.parent))
        self.assertEqual([], errors)
        for gate_id, predicate in registry.items():
            if predicate["lifecycle_states"] == ("not-batch-scoped",):
                self.assertIn(gate_id, completed.stdout)
            else:
                self.assertNotIn("%s " % gate_id, completed.stdout)


if __name__ == "__main__":
    unittest.main()
