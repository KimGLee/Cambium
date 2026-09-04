#!/usr/bin/env python3
"""Parse and execute the Kernel-owned contract-exception policy registry.

``kernel/K00 Standards Control/contract-exception-policy-base.yaml`` is the
sole authority for which policies are exceptable, who owns them, what their
limits mean, and their effective-policy fingerprint payload.
This module owns only deterministic loading, validation, Profile-value
parsing, policy resolution, hashing, and effective-ceiling arithmetic.  It
does not create governance policy, measure a corpus, issue a verdict, or
authorize an amendment.

Runtime consumers resolve the current policy directly from this registry.
"""
from Tools.platform.repository.repository import repository_source_root

import json
import os
from pathlib import Path, PurePosixPath
import re

import Tools.platform.common.kblib as kblib


POLICY_REGISTRY_PATH = (
    "kernel/K00 Standards Control/contract-exception-policy-base.yaml")
_ID_RE = re.compile(r"[a-z][a-z0-9_]*(?:[.-][A-Za-z0-9_]+)*")


def _closed_mapping(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(
            "%s fields must be exactly %s" %
            (label, ", ".join(sorted(fields))))


def _positive_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("%s must be a positive integer" % label)


def _nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % label)


def _owner_path(owner, root, label, require_owner_files):
    _nonempty(owner, label)
    if "\\" in owner:
        raise ValueError("%s must use repository-relative POSIX syntax" % label)
    pure = PurePosixPath(owner)
    if (pure.is_absolute() or not pure.parts or pure.parts[0] != "kernel" or
            any(part in ("", ".", "..") for part in pure.parts) or
            pure.suffix != ".md"):
        raise ValueError(
            "%s must be a safe repository-relative Kernel Markdown path" %
            label)
    if require_owner_files:
        root_path = Path(root).resolve()
        candidate = (root_path / Path(*pure.parts)).resolve()
        try:
            candidate.relative_to(root_path / "kernel")
        except ValueError as exc:
            raise ValueError("%s escapes the Kernel root" % label) from exc
        if not candidate.is_file():
            raise ValueError("%s does not resolve to a Kernel owner" % label)


def policy_registry_records(document, *, root=None,
                            require_owner_files=True):
    """Validate a registry document and return policy rows by stable ID."""
    if root is None:
        root = repository_source_root(__file__)
    _closed_mapping(
        document, {"schema_version", "registry_id", "families"},
        "contract-exception policy registry")
    if document.get("schema_version") != 2:
        raise ValueError(
            "contract-exception policy registry schema_version must be 2")
    if document.get("registry_id") != "contract-exception-policy":
        raise ValueError(
            "contract-exception policy registry has the wrong registry_id")
    families = document.get("families")
    if not isinstance(families, list) or not families:
        raise ValueError("contract-exception policy families must be non-empty")

    family_ids = set()
    kinds = set()
    records = {}
    for family_index, family in enumerate(families):
        label = "contract-exception policy family %d" % family_index
        if not isinstance(family, dict):
            raise ValueError("%s must be a mapping" % label)
        kind = family.get("policy_kind")
        common = {
            "family_id", "policy_kind", "fingerprint_payload",
            "limit_domain", "policies",
        }
        fields = common | {"profile_resolution"}
        _closed_mapping(family, fields, label)
        family_id = family.get("family_id")
        _nonempty(family_id, "%s family_id" % label)
        if not re.fullmatch(r"[a-z][a-z0-9_]*", family_id):
            raise ValueError("%s has an invalid family_id" % label)
        if family_id in family_ids:
            raise ValueError("duplicate policy family %s" % family_id)
        family_ids.add(family_id)
        if kind != "profile-priority-quota":
            raise ValueError("%s has unsupported policy_kind %r" %
                             (label, kind))
        if kind in kinds:
            raise ValueError("duplicate policy family kind %s" % kind)
        kinds.add(kind)

        payload = family.get("fingerprint_payload")
        _closed_mapping(payload, {
            "schema_version", "protocol_version",
            "profile_none_source", "profile_configured_source",
        }, "%s fingerprint_payload" % label)
        _positive_int(payload.get("schema_version"),
                      "%s payload schema_version" % label)
        _positive_int(payload.get("protocol_version"),
                      "%s payload protocol_version" % label)
        for field in set(payload) - {"schema_version", "protocol_version"}:
            _nonempty(payload.get(field), "%s payload %s" % (label, field))
        if (payload["profile_none_source"] ==
                payload["profile_configured_source"]):
            raise ValueError("%s payload source labels must be distinct" % label)

        domain = family.get("limit_domain")
        _closed_mapping(domain, {
            "domain_id", "value_type", "minimum_inclusive",
            "maximum_exclusive", "joint_maximum_exclusive",
        }, "%s limit_domain" % label)
        if (domain.get("domain_id") != "percent-share-under-100" or
                domain.get("value_type") != "number"):
            raise ValueError("%s has an unsupported quota limit domain" % label)
        minimum = domain.get("minimum_inclusive")
        maximum = domain.get("maximum_exclusive")
        joint = domain.get("joint_maximum_exclusive")
        if any(isinstance(value, bool) or
               not isinstance(value, (int, float))
               for value in (minimum, maximum, joint)):
            raise ValueError("%s quota bounds must be numeric" % label)
        if not minimum < maximum or joint != maximum:
            raise ValueError(
                "%s quota bounds must leave one common remainder" % label)

        resolution = family.get("profile_resolution")
        _closed_mapping(resolution, {
            "section", "registration_none", "registration_configured",
            "remainder_class",
        }, "%s profile_resolution" % label)
        for field, value in resolution.items():
            _nonempty(value, "%s profile_resolution %s" % (label, field))
        if resolution["registration_none"] == \
                resolution["registration_configured"]:
            raise ValueError(
                "%s registration states must be distinct" % label)

        policies = family.get("policies")
        if not isinstance(policies, list) or not policies:
            raise ValueError("%s policies must be non-empty" % label)
        classes = set()
        for policy_index, policy in enumerate(policies):
            policy_label = "%s policy %d" % (label, policy_index)
            fields = {"policy_id", "owner", "quota_class"}
            _closed_mapping(policy, fields, policy_label)
            policy_id = policy.get("policy_id")
            _nonempty(policy_id, "%s policy_id" % policy_label)
            if not _ID_RE.fullmatch(policy_id):
                raise ValueError("%s has an invalid policy_id" % policy_label)
            if policy_id in records:
                raise ValueError("duplicate policy_id %s" % policy_id)
            _owner_path(policy.get("owner"), root,
                        "%s owner" % policy_label, require_owner_files)
            record = dict(policy)
            record["family_id"] = family_id
            record["policy_kind"] = kind
            record.update(domain)
            # Project the registry-owned identity without inventing a second
            # public spelling.  Consumers use this exact current-contract
            # field; the enclosing ``limit_domain`` object remains the
            # machine owner's source of the domain constraints.
            record["domain_id"] = domain["domain_id"]
            quota_class = policy.get("quota_class")
            _nonempty(quota_class, "%s quota_class" % policy_label)
            if quota_class in classes:
                raise ValueError("duplicate quota_class %s" % quota_class)
            classes.add(quota_class)
            record["remainder_class"] = \
                family["profile_resolution"]["remainder_class"]
            records[policy_id] = record

    if kinds != {"profile-priority-quota"}:
        raise ValueError(
            "the shipped registry must carry its priority quota family")
    return records


def load_policy_registry(root=None, *, text=None,
                         require_owner_files=True):
    """Load and strictly validate the Kernel-owned machine registry."""
    if root is None:
        root = repository_source_root(__file__)
    if text is None:
        text = kblib.read_text(
            os.path.join(root, *POLICY_REGISTRY_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    policy_registry_records(
        document, root=root, require_owner_files=require_owner_files)
    return document


def _family(document, kind):
    return next(row for row in document["families"]
                if row["policy_kind"] == kind)


_SHIPPED_POLICY_REGISTRY = load_policy_registry()
POLICY_REGISTRY = policy_registry_records(_SHIPPED_POLICY_REGISTRY)
_PRIORITY_FAMILY = _family(
    _SHIPPED_POLICY_REGISTRY, "profile-priority-quota")
PRIORITY_QUOTA_SECTION = _PRIORITY_FAMILY["profile_resolution"]["section"]
PRIORITY_QUOTA_NONE = \
    _PRIORITY_FAMILY["profile_resolution"]["registration_none"]
PRIORITY_QUOTA_CONFIGURED = \
    _PRIORITY_FAMILY["profile_resolution"]["registration_configured"]
_PRIORITY_POLICIES = tuple(_PRIORITY_FAMILY["policies"])


def priority_quota_policy(rubric_text, registry=None):
    """Read the Priority Rubric slot's quota registration, K00/07.

    Returns ``((p0, p1), configured, errors)`` when configured, and
    ``((), False, errors)`` when the slot explicitly selects no quota. One
    reader owns the long-lived quota truth: the profile-load Gate validates
    through it and the batch-close consumer resolves through it, so the two
    can never disagree about what the slot declares. ``Registration: None``
    leaves quota enforcement inactive. ``Configured`` requires one row for every
    registered quota class, a nonempty rationale, and values inside the
    registry's individual and joint domains so the registered remainder class
    stays reachable.
    """
    registry = registry or _SHIPPED_POLICY_REGISTRY
    family = _family(registry, "profile-priority-quota")
    resolution = family["profile_resolution"]
    section = resolution["section"]
    registration_none = resolution["registration_none"]
    registration_configured = resolution["registration_configured"]
    policies = tuple(family["policies"])
    classes = tuple(row["quota_class"] for row in policies)
    domain = family["limit_domain"]
    minimum = domain["minimum_inclusive"]
    maximum = domain["maximum_exclusive"]
    joint_maximum = domain["joint_maximum_exclusive"]
    remainder_class = resolution["remainder_class"]

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
                      heading[1] == section)
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
            "the %s section must declare `- Registration: %s` (no quota) or "
            "`- Registration: %s`" %
            (section, registration_none, registration_configured))
        return (), False, errors
    if declaration == registration_none:
        data_rows = rows[1:] if rows else []
        if data_rows:
            errors.append(
                "Registration: %s leaves active quota rows behind; remove "
                "them so the single declaration is authoritative" %
                registration_none)
        return (), False, errors
    if declaration != registration_configured:
        errors.append(
            "%s declaration %r is invalid; use `%s` or `%s`" %
            (section, declaration, registration_none,
             registration_configured))
        return (), False, errors

    values = {}
    data_rows = rows[1:] if rows else []
    for cells in data_rows:
        if len(cells) != 3 or not all(cells):
            errors.append(
                "a %s quota row must carry exactly class, maximum share, "
                "and a nonempty rationale; found %r" %
                (registration_configured, cells))
            continue
        cls = cells[0].strip("`").strip()
        if cls not in classes:
            errors.append("quota class %r is not %s" %
                          (cls, " or ".join(classes)))
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
        if not minimum <= share < maximum:
            errors.append(
                "%s maximum share must be at least %s and under %s" %
                (cls, minimum, maximum))
            continue
        values[cls] = share
    missing = sorted(set(classes) - set(values))
    if missing:
        errors.append(
            "%s must declare every quota class; missing %s" %
            (registration_configured, ", ".join(missing)))
        return (), False, errors
    joint = sum(values[quota_class] for quota_class in classes)
    if joint >= joint_maximum:
        errors.append(
            "the two quota shares sum to %.1f%%; K00/07 requires the pair to "
            "stay strictly below %s so the %s remainder class stays "
            "non-empty" % (joint, joint_maximum, remainder_class))
    return tuple(values[quota_class] for quota_class in classes), True, errors


PRIORITY_QUOTA_POLICY_IDS = frozenset(
    policy_id for policy_id, entry in POLICY_REGISTRY.items()
    if entry["domain_id"] == "percent-share-under-100")
PRIORITY_QUOTA_PROTOCOL_VERSION = \
    _PRIORITY_FAMILY["fingerprint_payload"]["protocol_version"]


def effective_priority_policy(rubric_text, registry=None):
    """Resolve the one effective quota policy and its canonical fingerprint.

    Everything an authorization decision depends on is folded into one object
    and one fingerprint: whether this optional policy is active, the registered
    policy IDs and resolved per-class values when active, the resolution
    source, and the comparison protocol version. ``Registration: None`` is an
    explicit, fingerprinted inactive policy; it never acquires hidden numeric
    defaults. An exception's baseline fingerprint binds to this object; hashing
    the rubric file alone would let the effective policy drift underneath an
    active grant.

    Returns ``(policy, fingerprint, errors)``.  ``fingerprint`` is None when
    the slot does not resolve.
    """
    registry = registry or _SHIPPED_POLICY_REGISTRY
    family = _family(registry, "profile-priority-quota")
    rows = tuple(family["policies"])
    payload_contract = family["fingerprint_payload"]
    values, configured, errors = priority_quota_policy(
        rubric_text, registry=registry)
    resolved = ({
        row["policy_id"]: values[index]
        for index, row in enumerate(rows)
    } if configured else {})
    policy = {
        "schema_version": payload_contract["schema_version"],
        "protocol_version": payload_contract["protocol_version"],
        "enabled": configured,
        "source": (payload_contract["profile_configured_source"]
                   if configured else
                   payload_contract["profile_none_source"]),
        "resolved": resolved,
    }
    if errors:
        return policy, None, errors
    payload = json.dumps(policy, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return policy, kblib.sha256_bytes(payload), errors


def effective_policy_for(policy_id, rubric_text=None, registry=None):
    """Resolve the effective policy object for one registered policy.

    One dispatcher so every consumer -- the amendment writer, the runtime
    validator, the close -- judges an exception against the same baseline
    its family defines, instead of each deciding what "the policy" means.

    Returns ``(policy, fingerprint, errors)``.  A quota policy needs the
    selected Profile's Priority Rubric bytes; a kernel-owned policy takes
    none.  An unregistered policy id resolves to nothing.
    """
    registry = registry or _SHIPPED_POLICY_REGISTRY
    records = policy_registry_records(registry)
    priority_ids = frozenset(records)
    if policy_id in priority_ids:
        if rubric_text is None:
            return None, None, [
                "%s is a Profile-configured policy; its Priority Rubric "
                "bytes are required to resolve it" % policy_id]
        return effective_priority_policy(rubric_text, registry=registry)
    return None, None, [
        "%r is not in the closed policy registry" % policy_id]


def effective_quota_ceilings(policy, exceptions, registry=None):
    """Fold configured quotas and granted exceptions into effective ceilings.

    ``policy`` is the object from :func:`effective_priority_policy`;
    ``exceptions`` is the list of currently applicable contract policy
    exceptions (the caller decides currency and scope). For an enabled policy,
    each registered class uses the largest granted exception limit when one
    exists, else the Profile-resolved value. An inactive policy has no ceiling
    to relax, so any quota exception against it is an error rather than a way
    to create an implicit quota.

    K00/07's registry-defined joint bound is judged over the effective pair,
    because a grant and the other class's configured quota partition the same
    corpus. Summing grants alone could call the pair bounded while ignoring a
    configured ceiling. This function executes that arithmetic; it does not own
    the bound.

    Returns ``(ceilings, errors)``.  ``ceilings`` maps policy_id to
    ``{"limit": number, "source": "configured" | "exception:<decision_id>"}``.
    """
    from fractions import Fraction
    registry = registry or _SHIPPED_POLICY_REGISTRY
    family = _family(registry, "profile-priority-quota")
    priority_ids = frozenset(
        row["policy_id"] for row in family["policies"])
    joint_maximum = family["limit_domain"]["joint_maximum_exclusive"]
    remainder_class = family["profile_resolution"]["remainder_class"]
    quota_exceptions = [
        entry for entry in (exceptions or [])
        if isinstance(entry, dict) and entry.get("policy_id") in priority_ids
    ]
    if not isinstance(policy, dict) or policy.get("enabled") is not True:
        errors = []
        if quota_exceptions:
            errors.append(
                "priority quota is not configured by the selected Profile; "
                "an inactive policy has no ceiling to relax")
        return {}, errors

    ceilings = {}
    # Quota family only: the joint bound is an arithmetic over corpus shares,
    # and a policy from another family has no configured share to fold in.
    for policy_id in sorted(priority_ids):
        resolved = (policy or {}).get("resolved", {}).get(policy_id)
        ceilings[policy_id] = {"limit": resolved, "source": "configured"}
    for entry in quota_exceptions:
        if not isinstance(entry, dict):
            continue
        policy_id = entry.get("policy_id")
        limit = entry.get("limit")
        if policy_id not in priority_ids:
            continue
        if isinstance(limit, bool) or not isinstance(limit, (int, float)):
            continue
        current = ceilings[policy_id]
        if (current["source"] == "configured" or
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
    if not errors and joint >= joint_maximum:
        detail = ", ".join(
            "%s=%s(%s)" % (policy_id, ceiling["limit"], ceiling["source"])
            for policy_id, ceiling in sorted(ceilings.items()))
        errors.append(
            "effective quota ceilings sum to %s%% (%s); K00/07 requires the "
            "pair to stay strictly below %s so the %s remainder class "
            "stays non-empty" %
            (float(joint), detail, joint_maximum, remainder_class))
    return ceilings, errors
