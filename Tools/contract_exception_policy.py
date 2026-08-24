#!/usr/bin/env python3
"""The closed set of policies a contract exception may except.

A contract exception is a bounded grant against one named policy.  K13/02
fixes the shape of the record, K13/06 fixes who may write it, and the kernel
row named on each registry entry below owns the rule being excepted.  What
none of those owns on its own is the part kept here: which policies are
exceptable at all, what a `limit` means for each, what the policy resolves to
right now, and how standing quotas and granted exceptions fold into the one
effective ceiling an authorization is judged against.

This capability was carried by `kblib` until this module existed, and being
carried there was the defect.  `kblib` is the layer nearly every shipped tool
imports -- a restricted YAML parser, receipt construction, atomic writes,
markdown readers -- and it is infrastructure in the strict sense that nothing
in it records a governance decision.  A governance domain object placed in
that layer makes the entire tree a dependency of one policy question: the
closed registry could not be extended, a protocol version could not be
bumped, and a fingerprint algorithm could not be revised without editing what
every tool imports.  The blast radius read "shared library" while the change
was "governance", and the two must not be the same edit.  Contract exception
policy is not infrastructure; this module is where that is said out loud.

Two boundaries this module holds deliberately:

* It is not `amendment_policy`.  That module owns operational Amendment
  impact and delegated authority -- whether this actor may make a change of
  this class.  This one owns which policies are exceptable and what an
  exception is judged against.  Folding them together would put "may the
  actor act" and "what is the policy" behind one name, one import, and one
  change.

* It owns no measurement and no verdict.  `kblib.quota_share_within_limit`
  still decides whether a measured share fits a limit, and each consumer
  still decides what its own finding is.  Resolved here is the policy the
  comparison is made against, never the comparison and never its outcome.

Direction is one-way by construction: this module imports `kblib` and nothing
else in the tree, and `kblib` imports nothing from the tree at all.  Policy
depends on infrastructure; infrastructure never depends on policy.
"""

import json
import re

import kblib


PRIORITY_QUOTA_SECTION = "Priority Quota"
PRIORITY_QUOTA_KERNEL_DEFAULTS = (15.0, 35.0)


def priority_quota_policy(rubric_text):
    """Read the Priority Rubric slot's quota registration, K00/07.

    Returns ``((p0, p1), configured, errors)``.  One reader for the one
    long-lived quota truth: the profile-load Gate validates through it and the
    batch-close consumer resolves through it, so the two can never disagree
    about what the slot declares.  ``Registration: None`` selects the kernel
    defaults; ``Configured`` requires exactly one ``P0`` and one ``P1`` row,
    each a percent share in [0, 100), a nonempty rationale, and the pair
    strictly below 100 together -- P2 is the remainder class, carries every
    terminology stub and placeholder page, and must stay reachable.
    """
    errors = []
    inside = False
    declaration = None
    rows = []
    for _line_number, line in kblib.markdown_authority_lines(
            rubric_text or ""):
        heading = kblib.markdown_atx_heading(line)
        if heading is not None:
            if inside and heading[0] <= 2:
                break
            inside = (heading[0] == 2 and
                      heading[1] == PRIORITY_QUOTA_SECTION)
            continue
        if not inside:
            continue
        stripped = line.strip()
        match = re.fullmatch(r"-\s+Registration:\s*(.+)", stripped)
        if match:
            declaration = match.group(1).strip()
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= {"-", ":", " "} for cell in cells):
                continue
            rows.append(cells)
    if declaration is None:
        errors.append(
            "the %s section must declare `- Registration: None` (kernel "
            "defaults) or `- Registration: Configured`" %
            PRIORITY_QUOTA_SECTION)
        return PRIORITY_QUOTA_KERNEL_DEFAULTS, False, errors
    if declaration == "None":
        data_rows = rows[1:] if rows else []
        if data_rows:
            errors.append(
                "Registration: None leaves active quota rows behind; remove "
                "them so the single declaration is authoritative")
        return PRIORITY_QUOTA_KERNEL_DEFAULTS, False, errors
    if declaration != "Configured":
        errors.append(
            "%s declaration %r is invalid; use `None` or `Configured`" %
            (PRIORITY_QUOTA_SECTION, declaration))
        return PRIORITY_QUOTA_KERNEL_DEFAULTS, False, errors

    values = {}
    data_rows = rows[1:] if rows else []
    for cells in data_rows:
        if len(cells) != 3 or not all(cells):
            errors.append(
                "a Configured quota row must carry exactly class, maximum "
                "share, and a nonempty rationale; found %r" % (cells,))
            continue
        cls = cells[0].strip("`").strip()
        if cls not in ("P0", "P1"):
            errors.append("quota class %r is not P0 or P1" % cls)
            continue
        if cls in values:
            errors.append("quota class %s is declared twice" % cls)
            continue
        raw = cells[1].strip("`").strip()
        number = raw[:-1].strip() if raw.endswith("%") else raw
        try:
            share = float(number)
        except ValueError:
            errors.append(
                "%s maximum share %r is not a number, optionally followed "
                "by %%" % (cls, raw))
            continue
        if not 0 <= share < 100:
            errors.append(
                "%s maximum share must be at least 0 and under 100" % cls)
            continue
        values[cls] = share
    missing = sorted({"P0", "P1"} - set(values))
    if missing:
        errors.append(
            "Configured must declare both quota classes; missing %s" %
            ", ".join(missing))
        return PRIORITY_QUOTA_KERNEL_DEFAULTS, False, errors
    if values["P0"] + values["P1"] >= 100:
        errors.append(
            "the two quota shares sum to %.1f%%; K00/07 requires the pair to "
            "stay strictly below 100 so the P2 remainder class stays "
            "non-empty" % (values["P0"] + values["P1"]))
    return (values["P0"], values["P1"]), True, errors


POLICY_REGISTRY = {
    # The closed registry of policies a contract exception may except.  Each
    # entry names the owner module and the bound domain its `limit` uses.
    # Extending this mapping is a governance change under the owner named on
    # the row, not an edit.
    "priority_quota.P0": {
        "owner": "kernel/K00 Standards Control/"
                 "07 Effort Tiering and Priority Quota.md",
        "quota_class": "P0",
        "limit_domain": "percent-share-under-100",
    },
    "priority_quota.P1": {
        "owner": "kernel/K00 Standards Control/"
                 "07 Effort Tiering and Priority Quota.md",
        "quota_class": "P1",
        "limit_domain": "percent-share-under-100",
    },
    "coverage.reviewed_era": {
        "owner": "kernel/K02 Knowledge Work Construction/"
                 "01 Inventory and Coverage Ledger.md",
        "limit_domain": "record-count-ceiling",
    },
}
# Policy families.  A family fixes what `limit` means and which resolver
# produces the baseline fingerprint an exception is judged against.
PRIORITY_QUOTA_POLICY_IDS = frozenset(
    policy_id for policy_id, entry in POLICY_REGISTRY.items()
    if entry["limit_domain"] == "percent-share-under-100")
RECORD_COUNT_POLICY_IDS = frozenset(
    policy_id for policy_id, entry in POLICY_REGISTRY.items()
    if entry["limit_domain"] == "record-count-ceiling")
# Bumped when the comparison arithmetic or the resolution semantics change,
# so an exception judged under one protocol cannot silently authorize under
# another.
PRIORITY_QUOTA_PROTOCOL_VERSION = 1


def effective_priority_policy(rubric_text):
    """Resolve the one effective quota policy and its canonical fingerprint.

    Everything an authorization decision depends on is folded into one object
    and one fingerprint: the registered policy IDs, the *resolved* per-class
    values (kernel defaults included -- a `Registration: None` slot resolves
    to the kernel numbers, so a kernel default change moves this fingerprint
    even though the rubric bytes did not), the resolution source, and the
    comparison protocol version.  An exception's baseline fingerprint binds
    to this object; hashing the rubric file alone would let the effective
    policy drift underneath a standing grant.

    Returns ``(policy, fingerprint, errors)``.  ``fingerprint`` is None when
    the slot does not resolve.
    """
    (p0, p1), configured, errors = priority_quota_policy(rubric_text)
    policy = {
        "schema_version": 1,
        "protocol_version": PRIORITY_QUOTA_PROTOCOL_VERSION,
        "source": "profile-configured" if configured else "kernel-defaults",
        "kernel_defaults": {
            "priority_quota.P0": PRIORITY_QUOTA_KERNEL_DEFAULTS[0],
            "priority_quota.P1": PRIORITY_QUOTA_KERNEL_DEFAULTS[1],
        },
        "resolved": {
            "priority_quota.P0": p0,
            "priority_quota.P1": p1,
        },
    }
    if errors:
        return policy, None, errors
    payload = json.dumps(policy, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return policy, kblib.sha256_bytes(payload), errors


COVERAGE_POLICY_PROTOCOL_VERSION = 1


def effective_coverage_policy():
    """Resolve the kernel-owned Coverage evidence-era policy.

    K02/01 fixes this rule with no profile input to resolve: `reviewed`
    carries the era of the evidence that earned it.  The object exists for
    the same reason the quota resolver's does -- an exception binds to a
    fingerprint of the policy it was judged against, so a later revision of
    the rule invalidates a grant made under the old one -- but here the
    whole policy is kernel text, so the object is closed and constant.

    Returns ``(policy, fingerprint, errors)`` for symmetry with
    :func:`effective_priority_policy`; ``errors`` is always empty.
    """
    policy = {
        "schema_version": 1,
        "protocol_version": COVERAGE_POLICY_PROTOCOL_VERSION,
        "policy_id": "coverage.reviewed_era",
        "source": "kernel",
        "rule": "authoring_status reviewed names the receipt era that "
                "earned it",
    }
    payload = json.dumps(policy, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return policy, kblib.sha256_bytes(payload), []


def effective_policy_for(policy_id, rubric_text=None):
    """Resolve the effective policy object for one registered policy.

    One dispatcher so every consumer -- the amendment writer, the runtime
    validator, the close -- judges an exception against the same baseline
    its family defines, instead of each deciding what "the policy" means.

    Returns ``(policy, fingerprint, errors)``.  A quota policy needs the
    selected Profile's Priority Rubric bytes; a kernel-owned policy takes
    none.  An unregistered policy id resolves to nothing.
    """
    if policy_id in PRIORITY_QUOTA_POLICY_IDS:
        if rubric_text is None:
            return None, None, [
                "%s is a Profile-configured policy; its Priority Rubric "
                "bytes are required to resolve it" % policy_id]
        return effective_priority_policy(rubric_text)
    if policy_id in RECORD_COUNT_POLICY_IDS:
        return effective_coverage_policy()
    return None, None, [
        "%r is not in the closed policy registry" % policy_id]


def effective_quota_ceilings(policy, exceptions):
    """Fold standing quotas and granted exceptions into effective ceilings.

    ``policy`` is the object from :func:`effective_priority_policy`;
    ``exceptions`` is the list of currently applicable contract policy
    exceptions (the caller decides currency and scope).  For each registered
    policy the effective ceiling is the largest granted exception limit when
    one exists, else the standing resolved value.

    K00/07's joint bound is judged HERE, over the effective pair, because a
    grant and the other class's standing quota partition the same corpus: a
    P0 grant of 80 next to a standing P1 of 35 is a 115 percent ceiling, and
    summing the grants alone would call that bounded.  This function is the
    one owner of that arithmetic; shape validators may keep the weaker
    grants-only necessary condition but never redefine this rule.

    Returns ``(ceilings, errors)``.  ``ceilings`` maps policy_id to
    ``{"limit": number, "source": "standing" | "exception:<decision_id>"}``.
    """
    from fractions import Fraction
    ceilings = {}
    # Quota family only: the joint bound is an arithmetic over corpus shares,
    # and a policy from another family has no standing share to fold in.
    for policy_id in sorted(PRIORITY_QUOTA_POLICY_IDS):
        resolved = (policy or {}).get("resolved", {}).get(policy_id)
        ceilings[policy_id] = {"limit": resolved, "source": "standing"}
    for entry in exceptions or []:
        if not isinstance(entry, dict):
            continue
        policy_id = entry.get("policy_id")
        limit = entry.get("limit")
        if policy_id not in PRIORITY_QUOTA_POLICY_IDS:
            continue
        if isinstance(limit, bool) or not isinstance(limit, (int, float)):
            continue
        current = ceilings[policy_id]
        if (current["source"] == "standing" or
                not isinstance(current["limit"], (int, float)) or
                limit > current["limit"]):
            ceilings[policy_id] = {
                "limit": limit,
                "source": "exception:%s" % entry.get("decision_id"),
            }
    errors = []
    joint = Fraction(0)
    for policy_id, ceiling in sorted(ceilings.items()):
        limit = ceiling["limit"]
        if isinstance(limit, bool) or not isinstance(limit, (int, float)):
            errors.append(
                "effective ceiling for %s does not resolve to a number; an "
                "unresolvable policy authorizes nothing" % policy_id)
            continue
        joint += Fraction(str(limit))
    if not errors and joint >= 100:
        detail = ", ".join(
            "%s=%s(%s)" % (policy_id, ceiling["limit"], ceiling["source"])
            for policy_id, ceiling in sorted(ceilings.items()))
        errors.append(
            "effective quota ceilings sum to %s%% (%s); K00/07 requires the "
            "pair to stay strictly below 100 so the P2 remainder class "
            "stays non-empty" % (float(joint), detail))
    return ceilings, errors
