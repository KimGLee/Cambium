"""The Kernel interface, candidate template, and interview must stay in step.

`kernel/K00 Standards Control/profile-interface.yaml` is the single normative
Profile-slot registry. `profiles/_template` is a copyable candidate form and
`profiles/interview.yaml` is one way to collect confirmed instance answers. A
slot therefore reaches an adopter through three surfaces, but only the Kernel
registry defines the common interface.

The module pins the joins:

1. The manifest binds exactly the interface's slot set, with no duplicate and
   no extra, and every bound file exists.
2. Every interface slot is reachable from `interview.yaml` -- through a core
   pack question's `maps_to[].file` or an expansion pack's `binds_slot`, and
   every `binds_slot` names a real slot.
3. Every interface slot names its Kernel semantic owner. A slot exists because
   a Kernel extension point needs an instance-side answer.
4. Validating the unfilled template fails on nothing but its open decisions --
   the placeholder sentinel and the unfilled identity. Every switch with a
   legal exit state ships in it, so a shipped applicability failure means a
   switch regressed to unfilled, and any other code means an adopter would
   inherit a structural defect by copying.

Two limits are worth stating, because overstating a test's reach is how a
surface ends up feeling guarded when it is not.

Assertion 4 reaches exactly as far as `check_profile.py` looks. Slot files it
does not read -- `vocabulary-extensions.yaml` belongs to `compose_vocab.py`,
`metadata-contract.yaml`'s body to `compose_page_contract.py` -- are covered by
those tools' own suites, not here.

Nothing here judges the semantic quality of a template answer or confirms it
on a user's behalf.

These are regression tests, not gates: they record no receipt, claim no Gate
ID, and judge no answer quality.
"""

import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
PROFILES = REPOSITORY / "profiles"
INTERVIEW = PROFILES / "interview.yaml"
CHECK_PROFILE = TOOLS / "check_profile.py"

TEMPLATE = "_template"

OPEN_DECISION_CODES = ("unfilled-placeholder", "profile-id-invalid")

FAIL_CODE_RE = re.compile(r"\[FAIL ([a-z0-9-]+)\]")
INLINE_FILE_RE = re.compile(r"\{file:\s*([^,}]+)")
BINDS_SLOT_RE = re.compile(r"^\s*binds_slot:\s*(.+?)\s*$", re.MULTILINE)


def _load_check_profile():
    """Reuse the production parsers so this test cannot drift from the tool."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(
        "_check_profile_under_test", CHECK_PROFILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_profile = _load_check_profile()


def interface_document():
    path = REPOSITORY / check_profile.profile_contract.PROFILE_INTERFACE_PATH
    return check_profile.kblib.parse_yaml_subset(
        path.read_text(encoding="utf-8"))


def interface_slot_names():
    return list(check_profile.profile_contract.profile_interface_slots(
        interface_document()))


def slot_records():
    """Slot name -> its Kernel-owned interface record."""
    return {row["name"]: row for row in interface_document()["slots"]}


def template_bindings():
    """Slot name -> profile-relative file, backticks off."""
    manifest = (PROFILES / TEMPLATE / "profile.md").read_text(encoding="utf-8")
    bindings, duplicates = check_profile.parse_bindings(manifest)
    return ({name: value.strip("`") for name, value in bindings.items()},
            duplicates)


class InterfaceBinding(unittest.TestCase):
    def test_template_binds_exactly_the_interface_slots(self):
        slots = interface_slot_names()
        self.assertTrue(slots, "the interface declares no slots")
        bindings, duplicates = template_bindings()
        self.assertEqual([], duplicates, "a slot name is bound twice")
        self.assertEqual(
            sorted(slots), sorted(bindings),
            "profiles/%s/profile.md must bind exactly the slots "
            "the Kernel interface declares; a slot added to the interface "
            "reaches an adopter only through the template" % TEMPLATE)

    def test_template_ships_every_bound_file(self):
        bindings, _ = template_bindings()
        for slot, relative in sorted(bindings.items()):
            with self.subTest(slot=slot):
                self.assertTrue(
                    (PROFILES / TEMPLATE / relative).is_file(),
                    "the manifest binds `%s` to %s, which does not exist; a "
                    "copied profile would fail check_profile.py on an unbound "
                    "slot" % (slot, relative))


class KernelProjection(unittest.TestCase):
    """A slot exists because a kernel module needs an instance-side answer."""

    def test_every_slot_names_its_kernel_owner(self):
        missing = sorted(
            name for name, row in slot_records().items()
            if not isinstance(row.get("kernel_owner"), str)
            or not row["kernel_owner"].strip())
        self.assertEqual(
            [], missing,
            "these interface slots name no Kernel semantic owner: %s"
            % missing)


class InterviewCoverage(unittest.TestCase):
    """Every slot must be something the interview actually asks about."""

    def _reachable_slots(self):
        text = INTERVIEW.read_text(encoding="utf-8")
        bindings, _ = template_bindings()
        file_to_slot = {relative: slot for slot, relative in bindings.items()}

        reached = set()
        # A core pack question reaches a slot through the file it writes.
        for raw in INLINE_FILE_RE.findall(text):
            slot = file_to_slot.get(raw.strip())
            if slot is not None:
                reached.add(slot)
        # An expansion pack reaches a slot by naming it.
        for raw in BINDS_SLOT_RE.findall(text):
            reached.add(raw.strip())
        return reached

    def test_every_interface_slot_is_reachable_from_the_interview(self):
        unreachable = sorted(set(interface_slot_names())
                             - self._reachable_slots())
        self.assertEqual(
            [], unreachable,
            "no interview question or expansion pack fills these slots, so an "
            "interview-conducted profile leaves them at whatever the template "
            "shipped -- not a decision the operator made: %s" % unreachable)

    def test_binds_slot_values_are_real_interface_slots(self):
        unknown = sorted(
            {raw.strip() for raw
             in BINDS_SLOT_RE.findall(INTERVIEW.read_text(encoding="utf-8"))}
            - set(interface_slot_names()))
        self.assertEqual(
            [], unknown,
            "binds_slot must carry the exact interface slot name so the join "
            "is machine-checkable rather than a slug a reader has to guess "
            "at: %s" % unknown)


class TemplateShape(unittest.TestCase):
    def setUp(self):
        self.result = subprocess.run(
            [sys.executable, str(CHECK_PROFILE), "profiles/%s" % TEMPLATE,
             "--root", str(REPOSITORY)],
            cwd=str(REPOSITORY), text=True, capture_output=True, check=False)

    def test_unfilled_failures_are_exactly_the_open_decisions(self):
        self.assertNotEqual(
            0, self.result.returncode,
            "the shipped template must not validate: its identity is unfilled "
            "so it is never runnable or selectable in place")
        fail_lines = [line for line in self.result.stdout.splitlines()
                      if line.strip().startswith("[FAIL")]
        self.assertTrue(fail_lines, self.result.stdout)
        for line in fail_lines:
            match = FAIL_CODE_RE.search(line)
            self.assertIsNotNone(match, line)
            self.assertIn(
                match.group(1), OPEN_DECISION_CODES,
                "unexpected failure in the shipped template. Every switch "
                "with a legal exit state ships in it, so an applicability "
                "failure means a switch regressed to unfilled and any other "
                "code is a structural defect an adopter inherits by copying: "
                "%s" % line)


if __name__ == "__main__":
    unittest.main()
