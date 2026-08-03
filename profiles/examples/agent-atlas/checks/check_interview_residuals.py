#!/usr/bin/env python3
"""Find Interview Card answer structures outside the registered expression root.

Content findings are candidates only: exit 2 requests disposition review and
never authorizes deletion or reclassification. Exit 1 is reserved for an
invalid invocation, unreadable input, unsafe symlink, or time-budget failure.
Exit 0 means the completed scan found no candidate in its effective scope.
"""

import argparse
import json
import os
import re
import sys
import time
import uuid


TOOL = "check_interview_residuals"
TOOL_VERSION = "1.0.0"
DEFAULT_TIME_LIMIT = 55.0
DEFAULT_TOP_LEVEL_EXCLUDES = {
    ".git",
    ".hg",
    ".svn",
    "Tools",
    "kernel",
    "node_modules",
    "profiles",
}

TYPE_RE = re.compile(
    r"^\s*type\s*:\s*[\"']?interview-card[\"']?\s*(?:#.*)?$",
    re.IGNORECASE | re.MULTILINE,
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
BILINGUAL_SUFFIX_RE = re.compile(r"\s*[（(][^）)]*[）)]\s*$")
# Strip an actual outline prefix ("1.", "2)", "3、"), but preserve the
# semantic duration in headings such as "30-Second Answer" and "90 秒回答".
LEADING_NUMBER_RE = re.compile(r"^\s*\d+(?:\.\d+)*[.)、:]\s*")
SPACE_RE = re.compile(r"[\s_-]+")

EXPLICIT_HEADINGS = {
    "interview card",
    "interview answer",
    "interview question",
    "30 second answer",
    "90 second answer",
    "common follow ups",
    "common followups",
    "follow up answers",
    "strong answer signals",
    "weak answer signals",
    "面试卡",
    "面试卡片",
    "面试回答",
    "面试问题",
    "30 秒回答",
    "90 秒回答",
    "常见追问",
    "追问答案",
    "强回答信号",
    "弱回答信号",
}
SUPPORT_HEADINGS = EXPLICIT_HEADINGS | {
    "core knowledge links",
    "deep dive follow up tree",
    "common misconceptions",
    "comparison questions",
    "scenario questions",
    "self test questions",
    "核心知识链接",
    "深挖追问树",
    "常见误解",
    "比较类问题",
    "场景类问题",
    "自测问题",
}


def receipt(check, target, result, details, sequence, run_token):
    now = time.time()
    return {
        "receipt_id": "audit-%s-%s-%s-%04d" % (
            TOOL,
            time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now)),
            run_token,
            sequence,
        ),
        "check": check,
        "target": target,
        "result": result,
        "details": details,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "invalidated_by": None,
    }


def write_receipts(path, items):
    if not path:
        return
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def normalize_relative_path(value):
    normalized = os.path.normpath(value.strip()).replace(os.sep, "/")
    if not value.strip() or normalized in (".", ".."):
        raise ValueError("expression root must be a non-empty relative subpath")
    if os.path.isabs(value) or normalized.startswith("../"):
        raise ValueError("expression root must remain inside the vault root")
    return normalized


def is_under(relative_path, root_path):
    return relative_path == root_path or relative_path.startswith(root_path + "/")


def frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index])
    return ""


def normalized_heading(value):
    value = BILINGUAL_SUFFIX_RE.sub("", value.strip())
    value = LEADING_NUMBER_RE.sub("", value)
    value = value.replace("–", "-").replace("—", "-")
    return SPACE_RE.sub(" ", value).strip().casefold()


def headings_outside_fences(text):
    found = []
    fence = None
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        marker = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and marker:
            fence = marker.group(1)[0]
            continue
        if fence is not None:
            if marker and marker.group(1)[0] == fence:
                fence = None
            continue
        match = HEADING_RE.match(line)
        if match:
            found.append((line_number, match.group(2).strip()))
    return found


def classify(text):
    markers = []
    if TYPE_RE.search(frontmatter(text)):
        markers.append((1, "frontmatter type: interview-card"))

    matched = []
    for line_number, heading in headings_outside_fences(text):
        normalized = normalized_heading(heading)
        if normalized in SUPPORT_HEADINGS:
            matched.append((line_number, heading, normalized))

    explicit = [item for item in matched if item[2] in EXPLICIT_HEADINGS]
    if explicit:
        markers.extend((line, "heading: %s" % heading)
                       for line, heading, _normalized in explicit)
    elif len({normalized for _line, _heading, normalized in matched}) >= 2:
        markers.extend((line, "answer-structure heading: %s" % heading)
                       for line, heading, _normalized in matched)
    return markers


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Find Interview Card answer structures outside the expression root."
    )
    parser.add_argument("vault_root", help="knowledge-vault root to scan")
    parser.add_argument(
        "--expression-root",
        default="Interview Preparation",
        help="vault-relative expression root excluded from residual candidates",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="path component to exclude in addition to control-plane defaults",
    )
    parser.add_argument("--receipts", help="optional JSONL receipt path")
    parser.add_argument(
        "--time-limit",
        type=float,
        default=DEFAULT_TIME_LIMIT,
        help="hard scan budget in seconds (must be greater than 0 and at most 60)",
    )
    args = parser.parse_args(argv)

    run_token = uuid.uuid4().hex
    items = []
    sequence = 0

    def add(check, target, result, details):
        nonlocal sequence
        sequence += 1
        items.append(receipt(check, target, result, details, sequence, run_token))

    root = os.path.abspath(args.vault_root)
    if not os.path.isdir(root):
        add("interview-residual-invocation", args.vault_root, "fail",
            "vault root does not exist or is not a directory")
        write_receipts(args.receipts, items)
        print("check_interview_residuals: FAIL — invalid vault root")
        return 1
    if args.time_limit <= 0 or args.time_limit > 60:
        add("interview-residual-invocation", root, "fail",
            "time limit must be greater than 0 and at most 60 seconds")
        write_receipts(args.receipts, items)
        print("check_interview_residuals: FAIL — invalid time limit")
        return 1
    try:
        expression_root = normalize_relative_path(args.expression_root)
    except ValueError as exc:
        add("interview-residual-invocation", root, "fail", str(exc))
        write_receipts(args.receipts, items)
        print("check_interview_residuals: FAIL — %s" % exc)
        return 1

    expression_path = os.path.join(root, *expression_root.split("/"))
    if not os.path.isdir(expression_path) or os.path.islink(expression_path):
        add("interview-residual-invocation", expression_root, "fail",
            "registered expression root does not exist as a real directory "
            "under the supplied vault root")
        write_receipts(args.receipts, items)
        print("check_interview_residuals: FAIL — registered expression root "
              "is missing or unsafe")
        return 1

    started = time.monotonic()
    scanned = 0
    candidates = 0
    extra_excludes = set(args.exclude)
    timed_out = False

    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        relative_directory = os.path.relpath(directory, root).replace(os.sep, "/")
        if relative_directory == ".":
            relative_directory = ""

        kept_dirs = []
        for name in sorted(dirnames):
            full = os.path.join(directory, name)
            relative = "/".join(part for part in (relative_directory, name) if part)
            top_level_control = not relative_directory and name in DEFAULT_TOP_LEVEL_EXCLUDES
            explicitly_excluded = name.startswith(".") or name in extra_excludes
            expression_excluded = is_under(relative, expression_root)
            if top_level_control or explicitly_excluded or expression_excluded:
                continue
            if os.path.islink(full):
                add("interview-residual-symlink", relative, "fail",
                    "symlinked directory is not traversed; scan a real bounded root")
                continue
            kept_dirs.append(name)
        dirnames[:] = kept_dirs

        for name in sorted(filenames):
            if time.monotonic() - started > args.time_limit:
                add("interview-residual-time-budget", root, "fail",
                    "scan exceeded the %.1f-second budget" % args.time_limit)
                timed_out = True
                break
            if name.startswith(".") or not name.lower().endswith(".md"):
                continue
            full = os.path.join(directory, name)
            relative = "/".join(part for part in (relative_directory, name) if part)
            if is_under(relative, expression_root):
                continue
            if os.path.islink(full):
                add("interview-residual-symlink", relative, "fail",
                    "symlinked Markdown file is not accepted as scanned evidence")
                continue
            try:
                with open(full, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except (OSError, UnicodeError) as exc:
                add("interview-residual-read-error", relative, "fail",
                    "cannot read UTF-8 Markdown: %s" % exc)
                continue
            scanned += 1
            markers = classify(text)
            if markers:
                candidates += 1
                first_line = min(line for line, _description in markers)
                details = "; ".join(description for _line, description in markers)
                add("interview-residual-candidate", "%s:%d" % (relative, first_line),
                    "candidate", details)
        if timed_out:
            break

    failures = [item for item in items if item["result"] == "fail"]
    if scanned == 0 and not failures:
        add("interview-residual-empty-scope", root, "fail",
            "effective scan set contains no Markdown files; zero-file scan is not a pass")
        failures = [items[-1]]
    if not failures and candidates == 0:
        add("interview-residual-summary", root, "pass",
            "scanned %d Markdown file(s); no Interview answer-structure candidate "
            "exists outside %s" % (scanned, expression_root))

    elapsed = time.monotonic() - started
    print("check_interview_residuals: scanned %d file(s), candidates=%d, "
          "failures=%d, elapsed=%.3fs" %
          (scanned, candidates, len(failures), elapsed))
    for item in items:
        if item["result"] in ("candidate", "fail"):
            print("  [%s] %s — %s" %
                  (item["result"].upper(), item["target"], item["details"]))
    write_receipts(args.receipts, items)
    if failures:
        return 1
    if candidates:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
