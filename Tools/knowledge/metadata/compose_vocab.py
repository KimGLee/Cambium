#!/usr/bin/env python3
"""compose_vocab.py -- persistent vocabulary compiler (kernel tooling).

Deterministically composes the selected-profile vocabulary artifact
(.cambium/derived/vocab.yaml by default) from two restricted-YAML-subset
inputs:

  --base        kernel vocabulary base
                (default: "kernel/K08 Metadata and Status/vocabulary-base.yaml")
  --extensions  selected profile's vocabulary extensions. The canonical
                adopter Standards state determines the one
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
  default  recompute and write --output (.cambium/derived/vocab.yaml by
           default),
           with an English provenance header (input paths + sha256).
  --check  recompute and compare against the existing --output at the
           value and provenance level. Exit 0 only when the deterministic
           artifact is byte-identical; exit 2 with the first differing key
           or a provenance/rendering mismatch otherwise.

Exit codes: 0 = ok / check passed; 1 = conflict or input error;
            2 = --check mismatch.

Only the python3 standard library is used; YAML parsing goes through the
shared ``Tools.platform.common.kblib`` restricted subset parser.
"""
from Tools.platform.repository.repository import repository_source_root, tools_source_root

import hashlib
import json
import os
import re
import sys
from pathlib import Path

TOOLS_DIR = tools_source_root(__file__)
REPO_ROOT = repository_source_root(__file__)

import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.governance.profile.profile_admission as profile_admission  # noqa: E402
import Tools.governance.profile.profile_contract as profile_contract  # noqa: E402
import Tools.governance.profile.profile_layout_contract as profile_layout_contract  # noqa: E402
import Tools.execution.task_runtime.runtime_paths as runtime_paths  # noqa: E402
import Tools.knowledge.metadata.vocabulary_contract as vocabulary_contract  # noqa: E402
from Tools.platform.repository import repository  # noqa: E402

TOOL_VERSION = "1.7.0"

DEFAULT_BASE = "kernel/K08 Metadata and Status/vocabulary-base.yaml"
DEFAULT_OUTPUT = runtime_paths.VOCAB_ARTIFACT_PATH
ACTIVE_STATE_PATH = runtime_paths.ACTIVE_STANDARDS_PATH
UNINSTANTIATED_RE = re.compile(r"\{\{.*?\}\}")

# There is deliberately no DEFAULT_EXTENSIONS. Naming one profile here would
# make that profile the tool's implicit answer to "which vocabulary is the
# real one", which is a decision the kernel does not make and this script
# must not make on its behalf. It also breaks silently rather than loudly:
# in a clone that does not carry the named profile, a hardcoded default
# resolves to a missing file, and in a clone that carries a different
# profile, it composes the wrong one without saying so.
EXTENSIONS_BASENAME = "vocabulary-extensions.yaml"
PROFILES_DIR = profile_layout_contract.PROFILES_DIRECTORY
# Directory names under profiles/ that are not selectable profiles:
# `_template` is an unfilled skeleton whose value lists are empty by design,
# so composing against it would yield a base-only artifact that looks valid.
NON_PROFILE_DIRS = profile_layout_contract.RESERVED_PROFILE_IDS
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
        if profile_layout_contract.PROFILE_MANIFEST_NAME in files:
            relative = os.path.relpath(
                os.path.join(
                    current, profile_layout_contract.PROFILE_MANIFEST_NAME),
                REPO_ROOT)
            found.append(Path(relative).as_posix())
    return found



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
              "until canonical adopter Standards state selects one):")
        for item in candidates:
            print("    %s" % item)
    else:
        print("  No filled profile manifest in this repository resolves a "
              "Vocabulary Extensions binding.")
        print("  Copy profiles/_template/ to profiles/<your-profile-id>/ "
              "and fill it in first.")



def load_subset(path, text=None):
    if text is not None:
        return kblib.parse_yaml_subset(text)
    with open(path, "r", encoding="utf-8") as fh:
        return kblib.parse_yaml_subset(fh.read())


def compiled_artifact(root, admission, *, base_arg=DEFAULT_BASE,
                      extensions_arg=None):
    """Return canonical vocabulary bytes from one admitted input snapshot."""
    errors = []
    try:
        _base_relative, base_snapshot = repository.repository_input_snapshot(
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
    try:
        volatility_defaults = \
            profile_contract.volatility_defaults_projection(
                admission.contract)
    except (AttributeError, TypeError,
            profile_contract.ProfileContractError) as exc:
        return None, None, [
            "authorized Profile has no valid typed volatility_defaults "
            "projection: %s" % exc]
    output, conflicts = compose(
        base, profile, base_arg, extensions_arg, admission.profile_id,
        volatility_defaults=volatility_defaults)
    errors.extend(conflicts)
    if errors:
        return None, None, errors
    base_sha = base_snapshot.sha256.split(":", 1)[1]
    ext_sha = hashlib.sha256(
        admission.slot_bytes["Vocabulary Extensions"]).hexdigest()
    rendered = render(output, build_header(
        base_arg, extensions_arg, base_sha, ext_sha))
    return rendered, output, []


def _admitted_projection(root, artifact_path, admission):
    """Return one current artifact snapshot and its typed compiled value."""
    rendered, output, errors = compiled_artifact(root, admission)
    if errors:
        return None, None, errors
    try:
        relative, artifact = repository.repository_input_snapshot(
            root, artifact_path, "compiled vocabulary")
    except (OSError, ValueError) as exc:
        return None, None, [
            "compiled vocabulary is unsafe or unreadable: %s" % exc]
    if artifact.data != rendered.encode("utf-8"):
        return None, None, [
            "compiled vocabulary %s does not match the selected Profile and "
            "kernel base; recompose it with Tools/compose_vocab.py" % relative
        ]
    currency = profile_admission.currency_errors(admission)
    return (None, None, currency) if currency else (artifact, output, [])


def admitted_artifact(root, artifact_path, admission):
    """Return immutable compiled bytes iff they equal the admitted IR."""
    artifact, _output, errors = _admitted_projection(
        root, artifact_path, admission)
    return artifact, errors


def admitted_volatility_defaults(root, artifact_path, admission):
    """Project defaults from one current canonical vocabulary artifact.

    Consumers receive the artifact snapshot that proves byte currentness and
    the compiler-owned typed value.  They do not parse the generated YAML as
    an independent volatility policy source.
    """
    artifact, output, errors = _admitted_projection(
        root, artifact_path, admission)
    if errors:
        return None, None, errors
    defaults = output.get("volatility_defaults") \
        if isinstance(output, dict) else None
    if not isinstance(defaults, dict):
        return None, None, [
            "compiled vocabulary has no typed volatility_defaults projection"]
    return artifact, dict(defaults), []


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


def compose(base, profile, base_arg, ext_arg, profile_id, *,
            volatility_defaults):
    """Compose the merged vocabulary. Returns (output_dict, conflicts)."""
    conflicts = []

    try:
        vocabulary_contract.validate_vocabulary_base(base)
    except vocabulary_contract.VocabularyContractError as exc:
        return None, ["base: %s" % exc]

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

    volatility_defaults = dict(volatility_defaults)
    if profile.get("volatility_defaults") != volatility_defaults:
        conflicts.append(
            "extensions: volatility_defaults differs from the authorized "
            "typed Profile contract")
    domain_values = list(volatility_defaults)
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
    parser = kblib.ArgumentParser(
        description="Deterministically compose the vocabulary artifact "
        "from the kernel base and the selected profile's extensions."
    )
    parser.add_argument("--base", default=DEFAULT_BASE,
                        help="the kernel vocabulary base the extensions are "
                             "appended to (default: %s)" % DEFAULT_BASE)
    parser.add_argument(
        "--extensions",
        default=None,
        help="the active profile's %s. Canonical adopter Standards state "
             "selects the path; when this "
             "flag is present it must name that same path"
        % EXTENSIONS_BASENAME,
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="composed vocabulary artifact to write, or to "
                             "compare against under --check (default: %s)"
                             % DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute and compare against the existing output; "
        "exit 0 when values and provenance are identical, 2 otherwise",
    )
    args = parser.parse_args(argv)

    try:
        output_path = kblib.registered_repository_artifact_path(
            REPO_ROOT, args.output, DEFAULT_OUTPUT)
    except ValueError as exc:
        print("compose_vocab: unsafe artifact output: %s" % exc)
        return 1

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

    if args.check:
        if not os.path.exists(output_path):
            print("compose_vocab --check: output not found: %s" % output_path)
            return 2
        existing_text = kblib.read_text(output_path)
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
    runtime_paths.ensure_directory(REPO_ROOT, "derived-root")
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
