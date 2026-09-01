"""Ownership tests for interface-projection -> Host configuration products.

The Host registry and shared transport policy own product membership and
shape. This suite exercises those owners directly instead of maintaining one
expected file per Host. Pure serializers and registry relations stay
in-process; integration tests start from a minimal projection checkpoint; one
test alone owns the public CLI transport.
"""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
SCRIPT = TOOLS_DIR / "render_host_configs.py"

sys.path.insert(0, str(TOOLS_DIR))
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.platform.agent_interface.agent_interface_policy as agent_interface_policy  # noqa: E402
import Tools.platform.agent_interface.render_host_configs as renderer  # noqa: E402
import Tools.platform.agent_interface.tool_availability as tool_availability  # noqa: E402


def run_in_process(*arguments):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = renderer.main(list(arguments))
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


def fixture_projection(**overrides):
    value = {
        "schema_version": renderer.UPSTREAM_SCHEMA_VERSION,
        "artifact": renderer.UPSTREAM_ARTIFACT,
        "form": renderer.UPSTREAM_FORM,
        "projection_target": tool_availability.SOURCE_DISTRIBUTION,
        "source_hash": kblib.sha256_bytes(b"fixture contract"),
        "tool_count": 1,
        "tools": [{"name": "sample", "inputSchema": {"type": "object"}}],
    }
    value.update(overrides)
    return value


def write_projection(root, projection):
    relative = renderer.projection_for_target(projection["projection_target"])
    path = Path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(projection), encoding="utf-8")
    return path


@contextmanager
def temporary_repository(projection=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory, "repository")
        root.mkdir()
        selected = projection or fixture_projection()
        write_projection(root, selected)
        if selected["projection_target"] == tool_availability.CARRIED_RUNTIME:
            entry_point = root / renderer.SERVER_ENTRY_POINT
            entry_point.parent.mkdir(parents=True, exist_ok=True)
            entry_point.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        yield root


def product_context():
    source_hash = kblib.sha256_bytes(b"fixture projection")
    bindings = (
        (renderer.PROJECTION_PATH_PLACEHOLDER,
         "%s/%s" % (renderer.DISTRIBUTION_PLACEHOLDER,
                     renderer.DEFAULT_PROJECTION)),
        (renderer.DISTRIBUTION_PLACEHOLDER,
         renderer.DISTRIBUTION_PLACEHOLDER),
        (renderer.WORKSPACE_PLACEHOLDER, renderer.WORKSPACE_PLACEHOLDER),
        (renderer.SOURCE_HASH_PLACEHOLDER, source_hash),
    )
    return {
        "source": renderer.DEFAULT_PROJECTION,
        "source_hash": source_hash,
        "projection_target": tool_availability.SOURCE_DISTRIBUTION,
        "root": str(REPO_ROOT),
        "output_dir": str(REPO_ROOT / renderer.DEFAULT_OUTPUT_DIR),
        "bindings": bindings,
        "unsubstituted": tuple(
            placeholder for placeholder, replacement in bindings
            if placeholder == replacement),
    }


def build_products(context=None):
    context = context or product_context()
    return {
        host: entry["build"](host, context)
        for host, entry in renderer.HOSTS.items()
    }


class HostProductContractTests(unittest.TestCase):
    """Contract: the registry is the sole product membership and shape owner."""

    def test_registry_builds_unique_parseable_products(self):
        products = build_products()
        outputs = [entry["output"] for entry in renderer.HOSTS.values()]
        self.assertEqual(len(outputs), len(set(outputs)))
        self.assertEqual(set(products), set(renderer.HOSTS))

        for host, product in products.items():
            entry = renderer.HOSTS[host]
            with self.subTest(host=host):
                self.assertTrue(set(entry["carries"]) <= {
                    "registration", "binding"})
                text = renderer.SERIALIZERS[entry["format"]](product)
                renderer.validator_for(
                    entry["format"], product["document"])(text)
                self.assertTrue(text.endswith("\n"))
                self.assertFalse(text.endswith("\n\n"))

    def test_registration_and_binding_are_projected_once_then_partitioned(self):
        context = product_context()
        products = build_products(context)
        expected = renderer.server_body(context)
        transport = agent_interface_policy.shared_host_transport(REPO_ROOT)

        self.assertEqual(renderer.HOST_TRANSPORT_ID,
                         transport["transport_id"])
        self.assertEqual(renderer.SERVER_NAME, transport["server_name"])
        self.assertEqual(renderer.SERVER_COMMAND, transport["command"])
        self.assertEqual(renderer.SERVER_ENTRY_POINT, transport["path"])
        self.assertEqual(renderer.DSH_TRANSPORT, transport["mode"])

        registrations = []
        for host, key in (("claude-code", "mcpServers"),
                          ("kimi-code", "mcpServers"),
                          ("codex", "mcp_servers")):
            body = products[host]["document"][key][renderer.SERVER_NAME]
            registrations.append({
                field: body[field] for field in renderer.REGISTRATION_FIELDS})
            self.assertEqual(body[renderer.ENV_FIELD], expected[renderer.ENV_FIELD])
        self.assertTrue(all(item == registrations[0]
                            for item in registrations[1:]))

        patch_entry, = products["dsh-profile-patch"]["document"][0]["insert"]
        config = patch_entry["config"]
        self.assertEqual(
            {field: config[field] for field in renderer.REGISTRATION_FIELDS},
            registrations[0])
        self.assertNotIn(renderer.ENV_FIELD, config)
        for field, value in renderer.MCP_SERVER[renderer.RESILIENCE_FIELD].items():
            self.assertEqual(config[field], value)

        binding = products["dsh-env"]["document"]
        self.assertEqual(binding, expected[renderer.ENV_FIELD])
        for field in renderer.REGISTRATION_FIELDS:
            self.assertNotIn(field, binding)

    def test_field_sources_and_packaging_rules_close_over_every_product(self):
        products = list(build_products().items())
        self.assertEqual(renderer.unbound_field_paths(products), [])
        rendered_fields = set().union(*(
            renderer.artifact_field_paths(product, host)
            for host, product in products
        ))
        self.assertEqual(rendered_fields, set(renderer.FIELD_SOURCES))
        self.assertEqual(renderer.forbidden_document_keys(products), [])
        self.assertEqual(renderer.name_violations(renderer.SERVER_NAME), [])

        for rejected in ("Cambium", "cambium mcp", "-cambium",
                         "cambium-", "cam--bium", "cambium_mcp"):
            with self.subTest(name=rejected):
                self.assertTrue(renderer.name_violations(rejected))

        invented = [("claude-code", {
            "header": [], "document": {"invented": True}})]
        self.assertTrue(renderer.unbound_field_paths(invented))
        skill = [("claude-code", {
            "header": [], "document": {"skills": ["invented"]}})]
        self.assertTrue(renderer.forbidden_document_keys(skill))

    def test_invalid_projection_contract_matrix(self):
        cases = (
            ("missing", None),
            ("unparseable", "raw"),
            ("non-object", []),
            ("foreign-artifact", {"artifact": "other"}),
            ("foreign-form", {"form": "other"}),
            ("schema", {
                "schema_version": renderer.UPSTREAM_SCHEMA_VERSION + 1}),
            ("source-hash", {"source_hash": None}),
            ("projection-target", {"projection_target": "other"}),
            ("tools-shape", {"tools": {}}),
            ("empty-tools", {"tools": []}),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "projection.json")
            for name, mutation in cases:
                if path.exists():
                    path.unlink()
                if mutation is None:
                    pass
                elif mutation == "raw":
                    path.write_text("{not json", encoding="utf-8")
                elif isinstance(mutation, list):
                    path.write_text(json.dumps(mutation), encoding="utf-8")
                else:
                    path.write_text(
                        json.dumps(fixture_projection(**mutation)),
                        encoding="utf-8")
                with self.subTest(case=name), self.assertRaises(
                        renderer.RenderError):
                    renderer.read_projection(path)


class HostSerializerTests(unittest.TestCase):
    """Unit: one matrix owns the two local restricted serializers."""

    def test_serializer_acceptance_matrix(self):
        self.assertEqual(
            renderer.toml_table_lines({"outer": {"inner": {"b": 1, "a": 2}}}),
            ["[outer.inner]", "a = 2", "b = 1"])
        self.assertEqual(
            renderer.dotenv_lines({"A": "/two words/here"}),
            ['A="/two words/here"'])

        invalid = (
            ("toml-key", lambda: renderer.toml_table_lines(
                {"table": {"a key": 1}})),
            ("toml-top-level-scalar", lambda: renderer.toml_table_lines(
                {"value": 1})),
            ("toml-control", lambda: renderer.toml_scalar("line\nbreak")),
            ("dotenv-key", lambda: renderer.dotenv_lines(
                {"not-valid": "value"})),
            ("dotenv-quote", lambda: renderer.dotenv_lines(
                {"A": 'has"quote'})),
            ("dotenv-backslash", lambda: renderer.dotenv_lines(
                {"A": "has\\backslash"})),
            ("dotenv-control", lambda: renderer.dotenv_lines(
                {"A": "line\nbreak"})),
            ("json-header", lambda: renderer.render_json(
                {"header": ["not representable"], "document": {}})),
        )
        for name, operation in invalid:
            with self.subTest(case=name):
                with self.assertRaises(renderer.RenderError):
                    operation()


class HostProductLifecycleTests(unittest.TestCase):
    """Integration: projection, products, currentness and target registry."""

    def test_write_check_and_one_upstream_invalidates_every_product(self):
        with temporary_repository() as root:
            self.assertEqual(run_in_process(str(root)).returncode, 0)
            self.assertEqual(run_in_process(str(root), "--check").returncode, 0)

            changed = root / renderer.DEFAULT_OUTPUT_DIR / renderer.HOSTS[
                "codex"]["output"]
            changed.write_text(changed.read_text(encoding="utf-8") + " ",
                               encoding="utf-8")
            self.assertEqual(run_in_process(str(root), "--check").returncode, 2)

            self.assertEqual(run_in_process(str(root)).returncode, 0)
            write_projection(root, fixture_projection(
                source_hash=kblib.sha256_bytes(b"later interface")))
            result = run_in_process(str(root), "--check")
            self.assertEqual(result.returncode, 2)
            for entry in renderer.HOSTS.values():
                self.assertIn(entry["output"], result.stdout)

            self.assertEqual(run_in_process(str(root)).returncode, 0)
            Path(root, renderer.DEFAULT_OUTPUT_DIR,
                 renderer.SKILL_MANIFEST).write_text(
                     "# forbidden package shape\n", encoding="utf-8")
            self.assertEqual(run_in_process(str(root), "--check").returncode, 1)

    def test_carried_target_has_one_registered_input_and_external_staging(self):
        carried = fixture_projection(
            projection_target=tool_availability.CARRIED_RUNTIME)
        with temporary_repository(carried) as root:
            output = root / "host-config-staging"
            result = run_in_process(
                str(root), "--projection-target",
                tool_availability.CARRIED_RUNTIME,
                "--output-dir", str(output),
                "--distribution-root", str(root),
                "--workspace-root", str(root))
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {entry["output"] for entry in renderer.HOSTS.values()})
            claude = json.loads((output / renderer.HOSTS[
                "claude-code"]["output"]).read_text(encoding="utf-8"))
            bound = claude["mcpServers"][renderer.SERVER_NAME]["env"][
                renderer.PROJECTION_PATH_ENV]
            self.assertEqual(
                bound, "%s/%s" % (
                    root, renderer.CARRIED_RUNTIME_PROJECTION))
            self.assertFalse((root / renderer.DEFAULT_OUTPUT_DIR).exists())

            cases = ("missing-roots", "runtime-output", "tracked-output",
                     "other-workspace", "other-component",
                     "missing-entry-point")
            for case in cases:
                output = root / "host-config-staging"
                arguments = [
                    str(root), "--projection-target",
                    tool_availability.CARRIED_RUNTIME,
                    "--output-dir", str(output),
                    "--distribution-root", str(root),
                    "--workspace-root", str(root),
                ]
                if case == "missing-roots":
                    arguments = [
                        str(root), "--projection-target",
                        tool_availability.CARRIED_RUNTIME]
                elif case == "runtime-output":
                    arguments[arguments.index(str(output))] = str(
                        root / ".cambium/host-configs")
                elif case == "tracked-output":
                    arguments[arguments.index(str(output))] = str(
                        root / renderer.DEFAULT_OUTPUT_DIR)
                elif case == "other-workspace":
                    arguments[-1] = str(root.parent / "other-workspace")
                elif case == "other-component":
                    arguments[-3] = str(root.parent / "other-component")
                elif case == "missing-entry-point":
                    (root / renderer.SERVER_ENTRY_POINT).unlink()
                with self.subTest(case=case):
                    result = run_in_process(*arguments)
                    self.assertEqual(result.returncode, 1,
                                     result.stdout + result.stderr)

    def test_bound_header_replays_the_exact_render_context(self):
        with temporary_repository() as root:
            distribution = root / "a distribution"
            corpus = root / "corpus"
            result = run_in_process(
                str(root), "--distribution-root", str(distribution),
                "--workspace-root", str(corpus))
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)

            header = (root / renderer.DEFAULT_OUTPUT_DIR / renderer.HOSTS[
                "codex"]["output"]).read_text(encoding="utf-8")
            verify = next(
                line.split(": ", 1)[1] for line in header.splitlines()
                if line.startswith("# verify: "))
            command = shlex.split(verify)
            self.assertIn(str(distribution), command)
            self.assertIn(str(corpus), command)

            replayed = run_in_process(str(root), *command[3:])
            self.assertEqual(
                replayed.returncode, 0,
                "the generated verify command did not reproduce its bytes")


class HostProductSlowTests(unittest.TestCase):
    """Slow: filesystem identity and currentness race boundaries."""

    def test_output_staging_cannot_escape_repository_identity(self):
        with temporary_repository() as root:
            for case in ("outside", "symlink", "nested-symlink"):
                outside = root.parent / ("outside-" + case)
                outside.mkdir()
                if case == "outside":
                    output = outside / "host-configs"
                elif case == "symlink":
                    output = root / "redirect-symlink"
                    output.symlink_to(outside, target_is_directory=True)
                else:
                    parent = root / "staging"
                    parent.mkdir()
                    (parent / "redirect").symlink_to(
                        outside, target_is_directory=True)
                    output = parent / "redirect/host-configs"

                with self.subTest(case=case):
                    result = run_in_process(
                        str(root), "--output-dir", str(output))
                    self.assertEqual(result.returncode, 1,
                                     result.stdout + result.stderr)
                    self.assertEqual(list(outside.iterdir()), [])

    def test_upstream_change_during_render_has_no_verdict(self):
        original = renderer.read_projection

        def moving_target(path):
            projection, digest = original(path)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("\n")
            return projection, digest

        renderer.read_projection = moving_target
        self.addCleanup(setattr, renderer, "read_projection", original)

        with temporary_repository() as root:
            result = run_in_process(str(root), "--check")
        self.assertEqual(result.returncode, 1)


class HostProductTransportTests(unittest.TestCase):
    def test_public_cli_writes_one_selected_host_product(self):
        with temporary_repository() as root:
            result = run_cli(str(root), "--host", "codex")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = root / renderer.DEFAULT_OUTPUT_DIR
            self.assertTrue((output / renderer.HOSTS["codex"]["output"]).is_file())
            self.assertFalse(
                (output / renderer.HOSTS["claude-code"]["output"]).exists())


if __name__ == "__main__":
    unittest.main()
