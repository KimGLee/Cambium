## Navigation

- Parent: [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]].
- Previous: [[kernel/K06 Knowledge Intake and Evolution/01 Intake Scope and Knowledge Model|Intake Scope and Knowledge Model]].
- Next: [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]].

## User Guidance, Hypotheses And Source Leads

Guidance provided by the user during a long task can simultaneously change the task contract and trigger knowledge investigation. Execution control follows [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis#Mid-task Guidance And Contract Amendment|Mid-task Guidance And Contract Amendment]]; this section specifies only its evidence role.

The following MUST be distinguished:

| User Input | Authority | Evidence Treatment |
|---|---|---|
| Learning goals, scope, priorities, format, and stop requirements | The user has authority over the current task | Goes directly into a task amendment; no external source is needed to prove user preferences |
| Technical opinions or industry judgments | The user can trigger investigation | Defaults to a `research signal`; MUST NOT directly become a canonical fact |
| Official articles, papers, links, or documentation leads | The user decides that source needs to be checked | The actual document is the Source; identity, date, claim, and scope still require verification |
| The user's project experience, metrics, or incident descriptions | The user is a party to that context | Treated as bounded first-party context; MUST NOT be generalized into an industry law without other evidence |
| Corrections to existing knowledge | Triggers a targeted audit | Change the canonical note only after confirmation against formulas, specifications, original sources, or implementation evidence |
| Reusable build rules | The user can authorize a governance change | Standards adoption resolves the selected upstream Git commit; `standards_version` is only its compatibility alias, while a Profile-only change is bound by Profile snapshot evidence |

A user stating "Topic X is a recent hot topic" can raise research priority and trigger environmental scanning, but until sources are found and compared it MAY only be written as a signal. A user stating "add a Topic X section" is at the same time a scope amendment; whether to create a new page, expand an existing page, or form a system vertical slice is still decided by gap analysis and canonical ownership.

The processing flow is:

```text
User Guidance Event
 -> Task Authority And Scope Classification
 -> Research Signal / Source Lead Classification
 -> Amendment Record
 -> Source Capture When Needed
 -> Claim Extraction And Evidence Review
 -> Existing Graph Gap Analysis
 -> Canonical Integration Or Justified Deferral
```

The following rules always apply:

- A standalone Source Note MUST NOT be created for a user opinion that has no external evidence.
- When the user provides a URL, record the document's own organization, author, date, and applicability; "sent by the user" MUST NOT be treated as source authority.
- Project facts provided by the user MUST note system, time, dataset, role, and verifiable boundary; missing information stays unknown.
- When a user opinion conflicts with a reliable source, keep the conflict and explain it; the more convenient account MUST NOT be silently chosen.
- When the user merely expresses interest, all related pages MUST NOT be automatically set to P0; priority still combines the goals declared by `Profile Scope`, dependencies, and explicit task intent.
- When the user requests immediate inclusion in scope, first update scope / queue, then build via the source-to-knowledge pipeline; an unverified opinion MUST NOT be written directly as a stable conclusion.
