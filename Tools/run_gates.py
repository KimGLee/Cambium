#!/usr/bin/env python3
"""Run the adopter verification set derived from the K00/12 Gate registry.

The set this tool runs is NOT its own opinion.  K00/12's Stable Gate ID
Registry is the one enumeration of registered Gates; the adopter verification
set is DERIVED from it: every row whose producer is a named deterministic
tool and whose Lifecycle is `not-batch-scoped`.  Batch-positioned rows run at
their batch boundary, `manual-attestation` rows are recorded by a person, and
transaction writers (`adopt_standards`, `record_corpus_acceptance`) produce
their receipts inside their own guarded transactions -- a verification sweep
never runs them.  A registry row this runner recognizes in none of those
classes fails the run closed: the registry grew and this runner must be
extended WITH it, loudly, never silently skipped.

Before any gate runs, two preflights guard the conclusions:

* the registry/producer agreement check (`check_queue`
  `gate_registry_producer_errors`) -- a registry row contradicting an
  installed producer would make every downstream result unreliable;
* compiled-artifact freshness (`compose_vocab --check`,
  `compose_page_contract --check`) -- a stale composed artifact lets a gate
  pass against bytes that are not the profile's current answers.

Exit codes follow the shared contract stated in K00/12 (implementation:
``kblib.exit_code``): 0 = every gate passed clean; 1 = at least one failure
or an unrunnable/unreliable setup; 2 = no failure, but at least one HOLD --
an exit-2 child, a freshness mismatch, or a distribution-boundary candidate.
2 is never success and never failure: each held line must be read.

The distribution boundary (root `distribution-boundary.yaml`, owner K00/03)
is checked when the selected profile lives outside `profiles/examples/`:
such a runtime is an adopter's, and a distribution-only tree present in it
(shipped tests, profile scaffolding) is reported as a candidate.  What an
adopter carries is what its governance needs, not what upstream has.

Exit codes: 0 = all pass; 1 = failure; 2 = holds to read.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib
import profile_contract

TOOL = "run_gates"
TOOL_VERSION = "1.0.0"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Producers whose receipts exist only as commit evidence of their own guarded
# transaction.  Running one is a state write, which a verification sweep must
# never perform; their gates are satisfied by the receipts the transactions
# already appended.
TRANSACTION_WRITER_TOOLS = frozenset((
    "adopt_standards", "record_corpus_acceptance",
))

DISTRIBUTION_BOUNDARY_PATH = "distribution-boundary.yaml"


class RunnerError(Exception):
    pass


def _python():
    return sys.executable or "python3"


def _tool_path(name):
    return os.path.join(SCRIPT_DIR, "%s.py" % name)


def _selected_profile(root, override):
    """Resolve the selected profile manifest, live runtime first."""
    if override:
        manifest = os.path.join(override, "profile.md")
        if not os.path.isfile(os.path.join(root, manifest)):
            raise RunnerError(
                "--profile %s has no profile.md under the repository root"
                % override)
        return manifest.replace(os.sep, "/")
    queue_path = os.path.join(root, check_queue.QUEUE_PATH)
    if os.path.isfile(queue_path):
        with open(queue_path, encoding="utf-8") as handle:
            queue = kblib.parse_yaml_subset(handle.read())
        manifest = (queue or {}).get("selected_profile_manifest")
        if isinstance(manifest, str) and manifest.strip():
            return manifest.strip()
    raise RunnerError(
        "no selected profile: pass --profile <dir> or run inside a "
        "materialized runtime whose Queue names selected_profile_manifest")


def _boundary_declaration(root):
    """Read the distribution boundary declaration, shape-checked."""
    path = os.path.join(root, DISTRIBUTION_BOUNDARY_PATH)
    if not os.path.isfile(path):
        return None, ["%s is missing; the distribution boundary is a "
                      "declared fact, not an inference" %
                      DISTRIBUTION_BOUNDARY_PATH]
    with open(path, encoding="utf-8") as handle:
        declaration = kblib.parse_yaml_subset(handle.read())
    errors = []
    if not isinstance(declaration, dict) or \
            declaration.get("schema_version") != 1:
        return None, ["%s schema_version must be 1" %
                      DISTRIBUTION_BOUNDARY_PATH]
    entries = declaration.get("distribution_only")
    if not isinstance(entries, list) or not entries:
        return None, ["%s distribution_only must be a non-empty list" %
                      DISTRIBUTION_BOUNDARY_PATH]
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or \
                not isinstance(entry.get("path"), str) or \
                not entry.get("path").strip() or \
                not isinstance(entry.get("reason"), str) or \
                not entry.get("reason").strip():
            errors.append(
                "%s distribution_only[%d] needs a path and a reason" %
                (DISTRIBUTION_BOUNDARY_PATH, index))
    return (None, errors) if errors else (entries, [])


def _boundary_findings(root, manifest):
    """Candidates for distribution-only trees present in an adopter runtime."""
    if manifest.startswith("profiles/examples/"):
        # The distribution's own repository (and its fixtures) selects a
        # shipped example profile; the boundary speaks only to adopters.
        return [], []
    entries, errors = _boundary_declaration(root)
    if errors:
        return [], errors
    findings = []
    for entry in entries:
        relative = entry["path"].strip().rstrip("/")
        if os.path.exists(os.path.join(root, relative)):
            findings.append(
                "%s is present but declared distribution-only: %s"
                % (relative, entry["reason"].strip()))
    return findings, []


def _effective_policy(root, manifest):
    """Resolve the selected profile's standing quota policy, or fail closed.

    The sweep hands `check_vocab` the SAME resolved values and fingerprint
    the batch-close consumer uses (one resolver, `kblib`), because a sweep
    that measures against kernel defaults on a profile with a Configured
    quota block reports an excess nobody has -- the first live run of this
    tool did exactly that, which is why this function exists.
    """
    manifest_path = os.path.join(root, manifest)
    with open(manifest_path, encoding="utf-8") as handle:
        manifest_text = handle.read()
    bindings = kblib.profile_slot_bindings(manifest_text)
    binding = (bindings.get("Priority Rubric") or "").strip("`").strip()
    if not binding:
        raise RunnerError("the selected Profile binds no Priority Rubric "
                          "slot; K00/07 places the standing quotas there")
    rubric_path = os.path.join(os.path.dirname(manifest_path), binding)
    with open(rubric_path, encoding="utf-8") as handle:
        rubric_text = handle.read()
    policy, fingerprint, errors = kblib.effective_priority_policy(rubric_text)
    if errors or fingerprint is None:
        raise RunnerError(
            "the selected Profile's Priority Rubric does not resolve:\n  %s"
            % "\n  ".join(errors[:5]))
    return policy, fingerprint


def _residual_scan_command(root, manifest):
    """Compile the profile's registered scan, or explain why there is none."""
    contract = profile_contract.load_profile_contract(root, manifest)
    if not contract.authorized:
        raise RunnerError(
            "profile contract is not authorized: %s" %
            profile_contract.format_diagnostics(contract.diagnostics))
    if contract.required_scan is None:
        return None
    return list(profile_contract.compile_registered_scan_command(
        root, contract))


def _recipes(root, manifest, excludes):
    """Invocation recipes per (tool, mode) for runnable registry rows.

    This mapping is the runner's own contract, not a second Gate authority:
    K00/12 stays the only enumeration of Gates, and a registered deterministic
    producer missing here fails the run closed instead of being skipped.
    """
    profile_dir = os.path.dirname(manifest)
    exclude_args = []
    for value in excludes:
        exclude_args.extend(["--exclude", value])
    python = _python()
    policy, policy_fingerprint = _effective_policy(root, manifest)
    recipes = {
        ("check_links", "*"): [
            python, _tool_path("check_links"), root, *exclude_args],
        ("check_vocab", "*"): [
            python, _tool_path("check_vocab"), root, *exclude_args,
            "--quota-p0",
            str(policy["resolved"]["priority_quota.P0"]),
            "--quota-p1",
            str(policy["resolved"]["priority_quota.P1"]),
            "--policy-fingerprint", policy_fingerprint],
        ("check_structure", "*"): [
            python, _tool_path("check_structure"), root,
            "--profile", os.path.join(root, profile_dir)],
        ("check_profile", "*"): [
            python, _tool_path("check_profile"),
            os.path.join(root, profile_dir), "--root", root],
        ("check_corpus_plan", "*"): [
            python, _tool_path("check_corpus_plan"), root],
        ("check_queue", "consistency"): [
            python, _tool_path("check_queue"), root],
        ("check_queue", "resume-status"): [
            python, _tool_path("check_queue"), root, "--resume-status"],
        ("check_page_contract", "*"): [
            python, _tool_path("check_page_contract"), root,
            "--profile", os.path.join(root, profile_dir), *exclude_args],
        ("check_boundary_contract", "*"): [
            python, _tool_path("check_boundary_contract"), root,
            "--profile", os.path.join(root, profile_dir), *exclude_args],
    }
    residual = _residual_scan_command(root, manifest)
    if residual is not None:
        recipes[("check_residual_content", "*")] = residual
    else:
        recipes[("check_residual_content", "*")] = None  # not applicable
    return recipes


def _freshness_commands(root, manifest):
    profile_dir = os.path.join(root, os.path.dirname(manifest))
    python = _python()
    return [
        ("compose_vocab --check", [
            python, _tool_path("compose_vocab"),
            "--extensions",
            os.path.join(profile_dir, "vocabulary-extensions.yaml"),
            "--output", os.path.join(SCRIPT_DIR, "vocab.yaml"),
            "--check"]),
        ("compose_page_contract --check", [
            python, _tool_path("compose_page_contract"),
            "--profile", profile_dir,
            "--output", os.path.join(SCRIPT_DIR, "page_contract.yaml"),
            "--check"]),
    ]


def derive_verification_set(root, registry, recipes):
    """Derive the adopter verification set from the K00/12 registry.

    Every deterministic `not-batch-scoped` row must resolve to exactly one
    of: an invocation recipe, a transaction writer, or a manual attestation.
    A row that resolves to none is a hard error, never a skip.
    """
    derived = []
    hard_errors = []
    for gate_id, predicate in sorted(registry.items()):
        if predicate["lifecycle_states"] != ("not-batch-scoped",):
            continue
        tool = predicate["tool"]
        mode = predicate["mode"]
        if tool == check_queue.MANUAL_ATTESTATION_TOOL:
            # Human-recorded.  One row declares a machine INPUT the runner
            # can produce for the person: runtime-card-synchronization is
            # signed over `stamp_cards . --check` output (K00/12 row text).
            if gate_id == "runtime-card-synchronization":
                derived.append((gate_id, "input", [
                    _python(), _tool_path("stamp_cards"), root, "--check"]))
            else:
                derived.append((gate_id, "manual", None))
            continue
        if tool in TRANSACTION_WRITER_TOOLS:
            derived.append((gate_id, "transaction", None))
            continue
        key = (tool, mode if (tool, mode) in recipes else "*")
        if key not in recipes:
            hard_errors.append(
                "Gate ID %s registers producer %s (mode %s) that this "
                "runner has no recipe for; extend run_gates.py together "
                "with the registry -- a silent skip is how verification "
                "sets rot" % (gate_id, tool, mode))
            continue
        derived.append((gate_id, "run", recipes[key]))
    return derived, hard_errors


def _run(command):
    completed = subprocess.run(
        command, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False)
    return completed.returncode, completed.stdout


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the adopter verification set derived from the "
                    "K00/12 Stable Gate ID Registry (deterministic, "
                    "not-batch-scoped producers).")
    parser.add_argument("root", help="repository root")
    parser.add_argument("--profile",
                        help="profile directory override; default is the "
                             "live runtime's selected_profile_manifest")
    parser.add_argument("--exclude", action="append", default=[],
                        help="path prefix passed through to scanners that "
                             "accept it (repeatable)")
    parser.add_argument("--list", action="store_true",
                        help="print the derived set and each command "
                             "without running anything")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)

    registry, registry_errors = check_queue.standards_gate_registry(root)
    registry_errors.extend(
        check_queue.gate_registry_producer_errors(registry))
    if registry_errors:
        for error in registry_errors:
            print("  [FAIL registry] %s" % error)
        print("run_gates: the Gate registry and its producers disagree; "
              "no verification result would be reliable")
        return 1

    try:
        manifest = _selected_profile(root, args.profile)
        recipes = _recipes(root, manifest, args.exclude)
    except (RunnerError, profile_contract.ProfileContractError,
            OSError, ValueError) as exc:
        print("run_gates: %s" % exc)
        return 1

    derived, hard_errors = derive_verification_set(root, registry, recipes)

    if hard_errors:
        for error in hard_errors:
            print("  [FAIL derive] %s" % error)
        return 1

    freshness = _freshness_commands(root, manifest)
    boundary_findings, boundary_errors = _boundary_findings(root, manifest)

    if args.list:
        for label, command in freshness:
            print("freshness %-28s %s" % (label, " ".join(command)))
        for gate_id, kind, command in derived:
            print("%-12s %-36s %s" % (
                kind, gate_id, " ".join(command) if command else "-"))
        return 0

    failures = 0
    holds = 0

    for label, command in freshness:
        code, output = _run(command)
        if code == 0:
            print("  [PASS freshness] %s" % label)
        elif code == 2:
            holds += 1
            print("  [HOLD freshness] %s -- stale compiled artifact; gate "
                  "conclusions below are unreliable until recomposed" % label)
            print("    " + output.strip().splitlines()[-1]
                  if output.strip() else "")
        else:
            failures += 1
            print("  [FAIL freshness] %s (exit %d)" % (label, code))
            for line in output.strip().splitlines()[-5:]:
                print("    " + line)

    ran = {}
    for gate_id, kind, command in derived:
        if kind == "manual":
            print("  [MANUAL] %s -- recorded by a person under K12/17, "
                  "never produced by a sweep" % gate_id)
            continue
        if kind == "transaction":
            print("  [TRANSACTION] %s -- produced only inside its own "
                  "guarded transaction" % gate_id)
            continue
        if command is None:
            print("  [N/A] %s -- the selected profile registers no scan"
                  % gate_id)
            continue
        key = tuple(command)
        if key in ran:
            code, output = ran[key]
            print("  [%s] %s (same run as above)" %
                  ("PASS" if code == 0 else
                   "HOLD" if code == 2 else "FAIL", gate_id))
            continue
        code, output = _run(command)
        ran[key] = (code, output)
        if code == 0:
            print("  [PASS] %s" % gate_id)
        elif code == 2:
            holds += 1
            print("  [HOLD] %s -- exit 2 is neither pass nor failure; "
                  "read each held line:" % gate_id)
            for line in output.strip().splitlines():
                if "[CAND" in line or "HOLD" in line or "hold" in line:
                    print("    " + line.strip())
        else:
            failures += 1
            print("  [FAIL] %s (exit %d)" % (gate_id, code))
            for line in output.strip().splitlines()[-8:]:
                print("    " + line)

    for error in boundary_errors:
        failures += 1
        print("  [FAIL boundary] %s" % error)
    for finding in boundary_findings:
        holds += 1
        print("  [CAND boundary] %s" % finding)

    print("run_gates: gates=%d failures=%d holds=%d" %
          (sum(1 for _, kind, _ in derived if kind in ("run", "input")),
           failures, holds))
    if failures:
        print("  Conclusion: at least one registered gate failed; the "
              "repository is not in a verified state.")
        return 1
    if holds:
        print("  Conclusion: no failures, %d hold(s); a hold is a line a "
              "person must read, never a pass and never an error." % holds)
        return 2
    print("  Conclusion: every derived gate passed clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
