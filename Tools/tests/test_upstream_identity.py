"""Owner tests for the current upstream Git commit identity."""

from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import Tools.platform.distribution.upstream_identity as upstream_identity


class UpstreamIdentityContractTests(unittest.TestCase):
    def test_full_commit_identity_is_one_closed_sha_shape(self):
        accepted = ("a" * 40, "b" * 64)
        rejected = (
            "a" * 39,
            "a" * 41,
            "A" * 40,
            "sha256:" + "a" * 64,
            "release-name",
            "",
            None,
        )
        for value in accepted:
            with self.subTest(value=value):
                self.assertTrue(upstream_identity.is_full_commit_sha(value))
        for value in rejected:
            with self.subTest(value=value):
                self.assertFalse(upstream_identity.is_full_commit_sha(value))

    def test_root_and_ref_inputs_fail_closed_before_git(self):
        with self.assertRaisesRegex(
                upstream_identity.UpstreamIdentityError,
                "not an existing directory"):
            upstream_identity.resolve_revision(
                "/definitely/not/a/current/upstream", "HEAD")

        invalid_refs = (None, "", " HEAD", "HEAD ", "HEAD\n", "HEAD\0x",
                        "--help")
        with mock.patch.object(
                upstream_identity.os.path, "isdir", return_value=True), \
                mock.patch.object(
                    upstream_identity.kblib,
                    "run_cambium_subprocess") as run_git:
            for revision in invalid_refs:
                with self.subTest(revision=revision):
                    with self.assertRaisesRegex(
                            upstream_identity.UpstreamIdentityError,
                            "one non-empty Git revision argument"):
                        upstream_identity.resolve_revision(
                            "/synthetic/upstream", revision)
            run_git.assert_not_called()

    def test_git_transport_and_response_form_one_fail_closed_contract(self):
        complete = "c" * 40
        with mock.patch.object(
                upstream_identity.os.path, "isdir", return_value=True), \
                mock.patch.object(
                    upstream_identity.kblib, "run_cambium_subprocess",
                    return_value=SimpleNamespace(
                        returncode=0, stdout=complete + "\n",
                        stderr="")) as run_git:
            self.assertEqual(
                complete, upstream_identity.resolve_revision(
                    "/synthetic/upstream", "main"))
            command = run_git.call_args.args[0]
            self.assertEqual(
                ["rev-parse", "--verify", "--end-of-options",
                 "main^{commit}"],
                command[-4:])
            self.assertEqual(
                "1", run_git.call_args.kwargs["env"]["GIT_NO_REPLACE_OBJECTS"])

        responses = (
            SimpleNamespace(returncode=1, stdout="", stderr="unknown ref"),
            SimpleNamespace(returncode=0, stdout="not-a-sha\n", stderr=""),
            SimpleNamespace(
                returncode=0,
                stdout=("d" * 40) + "\n" + ("e" * 40) + "\n",
                stderr=""),
        )
        with mock.patch.object(
                upstream_identity.os.path, "isdir", return_value=True):
            for response in responses:
                with self.subTest(response=response):
                    with mock.patch.object(
                            upstream_identity.kblib,
                            "run_cambium_subprocess",
                            return_value=response), self.assertRaises(
                                upstream_identity.UpstreamIdentityError):
                        upstream_identity.resolve_revision(
                            "/synthetic/upstream", "main")


class UpstreamIdentityGitIntegrationTests(unittest.TestCase):
    def test_ref_and_explicit_commit_remain_bound_across_worktree_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "upstream"
            root.mkdir()

            def git(*arguments):
                completed = subprocess.run(
                    ["git", "-C", str(root), *arguments],
                    text=True, capture_output=True, check=False)
                self.assertEqual(
                    0, completed.returncode,
                    completed.stdout + completed.stderr)

            git("init", "-q")
            page = root / "contract.txt"
            page.write_text("first\n", encoding="utf-8")
            git("add", "contract.txt")
            git("-c", "user.name=Cambium Test",
                "-c", "user.email=cambium@example.test",
                "commit", "-qm", "first")

            first = upstream_identity.resolve_revision(root, "HEAD")
            page.write_text("dirty worktree\n", encoding="utf-8")
            self.assertEqual(
                first, upstream_identity.resolve_revision(root, "HEAD"))

            git("add", "contract.txt")
            git("-c", "user.name=Cambium Test",
                "-c", "user.email=cambium@example.test",
                "commit", "-qm", "second")
            second = upstream_identity.resolve_revision(root, "HEAD")
            self.assertNotEqual(first, second)
            self.assertEqual(
                first, upstream_identity.resolve_revision(root, first[:12]))


if __name__ == "__main__":
    unittest.main()
