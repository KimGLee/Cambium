"""`Tools/README.md` must not drift away from what `Tools/` actually ships.

The check the Card layer already carries is applied to the distribution README:
a code span whose first token is `python3` is the copy-and-run form, so the
named tool must exist and receive every argument it declares as required, and
no span may name a flag its tool does not define. The inventory and schema
lists are checked as set equality against the directory itself.

Only set/existence/equality judgments are made here. Whether a prose sentence
describes a tool's behaviour correctly is a semantic question and stays with
review; nothing in this module restates a rule, a flag list, or a tool
description -- every expectation is derived from the repository bytes.
"""

import ast
import re
import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
README = TOOLS_DIR / "README.md"

sys.path.insert(0, str(TOOLS_DIR))
import stamp_cards  # noqa: E402


COMMAND_PREFIX = "python3"
TOOL_PREFIX = "Tools/"


def shipped_scripts():
    """Every Python module shipped directly under `Tools/`."""
    return sorted(path.name for path in TOOLS_DIR.glob("*.py"))


def shipped_schemas():
    """Every template file shipped under `Tools/schemas/`."""
    return sorted(path.name for path in (TOOLS_DIR / "schemas").iterdir()
                  if path.is_file())


def section(text, heading):
    """Return the body of one H2 section, exclusive of the next H2."""
    marker = "\n## %s\n" % heading
    start = text.index(marker) + len(marker)
    rest = text[start:]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


def tool_option_names(source_text):
    """Every option string the tool's own argparse defines.

    Read statically from the tool source, exactly as `stamp_cards` reads the
    required-argument contract, so the tool stays the sole owner of its
    interface and no flag list is duplicated in a test.
    """
    options = set()
    for node in ast.walk(ast.parse(source_text)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "add_argument":
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and \
                    isinstance(argument.value, str) and \
                    argument.value.startswith("-"):
                options.add(argument.value)
    return options


def fenced_commands(text):
    """Return (line number, command) for `python3 Tools/...` fenced commands.

    Fenced blocks carry the multi-line copy-and-run forms that the inline
    span scan cannot see. Backslash continuations are joined so the whole
    invocation is checked as one command.
    """
    commands = []
    inside = False
    pending = []
    first_line = 0
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            inside = not inside
            pending = []
            continue
        if not inside:
            continue
        if pending:
            pending.append(stripped.rstrip("\\").strip())
            if not stripped.endswith("\\"):
                commands.append((first_line, " ".join(pending)))
                pending = []
            continue
        if not stripped.startswith(COMMAND_PREFIX + " "):
            continue
        tokens = stripped.split()
        if len(tokens) < 2 or not tokens[1].startswith(TOOL_PREFIX):
            continue
        first_line = number
        if stripped.endswith("\\"):
            pending = [stripped.rstrip("\\").strip()]
        else:
            commands.append((number, stripped))
    return commands


def command_option_failures(label, text):
    """Report command spans naming an option their tool does not define."""
    failures = []
    spans = [
        (number, match.group(1))
        for number, line in enumerate(text.splitlines(), 1)
        for match in stamp_cards.CODE_SPAN_RE.finditer(line)
    ]
    for number, command in spans + fenced_commands(text):
        tokens = command.split()
        if len(tokens) < 2 or tokens[0] != COMMAND_PREFIX:
            continue
        script = tokens[1]
        if not script.startswith(TOOL_PREFIX):
            continue
        path = REPO_ROOT / script
        if not path.is_file():
            failures.append("%s:%d names a tool that does not exist: %s"
                            % (label, number, script))
            continue
        defined = tool_option_names(path.read_text(encoding="utf-8"))
        for token in tokens[2:]:
            if not token.startswith("-") or token == "--":
                continue
            flag = token.split("=", 1)[0]
            if flag not in defined:
                failures.append("%s:%d runs %s with an option it does not "
                                "define: %s" % (label, number, script, flag))
    return failures


class ToolsReadmeInventoryTests(unittest.TestCase):
    def setUp(self):
        self.text = README.read_text(encoding="utf-8")

    def test_every_shipped_script_has_an_inventory_row(self):
        rows = set(re.findall(r"^\|\s*`([A-Za-z0-9_]+\.py)`\s*\|",
                              self.text, re.M))

        self.assertEqual(sorted(rows), shipped_scripts())

    def test_every_shipped_script_is_named_in_the_distribution_sentence(self):
        body = self.text.split("The core distribution tools are")[1]
        body = body.split("\n## ")[0]
        named = set(re.findall(r"`([A-Za-z0-9_]+)`", body))

        missing = [name for name in shipped_scripts()
                   if name[: -len(".py")] not in named]

        self.assertEqual(missing, [])

    def test_every_shipped_schema_template_is_listed(self):
        body = section(self.text, "schemas/ templates (the template is the schema doc)")
        listed = set(re.findall(r"^- `([^`]+)`", body, re.M))

        self.assertEqual(sorted(listed), shipped_schemas())

    def test_no_listed_row_names_a_script_that_is_not_shipped(self):
        rows = re.findall(r"^\|\s*`([A-Za-z0-9_]+\.py)`\s*\|", self.text, re.M)

        for name in rows:
            self.assertTrue((TOOLS_DIR / name).is_file(), name)


class ToolsReadmeCommandTests(unittest.TestCase):
    """Every copy-and-run command in the README must satisfy its own tool."""

    documents = (
        "Tools/README.md",
        "README.md",
        "profiles/README.md",
    )

    def test_required_arguments_are_supplied(self):
        for relative in self.documents:
            with self.subTest(document=relative):
                text = (REPO_ROOT / relative).read_text(encoding="utf-8")
                failures = stamp_cards.command_span_failures(
                    relative, text, REPO_ROOT, {}
                )

                self.assertEqual(failures, [])

    def test_no_command_names_an_undefined_option(self):
        for relative in self.documents:
            with self.subTest(document=relative):
                text = (REPO_ROOT / relative).read_text(encoding="utf-8")

                self.assertEqual(command_option_failures(relative, text), [])

    def test_multi_line_fenced_commands_are_scanned(self):
        commands = fenced_commands(README.read_text(encoding="utf-8"))

        self.assertTrue(
            any("--require-maintenance-complete" in command
                and "--watermark-advance-receipt" in command
                for _, command in commands),
            "the joined maintenance-completion command was not recovered",
        )

    def test_an_undefined_option_is_reported_with_its_line(self):
        body = (
            "Intro line.\n"
            "\n"
            "Run `python3 Tools/check_links.py . --not-a-real-flag`.\n"
        )

        failures = command_option_failures("Tools/README.md", body)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("Tools/README.md:3", failures[0])
        self.assertIn("--not-a-real-flag", failures[0])

    def test_an_undefined_option_in_a_fenced_block_is_reported(self):
        body = (
            "```text\n"
            "python3 Tools/check_queue.py . \\\n"
            "  --not-a-real-flag VALUE\n"
            "```\n"
        )

        failures = command_option_failures("Tools/README.md", body)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("--not-a-real-flag", failures[0])

    def test_prose_mention_of_a_tool_is_not_scanned(self):
        body = "Consume a current `Tools/check_queue.py` receipt.\n"

        self.assertEqual(command_option_failures("Tools/README.md", body), [])
        self.assertEqual(
            stamp_cards.command_span_failures(
                "Tools/README.md", body, REPO_ROOT, {}
            ),
            [],
        )

    def test_scan_is_deterministic_for_the_same_bytes(self):
        text = README.read_text(encoding="utf-8")

        self.assertEqual(
            command_option_failures("Tools/README.md", text),
            command_option_failures("Tools/README.md", text),
        )


if __name__ == "__main__":
    unittest.main()
