# Source Policy

Implements the `Source Policy` slot.

TODO(profile) — fill in the sections below, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

Which sources this knowledge base treats as authoritative, in what order, how a claim gets verified against them, and what happens when two sources disagree. The kernel owns the machinery of source handling; it cannot know what counts as a primary source in your domain.

You may tighten the kernel's source rules. You may not weaken or replace them. Specifically, the following remain in force regardless of what you write here: the source hierarchy, the four-dimension judgment of authority, evidence role, applicability, and bias, the requirement that independent sources be genuinely independent and comparable, the ten-element provenance record, the `unknown` marking for missing provenance, source quality assessment, and the promotion gate.

## Named Primary Sources

TODO(profile) — list this profile's authoritative sources in descending authority, and state what each one is canonical *for*. A source is rarely canonical for everything: a decision record may be canonical for why a choice was made while telling you nothing reliable about current behavior.

Name them concretely. "Official documentation" is not a source; a specific document set, repository, register, or dataset is.

TODO(profile) — state where external or third-party sources sit relative to internal ones, and what happens when an external source contradicts direct observation. The kernel-consistent handling is to record the conflict rather than average the two into a claim neither source supports.

## Scan And Verification Entry Points

TODO(profile) — state how a claim is checked: which source a verifier reads, and what they read it at. For anything versioned or time-varying, name the pin — a commit, an edition, a revision date, a captured time window. A quantitative claim without a window has unknown provenance and must be recorded as `unknown` rather than passed through.

## Applicability Scope And Priority Triggers

TODO(profile) — state which events make existing pages stale and pull them into the next batch as update candidates. Every domain has these: a new release, a regulation change, a retraction, a superseding edition, a post-incident finding.

TODO(profile) — state which parts of the vault each trigger reaches, so the retargeting is bounded rather than a vault-wide re-review.

## Comparison And Gap Recording

TODO(profile) — state what happens when two sources of comparable authority disagree. The kernel-consistent handling is to record both, mark the claim `contested`, and file the discrepancy — not to pick a winner silently.

TODO(profile) — state how uncovered areas are recorded. A subject with no authoritative source is a provenance gap and is recorded as one; it is not backfilled with inference presented as sourced fact.

## Provenance Extensions

TODO(profile) — list any provenance elements this profile requires beyond the kernel's ten, or write that it requires none. Extensions here tighten the record; they cannot remove a kernel element or make one optional.
