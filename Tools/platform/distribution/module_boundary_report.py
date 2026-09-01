#!/usr/bin/env python3
"""Report what the Tool module boundary contract observes.

The Tool-owned contract guards the public surface, and a public surface cannot
see everything that went wrong in this tree. A module can absorb a
new mode, grow a thousand-line function, or take on a second responsibility
without adding one public symbol, and the guard will stay green through all
of it -- correctly, because none of that broke a compatibility boundary.

So this prints the signals instead of judging them.  Line counts, top-level
definitions, importer counts and dependency components are observations that
a reviewer weighs; the moment one of them became an exit code it would be a
byte cap wearing a different name, and the register this contract deliberately
did not copy already showed what byte caps cost.  The exit code here is 0 for
a readable tree and non-zero only when the tree cannot be parsed at all.

Also emits the manifest itself (`--emit-manifest`).  Dependency facts remain
derived from the tree, while the Area / Domain / Layer classification is a
reviewed engineering decision preserved across regeneration.  A new module is
emitted as `unclassified` and therefore cannot pass the boundary guard until
its responsibility has been placed deliberately.
"""
from Tools.platform.repository.repository import repository_source_root

import argparse
import collections
import json
import os
import subprocess
import sys

import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.platform.distribution.module_boundary_facts as facts_module  # noqa: E402


# Written by a person, recomputed by nobody: a machine can see that a
# consumption exists, never why it is acceptable or what would end it.  These
# fields therefore survive regeneration untouched -- otherwise the contract's
# demand for a necessity and a retirement condition would hold only until the
# next time anyone ran the generator.
ANNOTATED_FIELDS = ("necessity", "retires_when")
PRESERVED_FIELDS = ("content_sha256",) + ANNOTATED_FIELDS
CLASSIFICATION_FIELDS = ("area", "domain", "layer")
MANIFEST_SCHEMA_VERSION = 3
MANIFEST_FIELDS = frozenset(("schema_version", "modules"))
MODULE_FIELDS = frozenset((
    "module", "path", "area", "domain", "layer", "public", "exceptions",
))
REQUIRED_MODULE_FIELDS = MODULE_FIELDS - {"exceptions"}
EXCEPTION_FIELDS = frozenset((
    "consumer", "symbol", "content_sha256", "necessity", "retires_when",
))
REQUIRED_EXCEPTION_FIELDS = EXCEPTION_FIELDS - {"content_sha256"}

REPO_ROOT = repository_source_root(__file__)


def manifest_errors(document):
    """Return closed-shape errors for the current module boundary contract."""
    errors = []
    if not isinstance(document, dict):
        return ["module boundary manifest must be a mapping"]
    missing = sorted(MANIFEST_FIELDS - set(document))
    extra = sorted(set(document) - MANIFEST_FIELDS)
    if missing or extra:
        errors.append(
            "module boundary manifest fields are not closed: missing=%s "
            "extra=%s" % (missing, extra))
    if document.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("module boundary schema_version must be %d" %
                      MANIFEST_SCHEMA_VERSION)
    rows = document.get("modules")
    if not isinstance(rows, list):
        errors.append("module boundary modules must be a list")
        return errors
    names = set()
    paths = set()
    for index, row in enumerate(rows):
        label = "module boundary modules[%d]" % index
        if not isinstance(row, dict):
            errors.append("%s must be a mapping" % label)
            continue
        row_missing = sorted(REQUIRED_MODULE_FIELDS - set(row))
        row_extra = sorted(set(row) - MODULE_FIELDS)
        if row_missing or row_extra:
            errors.append("%s fields are not closed: missing=%s extra=%s" %
                          (label, row_missing, row_extra))
        for field, seen in (("module", names), ("path", paths)):
            value = row.get(field)
            if not isinstance(value, str) or not value:
                errors.append("%s %s must be non-empty text" %
                              (label, field))
            elif value in seen:
                errors.append("%s repeats %s %s" % (label, field, value))
            else:
                seen.add(value)
        public = row.get("public")
        if (not isinstance(public, list) or
                any(not isinstance(value, str) or not value
                    for value in public) or
                len(public) != len(set(public))):
            errors.append("%s public must be a unique text list" % label)
        exceptions = row.get("exceptions", [])
        if not isinstance(exceptions, list):
            errors.append("%s exceptions must be a list" % label)
            continue
        exception_keys = set()
        for exception_index, exception in enumerate(exceptions):
            exception_label = "%s exceptions[%d]" % (
                label, exception_index)
            if not isinstance(exception, dict):
                errors.append("%s must be a mapping" % exception_label)
                continue
            exception_missing = sorted(
                REQUIRED_EXCEPTION_FIELDS - set(exception))
            exception_extra = sorted(set(exception) - EXCEPTION_FIELDS)
            if exception_missing or exception_extra:
                errors.append(
                    "%s fields are not closed: missing=%s extra=%s" %
                    (exception_label, exception_missing, exception_extra))
                continue
            if any(not isinstance(exception.get(field), str) or
                   not exception.get(field)
                   for field in REQUIRED_EXCEPTION_FIELDS):
                errors.append("%s fields must be non-empty text" %
                              exception_label)
                continue
            content_sha256 = exception.get("content_sha256")
            if (content_sha256 is not None and
                    (not isinstance(content_sha256, str) or
                     not content_sha256)):
                errors.append(
                    "%s content_sha256 must be non-empty text when present" %
                    exception_label)
                continue
            key = (exception["consumer"], exception["symbol"])
            if key in exception_keys:
                errors.append("%s repeats consumer/symbol %s.%s" %
                              (label, key[0], key[1]))
            exception_keys.add(key)
    return errors


def _resolved_classifications(rows, facts):
    """Return exact reviewed classifications for current module identities.

    A moved or newly added module is deliberately unclassified.  Carrying a
    classification by basename, former package prefix, or wrapper inference
    would keep a one-time source-layout migration alive as permanent policy.
    """
    recorded = {
        row.get("module"): {
            field: row.get(field, "unclassified")
            for field in CLASSIFICATION_FIELDS
        }
        for row in rows
        if row.get("module")
    }
    result = {}
    for module in facts:
        classification = recorded.get(module)
        if classification is None:
            result[module] = {
                field: "unclassified" for field in CLASSIFICATION_FIELDS
            }
            continue
        result[module] = dict(classification)
    return result


def _classification_map(repo_root, facts=None):
    path = os.path.join(repo_root, "Tools", "module-boundaries.yaml")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            document = kblib.parse_yaml_subset(handle.read())
    except (OSError, UnicodeError, kblib.YamlSubsetError):
        return {}
    if manifest_errors(document):
        return {}
    rows = document.get("modules") or ()
    if facts is not None:
        return _resolved_classifications(rows, facts)
    return {
        row.get("module"): {
            field: row.get(field, "unclassified")
            for field in CLASSIFICATION_FIELDS
        }
        for row in rows if row.get("module")
    }


def build_report(repo_root):
    facts = facts_module.collect(repo_root)
    classifications = _classification_map(repo_root, facts)
    graph = facts_module.import_graph(facts)
    pairs = facts_module.consumption_pairs(facts)
    private = facts_module.private_pairs(facts)

    importers = {}
    for consumer, target, _symbol in pairs:
        importers.setdefault(target, set()).add(consumer)

    modules = []
    for name in sorted(facts):
        entry = facts[name]
        consumed = {symbol for c, m, symbol in pairs if m == name}
        row = {
            "module": name,
            "path": entry["path"],
            "lines": entry["lines"],
            "top_level_defs": len(entry["top_level_defs"]),
            "top_level_classes": len(entry["top_level_classes"]),
            "imports": len(entry["imports"]),
            "importers": len(importers.get(name, ())),
            "consumed_symbols": len(consumed),
            "private_consumed": len(
                {s for c, m, s in private if m == name}),
        }
        row.update(classifications.get(name, {
            field: "unclassified" for field in CLASSIFICATION_FIELDS
        }))
        modules.append(row)

    areas = collections.Counter(row["area"] for row in modules)
    domains = collections.Counter(
        "%s/%s" % (row["area"], row["domain"]) for row in modules)
    layers = collections.Counter(row["layer"] for row in modules)

    return {
        "shipped_modules": len(facts),
        "total_lines": sum(row["lines"] for row in modules),
        "consumption_pairs": len(pairs),
        "private_consumption_pairs": len(private),
        "cycles": facts_module.strongly_connected(graph),
        "classification": {
            "areas": dict(sorted(areas.items())),
            "domains": dict(sorted(domains.items())),
            "layers": dict(sorted(layers.items())),
        },
        "modules": modules,
    }


def render_hierarchy(report):
    """Render the reviewed Area -> Domain -> Layer -> module hierarchy.

    This is a navigation projection of ``module-boundaries.yaml``.  It does
    not infer responsibility from filenames and therefore cannot become a
    second classification owner.
    """
    grouped = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    for row in report["modules"]:
        grouped[row["area"]][row["domain"]][row["layer"]].append(row)

    lines = ["Tool implementation hierarchy"]
    for area in sorted(grouped):
        lines.append("%s/" % area)
        for domain in sorted(grouped[area]):
            lines.append("  %s/" % domain)
            for layer in sorted(grouped[area][domain]):
                lines.append("    %s/" % layer)
                for row in sorted(
                        grouped[area][domain][layer],
                        key=lambda value: value["module"]):
                    lines.append("      %s  [%s]" % (
                        row["module"], row["path"]))
    return "\n".join(lines) + "\n"


def _baseline(repo_root, base_ref):
    """Report the same numbers for a base revision, when one is named."""
    if not base_ref:
        return None
    try:
        out = kblib.run_cambium_subprocess(
            ["git", "-C", repo_root, "rev-parse", "--verify", base_ref],
            capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    # Comparing against a checked-out worktree keeps this a pure read of the
    # base revision; rewriting the live tree to measure it would make a
    # reporting tool capable of destroying the work it reports on.
    import tempfile
    with tempfile.TemporaryDirectory() as scratch:
        add = kblib.run_cambium_subprocess(
            ["git", "-C", repo_root, "worktree", "add", "--detach",
             scratch, base_ref],
            capture_output=True, text=True, timeout=120)
        if add.returncode != 0:
            return None
        try:
            return build_report(scratch)
        finally:
            kblib.run_cambium_subprocess(
                ["git", "-C", repo_root, "worktree", "remove", "--force",
                 scratch], capture_output=True, text=True, timeout=60)


def _recorded_manifest(manifest_path, facts=None):
    """Read reviewed declarations that regeneration must not erase.

    The register holds derived dependency facts and three reviewed judgments:
    why a private consumption is temporarily necessary, where a module
    belongs in the Tool hierarchy, and which public names form the reviewed
    current module interface. Regeneration must carry all three across
    untouched. An internal import graph cannot observe every intended
    consumer, so absence from that graph is never sufficient evidence that a
    public name may be removed.

    Regeneration must also not be able to launder a drifted exception.  The guard
    refuses an exception whose definition changed, on the grounds that the
    judgment was made about different code -- and if the only way to satisfy
    the guard silently rewrote the hash, the refusal would mean nothing and
    re-argument would never happen.  So a recorded binding survives
    regeneration until someone acknowledges the drift on purpose, the same
    separation `stamp_cards` keeps between tracking source drift and recording
    that a curator has reviewed the current Card projection.
    """
    if not os.path.exists(manifest_path):
        return {}, {}, {}
    with open(manifest_path, encoding="utf-8") as handle:
        parsed = kblib.parse_yaml_subset(handle.read())
    errors = manifest_errors(parsed)
    if errors:
        raise ValueError("invalid module boundary manifest: %s" %
                         "; ".join(errors))
    recorded = {}
    rows = parsed.get("modules") or ()
    classifications = {}
    public_surfaces = {}
    for row in rows:
        module = row.get("module")
        if module:
            classifications[module] = {
                field: row.get(field, "unclassified")
                for field in CLASSIFICATION_FIELDS
            }
            public_surfaces[module] = tuple(row.get("public") or ())
        for entry in row.get("exceptions") or ():
            key = (module, entry.get("consumer"),
                   entry.get("symbol"))
            recorded[key] = {
                field: entry[field] for field in PRESERVED_FIELDS
                if entry.get(field)
            }
    if facts is not None:
        classifications = _resolved_classifications(rows, facts)
    return recorded, classifications, public_surfaces


def _emit_manifest(repo_root, *, acknowledge_drift=False,
                   manifest_path=None):
    """Print a manifest describing what the tree does today, verbatim.

    Every module gets an entry because an undeclared module is a hole in the
    contract, and every existing private consumption gets an exception with a
    content binding because the alternative -- declaring them public -- would
    promise compatibility this distribution never made.
    """
    facts = facts_module.collect(repo_root)
    recorded, classifications, recorded_public = _recorded_manifest(
        manifest_path or os.path.join(repo_root, "Tools",
                                      "module-boundaries.yaml"), facts)
    if acknowledge_drift:
        # Acknowledging drift re-binds the hash and nothing else.  Dropping the
        # whole recorded entry would take the necessity and the retirement
        # condition with it, so the act of saying "this consumption still holds
        # against the new code" would erase the reasons it holds -- and the
        # guard would then demand they be written again from memory.
        recorded = {key: {field: value for field, value in entry.items()
                          if field != "content_sha256"}
                    for key, entry in recorded.items()}
    pairs = facts_module.consumption_pairs(facts)
    private = facts_module.private_pairs(facts)

    consumed_public = {}
    for consumer, target, symbol in pairs:
        if symbol.startswith("_"):
            continue
        consumed_public.setdefault(target, set()).add(symbol)

    exceptions = {}
    for consumer, target, symbol in private:
        kept = recorded.get((target, consumer, symbol)) or {}
        binding = kept.get("content_sha256") or \
            facts_module.def_span_sha256(repo_root, target, symbol)
        entry = {"consumer": consumer, "symbol": symbol,
                 "content_sha256": binding}
        for field in ANNOTATED_FIELDS:
            if kept.get(field):
                entry[field] = kept[field]
        exceptions.setdefault(target, []).append(entry)

    lines = [
        "# Tool module boundary contract -- machine owner:"
        " Tools/module-boundaries.yaml",
        "#",
        "# Generated by Tools/module_boundary_report.py"
        " --emit-manifest.",
        "# Every shipped module carries an entry; a module without one, and an"
        " entry",
        "# without a module, both fail the guard. Current public interfaces",
        "# are explicit reviewed declarations; regeneration unions in newly",
        "# observed internal consumers without retaining a migration-era flag.",
        "# Area, Domain, and Layer are reviewed against tool-taxonomy.yaml; a",
        "# newly discovered module is emitted as unclassified and cannot pass",
        "# the boundary guard until it is placed deliberately.",
        "",
        "schema_version: %d" % MANIFEST_SCHEMA_VERSION,
        "modules:",
    ]
    for name in sorted(facts):
        entry = facts[name]
        classification = classifications.get(name, {})
        lines.append("  - module: %s" % name)
        lines.append("    path: Tools/%s" % entry["path"])
        for field in CLASSIFICATION_FIELDS:
            lines.append("    %s: %s" % (
                field, classification.get(field, "unclassified")))
        public = sorted(
            set(recorded_public.get(name, ())) |
            set(consumed_public.get(name, ()))
        )
        if public:
            lines.append("    public:")
            for symbol in public:
                lines.append("      - %s" % symbol)
        else:
            lines.append("    public: []")
        rows = exceptions.get(name)
        if rows:
            lines.append("    exceptions:")
            for row in sorted(rows,
                              key=lambda r: (r["consumer"], r["symbol"])):
                lines.append("      - consumer: %s" % row["consumer"])
                lines.append("        symbol: %s" % row["symbol"])
                if row["content_sha256"]:
                    lines.append("        content_sha256: %s"
                                 % row["content_sha256"])
                for field in ANNOTATED_FIELDS:
                    if row.get(field):
                        lines.append("        %s: %s" % (field, row[field]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Non-blocking module boundary observations")
    parser.add_argument("--root", default=REPO_ROOT)
    parser.add_argument("--format", choices=("text", "json", "hierarchy"),
                        default="text")
    parser.add_argument("--base-ref", default=None,
                        help="also report the same numbers at this revision")
    parser.add_argument("--emit-manifest", action="store_true",
                        help="print a manifest describing the current tree")
    parser.add_argument("--output", default=None,
                        help="write the manifest here instead of stdout; "
                             "required when regenerating in place, because a "
                             "shell redirect truncates the file before this "
                             "runs and the recorded bindings would be read "
                             "from the emptied file")
    parser.add_argument("--acknowledge-drift", action="store_true",
                        help="re-bind exceptions whose excepted definition "
                             "changed; without this a recorded binding is "
                             "carried forward so the guard keeps refusing")
    args = parser.parse_args(argv)

    root = os.path.realpath(os.path.abspath(args.root))
    if args.emit_manifest:
        rendered = _emit_manifest(
            root, acknowledge_drift=args.acknowledge_drift)
        if args.output:
            # Read-then-write, never redirect: the recorded bindings live in
            # the file being replaced, and `> file` empties it first.
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
            return 0
        sys.stdout.write(rendered)
        return 0

    report = build_report(root)
    base = _baseline(root, args.base_ref)

    if args.format == "hierarchy":
        sys.stdout.write(render_hierarchy(report))
        return 0

    if args.format == "json":
        payload = {"current": report}
        if base is not None:
            payload["base"] = base
        json.dump(payload, sys.stdout, indent=1, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    print("module-boundary observations (advisory; never fails a build)")
    print("  shipped modules      %d" % report["shipped_modules"])
    print("  total lines          %d" % report["total_lines"])
    print("  consumption pairs    %d" % report["consumption_pairs"])
    print("  private pairs        %d" % report["private_consumption_pairs"])
    print("  dependency cycles    %s" % (report["cycles"] or "none"))
    print("  areas               %s" % ", ".join(
        "%s=%d" % item
        for item in report["classification"]["areas"].items()))
    print("  layers              %s" % ", ".join(
        "%s=%d" % item
        for item in report["classification"]["layers"].items()))
    print()
    print("  %-34s %7s %6s %6s %6s" %
          ("module", "lines", "defs", "imprs", "priv"))
    ranked = sorted(report["modules"], key=lambda r: -r["lines"])[:12]
    for row in ranked:
        print("  %-34s %7d %6d %6d %6d" %
              (row["module"][:34], row["lines"], row["top_level_defs"],
               row["importers"], row["private_consumed"]))

    if base is not None:
        print()
        print("  against base: lines %+d, pairs %+d, private %+d, modules %+d"
              % (report["total_lines"] - base["total_lines"],
                 report["consumption_pairs"] - base["consumption_pairs"],
                 report["private_consumption_pairs"]
                 - base["private_consumption_pairs"],
                 report["shipped_modules"] - base["shipped_modules"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
