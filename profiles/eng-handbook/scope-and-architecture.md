# Scope And Architecture

Implements the `Profile Scope` slot for `eng-handbook`.

## Goal

Build and maintain the internal engineering handbook of a product team: the knowledge base a working engineer — especially the on-call engineer — reaches for first. Success is measured by whether an engineer can answer "how does this service work, why is it built this way, and what do I do when it breaks" without paging a colleague.

## Content Priority Factors

1. Incident-critical operational knowledge: runbooks, failure modes, recovery paths for production services.
2. Core service architecture: what each service does, its dependencies, its data flows, and the reasoning behind its design decisions.
3. Team process knowledge: deployment, review, release, and escalation procedures.
4. Onboarding foundations: what a new engineer must understand in the first month.

## Exclusion List

- Secrets, credentials, tokens, and any material governed by the security team's access policy — link to the secret manager or policy page instead.
- Personal performance or HR material.
- Product roadmap debate and meeting minutes without distilled decisions — only recorded decisions (ADRs) enter the handbook.
- Vendor marketing content — vendor material enters only through `Source Policy`.

## Logical Architecture

Four layers, from stable to volatile:

| Layer | Directory | Content | Typical volatility |
|---|---|---|---|
| Foundations | `Foundations/` | Concepts the stack is built on: the runtime model, storage engines, queueing, consistency trade-offs | slow / stable |
| Services | `Services/` | One section per production service: purpose, architecture, dependencies, data model, design decisions | slow |
| Operations | `Operations/` | Runbooks, dashboards, alert catalogs, deployment and rollback procedures, incident reviews | fast |
| Team | `Team/` | Onboarding paths, engineering conventions, review and release process, escalation matrix | slow |

## Knowledge Spine

The spine is the **incident lifecycle**: detect → diagnose → mitigate → recover → learn. Every Operations page states where it sits on this spine; every Services page links to the Operations pages that cover its failure modes; every incident review closes the loop by feeding corrections back into Services and Foundations pages.

## Foundation Depth Requirements

Foundations pages must explain the mechanism, not just the team's usage. A page on the message queue explains delivery semantics, ordering guarantees, and what breaks under partition — not only which topics the team uses. A Foundations page compressed into a usage note fails Depth review.

## Production System Reasoning Applicability

Services pages must carry design reasoning: the constraint that forced the decision, the alternatives rejected, and the failure modes the current design accepts. "It uses PostgreSQL" is inventory; "it uses PostgreSQL because the write pattern needs transactional integrity across three tables, at the accepted cost of manual shard management past N tenants" is knowledge.

## Directory Layout

Physical tree of the handbook vault:

```
Engineering Handbook/
├── Overview.md
├── Foundations/
├── Services/
│   └── <service-name>/
├── Operations/
│   ├── Runbooks/
│   ├── Alerts/
│   └── Incident Reviews/
├── Team/
└── Shared/
```

### Shared Layer Registration

`Shared/` is this profile's registered shared-layer directory: cross-cutting terms and concepts referenced by two or more layers (for example "circuit breaker", "SLO", "blue-green deployment") live here once, with `scope: shared`, and are linked from every usage site. Duplicating a shared concept inside a service section is a conservation violation handled by the kernel's split and duplication policy.

### New Page Placement Rule

Placement is decided by the question the page answers, in this order:

1. "What do I do right now when X breaks?" → `Operations/Runbooks/`.
2. "How and why is service X built this way?" → `Services/<service-name>/`.
3. "How does the underlying technology work?" → `Foundations/`.
4. "How does the team work?" → `Team/`.
5. Referenced from two or more of the above → `Shared/`.

A page that answers more than one question is split along these lines, not placed in both.
