## Navigation

- Profile: [[profiles/examples/eng-handbook/profile|Eng Handbook Profile]].
- Kernel contract: [[kernel/04 Content Depth/03 Process and Flow Structure|Process And Flow Structure]].

## Process And Flow Role Bindings

- `proposer` → `Authoring engineer`: drafts pages, proposes structure changes, and nominates priority grants.
- `gatekeeper` → `Reviewer plus CI`: a second engineer reviews content; deterministic checks run in CI and gate the merge.
- `executor` → `Merge automation`: the CI/CD pipeline that lands approved changes into the handbook repository.
- `stopper` → `On-call lead`: approves, rejects, or takes over changes to P0 operational pages, and adjudicates escalations.

These are profile name bindings, not a requirement for four distinct parties; one party may hold multiple roles. A solo maintainer may hold `proposer` and `executor` while CI holds `gatekeeper` and a designated senior engineer holds `stopper` — the four-question floor still applies.

## Extension Roles

- `incident-scribe`: during an incident, captures the timeline that later becomes the incident review. This role feeds `Source Policy` source 3; it carries no gate authority.

## Knowledge Host Role Bindings

- `knowledge-host` → the handbook's git repository (Markdown vault).
- `knowledge-host UI` → the team's rendered docs site or Markdown editor of choice.

These bindings supply eng-handbook deployment values only; the kernel references the host through the stable role and never depends on a product name.
