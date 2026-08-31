"""Ownership tests for the CLI-contract -> agent-interface projection.

The compiled CLI contract owns the tool and argument surface. This suite
tests the projection relation without copying the shipped JSON back into a
second expected dictionary. Pure mapping rules stay in-process; filesystem
lifecycle tests start from a minimal contract checkpoint; one test alone owns
the public CLI transport.
"""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
SCRIPT = TOOLS_DIR / "render_interface_projection.py"

sys.path.insert(0, str(TOOLS_DIR))
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.platform.agent_interface.compile_cli_contract as cli_owner  # noqa: E402
import Tools.platform.agent_interface.render_interface_projection as projector  # noqa: E402
import Tools.platform.agent_interface.tool_availability as tool_availability  # noqa: E402


_CURRENT_CONTRACT = None


def current_contract():
    """Compile the current machine owners once; never copy their shape here."""
    global _CURRENT_CONTRACT
    if _CURRENT_CONTRACT is None:
        _CURRENT_CONTRACT = cli_owner.compile_contract(
            REPO_ROOT, tool_availability.SOURCE_DISTRIBUTION)
    return _CURRENT_CONTRACT


def run_in_process(*arguments):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = projector.main(list(arguments))
        except SystemExit as exc:
            code = int(exc.code)
    return SimpleNamespace(
        returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def run_cli(*arguments):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, arguments)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        env=environment, check=False)


def argument(**overrides):
    owner_argument = next(
        item
        for record in current_contract()["tools"]
        for item in record["arguments"]
    )
    value = {key: None for key in owner_argument}
    value.update({
        "dest": "sample",
        "option_strings": ["--sample"],
        "required": False,
        "default": None,
        "default_type": "NoneType",
        "choices": None,
        "nargs": None,
        "action": "store",
        "type": None,
        "help": None,
    })
    value.update(overrides)
    return value


def tool_record(name="sample", exposure="mcp", arguments=None,
                value_arguments=None, path_arguments=None, description=None,
                groups=None):
    if arguments is None:
        arguments = [argument(
            dest="root", option_strings=[], required=True, help="workspace")]
    record = deepcopy(next(
        row for row in current_contract()["tools"]
        if row["agent_interface"]["exposure"] == "mcp"))
    interface = deepcopy(record["agent_interface"])
    interface.update({
        "exposure": exposure,
        "workspace_argument": "root" if arguments else None,
        "workspace_access": "read" if arguments else None,
        "value_arguments": list(value_arguments or []),
        "path_arguments": list(path_arguments or []),
        "external_write": "none",
    })
    record.update({
        "tool": name,
        "module": "Tools/%s.py" % name,
        "source_hash": kblib.sha256_bytes(name.encode("utf-8")),
        "description": description,
        "arguments": arguments,
        "mutually_exclusive_groups": groups or [],
        "receipt_extensions": [],
        "receipt_extensions_extraction": "complete",
        "receipt_extension_sources": [],
        "agent_interface": interface,
    })
    return record


def fixture_contract(**overrides):
    tools = overrides.pop("tools", None) or [tool_record(description="fixture")]
    value = deepcopy(current_contract())
    value.update({
        "source_hash": kblib.sha256_bytes(b"fixture manifest"),
        "included_tools": [record["tool"] for record in tools],
        "excluded_tools": [],
        "tool_count": len(tools),
        "tools": tools,
    })
    value.update(overrides)
    return value


def write_contract(root, contract):
    relative = projector.contract_for_projection_target(
        contract["projection_target"])
    path = Path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(kblib.canonical_yaml(contract), encoding="utf-8")
    return path


@contextmanager
def temporary_repository(contract=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_contract(root, contract or fixture_contract())
        yield root


class CurrentContractProjectionTests(unittest.TestCase):
    """Contract: the current owner closes over the complete projection."""

    @classmethod
    def setUpClass(cls):
        cls.contract = current_contract()
        cls.raw = cli_owner.render(cls.contract).encode("utf-8")
        cls.artifact = projector.build_mcp(
            "mcp", cls.contract, kblib.sha256_bytes(cls.raw),
            projector.DEFAULT_CONTRACT)

    def test_current_contract_closes_over_tools_arguments_and_capabilities(self):
        records = [
            record for record in self.contract["tools"]
            if record["agent_interface"]["exposure"] == "mcp"
        ]
        self.assertEqual(
            [item["name"] for item in self.artifact["tools"]],
            [record["tool"] for record in records])
        self.assertEqual(self.artifact["tool_count"], len(records))

        for record, item in zip(records, self.artifact["tools"]):
            policy = record["agent_interface"]
            properties = item["inputSchema"]["properties"]
            with self.subTest(tool=record["tool"]):
                self.assertEqual(
                    set(properties),
                    {entry["dest"] for entry in record["arguments"]})
                self.assertEqual(
                    item[projector.WORKSPACE_EXTENSION_KEY],
                    {"argument": policy["workspace_argument"],
                     "access": policy["workspace_access"]})
                expected_paths = {
                    entry["argument"]: {
                        key: deepcopy(value)
                        for key, value in entry.items()
                        if key not in {"argument", "runtime_path_id"}
                    }
                    for entry in policy["path_arguments"]
                }
                actual_paths = {
                    name: schema[projector.PATH_EXTENSION_KEY]
                    for name, schema in properties.items()
                    if projector.PATH_EXTENSION_KEY in schema
                }
                self.assertEqual(actual_paths, expected_paths)

    def test_envelope_binds_owner_bytes_and_has_no_unowned_fields(self):
        self.assertEqual(
            self.artifact["source_hash"], kblib.sha256_bytes(self.raw))
        self.assertEqual(
            self.artifact["source_manifest_hash"],
            self.contract["source_hash"])
        self.assertEqual(
            self.artifact["transports"], list(projector.MCP_TRANSPORTS))
        self.assertEqual(projector.unbound_field_paths(self.artifact), [])
        self.assertEqual(
            projector.render(self.artifact),
            projector.render(projector.build_mcp(
                "mcp", self.contract, kblib.sha256_bytes(self.raw),
                projector.DEFAULT_CONTRACT)))


class ArgumentProjectionTests(unittest.TestCase):
    """Unit: one table owns argparse-to-JSON-Schema shape semantics."""

    def test_argument_shape_matrix(self):
        cases = (
            ("default-string", {}, {"type": "string"}, ()),
            ("custom-converter", {"type": "positive_int"},
             {"type": "string"}, ()),
            ("count", {"action": "count"}, {"type": "integer"}, ()),
            ("presence-flag", {"action": "store_true", "nargs": 0},
             {"type": "boolean"}, ()),
            ("append", {"action": "append", "type": "int"},
             {"type": "array", "items": {"type": "integer"}}, ()),
            ("one-or-more", {"nargs": "+"},
             {"type": "array", "items": {"type": "string"},
              "minItems": 1}, ("maxItems",)),
            ("fixed-count", {"nargs": 2},
             {"type": "array", "items": {"type": "string"},
              "minItems": 2, "maxItems": 2}, ()),
            ("choices", {"choices": ["a", "b"]},
             {"type": "string", "enum": ["a", "b"]}, ()),
            ("suppressed-default",
             {"default": "==SUPPRESS==",
              "default_type": "argparse.SUPPRESS"},
             {"type": "string"}, ("default",)),
        )
        for name, changes, expected, absent in cases:
            with self.subTest(case=name):
                schema = projector.property_schema(argument(**changes))
                for key, value in expected.items():
                    self.assertEqual(schema[key], value)
                for key in absent:
                    self.assertNotIn(key, schema)
                if changes.get("type") == "positive_int":
                    self.assertEqual(
                        schema[projector.CLI_EXTENSION_KEY]["type"],
                        "positive_int")

    def test_record_schema_preserves_closed_classification_not_owner_ids(self):
        path = argument(dest="target", option_strings=["--target"])
        mode = argument(dest="mode", option_strings=["--mode"],
                        choices=["read", "write"])
        capability = deepcopy(next(
            item
            for record in current_contract()["tools"]
            for item in record["agent_interface"]["path_arguments"]
        ))
        capability.update({
            "argument": "target", "access": "read",
            "consumption": "snapshot", "constraint": "exact",
            "value": ".cambium/derived/target.yaml",
            "runtime_path_id": "target-artifact",
            "suffixes": [], "active_when_any": [],
            "inactive_when_any": [],
        })
        record = tool_record(
            arguments=[argument(dest="root", option_strings=[], required=True),
                       mode, path],
            value_arguments=["mode"], path_arguments=[capability],
            groups=[{"required": False, "dests": ["mode", "target"]}])

        projected = projector.mcp_tool(record)
        schema = projected["inputSchema"]

        self.assertEqual(set(schema["properties"]), {"root", "mode", "target"})
        self.assertEqual(schema["required"], ["root"])
        self.assertFalse(schema["additionalProperties"])
        path_projection = schema["properties"]["target"][
            projector.PATH_EXTENSION_KEY]
        self.assertNotIn("runtime_path_id", path_projection)
        self.assertEqual(
            path_projection,
            {key: value for key, value in capability.items()
             if key not in {"argument", "runtime_path_id"}})
        self.assertEqual(
            projected[projector.EXCLUSIVE_EXTENSION_KEY][0]["dests"],
            ["mode", "target"])


class InterfaceProjectionContractInputTests(unittest.TestCase):
    """Contract: upstream bytes are accepted or rejected as a closed shape."""

    def test_contract_validation_matrix(self):
        cases = []

        foreign = fixture_contract(artifact="other")
        cases.append(("foreign-artifact", foreign, "not the"))
        schema = fixture_contract(
            schema_version=projector.UPSTREAM_SCHEMA_VERSION + 1)
        cases.append(("schema-version", schema, "schema_version"))
        open_contract = fixture_contract(retired_field={})
        cases.append(("open-contract", open_contract, "closed schema_version"))
        open_policy = fixture_contract()
        open_policy["tools"][0]["agent_interface"]["invented"] = True
        cases.append(("open-policy", open_policy, "closed agent-interface"))
        unclassified = fixture_contract()
        unclassified["tools"][0]["arguments"].append(
            argument(dest="extra", option_strings=["--extra"]))
        cases.append(("unclassified-argument", unclassified, "do not close"))

        for name, contract, message in cases:
            with self.subTest(case=name), temporary_repository(contract) as root:
                path = root / projector.DEFAULT_CONTRACT
                with self.assertRaisesRegex(projector.ProjectionError, message):
                    projector.read_contract(path)

class InterfaceProjectionLifecycleTests(unittest.TestCase):
    """Integration: adjacent contract, renderer, artifact and check seams."""

    def test_write_check_and_stale_classification(self):
        with temporary_repository() as root:
            output = root / projector.FORMS["mcp"]["output"]
            self.assertEqual(run_in_process(str(root), "--form", "mcp").returncode, 0)
            self.assertEqual(
                run_in_process(str(root), "--form", "mcp", "--check").returncode,
                0)

            output.write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                run_in_process(str(root), "--form", "mcp", "--check").returncode,
                2)

            self.assertEqual(run_in_process(str(root), "--form", "mcp").returncode, 0)
            contract = fixture_contract(
                source_hash=kblib.sha256_bytes(b"later manifest"))
            write_contract(root, contract)
            self.assertEqual(
                run_in_process(str(root), "--form", "mcp", "--check").returncode,
                2)

    def test_projection_target_registry_controls_input_and_output(self):
        carried = fixture_contract(
            projection_target=tool_availability.CARRIED_RUNTIME)
        with temporary_repository(carried) as root:
            result = run_in_process(
                str(root), "--form", "mcp", "--projection-target",
                tool_availability.CARRIED_RUNTIME)
            runtime_output = root / projector.FORMS["mcp"]["runtime_output"]
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(runtime_output.is_file())
            self.assertFalse((root / projector.FORMS["mcp"]["output"]).exists())

            alternate = root / "alternate.yaml"
            alternate.write_text(kblib.canonical_yaml(carried), encoding="utf-8")
            result = run_in_process(
                str(root), "--form", "mcp", "--projection-target",
                tool_availability.CARRIED_RUNTIME, "--contract", str(alternate))
            self.assertEqual(result.returncode, 1)

            result = run_in_process(
                str(root), "--form", "mcp", "--projection-target",
                tool_availability.CARRIED_RUNTIME, "--output",
                str(root / projector.FORMS["mcp"]["output"]))
            self.assertEqual(result.returncode, 1)

    def test_registered_forms_are_the_complete_default_and_selection_boundary(self):
        second = "Tools/compiled/fixture-form.json"
        projector.FORMS["fixture"] = {
            "output": second,
            "runtime_output": ".cambium/derived/interfaces/fixture.json",
            "build": projector.build_envelope,
            "summary": "fixture form",
        }
        self.addCleanup(projector.FORMS.pop, "fixture", None)

        with temporary_repository() as root:
            self.assertEqual(run_in_process(str(root)).returncode, 0)
            for form in projector.FORMS.values():
                self.assertTrue((root / form["output"]).is_file())
            self.assertEqual(run_in_process(str(root), "--check").returncode, 0)

            (root / second).unlink()
            self.assertEqual(run_in_process(str(root), "--check").returncode, 2)
            self.assertEqual(
                run_in_process(str(root), "--form", "mcp").returncode, 0)


class InterfaceProjectionSlowTests(unittest.TestCase):
    def test_upstream_change_during_projection_has_no_verdict(self):
        original = projector.read_contract

        def moving_target(path):
            contract, digest = original(path)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("\n# concurrent recompilation\n")
            return contract, digest

        projector.read_contract = moving_target
        self.addCleanup(setattr, projector, "read_contract", original)

        with temporary_repository() as root:
            result = run_in_process(str(root), "--form", "mcp", "--check")
        self.assertEqual(result.returncode, 1)


class InterfaceProjectionTransportTests(unittest.TestCase):
    def test_public_cli_writes_registered_projection(self):
        with temporary_repository() as root:
            result = run_cli(str(root), "--form", "mcp")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifact = json.loads(
                (root / projector.FORMS["mcp"]["output"]).read_text(
                    encoding="utf-8"))
            self.assertEqual(artifact["artifact"], projector.ARTIFACT_KIND)


if __name__ == "__main__":
    unittest.main()
