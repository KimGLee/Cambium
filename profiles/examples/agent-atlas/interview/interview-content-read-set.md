---
type: profile-read-set
route_id: P:agent-atlas:interview-content
supplements: R05
---
# Agent Atlas Interview Content Read Set

## Purpose

Use this supplemental Read Set when creating, revising, migrating, or reviewing Agent Systems Atlas Interview Cards, Roadmaps, or Cheat Sheets. It supplies the concrete Atlas artifact rules alongside [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer Read Set]] and never replaces the R05 kernel floor.

## Start

After R05 has loaded [[kernel/Read Sets/R01 Core Bootstrap Read Set|R01 Core Bootstrap]] and the selected profile bindings, read:

- [[profiles/examples/agent-atlas/interview/interview-content-standard|Interview Content Standard]];
- [[profiles/examples/agent-atlas/interview/card-granularity-and-readiness|Card Granularity And Readiness]];
- [[profiles/examples/agent-atlas/interview/card-structure-and-answer-levels|Card Structure And Answer Levels]];
- the selected profile's [[profiles/examples/agent-atlas/language-contract|Language Contract]].

Resolve the target canonical owners, Card category, `interview_status`, target path under `Interview Preparation/`, and applicable acceptance gate before writing.

## Triggered

- System Design Card or Project Deep Dive Card: read [[profiles/examples/agent-atlas/interview/system-and-project-deep-dive|System And Project Deep Dive]].
- Roadmap or Cheat Sheet work: read [[profiles/examples/agent-atlas/interview/roadmap-and-cheat-sheet|Roadmap And Cheat Sheet]].
- Readiness promotion or profile-wide interview review: read [[profiles/examples/agent-atlas/interview/interview-review-and-acceptance|Interview Review And Acceptance]] and the profile's [[profiles/examples/agent-atlas/registries/routing-and-gates|Routing And Gate Registry]].
- Migration or residual-content disposition: additionally read [[kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance|K11/07 Expression Migration Audit And Acceptance]] and combine [[kernel/Read Sets/R06 Migration and Refactor Read Set|R06 Migration And Refactor]].
- Work spanning multiple Cards or a complete domain: combine [[kernel/Read Sets/R03 Module Build Read Set|R03 Module Build]].

## Gate

Before an Atlas Interview Card closes, run the applicable R05 gates and [[profiles/examples/agent-atlas/interview/interview-review-and-acceptance#Interview Card Review|Interview Card Review]]. Before `interview_status` becomes `interview-ready`, also pass [[profiles/examples/agent-atlas/interview/interview-review-and-acceptance#Interview Readiness Acceptance|Interview Readiness Acceptance]] under the profile-registered authority and gate.

Migration work additionally resolves every registered residual candidate under [[profiles/examples/agent-atlas/interview/interview-review-and-acceptance#Residual-content Disposition|Residual-content Disposition]]. Roadmap and Cheat Sheet work closes only when its links resolve to current canonical owners and applicable Cards.
