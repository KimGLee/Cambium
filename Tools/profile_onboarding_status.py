#!/usr/bin/env python3
"""Read-only onboarding status projector for one adopting root.

What this tool is for: between "a directory that merely contains Cambium"
and "a governed corpus doing routine work" lie several distinct states --
no candidate profile yet, a scaffolded candidate whose interview is open, a
passing candidate awaiting R09 adoption, an adopted standard over an empty
or an existing corpus, an interrupted task runtime.  Each state already has
one canonical owner (scaffold_profile, the interview, check_profile, R09,
init_state, check_queue --resume-status); what was missing is one place
that *derives* which state the root is in and names the single next step.

This tool is strictly a projection:

* it never writes, never creates receipts, never mutates state, and keeps
  no second authoritative ledger -- every reported value is derived from
  bytes owned elsewhere (adopter Standards state, profiles/, the corpus tree,
  `.cambium/`);
* it evaluates a targeted candidate through ``check_profile``'s in-process
  ``evaluate_profile_load`` (which itself writes nothing) and classifies its
  findings through ``check_profile.FINDING_CATEGORIES``, so an assisting
  agent can tell mechanical breakage from open interview answers;
* it emits exactly one machine-readable ``next_action`` token, in the same
  spirit as ``check_queue.py --resume-status``.

``next_action`` precedence (first match wins):

1. root lacks kernel/ + profiles/ + Tools/     -> ``not-a-cambium-root``
2. `.cambium/state/` present                   -> ``resume-existing-task``
   (existing-task recovery always wins; scaffolding or adoption must not
   proceed over runtime state)
3. Standards state malformed or unreadable     -> ``repair-control-state``
4. pre-adoption, no candidate, a missing targeted candidate, or several
   candidates without ``--profile-id``         -> ``confirm-profile-identity``
5. pre-adoption, targeted candidate fails
   ``profile-load``                            -> ``complete-profile-interview``
6. pre-adoption, targeted candidate passes     -> ``authorize-r09``
7. adopted, corpus empty                       -> ``found-empty-corpus``
8. adopted, corpus existing, Corpus Planning
   ``configured`` (no runtime, per rule 2)     -> ``prepare-task-plan``
9. adopted, corpus existing, Corpus Planning
   ``not-applicable``                          -> ``onboarding-complete``
   (bounded content routes are available now; large-scale work first
   configures Corpus Planning through a later R09 revision)
An adopted root whose selected Corpus Planning slot is unreadable falls
back to ``repair-control-state``.

Exit codes: 0 = the status view was derived (whatever it says);
1 = invocation error (the root does not exist).

Usage: python3 Tools/profile_onboarding_status.py <root>
       [--profile-id <id>] [--json]
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_profile
import kblib
import standards_state

TOOL = "profile_onboarding_status"
TOOL_VERSION = "1.1.0"

ACTIVE_STATE_RELATIVE = standards_state.STATE_PATH
DEFAULTS_RELATIVE = "Tools/schemas/execution_defaults.template.yaml"
CORPUS_PLANNING_SLOT = "Corpus Planning"
MANIFEST_NAME = "profile.md"

# Trees and root-level files that are distribution/control plane, never
# corpus pages.  Dot-directories (.git, .cambium, .obsidian, ...) are
# excluded wherever they occur.
NON_CORPUS_TREES = frozenset(("kernel", "profiles", "Tools", "LICENSES",
                              "docs"))
NON_CORPUS_ROOT_FILES = frozenset(("ROADMAP.md", "ATTRIBUTION.md",
                                   "LICENSE.md", "NOTICE"))
NON_CORPUS_ROOT_PREFIX = "README"

# Candidate enumeration never treats these profiles/ members as candidates.
NON_CANDIDATE_DIRECTORIES = frozenset(("_template", "examples"))


def read_text(path):
    with open(path, encoding="utf-8", errors="strict") as handle:
        return handle.read()


def unfilled_sentinel(root):
    """The registered unfilled sentinel, defaulting like check_profile."""
    try:
        defaults = kblib.parse_yaml_subset(
            read_text(os.path.join(root, *DEFAULTS_RELATIVE.split("/"))))
        return str(defaults.get("unfilled_sentinel") or "TODO(profile)")
    except (OSError, UnicodeError, kblib.YamlSubsetError):
        return "TODO(profile)"


def standards_view(root):
    """Project the canonical adopter state into one onboarding token.

    Returns ``(state, values, uninstantiated, problems)`` where ``state`` is
    ``pre-adoption`` (state absent), ``adopted`` (valid state), or
    ``inconsistent`` (unsafe, unreadable, or malformed state).
    """
    path = os.path.join(root, *ACTIVE_STATE_RELATIVE.split("/"))
    fields = ["effective_date", "selected_profile_manifest", "status",
              "standards_version"]
    if not os.path.lexists(path):
        return "pre-adoption", None, fields, []
    try:
        text = read_text(path)
    except (OSError, UnicodeError) as exc:
        return ("inconsistent", None, fields, [
            "cannot read %s: %s" % (ACTIVE_STATE_RELATIVE, exc)])
    try:
        state, parse_errors = standards_state.parse(text)
    except (TypeError, ValueError, kblib.YamlSubsetError) as exc:
        return "inconsistent", None, fields, [
            "%s: %s" % (ACTIVE_STATE_RELATIVE, exc)]
    problems = ["%s: %s" % (ACTIVE_STATE_RELATIVE, error)
                for error in parse_errors]
    if problems:
        return "inconsistent", None, [], problems
    return ("adopted", {field: state[field] for field in fields}, [], [])


def corpus_planning_state(root, profile_dir):
    """``applicability.state`` of one profile's Corpus Planning slot.

    Returns ``configured``, ``not-applicable``, or ``unreadable``.  This is
    a projection only; slot validation stays with ``check_profile``.
    """
    try:
        manifest_text = read_text(os.path.join(profile_dir, MANIFEST_NAME))
        binding = kblib.profile_slot_bindings(manifest_text).get(
            CORPUS_PLANNING_SLOT)
        if binding is None:
            return "unreadable"
        kind, detail = kblib.resolve_profile_binding(
            binding, root, profile_dir)
        if kind != "path":
            return "unreadable"
        document = kblib.parse_yaml_subset(read_text(detail))
        applicability = document.get("applicability")
        state = (applicability.get("state")
                 if isinstance(applicability, dict) else None)
    except (OSError, UnicodeError, kblib.YamlSubsetError):
        return "unreadable"
    if state in ("configured", "not-applicable"):
        return state
    return "unreadable"


def sentinel_count(directory, sentinel):
    """Total sentinel occurrences across every regular file in the tree."""
    needle = sentinel.encode("utf-8")
    total = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            try:
                with open(path, "rb") as handle:
                    total += handle.read().count(needle)
            except OSError:
                continue
    return total


def candidate_directories(root):
    """Profile directories under profiles/, excluding template and examples."""
    profiles_dir = os.path.join(root, "profiles")
    names = []
    try:
        entries = sorted(os.listdir(profiles_dir))
    except OSError:
        return names
    for name in entries:
        if name in NON_CANDIDATE_DIRECTORIES or name.startswith("."):
            continue
        if os.path.isdir(os.path.join(profiles_dir, name)):
            names.append(name)
    return names


def candidate_profile_id(root, name):
    """The manifest's declared profile_id, or None when unreadable."""
    manifest = os.path.join(root, "profiles", name, MANIFEST_NAME)
    try:
        manifest_text = read_text(manifest)
    except (OSError, UnicodeError):
        return None
    profile_id, _errors = kblib.profile_identity(manifest_text, name)
    return profile_id


def evaluate_candidate(root, name):
    """One in-process ``profile-load`` evaluation with categorized counts."""
    profile_dir = os.path.join(root, "profiles", name)
    try:
        evaluation = check_profile.evaluate_profile_load(
            profile_dir, root=root, receipt_identity=None)
    except (OSError, UnicodeError, ValueError) as exc:
        return {
            "result": "error",
            "error": str(exc),
            "mechanical": 0,
            "semantic_unresolved": 0,
        }
    counts = {check_profile.MECHANICAL: 0,
              check_profile.SEMANTIC_UNRESOLVED: 0}
    for finding in evaluation.findings:
        category = check_profile.finding_category(finding.get("check"))
        counts[category] = counts.get(category, 0) + 1
    return {
        "result": {0: "pass", 1: "fail", 2: "candidate"}.get(
            evaluation.exit_code, "fail"),
        "mechanical": counts[check_profile.MECHANICAL],
        "semantic_unresolved": counts[check_profile.SEMANTIC_UNRESOLVED],
    }


def corpus_page_count(root):
    """Count corpus Markdown pages outside the distribution/control trees."""
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        relative = os.path.relpath(dirpath, root)
        at_root = relative == "."
        dirnames[:] = sorted(
            name for name in dirnames
            if not name.startswith(".")
            and not (at_root and name in NON_CORPUS_TREES))
        for name in sorted(filenames):
            if not name.lower().endswith(".md"):
                continue
            if at_root and (name.startswith(NON_CORPUS_ROOT_PREFIX)
                            or name in NON_CORPUS_ROOT_FILES):
                continue
            count += 1
    return count


def runtime_view(root):
    cambium = os.path.join(root, ".cambium")
    state_dir = os.path.join(cambium, "state")
    present = os.path.isdir(state_dir)
    state_has_content = False
    if present:
        try:
            state_has_content = bool(os.listdir(state_dir))
        except OSError:
            state_has_content = False
    return {"present": present, "state_has_content": state_has_content}


def derive_status(root, targeted_id):
    """Derive the complete deterministic status view for one root."""
    adopting_root = all(
        os.path.isdir(os.path.join(root, name))
        for name in ("kernel", "profiles", "Tools"))
    view = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "root": root,
        "adopting_root": adopting_root,
        "standards_state": None,
        "standards_values": None,
        "standards_uninstantiated": [],
        "selected_profile": None,
        "corpus_planning_state": None,
        "candidates": [],
        "corpus_state": None,
        "corpus_page_count": None,
        "cambium_runtime": runtime_view(root),
        "next_action": None,
        "notes": [],
    }
    notes = view["notes"]

    if not adopting_root:
        view["next_action"] = "not-a-cambium-root"
        notes.append(
            "%s does not look like a Cambium adopting root: kernel/, "
            "profiles/, and Tools/ must all be present; nothing further "
            "can be derived here" % root)
        return view

    state, values, uninstantiated, problems = standards_view(root)
    view["standards_state"] = state
    view["standards_values"] = values
    view["standards_uninstantiated"] = uninstantiated

    sentinel = unfilled_sentinel(root)
    names = candidate_directories(root)
    targeted = None
    if targeted_id is not None:
        targeted = targeted_id if targeted_id in names else None
    elif len(names) == 1:
        targeted = names[0]
    for name in names:
        entry = {
            "directory": "profiles/%s" % name,
            "profile_id": candidate_profile_id(root, name),
            "sentinel_count": sentinel_count(
                os.path.join(root, "profiles", name), sentinel),
            "targeted": name == targeted,
            "profile_load": None,
        }
        if name == targeted:
            entry["profile_load"] = evaluate_candidate(root, name)
        view["candidates"].append(entry)

    if state == "adopted":
        view["selected_profile"] = values["selected_profile_manifest"]
        selected_dir = os.path.join(
            root, os.path.dirname(view["selected_profile"]))
        view["corpus_planning_state"] = corpus_planning_state(
            root, selected_dir)
    elif targeted is not None:
        view["corpus_planning_state"] = corpus_planning_state(
            root, os.path.join(root, "profiles", targeted))

    pages = corpus_page_count(root)
    view["corpus_page_count"] = pages
    view["corpus_state"] = "empty" if pages == 0 else "existing"

    # ---- exactly one next_action, by fixed precedence ----
    if view["cambium_runtime"]["present"]:
        view["next_action"] = "resume-existing-task"
        notes.append(
            ".cambium/ runtime state exists (state/ %s); existing-task "
            "recovery always wins -- run `python3 Tools/check_queue.py . "
            "--resume-status` and follow its next_action; scaffolding or "
            "adoption must not proceed over an existing runtime"
            % ("has content" if view["cambium_runtime"]["state_has_content"]
               else "is empty"))
        return view

    if state == "inconsistent":
        view["next_action"] = "repair-control-state"
        for problem in problems:
            notes.append(problem)
        if not problems:
            notes.append(
                "the canonical adopter Standards state is not coherent; "
                "repair it before anything else")
        return view

    if state == "pre-adoption":
        if targeted is None:
            view["next_action"] = "confirm-profile-identity"
            if targeted_id is not None:
                notes.append(
                    "--profile-id %r does not name a candidate directory "
                    "under profiles/; found: %s"
                    % (targeted_id,
                       ", ".join(names) if names else "none"))
            elif not names:
                notes.append(
                    "no candidate profile directory exists under profiles/ "
                    "(excluding _template and examples); confirm the "
                    "profile identity with the operator, then scaffold it "
                    "with `python3 Tools/scaffold_profile.py . --profile-id "
                    "<id> --apply`")
            else:
                notes.append(
                    "multiple candidate profiles exist: %s; exactly one "
                    "must be targeted -- rerun with --profile-id <id>"
                    % ", ".join(names))
            return view
        entry = next(item for item in view["candidates"]
                     if item["targeted"])
        load = entry["profile_load"]
        if load["result"] == "pass":
            view["next_action"] = "authorize-r09"
            notes.append(
                "candidate profiles/%s passes profile-load; selection and "
                "adoption remain an R09 governance decision: create the "
                "canonical adopter Standards state for %s/profile.md, then run "
                "the write-back checklist" % (targeted, entry["directory"]))
        else:
            view["next_action"] = "complete-profile-interview"
            notes.append(
                "candidate %s does not pass profile-load: %d "
                "semantic-unresolved finding(s) (operator answers missing "
                "or unconfirmed; %d unfilled sentinel occurrence(s)) and "
                "%d mechanical finding(s); complete the interview "
                "(profiles/interview.yaml), then rerun `python3 "
                "Tools/check_profile.py %s --root . --json`"
                % (entry["directory"], load["semantic_unresolved"],
                   entry["sentinel_count"], load["mechanical"],
                   entry["directory"]))
        return view

    # state == "adopted"
    if view["corpus_state"] == "empty":
        view["next_action"] = "found-empty-corpus"
        notes.append(
            "the standard is adopted and the corpus holds no page yet; "
            "bounded founding = one canonical owner page per Profile Scope "
            "layer plus the residual witness, then a second R09 revision "
            "configures Corpus Planning before large-scale construction")
        return view
    if view["corpus_planning_state"] == "configured":
        view["next_action"] = "prepare-task-plan"
        notes.append(
            "the standard is adopted over an existing corpus (%d page(s)) "
            "and Corpus Planning is configured, but no task runtime "
            "exists; initialize one with init_state.py and fill it through "
            "apply_task_plan.py" % pages)
        return view
    if view["corpus_planning_state"] == "not-applicable":
        view["next_action"] = "onboarding-complete"
        notes.append(
            "the standard is adopted over an existing corpus (%d page(s)); "
            "bounded content routes are available now; large-scale work "
            "first configures Corpus Planning through a later R09 revision"
            % pages)
        return view
    view["next_action"] = "repair-control-state"
    notes.append(
        "the selected profile's Corpus Planning slot is unreadable; the "
        "selected Profile must pass profile-load before onboarding state "
        "can be derived -- run `python3 Tools/check_profile.py %s --root . "
        "--json`" % os.path.dirname(view["selected_profile"]))
    return view


def print_human(view):
    print("profile_onboarding_status: %s" % view["root"])
    print("  adopting_root=%s" % str(view["adopting_root"]).lower())
    print("  standards_state=%s" % view["standards_state"])
    if view["standards_values"]:
        for field in sorted(view["standards_values"]):
            print("    %s=%s" % (field, view["standards_values"][field]))
    if view["standards_uninstantiated"] and \
            view["standards_state"] == "inconsistent":
        print("    uninstantiated=%s"
              % ",".join(view["standards_uninstantiated"]))
    print("  selected_profile=%s" % view["selected_profile"])
    print("  corpus_planning_state=%s" % view["corpus_planning_state"])
    print("  candidates=%d" % len(view["candidates"]))
    for entry in view["candidates"]:
        line = ("    - %s profile_id=%s sentinel_count=%d"
                % (entry["directory"], entry["profile_id"],
                   entry["sentinel_count"]))
        load = entry["profile_load"]
        if load is not None:
            line += (" profile_load=%s mechanical=%d semantic_unresolved=%d"
                     % (load["result"], load["mechanical"],
                        load["semantic_unresolved"]))
        if entry["targeted"]:
            line += " (targeted)"
        print(line)
    print("  corpus_state=%s corpus_page_count=%s"
          % (view["corpus_state"], view["corpus_page_count"]))
    runtime = view["cambium_runtime"]
    if runtime["present"]:
        print("  cambium_runtime=present state_has_content=%s"
              % str(runtime["state_has_content"]).lower())
    else:
        print("  cambium_runtime=.cambium/ absent")
    print("  next_action=%s" % view["next_action"])
    for note in view["notes"]:
        print("  note: %s" % note)


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Read-only onboarding status projector: derives the "
                    "adoption/onboarding state of one root and exactly one "
                    "next_action token; writes nothing and owns no ledger")
    parser.add_argument("root", help="the adopting repository root to project")
    parser.add_argument("--profile-id",
                        help="target one candidate profile directory name "
                             "under profiles/ for the full profile-load "
                             "evaluation (defaults to the single candidate "
                             "when exactly one exists)")
    parser.add_argument("--json", action="store_true",
                        help="emit the status view as one deterministic "
                             "JSON object instead of the human summary")
    args = parser.parse_args(argv)

    root = os.path.realpath(os.path.abspath(args.root))
    if not os.path.isdir(root):
        if args.json:
            print(json.dumps({
                "tool": TOOL,
                "tool_version": TOOL_VERSION,
                "root": args.root,
                "error": "root is not an existing directory",
            }, ensure_ascii=False, sort_keys=True, indent=2))
        else:
            print("[FAIL] root is not an existing directory: %s" % args.root)
        return 1

    view = derive_status(root, args.profile_id)
    if args.json:
        print(json.dumps(view, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print_human(view)
    return 0


if __name__ == "__main__":
    sys.exit(main())
