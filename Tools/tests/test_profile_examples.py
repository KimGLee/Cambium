"""Re-validate every published profile example against the current tools.

`profiles/examples/*` are non-normative reference cases, but nothing else in
the distribution re-checks them: `check_profile.py` is not a registered gate,
the examples are not in any Card's `source_files`, and the public repository is
intentionally uninstantiated, so there is no `standards_version` for an example
to bind to.  An interface, kernel, or tool change can therefore leave a
published example stale while every deterministic check stays green.

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

import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
EXAMPLES = REPOSITORY / "profiles" / "examples"
TOOLS = REPOSITORY / "Tools"
PROVENANCE_HEADING = "Validation Provenance"
EXPECTED_COLUMNS = ("Validator", "Tool version", "Command", "Expected result")


def example_directories():
    """Every published example package, identified by its manifest."""
    return sorted(
        path.parent for path in EXAMPLES.glob("*/profile.md")
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
    """Read TOOL_VERSION out of Tools/<name>.py without importing its deps."""
    source = (TOOLS / ("%s.py" % name)).read_text(encoding="utf-8")
    match = re.search(r"^TOOL_VERSION = \"([^\"]+)\"$", source, re.M)
    return match.group(1) if match else None


class ProfileExampleProvenance(unittest.TestCase):
    def test_examples_exist(self):
        self.assertTrue(
            example_directories(),
            "profiles/examples/ has no package with a profile.md; a validation "
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
                command = unbacktick(row["Command"]).split()
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
                    completed = subprocess.run(
                        [sys.executable] + command[1:],
                        cwd=str(REPOSITORY), capture_output=True, text=True)
                    self.assertEqual(
                        completed.returncode, int(match.group(1)),
                        "%s: `%s` exited %d\n%s%s"
                        % (directory.name, " ".join(command),
                           completed.returncode, completed.stdout,
                           completed.stderr),
                    )


class TemplateScaffold(unittest.TestCase):
    """The scaffolding an adopter copies must stay complete and unfilled."""

    TEMPLATE = REPOSITORY / "profiles" / "_template"

    def test_template_ships_a_scan_config_scaffold(self):
        scaffold = self.TEMPLATE / "scan-configs" / "residual-scan.yaml"
        self.assertTrue(
            scaffold.is_file(),
            "the Registered Scan Registry slot is Required, so _template must "
            "ship the profile-owned scan configuration it tells adopters to "
            "fill; without it a copied profile passes check_profile.py with no "
            "runnable verifier",
        )
        text = scaffold.read_text(encoding="utf-8")
        self.assertIn(
            "TODO(profile)", text,
            "the scaffold must retain the unfilled sentinel so check_profile.py "
            "fails until the adopter fills it",
        )
        self.assertIn(
            "scan-configs/residual-scan.yaml",
            (self.TEMPLATE / "registries" / "registered-scans.md")
            .read_text(encoding="utf-8"),
            "the Registered Scan Registry template must name the exact scaffold "
            "path, not just 'copy it into the filled profile'",
        )

    def test_filled_scaffold_shape_survives_the_matcher_contract(self):
        """A faithfully filled scaffold must load and be able to fire."""
        spec = importlib.util.spec_from_file_location(
            "_residual_scan_under_test", TOOLS / "check_residual_content.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        scaffold = (self.TEMPLATE / "scan-configs" / "residual-scan.yaml"
                    ).read_text(encoding="utf-8")
        answers = iter(["Accepted Root", "accepted-type", "Accepted Heading",
                        "Weak One", "Weak Two"])
        # An adopter replaces the sentinels that carry values; the ones inside
        # comments go away with the comment.
        filled = "\n".join(
            line if line.lstrip().startswith("#")
            else re.sub(r"TODO\(profile\)", lambda _m: next(answers), line)
            for line in scaffold.splitlines()
        )
        self.assertEqual(
            list(answers), [],
            "the scaffold's value sentinels no longer match this test's answer "
            "set; update both together",
        )

        with self.subTest("loads"):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "residual-scan.yaml"
                path.write_text(filled, encoding="utf-8")
                config, _fingerprint = module.load_config(str(path))
        with self.subTest("can fire"):
            page = "---\ntype: accepted-type\n---\n\n# Page\n"
            self.assertTrue(
                module.classify(page, config),
                "a page carrying the filled scaffold's own frontmatter value "
                "must be recognised, or the configuration is inert and "
                "check_residual_content.py fails the run",
            )
            headings = "# Page\n\n## Accepted Heading\n\ntext\n"
            self.assertTrue(module.classify(headings, config))
            combination = "# Page\n\n## Weak One\n\na\n\n## Weak Two\n\nb\n"
            self.assertTrue(module.classify(combination, config))


if __name__ == "__main__":
    unittest.main()
