"""Host setup owner tests: no corpus fixture, lifecycle replay, or real CLI."""

from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from Tools.knowledge.rendering import static_render_runtime as runtime
from Tools.platform.distribution import prepare_rendering_runtime as setup


REPOSITORY = Path(__file__).resolve().parents[2]


class RenderingHostPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.host = Path(self.temporary.name).resolve()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.host)}, clear=True))
        self.stack.enter_context(mock.patch.object(runtime, "_version", side_effect=lambda path:
            "v22.19.0" if Path(path).name == "node" else "Google Chrome 140.0.0"))
        self.stack.enter_context(mock.patch.object(runtime, "_discover_executable", return_value=[]))
        self.requirement = runtime.runtime_requirements(REPOSITORY)
        self.node = self.host / "node"
        self.node.write_text("host executable placeholder")
        self.node.chmod(0o700)
        self.browser = self.host / "chrome"
        self.browser.write_text("host browser placeholder")
        self.browser.chmod(0o700)

    def installed(self):
        package = self.host / "installed"
        package.mkdir(exist_ok=True)
        for name, source in (("package.json", self.requirement["manifest"]),
                             ("package-lock.json", self.requirement["lock"])):
            shutil.copyfile(source, package / name)
        for relative, row in self.requirement["packages"].items():
            if relative:
                target = package / relative / "package.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({"version": row["version"]}))
        return {"CAMBIUM_RENDER_NODE": str(self.node),
                "CAMBIUM_RENDER_NODE_MODULES": str(package / "node_modules")}

    def publish(self, bindings):
        target = runtime.default_runtime_bindings_path(REPOSITORY)
        target.parent.mkdir(parents=True, exist_ok=True)
        setup._publish_bindings(REPOSITORY, target, bindings)
        return target

    def test_requirements_come_from_registered_capability_and_npm_owner(self):
        source = json.loads(Path(self.requirement["manifest"]).read_text())
        self.assertEqual(source["engines"]["node"], self.requirement["node_engine"])
        self.assertEqual(source["dependencies"], self.requirement["dependencies"])
        setup._installation_inputs(self.requirement)

    def test_default_probe_does_not_install_or_create_cache(self):
        with mock.patch.object(setup.kblib, "run_cambium_subprocess") as child:
            result = setup.prepare_runtime(REPOSITORY)
        self.assertEqual("needs-preparation", result["result"])
        self.assertFalse(Path(result["bindings_path"]).parent.exists())
        child.assert_not_called()

    def test_parser_ready_without_browser_but_rendering_is_not_ready(self):
        self.publish(self.installed())
        self.assertEqual("ready", runtime.probe_runtime(REPOSITORY)["result"])
        result = runtime.probe_runtime(REPOSITORY, require_browser=True)
        self.assertEqual("needs-preparation", result["result"])
        self.assertTrue(any("CAMBIUM_RENDER_BROWSER" in value for value in result["findings"]))

    def test_explicit_valid_binding_precedes_managed_binding_and_bad_explicit_fails_closed(self):
        bindings = self.installed()
        with mock.patch.dict(os.environ, bindings), \
                mock.patch.object(runtime, "read_runtime_bindings", side_effect=AssertionError("must not consult cache")):
            self.assertEqual("ready", runtime.probe_runtime(REPOSITORY)["result"])
            os.environ["CAMBIUM_RENDER_NODE"] = "relative/node"
            self.assertEqual("invalid", runtime.probe_runtime(REPOSITORY)["result"])
        target = self.publish(bindings)
        moved = self.host / "new-node" / "node"
        moved.parent.mkdir()
        self.node.rename(moved)
        with self.assertRaisesRegex(runtime.StaticRenderRuntimeError, "unavailable"):
            runtime.read_runtime_bindings(REPOSITORY, target)
        with mock.patch.object(runtime, "_discover_executable", side_effect=lambda name: [str(moved)] if name == "node" else []), \
                mock.patch.object(runtime, "verify_runtime_bindings", return_value={"result": "pass"}):
            result = setup.prepare_runtime(REPOSITORY, apply=True)
        self.assertEqual("ready", result["result"])
        self.assertEqual(str(moved), runtime.read_runtime_bindings(REPOSITORY, target)["CAMBIUM_RENDER_NODE"])

    def test_binding_schema_staleness_and_repository_location_are_rejected(self):
        target = self.publish(self.installed())
        document = json.loads(target.read_text())
        for change in ({"schema_version": True}, {"schema_version": 1.0}, {"unknown": "value"}):
            with self.subTest(change=change):
                invalid = dict(document, **change)
                target.write_text(json.dumps(invalid))
                with self.assertRaisesRegex(runtime.StaticRenderRuntimeError, "Invalid rendering Host binding document"):
                    runtime.read_runtime_bindings(REPOSITORY, target)
        document["package_lock_sha256"] = "sha256:" + "0" * 64
        target.write_text(json.dumps(document))
        with self.assertRaisesRegex(runtime.StaticRenderRuntimeError, "stale"):
            runtime.read_runtime_bindings(REPOSITORY, target)
        with self.assertRaisesRegex(runtime.StaticRenderRuntimeError, "outside the repository"):
            runtime.read_runtime_bindings(REPOSITORY, REPOSITORY / ".cambium/bindings.json")
        target.unlink()
        target.symlink_to(self.host / "missing-bindings.json")
        with self.assertRaisesRegex(runtime.StaticRenderRuntimeError, "regular file"):
            runtime.read_runtime_bindings(REPOSITORY)

    def test_transitive_dependency_versions_are_verified_not_just_direct_packages(self):
        bindings = self.installed()
        nested = next(path for path in self.requirement["packages"] if path and
                      path.removeprefix("node_modules/") not in self.requirement["dependencies"])
        target = Path(bindings["CAMBIUM_RENDER_NODE_MODULES"]).parent / nested / "package.json"
        target.write_text('{"version":"0.0.0"}')
        with mock.patch.dict(os.environ, bindings):
            self.assertEqual("invalid", runtime.probe_runtime(REPOSITORY)["result"])

    def test_locked_install_disables_scripts_uses_fresh_cache_and_smokes_before_publish(self):
        bindings = {"CAMBIUM_RENDER_NODE": str(self.node)}
        order = []
        def installed(*args, **kwargs):
            command = args[0]
            self.assertIn("--ignore-scripts", command)
            self.assertIn("--strict-ssl=true", command)
            self.assertEqual(300, kwargs["timeout"])
            self.assertTrue(Path(kwargs["cwd"]).is_relative_to(self.host))
            self.assertNotEqual(kwargs["env"]["NPM_CONFIG_USERCONFIG"],
                                kwargs["env"]["NPM_CONFIG_GLOBALCONFIG"])
            self.assertEqual("", Path(kwargs["env"]["NPM_CONFIG_USERCONFIG"]).read_text())
            order.append("install")
            return subprocess.CompletedProcess(command, 0, "", "")
        def smoke(*args, **kwargs):
            order.append("smoke")
            self.assertFalse(runtime.default_runtime_bindings_path(REPOSITORY).exists())
            return {"result": "pass"}
        with mock.patch.object(runtime, "probe_runtime", return_value={"result": "needs-preparation", "bindings": bindings, "findings": []}), \
                mock.patch.object(setup.shutil, "which", return_value="/usr/bin/npm"), \
                mock.patch.object(setup.kblib, "run_cambium_subprocess", side_effect=installed), \
                mock.patch.object(runtime, "verify_runtime_bindings", side_effect=smoke), \
                mock.patch.object(runtime, "read_runtime_bindings", side_effect=lambda root, target: json.loads(target.read_text())["bindings"]):
            result = setup.prepare_runtime(REPOSITORY, apply=True)
        self.assertEqual(["install", "smoke"], order)
        self.assertEqual("ready", result["result"])
        self.assertTrue(Path(result["bindings_path"]).exists())
        self.assertFalse((REPOSITORY / ".cambium/bindings.json").exists())

    def test_repeated_preparation_reuses_valid_dependencies_without_npm(self):
        self.publish(self.installed())
        with mock.patch.object(setup.kblib, "run_cambium_subprocess") as child, \
                mock.patch.object(runtime, "verify_runtime_bindings", return_value={"result": "pass"}) as smoke:
            self.assertEqual("ready", setup.prepare_runtime(REPOSITORY, apply=True)["result"])
            self.assertEqual("ready", setup.prepare_runtime(REPOSITORY, apply=True)["result"])
        child.assert_not_called()
        self.assertEqual(2, smoke.call_count)

    def test_explicit_preparation_can_add_browser_to_parser_only_binding(self):
        initial = self.installed()
        target = self.publish(initial)
        with mock.patch.dict(os.environ, {"CAMBIUM_RENDER_BROWSER": str(self.browser)}), \
                mock.patch.object(runtime, "verify_runtime_bindings", return_value={"result": "pass"}):
            result = setup.prepare_runtime(REPOSITORY, apply=True, require_browser=True)
        self.assertEqual("ready", result["result"])
        upgraded = runtime.read_runtime_bindings(REPOSITORY, target)
        self.assertEqual(str(self.browser), upgraded.pop("CAMBIUM_RENDER_BROWSER"))
        self.assertEqual(initial, upgraded)

    def test_failed_smoke_cannot_publish_bindings(self):
        with mock.patch.dict(os.environ, self.installed()), \
                mock.patch.object(runtime, "verify_runtime_bindings", side_effect=runtime.StaticRenderRuntimeError("smoke failed")):
            with self.assertRaisesRegex(runtime.StaticRenderRuntimeError, "smoke failed"):
                setup.prepare_runtime(REPOSITORY, apply=True)
        self.assertFalse(runtime.default_runtime_bindings_path(REPOSITORY).exists())

    def test_unsafe_lock_urls_links_and_integrity_are_rejected(self):
        first = next(path for path in self.requirement["packages"] if path)
        for change in ({"resolved": "http://registry.npmjs.org/package.tgz"},
                       {"resolved": "https://example.invalid/package.tgz"},
                       {"link": True}, {"integrity": ""}):
            with self.subTest(change=change):
                document = copy.deepcopy(self.requirement)
                document["packages"][first].update(change)
                with self.assertRaisesRegex(runtime.StaticRenderRuntimeError, "Unsafe or unlocked"):
                    setup._installation_inputs(document)


if __name__ == "__main__":
    unittest.main()
