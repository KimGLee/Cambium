"""Exact K12/02 changed-page predicates that already have machine meaning.

The active rules and routing live in the Kernel changed-scope registry.  This
module evaluates only byte-level predicates whose acceptance boundary is
already fixed.  The separate K12/02 machine contract lists prose obligations
that remain unadmitted because no unique predicate exists; this module never
fills those gaps by choosing its own grammar, threshold, compiler, or renderer.
"""

from copy import deepcopy
from types import MappingProxyType

import markdown_structure_checks


TOOL = "changed_scope_rendering_checks"
TOOL_VERSION = "1.0.0"

FENCE_RULE_ID = "k12-02-level0-fence-closure"
FENCE_CHECK_ID = "changed_scope_level0_fence_closure"
MERMAID_RULE_ID = "k12-02-level0-mermaid-fence-closure"
MERMAID_CHECK_ID = "changed_scope_level0_mermaid_fence_closure"
TABLE_RULE_ID = "k12-02-level1-markdown-table-static"
TABLE_CHECK_ID = "changed_scope_level1_markdown_table_static"

CHECKS_BY_RULE_ID = MappingProxyType({
    FENCE_RULE_ID: FENCE_CHECK_ID,
    MERMAID_RULE_ID: MERMAID_CHECK_ID,
    TABLE_RULE_ID: TABLE_CHECK_ID,
})

_RESULT_FIELDS = frozenset((
    "check_id", "rule_id", "scope", "result", "diagnostics", "metrics",
))
_SCOPE_FIELDS = frozenset(("kind", "targets"))
_DIAGNOSTIC_FIELDS = frozenset((
    "diagnostic_id", "target", "field", "expected", "actual",
))


def _diagnostic(diagnostic_id, target, field, expected, actual):
    return {
        "diagnostic_id": diagnostic_id,
        "target": target,
        "field": field,
        "expected": deepcopy(expected),
        "actual": deepcopy(actual),
    }


def _result(rule_id, target, diagnostics, metrics):
    diagnostics = sorted(
        diagnostics,
        key=lambda row: (row["target"], row["field"], row["diagnostic_id"]),
    )
    value = {
        "check_id": CHECKS_BY_RULE_ID[rule_id],
        "rule_id": rule_id,
        "scope": {"kind": "markdown-page", "targets": [target]},
        "result": "pass" if not diagnostics else "fail",
        "diagnostics": diagnostics,
        "metrics": deepcopy(metrics),
    }
    return validate_check_result(value)


def validate_check_result(value):
    if not isinstance(value, dict) or set(value) != _RESULT_FIELDS:
        raise ValueError("rendering check result fields are not closed")
    rule_id = value.get("rule_id")
    if rule_id not in CHECKS_BY_RULE_ID:
        raise ValueError("rendering check result has unknown rule_id")
    if value.get("check_id") != CHECKS_BY_RULE_ID[rule_id]:
        raise ValueError("rendering check result identity differs from rule")
    scope = value.get("scope")
    if (not isinstance(scope, dict) or set(scope) != _SCOPE_FIELDS or
            scope.get("kind") != "markdown-page" or
            not isinstance(scope.get("targets"), list) or
            len(scope["targets"]) != 1 or
            not isinstance(scope["targets"][0], str) or
            not scope["targets"][0]):
        raise ValueError("rendering check result scope is invalid")
    diagnostics = value.get("diagnostics")
    if not isinstance(diagnostics, list):
        raise ValueError("rendering check diagnostics must be a list")
    for index, row in enumerate(diagnostics):
        if not isinstance(row, dict) or set(row) != _DIAGNOSTIC_FIELDS:
            raise ValueError(
                "rendering diagnostic %d fields are not closed" % index)
        for field in ("diagnostic_id", "target", "field"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ValueError(
                    "rendering diagnostic %d has invalid %s" %
                    (index, field))
    if value.get("result") != ("pass" if not diagnostics else "fail"):
        raise ValueError("rendering check result disagrees with diagnostics")
    if not isinstance(value.get("metrics"), dict):
        raise ValueError("rendering check metrics must be a mapping")
    return value


def level0_fence_closure(text, target):
    blocks, unclosed = markdown_structure_checks.fence_scan(text)
    diagnostics = []
    if unclosed is not None:
        diagnostics.append(_diagnostic(
            "markdown-fence-unclosed", "%s:%d" % (target, unclosed["line"]),
            "fence", "matching-closing-fence", unclosed["marker"]))
    return _result(FENCE_RULE_ID, target, diagnostics, {
        "closed_fence_count": len(blocks),
        "unclosed_fence_count": 1 if unclosed is not None else 0,
    })


def level0_mermaid_fence_closure(text, target):
    blocks, unclosed = markdown_structure_checks.fence_scan(text)
    mermaid_blocks = [row for row in blocks if row["language"] == "mermaid"]
    diagnostics = []
    if unclosed is not None and unclosed["language"] == "mermaid":
        diagnostics.append(_diagnostic(
            "mermaid-fence-unclosed",
            "%s:%d" % (target, unclosed["line"]), "mermaid_fence",
            "matching-closing-fence", unclosed["marker"]))
    return _result(MERMAID_RULE_ID, target, diagnostics, {
        "closed_mermaid_fence_count": len(mermaid_blocks),
        "unclosed_mermaid_fence_count": (
            1 if unclosed is not None and
            unclosed["language"] == "mermaid" else 0),
    })


def level1_markdown_table_static(text, target):
    tables = markdown_structure_checks.table_scan(text)
    diagnostics = []
    for table in tables:
        table_target = "%s:%d" % (target, table["line"])
        if not table["delimiter_valid"]:
            diagnostics.append(_diagnostic(
                "table-delimiter-invalid", table_target, "delimiter_row",
                "three-or-more-hyphens-per-column", "invalid"))
            continue
        for offset, actual in enumerate(table["row_columns"]):
            if actual != table["expected_columns"]:
                diagnostics.append(_diagnostic(
                    "table-column-count-mismatch",
                    "%s:%d" % (target, table["line"] + offset), "columns",
                    table["expected_columns"], actual))
        for line in table["unescaped_alias_lines"]:
            diagnostics.append(_diagnostic(
                "table-wiki-alias-pipe-unescaped", "%s:%d" % (target, line),
                "wiki_alias_separator", "\\|", "|"))
    return _result(TABLE_RULE_ID, target, diagnostics, {
        "table_count": len(tables),
        "invalid_delimiter_count": sum(
            1 for row in tables if not row["delimiter_valid"]),
        "column_mismatch_count": sum(
            1 for row in diagnostics
            if row["diagnostic_id"] == "table-column-count-mismatch"),
        "unescaped_alias_count": sum(
            1 for row in diagnostics
            if row["diagnostic_id"] == "table-wiki-alias-pipe-unescaped"),
    })


RUNNERS_BY_RULE_ID = MappingProxyType({
    FENCE_RULE_ID: level0_fence_closure,
    MERMAID_RULE_ID: level0_mermaid_fence_closure,
    TABLE_RULE_ID: level1_markdown_table_static,
})

PROFILE_RENDERING_STATES = frozenset((
    "not-applicable", "contract-gap", "ready",
))


class ProfileRenderingContractGap(ValueError):
    """A selector-owned construct has no valid typed Profile contract."""

    def __init__(self, targets):
        normalized = []
        for target, constructs in targets:
            normalized.append({
                "target": str(target),
                "constructs": sorted(set(str(value) for value in constructs)),
            })
        self.targets = tuple(sorted(
            normalized, key=lambda row: row["target"]))
        super().__init__(
            "contract-gap/HOLD: Profile Rendering Contract is missing for "
            "%s" % "; ".join("%s [%s]" % (
                row["target"], ", ".join(row["constructs"]))
                for row in self.targets))


def selector_owned_profile_rendering_constructs(text):
    """Return constructs whose applicability already has a machine owner.

    This is a trigger classifier, not a rendering verdict.  The existing
    K12/02 base contract uniquely identifies Mermaid fences and outer-pipe
    Markdown tables, so those same selectors may route a future Profile
    Rendering Contract.  Formula, image, embed, asset, and callout syntax has
    no such typed construct selector yet and is deliberately absent.  A Tool
    must not turn a dollar sign, an ad-hoc regular expression, or a filename
    suffix into a blocking applicability decision.
    """
    constructs = []
    if markdown_structure_checks.has_mermaid_fence(text):
        constructs.append("mermaid-fence")
    if markdown_structure_checks.has_markdown_table(text):
        constructs.append("outer-pipe-markdown-table")
    return tuple(sorted(set(constructs)))


def selector_owned_profile_rendering_contract_state(
        text, *, contract_is_bound_and_valid):
    """Return the required three-state routing decision.

    The boolean is supplied only by a future typed Profile Rendering Contract
    validator.  This module does not inspect an ad-hoc Profile field and cannot
    manufacture validity from file presence.  ``not-applicable`` is scoped to
    the selector-owned constructs returned above; it makes no claim about
    formula, image, embed, asset, or callout syntax that lacks an owner.
    """
    if not isinstance(contract_is_bound_and_valid, bool):
        raise ValueError("contract validity must be a typed boolean result")
    constructs = selector_owned_profile_rendering_constructs(text)
    if not constructs:
        state = "not-applicable"
    elif contract_is_bound_and_valid:
        state = "ready"
    else:
        state = "contract-gap"
    if state not in PROFILE_RENDERING_STATES:
        raise AssertionError("Profile rendering state drifted")
    return {"state": state, "constructs": list(constructs)}


def profile_rendering_contract_gap_targets(
        pages, *, contract_is_bound_and_valid):
    """Return exact current pages that resolve to ``contract-gap``.

    ``pages`` contains ``(repository-relative path, current text)`` pairs.
    This function owns only routing state.  A ``ready`` result still requires
    the Profile-selected deterministic capability to execute and prove its
    own acceptance contract.
    """
    gaps = []
    for target, text in pages:
        if not isinstance(target, str) or not target or not isinstance(
                text, str):
            raise ValueError(
                "Profile rendering targets require path and text strings")
        decision = selector_owned_profile_rendering_contract_state(
            text,
            contract_is_bound_and_valid=contract_is_bound_and_valid)
        if decision["state"] == "contract-gap":
            gaps.append((target, tuple(decision["constructs"])))
    return tuple(sorted(gaps))


def require_profile_rendering_contract_state(
        pages, *, contract_is_bound_and_valid):
    """Fail closed on gaps without treating that refusal as evidence."""
    gaps = profile_rendering_contract_gap_targets(
        pages,
        contract_is_bound_and_valid=contract_is_bound_and_valid)
    if gaps:
        raise ProfileRenderingContractGap(gaps)
    return True


__all__ = [
    "CHECKS_BY_RULE_ID", "FENCE_CHECK_ID", "FENCE_RULE_ID",
    "MERMAID_CHECK_ID", "MERMAID_RULE_ID", "RUNNERS_BY_RULE_ID",
    "TABLE_CHECK_ID", "TABLE_RULE_ID", "TOOL", "TOOL_VERSION",
    "ProfileRenderingContractGap",
    "level0_fence_closure", "level0_mermaid_fence_closure",
    "level1_markdown_table_static",
    "profile_rendering_contract_gap_targets",
    "require_profile_rendering_contract_state",
    "selector_owned_profile_rendering_constructs",
    "selector_owned_profile_rendering_contract_state",
    "PROFILE_RENDERING_STATES",
    "validate_check_result",
]
