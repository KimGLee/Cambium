"""Mechanical checks for the Tool usage guide.

``Tools/README.md`` is navigation and an operator guide, not an inventory of
every implementation module. These tests therefore check only properties that
can be derived from repository bytes: local link targets, named machine
contracts, and copyable ``python3 Tools/...`` command shapes.

The command scan reads each script's ``argparse`` declarations with ``ast``.
It never imports a Cambium module and does not depend on ``stamp_cards`` or any
other runtime parser.
"""

import ast
import re
import shlex
import unittest
from pathlib import Path
from urllib.parse import unquote


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
README = TOOLS_DIR / "README.md"

COMMAND_PREFIX = "python3"
TOOL_PREFIX = "Tools/"
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
LINK_RE = re.compile(r"\]\((<[^>]+>|[^)\s]+)\)")

MACHINE_NAVIGATION = {
    line for line in """../distribution-boundary.yaml
../kernel/K00 Standards Control/profile-interface.yaml
../kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml
../kernel/K12 Quality Assurance/batch-close-closed-list.yaml
schemas/card.schema.yaml
../Card/card-budget.yaml
../Read Set/read-set.schema.yaml
operation-capabilities.yaml
scan-capabilities.yaml
agent-interface-policy.yaml
runtime_paths.py
corpus_planning_contract.py
read_set_contract.py
profile_contract.py
profile_admission.py
check_profile.py
batch_close_contract.py
module-boundaries.yaml
module_boundary_facts.py
module_boundary_report.py
kernel-size-policy.yaml
kernel-size-exceptions.md
check_kernel_size.py
check_upstream_components.py
upstream_component_boundary.py
upstream_identity.py
schemas/
compiled/""".splitlines()
}

USER_ENTRY_POINTS = set("""run_gates.py
stamp_cards.py
check_kernel_size.py
check_upstream_components.py
scaffold_profile.py
check_profile.py
apply_profile_adoption.py
adopt_standards.py
init_state.py
apply_task_plan.py
check_queue.py
metadata_execution_contract.py
compile_cli_contract.py
render_interface_projection.py
render_host_configs.py
seal_receipts.py
module_boundary_report.py""".splitlines())

OBSOLETE_RESPONSIBILITY_CLAIMS = (
    "kernel/" + "Cards",
    "kernel/" + "Read Sets",
    "compiled" + " Card",
    "compiled" + "-Card",
    "K00/" + "14",
    "K00/" + "15",
    "K00/" + "16",
    "K00/" + "18",
)


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


def tool_option_names(source_text):
    """Return literal option strings declared through ``add_argument``."""
    options = {"-h", "--help"}  # argparse supplies these by default.
    for node in ast.walk(ast.parse(source_text)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "add_argument":
            continue
        for argument in node.args:
            if not isinstance(argument, ast.Constant):
                continue
            value = argument.value
            if isinstance(value, str) and value.startswith("-"):
                options.add(value)
    return options


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
        defined = tool_option_names(path.read_text(encoding="utf-8"))
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


class ToolsReadmeResponsibilityTests(unittest.TestCase):
    def setUp(self):
        self.text = README.read_text(encoding="utf-8")

    def test_readme_is_a_bounded_guide_not_a_full_module_inventory(self):
        self.assertLessEqual(len(self.text.encode("utf-8")), 24000)
        self.assertLessEqual(len(self.text.splitlines()), 360)
        self.assertNotIn("## Tool inventory", self.text)
        self.assertNotIn("The core distribution tools are", self.text)

    def test_obsolete_component_locations_and_kernel_registers_are_absent(self):
        for claim in OBSOLETE_RESPONSIBILITY_CLAIMS:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, self.text)

    def test_required_machine_contract_navigation_is_present_and_resolves(self):
        targets = markdown_targets(self.text)
        self.assertEqual(sorted(MACHINE_NAVIGATION - targets), [])
        for target in MACHINE_NAVIGATION:
            with self.subTest(target=target):
                self.assertTrue((TOOLS_DIR / target).exists(), target)

    def test_every_local_readme_link_resolves(self):
        for target in markdown_targets(self.text):
            if "://" in target or target.startswith("#"):
                continue
            with self.subTest(target=target):
                self.assertTrue((TOOLS_DIR / target).exists(), target)

    def test_operator_entry_points_are_demonstrated_without_exhaustive_inventory(self):
        scripts = {
            Path(command_tokens(command)[1]).name
            for _, command in documented_commands(self.text)
        }
        self.assertEqual(sorted(USER_ENTRY_POINTS - scripts), [])


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

    def test_scan_is_deterministic_for_the_same_bytes(self):
        text = README.read_text(encoding="utf-8")
        self.assertEqual(
            command_failures("Tools/README.md", text),
            command_failures("Tools/README.md", text),
        )


if __name__ == "__main__":
    unittest.main()
