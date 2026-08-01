# Scope And Architecture

Implements the `Profile Scope` slot.

TODO(profile) — fill in the sections below, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

This is the largest slot, and the one the rest of the profile leans on. It declares what the knowledge base is for, what belongs in it, how it is laid out, and how deep a page must go before it counts as done. Later slots refer back to these sections by name, so answer them here rather than scattering the decisions.

You may replace every domain-specific commitment below. You may not override the kernel's conservation, ownership, migration, or quality invariants — this slot decides what your knowledge base contains, not whether the kernel's rules apply to it.

A filled version of every section below is in `profiles/examples/eng-handbook/scope-and-architecture.md`. Read it for the level of specificity, not for its answers; that example governs an engineering handbook, and its four-layer architecture is one domain's choice, not a requirement for yours.

## Goal

TODO(profile) — state what this knowledge base is for and who reads it. Then state how you would know it is succeeding: name the question a reader should be able to answer without asking a person. A goal that cannot fail any test is not usable by the reviewer downstream.

## Content Priority Factors

TODO(profile) — list, in descending order, the kinds of content that matter most. This ordering is what `Priority Rubric` converts into P0 / P1 / P2 grants, so make it an ordering, not an unranked set.

## Exclusion List

TODO(profile) — list what does not belong in this knowledge base even though it is adjacent to the subject, and say where each excluded kind lives instead. Exclusions prevent scope drift; an empty exclusion list usually means the boundary has not been thought through yet.

## Logical Architecture

TODO(profile) — describe the layers or top-level divisions of the knowledge base and what each holds. State each layer's typical volatility (`fast`, `slow`, or `stable`), because volatility drives review scheduling.

A table works well here: one row per layer, with its directory, its content, and its volatility.

## Knowledge Spine

TODO(profile) — name the single organizing thread that connects pages across layers, and state what each page must declare about its position on that thread. The spine is what keeps a knowledge base from becoming an unordered pile of correct pages; it is usually a lifecycle, a pipeline, a progression, or a dependency order.

## Directory Layout

TODO(profile) — give the physical tree of the vault, including the foundation-layer directories. Use a fenced code block so the tree renders as written.

### Shared Layer Registration

TODO(profile) — name the directory that holds cross-cutting material referenced by two or more layers, and state the frontmatter marking those pages carry. Every profile needs somewhere for concepts that belong to no single layer; duplicating such a concept into several layers instead is a conservation violation handled by the kernel's split and duplication policy.

### New Page Placement Rule

TODO(profile) — give an ordered decision rule that sends a new page to exactly one directory, phrased as the question the page answers. State what happens to a page that answers more than one question: under the kernel's conservation rules it is split along those lines, not filed in both places.

## Foundation Depth Requirements

TODO(profile) — state what makes a foundation-layer page deep enough to pass review, and give one concrete example of a page that fails the bar and why. This section is consumed by the Depth dimension of single-note review, so a vague answer here weakens every later depth judgment.

## Production System Reasoning Applicability

TODO(profile) — state which pages must carry design reasoning rather than description, and what that reasoning must contain. In most domains the useful form is: the constraint that forced the decision, the alternatives rejected, and the failure modes the current design accepts.

If reasoning of this kind does not apply to your domain, write that explicitly and say why. The interface requires this sub-item to be implemented; declaring it inapplicable with a reason is an implementation, silence is not.
