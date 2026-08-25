import importlib.util
import http.client
import json
from pathlib import Path
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / ".github" / "scripts" / "issue_owner.py"
SPEC = importlib.util.spec_from_file_location("issue_owner", SCRIPT)
issue_owner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(issue_owner)


class IssueOwnerTests(unittest.TestCase):

    def test_accepts_local_and_absolute_closing_references(self):
        body = (
            "Closes #12\n"
            "Fixes https://github.com/KimGLee/Cambium/issues/34\n"
            "Related to #56\n"
            "Closes #12\n"
        )
        self.assertEqual(
            (12, 34),
            issue_owner.closing_issue_numbers(
                body, "KimGLee/Cambium"),
        )

    def test_rejects_missing_closing_reference(self):
        with self.assertRaisesRegex(
                issue_owner.IssueOwnerError, "must contain"):
            issue_owner.validate_owner_issues(
                "Related to #12", "KimGLee/Cambium", lambda _number: {})

    def test_does_not_accept_another_repository_issue(self):
        self.assertEqual(
            (),
            issue_owner.closing_issue_numbers(
                "Closes https://github.com/elsewhere/project/issues/12",
                "KimGLee/Cambium",
            ),
        )

    def test_rejects_pull_request_number(self):
        with self.assertRaisesRegex(
                issue_owner.IssueOwnerError, "pull request"):
            issue_owner.validate_owner_issues(
                "Closes #12", "KimGLee/Cambium",
                lambda number: {
                    "number": number, "state": "open", "pull_request": {},
                },
            )

    def test_rejects_closed_issue(self):
        with self.assertRaisesRegex(issue_owner.IssueOwnerError, "must be open"):
            issue_owner.validate_owner_issues(
                "Resolves #12", "KimGLee/Cambium",
                lambda number: {"number": number, "state": "closed"},
            )

    def test_rejects_mismatched_issue_response(self):
        with self.assertRaisesRegex(
                issue_owner.IssueOwnerError, "different object"):
            issue_owner.validate_owner_issues(
                "Fixes #12", "KimGLee/Cambium",
                lambda _number: {"number": 13, "state": "open"},
            )

    def test_accepts_real_open_issue_shape(self):
        self.assertEqual(
            (165,),
            issue_owner.validate_owner_issues(
                "Closes #165", "KimGLee/Cambium",
                lambda number: {"number": number, "state": "open"},
            ),
        )

    def test_github_loader_retries_an_incomplete_response(self):
        payload = json.dumps({"number": 165, "state": "open"}).encode()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return payload

        loader = issue_owner.github_issue_loader(
            "KimGLee/Cambium", "test-token")
        with mock.patch.object(
                issue_owner.urllib.request, "urlopen",
                side_effect=(
                    http.client.IncompleteRead(b"partial", 10), Response(),
                )) as urlopen, mock.patch.object(issue_owner.time, "sleep"):
            self.assertEqual(
                {"number": 165, "state": "open"}, loader(165))
        self.assertEqual(2, urlopen.call_count)


if __name__ == "__main__":
    unittest.main()
