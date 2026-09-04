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
   pack question's `maps_to[].file` or an expansion pack's `binds_slot`.
   Every mapped file must exist, every Markdown anchor must name a heading in
   the Kernel-owned form, every YAML anchor must name a real top-level key,
   and duplicate/unknown destinations fail.
3. Every interface slot names its Kernel semantic owner. A slot exists because
   a Kernel extension point needs an instance-side answer.
4. Validating the unfilled template fails on nothing but its open decisions --
   the placeholder sentinel and the unfilled identity. Every switch with a
   legal exit state ships in it, so a shipped applicability failure means a
   switch regressed to unfilled, and any other code means an adopter would
   inherit a structural defect by copying.

Two limits are worth stating, because overstating a test's reach is how a
surface ends up feeling guarded when it is not.

Assertion 4 reaches exactly as far as `check_profile.py` looks. It validates
the common file form and typed Profile closure; domain-specific body contracts
such as Vocabulary composition and page-contract projection remain covered by
their owning tools, not redefined here.

Nothing here judges the semantic quality of a template answer or confirms it
on a user's behalf.

These are regression tests, not gates: they record no receipt, claim no Gate
ID, and judge no answer quality.
"""

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
MAP_TO_RE = re.compile(
    r"^\s*-\s*\{file:\s*([^,}]+?)"
    r"(?:,\s*anchor:\s*(.+?))?\}\s*$")
BINDS_SLOT_RE = re.compile(r"^\s*binds_slot:\s*(.+?)\s*$", re.MULTILINE)

if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

import Tools.platform.agent_interface.entrypoint_loader as entrypoint_loader  # noqa: E402


check_profile = entrypoint_loader.load_tool_implementation(
    "check_profile", TOOLS)


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


def form_records():
    """Profile-relative path -> (slot name or manifest, form)."""
    manifest, slots = check_profile.profile_contract.profile_interface_forms(
        interface_document())
    records = {manifest.path: ("manifest", manifest)}
    records.update({form.path: (slot, form) for slot, form in slots.items()})
    return records


def form_records_by_id(interface):
    """Form ID -> (template-relative path, parsed common form)."""
    manifest, slots = check_profile.profile_contract.profile_interface_forms(
        interface)
    records = {"profile-manifest": (manifest.path, manifest)}
    slot_ids = {row["name"]: row["slot_id"] for row in interface["slots"]}
    records.update({
        slot_ids[slot]: (form.path, form)
        for slot, form in slots.items()
    })
    return records


def markdown_contracts_for_form(interface, form_id):
    tables = tuple(
        row for row in interface["tables"].values()
        if row["form_id"] == form_id)
    carriers = tuple(
        (carrier_id, row)
        for carrier_id, row in interface["scalar_carriers"].items()
        if row["form_id"] == form_id)
    return tables, carriers


def mutate_direct_table(text, section, header, mode):
    """Mutate one exact direct-H2 table without relying on its prose."""
    matches = []
    for h2, h3, rows in check_profile.profile_contract.\
            _direct_h2_table_groups(text):
        if h2 == section and h3 is None and rows and \
                rows[0].cells == tuple(header):
            matches.append(rows)
    if len(matches) != 1:
        raise AssertionError(
            "expected one %r table, found %d" % (section, len(matches)))
    rows = matches[0]
    lines = text.splitlines(keepends=True)
    start = rows[0].line - 1
    end = rows[-1].line
    block = lines[start:end]
    if mode == "header":
        block[0] = "| Arbitrary owner column | " + \
            " | ".join(header[1:]) + " |\n"
        lines[start:end] = block
    elif mode == "missing":
        del lines[start:end]
    elif mode == "multiple":
        lines[end:end] = ["\n"] + block
    else:
        raise AssertionError("unsupported table mutation %r" % mode)
    return "".join(lines)


def mutate_scalar_carrier(text, section, label):
    """Replace one carrier value in its exact H2 with an invalid form."""
    lines = text.splitlines(keepends=True)
    current_h2 = None
    matches = []
    pattern = re.compile(r"^(\s*-\s+%s:\s*).*$" % re.escape(label))
    for index, line in enumerate(lines):
        heading = check_profile.kblib.markdown_atx_heading(
            line.rstrip("\r\n"))
        if heading is not None:
            current_h2 = heading[1] if heading[0] == 2 else current_h2
            if heading[0] == 1:
                current_h2 = None
            continue
        match = pattern.match(line.rstrip("\r\n"))
        if current_h2 == section and match is not None:
            matches.append((index, match.group(1)))
    if len(matches) != 1:
        raise AssertionError(
            "expected one %s carrier in %r, found %d" %
            (label, section, len(matches)))
    index, prefix = matches[0]
    ending = "\n" if lines[index].endswith("\n") else ""
    lines[index] = prefix + "invalid-owner-form" + ending
    return "".join(lines)


def _unquote(value):
    value = value.strip()
    if (len(value) >= 2 and value[0] == value[-1] and
            value[0] in ("'", '"')):
        return value[1:-1]
    return value


def interview_maps():
    """Return (line, file, optional anchor) for every maps_to row."""
    rows = []
    text = INTERVIEW.read_text(encoding="utf-8")
    maps_to_indent = None
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if stripped == "maps_to:":
            maps_to_indent = indent
            continue
        if maps_to_indent is None:
            continue
        if stripped and indent <= maps_to_indent:
            maps_to_indent = None
            continue
        if "{file:" not in line:
            continue
        match = MAP_TO_RE.match(line)
        if match is None:
            raise AssertionError(
                "interview maps_to row %d is not the closed inline form: %s" %
                (line_number, line))
        rows.append((
            line_number,
            _unquote(match.group(1)),
            _unquote(match.group(2)) if match.group(2) is not None else None,
        ))
    return rows


def interview_map_findings(rows):
    """Return duplicate and unresolved maps_to findings for supplied rows."""
    records = form_records()
    seen = set()
    duplicates = []
    invalid = []
    for line, relative, anchor in rows:
        key = (relative, anchor)
        if key in seen:
            duplicates.append("line %d: %r" % (line, key))
        seen.add(key)
        if (relative.startswith("/") or "\\" in relative or
                any(part in ("", ".", "..")
                    for part in relative.split("/"))):
            invalid.append("line %d: invalid file %r" % (line, relative))
            continue
        target = PROFILES / TEMPLATE / relative
        if not target.is_file():
            invalid.append("line %d: missing file %r" % (line, relative))
            continue
        if anchor is None:
            continue
        if relative.endswith(".md"):
            record = records.get(relative)
            if record is None or anchor not in record[1].required_headings:
                invalid.append(
                    "line %d: Markdown anchor %r is not registered for %r"
                    % (line, anchor, relative))
        elif relative.endswith((".yaml", ".yml")):
            document = check_profile.kblib.parse_yaml_subset(
                target.read_text(encoding="utf-8"))
            record = records.get(relative)
            if (record is None or not isinstance(document, dict) or
                    anchor not in document):
                invalid.append(
                    "line %d: YAML anchor %r is not a registered top-level "
                    "key of %r"
                    % (line, anchor, relative))
        else:
            invalid.append(
                "line %d: anchored maps_to file has no supported form: %r"
                % (line, relative))
    return duplicates, invalid


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

    def test_template_bindings_are_the_kernel_owned_form_paths(self):
        bindings, _ = template_bindings()
        expected = {
            slot: form.path for slot, form in
            check_profile.profile_contract.profile_interface_forms(
                interface_document())[1].items()
        }
        self.assertEqual(expected, bindings)

    def test_template_markdown_skeletons_are_owner_exact(self):
        interface = interface_document()
        tables = {}
        for row in interface["tables"].values():
            tables.setdefault(row["form_id"], []).append(row)
        carriers = {}
        for carrier_id, row in interface["scalar_carriers"].items():
            carriers.setdefault(row["form_id"], []).append((carrier_id, row))
        slot_ids = {
            row["name"]: row["slot_id"] for row in interface["slots"]
        }
        for relative, (_name, form) in sorted(form_records().items()):
            if not relative.endswith(".md"):
                continue
            with self.subTest(path=relative):
                text = (PROFILES / TEMPLATE / relative).read_text(
                    encoding="utf-8")
                headings = tuple(
                    "%s %s" % ("#" * level, title)
                    for _line, level, title in
                    check_profile.kblib.headings_of(
                        check_profile.kblib.blank_markdown_authority(text))
                    if level <= 2)
                self.assertEqual(form.required_headings, headings)
                form_id = (
                    "profile-manifest" if _name == "manifest" else
                    slot_ids[_name])
                errors, _subheadings = check_profile.profile_contract.\
                    _markdown_form_errors(
                        text, form, tables.get(form_id, ()),
                        carriers.get(form_id, ()),
                        interface["scalar_carrier_types"])
                self.assertEqual((), errors)

    def test_template_yaml_envelopes_are_owner_exact(self):
        interface = interface_document()
        for relative, (_name, form) in sorted(form_records().items()):
            if not relative.endswith(".yaml"):
                continue
            with self.subTest(path=relative):
                text = (PROFILES / TEMPLATE / relative).read_text(
                    encoding="utf-8")
                self.assertEqual((), check_profile.profile_contract.\
                    _yaml_form_errors(
                        text, form, str(REPOSITORY), interface))

    def test_every_registered_table_fails_closed_under_form_drift(self):
        interface = interface_document()
        forms = form_records_by_id(interface)
        self.assertEqual(39, len(interface["tables"]))
        for table_id, table in sorted(interface["tables"].items()):
            relative, form = forms[table["form_id"]]
            original = (PROFILES / TEMPLATE / relative).read_text(
                encoding="utf-8")
            tables, carriers = markdown_contracts_for_form(
                interface, table["form_id"])
            for mutation, expected in (
                    ("header", "profile-form-table-header"),
                    ("missing", "profile-form-table-count"),
                    ("multiple", "profile-form-table-count")):
                with self.subTest(table=table_id, mutation=mutation):
                    changed = mutate_direct_table(
                        original, table["section"], table["header"],
                        mutation)
                    errors, _subheadings = check_profile.profile_contract.\
                        _markdown_form_errors(
                            changed, form, tables, carriers,
                            interface["scalar_carrier_types"])
                    self.assertIn(expected, {code for code, _ in errors})

    def test_every_scalar_carrier_fails_closed_under_value_drift(self):
        interface = interface_document()
        forms = form_records_by_id(interface)
        self.assertEqual(19, len(interface["scalar_carriers"]))
        for carrier_id, carrier in sorted(
                interface["scalar_carriers"].items()):
            with self.subTest(carrier=carrier_id):
                relative, form = forms[carrier["form_id"]]
                original = (PROFILES / TEMPLATE / relative).read_text(
                    encoding="utf-8")
                carrier_type = interface["scalar_carrier_types"][
                    carrier["carrier_type"]]
                changed = mutate_scalar_carrier(
                    original, carrier["section"], carrier_type["label"])
                tables, carriers = markdown_contracts_for_form(
                    interface, carrier["form_id"])
                errors, _subheadings = check_profile.profile_contract.\
                    _markdown_form_errors(
                        changed, form, tables, carriers,
                        interface["scalar_carrier_types"])
                self.assertIn(
                    "profile-form-scalar-value",
                    {code for code, _ in errors})

    def test_every_yaml_form_rejects_unknown_and_duplicate_top_level_keys(self):
        interface = interface_document()
        yaml_forms = tuple(
            (relative, form)
            for relative, (_name, form) in sorted(form_records().items())
            if relative.endswith(".yaml"))
        self.assertEqual(4, len(yaml_forms))
        for relative, form in yaml_forms:
            original = (PROFILES / TEMPLATE / relative).read_text(
                encoding="utf-8")
            match = re.search(r"^schema_version:\s*.*$", original,
                              re.MULTILINE)
            self.assertIsNotNone(match, relative)
            duplicate = (
                original[:match.start()] + match.group(0) + "\n" +
                original[match.start():])
            variants = {
                "unknown": original.rstrip() +
                           "\nunknown_top_level: invalid\n",
                "duplicate": duplicate,
            }
            for mutation, changed in variants.items():
                with self.subTest(path=relative, mutation=mutation):
                    errors = check_profile.profile_contract.\
                        _yaml_form_errors(
                            changed, form, str(REPOSITORY), interface)
                    self.assertIn(
                        "profile-form-yaml-shape",
                        {code for code, _ in errors})


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
        forms = check_profile.profile_contract.profile_interface_forms(
            interface_document())[1]
        file_to_slot = {form.path: slot for slot, form in forms.items()}

        reached = set()
        # A core pack question reaches a slot through the file it writes.
        for _line, path, _anchor in interview_maps():
            slot = file_to_slot.get(path)
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

    def test_maps_to_files_and_anchors_resolve_exactly_once(self):
        duplicates, invalid = interview_map_findings(interview_maps())
        self.assertEqual([], duplicates, "duplicate maps_to targets: %s" %
                         duplicates)
        self.assertEqual([], invalid, "unresolved maps_to targets: %s" %
                         invalid)

    def test_maps_to_validator_rejects_duplicate_and_unknown_anchors(self):
        first = interview_maps()[0]
        duplicates, invalid = interview_map_findings((first, first))
        self.assertTrue(duplicates)
        self.assertEqual([], invalid)

        _duplicates, invalid = interview_map_findings((
            (999, "scope-and-architecture.md", "## Unknown Section"),
            (1000, "vocabulary-extensions.yaml", "unknown_key"),
        ))
        self.assertEqual(2, len(invalid))


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
