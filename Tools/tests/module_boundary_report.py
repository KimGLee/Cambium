#!/usr/bin/env python3
"""Report what the boundary contract can see but never fails on.

The contract in `K00/18` guards the public surface, and a public surface
cannot see everything that went wrong in this tree.  A module can absorb a
new mode, grow a thousand-line function, or take on a second responsibility
without adding one public symbol, and the guard will stay green through all
of it -- correctly, because none of that broke a compatibility boundary.

So this prints the signals instead of judging them.  Line counts, top-level
definitions, importer counts and dependency components are observations that
a reviewer weighs; the moment one of them became an exit code it would be a
byte cap wearing a different name, and the register this contract deliberately
did not copy already showed what byte caps cost.  The exit code here is 0 for
a readable tree and non-zero only when the tree cannot be parsed at all.

Also emits the manifest itself (`--emit-manifest`), because a v1 register of
what a tree already does must be derivable from the tree rather than typed by
hand -- a hand-typed inventory is stale the day after it is written, and this
one exists precisely to stop silent drift.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import module_boundary_facts as facts_module  # noqa: E402


REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_report(repo_root):
    facts = facts_module.collect(repo_root)
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
        modules.append({
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
        })

    return {
        "shipped_modules": len(facts),
        "total_lines": sum(row["lines"] for row in modules),
        "consumption_pairs": len(pairs),
        "private_consumption_pairs": len(private),
        "cycles": facts_module.strongly_connected(graph),
        "modules": modules,
    }


def _baseline(repo_root, base_ref):
    """Report the same numbers for a base revision, when one is named."""
    if not base_ref:
        return None
    try:
        out = subprocess.run(
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
        add = subprocess.run(
            ["git", "-C", repo_root, "worktree", "add", "--detach",
             scratch, base_ref],
            capture_output=True, text=True, timeout=120)
        if add.returncode != 0:
            return None
        try:
            return build_report(scratch)
        finally:
            subprocess.run(
                ["git", "-C", repo_root, "worktree", "remove", "--force",
                 scratch], capture_output=True, text=True, timeout=60)


def _emit_manifest(repo_root):
    """Print a manifest describing what the tree does today, verbatim.

    Every module gets an entry because an undeclared module is a hole in the
    contract, and every existing private consumption gets an exception with a
    content binding because the alternative -- declaring them public -- would
    promise compatibility this distribution never made.
    """
    facts = facts_module.collect(repo_root)
    pairs = facts_module.consumption_pairs(facts)
    private = facts_module.private_pairs(facts)

    consumed_public = {}
    for consumer, target, symbol in pairs:
        if symbol.startswith("_"):
            continue
        consumed_public.setdefault(target, set()).add(symbol)

    exceptions = {}
    for consumer, target, symbol in private:
        binding = facts_module.def_span_sha256(repo_root, target, symbol)
        exceptions.setdefault(target, []).append({
            "consumer": consumer,
            "symbol": symbol,
            "content_sha256": binding,
        })

    lines = [
        "# Tool module boundary contract -- owner"
        " kernel/K00 Standards Control/18 Tool Module Boundary Contract.md",
        "#",
        "# Generated by Tools/tests/module_boundary_report.py"
        " --emit-manifest.",
        "# Every shipped module carries an entry; a module without one, and an"
        " entry",
        "# without a module, both fail the guard.  `provisional: true` marks a"
        " public",
        "# surface inherited from before the contract existed: it is guarded"
        " against",
        "# widening, and shrinking it is not a compatibility break.",
        "",
        "schema_version: 1",
        "modules:",
    ]
    for name in sorted(facts):
        entry = facts[name]
        lines.append("  - module: %s" % name)
        lines.append("    path: Tools/%s" % entry["path"])
        public = sorted(consumed_public.get(name, ()))
        if public:
            lines.append("    provisional: true")
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
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Non-blocking module boundary observations")
    parser.add_argument("--root", default=REPO_ROOT)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--base-ref", default=None,
                        help="also report the same numbers at this revision")
    parser.add_argument("--emit-manifest", action="store_true",
                        help="print a manifest describing the current tree")
    args = parser.parse_args(argv)

    root = os.path.realpath(os.path.abspath(args.root))
    if args.emit_manifest:
        sys.stdout.write(_emit_manifest(root))
        return 0

    report = build_report(root)
    base = _baseline(root, args.base_ref)

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
