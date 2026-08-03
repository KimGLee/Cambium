## Reference

- Profile manifest: `profiles/<your-profile-id>/profile.md`
- Slot interface: `profiles/README.md`, `Role Registry Slot`
- Kernel contract: `kernel/K04 Content Depth/03 Process and Flow Structure.md`

Implements the `Role Registry` slot.

TODO(profile) — fill in the sections below, correct the manifest path above, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

The kernel names four roles in every process and flow: `proposer` (who puts a change forward), `gatekeeper` (who checks it), `executor` (who carries it out), and `stopper` (who can halt or take it over). It refers to them by these stable names and never by a job title, because titles differ between organizations. This file binds each kernel role to whoever fills it here.

Two limits apply. You may add extension roles, but you may not lower the four-question floor: every process must still answer who proposes, who checks, who executes, and who can stop. And one party may hold several roles — the floor is about the four questions being answered, not about four distinct people existing.

A solo maintainer is a legitimate configuration. Write out how the four questions are answered in that case rather than leaving roles unbound; an unbound role reads as an unanswered question during audit.

## Process And Flow Role Bindings

- `proposer` → TODO(profile) — who or what drafts and puts changes forward.
- `gatekeeper` → TODO(profile) — who or what checks a change before it lands. Automated checks are a legitimate gatekeeper for the parts they actually cover; say which parts.
- `executor` → TODO(profile) — who or what lands the approved change.
- `stopper` → TODO(profile) — who can halt, reject, or take over a change, and over which material. Name a party, not a policy; the point of this role is that someone can be reached.

TODO(profile) — state how these bindings work when one party holds several of them, so the arrangement is recorded rather than improvised per task.

## Extension Roles

TODO(profile) — register any additional roles this profile needs, each with what it does and whether it carries gate authority. A role with no gate authority is fine and should say so explicitly. If you need none, write that this profile registers no extension roles.

## Metric Traceability Roles

A page that reports a metric must let a reader trace it back to the task it measured, the dataset it ran on, the trial it came from, the runtime it executed in, the grader that scored it, and the aggregation that produced the reported number. The kernel fixes those six questions and defers the names to this registry, because what counts as a "trial" or a "grader" differs by domain.

- Task → TODO(profile) — what this profile calls the unit of work a metric measures.
- Dataset → TODO(profile) — what the metric was computed over, and how a specific version of it is identified.
- Trial → TODO(profile) — the unit of repetition, and whether a reported number is one trial or several.
- Execution runtime → TODO(profile) — the environment the measurement ran in, at whatever granularity actually changes results here.
- Grader → TODO(profile) — what assigns the score, whether that is a script, a rubric, a model, or a person.
- Aggregation → TODO(profile) — how trial-level results become the reported number, including which statistic.

If a metric of this kind never appears in this profile's material, write that explicitly and say so once here. The Provenance dimension of single-note review reads this section; an unbound role reads as an unanswered question during audit, not as an absent one.

## Knowledge Host Role Bindings

The kernel refers to the system that stores the knowledge base through a stable role, so it never depends on a product name.

- `knowledge-host` → TODO(profile) — the store itself.
- `knowledge-host UI` → TODO(profile) — what people read and edit it through.

These bindings supply deployment values for this profile only.
