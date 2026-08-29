"""End-to-end tests for the upstream component byte boundary."""

import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import upstream_component_boundary as boundary  # noqa: E402
import compile_cli_contract  # noqa: E402
import module_boundary_facts  # noqa: E402
import render_host_configs  # noqa: E402


CHECKER = TOOLS / "check_upstream_components.py"

BOUNDARY = """schema_version: 1
distribution_only:
  - path: Tools/tests/
    reason: "distribution test suite"
  - path: Tools/compiled/cli-contract.yaml
    reason: "source distribution CLI projection"
  - path: Tools/compiled/mcp-tools.json
    reason: "source distribution MCP projection"
  - path: Tools/compiled/host-configs/
    reason: "source distribution host templates"
  - path: profiles/_template/
    reason: "distribution Profile authoring form"
"""

SOURCE_FILES = {
    "kernel/K00/rule.md": "kernel rule\n",
    "Card/R01.md": "card\n",
    "Read Set/R01.md": "read set\n",
    "Tools/runtime.py": "VALUE = 1\n",
    "Tools/tests/test_distribution.py": "def test_upstream(): pass\n",
    "Tools/compiled/cli-contract.yaml": "artifact: cli\n",
    "Tools/compiled/mcp-tools.json": "{\"artifact\":\"mcp\"}\n",
    "Tools/compiled/host-configs/codex.toml": "[mcp]\n",
    "Tools/compiled/metadata-execution-contract.json":
        "{\"artifact\":\"metadata\"}\n",
    "profiles/README.md": "profile guide\n",
    "profiles/_template/profile.md": "template only\n",
    "distribution-boundary.yaml": BOUNDARY,
}


class UpstreamComponentBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.upstream = self.base / "upstream"
        self.adopter = self.base / "adopter"
        self.upstream.mkdir()
        self.adopter.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "tests@example.invalid")
        self._git("config", "user.name", "Cambium tests")
        for relative, text in SOURCE_FILES.items():
            self._write(self.upstream / relative, text)
        self._git("add", ".")
        self._git("commit", "-q", "-m", "upstream v1")
        self.revision_v1 = self._git("rev-parse", "HEAD").stdout.strip()
        self._install_adopter()

    def _git(self, *args):
        completed = subprocess.run(
            ["git", "-C", str(self.upstream), *args],
            text=True, capture_output=True, check=False)
        self.assertEqual(
            0, completed.returncode, completed.stdout + completed.stderr)
        return completed

    @staticmethod
    def _write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _install_adopter(self):
        for relative in (
                "kernel/K00/rule.md", "Card/R01.md", "Read Set/R01.md",
                "Tools/runtime.py",
                "Tools/compiled/metadata-execution-contract.json",
                "profiles/README.md",
                "distribution-boundary.yaml"):
            destination = self.adopter / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.upstream / relative, destination)
        # This is adopter-owned configuration and is intentionally not copied
        # from the upstream Profile authoring kit.
        self._write(
            self.adopter / "profiles/my-knowledge-base/profile.md",
            "# Confirmed adopter Profile\n")

    def _evaluate(self, revision=None):
        return boundary.evaluate(
            self.adopter, self.upstream, revision or self.revision_v1)

    def _checker(self, *extra):
        return subprocess.run(
            [sys.executable, str(CHECKER), str(self.adopter),
             "--upstream-root", str(self.upstream),
             "--revision", self.revision_v1, *extra],
            text=True, capture_output=True, check=False)

    def test_exact_components_and_upstream_declared_omission_pass(self):
        report = self._evaluate()
        self.assertEqual((), report.errors)
        self.assertEqual(self.revision_v1, report.upstream_revision_id)
        self.assertEqual(7, report.present_count)
        self.assertEqual(4, report.omitted_count)
        self.assertEqual(
            [
                "Tools/compiled/cli-contract.yaml",
                "Tools/compiled/host-configs/codex.toml",
                "Tools/compiled/mcp-tools.json",
                "Tools/tests/test_distribution.py",
            ],
            [row.path for row in report.rows
             if row.presence == "omitted-distribution-only"])

    def test_selected_profile_is_outside_the_immutable_component_set(self):
        self._write(
            self.adopter / "profiles/my-knowledge-base/extra.yaml",
            "adopter: value\n")
        self.assertEqual((), self._evaluate().errors)

    def test_a_component_byte_change_fails(self):
        self._write(self.adopter / "Card/R01.md", "locally rewritten\n")
        report = self._evaluate()
        self.assertTrue(any(
            "component bytes differ from upstream: Card/R01.md" in error
            for error in report.errors), report.errors)

    def test_an_undeclared_missing_component_fails(self):
        (self.adopter / "Read Set/R01.md").unlink()
        report = self._evaluate()
        self.assertIn(
            "required component is missing: Read Set/R01.md", report.errors)

    def test_adopter_cannot_invent_an_omission_allowlist(self):
        (self.adopter / "Card/R01.md").unlink()
        self._write(
            self.adopter / "distribution-boundary.yaml",
            BOUNDARY +
            "  - path: Card/\n    reason: \"adopter-created exception\"\n")
        report = self._evaluate()
        self.assertIn("required component is missing: Card/R01.md", report.errors)
        self.assertTrue(any(
            "component bytes differ from upstream: distribution-boundary.yaml"
            in error for error in report.errors), report.errors)

    def test_present_distribution_only_bytes_must_still_match(self):
        destination = self.adopter / "Tools/tests/test_distribution.py"
        self._write(destination, "locally modified distribution test\n")
        report = self._evaluate()
        self.assertTrue(any(
            "component bytes differ from upstream: "
            "Tools/tests/test_distribution.py" in error
            for error in report.errors), report.errors)

    def test_extra_file_in_an_immutable_component_fails(self):
        self._write(self.adopter / "Tools/local_override.py", "override = 1\n")
        report = self._evaluate()
        self.assertIn(
            "unregistered file in immutable component: "
            "Tools/local_override.py", report.errors)

    def test_runtime_python_bytecode_is_rejected_as_unverified_executable(self):
        environment = dict(os.environ)
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment.pop("PYTHONPYCACHEPREFIX", None)
        imported = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, 'Tools'); import runtime"],
            cwd=self.adopter, env=environment,
            text=True, capture_output=True, check=False)
        self.assertEqual(
            0, imported.returncode, imported.stdout + imported.stderr)
        self.assertTrue(
            any((self.adopter / "Tools/__pycache__").glob("runtime.*.pyc")))
        report = self._evaluate()
        self.assertTrue(any(
            error.startswith(
                "unregistered file in immutable component: "
                "Tools/__pycache__/runtime.") and error.endswith(".pyc")
            for error in report.errors), report.errors)

    def test_entrypoints_ignore_local_bytecode_and_create_no_local_cache(self):
        """The bootstrap runs before all repository-local Tool imports.

        An unchecked-hash pyc is deliberately valid even though its code does
        not match ``kblib.py``.  A normal import proves the poison is usable;
        each protected real CLI must then ignore it while leaving the local
        cache tree byte-for-byte unchanged.
        """
        entrypoint_root = self.base / "entrypoint-adopter"
        copied_tools = entrypoint_root / "Tools"
        shutil.copytree(
            TOOLS, copied_tools,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        repository = TOOLS.parent
        for component in ("kernel", "Card", "Read Set"):
            shutil.copytree(
                repository / component, entrypoint_root / component,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (entrypoint_root / "profiles").mkdir()
        shutil.copy2(
            repository / "profiles/README.md",
            entrypoint_root / "profiles/README.md")
        shutil.copy2(
            repository / "distribution-boundary.yaml",
            entrypoint_root / "distribution-boundary.yaml")

        evil = self.base / "poison-kblib.py"
        evil.write_text(
            "raise RuntimeError('LOCAL-PYCACHE-WAS-READ')\n",
            encoding="utf-8")
        cache_path = (
            copied_tools / "__pycache__" /
            ("kblib.%s.pyc" % sys.implementation.cache_tag))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        py_compile.compile(
            str(evil), cfile=str(cache_path),
            dfile=str(copied_tools / "kblib.py"), doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)

        environment = dict(os.environ)
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment.pop("PYTHONPYCACHEPREFIX", None)
        unsafe_temp = entrypoint_root / "adopter-controlled-temp"
        unsafe_temp.mkdir()
        environment["TMPDIR"] = str(unsafe_temp)
        unprotected = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, 'Tools'); import kblib"],
            cwd=entrypoint_root, env=environment, text=True,
            capture_output=True, check=False)
        self.assertNotEqual(0, unprotected.returncode)
        self.assertIn(
            "LOCAL-PYCACHE-WAS-READ",
            unprotected.stdout + unprotected.stderr)

        before = {
            path.relative_to(copied_tools).as_posix(): path.read_bytes()
            for path in copied_tools.rglob("*.pyc")
        }
        # Derive both launch surfaces from their existing machine owners.
        # CLI entry points that can reach the component boundary must protect
        # their imports before they validate it; the host registry separately
        # owns the MCP process entry point.  Neither filename set is repeated
        # in this test.
        facts = module_boundary_facts.collect(str(TOOLS.parent))
        graph = module_boundary_facts.import_graph(facts)

        def reaches(start, target):
            pending = [start]
            seen = set()
            while pending:
                current = pending.pop()
                if current == target:
                    return True
                if current in seen:
                    continue
                seen.add(current)
                pending.extend(graph.get(current, ()))
            return False

        protected = {}
        for module, path, _source in compile_cli_contract.discover_tools(
                str(TOOLS.parent)):
            if reaches(module, boundary.__name__):
                relative = Path(path).relative_to(TOOLS).as_posix()
                protected[relative] = ("--help",)

        host_path = Path(render_host_configs.SERVER_ENTRY_POINT)
        self.assertEqual("Tools", host_path.parts[0])
        protected[Path(*host_path.parts[1:]).as_posix()] = ()
        self.assertTrue(protected, "no cache-isolated entry point was found")

        for relative, extra_arguments in sorted(protected.items()):
            name = Path(relative).name
            arguments = [
                sys.executable, str(copied_tools / relative),
                *extra_arguments,
            ]
            completed = subprocess.run(
                arguments,
                cwd=entrypoint_root, env=environment, text=True,
                input="", capture_output=True, check=False)
            self.assertEqual(
                0, completed.returncode,
                "%s\n%s%s" %
                (name, completed.stdout, completed.stderr))
            self.assertNotIn(
                "LOCAL-PYCACHE-WAS-READ",
                completed.stdout + completed.stderr)
            inherited = subprocess.run(
                [
                    sys.executable, "-c",
                    (
                        "import os, runpy, subprocess, sys; "
                        "sys.path.insert(0, os.path.dirname(sys.argv[1])); "
                        "runpy.run_path(sys.argv[1], "
                        "run_name='cambium_bootstrap_probe'); "
                        "prefix = os.environ['PYTHONPYCACHEPREFIX']; "
                        "assert sys.pycache_prefix == prefix; "
                        "assert sys.dont_write_bytecode; "
                        "assert os.environ['PYTHONDONTWRITEBYTECODE'] == '1'; "
                        "assert not os.path.exists(prefix); "
                        "assert os.path.commonpath((prefix, sys.argv[2])) "
                        "!= os.path.realpath(sys.argv[2]); "
                        "child = subprocess.run([sys.executable, '-c', "
                        "'import os, sys; assert sys.dont_write_bytecode; '"
                        "'assert sys.pycache_prefix == '"
                        "'os.environ[\"PYTHONPYCACHEPREFIX\"]']); "
                        "raise SystemExit(child.returncode)"
                    ),
                    str(copied_tools / relative), str(entrypoint_root),
                ],
                cwd=entrypoint_root, env=environment, text=True,
                capture_output=True, check=False)
            self.assertEqual(
                0, inherited.returncode,
                "%s child environment\n%s%s" %
                (name, inherited.stdout, inherited.stderr))
        after = {
            path.relative_to(copied_tools).as_posix(): path.read_bytes()
            for path in copied_tools.rglob("*.pyc")
        }
        self.assertEqual(before, after)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_a_symlink_cannot_substitute_for_component_bytes(self):
        target = self.adopter / "Card/R01.md"
        target.unlink()
        os.symlink(str(self.upstream / "Card/R01.md"), target)
        report = self._evaluate()
        self.assertTrue(any(
            error.startswith("unsafe component Card/R01.md:")
            for error in report.errors), report.errors)

    def test_ref_is_resolved_before_current_worktree_bytes_are_read(self):
        # Neither a later commit nor dirty working-tree bytes may alter the
        # meaning of the already selected v1 revision.
        self._write(self.upstream / "kernel/K00/rule.md", "kernel v2\n")
        self._git("add", "kernel/K00/rule.md")
        self._git("commit", "-q", "-m", "upstream v2")
        self._write(self.upstream / "Tools/runtime.py", "dirty worktree\n")
        report = self._evaluate(self.revision_v1[:12])
        self.assertEqual((), report.errors)
        self.assertEqual(self.revision_v1, report.upstream_revision_id)

    def test_manifest_write_and_check_are_confined_to_derived_state(self):
        written = self._checker("--write-manifest")
        self.assertEqual(
            0, written.returncode, written.stdout + written.stderr)
        path = self.adopter / boundary.DEFAULT_MANIFEST_PATH
        text = path.read_text(encoding="utf-8")
        self.assertIn(
            "# upstream_revision_id: %s" % self.revision_v1, text)
        self.assertIn(
            "Tools/tests/test_distribution.py\t", text)
        checked = self._checker("--check-manifest")
        self.assertEqual(
            0, checked.returncode, checked.stdout + checked.stderr)

        path.write_text(text + "stale\n", encoding="utf-8")
        stale = self._checker("--check-manifest")
        self.assertEqual(2, stale.returncode, stale.stdout + stale.stderr)
        self.assertIn("manifest is stale", stale.stdout + stale.stderr)

        relocated = self._checker(
            "--manifest", "Tools/upstream-manifest.tsv", "--write-manifest")
        self.assertNotEqual(
            0, relocated.returncode, relocated.stdout + relocated.stderr)
        self.assertIn("unrecognized arguments", relocated.stderr)

    def test_unknown_revision_fails_without_a_manifest(self):
        result = subprocess.run(
            [sys.executable, str(CHECKER), str(self.adopter),
             "--upstream-root", str(self.upstream),
             "--revision", "not-a-real-ref", "--write-manifest"],
            text=True, capture_output=True, check=False)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            "cannot resolve upstream revision", result.stdout + result.stderr)
        self.assertFalse(
            (self.adopter / boundary.DEFAULT_MANIFEST_PATH).exists())


if __name__ == "__main__":
    unittest.main()
