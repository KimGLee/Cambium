"""Re-validate every published profile example against the current tools.

`profiles/examples/*` are non-normative reference cases. The public repository
is intentionally uninstantiated: validating example data does not select the
example, create adopter state, or confirm its answers. Owner changes must not
silently leave these advertised reference cases stale.

This module closes that hole with the only binding the repository actually
carries: each example README declares a `## Validation Provenance` table naming
the validators it claims to pass and the tool version it was validated against.
The tests below re-run every declared command and compare every declared
version with the tool's own `TOOL_VERSION`, so a tool bump or a newly failing
example fails here instead of being discovered by an adopter.

This is a regression test, not a gate: it records no receipt and claims no Gate
ID.  It also judges no answer -- an example passing here is structurally valid,
not necessarily well answered.
"""

import contextlib
import io
import os
import re
import shlex
import sys
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
EXAMPLES = REPOSITORY / "profiles" / "examples"
TOOLS = REPOSITORY / "Tools"
PROVENANCE_HEADING = "Validation Provenance"
EXPECTED_COLUMNS = ("Validator", "Tool version", "Command", "Expected result")

if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

import Tools.platform.agent_interface.entrypoint_loader as entrypoint_loader  # noqa: E402
import Tools.governance.profile.profile_layout_contract as profile_layout_contract  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
from Tools.tests.support.profile_template_fixture import SCAN_CONFIG  # noqa: E402


def example_directories():
    """Every published example package, identified by its manifest."""
    return sorted(
        path.parent for path in EXAMPLES.glob(
            "*/" + profile_layout_contract.PROFILE_MANIFEST_NAME)
    )


def unbacktick(cell):
    match = re.fullmatch(r"`([^`]*)`", cell.strip())
    return match.group(1).strip() if match else cell.strip()


def provenance_rows(readme_text):
    """Return the data rows of the README's Validation Provenance table."""
    rows = []
    inside = False
    header = None
    for line in readme_text.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if heading:
            inside = heading.group(2).strip() == PROVENANCE_HEADING
            continue
        if not inside or not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
            continue
        if header is None:
            header = tuple(cells)
            continue
        rows.append(dict(zip(header, cells)))
    return header, rows


def tool_version(name):
    """Read the resolved version from the public Tool's implementation."""
    implementation = entrypoint_loader.load_tool_implementation(name, TOOLS)
    version = getattr(implementation, "TOOL_VERSION", None)
    return version if isinstance(version, str) else None


def load_residual_module():
    return entrypoint_loader.load_tool_implementation(
        "check_residual_content", TOOLS)


class ProfileExampleProvenance(unittest.TestCase):
    def test_examples_exist(self):
        self.assertTrue(
            example_directories(),
            "profiles/examples/ has no package with a profile.toml; a validation "
            "sweep with nothing to check is an invocation error, never a pass",
        )

    def test_every_example_declares_its_validation(self):
        for directory in example_directories():
            with self.subTest(example=directory.name):
                readme = directory / "README.md"
                self.assertTrue(
                    readme.is_file(),
                    "%s has no README.md to carry its Validation Provenance"
                    % directory.name,
                )
                header, rows = provenance_rows(
                    readme.read_text(encoding="utf-8"))
                self.assertEqual(
                    header, EXPECTED_COLUMNS,
                    "%s/README.md must carry a `## %s` table with columns %s"
                    % (directory.name, PROVENANCE_HEADING,
                       ", ".join(EXPECTED_COLUMNS)),
                )
                self.assertTrue(
                    rows,
                    "%s/README.md declares no validator" % directory.name)
                validators = [unbacktick(row["Validator"]) for row in rows]
                self.assertIn(
                    "check_profile", validators,
                    "%s/README.md must declare check_profile" % directory.name,
                )

    def test_declared_tool_versions_match_the_tools(self):
        for directory in example_directories():
            _header, rows = provenance_rows(
                (directory / "README.md").read_text(encoding="utf-8"))
            for row in rows:
                validator = unbacktick(row["Validator"])
                declared = unbacktick(row["Tool version"])
                with self.subTest(example=directory.name, tool=validator):
                    script = TOOLS / ("%s.py" % validator)
                    self.assertTrue(
                        script.is_file(),
                        "%s names validator %r, which is not a tool in Tools/"
                        % (directory.name, validator),
                    )
                    self.assertEqual(
                        declared, tool_version(validator),
                        "%s/README.md declares %s %s but the tool is at %s; "
                        "re-validate the example and update the stamp"
                        % (directory.name, validator, declared,
                           tool_version(validator)),
                    )

    def test_declared_commands_reference_their_own_example(self):
        for directory in example_directories():
            relative = directory.relative_to(REPOSITORY).as_posix()
            _header, rows = provenance_rows(
                (directory / "README.md").read_text(encoding="utf-8"))
            for row in rows:
                with self.subTest(example=directory.name,
                                  tool=unbacktick(row["Validator"])):
                    command = unbacktick(row["Command"])
                    self.assertIn(
                        relative, command,
                        "%s declares a command that does not name its own "
                        "package: %r" % (directory.name, command),
                    )

    def test_declared_commands_still_pass(self):
        for directory in example_directories():
            _header, rows = provenance_rows(
                (directory / "README.md").read_text(encoding="utf-8"))
            for row in rows:
                validator = unbacktick(row["Validator"])
                command = shlex.split(unbacktick(row["Command"]))
                self.assertEqual(command[0], "python3")
                expected = unbacktick(row["Expected result"])
                match = re.fullmatch(r"exit (\d+)", expected)
                self.assertIsNotNone(
                    match,
                    "%s declares an unsupported expected result %r; this test "
                    "can only re-run a command with an exit-code expectation"
                    % (directory.name, expected),
                )
                with self.subTest(example=directory.name, tool=validator):
                    self.assertEqual("Tools/%s.py" % validator, command[1])
                    implementation = entrypoint_loader.load_tool_implementation(
                        validator, TOOLS)
                    captured = io.StringIO()
                    previous = os.getcwd()
                    try:
                        os.chdir(REPOSITORY)
                        with contextlib.redirect_stdout(captured), \
                                contextlib.redirect_stderr(captured):
                            code = implementation.main(command[2:])
                    finally:
                        os.chdir(previous)
                    self.assertEqual(
                        code, int(match.group(1)),
                        "%s: `%s` exited %d\n%s"
                        % (directory.name, " ".join(command),
                           code, captured.getvalue()),
                    )


class ResidualPathSetContract(unittest.TestCase):
    """The configured scan roots form one disjoint case-insensitive set."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_residual_module()

    def test_nested_roots_are_rejected_within_and_across_sets(self):
        cases = (
            (["Accepted", "Accepted/Child"], []),
            (["Accepted"], ["Archive", "Archive/Child"]),
            (["Accepted"], ["Accepted/Archive"]),
            (["Accepted/Current"], ["Accepted"]),
        )
        for allowed, excluded in cases:
            with self.subTest(allowed=allowed, excluded=excluded):
                with self.assertRaisesRegex(ValueError, "overlap"):
                    self.module.validate_path_sets(allowed, excluded)

    def test_disjoint_sibling_roots_are_accepted(self):
        self.assertIsNone(self.module.validate_path_sets(
            ["Notes/Accepted", "Published"],
            ["Notes/Archive", "Scratch"],
        ))

    def test_containment_is_casefolded_before_comparison(self):
        cases = (
            (["Knowledge/Accepted"], ["knowledge/accepted/Archive"]),
            (["Knowledge", "knowledge/Accepted"], []),
        )
        for allowed, excluded in cases:
            with self.subTest(allowed=allowed, excluded=excluded):
                with self.assertRaisesRegex(ValueError, "overlap"):
                    self.module.validate_path_sets(allowed, excluded)


class ResidualScanFixtureContract(unittest.TestCase):
    """Explicit fixture parameters must remain a runnable owned matcher input."""

    def test_explicit_scan_answers_survive_the_matcher_contract(self):
        import tempfile
        module = load_residual_module()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "residual-scan.yaml"
            path.write_text(kblib.canonical_yaml(SCAN_CONFIG), encoding="utf-8")
            config, _fingerprint = module.load_config(str(path))
        pages = (
            "---\ntype: daily-log\n---\n\n# Page\n",
            "# Page\n\n## Daily Log Entry\n\ntext\n",
            "# Page\n\n## Scratch\n\na\n\n## To Sort\n\nb\n",
        )
        for page in pages:
            with self.subTest(page=page):
                self.assertTrue(module.classify(page, config))


if __name__ == "__main__":
    unittest.main()
