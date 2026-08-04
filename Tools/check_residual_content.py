#!/usr/bin/env python3
"""Find configured residual-content candidates outside their accepted roots.

The selected profile owns the scan configuration and acceptance predicate;
this tool owns only deterministic traversal, matching, receipts, and failure
semantics. Content findings are candidates (exit 2), never automatic defects.
Exit 1 is reserved for a scan that failed to produce reliable evidence.
"""

import argparse
import hashlib
import os
import re
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib


TOOL = "check_residual_content"
TOOL_VERSION = "1.0.0"
CONFIG_VERSION = 1
DEFAULT_TIME_LIMIT = 55.0
MAX_TIME_LIMIT = 55.0
VCS_CONTROL_DIRS = {".git", ".hg", ".svn"}

TOP_LEVEL_CONFIG_KEYS = {
    "residual_scan_config_version",
    "allowed_roots",
    "excluded_roots",
    "frontmatter_match",
    "heading_match",
}
FRONTMATTER_CONFIG_KEYS = {"field", "values"}
HEADING_CONFIG_KEYS = {"any", "combination", "minimum_distinct"}
FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
SCAN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
HEADING_RE = re.compile(r"^[ ]{0,3}(#{1,6})(.*)$")
ATX_CLOSING_RE = re.compile(r"[ \t]+#+$")


class ScanTimeBudgetExceeded(Exception):
    """Raised by the process-level timer when the scan exceeds its budget."""


def raise_scan_timeout(_signum, _frame):
    raise ScanTimeBudgetExceeded()


def normalized_heading(value):
    # Heading semantics belong to the profile. The generic matcher strips only
    # Markdown heading syntax; the configured text itself remains exact.
    return value.strip()


def normalize_relative_path(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s entries must be non-empty strings" % field)
    stripped = value.strip()
    if "\x00" in stripped or "\\" in stripped:
        raise ValueError("%s entries must use safe forward-slash paths" % field)
    normalized = os.path.normpath(stripped).replace(os.sep, "/")
    if normalized in (".", "..") or os.path.isabs(stripped):
        raise ValueError("%s entries must be relative subpaths" % field)
    if normalized.startswith("../"):
        raise ValueError("%s entries must remain inside the vault root" % field)
    return normalized


def is_under(path, root):
    return path == root or path.startswith(root + "/")


def under_any(path, roots):
    return any(is_under(path, root) for root in roots)


def require_exact_keys(mapping, expected, label):
    if not isinstance(mapping, dict):
        raise ValueError("%s must be a mapping" % label)
    missing = sorted(expected - set(mapping))
    unknown = sorted(set(mapping) - expected)
    if missing:
        raise ValueError("%s missing key(s): %s" % (label, ", ".join(missing)))
    if unknown:
        raise ValueError("%s has unknown key(s): %s" % (label, ", ".join(unknown)))


def string_list(value, label, allow_empty=True):
    if not isinstance(value, list):
        raise ValueError("%s must be a list" % label)
    if not allow_empty and not value:
        raise ValueError("%s must contain at least one entry" % label)
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError("%s entries must be non-empty strings" % label)
    return [item.strip() for item in value]


def normalized_unique(values, label, normalizer=lambda value: value.casefold()):
    output = []
    seen = set()
    for value in values:
        normalized = normalizer(value)
        if normalized in seen:
            raise ValueError("%s contains a duplicate after normalization: %r" %
                             (label, value))
        seen.add(normalized)
        output.append(normalized)
    return output


def validate_path_sets(allowed, excluded):
    for label, paths in (("allowed_roots", allowed), ("excluded_roots", excluded)):
        for index, path in enumerate(paths):
            for other in paths[index + 1:]:
                folded_path = path.casefold()
                folded_other = other.casefold()
                if (is_under(folded_path, folded_other) or
                        is_under(folded_other, folded_path)):
                    raise ValueError("%s contains overlapping roots: %r and %r" %
                                     (label, path, other))
    for allowed_path in allowed:
        for excluded_path in excluded:
            folded_allowed = allowed_path.casefold()
            folded_excluded = excluded_path.casefold()
            if (is_under(folded_allowed, folded_excluded) or
                    is_under(folded_excluded, folded_allowed)):
                raise ValueError("allowed_roots and excluded_roots overlap: %r and %r" %
                                 (allowed_path, excluded_path))


def load_config(path):
    if not os.path.isfile(path) or os.path.islink(path):
        raise ValueError("config must be a real readable file")
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        text = raw.decode("utf-8")
        data = kblib.parse_yaml_subset(text)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("cannot parse restricted YAML config: %s" % exc)

    require_exact_keys(data, TOP_LEVEL_CONFIG_KEYS, "config")
    version = data["residual_scan_config_version"]
    if type(version) is not int or version != CONFIG_VERSION:
        raise ValueError("unsupported residual_scan_config_version %r; expected %d" %
                         (version, CONFIG_VERSION))

    allowed = [normalize_relative_path(item, "allowed_roots") for item in
               string_list(data["allowed_roots"], "allowed_roots", allow_empty=False)]
    excluded = [normalize_relative_path(item, "excluded_roots") for item in
                string_list(data["excluded_roots"], "excluded_roots")]
    normalized_unique(allowed, "allowed_roots")
    normalized_unique(excluded, "excluded_roots")
    validate_path_sets(allowed, excluded)

    frontmatter = data["frontmatter_match"]
    require_exact_keys(frontmatter, FRONTMATTER_CONFIG_KEYS, "frontmatter_match")
    field = frontmatter["field"]
    if not isinstance(field, str) or not FIELD_RE.fullmatch(field):
        raise ValueError("frontmatter_match.field must be a simple field name")
    values = string_list(frontmatter["values"], "frontmatter_match.values")
    normalized_values = normalized_unique(
        values, "frontmatter_match.values", lambda value: value)

    heading = data["heading_match"]
    require_exact_keys(heading, HEADING_CONFIG_KEYS, "heading_match")
    any_headings = string_list(heading["any"], "heading_match.any")
    combination_headings = string_list(
        heading["combination"], "heading_match.combination")
    normalized_any = normalized_unique(
        any_headings, "heading_match.any", normalized_heading)
    normalized_combination = normalized_unique(
        combination_headings, "heading_match.combination", normalized_heading)
    overlap = sorted(set(normalized_any) & set(normalized_combination))
    if overlap:
        raise ValueError("heading_match.any and combination overlap: %s" %
                         ", ".join(overlap))

    minimum = heading["minimum_distinct"]
    if not isinstance(minimum, int) or isinstance(minimum, bool):
        raise ValueError("heading_match.minimum_distinct must be an integer")
    if normalized_combination:
        if minimum < 2 or minimum > len(normalized_combination):
            raise ValueError("heading_match.minimum_distinct must be between 2 and %d" %
                             len(normalized_combination))
    elif minimum != 0:
        raise ValueError("heading_match.minimum_distinct must be 0 when combination is empty")

    if not (normalized_values or normalized_any or normalized_combination):
        raise ValueError("config must define at least one residual-content matcher")

    config = {
        "allowed_roots": tuple(allowed),
        "excluded_roots": tuple(excluded),
        "frontmatter_field": field,
        "frontmatter_values": frozenset(normalized_values),
        "any_headings": frozenset(normalized_any),
        "combination_headings": frozenset(normalized_combination),
        "minimum_distinct": minimum,
    }
    return config, hashlib.sha256(raw).hexdigest()


def frontmatter(text):
    raw = kblib.extract_frontmatter(text)
    if raw is None:
        return []
    return raw.splitlines()


def frontmatter_matches(text, field, accepted_values):
    if not accepted_values:
        return []
    pattern = re.compile(r"^\s*%s\s*:\s*(.*?)\s*$" % re.escape(field))
    matches = []
    for line_number, line in enumerate(frontmatter(text), 2):
        match = pattern.match(line)
        if not match:
            continue
        raw = kblib.strip_yaml_comment(match.group(1)).strip()
        value = kblib.parse_scalar(raw)
        if isinstance(value, str) and value.strip() in accepted_values:
            matches.append((line_number, "frontmatter %s: %s" % (field, value.strip())))
    return matches


def headings_outside_fences(text):
    found = []
    fence_character = None
    fence_length = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        if fence_character is None:
            marker = re.match(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$", line)
            if marker:
                opening = marker.group(1)
                info = marker.group(2)
                if opening[0] != "`" or "`" not in info:
                    fence_character = opening[0]
                    fence_length = len(opening)
                    continue
        else:
            closing = re.match(
                r"^[ ]{0,3}%s{%d,}[ \t]*$" %
                (re.escape(fence_character), fence_length), line)
            if closing:
                fence_character = None
                fence_length = 0
            continue
        match = HEADING_RE.match(line)
        if match:
            remainder = match.group(2)
            if remainder and remainder[0] not in " \t":
                continue
            heading = ATX_CLOSING_RE.sub("", remainder.strip()).strip()
            found.append((line_number, heading))
    return found


def classify(text, config):
    markers = frontmatter_matches(
        text, config["frontmatter_field"], config["frontmatter_values"])
    matched_any = []
    matched_combination = []
    for line_number, heading in headings_outside_fences(text):
        normalized = normalized_heading(heading)
        if normalized in config["any_headings"]:
            matched_any.append((line_number, heading, normalized))
        elif normalized in config["combination_headings"]:
            matched_combination.append((line_number, heading, normalized))

    if matched_any:
        markers.extend((line, "heading: %s" % heading)
                       for line, heading, _normalized in matched_any)
    elif (config["minimum_distinct"] and
          len({item[2] for item in matched_combination}) >=
          config["minimum_distinct"]):
        markers.extend((line, "residual-structure heading: %s" % heading)
                       for line, heading, _normalized in matched_combination)
    return markers


def scan_scope(root, config, add):
    """Traverse the profile-defined scope; the caller owns the hard deadline."""
    scanned = 0
    candidates = 0

    def walk_error(exc):
        target = getattr(exc, "filename", None) or root
        try:
            target = os.path.relpath(target, root).replace(os.sep, "/")
        except (TypeError, ValueError):
            target = str(target)
        add("residual-content-walk-error", target, "fail",
            "cannot traverse scan scope: %s" % exc)

    for directory, dirnames, filenames in os.walk(
            root, followlinks=False, onerror=walk_error):
        relative_directory = os.path.relpath(directory, root).replace(os.sep, "/")
        if relative_directory == ".":
            relative_directory = ""

        kept_dirs = []
        for name in sorted(dirnames):
            full = os.path.join(directory, name)
            relative = "/".join(
                part for part in (relative_directory, name) if part)
            vcs_control = name in VCS_CONTROL_DIRS
            configured_exclude = under_any(relative, config["excluded_roots"])
            accepted_content = under_any(relative, config["allowed_roots"])
            if vcs_control or configured_exclude or accepted_content:
                continue
            if os.path.islink(full):
                add("residual-content-symlink", relative, "fail",
                    "symlinked directory is not traversed as scan evidence")
                continue
            kept_dirs.append(name)
        dirnames[:] = kept_dirs

        for name in sorted(filenames):
            if not name.lower().endswith(".md"):
                continue
            full = os.path.join(directory, name)
            relative = "/".join(
                part for part in (relative_directory, name) if part)
            if (under_any(relative, config["allowed_roots"]) or
                    under_any(relative, config["excluded_roots"])):
                continue
            if os.path.islink(full):
                add("residual-content-symlink", relative, "fail",
                    "symlinked Markdown file is not accepted as scan evidence")
                continue
            if not os.path.isfile(full):
                add("residual-content-nonregular-file", relative, "fail",
                    "Markdown scan evidence must be a regular file")
                continue
            try:
                with open(full, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except (OSError, UnicodeError) as exc:
                add("residual-content-read-error", relative, "fail",
                    "cannot read UTF-8 Markdown: %s" % exc)
                continue
            scanned += 1
            try:
                markers = classify(text, config)
            except (TypeError, ValueError) as exc:
                add("residual-content-parse-error", relative, "fail",
                    "cannot classify configured metadata: %s" % exc)
                continue
            if markers:
                candidates += 1
                first_line = min(line for line, _description in markers)
                details = "; ".join(
                    description for _line, description in markers)
                add("residual-content-candidate", "%s:%d" % (relative, first_line),
                    "candidate", details)

    return scanned, candidates


def produce_evidence(root, config_path, time_limit, add, receipt_context):
    """Load, validate, and scan under one evidence-production deadline."""
    started = time.monotonic()
    scanned = 0
    candidates = 0

    if not all(hasattr(signal, name) for name in
               ("SIGALRM", "ITIMER_REAL", "getitimer", "setitimer")):
        add("residual-content-time-budget", root, "fail",
            "this Python platform cannot enforce the required hard deadline")
        return scanned, candidates, time.monotonic() - started

    previous_handler = None
    timer_installed = False
    try:
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
        if previous_timer != (0.0, 0.0):
            add("residual-content-time-budget", root, "fail",
                "cannot enforce an independent deadline while a process timer is active")
            return scanned, candidates, time.monotonic() - started
        previous_handler = signal.signal(signal.SIGALRM, raise_scan_timeout)
        timer_installed = True
        signal.setitimer(signal.ITIMER_REAL, time_limit)
    except ScanTimeBudgetExceeded:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        add("residual-content-time-budget", root, "fail",
            "evidence production exceeded the %g-second hard budget" % time_limit)
        return scanned, candidates, time.monotonic() - started
    except (OSError, RuntimeError, ValueError) as exc:
        if timer_installed:
            signal.setitimer(signal.ITIMER_REAL, 0)
        if previous_handler is not None:
            signal.signal(signal.SIGALRM, previous_handler)
        add("residual-content-time-budget", root, "fail",
            "cannot establish the required hard deadline: %s" % exc)
        return scanned, candidates, time.monotonic() - started

    try:
        try:
            config, config_sha256 = load_config(config_path)
        except ValueError as exc:
            add("residual-content-config", config_path, "fail", str(exc))
            return scanned, candidates, time.monotonic() - started
        receipt_context["config_fingerprint"] = "sha256:%s" % config_sha256

        if not os.path.isdir(root) or os.path.islink(root):
            add("residual-content-invocation", root, "fail",
                "vault root must be a real directory")
            return scanned, candidates, time.monotonic() - started

        scope_valid = True
        for allowed_root in config["allowed_roots"]:
            allowed_path = os.path.join(root, *allowed_root.split("/"))
            if not os.path.isdir(allowed_path) or os.path.islink(allowed_path):
                add("residual-content-allowed-root", allowed_root, "fail",
                    "accepted root is missing, not a directory, or a symlink")
                scope_valid = False
        if scope_valid:
            scanned, candidates = scan_scope(root, config, add)
    except ScanTimeBudgetExceeded:
        add("residual-content-time-budget", root, "fail",
            "evidence production exceeded the %g-second hard budget" % time_limit)
    finally:
        if timer_installed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    return scanned, candidates, time.monotonic() - started


def write_receipts_safely(path, receipts):
    try:
        kblib.write_receipts(path, receipts)
    except (OSError, UnicodeError) as exc:
        print("check_residual_content: FAIL — cannot write receipts: %s" % exc,
              file=sys.stderr)
        return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Find profile-configured residual content outside accepted roots."
    )
    parser.add_argument("vault_root", help="knowledge-vault root to scan")
    parser.add_argument("--scan-id", required=True,
                        help="stable ID from the selected profile's scan registry")
    parser.add_argument("--config", required=True,
                        help="profile-owned restricted YAML scan configuration")
    parser.add_argument("--receipts", help="optional JSONL receipt path")
    parser.add_argument(
        "--time-limit",
        type=float,
        default=DEFAULT_TIME_LIMIT,
        help="hard evidence-production budget in seconds (greater than 0 and at most 55)",
    )
    args = parser.parse_args(argv)

    receipts = []
    safe_scan_id = (args.scan_id if SCAN_ID_RE.fullmatch(args.scan_id)
                    else "invalid-residual-scan")
    receipt_context = {"config_fingerprint": None}

    def add(check, target, result, details):
        receipt = kblib.make_receipt(
            TOOL, TOOL_VERSION, check, target, result, details,
            len(receipts) + 1)
        receipt["scan_id"] = safe_scan_id
        receipt["config_fingerprint"] = receipt_context["config_fingerprint"]
        receipts.append(receipt)

    if safe_scan_id != args.scan_id:
        add("residual-content-invocation", args.scan_id, "fail",
            "scan ID must match %s" % SCAN_ID_RE.pattern)
        if not write_receipts_safely(args.receipts, receipts):
            return 1
        print("check_residual_content: FAIL — invalid scan ID")
        return 1

    root = os.path.abspath(args.vault_root)
    if not 0 < args.time_limit <= MAX_TIME_LIMIT:
        add("residual-content-invocation", root, "fail",
            "time limit must be greater than 0 and at most 55 seconds")
    if receipts:
        if not write_receipts_safely(args.receipts, receipts):
            return 1
        print("check_residual_content: FAIL — invalid invocation")
        return 1

    scanned, candidates, elapsed = produce_evidence(
        root, os.path.abspath(args.config), args.time_limit, add, receipt_context)

    failures = [item for item in receipts if item["result"] == "fail"]
    if scanned == 0 and not failures:
        add("residual-content-empty-scope", root, "fail",
            "effective scan set contains no Markdown files; zero-file scan is not a pass")
        failures = [receipts[-1]]
    if not failures and candidates == 0:
        add("residual-content-summary", root, "pass",
            "scanned %d Markdown file(s); no configured residual-content candidate found" %
            scanned)

    print("check_residual_content: scanned %d file(s), candidates=%d, "
          "failures=%d, elapsed=%.3fs" %
          (scanned, candidates, len(failures), elapsed))
    for item in receipts:
        if item["result"] in ("candidate", "fail"):
            print("  [%s] %s — %s" %
                  (item["result"].upper(), item["target"], item["details"]))
    if not write_receipts_safely(args.receipts, receipts):
        return 1
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
