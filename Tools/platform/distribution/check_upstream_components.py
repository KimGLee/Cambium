#!/usr/bin/env python3
"""Check or record the immutable Cambium component byte boundary.

Run this entry point from a trusted upstream checkout and pass the adopter as
``root``. It detects drift; an adopter copy cannot authenticate itself.
"""

import json
import os
import sys
import tempfile


import Tools.platform.common.kblib as kblib  # noqa: E402
from Tools.platform.distribution.upstream_component_boundary import (  # noqa: E402
    ComponentBoundaryError,
    DEFAULT_MANIFEST_PATH,
    evaluate,
    manifest_path,
    manifest_text,
)


TOOL = "check_upstream_components"
TOOL_VERSION = "1.0.0"


def _read_manifest(path):
    if not os.path.lexists(path):
        return None
    try:
        return kblib.read_text(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ComponentBoundaryError(
            "cannot read the derived component manifest: %s" % exc) from exc


def main(argv=None):
    parser = kblib.ArgumentParser(
        description=(
            "Compare adopter Cambium component bytes with one exact upstream "
            "Git revision"))
    parser.add_argument("root", help="adopter repository root")
    parser.add_argument(
        "--upstream-root", required=True,
        help="Cambium source Git repository (read-only)")
    parser.add_argument(
        "--revision", required=True,
        help="upstream ref to resolve to a full commit SHA")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write-manifest", action="store_true",
        help="atomically write and read back the derived manifest")
    mode.add_argument(
        "--check-manifest", action="store_true",
        help="require the existing derived manifest to match")
    parser.add_argument("--json", action="store_true",
                        help="emit one structured result")
    args = parser.parse_args(argv)

    errors = []
    candidates = []
    report = None
    output_path = None
    rendered = None
    try:
        report = evaluate(args.root, args.upstream_root, args.revision)
        errors.extend(report.errors)
        output_path = manifest_path(args.root)
        if not errors:
            rendered = manifest_text(report)
            if args.write_manifest:
                kblib.atomic_write_text(output_path, rendered)
                if _read_manifest(output_path) != rendered:
                    errors.append(
                        "derived component manifest failed resulting-state "
                        "read-back")
            elif args.check_manifest:
                existing = _read_manifest(output_path)
                if existing is None:
                    candidates.append(
                        "derived component manifest is missing: %s" %
                        DEFAULT_MANIFEST_PATH)
                elif existing != rendered:
                    candidates.append(
                        "derived component manifest is stale: %s" %
                        DEFAULT_MANIFEST_PATH)
    except (ComponentBoundaryError, OSError, UnicodeError, ValueError) as exc:
        errors.append(str(exc))

    summary = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "result": "FAIL" if errors else ("HOLD" if candidates else "PASS"),
        "upstream_revision_id": (
            report.upstream_revision_id if report is not None else None),
        "distribution_boundary_sha256": (
            report.distribution_boundary_sha256
            if report is not None else None),
        "manifest": DEFAULT_MANIFEST_PATH,
        "manifest_sha256": (
            kblib.sha256_bytes(rendered.encode("utf-8"))
            if rendered is not None else None),
        "present_count": report.present_count if report is not None else 0,
        "omitted_distribution_only_count": (
            report.omitted_count if report is not None else 0),
        "error_count": len(errors),
        "candidate_count": len(candidates),
    }
    if args.json:
        print(json.dumps(
            dict(summary, errors=errors, candidates=candidates),
            ensure_ascii=False, sort_keys=True))
    else:
        for message in errors:
            print("  [FAIL] %s" % message)
        for message in candidates:
            print("  [CAND] %s" % message)
        if errors:
            print("%s: FAIL - %d error(s)" % (TOOL, len(errors)))
        elif candidates:
            print("%s: HOLD - %d candidate(s)" %
                  (TOOL, len(candidates)))
        else:
            if args.write_manifest:
                action = "written and read back"
            elif args.check_manifest:
                action = "verified current"
            else:
                action = "computed only"
            print(
                "%s: PASS - revision %s; %d present, %d permitted "
                "omissions; manifest %s" %
                (TOOL, report.upstream_revision_id, report.present_count,
                 report.omitted_count, action))
    return 1 if errors else (2 if candidates else 0)


if __name__ == "__main__":
    raise SystemExit(main())
