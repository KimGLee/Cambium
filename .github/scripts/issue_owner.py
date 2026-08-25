#!/usr/bin/env python3
"""Require every pull request to name a canonical open Issue owner.

Local investigation notes are deliberately outside the distribution.  A
closing Issue reference is the promotion edge that gives confirmed repository
work a public lifecycle owner before implementation starts.
"""

import argparse
import http.client
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


class IssueOwnerError(ValueError):
    """The pull request has no valid canonical Issue owner."""


_CLOSING_KEYWORD = r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)"


def closing_issue_numbers(body, repository):
    """Return repository-local Issue numbers named by closing references."""
    if not isinstance(body, str):
        body = ""
    if not isinstance(repository, str) or repository.count("/") != 1:
        raise IssueOwnerError("repository must have owner/name form")
    local = r"#(?P<short>[1-9][0-9]*)"
    absolute = (
        r"https://github\.com/%s/issues/(?P<absolute>[1-9][0-9]*)" %
        re.escape(repository)
    )
    pattern = re.compile(
        r"(?i)\b%s\s+(?:%s|%s)" % (_CLOSING_KEYWORD, local, absolute)
    )
    numbers = []
    for match in pattern.finditer(body):
        number = match.group("short") or match.group("absolute")
        parsed = int(number)
        if parsed not in numbers:
            numbers.append(parsed)
    return tuple(numbers)


def validate_owner_issues(body, repository, load_issue):
    """Validate every closing reference and return its Issue numbers."""
    numbers = closing_issue_numbers(body, repository)
    if not numbers:
        raise IssueOwnerError(
            "pull request body must contain Closes/Fixes/Resolves #<open-issue>")
    for number in numbers:
        issue = load_issue(number)
        if not isinstance(issue, dict):
            raise IssueOwnerError("Issue #%d returned no object" % number)
        if "pull_request" in issue:
            raise IssueOwnerError(
                "#%d is a pull request, not an Issue owner" % number)
        if issue.get("number") != number:
            raise IssueOwnerError(
                "Issue lookup for #%d returned a different object" % number)
        if issue.get("state") != "open":
            raise IssueOwnerError(
                "owner Issue #%d must be open while the PR is reviewed" %
                number)
    return numbers


def github_issue_loader(repository, token):
    """Return a loader for repository Issues through the GitHub REST API."""
    if not token:
        raise IssueOwnerError("GITHUB_TOKEN is required for Issue validation")
    owner, name = repository.split("/", 1)
    base = "https://api.github.com/repos/%s/%s/issues/" % (
        urllib.parse.quote(owner, safe=""),
        urllib.parse.quote(name, safe=""),
    )

    def load(number):
        request = urllib.request.Request(
            base + str(number),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer %s" % token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "cambium-issue-owner-check",
            },
        )
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code != 429 and exc.code < 500:
                    raise IssueOwnerError(
                        "cannot validate owner Issue #%d: HTTP %d" %
                        (number, exc.code))
                last_error = exc
            except (OSError, UnicodeError, json.JSONDecodeError,
                    http.client.HTTPException, urllib.error.URLError) as exc:
                last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
        raise IssueOwnerError(
            "cannot validate owner Issue #%d after 3 attempts: %s" %
            (number, last_error))

    return load


def _parser():
    parser = argparse.ArgumentParser(
        description="Validate a PR closing reference against an open Issue")
    parser.add_argument(
        "--event-path", default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument(
        "--event-name", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    parser.add_argument(
        "--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.event_name != "pull_request":
        print("issue_owner: SKIP — event is %s" %
              (args.event_name or "unspecified"))
        return 0
    try:
        if not args.event_path:
            raise IssueOwnerError("GITHUB_EVENT_PATH is required")
        event = json.loads(Path(args.event_path).read_text(encoding="utf-8"))
        pull_request = event.get("pull_request")
        if not isinstance(pull_request, dict):
            raise IssueOwnerError("event has no pull_request object")
        numbers = validate_owner_issues(
            pull_request.get("body"), args.repository,
            github_issue_loader(
                args.repository, os.environ.get("GITHUB_TOKEN")),
        )
    except (OSError, UnicodeError, json.JSONDecodeError,
            IssueOwnerError) as exc:
        print("issue_owner: FAIL — %s" % exc, file=sys.stderr)
        return 1
    print("issue_owner: PASS — %s" %
          ", ".join("#%d" % number for number in numbers))
    return 0


if __name__ == "__main__":
    sys.exit(main())
