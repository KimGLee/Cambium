"""Shared deterministic repository-structure checks.

This module owns the implementation used by both the repository maintenance
check and the batch-close Closed List member. It consumes repository content
plus one explicitly selected Profile manifest path; it neither reads nor
creates adopter runtime state.
"""

from pathlib import Path

import Tools.platform.common.kblib as kblib
import Tools.knowledge.structure.markdown_structure_checks as markdown_structure_checks
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths


TOOL = "check_repository_structure"
TOOL_VERSION = "1.0.0"


def repository_files(root, suffixes):
    """Yield Git-managed content outside Git and Cambium runtime state."""
    for absolute, relative in kblib.repository_content_files(root):
        if relative.split("/", 1)[0] in (
                ".git", runtime_paths.RUNTIME_ROOT):
            continue
        if relative.lower().endswith(tuple(suffixes)):
            yield absolute, relative


def check_repository_structure(root, selected_profile_manifest):
    """Return the existing K12/09 structural observation for ``root``.

    ``selected_profile_manifest`` identifies which Profile directory is part
    of Cambium's restricted-YAML scope. An absent or malformed identity keeps
    that scope empty, exactly as the former batch-close implementation did;
    Profile/runtime identity validation remains with their existing owners.
    """
    errors = []
    markdown_count = yaml_count = table_count = 0
    try:
        profile_prefix = (
            profile_layout_contract.validate_selectable_profile_manifest_path(
                selected_profile_manifest).directory + "/")
    except profile_layout_contract.ProfileLayoutError:
        profile_prefix = ""

    for absolute, relative in repository_files(
            root, (".md", ".yaml", ".yml")):
        lower = relative.lower()
        cambium_yaml = (
            bool(profile_prefix and relative.startswith(profile_prefix)) or
            relative.startswith("kernel/"))
        if lower.endswith((".yaml", ".yml")) and not cambium_yaml:
            continue
        try:
            raw = Path(absolute).read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append("%s is not readable strict UTF-8: %s" %
                          (relative, exc))
            continue
        if lower.endswith((".yaml", ".yml")):
            # Cambium owns the restricted YAML grammar only for its own
            # machine contracts. Unrelated adopter application YAML is not
            # part of this check.
            yaml_count += 1
            try:
                value = kblib.parse_yaml_subset(text)
                if not isinstance(value, dict):
                    raise ValueError("top-level YAML must be a mapping")
            except (ValueError, kblib.YamlSubsetError) as exc:
                errors.append("%s has invalid restricted YAML: %s" %
                              (relative, exc))
            continue

        markdown_count += 1
        if text.startswith("---\n") or text.startswith("---\r\n"):
            frontmatter = kblib.extract_frontmatter(text)
            if frontmatter is None:
                errors.append("%s opens frontmatter without a closing fence" %
                              relative)
            else:
                try:
                    value = kblib.parse_yaml_subset(frontmatter)
                    if not isinstance(value, dict):
                        raise ValueError("frontmatter must be a mapping")
                except (ValueError, kblib.YamlSubsetError) as exc:
                    errors.append("%s has invalid frontmatter YAML: %s" %
                                  (relative, exc))

        _fences, unclosed_fence = markdown_structure_checks.fence_scan(text)
        if unclosed_fence is not None:
            errors.append("%s:%d has an unclosed %s fence" %
                          (relative, unclosed_fence["line"],
                           unclosed_fence["marker"]))

        for table in markdown_structure_checks.table_scan(text):
            table_count += 1
            width = table["expected_columns"]
            if not table["delimiter_valid"]:
                errors.append("%s:%d table has no valid delimiter row" %
                              (relative, table["line"]))
                continue
            for offset, actual in enumerate(table["row_columns"]):
                if actual != width:
                    errors.append("%s:%d table has %d columns, expected %d" %
                                  (relative, table["line"] + offset,
                                   actual, width))

    details = ("strict_utf8=pass markdown=%d cambium_yaml=%d tables=%d "
               "structural_errors=%d" %
               (markdown_count, yaml_count, table_count, len(errors)))
    return {"errors": errors, "candidates": [], "details": details}


def main(argv=None):
    """Run the repository-structure observation through its public CLI."""
    parser = kblib.ArgumentParser(
        description="Check deterministic repository structure")
    parser.add_argument("root", help="repository root")
    parser.add_argument(
        "--profile-manifest", required=True,
        help="repository-relative selected Profile manifest path")
    args = parser.parse_args(argv)

    result = check_repository_structure(args.root, args.profile_manifest)
    print("structural_errors = %d" % len(result["errors"]))
    return 1 if result["errors"] else 0
