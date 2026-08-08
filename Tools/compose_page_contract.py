#!/usr/bin/env python3
"""compose_page_contract.py -- persistent page-contract compiler.

Deterministically composes the selected profile's effective frontmatter
page contract (Tools/page_contract.yaml by default) from:

  --base           kernel applicability base
                   (default "kernel/K08 Metadata and Status/applicability-base.yaml";
                   semantic owner K08/06)
  --relationships  kernel relationship base
                   (default "kernel/K08 Metadata and Status/relationship-base.yaml";
                   semantic owner K08/08)
  the selected profile's `Metadata Contract` and `Vocabulary Extensions`
  slots. The active `selected_profile_manifest` in K00/03 determines the
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
  - a profile extension must not collide with a kernel field name.

Modes:
  default  recompute and write --output with a provenance header.
  --check  recompute and compare against the existing output; exit 0 when
           byte-identical, 2 otherwise.

Exit codes: 0 = ok / check passed; 1 = conflict or input error;
            2 = --check mismatch.
"""

import argparse
import hashlib
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, TOOLS_DIR)

import kblib  # noqa: E402

TOOL = "compose_page_contract"
TOOL_VERSION = "1.0.0"

DEFAULT_BASE = "kernel/K08 Metadata and Status/applicability-base.yaml"
DEFAULT_RELATIONSHIPS = (
    "kernel/K08 Metadata and Status/relationship-base.yaml"
)
DEFAULT_SOURCES_ROLE = (
    "kernel/K07 Sources and Accuracy/sources-role-base.yaml"
)
DEFAULT_OUTPUT = "Tools/page_contract.yaml"
ACTIVE_STATE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
METADATA_SLOT = "Metadata Contract"
VOCAB_SLOT = "Vocabulary Extensions"


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def fail(message):
    print("compose_page_contract: %s" % message)
    return 1


def resolve_profile_dir(root, override, errors):
    if override:
        profile_dir = override if os.path.isabs(override) \
            else os.path.join(root, override)
        if not os.path.isdir(profile_dir):
            errors.append("--profile does not name an existing directory: %s"
                          % override)
            return None
        return profile_dir
    state_path = os.path.join(root, ACTIVE_STATE_PATH)
    try:
        state_text = read_text(state_path)
    except OSError as exc:
        errors.append("cannot read the active Standards state: %s" % exc)
        return None
    state, parse_errors = kblib.active_standards_state(state_text)
    errors.extend(parse_errors)
    manifest = state.get("selected_profile_manifest") or ""
    if "{{" in manifest or not manifest.strip():
        errors.append("no instantiated selected_profile_manifest; pass "
                      "--profile for a validation run")
        return None
    manifest_path = os.path.join(root, manifest)
    if not os.path.isfile(manifest_path):
        errors.append("selected profile manifest does not exist: %s"
                      % manifest)
        return None
    return os.path.dirname(manifest_path)


def slot_file(root, profile_dir, slot, errors):
    manifest_path = os.path.join(profile_dir, "profile.md")
    try:
        manifest_text = read_text(manifest_path)
    except OSError as exc:
        errors.append("cannot read the profile manifest: %s" % exc)
        return None
    bindings = kblib.profile_slot_bindings(manifest_text)
    binding = bindings.get(slot)
    if binding is None:
        errors.append("the manifest does not bind the `%s` slot" % slot)
        return None
    kind, detail = kblib.resolve_profile_binding(binding, root, profile_dir)
    if kind != "path":
        errors.append("slot `%s` binding %r does not resolve" %
                      (slot, binding))
        return None
    return detail


def load_yaml(path, errors, label):
    try:
        return kblib.parse_yaml_subset(read_text(path))
    except (OSError, kblib.YamlSubsetError) as exc:
        errors.append("cannot parse %s (%s): %s" % (label, path, exc))
        return None


def compose(root, base_path, rel_path, sources_role_path, profile_dir):
    """Return (contract, provenance, errors); contract = fields + roles."""
    errors = []
    base = load_yaml(base_path, errors, "applicability base")
    relationships = load_yaml(rel_path, errors, "relationship base")
    sources_role = load_yaml(sources_role_path, errors, "sources-role base")
    contract_path = slot_file(root, profile_dir, METADATA_SLOT, errors)
    vocab_path = slot_file(root, profile_dir, VOCAB_SLOT, errors)
    contract = load_yaml(contract_path, errors, "Metadata Contract") \
        if contract_path else None
    vocab = load_yaml(vocab_path, errors, "Vocabulary Extensions") \
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

    provenance = []
    for label, path in (("applicability-base", base_path),
                        ("relationship-base", rel_path),
                        ("sources-role-base", sources_role_path),
                        ("metadata-contract", contract_path),
                        ("vocabulary-extensions", vocab_path)):
        digest = hashlib.sha256(
            open(path, "rb").read()).hexdigest()
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        provenance.append((label, rel, digest))
    ordered = {name: index[name] for name in fields}
    return {"fields": ordered, "section_roles": roles}, provenance, []


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
         "section_roles": contract["section_roles"]})
    return "\n".join(lines) + "\n" + body


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compose the effective frontmatter page contract from "
                    "the kernel bases and the selected profile's Metadata "
                    "Contract.")
    parser.add_argument("--root", default=REPO_ROOT,
                        help="vault root (default: this repository)")
    parser.add_argument("--base", default=None)
    parser.add_argument("--relationships", default=None)
    parser.add_argument("--sources-role", dest="sources_role", default=None)
    parser.add_argument("--profile",
                        help="profile directory for a validation run; the "
                             "vault selection stays with K00/03")
    parser.add_argument("--output", default=None)
    parser.add_argument("--check", action="store_true",
                        help="recompute and compare against the existing "
                             "output; exit 0 when byte-identical, 2 "
                             "otherwise")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    base_path = args.base or os.path.join(root, DEFAULT_BASE)
    rel_path = args.relationships or os.path.join(
        root, DEFAULT_RELATIONSHIPS)
    sources_role_path = args.sources_role or os.path.join(
        root, DEFAULT_SOURCES_ROLE)
    output = args.output or os.path.join(root, DEFAULT_OUTPUT)

    errors = []
    profile_dir = resolve_profile_dir(root, args.profile, errors)
    if profile_dir is None:
        for error in errors:
            print("compose_page_contract: %s" % error)
        return 1

    contract, provenance, errors = compose(root, base_path, rel_path,
                                           sources_role_path, profile_dir)
    if errors:
        for error in errors:
            print("compose_page_contract: %s" % error)
        return 1

    text = render(contract, provenance)
    if args.check:
        try:
            existing = read_text(output)
        except OSError as exc:
            print("compose_page_contract: --check cannot read %s: %s"
                  % (output, exc))
            return 2
        if existing != text:
            print("compose_page_contract: %s is stale; recompose it"
                  % output)
            return 2
        print("compose_page_contract: %s is current (%d field(s))"
              % (output, len(contract["fields"])))
        return 0
    kblib.atomic_write_text(output, text)
    print("compose_page_contract: wrote %s (%d field(s), %d section role(s))"
          % (output, len(contract["fields"]),
             len(contract["section_roles"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
