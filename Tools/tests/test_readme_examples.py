"""Link targets and executable interface names used by the usage guides.

``Tools/README.md`` is navigation and an operator guide, not an inventory of
every implementation module. These tests therefore check only properties that
can be derived from repository bytes: local link targets and copyable
``python3 Tools/...`` command shapes. Document length, headings, wording and
which tools to demonstrate are not machine contracts.

The command scan captures each public adapter's real ``argparse`` declaration
through its registered implementation edge. Capture stops at ``parse_args``;
it does not execute Tool behaviour or maintain a second option inventory.
"""

import re
import shlex
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
README = TOOLS_DIR / "README.md"

sys.path.insert(0, str(REPO_ROOT))
import Tools.platform.agent_interface.entrypoint_loader as entrypoint_loader  # noqa: E402

COMMAND_PREFIX = "python3"
TOOL_PREFIX = "Tools/"
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
LINK_RE = re.compile(r"\]\((<[^>]+>|[^)\s]+)\)")


def markdown_targets(text):
    """Return decoded Markdown link targets, retaining repository paths."""
    targets = set()
    for match in LINK_RE.finditer(text):
        target = match.group(1)
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        target = unquote(target.split("#", 1)[0])
        if target:
            targets.add(target)
    return targets


def fenced_commands(text):
    """Return ``(line, command)`` for direct commands in fenced blocks."""
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
        if not stripped.startswith(COMMAND_PREFIX + " " + TOOL_PREFIX):
            continue
        first_line = number
        if stripped.endswith("\\"):
            pending = [stripped.rstrip("\\").strip()]
        else:
            commands.append((number, stripped))
    return commands


def inline_commands(text):
    """Return direct Tool commands carried in inline code spans."""
    commands = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in CODE_SPAN_RE.finditer(line):
            command = match.group(1).strip()
            if command.startswith(COMMAND_PREFIX + " " + TOOL_PREFIX):
                commands.append((number, command))
    return commands


def documented_commands(text):
    return inline_commands(text) + fenced_commands(text)


def command_tokens(command):
    """Split a documented command without invoking a shell."""
    try:
        return shlex.split(command)
    except ValueError as exc:
        raise AssertionError("documented command cannot be parsed: %s" % command) from exc


def tool_option_names(script_path):
    """Return options from the public adapter's unique real parser."""
    parser = entrypoint_loader.capture_argument_parser(
        script_path.stem, TOOLS_DIR)
    return {
        option
        for action in parser._actions  # argparse has no public action iterator
        for option in action.option_strings
    }


def command_failures(label, text):
    """Report missing scripts and options absent from their local parser."""
    failures = []
    for number, command in documented_commands(text):
        tokens = command_tokens(command)
        if len(tokens) < 2:
            failures.append("%s:%d has an incomplete command" % (label, number))
            continue
        script = tokens[1]
        path = REPO_ROOT / script
        if not script.startswith(TOOL_PREFIX) or not path.is_file():
            failures.append(
                "%s:%d names a tool that does not exist: %s"
                % (label, number, script)
            )
            continue
        defined = tool_option_names(path)
        after_double_dash = False
        for token in tokens[2:]:
            if token == "--":
                after_double_dash = True
                continue
            if after_double_dash or not token.startswith("-"):
                continue
            if re.fullmatch(r"-\d+(?:\.\d+)?", token):
                continue
            option = token.split("=", 1)[0]
            if option not in defined:
                failures.append(
                    "%s:%d runs %s with an option it does not define: %s"
                    % (label, number, script, option)
                )
    return failures


class ToolsReadmeLinkTests(unittest.TestCase):
    def test_every_local_readme_link_resolves(self):
        # check_links owns wiki links, not these ordinary Markdown targets.
        for target in markdown_targets(README.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            with self.subTest(target=target):
                self.assertTrue((TOOLS_DIR / target).exists(), target)


class ToolsReadmeCommandTests(unittest.TestCase):
    """Public command examples must agree with local ``argparse`` bytes."""

    documents = (
        "Tools/README.md",
        "README.md",
        "profiles/README.md",
    )

    def test_documented_scripts_and_options_exist(self):
        for relative in self.documents:
            with self.subTest(document=relative):
                text = (REPO_ROOT / relative).read_text(encoding="utf-8")
                self.assertEqual(command_failures(relative, text), [])

    def test_fenced_continuations_are_joined(self):
        body = (
            "```text\n"
            "python3 Tools/check_queue.py . \\\n"
            "  --resume-status\n"
            "```\n"
        )
        self.assertEqual(
            fenced_commands(body),
            [(2, "python3 Tools/check_queue.py . --resume-status")],
        )

    def test_missing_script_is_reported_with_line(self):
        body = "Run `python3 Tools/not_shipped.py .`.\n"
        failures = command_failures("Tools/README.md", body)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("Tools/README.md:1", failures[0])

    def test_undefined_option_is_reported_with_line(self):
        body = "Run `python3 Tools/check_queue.py . --not-a-real-flag`.\n"
        failures = command_failures("Tools/README.md", body)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("Tools/README.md:1", failures[0])
        self.assertIn("--not-a-real-flag", failures[0])

    def test_prose_tool_link_is_not_treated_as_a_command(self):
        body = "Use [`check_queue.py`](../Tools/check_queue.py).\n"
        self.assertEqual(command_failures("Tools/README.md", body), [])


if __name__ == "__main__":
    unittest.main()
