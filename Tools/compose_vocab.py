#!/usr/bin/env python3
"""compose_vocab.py -- persistent vocabulary compiler (kernel tooling).

Deterministically composes the selected-profile vocabulary artifact
(Tools/vocab.yaml by default) from two restricted-YAML-subset inputs:

  --base        kernel vocabulary base
                (default: "kernel/08 Metadata and Status/vocabulary-base.yaml")
  --extensions  selected profile's vocabulary extensions
                (default: "profiles/agent-atlas/vocabulary-extensions.yaml")

Merge policy (matches docs/vocab_build_receipt.json):
  - root keys are emitted in the fixed base-driven order;
  - fields: kernel fields in source order, then profile-only fields in
    source order;
  - values: kernel values first, then profile additions in source order,
    deduplicated (stable first occurrence);
  - extensions are append-only: they must not remove, rename, or redefine
    base values or base-owned sections. Any conflict is listed and the
    script exits 1.

Modes:
  default  recompute and write --output (Tools/vocab.yaml by default),
           with an English provenance header (input paths + sha256).
  --check  recompute and compare against the existing --output at the
           value level (header comments are ignored). Exit 0 when
           identical, exit 2 with the first differing key otherwise.

Exit codes: 0 = ok / check passed; 1 = conflict or input error;
            2 = --check mismatch.

Only the python3 standard library is used; YAML parsing goes through
Tools/kblib.py parse_yaml_subset (restricted subset only).
"""

import argparse
import hashlib
import json
import os
import re
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, TOOLS_DIR)

import kblib  # noqa: E402

TOOL_VERSION = "1.0.0"

DEFAULT_BASE = "kernel/08 Metadata and Status/vocabulary-base.yaml"
DEFAULT_EXTENSIONS = "profiles/agent-atlas/vocabulary-extensions.yaml"
DEFAULT_OUTPUT = "Tools/vocab.yaml"

# Fixed root key order of the composed artifact (base-driven; profile-derived
# keys are interleaved at their canonical positions). Keys absent from the
# inputs are simply skipped.
ROOT_KEY_ORDER = [
    "schema_version",
    "profile_id",
    "composition_policy",
    "compiled_from",
    "frontmatter_extensions",
    "fields",
    "review_intervals_days",
    "volatility_defaults",
    "task_state",
]

# Sections owned by the base input: the profile must not redefine them.
BASE_OWNED_SECTIONS = ["review_intervals_days", "task_state"]


def resolve_path(path):
    """Resolve a (possibly relative) path against cwd first, then repo root."""
    if os.path.isabs(path) or os.path.exists(path):
        return path
    candidate = os.path.join(REPO_ROOT, path)
    if os.path.exists(candidate):
        return candidate
    return path


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_subset(path):
    with open(path, "r", encoding="utf-8") as fh:
        return kblib.parse_yaml_subset(fh.read())


def dedup_append(target, additions):
    """Append additions to target in source order, deduplicated (stable)."""
    for value in additions:
        if value not in target:
            target.append(value)
    return target


def compose(base, profile, base_arg, ext_arg):
    """Compose the merged vocabulary. Returns (output_dict, conflicts)."""
    conflicts = []

    base_fields = base.get("fields")
    profile_fields = profile.get("fields") or {}
    if not isinstance(base_fields, dict):
        conflicts.append("base: missing or non-mapping 'fields' section")
        return None, conflicts
    if not isinstance(profile_fields, dict):
        conflicts.append("extensions: 'fields' section is not a mapping")
        return None, conflicts

    # The profile must not redefine base-owned scalar/mapping sections.
    for section in BASE_OWNED_SECTIONS:
        if section in profile and profile[section] != base.get(section):
            conflicts.append(
                "extensions redefine base-owned section %r" % section
            )

    fields = {}
    for name, base_spec in base_fields.items():
        if not isinstance(base_spec, dict):
            conflicts.append("base field %r is not a mapping" % name)
            continue
        base_values = list(base_spec.get("values") or [])
        merged = {"owner": base_spec.get("owner")}
        extension = profile_fields.get(name)
        if extension is not None:
            if not isinstance(extension, dict):
                conflicts.append(
                    "fields.%s: extension entry is not a mapping" % name
                )
                extension = {}
            extra_keys = [k for k in extension if k not in ("owner", "values")]
            if extra_keys:
                conflicts.append(
                    "fields.%s: extension may only append owner+values; "
                    "found extra keys %s (base fields cannot be redefined)"
                    % (name, extra_keys)
                )
            if extension.get("owner") is not None:
                merged["extension_owner"] = extension["owner"]
            dedup_append(base_values, list(extension.get("values") or []))
        merged["values"] = base_values
        fields[name] = merged

    for name, profile_spec in profile_fields.items():
        if name in fields:
            continue
        if not isinstance(profile_spec, dict):
            conflicts.append("profile-only field %r is not a mapping" % name)
            continue
        allowed = ("owner", "role", "values")
        extra_keys = [k for k in profile_spec if k not in allowed]
        if extra_keys:
            conflicts.append(
                "fields.%s: profile-only field may only carry owner/role/"
                "values; found extra keys %s" % (name, extra_keys)
            )
        spec = {}
        if profile_spec.get("owner") is not None:
            spec["owner"] = profile_spec["owner"]
        if profile_spec.get("role") is not None:
            spec["role"] = profile_spec["role"]
        spec["values"] = dedup_append([], list(profile_spec.get("values") or []))
        fields[name] = spec

    candidate = {
        "schema_version": base.get("schema_version"),
        "profile_id": profile.get("profile_id"),
        "composition_policy": base.get("composition_policy"),
        "compiled_from": {"kernel": base_arg, "profile": ext_arg},
        "frontmatter_extensions": profile.get("frontmatter_extensions"),
        "fields": fields,
        "review_intervals_days": base.get("review_intervals_days"),
        "volatility_defaults": profile.get("volatility_defaults"),
        "task_state": base.get("task_state"),
    }
    output = {}
    for key in ROOT_KEY_ORDER:
        if candidate.get(key) is not None:
            output[key] = candidate[key]
    return output, conflicts


# ---------------------------------------------------------------------------
# Restricted-YAML-subset emitter (matches the serialization policy recorded
# in docs/vocab_build_receipt.json: JSON-quoted strings with ensure_ascii
# false, unquoted integers, null as empty scalar, [] for empty lists,
# 2-space indentation, final newline).
# ---------------------------------------------------------------------------


def emit_scalar(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    raise TypeError("unsupported scalar: %r" % (value,))


def emit_map(mapping, indent=0):
    lines = []
    prefix = " " * indent
    for key, value in mapping.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            raise ValueError("unsupported YAML key: %r" % key)
        if isinstance(value, dict):
            lines.append("%s%s:" % (prefix, key))
            lines.extend(emit_map(value, indent + 2))
        elif isinstance(value, list):
            if not value:
                lines.append("%s%s: []" % (prefix, key))
            else:
                lines.append("%s%s:" % (prefix, key))
                for item in value:
                    if isinstance(item, (dict, list)):
                        raise ValueError(
                            "nested containers in lists are unsupported"
                        )
                    lines.append("%s  - %s" % (prefix, emit_scalar(item)))
        else:
            rendered = emit_scalar(value)
            lines.append(
                "%s%s:%s" % (prefix, key, " " + rendered if rendered else "")
            )
    return lines


def build_header(base_arg, ext_arg, base_sha, ext_sha):
    return [
        "# Generated artifact -- do not edit directly.",
        "# Inputs:",
        "#   base:       %s (sha256: %s)" % (base_arg, base_sha),
        "#   extensions: %s (sha256: %s)" % (ext_arg, ext_sha),
        "# Merge rule: root keys follow the fixed base key order; for each",
        "#   field, kernel values come first and profile additions are",
        "#   appended in source order, deduplicated; extensions must not",
        "#   remove, rename, or redefine base values.",
        "# regenerate with: python3 Tools/compose_vocab.py",
        "",
    ]


def render(output, header_lines):
    return "\n".join(header_lines + emit_map(output)) + "\n"


def first_diff_key(expected, actual, path=""):
    """Return a human-readable key path of the first difference."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in list(expected.keys()) + [
            k for k in actual.keys() if k not in expected
        ]:
            child = "%s.%s" % (path, key) if path else str(key)
            if key not in actual:
                return "%s (missing in existing output)" % child
            if key not in expected:
                return "%s (unexpected in existing output)" % child
            diff = first_diff_key(expected[key], actual[key], child)
            if diff:
                return diff
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        for idx in range(max(len(expected), len(actual))):
            child = "%s[%d]" % (path, idx)
            if idx >= len(actual):
                return "%s (missing in existing output)" % child
            if idx >= len(expected):
                return "%s (unexpected in existing output)" % child
            diff = first_diff_key(expected[idx], actual[idx], child)
            if diff:
                return diff
        return None
    if expected != actual:
        return "%s (expected %r, found %r)" % (path or "<root>", expected, actual)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Deterministically compose the vocabulary artifact "
        "from the kernel base and the selected profile's extensions."
    )
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--extensions", default=DEFAULT_EXTENSIONS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute and compare against the existing output; "
        "exit 0 when identical at the value level, 2 otherwise",
    )
    args = parser.parse_args(argv)

    base_path = resolve_path(args.base)
    ext_path = resolve_path(args.extensions)
    for label, path in (("base", base_path), ("extensions", ext_path)):
        if not os.path.exists(path):
            print("compose_vocab: %s input not found: %s" % (label, path))
            return 1

    try:
        base = load_subset(base_path)
        profile = load_subset(ext_path)
    except kblib.YamlSubsetError as exc:
        print("compose_vocab: input outside the restricted YAML subset: %s" % exc)
        return 1

    output, conflicts = compose(base, profile, args.base, args.extensions)
    if conflicts:
        print("compose_vocab: %d conflict(s); extensions must be append-only:"
              % len(conflicts))
        for item in conflicts:
            print("  - %s" % item)
        return 1

    base_sha = sha256_file(base_path)
    ext_sha = sha256_file(ext_path)
    rendered = render(output, build_header(args.base, args.extensions,
                                           base_sha, ext_sha))

    # Round-trip guard: the emitted document must parse back to the same
    # values through the same restricted-subset parser.
    if kblib.parse_yaml_subset(rendered) != output:
        print("compose_vocab: internal error: kblib round-trip mismatch")
        return 1

    output_path = resolve_path(args.output)

    if args.check:
        if not os.path.exists(output_path):
            print("compose_vocab --check: output not found: %s" % output_path)
            return 2
        with open(output_path, "r", encoding="utf-8") as fh:
            try:
                existing = kblib.parse_yaml_subset(fh.read())
            except kblib.YamlSubsetError as exc:
                print("compose_vocab --check: existing output is not "
                      "parseable: %s" % exc)
                return 2
        diff = first_diff_key(output, existing)
        if diff:
            print("compose_vocab --check: MISMATCH at key: %s" % diff)
            return 2
        print("compose_vocab --check: OK (%s matches composed values)"
              % args.output)
        return 0

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(rendered)
    field_count = len(output.get("fields") or {})
    value_count = sum(
        len(spec.get("values") or [])
        for spec in (output.get("fields") or {}).values()
    )
    print("compose_vocab: wrote %s (%d fields, %d values)"
          % (args.output, field_count, value_count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
