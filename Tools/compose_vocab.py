#!/usr/bin/env python3
"""compose_vocab.py -- persistent vocabulary compiler (kernel tooling).

Deterministically composes the selected-profile vocabulary artifact
(Tools/vocab.yaml by default) from two restricted-YAML-subset inputs:

  --base        kernel vocabulary base
                (default: "kernel/K08 Metadata and Status/vocabulary-base.yaml")
  --extensions  selected profile's vocabulary extensions. The active
                `selected_profile_manifest` in K00/03 determines the one
                allowed `Vocabulary Extensions` binding. The flag may repeat
                that path
                explicitly; it cannot choose a different profile. The
                generated header records provenance only and never selects
                the active profile.

Merge policy:
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
           value and provenance level. Exit 0 only when the deterministic
           artifact is byte-identical; exit 2 with the first differing key
           or a provenance/rendering mismatch otherwise.

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
from pathlib import Path

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.realpath(os.path.dirname(TOOLS_DIR))
sys.path.insert(0, TOOLS_DIR)

import kblib  # noqa: E402
import profile_admission  # noqa: E402

TOOL_VERSION = "1.7.0"

DEFAULT_BASE = "kernel/K08 Metadata and Status/vocabulary-base.yaml"
DEFAULT_OUTPUT = "Tools/vocab.yaml"
ACTIVE_STATE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
UNINSTANTIATED_RE = re.compile(r"\{\{.*?\}\}")

# There is deliberately no DEFAULT_EXTENSIONS. Naming one profile here would
# make that profile the tool's implicit answer to "which vocabulary is the
# real one", which is a decision the kernel does not make and this script
# must not make on its behalf. It also breaks silently rather than loudly:
# in a clone that does not carry the named profile, a hardcoded default
# resolves to a missing file, and in a clone that carries a different
# profile, it composes the wrong one without saying so.
EXTENSIONS_BASENAME = "vocabulary-extensions.yaml"
PROFILES_DIR = "profiles"
# Directory names under profiles/ that are not selectable profiles:
# `_template` is an unfilled skeleton whose value lists are empty by design,
# so composing against it would yield a base-only artifact that looks valid.
NON_PROFILE_DIRS = {"_template"}
PROFILE_ID_VALUE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

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

# The current Vocabulary Extensions input is deliberately closed. Profile
# identity and slot selection live in profile.md; base identity and composition
# policy live in the kernel base. Older extension files repeated those values.
PROFILE_ROOT_KEYS = {
    "schema_version",
    "frontmatter_extensions",
    "fields",
    "volatility_defaults",
}
FRONTMATTER_EXTENSION_KEYS = {"fields"}


def resolve_path(path):
    """Resolve a (possibly relative) path against cwd first, then repo root."""
    if os.path.isabs(path) or os.path.exists(path):
        return path
    candidate = os.path.join(REPO_ROOT, path)
    if os.path.exists(candidate):
        return candidate
    return path


def discover_profiles():
    """Profile manifest candidates for diagnostics only."""
    root = resolve_path(PROFILES_DIR)
    found = []
    if not os.path.isdir(root):
        return found
    for current, directories, files in os.walk(root):
        directories[:] = sorted(
            name for name in directories
            if name not in NON_PROFILE_DIRS and not name.startswith("."))
        if "profile.md" in files:
            relative = os.path.relpath(
                os.path.join(current, "profile.md"), REPO_ROOT)
            found.append(Path(relative).as_posix())
    return found


def _uninstantiated(value):
    return (not isinstance(value, str) or not value.strip() or
            UNINSTANTIATED_RE.search(value) is not None)


def _repo_relative_name(raw_path, relative_to_repo=False):
    """Return a lexical repo-relative path, preserving declared aliases."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, "path must be a non-empty string"
    raw_path = raw_path.strip()
    candidate = raw_path
    if not os.path.isabs(candidate):
        cwd_candidate = os.path.abspath(candidate)
        if relative_to_repo or not os.path.exists(cwd_candidate):
            candidate = os.path.join(REPO_ROOT, candidate)
    absolute = os.path.abspath(candidate)
    try:
        relative = os.path.relpath(absolute, REPO_ROOT)
    except ValueError as exc:
        return None, "path cannot be made repository-relative: %s" % exc
    parts = Path(relative).parts
    if relative == os.pardir or not parts or parts[0] == os.pardir:
        return None, "path escapes the repository"
    return Path(relative).as_posix(), None


def active_extensions_selection():
    """Return the one fully admitted Vocabulary Extensions selection."""
    admission, errors = profile_admission.admit_profile(
        REPO_ROOT, active_state_path=ACTIVE_STATE_PATH,
        require_approved=True)
    if admission is None:
        return None, None, errors, None
    path, error = profile_admission.require_slot(
        admission, "Vocabulary Extensions")
    if error:
        return None, None, [error], None
    extensions = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
    if not extensions.lower().endswith((".yaml", ".yml")):
        return None, None, [
            "Vocabulary Extensions binding must resolve to YAML; found %s" %
            extensions
        ], None
    return extensions, admission.profile_id, [], admission


def report_inactive_selection(errors):
    """Explain why no active profile can be composed."""
    print("compose_vocab: active profile selection is not usable:")
    for error in errors:
        print("  - %s" % error)
    candidates = discover_profiles()
    if candidates:
        print("  Profile manifest candidates found (candidates are not active "
              "until K00/03 selects one):")
        for item in candidates:
            print("    %s" % item)
    else:
        print("  No filled profile manifest in this repository resolves a "
              "Vocabulary Extensions binding.")
        print("  Copy profiles/_template/ to profiles/<your-profile-id>/ "
              "and fill it in first.")


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_subset(path, text=None):
    if text is not None:
        return kblib.parse_yaml_subset(text)
    with open(path, "r", encoding="utf-8") as fh:
        return kblib.parse_yaml_subset(fh.read())


def _repository_input_snapshot(root, raw_path, label):
    """Bind one compiler input through a canonical stable file descriptor."""
    root = os.path.abspath(os.fspath(root))
    candidate = os.fspath(raw_path)
    if not os.path.isabs(candidate):
        candidate = os.path.join(root, candidate)
    candidate = os.path.abspath(candidate)

    # Use actual ancestry so macOS's /var -> /private/var system alias does
    # not look like a repository escape.  The repository-internal spelling is
    # intentionally retained and is then checked by the no-follow snapshot.
    relative_parts = []
    current = candidate
    while True:
        try:
            if os.path.samefile(current, root):
                break
        except OSError:
            pass
        parent, name = os.path.split(current)
        if not name or parent == current:
            relative_parts = []
            break
        relative_parts.append(name)
        current = parent
    if not relative_parts:
        raise ValueError("%s path escapes the repository" % label)
    relative = "/".join(reversed(relative_parts))
    return relative, kblib.repository_file_snapshot(
        root, relative, singly_linked=True)


def compiled_artifact(root, admission, *, base_arg=DEFAULT_BASE,
                      extensions_arg=None):
    """Return canonical vocabulary bytes from one admitted input snapshot."""
    errors = []
    try:
        _base_relative, base_snapshot = _repository_input_snapshot(
            root, base_arg, "base")
        base = load_subset(None, base_snapshot.read_text())
        profile = load_subset(
            None, admission.slot_text("Vocabulary Extensions"))
    except (OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        return None, None, [
            "input outside the canonical restricted snapshot: %s" % exc]
    extension_path = admission.slot_path("Vocabulary Extensions")
    if extension_path is None:
        return None, None, [
            "authorized Profile has no Vocabulary Extensions slot"]
    extension_relative = os.path.relpath(
        extension_path, os.path.realpath(os.path.abspath(root))).replace(
            os.sep, "/")
    extensions_arg = extensions_arg or extension_relative
    output, conflicts = compose(
        base, profile, base_arg, extensions_arg, admission.profile_id)
    errors.extend(conflicts)
    if errors:
        return None, None, errors
    base_sha = base_snapshot.sha256.split(":", 1)[1]
    ext_sha = hashlib.sha256(
        admission.slot_bytes["Vocabulary Extensions"]).hexdigest()
    rendered = render(output, build_header(
        base_arg, extensions_arg, base_sha, ext_sha))
    return rendered, output, []


def admitted_artifact(root, artifact_path, admission):
    """Return immutable compiled bytes iff they equal the admitted IR."""
    rendered, _output, errors = compiled_artifact(root, admission)
    if errors:
        return None, errors
    try:
        relative, artifact = _repository_input_snapshot(
            root, artifact_path, "compiled vocabulary")
    except (OSError, ValueError) as exc:
        return None, [
            "compiled vocabulary is unsafe or unreadable: %s" % exc]
    if artifact.data != rendered.encode("utf-8"):
        return None, [
            "compiled vocabulary %s does not match the selected Profile and "
            "kernel base; recompose it with Tools/compose_vocab.py" % relative
        ]
    currency = profile_admission.currency_errors(admission)
    return (None, currency) if currency else (artifact, [])


def artifact_currency_errors(root, artifact_path, admission):
    """Require one compiled vocabulary to equal the admitted deterministic IR."""
    _artifact, errors = admitted_artifact(root, artifact_path, admission)
    return errors


def compilation_currency_errors(root, admission, expected_text, *, base_arg,
                                extensions_arg):
    """Recompile all inputs and require the initially rendered IR to persist."""
    current_text, _output, errors = compiled_artifact(
        root, admission, base_arg=base_arg,
        extensions_arg=extensions_arg)
    if errors:
        return errors
    if current_text != expected_text:
        return [
            "kernel vocabulary base changed during composition; rerun "
            "against one stable input revision"
        ]
    return profile_admission.currency_errors(admission)


def dedup_append(target, additions):
    """Append additions to target in source order, deduplicated (stable)."""
    for value in additions:
        if value not in target:
            target.append(value)
    return target


def compose(base, profile, base_arg, ext_arg, profile_id):
    """Compose the merged vocabulary. Returns (output_dict, conflicts)."""
    conflicts = []

    extra_root_keys = sorted(
        key for key in profile if key not in PROFILE_ROOT_KEYS
    )
    if extra_root_keys:
        conflicts.append(
            "extensions: unsupported root key(s) %s; profile_id and the "
            "Vocabulary Extensions binding come only from profile.md, while "
            "base identity and composition policy come only from the kernel "
            "base" % extra_root_keys
        )

    base_fields = base.get("fields")
    raw_profile_fields = profile.get("fields") or {}
    if not isinstance(base_fields, dict):
        conflicts.append("base: missing or non-mapping 'fields' section")
        return None, conflicts
    if not isinstance(raw_profile_fields, dict):
        conflicts.append("extensions: 'fields' section is not a mapping")
        return None, conflicts
    profile_fields = dict(raw_profile_fields)

    volatility_defaults = profile.get("volatility_defaults") or {}
    if not isinstance(volatility_defaults, dict):
        conflicts.append("extensions: 'volatility_defaults' is not a mapping")
        volatility_defaults = {}
    domain_values = list(volatility_defaults)
    if not domain_values:
        conflicts.append(
            "extensions: volatility_defaults must register at least one domain"
        )
    for domain, volatility in volatility_defaults.items():
        if volatility not in ("fast", "slow", "stable"):
            conflicts.append(
                "volatility_defaults.%s: expected fast, slow, or stable; found %r"
                % (domain, volatility)
            )
    if "domain" in profile_fields:
        conflicts.append(
            "fields.domain is a duplicate identity source; register each "
            "domain only in volatility_defaults"
        )
        del profile_fields["domain"]
    profile_fields["domain"] = {"values": domain_values}

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
            extra_keys = [k for k in extension if k != "values"]
            if extra_keys:
                conflicts.append(
                    "fields.%s: a kernel-field extension may only append "
                    "values; its extension_owner is derived from the selected "
                    "Vocabulary Extensions file, so found extra keys %s"
                    % (name, extra_keys)
                )
            merged["extension_owner"] = ext_arg
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

    frontmatter = profile.get("frontmatter_extensions") or {}
    if not isinstance(frontmatter, dict):
        conflicts.append("extensions: 'frontmatter_extensions' is not a mapping")
        frontmatter = {}
    extra_frontmatter_keys = sorted(
        key for key in frontmatter if key not in FRONTMATTER_EXTENSION_KEYS
    )
    if extra_frontmatter_keys:
        conflicts.append(
            "extensions: frontmatter_extensions supports only 'fields'; "
            "found unsupported key(s) %s" % extra_frontmatter_keys
        )
    explicit_frontmatter_fields = frontmatter.get("fields") or []
    if not isinstance(explicit_frontmatter_fields, list):
        conflicts.append("extensions: 'frontmatter_extensions.fields' is not a list")
        explicit_frontmatter_fields = []
    elif any(not isinstance(name, str) or not name for name in explicit_frontmatter_fields):
        conflicts.append(
            "extensions: 'frontmatter_extensions.fields' entries must be "
            "non-empty strings"
        )
        explicit_frontmatter_fields = [
            name for name in explicit_frontmatter_fields
            if isinstance(name, str) and name
        ]
    derived_frontmatter_fields = dedup_append(
        list(explicit_frontmatter_fields),
        [name for name in profile_fields if name not in base_fields],
    )
    frontmatter_out = {"fields": derived_frontmatter_fields}

    candidate = {
        "schema_version": base.get("schema_version"),
        "profile_id": profile_id,
        "composition_policy": base.get("composition_policy"),
        "compiled_from": {"kernel": base_arg, "profile": ext_arg},
        "frontmatter_extensions": frontmatter_out,
        "fields": fields,
        "review_intervals_days": base.get("review_intervals_days"),
        "volatility_defaults": volatility_defaults,
        "task_state": base.get("task_state"),
    }
    output = {}
    for key in ROOT_KEY_ORDER:
        if candidate.get(key) is not None:
            output[key] = candidate[key]
    return output, conflicts


# ---------------------------------------------------------------------------
# Restricted-YAML-subset emitter (serialization policy: JSON-quoted strings
# with ensure_ascii false, unquoted integers, null as empty scalar, [] for
# empty lists, 2-space indentation, final newline).
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
        "# The extensions path above is compilation provenance only; K00/03",
        "# active Standards state selects the profile for every run.",
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
    parser.add_argument(
        "--extensions",
        default=None,
        help="the active profile's %s. K00/03 selects the path; when this "
        "flag is present it must name that same path"
        % EXTENSIONS_BASENAME,
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute and compare against the existing output; "
        "exit 0 when values and provenance are identical, 2 otherwise",
    )
    args = parser.parse_args(argv)

    active_extensions, active_profile_id, selection_errors, admission = (
        active_extensions_selection()
    )
    if selection_errors or not active_extensions or not active_profile_id:
        report_inactive_selection(selection_errors or [
            "%s does not yield one selected profile" % ACTIVE_STATE_PATH
        ])
        return 1

    if args.extensions is None:
        args.extensions = active_extensions
        print("compose_vocab: using the profile selected by %s: %s" %
              (ACTIVE_STATE_PATH, active_extensions))
    else:
        requested_extensions, requested_error = _repo_relative_name(
            args.extensions
        )
        if requested_error:
            print("compose_vocab: --extensions is invalid: %s" %
                  requested_error)
            return 1
        if requested_extensions != active_extensions:
            print("compose_vocab: --extensions %r does not match the active "
                  "profile selected by %s: %s" %
                  (requested_extensions, ACTIVE_STATE_PATH, active_extensions))
            print("  Change profile selection through R09 governance; this "
                  "compiler does not select profiles.")
            return 1
        args.extensions = requested_extensions

    profile_id = active_profile_id
    if not isinstance(profile_id, str) or not PROFILE_ID_VALUE_RE.fullmatch(profile_id):
        print("compose_vocab: invalid profile_id %r; use a lowercase path slug "
              "matching [a-z0-9][a-z0-9_-]*" % profile_id)
        return 1

    rendered, output, compile_errors = compiled_artifact(
        REPO_ROOT, admission, base_arg=args.base,
        extensions_arg=args.extensions)
    if compile_errors:
        print("compose_vocab: %d conflict/input error(s); extensions must be "
              "append-only:" % len(compile_errors))
        for item in compile_errors:
            print("  - %s" % item)
        return 1

    currency = compilation_currency_errors(
        REPO_ROOT, admission, rendered, base_arg=args.base,
        extensions_arg=args.extensions)
    if currency:
        for error in currency:
            print("compose_vocab: %s" % error)
        return 1

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
            existing_text = fh.read()
            try:
                existing = kblib.parse_yaml_subset(existing_text)
            except kblib.YamlSubsetError as exc:
                print("compose_vocab --check: existing output is not "
                      "parseable: %s" % exc)
                return 2
        diff = first_diff_key(output, existing)
        if diff:
            print("compose_vocab --check: MISMATCH at key: %s" % diff)
            return 2
        if existing_text != rendered:
            print("compose_vocab --check: MISMATCH in generated provenance "
                  "or canonical rendering; values parse identically but %s "
                  "is not the artifact produced from the active inputs"
                  % args.output)
            return 2
        currency = compilation_currency_errors(
            REPO_ROOT, admission, rendered, base_arg=args.base,
            extensions_arg=args.extensions)
        if currency:
            for error in currency:
                print("compose_vocab --check: %s" % error)
            return 1
        print("compose_vocab --check: OK (%s matches composed values and provenance)"
              % args.output)
        return 0

    # The artifact is a gate input: `check_vocab` reads it to decide whether a
    # frontmatter value is legal, and an empty or half-written file makes every
    # value legal. A non-atomic write leaves exactly that state behind when the
    # process dies between truncate and flush, so the bytes are staged and
    # renamed into place, and never published unless they satisfy the same
    # predicate the consumer applies.
    kblib.atomic_write_text(output_path, rendered,
                            validator=kblib.parse_vocabulary_artifact)
    currency = compilation_currency_errors(
        REPO_ROOT, admission, rendered, base_arg=args.base,
        extensions_arg=args.extensions)
    if currency:
        for error in currency:
            print("compose_vocab: %s" % error)
        return 1
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
