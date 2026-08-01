#!/usr/bin/env python3
"""Profile manifest completeness check script.

Rule owners:
- "profiles/README.md" (the normative profile interface: which slots exist and
  what constrains each; the Execution Default Overrides Contract);
- "Tools/schemas/execution_defaults.template.yaml" (the machine-readable copy
  of that contract's item lists, and this script's single source of truth for
  the overridable / constitutional split, the reserved profile_id values, the
  unfilled sentinel, and the template scaffolding heading).

What this script is for: a profile copied from `profiles/_template/` is a
skeleton of constraints and TODOs, not a runnable profile. Nothing in prose can
stop an agent from loading a half-filled skeleton and reporting success. This
script is the mechanical stop: it fails while the skeleton is still visible, so
an unfilled profile cannot pass a gate that runs it.

Method:
- Slot list: the H2 headings of the interface file ending in " Slot", with the
  suffix stripped. The Execution Default Overrides Contract is not a file-bound
  slot -- it is a declaration table, checked separately below.
- Manifest: `<profile_dir>/profile.md`. Its `## Implemented Slots` section must
  bind every interface slot, as `- `Slot Name`: <binding>`.
- A binding is resolved in this order: `[[vault/relative/path|alias]]` wiki
  link -> markdown link `[text](path)` -> a binding whose text says the slot is
  declared `inline` (then profile.md must carry an H2 section whose heading
  starts with the slot name) -> a single inline-code span that looks like a
  path. Anything else is unrecognized.
- Execution Default Overrides: profile.md must carry an `## Execution Default
  Overrides` section whose table registers every overridable item with a
  non-empty profile choice. Registering a constitutional constant there is a
  failure -- it is not a value the profile may choose.

Three independent incompleteness blocks, any one of which fails the profile:
1. the unfilled sentinel (default `TODO(profile)`) appearing anywhere under the
   profile directory;
2. a `profile_id` that is missing or still one of the reserved placeholder
   values (the template ships as `_template`);
3. the template scaffolding heading (`## Template Usage`) still present in
   profile.md.
Each block is cleared only by editing the file, so clearing all three is the
mechanical definition of "this profile has been filled in". None of them is
evidence that the answers are *good*; content quality stays a human call.

Result semantics: unbound slots, unresolved bindings, unregistered override
items, and all three incompleteness blocks are result=fail. A manifest binding
for a slot the interface does not define is result=candidate (an extension
binding may be legitimate; whether it is, is a human call).

Scope semantics: a profile directory that does not exist, or that has no
profile.md, is result=fail -- a scan with nothing to check is an invocation
error, never a pass.

Exit codes: 0 = all pass, 1 = at least one fail, 2 = no fail but candidates.

Usage: python3 check_profile.py <profile_dir> [--root VAULT_ROOT]
       [--interface profiles/README.md]
       [--defaults Tools/schemas/execution_defaults.template.yaml]
       [--receipts PATH]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_profile"
TOOL_VERSION = "1.0.0"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_INTERFACE = "profiles/README.md"
DEFAULT_DEFAULTS = "Tools/schemas/execution_defaults.template.yaml"

MANIFEST_NAME = "profile.md"
SLOT_SUFFIX = " Slot"
SLOTS_SECTION = "Implemented Slots"
OVERRIDES_SECTION = "Execution Default Overrides"

# Extensions read as text during the sentinel scan; anything else (images,
# archives) is skipped and reported in the summary counts.
TEXT_SUFFIXES = (".md", ".yaml", ".yml", ".txt", ".json", ".jsonl", ".py", ".csv")

BINDING_RE = re.compile(r"^\s*-\s+`([^`]+)`\s*:\s*(.+?)\s*$")
WIKI_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")
PROFILE_ID_RE = re.compile(r"^\s*-\s+`profile_id`\s*:\s*`([^`]*)`")
INLINE_WORD_RE = re.compile(r"\binline\b", re.IGNORECASE)


def blank_fenced(text):
    """Blank out fenced code blocks, keeping inline code and the line count.

    kblib.strip_code also removes inline code, which this script must keep:
    slot names and bindings live inside backticks.
    """
    out = []
    fence = None
    for line in text.splitlines():
        stripped = line.lstrip()
        m = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and m:
            fence = m.group(1)[0] * 3
            out.append("")
            continue
        if fence is not None:
            if m and stripped.startswith(fence):
                fence = None
            out.append("")
            continue
        out.append(line)
    return "\n".join(out)


def h2_headings(text):
    """Return the H2 heading texts of a fence-blanked document, in order."""
    return [h for _, level, h in kblib.headings_of(blank_fenced(text)) if level == 2]


def section_lines(text, heading):
    """Return the lines of the H2 section with this exact heading (or [])."""
    lines = blank_fenced(text).splitlines()
    out = []
    inside = False
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            if inside and len(m.group(1)) <= 2:
                break
            inside = (len(m.group(1)) == 2 and m.group(2).strip() == heading)
            continue
        if inside:
            out.append(line)
    return out


def read_text(path):
    return open(path, encoding="utf-8", errors="replace").read()


def interface_slots(text):
    """Slot names = H2 headings ending in ' Slot', suffix stripped."""
    return [h[: -len(SLOT_SUFFIX)].strip()
            for h in h2_headings(text) if h.endswith(SLOT_SUFFIX)]


def parse_bindings(manifest_text):
    """Return {slot name: binding text} from the Implemented Slots section."""
    bindings = {}
    for line in section_lines(manifest_text, SLOTS_SECTION):
        m = BINDING_RE.match(line)
        if m:
            bindings[m.group(1).strip()] = m.group(2).strip()
    return bindings


def looks_like_path(value):
    return "/" in value or value.lower().endswith((".md", ".yaml", ".yml"))


def candidate_paths(target, root, profile_dir):
    """Candidate on-disk locations for a binding target, in resolution order."""
    target = target.strip().lstrip("./")
    if not target:
        return []
    variants = [target]
    if not target.lower().endswith((".md", ".yaml", ".yml")):
        variants.append(target + ".md")
    out = []
    for variant in variants:
        out.append(os.path.join(profile_dir, variant))
        out.append(os.path.join(root, variant))
    return out


def resolve_binding(binding, root, profile_dir):
    """Classify and resolve one binding.

    Returns (kind, detail): kind is "path" (detail = resolved absolute path),
    "unresolved" (detail = the target that resolved to nothing), "inline"
    (detail = None), or "unrecognized" (detail = None).
    """
    target = None
    m = WIKI_RE.search(binding)
    if m:
        target = re.split(r"\\\||\|", m.group(1), maxsplit=1)[0].strip()
    if target is None:
        m = MDLINK_RE.search(binding)
        if m:
            target = m.group(1).strip()
    if target is None and INLINE_WORD_RE.search(binding):
        return "inline", None
    if target is None:
        for code in CODE_RE.findall(binding):
            if looks_like_path(code):
                target = code.strip()
                break
    if target is None:
        return "unrecognized", None
    for path in candidate_paths(target, root, profile_dir):
        if os.path.isfile(path):
            return "path", path
    return "unresolved", target


def table_rows(lines):
    """Yield the cell lists of Markdown table rows, skipping separator rows."""
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        yield cells


def unbacktick(value):
    value = value.strip()
    m = re.fullmatch(r"`([^`]*)`", value)
    return m.group(1).strip() if m else value


def scan_sentinel(profile_dir, sentinel):
    """Return ([(relpath, lineno)], files_read, files_skipped)."""
    hits, read_n, skipped_n = [], 0, 0
    for dirpath, dirnames, filenames in os.walk(profile_dir):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            if not name.lower().endswith(TEXT_SUFFIXES):
                skipped_n += 1
                continue
            read_n += 1
            rel = os.path.relpath(full, profile_dir).replace(os.sep, "/")
            for lineno, line in enumerate(read_text(full).splitlines(), 1):
                if sentinel in line:
                    hits.append((rel, lineno))
    return hits, read_n, skipped_n


def main():
    ap = argparse.ArgumentParser(
        description="Profile manifest completeness and unfilled-template check")
    ap.add_argument("profile_dir", help="the profile directory to check "
                                        "(e.g. profiles/examples/eng-handbook)")
    ap.add_argument("--root", default=REPO_ROOT,
                    help="vault root that vault-relative bindings resolve "
                         "against (default: this script's repository root)")
    ap.add_argument("--interface", default=None,
                    help="normative slot interface file "
                         "(default: %s under --root)" % DEFAULT_INTERFACE)
    ap.add_argument("--defaults", default=None,
                    help="machine-readable execution default registry "
                         "(default: %s under --root)" % DEFAULT_DEFAULTS)
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    profile_dir = os.path.abspath(args.profile_dir)
    profile_disp = os.path.relpath(profile_dir, root).replace(os.sep, "/")
    interface_path = args.interface or os.path.join(root, DEFAULT_INTERFACE)
    defaults_path = args.defaults or os.path.join(root, DEFAULT_DEFAULTS)

    receipts = []
    seq = 0

    def add(check, target, result, details):
        nonlocal seq
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, check, target, result, details, seq))

    # ---- inputs must be readable before anything can be judged ----
    if not os.path.isdir(profile_dir):
        add("profile-dir-missing", profile_disp, "fail",
            "profile directory does not exist; a scan with nothing to check "
            "is an invocation error, never a pass")
        print("check_profile: FAIL — no such profile directory: %s" % args.profile_dir)
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)

    manifest_path = os.path.join(profile_dir, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        add("manifest-missing", "%s/%s" % (profile_disp, MANIFEST_NAME), "fail",
            "the profile manifest %s is missing; every slot binding is "
            "declared there, so nothing about this profile can be verified"
            % MANIFEST_NAME)
        print("check_profile: FAIL — %s has no %s" % (profile_disp, MANIFEST_NAME))
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)

    try:
        interface_text = read_text(interface_path)
    except OSError as exc:
        add("interface-unreadable", DEFAULT_INTERFACE, "fail",
            "cannot read the normative slot interface: %s" % exc)
        print("check_profile: FAIL — cannot read interface %s: %s" % (interface_path, exc))
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)

    try:
        defaults = kblib.parse_yaml_subset(read_text(defaults_path))
    except (OSError, kblib.YamlSubsetError) as exc:
        add("defaults-unreadable", DEFAULT_DEFAULTS, "fail",
            "cannot read/parse the execution default registry: %s" % exc)
        print("check_profile: FAIL — cannot read defaults %s: %s" % (defaults_path, exc))
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)

    sentinel = str(defaults.get("unfilled_sentinel") or "TODO(profile)")
    scaffolding = str(defaults.get("template_scaffolding_heading") or "Template Usage")
    reserved_ids = {str(v) for v in (defaults.get("reserved_profile_ids") or [])}
    overridable = [str(e.get("item")) for e in (defaults.get("overridable") or [])
                   if isinstance(e, dict) and e.get("item")]
    constitutional = {str(e.get("item")): e for e in (defaults.get("constitutional") or [])
                      if isinstance(e, dict) and e.get("item")}

    manifest_text = read_text(manifest_path)
    manifest_disp = "%s/%s" % (profile_disp, MANIFEST_NAME)

    slots = interface_slots(interface_text)
    if not slots:
        add("interface-no-slots", DEFAULT_INTERFACE, "fail",
            "the interface file declares no '<name>%s' H2 heading; with no "
            "slot list there is nothing to check against" % SLOT_SUFFIX)

    # ---- block 1: unfilled sentinel anywhere under the profile directory ----
    hits, files_read, files_skipped = scan_sentinel(profile_dir, sentinel)
    for rel, lineno in hits:
        add("unfilled-placeholder", "%s/%s:%d" % (profile_disp, rel, lineno), "fail",
            "line still carries the unfilled sentinel %r; a profile with any "
            "TODO left is a template skeleton, not a runnable profile"
            % sentinel)

    # ---- block 2: placeholder profile_id ----
    profile_id = None
    for line in section_lines(manifest_text, "Profile Identity"):
        m = PROFILE_ID_RE.match(line)
        if m:
            profile_id = m.group(1).strip()
            break
    if profile_id is None:
        add("profile-id-missing", "%s#Profile Identity" % manifest_disp, "fail",
            "no `profile_id`: `<value>` bullet found under Profile Identity; "
            "the manifest must name the profile it composes with the kernel")
    elif profile_id in reserved_ids:
        add("profile-id-placeholder", "%s#profile_id" % manifest_disp, "fail",
            "profile_id is still the reserved placeholder %r; replace it with "
            "this profile's own id before the profile may be loaded"
            % profile_id)

    # ---- block 3: template scaffolding still present ----
    if scaffolding in h2_headings(manifest_text):
        add("template-scaffolding-present", "%s#%s" % (manifest_disp, scaffolding),
            "fail",
            "the manifest still carries the template's '%s' section; it exists "
            "only to instruct someone filling the template in and must be "
            "deleted once the profile is filled" % scaffolding)

    # ---- slot coverage and binding resolution ----
    bindings = parse_bindings(manifest_text)
    if slots and not bindings:
        add("slots-section-empty", "%s#%s" % (manifest_disp, SLOTS_SECTION), "fail",
            "the %s section binds no slots; the composed standard cannot be "
            "judged loaded when no slot resolves" % SLOTS_SECTION)

    bound_ok = 0
    for slot in slots:
        binding = bindings.get(slot)
        if binding is None:
            add("slot-unbound", "%s#%s" % (manifest_disp, slot), "fail",
                "interface slot `%s` is not bound in %s; when a slot required "
                "by the current task is missing, the composed standard must "
                "not be judged fully loaded" % (slot, SLOTS_SECTION))
            continue
        kind, detail = resolve_binding(binding, root, profile_dir)
        if kind == "path":
            bound_ok += 1
        elif kind == "inline":
            if any(h == slot or h.startswith(slot + " ")
                   for h in h2_headings(manifest_text)):
                bound_ok += 1
            else:
                add("slot-inline-unbacked", "%s#%s" % (manifest_disp, slot), "fail",
                    "slot `%s` is declared inline, but the manifest has no H2 "
                    "section starting with that slot name to carry the "
                    "declaration" % slot)
        elif kind == "unresolved":
            add("slot-binding-unresolved", "%s#%s" % (manifest_disp, slot), "fail",
                "slot `%s` binds to %r, which does not exist under the profile "
                "directory or the vault root" % (slot, detail))
        else:
            add("slot-binding-unrecognized", "%s#%s" % (manifest_disp, slot), "fail",
                "slot `%s` binding %r is neither a resolvable path nor an "
                "inline declaration" % (slot, binding))

    for name in sorted(bindings):
        if name not in slots:
            add("slot-not-in-interface", "%s#%s" % (manifest_disp, name), "candidate",
                "`%s` is bound in %s but is not a slot the interface defines; "
                "whether this extension binding is reasonable is a human call"
                % (name, SLOTS_SECTION))

    # ---- Execution Default Overrides declaration table ----
    override_lines = section_lines(manifest_text, OVERRIDES_SECTION)
    registered = {}
    for cells in table_rows(override_lines):
        if not cells:
            continue
        registered[unbacktick(cells[0])] = unbacktick(cells[1]) if len(cells) > 1 else ""
    if not override_lines:
        add("overrides-section-missing", "%s#%s" % (manifest_disp, OVERRIDES_SECTION),
            "fail",
            "the manifest has no %s section; the contract requires the profile "
            "to declare, item by item, whether it adopts the kernel default or "
            "overrides it" % OVERRIDES_SECTION)
    else:
        for item in overridable:
            if item not in registered:
                add("override-item-unregistered",
                    "%s#%s" % (manifest_disp, item), "fail",
                    "overridable item `%s` is not registered in %s; the "
                    "contract requires an item-by-item declaration"
                    % (item, OVERRIDES_SECTION))
            elif not registered[item]:
                add("override-choice-empty", "%s#%s" % (manifest_disp, item), "fail",
                    "overridable item `%s` is registered with an empty profile "
                    "choice; declare `use-kernel-default` or an explicit "
                    "override value" % item)
        for item in sorted(set(registered) & set(constitutional)):
            add("override-constitutional-item",
                "%s#%s" % (manifest_disp, item), "fail",
                "`%s` is a constitutional constant (owner: %s) and is not "
                "overridable; it must not appear in %s"
                % (item, constitutional[item].get("owner", "kernel"),
                   OVERRIDES_SECTION))

    fails = [r for r in receipts if r["result"] == "fail"]
    if not fails:
        add("profile-check-summary", profile_disp, "pass",
            "profile_id=%s; %d/%d interface slot(s) bound and resolved; %d "
            "overridable item(s) registered; no unfilled sentinel, placeholder "
            "id, or template scaffolding remains"
            % (profile_id, bound_ok, len(slots), len(overridable)))

    # ---- human-readable summary ----
    print("check_profile: %s (profile_id=%s)"
          % (profile_disp, profile_id if profile_id else "<none>"))
    print("  interface=%s slots=%d bound_ok=%d overridable_items=%d "
          "files_scanned=%d files_skipped=%d"
          % (os.path.relpath(interface_path, root).replace(os.sep, "/"),
             len(slots), bound_ok, len(overridable), files_read, files_skipped))
    print("  sentinel_hits(fail)=%d" % len(hits))
    for r in receipts:
        if r["result"] == "fail":
            print("  [FAIL %s] %s — %s" % (r["check"], r["target"], r["details"]))
        elif r["result"] == "candidate":
            print("  [CAND %s] %s — %s" % (r["check"], r["target"], r["details"]))
    if fails:
        print("  Conclusion: NOT LOADABLE — %d failure(s). This profile is "
              "incomplete; the composed standard must not be judged fully "
              "loaded." % len(fails))
    else:
        print("  Conclusion: profile manifest complete; every interface slot "
              "resolves and no unfilled-template marker remains. This checks "
              "structure, not whether the answers are good.")

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
