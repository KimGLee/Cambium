"""Host bootstrap owners: local objects/checkpoints, never a task lifecycle."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from Tools.platform.common import host_toolchain
from Tools.platform.common.host_environment import HostEnvironmentUnavailable
from Tools.platform.distribution import prepare_host, prepare_host_toolchain
from Tools.platform.agent_interface import inspect_host


ROOT = Path(__file__).resolve().parents[2]


class HostToolchainContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cambium-host-test-")
        self.addCleanup(self.directory.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(Path(self.directory.name).resolve())})
        patch.start()
        self.addCleanup(patch.stop)

    def test_request_uses_owner_bytes_and_changes_identity_when_owner_changes(self):
        before = host_toolchain.requirements(ROOT)
        read = Path.read_bytes
        def altered(path):
            data = read(path)
            return data + b"\n# changed owner\n" if path.name == "requirements-host.txt" else data
        with mock.patch.object(Path, "read_bytes", altered):
            after = host_toolchain.requirements(ROOT)
        self.assertNotEqual(before["key"], after["key"])
        self.assertEqual(before["packages"], after["packages"])

    def test_explicit_broken_binding_never_falls_back_or_installs(self):
        failure = HostEnvironmentUnavailable("missing", capability_id=host_toolchain.CAPABILITY_ID,
                                             code="missing", resource="/missing/python")
        with mock.patch.dict(os.environ, {host_toolchain.PYTHON_ENV: "/missing/python"}), \
                mock.patch.object(host_toolchain, "verify_python", side_effect=failure), \
                mock.patch.object(host_toolchain, "verify_cue", return_value={}), \
                mock.patch.object(prepare_host_toolchain.kblib, "run_cambium_subprocess") as child:
            result = prepare_host_toolchain.prepare(ROOT, apply=True)
        self.assertEqual("configure", result["diagnostics"][0]["remedy"])
        self.assertFalse(result["published"])
        child.assert_not_called()

    def test_wrong_package_version_is_host_unavailable_not_a_profile_verdict(self):
        request = host_toolchain.requirements(ROOT)
        result = {"python": [3, 12, 0], "packages": {key: None for key in request["packages"]}}
        with mock.patch.object(host_toolchain, "_run", return_value=json.dumps(result)):
            with self.assertRaises(HostEnvironmentUnavailable):
                host_toolchain.verify_python(sys.executable, request["packages"])

    def test_binding_rejects_contract_drift_before_resource_execution(self):
        target = host_toolchain.binding_path(ROOT)
        target.parent.mkdir(parents=True)
        document = {"schema_version": 1, "source_hashes": {}, "python": "/python", "cue": "/cue"}
        target.write_text(json.dumps(document))
        with mock.patch.object(host_toolchain, "_run") as child:
            with self.assertRaises(ValueError):
                host_toolchain.observe(ROOT)
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch.object(host_toolchain, "binding_document", side_effect=ValueError("bad Host binding")):
                    with self.assertRaises(HostEnvironmentUnavailable) as failure:
                        host_toolchain.select_cue(ROOT)
                    self.assertEqual("configure", failure.exception.remedy)
        child.assert_not_called()

    def test_valid_resources_publish_then_reuse_without_installation(self):
        with mock.patch.object(host_toolchain, "verify_python", return_value={"version": "ok"}), \
                mock.patch.object(host_toolchain, "verify_cue", return_value={"version": "ok"}), \
                mock.patch.object(host_toolchain.shutil, "which", return_value="/fixture/cue"), \
                mock.patch.object(prepare_host_toolchain.kblib, "run_cambium_subprocess") as child:
            first = prepare_host_toolchain.prepare(ROOT, apply=True)
            second = prepare_host_toolchain.prepare(ROOT, apply=True)
        self.assertTrue(first["published"])
        self.assertTrue(second["published"])
        self.assertEqual(first["bindings"], second["bindings"])
        self.assertEqual([], second["created"])
        child.assert_not_called()


class HostPreparationCompositionTests(unittest.TestCase):
    def test_later_failure_preserves_completed_provider_and_failed_stage(self):
        completed = {"result": "ready", "published": True, "created": ["/host/candidate"]}
        failure = HostEnvironmentUnavailable("renderer cannot launch", capability_id="render", code="launch")
        with mock.patch.object(prepare_host.prepare_host_toolchain, "prepare", return_value=completed), \
                mock.patch.object(prepare_host.prepare_rendering_runtime, "prepare_runtime",
                                  side_effect=[{"result": "ready"}, failure]):
            result = prepare_host.prepare(ROOT, apply=True, rendering=True)
        self.assertEqual(completed, result["toolchain"])
        self.assertEqual("rendering", result["stage"])
        self.assertEqual("needs-preparation", result["result"])
        self.assertIsNone(result["rendering"])
        self.assertEqual(failure.diagnostic(), result["diagnostics"][0])

    def test_projection_target_refuses_carried_cross_workspace_before_preparation(self):
        with tempfile.TemporaryDirectory(prefix="host-target-") as directory, \
                mock.patch.object(prepare_host.prepare_host_toolchain, "prepare") as provider:
            with self.assertRaisesRegex(ValueError, "must be identical"):
                prepare_host.prepare(ROOT, workspace=directory, projection_target="carried-runtime", apply=True)
        provider.assert_not_called()

    def test_preview_never_applies_or_generates_host_config(self):
        toolchain = {"result": "needs-preparation"}
        with mock.patch.object(prepare_host.prepare_host_toolchain, "prepare", return_value=toolchain) as provider, \
                mock.patch.object(prepare_host.prepare_rendering_runtime, "prepare_runtime") as renderer, \
                mock.patch.object(prepare_host, "_host_stage") as host:
            result = prepare_host.prepare(ROOT, host="codex")
        provider.assert_called_once_with(ROOT, configuration=True)
        renderer.assert_not_called()
        host.assert_not_called()
        self.assertFalse(result["consumer_observed"])

    def test_missing_bootstrap_cannot_continue_to_rendering_or_host_install(self):
        with mock.patch.object(prepare_host.prepare_host_toolchain, "prepare",
                               return_value={"result": "needs-preparation"}) as provider, \
                mock.patch.object(prepare_host.prepare_rendering_runtime, "prepare_runtime",
                                  return_value={"result": "ready"}) as renderer, \
                mock.patch.object(prepare_host.kblib, "run_cambium_subprocess") as child:
            result = prepare_host.prepare(ROOT, apply=True, rendering=True, host="codex")
        self.assertEqual(2, provider.call_count)
        renderer.assert_called_once_with(ROOT, constructs=())
        child.assert_not_called()
        self.assertEqual("needs-preparation", result["result"])

    def test_actual_consumer_inspection_uses_process_not_prepared_python(self):
        with mock.patch.object(inspect_host.host_toolchain, "observe", return_value={"result": "ready"}) as observe, \
                mock.patch.object(inspect_host.static_render_runtime, "probe_runtime") as render:
            result = inspect_host.observe(ROOT)
        observe.assert_called_once_with(ROOT, current_process=True)
        render.assert_not_called()
        self.assertFalse(result["installed_by_this_call"])
        self.assertEqual(sys.executable, result["process_python"])


if __name__ == "__main__":
    unittest.main()
