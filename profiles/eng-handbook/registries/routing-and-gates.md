## Navigation

- Profile: [[profiles/eng-handbook/profile|Eng Handbook Profile]].
- Kernel contract: [[kernel/04 Content Depth Standard|04 Content Depth Standard]].
- Quality kernel: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].

## Profile Task Routes

No profile-specific routes or Read Sets are registered. Tasks in this profile use the kernel's standard routing; the kernel must not imply any eng-handbook route as loaded, because none exists.

## Effort Tier Bindings

Additional L-tier triggers for this profile (the kernel S / M / L axis, dispute escalation, quota coupling, and acceptance rituals are unchanged):

- Runbooks for paging services: L tier — these pages are executed under incident pressure, so they receive the full single-note review.
- Escalation matrix and rollback procedure: L tier.
- Incident reviews: M tier by default.
- Glossary stubs in `Shared/` and alert-catalog rows: S tier.

## Extension Gates

None registered. The kernel's batch gates, note gates, and Terminal Audit apply as-is. The expression-layer synchronization gates are `not_applicable` for this profile because [[profiles/eng-handbook/expression-layer|Expression Layer]] registers no artifacts.
