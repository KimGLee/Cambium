# Source Policy

Implements the `Source Policy` slot for `eng-handbook`. This policy tightens the kernel's source rules for an internal-systems domain; all kernel source invariants (hierarchy, four-dimension judgment, ten-element provenance, `unknown`, promotion gate) remain in force.

## Named Primary Sources

Internal, in descending authority for claims about the team's own systems:

1. **Running code and configuration** — the repository at the commit currently deployed; deployment manifests; alert definitions as configured.
2. **ADRs (architecture decision records)** — canonical for *why* a design decision was made.
3. **Incident reviews** — canonical for what actually failed and what the recovery was.
4. **Dashboards and metrics** — canonical for quantitative claims (latency, error rates, capacity), always with a captured time window.

External:

5. **Vendor and upstream documentation** — canonical for the behavior of third-party components, subordinate to observed behavior when the two conflict (record the conflict, do not average it).

## Scan And Verification Entry Points

- Claims about current behavior are verified against source 1 (code/config at the deployed commit), not against memory or older pages.
- Quantitative claims cite the dashboard and the time window; a number without a window is recorded as `unknown` provenance.

## Applicability Scope And Priority Triggers

- A new incident review is a priority trigger: affected Services and Operations pages enter the next batch as update candidates.
- A vendor major-version upgrade triggers re-verification of every page citing that vendor's documentation.

## Comparison And Gap Recording

- When code and an ADR disagree, the page records both, marks the claim `contested`, and files the discrepancy — it does not pick a winner silently.
- Systems with no ADR coverage are recorded as provenance gaps, not backfilled with inferred rationale presented as decision history.
