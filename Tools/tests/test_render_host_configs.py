"""The five host configuration products and the renderer that writes them.

These cover the properties the products are only useful for having: that one
server definition body reaches all five rather than five hand-kept copies of
it, that registration and binding stay separable (dsh receives them in two
files), that every product binds the sha256 of the compiled tool projection so
one upstream change makes all five stale at once, that two runs agree byte for
byte across hash seeds, that `--check` separates a stale product (2, a HOLD)
from unreliable evidence (1), that each product parses as its own format, and
that a field with no declaration source cannot reach a product at all.

No command, path, timeout, or header sentence is restated here. Every
expectation is read either from the tool's own declared constants or from a
fixture built inside the test, so this file cannot drift into a second
declaration of the configuration.
"""

import json
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - older interpreters
    tomllib = None

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
SCRIPT = TOOLS_DIR / "render_host_configs.py"

sys.path.insert(0, str(TOOLS_DIR))
import kblib  # noqa: E402
import render_host_configs as renderer  # noqa: E402
import tool_availability  # noqa: E402

PROJECTION = REPO_ROOT / renderer.DEFAULT_PROJECTION
OUTPUT_DIR = REPO_ROOT / renderer.DEFAULT_OUTPUT_DIR


def run(*arguments, env=None):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(arguments),
        capture_output=True, text=True, env=environment,
        cwd=str(REPO_ROOT), check=False)


def fixture_projection(**overrides):
    """One minimal interface projection, owned entirely by this test file."""
    data = {
        "schema_version": renderer.UPSTREAM_SCHEMA_VERSION,
        "artifact": renderer.UPSTREAM_ARTIFACT,
        "form": renderer.UPSTREAM_FORM,
        "projection_target": "source-distribution",
        "source_hash": kblib.sha256_bytes(b"fixture contract"),
        "tool_count": 1,
        "tools": [{"name": "sample", "inputSchema": {"type": "object"}}],
    }
    data.update(overrides)
    return data


def product_path(host):
    return OUTPUT_DIR / renderer.HOSTS[host]["output"]


class ShippedProductTests(unittest.TestCase):
    """What ships in the tree must be what the definition currently states."""

    def setUp(self):
        self.projection_hash = kblib.sha256_bytes(PROJECTION.read_bytes())

    def test_check_accepts_the_shipped_products(self):
        result = run(".", "--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_registered_host_ships_its_product(self):
        for host in renderer.HOSTS:
            with self.subTest(host=host):
                self.assertTrue(product_path(host).is_file(),
                                str(product_path(host)))

    def test_no_product_lands_at_a_path_a_host_would_load(self):
        """The products are for an adopter's corpus, not for this repository."""
        for forbidden in (".mcp.json", ".env", ".codex", ".kimi-code"):
            self.assertFalse((REPO_ROOT / forbidden).exists(), forbidden)
        for host in renderer.HOSTS:
            destination = renderer.HOSTS[host]["destination"]
            with self.subTest(host=host):
                self.assertNotEqual(
                    product_path(host).name,
                    destination.rsplit("/", 1)[-1],
                    "a rendered product is named exactly as the file a host "
                    "loads")

    def test_every_product_binds_the_projection_bytes_it_was_rendered_from(self):
        for host in renderer.HOSTS:
            with self.subTest(host=host):
                text = product_path(host).read_text(encoding="utf-8")

                self.assertIn(self.projection_hash, text)

    def test_the_declared_name_survives_the_four_host_intersection(self):
        self.assertEqual(renderer.name_violations(renderer.SERVER_NAME), [])

    def test_a_name_outside_the_intersection_is_reported(self):
        for rejected in ("Cambium", "cambium mcp", "-cambium", "cambium-",
                         "cam--bium", "cambium_mcp"):
            with self.subTest(name=rejected):
                self.assertTrue(renderer.name_violations(rejected), rejected)

    def test_no_skill_manifest_sits_in_the_rendered_tree(self):
        self.assertEqual(renderer.skill_manifests(str(OUTPUT_DIR)), [])

    def test_the_products_announce_that_they_are_generated(self):
        """Every format that has a comment syntax carries the notice."""
        for host, entry in renderer.HOSTS.items():
            if entry["format"] == "json":
                continue
            with self.subTest(host=host):
                text = product_path(host).read_text(encoding="utf-8")

                self.assertIn(renderer.NOTICE.split(".")[0], text)
                self.assertIn(renderer.BASE_INVOCATION, text)


class DefinitionReachesEveryProductTests(unittest.TestCase):
    """One definition body, five products; nothing is spelled twice."""

    def setUp(self):
        self.claude = json.loads(
            product_path("claude-code").read_text(encoding="utf-8"))
        self.kimi = json.loads(
            product_path("kimi-code").read_text(encoding="utf-8"))
        self.patch = kblib.parse_yaml_subset(
            product_path("dsh-profile-patch").read_text(encoding="utf-8"))

    def server(self, document, key="mcpServers"):
        return document[key][renderer.SERVER_NAME]

    def dsh_config(self):
        """The dsh registration body, reached the way dsh reaches it.

        dsh has no server map. Its product is a loader patch list whose
        one entry inserts a `dsh-mcp-client` plugin row, and the server
        lives in that row's `config`. Reaching it through the same shape
        dsh parses is the point: a test that indexed a `mcpServers` key
        would pass against a document dsh rejects.
        """
        entry, = self.patch[0]["insert"]

        self.assertEqual(entry["name"], renderer.DSH_PLUGIN_NAME)
        self.assertEqual(entry["config"]["transport"], renderer.DSH_TRANSPORT)
        self.assertEqual(entry["config"]["serverName"], renderer.SERVER_NAME)
        return entry["config"]

    def test_the_command_and_entry_point_are_the_declared_ones(self):
        body = self.server(self.claude)

        self.assertEqual(body["command"], renderer.MCP_SERVER["command"])
        self.assertEqual(len(body["args"]), 1)
        self.assertTrue(body["args"][0].endswith(renderer.SERVER_ENTRY_POINT))

    def test_every_registering_product_carries_the_same_registration(self):
        registrations = [
            {key: self.server(self.claude)[key]
             for key in renderer.REGISTRATION_FIELDS},
            {key: self.server(self.kimi)[key]
             for key in renderer.REGISTRATION_FIELDS},
            {key: self.dsh_config()[key]
             for key in renderer.REGISTRATION_FIELDS},
        ]
        if tomllib is not None:
            codex = tomllib.loads(
                product_path("codex").read_text(encoding="utf-8"))
            registrations.append(
                {key: codex["mcp_servers"][renderer.SERVER_NAME][key]
                 for key in renderer.REGISTRATION_FIELDS})

        for other in registrations[1:]:
            self.assertEqual(other, registrations[0])

    def test_the_two_json_hosts_are_separate_files_not_one_shared_file(self):
        self.assertNotEqual(product_path("claude-code"),
                            product_path("kimi-code"))
        self.assertTrue(product_path("claude-code").is_file())
        self.assertTrue(product_path("kimi-code").is_file())

    def test_the_resilience_superset_reaches_dsh_and_nothing_else(self):
        body = self.dsh_config()
        resilience = renderer.MCP_SERVER[renderer.RESILIENCE_FIELD]

        for key, value in resilience.items():
            self.assertEqual(body[key], value)
        for key in resilience:
            self.assertNotIn(key, self.server(self.claude))
            self.assertNotIn(key, self.server(self.kimi))

    def test_dsh_receives_registration_and_binding_in_two_files(self):
        binding = renderer.parse_dotenv(
            product_path("dsh-env").read_text(encoding="utf-8"))
        registration = self.dsh_config()

        self.assertIn(renderer.WORKSPACE_ENV, binding)
        self.assertNotIn(renderer.ENV_FIELD, registration)
        for key in renderer.REGISTRATION_FIELDS:
            self.assertNotIn(key, binding)

    def test_the_binding_travels_as_the_contract_environment_variable(self):
        for document, key in ((self.claude, "mcpServers"),
                              (self.kimi, "mcpServers")):
            body = self.server(document, key)
            self.assertIn(renderer.WORKSPACE_ENV, body[renderer.ENV_FIELD])

    def test_a_host_declaring_only_one_half_carries_only_that_half(self):
        for host, entry in renderer.HOSTS.items():
            with self.subTest(host=host):
                self.assertTrue(set(entry["carries"]) <=
                                {"registration", "binding"})
        self.assertEqual(renderer.HOSTS["dsh-env"]["carries"], ("binding",))
        self.assertEqual(renderer.HOSTS["dsh-profile-patch"]["carries"],
                         ("registration",))


class ProductShapeTests(unittest.TestCase):
    """Each product must be readable by a parser for its own format."""

    def test_the_json_products_parse_as_json_objects(self):
        for host in ("claude-code", "kimi-code"):
            with self.subTest(host=host):
                document = json.loads(
                    product_path(host).read_text(encoding="utf-8"))

                self.assertIn(renderer.SERVER_NAME, document["mcpServers"])

    @unittest.skipIf(tomllib is None, "tomllib requires Python 3.11+")
    def test_the_codex_product_parses_as_toml(self):
        document = tomllib.loads(
            product_path("codex").read_text(encoding="utf-8"))

        self.assertIn(renderer.SERVER_NAME, document["mcp_servers"])

    def test_the_dsh_binding_parses_as_a_dotenv_assignment_list(self):
        text = product_path("dsh-env").read_text(encoding="utf-8")
        document = renderer.parse_dotenv(text)

        self.assertIn(renderer.WORKSPACE_ENV, document)
        self.assertIn(renderer.SOURCE_HASH_ENV, document)
        for line in text.splitlines():
            if line and not line.startswith("#"):
                self.assertIn("=", line)

    def test_the_dsh_patch_row_parses_under_the_restricted_yaml_subset(self):
        document = kblib.parse_yaml_subset(
            product_path("dsh-profile-patch").read_text(encoding="utf-8"))

        # A loader patch list is a top-level sequence, and dsh throws on
        # anything else. The entry carries `insert` with no `id`, which is
        # what appends the plugin row at the top level of the profile tree.
        self.assertIsInstance(document, list)
        self.assertEqual(len(document), 1)
        self.assertEqual(set(document[0]), {"insert"})
        entry, = document[0]["insert"]
        self.assertEqual(entry["id"], renderer.DSH_ENTRY_ID)
        self.assertEqual(entry["name"], renderer.DSH_PLUGIN_NAME)
        self.assertEqual(entry["config"]["serverName"], renderer.SERVER_NAME)

    def test_an_unbound_header_stays_the_short_command(self):
        # No substitution happened, so no flag belongs in the command; a
        # header that grew one would churn every distribution artifact.
        header = product_path("codex").read_text(encoding="utf-8")
        line = next(l for l in header.splitlines() if l.startswith("# verify:"))

        self.assertNotIn("--distribution-root", line)
        self.assertNotIn("--workspace-root", line)

    def test_every_product_ends_with_exactly_one_newline(self):
        for host in renderer.HOSTS:
            with self.subTest(host=host):
                raw = product_path(host).read_bytes()

                self.assertTrue(raw.endswith(b"\n"))
                self.assertFalse(raw.endswith(b"\n\n"))


class SerializerTests(unittest.TestCase):
    """The two emitters this tool owns, because kblib has neither."""

    def test_an_intermediate_toml_table_is_left_implicit(self):
        lines = renderer.toml_table_lines({"outer": {"inner": {"a": 1}}})

        self.assertNotIn("[outer]", lines)
        self.assertIn("[outer.inner]", lines)

    def test_toml_keys_are_emitted_in_sorted_order(self):
        lines = renderer.toml_table_lines({"t": {"b": 1, "a": 2}})

        self.assertEqual(lines, ["[t]", "a = 2", "b = 1"])

    def test_a_toml_key_outside_the_bare_grammar_is_refused(self):
        with self.assertRaises(renderer.RenderError):
            renderer.toml_table_lines({"t": {"a key": 1}})

    def test_a_dotenv_value_is_always_quoted_so_a_path_may_hold_a_space(self):
        lines = renderer.dotenv_lines({"A": "/two words/here"})

        self.assertEqual(lines, ['A="/two words/here"'])

    def test_a_dotenv_value_needing_an_escape_is_refused_not_escaped(self):
        for value in ('has"quote', "has\\backslash", "has\nnewline"):
            with self.subTest(value=value):
                with self.assertRaises(renderer.RenderError):
                    renderer.dotenv_lines({"A": value})

    def test_a_json_product_may_not_carry_a_comment_header(self):
        with self.assertRaises(renderer.RenderError):
            renderer.render_json({"header": ["x"], "document": {}})


class FieldSourceTests(unittest.TestCase):
    def test_a_field_with_no_declaration_source_is_reported(self):
        products = [("claude-code", {"invented_here": "nothing states this"})]

        self.assertEqual(renderer.unbound_field_paths(products),
                         ["claude-code.invented_here"])

    def test_renaming_the_server_leaves_its_fields_unbound(self):
        """The name is a bound field, not a free string."""
        original = renderer.SERVER_NAME
        self.addCleanup(setattr, renderer, "SERVER_NAME", original)
        renderer.SERVER_NAME = "renamed"
        context = {"source": "x", "source_hash": "sha256:x",
                   "bindings": (), "unsubstituted": (),
                   "projection_target": "source-distribution"}

        products = [("claude-code",
                     renderer.build_claude_code("claude-code", context))]

        self.assertTrue(renderer.unbound_field_paths(products))

    def test_a_declared_skill_key_is_refused(self):
        products = [("claude-code", {"document": {"skills": ["anything"]}})]

        self.assertTrue(renderer.forbidden_document_keys(products))

    def test_the_source_table_is_printable_without_reading_a_product(self):
        result = run(".", "--sources")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path in renderer.FIELD_SOURCES:
            self.assertIn(path, result.stdout)

    def test_every_bound_path_is_actually_rendered(self):
        """The table is the admission rule, not a place entries accumulate."""
        context = {"source": renderer.DEFAULT_PROJECTION,
                   "source_hash": "sha256:x",
                   "bindings": (), "unsubstituted": (),
                   "projection_target": "source-distribution"}
        rendered = set()
        for host, entry in renderer.HOSTS.items():
            product = entry["build"](host, context)
            rendered |= renderer.artifact_field_paths(product, host)

        self.assertEqual(sorted(set(renderer.FIELD_SOURCES) - rendered), [])


class DeterminismTests(unittest.TestCase):
    def test_two_runs_agree_across_hash_seeds(self):
        with tempfile.TemporaryDirectory() as workspace:
            projection = Path(workspace, renderer.DEFAULT_PROJECTION)
            projection.parent.mkdir(parents=True, exist_ok=True)
            projection.write_text(json.dumps(fixture_projection()),
                                  encoding="utf-8")
            first = os.path.join(workspace, "first")
            second = os.path.join(workspace, "second")
            first_run = run(
                workspace, "--projection", str(projection),
                "--output-dir", first, env={"PYTHONHASHSEED": "0"})
            second_run = run(
                workspace, "--projection", str(projection),
                "--output-dir", second,
                env={"PYTHONHASHSEED": "12345"})
            self.assertEqual(first_run.returncode, 0,
                             first_run.stdout + first_run.stderr)
            self.assertEqual(second_run.returncode, 0,
                             second_run.stdout + second_run.stderr)

            for host in renderer.HOSTS:
                name = renderer.HOSTS[host]["output"]
                with self.subTest(host=host):
                    self.assertEqual(
                        Path(first, name).read_bytes(),
                        Path(second, name).read_bytes())


class FixtureRunTests(unittest.TestCase):
    """Exit codes, against a projection fixture this test owns end to end."""

    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.projection_path = os.path.join(self.workspace, "mcp-tools.json")
        self.output_dir = os.path.join(self.workspace, "host-configs")
        self.write_projection()

    def write_projection(self, **overrides):
        with open(self.projection_path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(fixture_projection(**overrides)))

    def render(self, *extra):
        return run(self.workspace, "--projection", self.projection_path,
                   "--output-dir", self.output_dir, *extra)

    def product(self, host):
        return Path(self.output_dir, renderer.HOSTS[host]["output"])

    def test_write_then_check_passes(self):
        self.assertEqual(self.render().returncode, 0)

        result = self.render("--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def write_carried_projection(self):
        path = Path(self.workspace, renderer.CARRIED_RUNTIME_PROJECTION)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fixture_projection(
            projection_target=tool_availability.CARRIED_RUNTIME)),
            encoding="utf-8")
        return path

    def test_carried_runtime_writes_only_adopter_derived_host_configs(self):
        self.write_carried_projection()

        result = run(
            self.workspace, "--projection-target",
            tool_availability.CARRIED_RUNTIME)

        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)
        output = Path(self.workspace, renderer.CARRIED_RUNTIME_OUTPUT_DIR)
        for entry in renderer.HOSTS.values():
            self.assertTrue((output / entry["output"]).is_file())
        claude = json.loads((output / renderer.HOSTS[
            "claude-code"]["output"]).read_text(encoding="utf-8"))
        projection_path = claude["mcpServers"][renderer.SERVER_NAME][
            "env"][renderer.PROJECTION_PATH_ENV]
        self.assertEqual(
            projection_path,
            "%s/%s" % (renderer.WORKSPACE_PLACEHOLDER,
                       renderer.CARRIED_RUNTIME_PROJECTION))
        self.assertNotIn("Tools/compiled", projection_path)
        self.assertFalse(Path(
            self.workspace, renderer.DEFAULT_OUTPUT_DIR).exists())

    def test_carried_runtime_refuses_an_alternate_output_directory(self):
        self.write_carried_projection()
        alternate = Path(self.workspace, "elsewhere")

        result = run(
            self.workspace, "--projection-target",
            tool_availability.CARRIED_RUNTIME,
            "--output-dir", str(alternate))

        self.assertEqual(result.returncode, 1,
                         result.stdout + result.stderr)
        self.assertFalse(alternate.exists())

    def test_a_single_changed_byte_holds_with_2(self):
        for host in renderer.HOSTS:
            with self.subTest(host=host):
                self.assertEqual(self.render().returncode, 0)
                path = self.product(host)
                raw = path.read_bytes()
                path.write_bytes(raw[:-1] + b" \n")

                result = self.render("--check")

                self.assertEqual(result.returncode, 2,
                                 result.stdout + result.stderr)

    def test_a_hand_edited_value_holds_with_2(self):
        self.render()
        path = self.product("claude-code")
        path.write_text(
            path.read_text(encoding="utf-8").replace("python3", "python"),
            encoding="utf-8")

        result = self.render("--check")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_a_missing_product_holds_with_2(self):
        result = self.render("--check")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_an_upstream_change_makes_every_product_stale_at_once(self):
        """No pairwise agreement between products is ever maintained."""
        self.render()
        self.write_projection(source_hash=kblib.sha256_bytes(b"later"))

        result = self.render("--check")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        for host in renderer.HOSTS:
            self.assertIn(str(self.product(host)), result.stdout)

    def test_a_missing_upstream_is_unreliable_evidence_with_1_not_2(self):
        self.render()
        os.unlink(self.projection_path)

        result = self.render("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_an_unparseable_upstream_is_unreliable_evidence_with_1(self):
        with open(self.projection_path, "w", encoding="utf-8") as handle:
            handle.write("{not json")

        result = self.render("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_a_foreign_upstream_artifact_is_unreliable_evidence_with_1(self):
        self.write_projection(artifact="something-else")

        result = self.render("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_an_upstream_of_another_form_is_unreliable_evidence_with_1(self):
        self.write_projection(form="not-mcp")

        result = self.render("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_an_unreadable_upstream_schema_version_is_unreliable_with_1(self):
        self.write_projection(
            schema_version=renderer.UPSTREAM_SCHEMA_VERSION + 1)

        result = self.render("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_an_upstream_offering_no_tools_is_unreliable_evidence_with_1(self):
        self.write_projection(tools=[])

        result = self.render("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_an_upstream_changing_underneath_the_run_reports_1(self):
        """Time-of-check / time-of-use: two upstreams, so no verdict."""
        original = renderer.read_projection

        def moving_target(path):
            projection, digest = original(path)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("\n")
            return projection, digest

        renderer.read_projection = moving_target
        self.addCleanup(setattr, renderer, "read_projection", original)

        code = renderer.main([self.workspace, "--projection",
                              self.projection_path, "--output-dir",
                              self.output_dir, "--check"])

        self.assertEqual(code, 1)

    def test_a_skill_manifest_in_the_rendered_tree_is_unreliable_with_1(self):
        self.render()
        Path(self.output_dir, renderer.SKILL_MANIFEST).write_text(
            "# not allowed here\n", encoding="utf-8")

        result = self.render("--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_a_relative_root_is_a_usage_error_with_1(self):
        for flag in ("--distribution-root", "--workspace-root"):
            with self.subTest(flag=flag):
                result = self.render(flag, "relative/path")

                self.assertEqual(result.returncode, 1,
                                 result.stdout + result.stderr)

    def test_one_host_can_be_rendered_on_its_own(self):
        self.assertEqual(
            self.render("--host", "codex").returncode, 0)

        self.assertTrue(self.product("codex").is_file())
        self.assertFalse(self.product("claude-code").exists())

    def test_an_unknown_host_is_a_usage_error_with_1(self):
        result = self.render("--host", "not-a-host")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


class SubstitutionTests(unittest.TestCase):
    """A bound render replaces the placeholders and says nothing about them."""

    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.projection_path = os.path.join(self.workspace, "mcp-tools.json")
        with open(self.projection_path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(fixture_projection()))
        self.output_dir = os.path.join(self.workspace, "bound")
        self.distribution = os.path.join(self.workspace, "distribution")
        self.corpus = os.path.join(self.workspace, "corpus")

    def test_both_roots_are_substituted_everywhere_they_appear(self):
        result = run(self.workspace, "--projection", self.projection_path,
                     "--output-dir", self.output_dir,
                     "--distribution-root", self.distribution,
                     "--workspace-root", self.corpus)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for host, entry in renderer.HOSTS.items():
            text = Path(self.output_dir,
                        entry["output"]).read_text(encoding="utf-8")
            with self.subTest(host=host):
                self.assertNotIn(renderer.DISTRIBUTION_PLACEHOLDER, text)
                self.assertNotIn(renderer.WORKSPACE_PLACEHOLDER, text)
                self.assertNotIn(renderer.SOURCE_HASH_PLACEHOLDER, text)
        binding = renderer.parse_dotenv(
            Path(self.output_dir,
                 renderer.HOSTS["dsh-env"]["output"]).read_text("utf-8"))

        self.assertEqual(binding[renderer.WORKSPACE_ENV], self.corpus)

    def test_the_shipped_templates_keep_their_placeholders(self):
        for host, entry in renderer.HOSTS.items():
            text = product_path(host).read_text(encoding="utf-8")
            with self.subTest(host=host):
                self.assertIn(renderer.WORKSPACE_PLACEHOLDER, text)



    def test_a_bound_header_reproduces_itself(self):
        """The header's own commands must work on the file carrying them.

        A bound render substitutes real paths, so the bare command names
        neither the file that exists nor the file it would write: running
        `regenerate` puts the placeholders back, and `--check` calls the
        substituted bytes stale. The header therefore has to echo the run.
        """
        out = os.path.join(self.workspace, "bound")
        distribution = os.path.join(self.workspace, "a dir")  # a real space
        corpus = os.path.join(self.workspace, "corpus")
        code = renderer.main([self.workspace, "--projection",
                              self.projection_path, "--output-dir", out,
                              "--distribution-root", distribution,
                              "--workspace-root", corpus])
        self.assertEqual(code, 0)

        header = Path(out, "codex.config.toml").read_text(encoding="utf-8")
        verify = next(line.split(": ", 1)[1] for line in header.splitlines()
                      if line.startswith("# verify: "))

        self.assertIn("--distribution-root", verify)
        self.assertIn("--workspace-root", verify)
        # A path with a space must survive being read back as a command.
        self.assertIn(distribution, shlex.split(verify))
        self.assertIn(corpus, shlex.split(verify))

        # Replay the header's own command: everything after `python3
        # <tool> <root>`, with this test's root and fixture paths.
        replayed = renderer.main(
            [self.workspace] + shlex.split(verify)[3:] +
            ["--projection", self.projection_path, "--output-dir", out])

        self.assertEqual(replayed, 0, "the header's own verify reported stale")

if __name__ == "__main__":
    unittest.main()
