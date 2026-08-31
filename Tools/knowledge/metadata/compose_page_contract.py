#!/usr/bin/env python3
"""compose_page_contract.py -- persistent page-contract compiler.

Deterministically composes the selected profile's effective frontmatter page
contract (.cambium/derived/page_contract.yaml by default) from:

  --base           kernel applicability base
                   (default "kernel/K08 Metadata and Status/applicability-base.yaml";
                   semantic owner K08/06)
  --relationships  kernel relationship base
                   (default "kernel/K08 Metadata and Status/relationship-base.yaml";
                   semantic owner K08/08)
  the selected profile's `Metadata Contract` and `Vocabulary Extensions`
  slots. The canonical adopter Standards state determines the
  selection; `--profile` names a profile directory explicitly for
  validation runs and never selects it for the vault.

Merge policy (K08/06 two-layer composition):
  - kernel fields first in base order, then kernel relationships, then
    profile extension fields and relationship extensions, then fields the
    Vocabulary Extensions slot registers that carry no Metadata Contract
    entry (defaulted to optional / nonempty-string; list-shaped when the
    vocabulary marks them so);
  - a profile difference must name an existing kernel field and only
    tighten it (optional -> required, optional -> conditional,
    conditional -> required); anything else is a conflict and exits 1;
  - a profile extension must not collide with a kernel field name;
  - the K08/09 boundary projection display labels compose as kernel
    defaults overlaid by the profile's `boundary_projection.labels`
    (display text only, never schema).

Modes:
  default  recompute and write --output with a provenance header.
  --check  recompute and compare against the existing output; exit 0 when
           byte-identical, 2 otherwise.

Exit codes: 0 = ok / check passed; 1 = conflict or input error;
            2 = --check mismatch.
"""
from Tools.platform.repository.repository import repository_source_root, tools_source_root

import hashlib
import os
import re
import sys

TOOLS_DIR = tools_source_root(__file__)
REPO_ROOT = repository_source_root(__file__)

import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.governance.profile.profile_admission as profile_admission  # noqa: E402
import Tools.governance.profile.profile_contract as profile_contract  # noqa: E402
import Tools.execution.task_runtime.runtime_paths as runtime_paths  # noqa: E402
from Tools.platform.repository import repository  # noqa: E402

TOOL = "compose_page_contract"
TOOL_VERSION = "1.2.0"

DEFAULT_BASE = "kernel/K08 Metadata and Status/applicability-base.yaml"
DEFAULT_RELATIONSHIPS = (
    "kernel/K08 Metadata and Status/relationship-base.yaml"
)
DEFAULT_SOURCES_ROLE = (
    "kernel/K07 Sources and Accuracy/sources-role-base.yaml"
)
DEFAULT_OUTPUT = runtime_paths.PAGE_CONTRACT_ARTIFACT_PATH
ACTIVE_STATE_PATH = runtime_paths.ACTIVE_STANDARDS_PATH
METADATA_SLOT = profile_contract.METADATA_CONTRACT_SLOT
VOCAB_SLOT = profile_contract.VOCABULARY_EXTENSIONS_SLOT
PROVENANCE_RE = re.compile(
    r"^# input ([a-z][a-z0-9-]*): (.+) sha256=([0-9a-f]{64})$")


def load_yaml(path, errors, label, text=None):
    try:
        return kblib.parse_yaml_subset(
            kblib.read_text(path) if text is None else text)
    except (OSError, kblib.YamlSubsetError) as exc:
        errors.append("cannot parse %s (%s): %s" % (label, path, exc))
        return None


def compose(root, base_path, rel_path, sources_role_path, admission):
    """Return (contract, provenance, errors); contract = fields + roles."""
    errors = []
    kernel_snapshots = {}
    for label, path in (
            ("applicability base", base_path),
            ("relationship base", rel_path),
            ("sources-role base", sources_role_path)):
        try:
            _relative, kernel_snapshots[path] = \
                repository.repository_input_snapshot(root, path, label)
        except (OSError, ValueError) as exc:
            errors.append("cannot bind %s (%s): %s" % (label, path, exc))
    base = load_yaml(
        base_path, errors, "applicability base",
        kernel_snapshots[base_path].read_text()) \
        if base_path in kernel_snapshots else None
    relationships = load_yaml(
        rel_path, errors, "relationship base",
        kernel_snapshots[rel_path].read_text()) \
        if rel_path in kernel_snapshots else None
    sources_role = load_yaml(
        sources_role_path, errors, "sources-role base",
        kernel_snapshots[sources_role_path].read_text()) \
        if sources_role_path in kernel_snapshots else None
    contract_path, error = profile_admission.require_slot(
        admission, METADATA_SLOT)
    if error:
        errors.append(error)
    vocab_path, error = profile_admission.require_slot(admission, VOCAB_SLOT)
    if error:
        errors.append(error)
    contract = load_yaml(
        contract_path, errors, "Metadata Contract",
        admission.slot_text(METADATA_SLOT)) \
        if contract_path else None
    vocab = load_yaml(
        vocab_path, errors, "Vocabulary Extensions",
        admission.slot_text(VOCAB_SLOT)) \
        if vocab_path else None
    if errors:
        return None, None, errors

    if not isinstance(base, dict) or \
            not isinstance(base.get("fields"), dict):
        errors.append("applicability base carries no fields mapping")
    if not isinstance(relationships, dict) or \
            not isinstance(relationships.get("relationships"), dict):
        errors.append("relationship base carries no relationships mapping")
    if isinstance(contract, dict):
        for _check, label, details in \
                kblib.validate_metadata_contract_shape(contract):
            errors.append("Metadata Contract %s: %s" % (label, details))
    else:
        errors.append("Metadata Contract is not a mapping")
    if errors:
        return None, None, errors

    fields = []
    index = {}

    def add_field(name, spec, origin):
        if name in index:
            errors.append("field %r declared twice (%s vs %s)" %
                          (name, index[name]["origin"], origin))
            return
        spec = dict(spec)
        spec["origin"] = origin
        index[name] = spec
        fields.append(name)

    for name, spec in base["fields"].items():
        if not isinstance(spec, dict) or spec.get("mode") not in \
                kblib.METADATA_MODES:
            errors.append("applicability base field %r has no valid mode"
                          % name)
            continue
        add_field(name, spec, "kernel")
    for name, spec in relationships["relationships"].items():
        if not isinstance(spec, dict) or spec.get("mode") not in \
                kblib.METADATA_MODES:
            errors.append("relationship base field %r has no valid mode"
                          % name)
            continue
        add_field(name, spec, "kernel-relationship")

    for entry in contract.get("applicability_differences") or []:
        name = entry.get("field")
        current = index.get(name)
        if current is None or not current["origin"].startswith("kernel"):
            errors.append("difference %r does not name a kernel base field"
                          % name)
            continue
        transition = (current["mode"], entry.get("mode"))
        if transition not in kblib.METADATA_TIGHTENING:
            errors.append(
                "difference %r declares %s -> %s, which is not a "
                "tightening" % (name, transition[0], transition[1]))
            continue
        current["mode"] = entry["mode"]
        if entry.get("condition") is not None:
            current["condition"] = entry["condition"]
        current["origin"] = current["origin"] + "+profile"

    for entry in contract.get("extension_fields") or []:
        add_field(entry.get("field"), {
            "mode": entry.get("mode"), "shape": entry.get("shape"),
            **({"condition": entry["condition"]}
               if entry.get("condition") is not None else {}),
            "owner": entry.get("owner"),
        }, "profile")
    for entry in contract.get("relationship_extensions") or []:
        add_field(entry.get("field"), {
            "mode": entry.get("mode"), "shape": entry.get("shape"),
            "direction": entry.get("direction"),
            "target": entry.get("target"),
            **({"condition": entry["condition"]}
               if entry.get("condition") is not None else {}),
            "owner": entry.get("owner"),
        }, "profile-relationship")

    # Vocabulary-registered fields with no Metadata Contract entry.
    if isinstance(vocab, dict):
        vocab_fields = []
        extensions = vocab.get("frontmatter_extensions")
        if isinstance(extensions, dict):
            for name in extensions.get("fields") or []:
                vocab_fields.append(str(name))
        base_names = set(base["fields"])
        vocab_field_map = vocab.get("fields")
        if not isinstance(vocab_field_map, dict):
            vocab_field_map = {}
        for name, spec in vocab_field_map.items():
            if isinstance(spec, dict) and name not in base_names and \
                    name not in ("type", "domain", "scope", "level", "depth",
                                 "priority"):
                vocab_fields.append(str(name))
        for name in vocab_fields:
            if name not in index:
                add_field(name, {"mode": "optional",
                                 "shape": "nonempty-string"},
                          "vocabulary")

    if errors:
        return None, None, errors

    roles = {}
    if not isinstance(sources_role, dict) or \
            sources_role.get("role") != "sources":
        errors.append("sources-role base does not declare role: sources")
        return None, None, errors
    roles["sources"] = {
        "titles": [str(v) for v in sources_role.get("default_titles") or []],
        "applicability": sources_role.get("applicability"),
        "binding_satisfies": sources_role.get("binding_satisfies"),
        "origin": "kernel",
    }
    roles["related"] = {"titles": ["Related"], "origin": "kernel"}
    for entry in contract.get("section_roles") or []:
        role = entry.get("role")
        if role not in roles:
            continue
        titles = [str(v) for v in entry.get("titles") or []]
        titles += [str(v) for v in entry.get("aliases") or []]
        roles[role]["titles"] = titles
        roles[role]["origin"] = roles[role].get("origin", "kernel") + \
            "+profile"

    # K08/09 boundary projection labels: kernel defaults overlaid by the
    # profile's boundary_projection.labels (validated by the shared shape
    # contract above; display text only).
    boundary_labels = dict(kblib.BOUNDARY_PROJECTION_LABELS)
    profile_projection = contract.get("boundary_projection")
    if isinstance(profile_projection, dict):
        for key, value in (profile_projection.get("labels") or {}).items():
            if key in boundary_labels and isinstance(value, str) and \
                    value.strip():
                boundary_labels[key] = value

    provenance = []
    admitted_bytes = {
        base_path: kernel_snapshots[base_path].data,
        rel_path: kernel_snapshots[rel_path].data,
        sources_role_path: kernel_snapshots[sources_role_path].data,
        contract_path: admission.slot_bytes.get(METADATA_SLOT),
        vocab_path: admission.slot_bytes.get(VOCAB_SLOT),
    }
    for label, path in (("applicability-base", base_path),
                        ("relationship-base", rel_path),
                        ("sources-role-base", sources_role_path),
                        ("metadata-contract", contract_path),
                        ("vocabulary-extensions", vocab_path)):
        data = admitted_bytes.get(path)
        digest = hashlib.sha256(data).hexdigest()
        if path in kernel_snapshots:
            rel = kernel_snapshots[path].repository_path
        else:
            rel = os.path.relpath(path, root).replace(os.sep, "/")
        provenance.append((label, rel, digest))
    ordered = {name: index[name] for name in fields}
    return {"fields": ordered, "section_roles": roles,
            "boundary_projection": {"labels": boundary_labels}}, \
        provenance, []


def render(contract, provenance):
    lines = [
        "# Generated by Tools/compose_page_contract.py — a reproducible",
        "# projection of its declared inputs, never a rule owner",
        "# (owners: K08/06, K08/07, K08/08 and the selected profile's",
        "# Metadata Contract).",
    ]
    for label, rel, digest in provenance:
        lines.append("# input %s: %s sha256=%s" % (label, rel, digest))
    body = kblib.canonical_yaml(
        {"schema_version": 1, "fields": contract["fields"],
         "section_roles": contract["section_roles"],
         "boundary_projection": contract["boundary_projection"]})
    return "\n".join(lines) + "\n" + body


def compiled_artifact(root, admission, *, base_path=None, rel_path=None,
                      sources_role_path=None):
    """Return deterministic page-contract bytes from one admitted revision."""
    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    base_path = base_path or os.path.join(root, DEFAULT_BASE)
    rel_path = rel_path or os.path.join(root, DEFAULT_RELATIONSHIPS)
    sources_role_path = sources_role_path or os.path.join(
        root, DEFAULT_SOURCES_ROLE)
    contract, provenance, errors = compose(
        root, base_path, rel_path, sources_role_path, admission)
    if errors:
        return None, None, errors
    return render(contract, provenance), contract, []


def _declared_kernel_inputs(artifact):
    """Read the three kernel input identities from immutable artifact bytes."""
    declared = {}
    try:
        lines = artifact.read_text().splitlines()
    except UnicodeError as exc:
        raise ValueError("compiled page contract is not UTF-8: %s" % exc)
    for line in lines:
        match = PROVENANCE_RE.match(line)
        if match is None:
            continue
        label, path, _digest = match.groups()
        if label in declared:
            raise ValueError(
                "compiled page contract repeats input %s" % label)
        declared[label] = path
    required = (
        "applicability-base", "relationship-base", "sources-role-base")
    missing = [label for label in required if label not in declared]
    if missing:
        raise ValueError(
            "compiled page contract lacks provenance for %s" %
            ", ".join(missing))
    return tuple(declared[label] for label in required)


def admitted_artifact(root, artifact_path, admission):
    """Return immutable compiled bytes iff they equal the admitted IR."""
    try:
        _relative, artifact = repository.repository_input_snapshot(
            root, artifact_path, "compiled page contract")
    except (OSError, ValueError) as exc:
        return None, [
            "compiled page contract is unsafe or unreadable: %s" % exc]
    compile_kwargs = {}
    if admission.active_state_repo_path is None:
        # Explicit Profile validation permits the composer's explicit kernel
        # base inputs.  They are names, not trusted bytes: each is rebound via
        # a canonical no-follow snapshot and the entire artifact must then be
        # byte-identical.  Active runtime admission always uses the canonical
        # kernel bases and cannot select inputs through an artifact.
        try:
            base_path, rel_path, sources_role_path = \
                _declared_kernel_inputs(artifact)
        except ValueError as exc:
            return None, [str(exc)]
        compile_kwargs = {
            "base_path": base_path,
            "rel_path": rel_path,
            "sources_role_path": sources_role_path,
        }
    text, _contract, errors = compiled_artifact(
        root, admission, **compile_kwargs)
    if errors:
        return None, errors
    if artifact.data != text.encode("utf-8"):
        return None, [
            "compiled page contract %s does not match the selected Profile "
            "and kernel bases; recompose it with "
            "Tools/compose_page_contract.py" % artifact.repository_path
        ]
    currency = profile_admission.currency_errors(admission)
    return (None, currency) if currency else (artifact, [])


def artifact_currency_errors(root, artifact_path, admission):
    """Require a compiled page contract to equal the admitted deterministic IR."""
    _artifact, errors = admitted_artifact(root, artifact_path, admission)
    return errors


def compilation_currency_errors(root, admission, expected_text, *, base_path,
                                rel_path, sources_role_path):
    """Recompile all inputs and require the initially rendered IR to persist."""
    current_text, _contract, errors = compiled_artifact(
        root, admission, base_path=base_path, rel_path=rel_path,
        sources_role_path=sources_role_path)
    if errors:
        return errors
    if current_text != expected_text:
        return [
            "kernel compiler inputs changed during page-contract composition; "
            "rerun against one stable input revision"
        ]
    return profile_admission.currency_errors(admission)


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Compose the effective frontmatter page contract from "
                    "the kernel bases and the selected profile's Metadata "
                    "Contract.")
    parser.add_argument("--root", default=REPO_ROOT,
                        help="vault root (default: this repository)")
    parser.add_argument("--base", default=None,
                        help="applicability base to compile from (default: "
                             "%s under --root)" % DEFAULT_BASE)
    parser.add_argument("--relationships", default=None,
                        help="relationship base to compile from (default: "
                             "%s under --root)" % DEFAULT_RELATIONSHIPS)
    parser.add_argument("--sources-role", dest="sources_role", default=None,
                        help="sources-role base to compile from (default: "
                             "%s under --root)" % DEFAULT_SOURCES_ROLE)
    parser.add_argument("--profile",
                        help="profile directory for a validation run; the "
                             "vault selection stays with K00/03")
    parser.add_argument("--output", default=None,
                        help="compiled page contract to write, or to compare "
                             "against under --check (default: %s under "
                             "--root)" % DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true",
                        help="recompute and compare against the existing "
                             "output; exit 0 when byte-identical, 2 "
                             "otherwise")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    try:
        output = kblib.registered_repository_artifact_path(
            root, args.output or DEFAULT_OUTPUT, DEFAULT_OUTPUT)
    except ValueError as exc:
        print("compose_page_contract: unsafe artifact output: %s" % exc)
        return 1
    base_path = args.base or os.path.join(root, DEFAULT_BASE)
    rel_path = args.relationships or os.path.join(
        root, DEFAULT_RELATIONSHIPS)
    sources_role_path = args.sources_role or os.path.join(
        root, DEFAULT_SOURCES_ROLE)
    admission, errors = profile_admission.admit_profile(
        root, args.profile, active_state_path=ACTIVE_STATE_PATH)
    if admission is None:
        for error in errors:
            print("compose_page_contract: %s" % error)
        return 1

    text, contract, errors = compiled_artifact(
        root, admission, base_path=base_path, rel_path=rel_path,
        sources_role_path=sources_role_path)
    if errors:
        for error in errors:
            print("compose_page_contract: %s" % error)
        return 1

    currency = compilation_currency_errors(
        root, admission, text, base_path=base_path, rel_path=rel_path,
        sources_role_path=sources_role_path)
    if currency:
        for error in currency:
            print("compose_page_contract: %s" % error)
        return 1
    if args.check:
        try:
            existing = kblib.read_text(output)
        except OSError as exc:
            print("compose_page_contract: --check cannot read %s: %s"
                  % (output, exc))
            return 2
        if existing != text:
            print("compose_page_contract: %s is stale; recompose it"
                  % output)
            return 2
        currency = compilation_currency_errors(
            root, admission, text, base_path=base_path, rel_path=rel_path,
            sources_role_path=sources_role_path)
        if currency:
            for error in currency:
                print("compose_page_contract: %s" % error)
            return 1
        print("compose_page_contract: %s is current (%d field(s))"
              % (output, len(contract["fields"])))
        return 0
    runtime_paths.ensure_directory(root, "derived-root")
    kblib.atomic_write_text(output, text)
    currency = compilation_currency_errors(
        root, admission, text, base_path=base_path, rel_path=rel_path,
        sources_role_path=sources_role_path)
    if currency:
        for error in currency:
            print("compose_page_contract: %s" % error)
        return 1
    print("compose_page_contract: wrote %s (%d field(s), %d section role(s))"
          % (output, len(contract["fields"]),
             len(contract["section_roles"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
