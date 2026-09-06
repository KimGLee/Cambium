"""Managed Node owner: archive safety and pinned publication, no task fixture."""

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from Tools.platform.distribution import node_runtime as owner
from Tools.knowledge.rendering import static_render_runtime
from Tools.platform.common.host_environment import HostEnvironmentUnavailable


ROOT = Path(__file__).resolve().parents[2]


class NodeRuntimeTests(unittest.TestCase):
    def archive(self, entries):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as archive:
            for name, kind, content in entries:
                info = tarfile.TarInfo(name)
                if kind == "link":
                    info.type = tarfile.SYMTYPE
                    info.linkname = content
                    archive.addfile(info)
                else:
                    info.mode = 0o755
                    content = content.encode()
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
        return data.getvalue()

    def test_platform_archive_and_version_follow_the_unique_lock(self):
        contract = json.loads((ROOT / "Tools/platform/distribution/node-toolchain.json").read_text())
        self.assertGreaterEqual(int(contract["version"].split('.')[0][1:]),
            static_render_runtime.runtime_requirements(ROOT)["node_minimum_major"])
        for target, row in contract["archives"].items():
            system, machine = target.split('-')
            with self.subTest(target=target), mock.patch.object(owner.platform, "system",
                    return_value="Windows" if system == "win" else system), \
                    mock.patch.object(owner.platform, "machine", return_value=machine):
                actual = owner.node_requirement(ROOT)
            self.assertEqual(row["sha256"], actual["sha256"])
            self.assertEqual(contract["release_base"] + '/' + contract["version"] + '/' +
                             actual["stem"] + '.' + row["suffix"], actual["url"])
        with mock.patch.object(owner.platform, "machine", return_value="unknown"):
            with self.assertRaises(HostEnvironmentUnavailable):
                owner.node_requirement(ROOT)

    def test_archive_rejects_traversal_escaping_links_and_linked_parents(self):
        bad = [
            [("node/../../outside", "file", "x")],
            [("node/bin/npm", "link", "../../../outside")],
            [("node/bin", "link", "lib"), ("node/bin/npm", "file", "x")],
            [("node/bin/node", "file", "x"), ("node/bin/node", "file", "y")],
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for entries in bad:
                with self.subTest(entries=entries), self.assertRaises(ValueError):
                    owner._extract(self.archive(entries), {"suffix": "tar.gz", "stem": "node"}, root)
                self.assertEqual([], list(root.iterdir()))

    def test_pinned_download_extracts_before_execution_and_preserves_existing_cache(self):
        data = self.archive([("node/bin/node", "file", "fixture node"),
            ("node/lib/node_modules/npm/bin/npm-cli.js", "file", "fixture npm"),
            ("node/bin/npm", "link", "../lib/node_modules/npm/bin/npm-cli.js")])
        request = {"suffix": "tar.gz", "stem": "node", "target": "linux-x64",
            "version": "v24.0.0", "url": "https://nodejs.org/dist/fixture",
            "sha256": hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory).resolve()
            previous = cache / "previous"
            previous.write_bytes(b"untouched")
            download = io.BytesIO(data)
            download.geturl = lambda: request["url"]
            with mock.patch.object(owner, "node_requirement", return_value=request), \
                    mock.patch.object(owner.locked_download.urllib.request, "urlopen", return_value=download), \
                    mock.patch.object(owner.kblib, "run_cambium_subprocess",
                        return_value=SimpleNamespace(returncode=0, stdout=request["version"])):
                node = Path(owner.prepare_node(ROOT, cache))
            self.assertTrue(node.is_relative_to(cache))
            self.assertEqual(b"untouched", previous.read_bytes())
            self.assertTrue(Path(owner.npm_cli(node)).is_relative_to(node.parents[1]))

    def test_checksum_failure_never_extracts_or_executes(self):
        download = io.BytesIO(b"unverified")
        download.geturl = lambda: "https://nodejs.org/dist/fixture"
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(owner, "node_requirement", return_value={
                    "url": download.geturl(), "sha256": "0" * 64}), \
                mock.patch.object(owner.locked_download.urllib.request, "urlopen", return_value=download), \
                mock.patch.object(owner, "_extract") as extract, \
                mock.patch.object(owner.kblib, "run_cambium_subprocess") as execute:
            with self.assertRaisesRegex(ValueError, "checksum"):
                owner.prepare_node(ROOT, Path(directory).resolve())
            self.assertEqual([], list(Path(directory).iterdir()))
            extract.assert_not_called()
            execute.assert_not_called()

    def test_truncated_transfer_resumes_only_the_exact_missing_range(self):
        url = "https://nodejs.org/dist/fixture"
        initial = io.BytesIO(b"abc")
        initial.headers = {"Content-Length": "6"}
        initial.geturl = lambda: url
        initial.getcode = lambda: 200
        remainder = io.BytesIO(b"def")
        remainder.headers = {"Content-Range": "bytes 3-5/6"}
        remainder.geturl = lambda: url
        remainder.getcode = lambda: 206
        with mock.patch.object(owner.locked_download.urllib.request, "urlopen", side_effect=[initial, remainder]) as fetch:
            self.assertEqual(b"abcdef", owner.locked_download.download({"url": url},
                capability_id="fixture-transfer", limit=1024))
        self.assertIsNone(fetch.call_args_list[0].args[0].get_header("Range"))
        self.assertEqual("bytes=3-", fetch.call_args_list[1].args[0].get_header("Range"))


if __name__ == "__main__":
    unittest.main()
