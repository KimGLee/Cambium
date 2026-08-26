#!/usr/bin/env python3
"""Canonical adopter Standards state.

Kernel Markdown owns rules.  This file format owns one adopter's current
Standards/Profile identity.  Adoption history remains append-only receipt
evidence under ``.cambium/receipts/standards-adoptions.jsonl``.

The public Cambium distribution intentionally carries no state file.  An
adopter creates it through the initial R09 adoption transaction; ordinary
runtime consumers fail closed when it is absent.
"""

import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import profile_layout_contract
import runtime_paths
import runtime_state_contract


STATE_PATH = runtime_paths.ACTIVE_STANDARDS_PATH
SCHEMA_VERSION = 1
STATE_FIELDS = frozenset((
    "schema_version", "state_revision", "standards_version", "status",
    "effective_date", "selected_profile_manifest",
    "latest_adoption_receipt", "upstream_source_ref",
    "upstream_revision_id",
))
SHA_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
RECEIPT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def state_errors(state, *, allow_initial_receipt_null=False):
    """Return closed-schema errors for one parsed state mapping."""
    if not isinstance(state, dict):
        return ["Standards state top level must be a mapping"]
    errors = []
    missing = sorted(STATE_FIELDS - set(state))
    extra = sorted(set(state) - STATE_FIELDS)
    if missing:
        errors.append("Standards state misses field(s): %s" %
                      ", ".join(missing))
    if extra:
        errors.append("Standards state has unsupported field(s): %s" %
                      ", ".join(extra))
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append("Standards state schema_version must be %d" %
                      SCHEMA_VERSION)
    revision = state.get("state_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        errors.append("Standards state state_revision must be an integer >= 1")
    for field in runtime_state_contract.RUNTIME_STANDARDS_IDENTITY_FIELDS:
        if not _nonempty(state.get(field)):
            errors.append("Standards state %s must be non-empty" % field)
    if state.get("status") != "approved":
        errors.append("Standards state status must be approved")
    date = state.get("effective_date")
    if not _nonempty(date):
        errors.append("Standards state effective_date must be YYYY-MM-DD")
    else:
        try:
            parsed = datetime.date.fromisoformat(date)
        except ValueError:
            parsed = None
        if parsed is None or parsed.isoformat() != date:
            errors.append("Standards state effective_date must be YYYY-MM-DD")
    manifest = state.get("selected_profile_manifest")
    if _nonempty(manifest):
        try:
            profile_layout_contract.\
                validate_selectable_profile_manifest_path(manifest)
        except profile_layout_contract.ProfileLayoutError as exc:
            errors.append(
                "Standards state selected_profile_manifest is invalid: %s" %
                exc)
    receipt = state.get("latest_adoption_receipt")
    if receipt is None:
        if not allow_initial_receipt_null:
            errors.append("Standards state latest_adoption_receipt must be non-null")
    elif not _nonempty(receipt) or not RECEIPT_ID_RE.fullmatch(receipt):
        errors.append("Standards state latest_adoption_receipt is invalid")
    upstream_source = state.get("upstream_source_ref")
    upstream_revision = state.get("upstream_revision_id")
    if (upstream_source is None) != (upstream_revision is None):
        errors.append(
            "Standards state upstream_source_ref and upstream_revision_id "
            "must be both null or both non-null")
    if upstream_source is not None and not _nonempty(upstream_source):
        errors.append("Standards state upstream_source_ref must be non-empty")
    if upstream_revision is not None and not _nonempty(upstream_revision):
        errors.append("Standards state upstream_revision_id must be non-empty")
    return errors


def parse(text, *, allow_initial_receipt_null=False):
    state = kblib.parse_yaml_subset(text)
    errors = state_errors(
        state, allow_initial_receipt_null=allow_initial_receipt_null)
    return state, errors


def canonical_text(state, *, allow_initial_receipt_null=False):
    errors = state_errors(
        state, allow_initial_receipt_null=allow_initial_receipt_null)
    if errors:
        raise ValueError("; ".join(errors))
    return kblib.canonical_yaml(state)


def snapshot(root, *, override_text=None, allow_initial_receipt_null=False):
    """Return ``(state, view, errors)`` from exact state bytes.

    ``override_text`` is for an in-memory transaction after-image.  It never
    falls back to K00/03: legacy Markdown is migration input, not authority.
    """
    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    if override_text is None:
        try:
            snap = kblib.repository_file_snapshot(
                root, STATE_PATH, singly_linked=True)
            text = snap.read_text()
            digest = snap.sha256
        except (OSError, UnicodeError, ValueError) as exc:
            return None, None, [
                "active Standards state %s is unsafe, absent, or unreadable: %s"
                % (STATE_PATH, exc)]
    else:
        if not isinstance(override_text, str):
            return None, None, ["active Standards state override must be text"]
        text = override_text
        digest = kblib.sha256_bytes(text)
    try:
        state, errors = parse(
            text, allow_initial_receipt_null=allow_initial_receipt_null)
    except (TypeError, ValueError, kblib.YamlSubsetError) as exc:
        return None, None, ["active Standards state is malformed: %s" % exc]
    if errors:
        return None, None, errors
    view = {
        "active_standards_path": STATE_PATH,
        "active_standards_sha256": digest,
        "standards_version": state["standards_version"],
        "selected_profile_manifest": state["selected_profile_manifest"],
        "standards_status": state["status"],
        "standards_effective_date": state["effective_date"],
        "standards_state_revision": state["state_revision"],
        "latest_adoption_receipt": state["latest_adoption_receipt"],
        "upstream_source_ref": state["upstream_source_ref"],
        "upstream_revision_id": state["upstream_revision_id"],
    }
    return state, view, []


def next_state(before, *, standards_version, effective_date,
               selected_profile_manifest, latest_adoption_receipt,
               upstream_source_ref, upstream_revision_id):
    """Construct the next canonical current-state record."""
    revision = 1 if before is None else before["state_revision"] + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "state_revision": revision,
        "standards_version": standards_version,
        "status": "approved",
        "effective_date": effective_date,
        "selected_profile_manifest": selected_profile_manifest,
        "latest_adoption_receipt": latest_adoption_receipt,
        "upstream_source_ref": upstream_source_ref,
        "upstream_revision_id": upstream_revision_id,
    }
