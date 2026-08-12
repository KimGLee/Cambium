# Registered Scan Registry

Interface: [Registered Scan Registry slot](../../README.md#registered-scan-registry-slot)

The interface requires one real residual-content verifier; a profile cannot
opt out. The common archetype: one class of structured content belongs only
under one root (dated scratch entries, derived cards, generated digests), and
the scan reports that structure leaking anywhere else. Derive the matchers
from content that really occurs in this corpus; on an empty corpus, declare
them from the page structure this profile registers and have the first batch
create the page that carries them. Either way the configuration must end up
repository-backed: the production scan requires at least one Markdown file the
matchers recognise, so a generic static default is impossible by design. The
positive control checks something narrower — that the matchers and
`mandated_headings` agree — and passes on an empty repository. Fill
[the profile-owned scan configuration](../scan-configs/residual-scan.yaml)
and bind `Tools/check_residual_content.py` below with the same Stable Scan ID
passed through `--scan-id`. Materialize the command's `--config` argument with
this Profile's repository-relative path. The executable remains under
`Tools/`; the configuration is a `profile-load` dependency and cannot point at
the template, another Profile, or a repository-root fallback.

## Scan Registrations

| Stable Scan ID | Activation role | Whole-corpus scope/root | Deterministic verifier command/path | Candidate predicate/boundary | Judgment Item ID reference |
|---|---|---|---|---|---|
| TODO(profile) | `K12/09 item 6 — residual-content scan` | TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) |
