"""Explicit interview answers applied to the current empty Profile template.

The template stays an unanswered candidate. This fixture is a confirmed
home-lab test scenario layered onto the shared minimal typed answer object;
it never learns answers from Markdown placeholders or adopts the Profile.
"""

from pathlib import Path

import Tools.governance.profile.profile_codec as profile_codec
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.platform.common.kblib as kblib
from Tools.tests.support.profile_contract_fixture import (
    install_profile_package, minimal_profile_document,
)


REPOSITORY = Path(__file__).resolve().parents[3]
TEMPLATE = REPOSITORY / "profiles" / "_template"
ORIENTATION = ("README.md",)
SENTINEL = "TODO(profile)"
PROFILE_ID = "fill-e2e"
SCAN_CONFIG = {
    "residual_scan_config_version": 1,
    "allowed_roots": ["Notes/Daily Log"], "excluded_roots": [],
    "frontmatter_match": {"field": "type", "values": ["daily-log"]},
    "heading_match": {
        "any": ["Daily Log Entry"], "combination": ["Scratch", "To Sort", "Loose Ends"],
        "minimum_distinct": 2},
    "mandated_headings": ["Daily Log Entry", "Scratch", "To Sort", "Loose Ends"],
}


def template_answer_document(profile_id=PROFILE_ID):
    """Return the explicit home-lab answers used by the template E2E."""
    document = minimal_profile_document(profile_id)
    slots = document["slots"]
    scope = slots["profile-scope"]
    scope["goal"] = {
        "statement": "Keep one maintainer's home-lab service notes findable, current, and safe to act on a year later.",
        "readers": ["The single maintainer who runs the lab."]}
    scope["content_priority_factors"] = [
        {"rank": 1, "factor": "The note is needed while something is broken."}]
    scope["logical_architecture"] = [{
        "layer_id": "L-MAIN", "directories": ["Notes"],
        "responsibility": "Own every canonical note, including dated scratch entries under Notes/Daily Log."}]
    scope["knowledge_spine"] = {
        "organizing_logic": "One page per service or recurring procedure; each page names what it depends on.",
        "locator": "The depends_on sentence in the page's opening paragraph."}
    for row in scope["placement_layer_registrations"]:
        if row["binding"]["kind"] != "predicate":
            row["binding"]["layer_id"] = "L-MAIN"
    scope["new_page_placement_rule"] = [
        {"predicate": "The page is a dated entry whose title starts with an ISO date.",
         "layer_id": "L-MAIN", "fallback": False},
        {"predicate": "Otherwise", "layer_id": "L-MAIN", "fallback": True}]
    scope["terminology_structure"] = [{
        "term_class": "Service names used in more than one note.", "layer_id": "L-MAIN",
        "boundary": "Included when the name is ambiguous across vendors; excluded when upstream documentation is the only reader-facing form."}]
    scope["foundation_depth_requirements"] = [{
        "page_class": "A page describing a service the maintainer must restore.",
        "predicate": "The page names the service, its current version, where its configuration backup lives, and the one command used to verify it is working."}]
    slots["language-contract"]["language_routing"]["body_language"] = "English (en)."
    slots["source-policy"]["source_authority"] = [{
        "rank": 1, "source_id": "maintainer-observation",
        "location": "What the maintainer observed on the running service itself.",
        "claim_class": "The configuration and version actually running in the lab.",
        "version_policy": "Retrieval date recorded in the note's opening paragraph."}]
    slots["source-policy"]["verification_entry_points"] = [{
        "claim_class": "A claim about what is currently running.",
        "source_id": "maintainer-observation",
        "verification": "Log in to the service and read the status screen named in the note.",
        "freshness": "180 days."}]
    slots["source-policy"]["staleness_triggers"] = [{
        "event": "A service is upgraded or replaced.",
        "affected_scope": "Every claim on that service's page about versions, defaults, or verification screens."}]
    roles = slots["role-registry"]
    roles["process_roles"] = {
        "proposer": profile_id + "-agent", "gatekeeper": profile_id + "-maintainer",
        "executor": profile_id + "-agent", "stopper": profile_id + "-maintainer"}
    roles["knowledge_host"] = {"host": "Markdown repository tree", "ui": "Headless"}
    scan = slots["registered-scan-registry"]["scan_registrations"][0]
    scan.update({
        "scan_id": profile_id + "-scratch-residuals",
        "scope": "Run from the vault root; the profile-owned configuration accepts Notes/Daily Log as the only root where dated-scratch structure belongs.",
        "candidate_predicate": "A Markdown file outside Notes/Daily Log is a candidate when it declares type: daily-log, carries a Daily Log Entry heading, or carries at least two distinct dated-scratch sorting headings. Candidate-only; adjudication belongs to " + profile_id + "-residual-disposition."})
    return document


def fill_profile(profile, profile_id=PROFILE_ID):
    """Apply this fixture's confirmed answers to a copied empty template."""
    profile = Path(profile)
    manifest = profile / profile_layout_contract.PROFILE_MANIFEST_NAME
    candidate = profile_codec.loads_profile(manifest.read_bytes())
    if candidate.get("slots") not in ({}, None):
        raise AssertionError("fixture filling requires an unanswered template")
    if candidate.get("profile_id") not in (None, profile_id):
        raise AssertionError("fixture identity differs from the candidate")
    install_profile_package(
        profile, profile_id, document=template_answer_document(profile_id))
    (profile / "scan-configs/residual-scan.yaml").write_text(
        kblib.canonical_yaml(SCAN_CONFIG), encoding="utf-8")
    (profile / "policies/residual-disposition.md").write_text(
        "# Residual Disposition\n\n"
        "The registered scan reports canonical notes that still carry dated-scratch "
        "structure outside Notes/Daily Log. Each candidate is resolved one of two "
        "ways, recorded on the candidate page: the scratch material is moved into "
        "the dated entry that owns it, or the page states why that structure is "
        "the canonical form for this note.\n", encoding="utf-8")
    return profile


def fill_scaffolded_profile(profile, profile_id=PROFILE_ID):
    """Apply exactly the same answers after mechanical candidate creation."""
    profile = Path(profile)
    candidate = profile_codec.loads_profile(
        (profile / profile_layout_contract.PROFILE_MANIFEST_NAME).read_bytes())
    if candidate != {"schema_version": 1, "profile_id": profile_id, "slots": {}}:
        raise AssertionError("scaffolder must bind identity without answering slots")
    return fill_profile(profile, profile_id)


__all__ = [
    "ORIENTATION", "PROFILE_ID", "SCAN_CONFIG", "SENTINEL", "TEMPLATE",
    "fill_profile", "fill_scaffolded_profile", "template_answer_document",
]
