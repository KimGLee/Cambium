"""The agent-facing form projections and the generator that derives them.

These cover the properties the artifact is only useful for having: that every
value in it is a projection of `Tools/compiled/cli-contract.yaml` rather than a
second declaration of the same interface, that two runs agree byte for byte
across hash seeds, that `--check` separates a stale artifact (2, a HOLD) from
unreliable evidence (1), that the upstream binding is a fingerprint of the
bytes actually read, and that a field with no declaration source cannot reach
the artifact at all.

No flag, default, help string, or transport name is restated here. Every
expectation is read either from the repository's own compiled contract or from
a fixture built inside the test, so this file cannot drift into a second
declaration of the projection.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
SCRIPT = TOOLS_DIR / "render_interface_projection.py"

sys.path.insert(0, str(TOOLS_DIR))
import kblib  # noqa: E402
import render_interface_projection as projector  # noqa: E402
import tool_availability  # noqa: E402

CONTRACT = REPO_ROOT / projector.DEFAULT_CONTRACT
MCP_ARTIFACT = REPO_ROOT / projector.FORMS["mcp"]["output"]


def run(*arguments, env=None):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(arguments),
        capture_output=True, text=True, env=environment,
        cwd=str(REPO_ROOT), check=False)


def shipped_contract():
    return kblib.parse_yaml_subset(CONTRACT.read_text(encoding="utf-8"))


def fixture_contract(**overrides):
    """One minimal compiled contract, owned entirely by this test file."""
    data = {
        "schema_version": projector.UPSTREAM_SCHEMA_VERSION,
        "artifact": projector.UPSTREAM_ARTIFACT,
        "projection_target": tool_availability.SOURCE_DISTRIBUTION,
        "source_hash": kblib.sha256_bytes(b"fixture manifest"),
        "component_path_registries": {},
        "tool_count": 1,
        "tools": [{
            "tool": "sample",
            "module": "Tools/sample.py",
            "source_hash": kblib.sha256_bytes(b"fixture source"),
            "description": "A fixture tool",
            "arguments": [{
                "dest": "root", "option_strings": [], "required": True,
                "default": None, "default_type": "NoneType",
                "choices": None, "nargs": None, "action": "store",
                "type": None, "help": "where to look",
            }],
            "mutually_exclusive_groups": [],
            "receipt_extensions": [],
            "receipt_extensions_extraction": "complete",
            "agent_interface": {
                "exposure": "mcp",
                "workspace_argument": "root",
                "workspace_access": "read",
                "value_arguments": [],
                "path_arguments": [],
                "external_write": "none",
            },
        }],
    }
    data.update(overrides)
    return data


class ShippedArtifactTests(unittest.TestCase):
    """The artifacts in the tree must be what the contract currently states."""

    def setUp(self):
        self.artifact = json.loads(MCP_ARTIFACT.read_text(encoding="utf-8"))
        self.contract = shipped_contract()

    def test_check_accepts_the_shipped_artifacts(self):
        result = run(".", "--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_registered_form_ships_its_artifact(self):
        for name, form in projector.FORMS.items():
            with self.subTest(form=name):
                self.assertTrue((REPO_ROOT / form["output"]).is_file())

    def test_every_contracted_tool_is_projected_under_its_own_name(self):
        expected = [
            record["tool"] for record in self.contract["tools"]
            if record["agent_interface"]["exposure"] == "mcp"
        ]

        self.assertEqual([tool["name"] for tool in self.artifact["tools"]],
                         expected)
        self.assertEqual(self.artifact["tool_count"], len(expected))

    def test_cli_only_operations_do_not_enter_the_mcp_surface(self):
        cli_only = {
            record["tool"] for record in self.contract["tools"]
            if record["agent_interface"]["exposure"] == "cli-only"
        }
        projected = {tool["name"] for tool in self.artifact["tools"]}

        self.assertTrue(cli_only)
        self.assertTrue({
            "adopt_standards",
            "apply_profile_adoption",
            "stamp_cards",
        }.issubset(cli_only))
        self.assertEqual(cli_only & projected, set())

    def test_every_projected_tool_carries_workspace_and_path_capabilities(self):
        contracted = {record["tool"]: record for record in
                      self.contract["tools"]}
        for tool in self.artifact["tools"]:
            policy = contracted[tool["name"]]["agent_interface"]
            with self.subTest(tool=tool["name"]):
                self.assertEqual(
                    tool[projector.WORKSPACE_EXTENSION_KEY],
                    {"argument": policy["workspace_argument"],
                     "access": policy["workspace_access"]})
                expected = {
                    item["argument"]: {
                        "access": item["access"],
                        "consumption": item["consumption"],
                        "constraint": item["constraint"],
                        "value": item["value"],
                        "suffixes": item["suffixes"],
                        "active_when_any": item["active_when_any"],
                        "inactive_when_any": item["inactive_when_any"],
                    }
                    for item in policy["path_arguments"]
                }
                actual = {}
                for name, schema in tool["inputSchema"]["properties"].items():
                    if projector.PATH_EXTENSION_KEY in schema:
                        actual[name] = schema[projector.PATH_EXTENSION_KEY]
                self.assertEqual(actual, expected)

    def test_receipts_and_registered_selectors_are_narrower_than_containment(self):
        by_name = {tool["name"]: tool for tool in self.artifact["tools"]}
        for tool in self.artifact["tools"]:
            receipts = tool["inputSchema"]["properties"].get("receipts")
            if receipts is None:
                continue
            with self.subTest(tool=tool["name"], argument="receipts"):
                capability = receipts[projector.PATH_EXTENSION_KEY]
                self.assertEqual(capability["access"], "write")
                self.assertEqual(capability["consumption"], "append")
                self.assertIn(
                    capability["constraint"], ("namespace", "exact"))
                if capability["constraint"] == "namespace":
                    self.assertEqual(
                        capability["value"], ".cambium/receipts")
                    self.assertEqual(capability["suffixes"], [".jsonl"])
                else:
                    self.assertTrue(capability["value"].startswith(
                        ".cambium/receipts/"))
                    self.assertTrue(capability["value"].endswith(".jsonl"))
                    self.assertEqual(capability["suffixes"], [])
        exact = {
            ("check_vocab", "vocab"): ".cambium/derived/vocab.yaml",
            ("check_proof", "template"):
                "Tools/schemas/terminal_proof.template.yaml",
        }
        for (tool_name, argument), value in exact.items():
            with self.subTest(tool=tool_name, argument=argument):
                capability = by_name[tool_name]["inputSchema"][
                    "properties"][argument][projector.PATH_EXTENSION_KEY]
                self.assertEqual(capability["constraint"], "exact")
                self.assertEqual(capability["value"], value)

    def test_the_upstream_binding_is_the_bytes_that_were_read(self):
        self.assertEqual(self.artifact["source_hash"],
                         kblib.sha256_bytes(CONTRACT.read_bytes()))
        self.assertEqual(self.artifact["source_manifest_hash"],
                         self.contract["source_hash"])

    def test_each_property_carries_its_argument_declaration_verbatim(self):
        contracted = {record["tool"]: record for record in
                      self.contract["tools"]}
        for tool in self.artifact["tools"]:
            record = contracted[tool["name"]]
            properties = tool["inputSchema"]["properties"]
            with self.subTest(tool=tool["name"]):
                self.assertEqual(
                    sorted(properties),
                    sorted(argument["dest"] for argument in
                           record["arguments"]))
                for argument in record["arguments"]:
                    schema = properties[argument["dest"]]
                    extension = schema[projector.CLI_EXTENSION_KEY]
                    self.assertEqual(extension["option_strings"],
                                     argument["option_strings"])
                    self.assertEqual(extension["action"], argument["action"])

    def test_required_is_exactly_what_argparse_marks_required(self):
        contracted = {record["tool"]: record for record in
                      self.contract["tools"]}
        for tool in self.artifact["tools"]:
            record = contracted[tool["name"]]
            expected = [argument["dest"] for argument in record["arguments"]
                        if argument["required"]]
            with self.subTest(tool=tool["name"]):
                self.assertEqual(tool["inputSchema"].get("required", []),
                                 expected)

    def test_declared_choices_become_the_enum(self):
        contracted = {record["tool"]: record for record in
                      self.contract["tools"]}
        seen = 0
        for tool in self.artifact["tools"]:
            record = contracted[tool["name"]]
            for argument in record["arguments"]:
                if not argument["choices"]:
                    continue
                schema = tool["inputSchema"]["properties"][argument["dest"]]
                carrier = schema.get("items", schema)
                with self.subTest(tool=tool["name"], dest=argument["dest"]):
                    self.assertEqual(carrier["enum"], argument["choices"])
                seen += 1
        self.assertTrue(seen, "no shipped tool declares choices")

    def test_a_tool_with_no_declared_description_omits_the_key(self):
        contracted = {record["tool"]: record for record in
                      self.contract["tools"]}
        for tool in self.artifact["tools"]:
            record = contracted[tool["name"]]
            with self.subTest(tool=tool["name"]):
                self.assertEqual("description" in tool,
                                 bool(record["description"]))

    def test_no_transport_branch_beyond_the_declared_ones_exists(self):
        """An unsupported transport has no key at all, not a false one."""
        self.assertEqual(self.artifact["transports"],
                         list(projector.MCP_TRANSPORTS))

        keys = set()
        stack = [self.artifact]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                keys |= set(node)
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)

        for absent in ("sse", "websocket"):
            self.assertNotIn(absent, keys)
            self.assertNotIn(absent, self.artifact["transports"])

    def test_the_artifact_announces_that_it_is_generated(self):
        generated = self.artifact["generated"]

        self.assertEqual(generated["notice"], projector.NOTICE)
        self.assertEqual(generated["not_a_revision_basis"],
                         projector.NOT_A_REVISION_BASIS)

    def test_every_emitted_field_is_bound_to_a_declaration_source(self):
        self.assertEqual(projector.unbound_field_paths(self.artifact), [])


class DeterminismTests(unittest.TestCase):
    def test_two_runs_agree_across_hash_seeds(self):
        with tempfile.TemporaryDirectory() as workspace:
            contract_path = Path(workspace) / projector.DEFAULT_CONTRACT
            contract_path.parent.mkdir(parents=True)
            contract_path.write_text(
                kblib.canonical_yaml(fixture_contract()), encoding="utf-8")
            artifact = Path(workspace) / projector.FORMS["mcp"]["output"]
            first_run = run(workspace, "--form", "mcp",
                            env={"PYTHONHASHSEED": "0"})
            self.assertEqual(first_run.returncode, 0,
                             first_run.stdout + first_run.stderr)
            first = artifact.read_bytes()
            second_run = run(workspace, "--form", "mcp",
                             env={"PYTHONHASHSEED": "12345"})
            self.assertEqual(second_run.returncode, 0,
                             second_run.stdout + second_run.stderr)

            self.assertEqual(first, artifact.read_bytes())


class MappingTests(unittest.TestCase):
    """Mapping rules the shipped tools do not happen to exercise."""

    def schema(self, **argument):
        record = dict({
            "dest": "sample", "option_strings": ["--sample"],
            "required": False, "default": None, "default_type": "NoneType",
            "choices": None, "nargs": None, "action": "store", "type": None,
            "help": None,
        }, **argument)
        return projector.property_schema(record)

    def test_an_undeclared_type_projects_as_a_string(self):
        self.assertEqual(self.schema()["type"],
                         projector.DEFAULT_SCALAR_TYPE)

    def test_a_custom_converter_projects_as_a_string_and_is_kept(self):
        schema = self.schema(type="positive_int")

        self.assertEqual(schema["type"], projector.DEFAULT_SCALAR_TYPE)
        self.assertEqual(schema[projector.CLI_EXTENSION_KEY]["type"],
                         "positive_int")

    def test_a_zero_value_action_projects_as_a_boolean(self):
        self.assertEqual(
            self.schema(action="store_true", nargs=0, default=False,
                        default_type="bool")["type"],
            "boolean")

    def test_a_repeated_argument_projects_as_an_array_of_its_element(self):
        schema = self.schema(action="append", type="int")

        self.assertEqual(schema["type"], "array")
        self.assertEqual(schema["items"]["type"], "integer")

    def test_one_or_more_projects_as_an_array_with_a_minimum(self):
        schema = self.schema(nargs="+")

        self.assertEqual(schema["type"], "array")
        self.assertEqual(schema["minItems"], 1)
        self.assertNotIn("maxItems", schema)

    def test_a_fixed_count_projects_as_an_array_of_that_exact_length(self):
        schema = self.schema(nargs=2)

        self.assertEqual((schema["minItems"], schema["maxItems"]), (2, 2))

    def test_a_suppressed_default_is_omitted_rather_than_recorded(self):
        schema = self.schema(default="==SUPPRESS==",
                             default_type="argparse.SUPPRESS")

        self.assertNotIn("default", schema)

    def test_a_positional_is_the_argument_with_no_option_strings(self):
        schema = self.schema(option_strings=[], dest="root")

        self.assertEqual(schema[projector.CLI_EXTENSION_KEY]["option_strings"],
                         [])


class FieldSourceTests(unittest.TestCase):
    def test_a_field_with_no_declaration_source_is_reported(self):
        artifact = {"invented_here": "a value nothing upstream states"}

        self.assertEqual(projector.unbound_field_paths(artifact),
                         ["invented_here"])

    def test_the_source_table_is_printable_without_reading_an_artifact(self):
        result = run(".", "--sources")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path in projector.FIELD_SOURCES:
            self.assertIn(path, result.stdout)


class FixtureRunTests(unittest.TestCase):
    """Exit codes, against a contract fixture this test owns end to end."""

    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.contract_path = os.path.join(self.workspace, "contract.yaml")
        self.output = os.path.join(
            self.workspace, projector.FORMS["mcp"]["output"])
        os.makedirs(os.path.dirname(self.output), exist_ok=True)
        self.write_contract()

    def write_contract(self, **overrides):
        with open(self.contract_path, "w", encoding="utf-8") as handle:
            handle.write(kblib.canonical_yaml(fixture_contract(**overrides)))

    def write_carried_contract(self):
        path = Path(self.workspace, projector.CARRIED_RUNTIME_CONTRACT)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(fixture_contract(
            projection_target=tool_availability.CARRIED_RUNTIME)),
            encoding="utf-8")
        return path

    def project(self, *extra):
        return run(self.workspace, "--form", "mcp", "--contract",
                   self.contract_path, *extra)

    def test_write_then_check_passes(self):
        self.assertEqual(self.project().returncode, 0)

        result = self.project("--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_carried_runtime_writes_only_the_registered_derived_projection(self):
        self.write_carried_contract()

        result = run(
            self.workspace, "--form", "mcp", "--projection-target",
            tool_availability.CARRIED_RUNTIME)

        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)
        runtime_output = Path(
            self.workspace, projector.FORMS["mcp"]["runtime_output"])
        self.assertTrue(runtime_output.is_file())
        self.assertFalse(Path(self.output).exists())
        artifact = json.loads(runtime_output.read_text(encoding="utf-8"))
        self.assertEqual(artifact["projection_target"],
                         tool_availability.CARRIED_RUNTIME)

    def test_carried_runtime_refuses_the_distribution_output(self):
        self.write_carried_contract()

        result = run(
            self.workspace, "--form", "mcp", "--projection-target",
            tool_availability.CARRIED_RUNTIME, "--output", self.output)

        self.assertEqual(result.returncode, 1,
                         result.stdout + result.stderr)
        self.assertFalse(Path(self.output).exists())

    def test_carried_runtime_refuses_an_alternate_contract_input(self):
        self.write_contract(
            projection_target=tool_availability.CARRIED_RUNTIME)

        result = run(
            self.workspace, "--form", "mcp", "--contract",
            self.contract_path, "--projection-target",
            tool_availability.CARRIED_RUNTIME)

        self.assertEqual(result.returncode, 1,
                         result.stdout + result.stderr)
        self.assertIn("unsafe carried-runtime contract input", result.stdout)
        self.assertFalse(Path(
            self.workspace,
            projector.FORMS["mcp"]["runtime_output"]).exists())

    def test_runtime_source_identity_does_not_change_mcp_path_semantics(self):
        contract = fixture_contract()
        record = contract["tools"][0]
        record["arguments"].append({
            "dest": "contract",
            "option_strings": ["--contract"],
            "required": False,
            "default": ".cambium/derived/page_contract.yaml",
            "default_type": "str",
            "choices": None,
            "nargs": None,
            "action": "store",
            "type": None,
            "help": "compiled page contract",
        })
        record["agent_interface"]["path_arguments"] = [{
            "argument": "contract",
            "access": "read",
            "consumption": "snapshot",
            "constraint": "exact",
            "value": ".cambium/derived/page_contract.yaml",
            "runtime_path_id": "effective-page-contract",
            "component_path_id": None,
            "suffixes": [],
            "active_when_any": [],
            "inactive_when_any": [],
        }]
        with open(self.contract_path, "w", encoding="utf-8") as handle:
            handle.write(kblib.canonical_yaml(contract))

        result = self.project()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        artifact = json.loads(Path(self.output).read_text(encoding="utf-8"))
        capability = artifact["tools"][0]["inputSchema"]["properties"][
            "contract"][projector.PATH_EXTENSION_KEY]
        self.assertEqual(
            capability,
            {
                "access": "read",
                "consumption": "snapshot",
                "constraint": "exact",
                "value": ".cambium/derived/page_contract.yaml",
                "suffixes": [],
                "active_when_any": [],
                "inactive_when_any": [],
            },
        )

    def test_component_source_identity_is_validated_but_not_exposed_to_mcp(self):
        contract = fixture_contract(component_path_registries={
            "card-directory": {
                "path": "Tools/schemas/card.schema.yaml",
                "sha256": kblib.sha256_bytes(b"fixture Card schema"),
            },
        })
        record = contract["tools"][0]
        record["arguments"].append({
            "dest": "cards_dir",
            "option_strings": ["--cards-dir"],
            "required": False,
            "default": "Card",
            "default_type": "str",
            "choices": None,
            "nargs": None,
            "action": "store",
            "type": None,
            "help": "canonical Card directory",
        })
        record["agent_interface"]["path_arguments"] = [{
            "argument": "cards_dir",
            "access": "read-write",
            "consumption": "transaction",
            "constraint": "exact",
            "value": "Card",
            "runtime_path_id": None,
            "component_path_id": "card-directory",
            "suffixes": [],
            "active_when_any": [],
            "inactive_when_any": [],
        }]
        with open(self.contract_path, "w", encoding="utf-8") as handle:
            handle.write(kblib.canonical_yaml(contract))

        result = self.project()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        artifact = json.loads(Path(self.output).read_text(encoding="utf-8"))
        capability = artifact["tools"][0]["inputSchema"]["properties"][
            "cards_dir"][projector.PATH_EXTENSION_KEY]
        self.assertEqual(
            capability,
            {
                "access": "read-write",
                "consumption": "transaction",
                "constraint": "exact",
                "value": "Card",
                "suffixes": [],
                "active_when_any": [],
                "inactive_when_any": [],
            },
        )

    def test_unknown_component_source_identity_is_unreliable(self):
        contract = fixture_contract()
        record = contract["tools"][0]
        record["arguments"].append({
            "dest": "cards_dir",
            "option_strings": ["--cards-dir"],
            "required": False,
            "default": "Card",
            "default_type": "str",
            "choices": None,
            "nargs": None,
            "action": "store",
            "type": None,
            "help": None,
        })
        record["agent_interface"]["path_arguments"] = [{
            "argument": "cards_dir",
            "access": "read-write",
            "consumption": "transaction",
            "constraint": "exact",
            "value": "Card",
            "runtime_path_id": None,
            "component_path_id": "card-directory",
            "suffixes": [],
            "active_when_any": [],
            "inactive_when_any": [],
        }]
        with open(self.contract_path, "w", encoding="utf-8") as handle:
            handle.write(kblib.canonical_yaml(contract))

        result = self.project()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("unknown component_path_id", result.stdout)

    def test_a_hand_edited_artifact_holds_with_2(self):
        self.project()
        text = Path(self.output).read_text(encoding="utf-8")
        Path(self.output).write_text(text.replace("sample", "renamed", 1),
                                     encoding="utf-8")

        result = self.project("--check")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_a_single_changed_byte_holds_with_2(self):
        self.project()
        raw = Path(self.output).read_bytes()
        Path(self.output).write_bytes(raw[:-2] + b" " + raw[-2:])

        result = self.project("--check")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_a_missing_artifact_holds_with_2(self):
        result = self.project("--check")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_an_upstream_change_makes_the_artifact_stale_with_2(self):
        self.project()
        self.write_contract(source_hash=kblib.sha256_bytes(b"later manifest"))

        result = self.project("--check")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_a_missing_upstream_is_unreliable_evidence_with_1_not_2(self):
        self.project()
        os.unlink(self.contract_path)

        result = self.project("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_an_unparseable_upstream_is_unreliable_evidence_with_1(self):
        with open(self.contract_path, "w", encoding="utf-8") as handle:
            handle.write("tools: [\n\tbroken\n")

        result = self.project("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_a_foreign_artifact_is_unreliable_evidence_with_1(self):
        self.write_contract(artifact="something-else")

        result = self.project("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_an_unreadable_upstream_schema_version_is_unreliable_with_1(self):
        self.write_contract(
            schema_version=projector.UPSTREAM_SCHEMA_VERSION + 1)

        result = self.project("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_an_upstream_changing_underneath_the_run_reports_1(self):
        """Time-of-check / time-of-use: two upstreams, so no verdict."""
        original = projector.read_contract

        def moving_target(path):
            contract, digest = original(path)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("\n# a concurrent recompilation\n")
            return contract, digest

        projector.read_contract = moving_target
        self.addCleanup(setattr, projector, "read_contract", original)

        code = projector.main([self.workspace, "--form", "mcp", "--contract",
                               self.contract_path, "--output", self.output,
                               "--check"])

        self.assertEqual(code, 1)

    def test_the_artifact_is_valid_json(self):
        self.project()

        artifact = json.loads(Path(self.output).read_text(encoding="utf-8"))

        self.assertEqual(artifact["artifact"], projector.ARTIFACT_KIND)
        self.assertEqual(artifact["form"], "mcp")


class FormRegistryTests(unittest.TestCase):
    """A second form joins the run by being registered, and nowhere else."""

    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        contract_path = os.path.join(
            self.workspace, projector.DEFAULT_CONTRACT)
        os.makedirs(os.path.dirname(contract_path))
        with open(contract_path, "w", encoding="utf-8") as handle:
            handle.write(kblib.canonical_yaml(fixture_contract()))

        self.second = "Tools/compiled/fixture-form.json"
        projector.FORMS["fixture"] = {
            "output": self.second,
            "build": projector.build_envelope,
            "summary": "a second form, registered only for this test",
        }
        self.addCleanup(projector.FORMS.pop, "fixture", None)

    def outputs(self):
        return [os.path.join(self.workspace, form["output"])
                for form in projector.FORMS.values()]

    def test_an_argument_free_run_covers_every_registered_form(self):
        self.assertEqual(projector.main([self.workspace]), 0)

        for path in self.outputs():
            self.assertTrue(os.path.isfile(path), path)

    def test_check_covers_every_registered_form(self):
        projector.main([self.workspace])

        self.assertEqual(projector.main([self.workspace, "--check"]), 0)

    def test_a_stale_second_form_holds_the_whole_run_with_2(self):
        projector.main([self.workspace])
        os.unlink(os.path.join(self.workspace, self.second))

        self.assertEqual(projector.main([self.workspace, "--check"]), 2)

    def test_one_form_can_be_selected_on_its_own(self):
        self.assertEqual(
            projector.main([self.workspace, "--form", "mcp"]), 0)

        self.assertFalse(os.path.exists(
            os.path.join(self.workspace, self.second)))


if __name__ == "__main__":
    unittest.main()
