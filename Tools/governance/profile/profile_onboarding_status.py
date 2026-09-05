#!/usr/bin/env python3
"""Read-only onboarding projection from candidate and adopter-owned state.

Incomplete candidates are read through the Profile draft API. A draft may be
ready, incomplete, or invalid; none of those states admits a runtime consumer,
emits profile-load evidence, confirms an answer, or selects a Profile. The
formal profile-load evaluator and the existing R09 transaction retain those
separate responsibilities. Existing task recovery always takes precedence.
"""

from collections.abc import Mapping
import json
import os
import sys

import Tools.execution.context_delivery.card_contract as card_contract
import Tools.governance.profile.check_profile as check_profile
import Tools.execution.planning.corpus_planning_contract as corpus_planning_contract
import Tools.platform.common.kblib as kblib
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.governance.profile.profile_contract as profile_contract
import Tools.execution.context_delivery.read_set_contract as read_set_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.governance.standards.adoption_lineage_contract as adoption_lineage_contract
import Tools.governance.standards.standards_state as standards_state

TOOL = "profile_onboarding_status"
TOOL_VERSION = "1.2.0"

ACTIVE_STATE_RELATIVE = standards_state.STATE_PATH
CORPUS_PLANNING_SLOT = corpus_planning_contract.SLOT_NAME

# Trees and root-level files that are distribution/control plane, never
# corpus pages.  Dot-directories (.git, .cambium, .obsidian, ...) are
# excluded wherever they occur.
BASE_NON_CORPUS_TREES = frozenset((
    "kernel", profile_layout_contract.PROFILES_DIRECTORY, "Tools",
    "LICENSES", "docs"))
NON_CORPUS_ROOT_FILES = frozenset(("ROADMAP.md", "ROADMAP.zh-CN.md",
                                   "ATTRIBUTION.md", "LICENSE.md", "NOTICE"))
NON_CORPUS_ROOT_PREFIX = "README"


def standards_view(root):
    """Project the canonical adopter state into one onboarding token.

    Returns ``(state, values, uninstantiated, problems)`` where ``state`` is
    ``pre-adoption`` (state absent), ``adopted`` (valid state), or
    ``inconsistent`` (unsafe, unreadable, or malformed state).
    """
    path = os.path.join(root, *ACTIVE_STATE_RELATIVE.split("/"))
    fields = ["effective_date", "selected_profile_manifest", "status",
              "upstream_revision_id"]
    if not os.path.lexists(path):
        return "pre-adoption", None, fields, []
    state, active_view, snapshot_errors = standards_state.snapshot(root)
    problems = ["%s: %s" % (ACTIVE_STATE_RELATIVE, error)
                for error in snapshot_errors]
    if problems:
        return "inconsistent", None, [], problems
    lineage_errors = adoption_lineage_contract.current_lineage_errors(
        active_view, root=root)
    if lineage_errors:
        return ("inconsistent", None, [], [
            "%s: %s" % (ACTIVE_STATE_RELATIVE, error)
            for error in lineage_errors
        ])
    return ("adopted", {field: state[field] for field in fields}, [], [])


def _candidate_draft(root, profile_dir):
    """Read a candidate without invoking the admission or Gate evaluator."""
    return profile_contract.load_profile_draft(
        root, os.path.join(
            profile_dir, profile_layout_contract.PROFILE_MANIFEST_NAME))


def corpus_planning_state(draft):
    """Project applicability from a draft; it is never admission evidence."""
    if draft is None:
        return "unreadable"
    try:
        document = draft.slot(CORPUS_PLANNING_SLOT)
    except (KeyError, ValueError):
        return "unreadable"
    applicability = (document.get("applicability")
                     if isinstance(document, Mapping) else None)
    state = (applicability.get("state")
             if isinstance(applicability, Mapping) else None)
    return (state if state in corpus_planning_contract.APPLICABILITY_STATES
            else "unreadable")


def candidate_directories(root):
    """Profile directories under profiles/, excluding template and examples."""
    profiles_dir = os.path.join(
        root, profile_layout_contract.PROFILES_DIRECTORY)
    names = []
    try:
        entries = sorted(os.listdir(profiles_dir))
    except OSError:
        return names
    for name in entries:
        if (name in profile_layout_contract.RESERVED_PROFILE_IDS or
                name.startswith(".")):
            continue
        if os.path.isdir(os.path.join(profiles_dir, name)):
            names.append(name)
    return names


def evaluate_candidate(draft, error=None):
    """Classify a draft without creating a pass receipt or runtime contract."""
    if error is not None:
        return {
            "result": "invalid", "error": str(error),
            "mechanical": 1, "semantic_unresolved": 0,
            "unresolved_items": [],
        }
    counts = {check_profile.MECHANICAL: 0,
              check_profile.SEMANTIC_UNRESOLVED: 0}
    for diagnostic in draft.diagnostics:
        category = check_profile.finding_category(diagnostic.check)
        counts[category] = counts.get(category, 0) + 1
    unresolved = tuple(draft.unresolved_items)
    return {
        "result": ("ready" if draft.ready else
                   "invalid" if draft.diagnostics else
                   "incomplete" if unresolved else "invalid"),
        "mechanical": counts[check_profile.MECHANICAL],
        "semantic_unresolved": max(
            counts[check_profile.SEMANTIC_UNRESOLVED], len(unresolved)),
        "unresolved_items": list(unresolved),
    }


def corpus_page_count(root):
    """Count corpus Markdown pages outside the distribution/control trees."""
    non_corpus_trees = BASE_NON_CORPUS_TREES | {
        card_contract.load_schema(root)["directory"],
        read_set_contract.load_schema(root)["directory"],
    }
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        relative = os.path.relpath(dirpath, root)
        at_root = relative == "."
        dirnames[:] = sorted(
            name for name in dirnames
            if not name.startswith(".")
            and not (at_root and name in non_corpus_trees))
        for name in sorted(filenames):
            if not name.lower().endswith(".md"):
                continue
            if at_root and (name.startswith(NON_CORPUS_ROOT_PREFIX)
                            or name in NON_CORPUS_ROOT_FILES):
                continue
            count += 1
    return count


def runtime_view(root):
    state_dir = os.path.join(root, runtime_paths.STATE_ROOT)
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
        for name in ("kernel", profile_layout_contract.PROFILES_DIRECTORY,
                     "Tools"))
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

    names = candidate_directories(root)
    targeted = None
    if targeted_id is not None:
        targeted = targeted_id if targeted_id in names else None
    elif len(names) == 1:
        targeted = names[0]
    drafts = {}
    for name in names:
        profile_dir = os.path.join(
            root, profile_layout_contract.PROFILES_DIRECTORY, name)
        try:
            draft = _candidate_draft(root, profile_dir)
            drafts[name] = draft
            inspection = evaluate_candidate(draft)
        except (OSError, UnicodeError, ValueError) as exc:
            draft = None
            inspection = evaluate_candidate(None, exc)
        entry = {
            "directory": profile_layout_contract.profile_relative(name),
            "profile_id": draft.profile_id if draft is not None else None,
            "unresolved_count": len(
                draft.unresolved_items if draft is not None else ()),
            "targeted": name == targeted,
            "draft": inspection,
        }
        view["candidates"].append(entry)

    if state == "adopted":
        view["selected_profile"] = values["selected_profile_manifest"]
        selected_dir = os.path.join(
            root, os.path.dirname(view["selected_profile"]))
        try:
            selected_draft = drafts.get(os.path.basename(selected_dir))
            if selected_draft is None:
                selected_draft = _candidate_draft(root, selected_dir)
            view["corpus_planning_state"] = (
                corpus_planning_state(selected_draft)
                if selected_draft.ready else "unreadable")
        except (OSError, UnicodeError, ValueError):
            view["corpus_planning_state"] = "unreadable"
    elif targeted is not None:
        view["corpus_planning_state"] = corpus_planning_state(
            drafts.get(targeted))

    pages = corpus_page_count(root)
    view["corpus_page_count"] = pages
    view["corpus_state"] = "empty" if pages == 0 else "existing"

    # ---- exactly one next_action, by fixed precedence ----
    if view["cambium_runtime"]["present"]:
        view["next_action"] = "resume-existing-task"
        notes.append(
            "%s/ runtime state exists (state/ %s); existing-task "
            "recovery always wins -- run `python3 Tools/check_queue.py . "
            "--resume-status` and follow its next_action; scaffolding or "
            "adoption must not proceed over an existing runtime"
            % (runtime_paths.RUNTIME_ROOT,
               "has content"
               if view["cambium_runtime"]["state_has_content"]
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
        draft = entry["draft"]
        if draft["result"] == "ready":
            view["next_action"] = "validate-profile-load"
            notes.append(
                "candidate %s is structurally ready as a draft; run "
                "`python3 Tools/check_profile.py %s --root . --json` for "
                "the formal profile-load evaluation. Draft readiness does "
                "not confirm answers, authorize runtime access, or adopt "
                "the Profile; selection and adoption remain the existing "
                "R09 transaction" % (entry["directory"], entry["directory"]))
        else:
            view["next_action"] = "complete-profile-interview"
            notes.append(
                "candidate %s is %s: %d unresolved decision(s), "
                "%d mechanical finding(s). Complete the applicable "
                "questions in profiles/interview.yaml and inspect the "
                "candidate again; this status view emits no Gate evidence"
                % (entry["directory"], draft["result"],
                   draft["semantic_unresolved"], draft["mechanical"]))
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
            "exists; confirm one Task Plan and publish it with "
            "`init_state.py --plan <path> --apply`" % pages)
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
        "selected Profile must have a complete structured candidate before "
        "this status can be derived -- inspect it, then run `python3 Tools/check_profile.py %s --root . "
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
        line = ("    - %s profile_id=%s unresolved_count=%d"
                % (entry["directory"], entry["profile_id"],
                   entry["unresolved_count"]))
        load = entry["draft"]
        if load is not None:
            line += (" draft=%s mechanical=%d semantic_unresolved=%d"
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
        print("  cambium_runtime=%s/ absent" % runtime_paths.RUNTIME_ROOT)
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
                             "under profiles/ for draft inspection (defaults to the single candidate "
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
