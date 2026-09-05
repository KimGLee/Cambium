"""Local installer predicates; no network or machine-wide installation.

The existing-executable tests isolate the version subprocess boundary. They
prove refusal/reuse behavior, not the authenticity of an arbitrary binary.
Actual Profile evaluation remains covered by the model/admission tests.
"""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from Tools.platform.distribution import install_profile_toolchain as installer


REPOSITORY = Path(__file__).resolve().parents[2]


class ProfileToolchainInstallationContractTests(unittest.TestCase):

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)
        self.destination = self.root / "toolchain"
        self.binary = self.destination / "cue"
        self.contract = json.loads((
            REPOSITORY / "Tools/governance/profile/cue-toolchain.json").read_text())
        for target, value in (("system", "Linux"), ("machine", "x86_64")):
            patcher = mock.patch.object(installer.platform, target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def invoke(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return installer.main(["--destination", str(self.destination)])

    def existing_binary(self):
        self.destination.mkdir()
        self.binary.write_bytes(b"existing caller-owned binary")

    def test_ci_entrypoint_uses_the_same_carried_implementation(self):
        namespace = runpy.run_path(str(REPOSITORY / ".github/scripts/install_cue.py"))
        self.assertIs(installer.main, namespace["main"])

    def test_matching_existing_binary_is_read_only_and_never_downloaded(self):
        self.existing_binary()
        before = self.binary.read_bytes()
        with mock.patch.object(
                installer.kblib, "run_cambium_subprocess",
                return_value=SimpleNamespace(
                    returncode=0, stdout="cue version " + self.contract["version"] + "\n")) as probe, \
                mock.patch.object(installer.urllib.request, "urlopen") as download:
            self.assertEqual(0, self.invoke())
        probe.assert_called_once_with(
            [str(self.binary), "version"], capture_output=True, text=True, timeout=15)
        download.assert_not_called()
        self.assertEqual(before, self.binary.read_bytes())

    def test_existing_version_failures_never_overwrite_or_download(self):
        self.existing_binary()
        before = self.binary.read_bytes()
        for code, output in ((1, "failed"), (0, ""), (0, "cue version v0.0.0\n")):
            with self.subTest(code=code, output=output), mock.patch.object(
                    installer.kblib, "run_cambium_subprocess",
                    return_value=SimpleNamespace(returncode=code, stdout=output)), \
                    mock.patch.object(installer.urllib.request, "urlopen") as download:
                with self.assertRaises(SystemExit):
                    self.invoke()
                download.assert_not_called()
                self.assertEqual(before, self.binary.read_bytes())

    def test_nonregular_existing_target_is_never_executed(self):
        self.destination.mkdir()
        self.binary.symlink_to(self.root / "missing")
        with mock.patch.object(installer.kblib, "run_cambium_subprocess") as probe, \
                mock.patch.object(installer.urllib.request, "urlopen") as download:
            with self.assertRaises(SystemExit):
                self.invoke()
        probe.assert_not_called()
        download.assert_not_called()
        self.assertTrue(self.binary.is_symlink())

    def test_unpinned_platform_is_rejected_before_target_creation(self):
        with mock.patch.object(installer.platform, "machine", return_value="unknown"), \
                mock.patch.object(installer.urllib.request, "urlopen") as download:
            with self.assertRaises(SystemExit):
                self.invoke()
        download.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_archive_checksum_failure_cannot_publish_an_executable(self):
        with mock.patch.object(
                installer.urllib.request, "urlopen", return_value=io.BytesIO(b"untrusted archive")):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.assertFalse(self.binary.exists())


if __name__ == "__main__":
    unittest.main()
