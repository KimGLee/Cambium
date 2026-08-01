# Priority Rubric

Implements the `Priority Rubric` slot for `eng-handbook`. Consumes the kernel-fixed P0 / P1 / P2 axis; this file defines grant criteria only.

## P0 Grant Criteria

A page is P0 when it is on the critical path of an active incident response:

- Runbooks and recovery procedures for services with a paging alert.
- Architecture pages for services whose failure pages a human.
- The escalation matrix and the deployment rollback procedure.

Readiness bar for P0: **the on-call engineer can execute the page at 3am, unaided, without contacting the author.** A P0 runbook that requires tribal knowledge to interpret fails acceptance regardless of its coverage score.

## P1 Grant Criteria

A page is P1 when an engineer needs it within a normal working week:

- Architecture and data-model pages for non-paging services.
- Deployment, review, and release process pages.
- Foundations pages for technologies in active production use.
- Onboarding-path pages for the first month.

## P2 Default

Everything else defaults to P2: historical incident reviews past their learning window, Foundations pages for technologies under evaluation, glossary stubs, convenience aggregations.

## Quotas And Overrides

This profile adopts the kernel default quotas (P0 ≤ 15%, P1 ≤ 35%) via `Execution Default Overrides` in the manifest. If the paging surface grows to where P0-qualifying pages exceed the quota, the correct response is to tighten the paging alert set or raise the quota through an explicit task-contract override — not to silently under-grade runbooks.
