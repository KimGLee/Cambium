# Scope And Architecture

Implements the `Profile Scope` slot.

TODO(profile) — fill in the sections below, then delete this line and the `What This Slot Must Answer` section. Both are scaffolding, not part of your profile.

## What This Slot Must Answer

This is the largest slot, and the one the rest of the profile leans on. It declares what the knowledge base is for, what belongs in it, how it is laid out, and how deep a page must go before it counts as done. Later slots refer back to these sections by name, so answer them here rather than scattering the decisions.

You may replace every domain-specific commitment below. You may not override the kernel's conservation, ownership, migration, or quality invariants — this slot decides what your knowledge base contains, not whether the kernel's rules apply to it.

## Goal

TODO(profile) — state what this knowledge base is for and who reads it. Then state how you would know it is succeeding: name the question a reader should be able to answer without asking a person. A goal that cannot fail any test is not usable by the reviewer downstream.

## Content Priority Factors

TODO(profile) — list, in descending order, the kinds of content that matter most. This ordering is what `Priority Rubric` converts into P0 / P1 / P2 grants, so make it an ordering, not an unranked set.

## Excluded Scope

TODO(profile) — list what does not belong in this knowledge base even though it is adjacent to the subject, and say where each excluded kind lives instead. Exclusions prevent scope drift; an empty exclusion list usually means the boundary has not been thought through yet.

The kernel reads this section by its role name, `Excluded Scope`, when it builds the coverage inventory, and it hard-codes no deployment paths of its own. Keep the heading as written unless you also rebind the role, or the inventory will find nothing here.

## Logical Architecture

TODO(profile) — describe the layers or top-level divisions of the knowledge base and what each holds. State each layer's typical volatility (`fast`, `slow`, or `stable`), because volatility drives review scheduling.

A table works well here: one row per layer, with its directory, its content, and its volatility.

## Knowledge Spine

TODO(profile) — name the single organizing thread that connects pages across layers, and state what each page must declare about its position on that thread. The spine is what keeps a knowledge base from becoming an unordered pile of correct pages; it is usually a lifecycle, a pipeline, a progression, or a dependency order.

## Directory Layout

TODO(profile) — give the physical tree of the vault, including the foundation-layer directories. Use a fenced code block so the tree renders as written.

### Placement Layer Registrations

The kernel decides where a page belongs by the "lowest reasonable common layer" rule, and it names the destinations by role rather than by directory. Each role below is a name the kernel already uses in its placement and terminology rules; this section binds each one to something real in your vault.

A role this profile does not use still has to be answered. Write that it is unregistered and say where material of that kind goes instead — otherwise the kernel's placement rule routes pages to a destination that does not exist.

- `Shared Foundation Layer` → TODO(profile) — where a concept goes when several domains reuse it and it has a natural foundational home. Give the directory and the frontmatter its pages carry. Copying such a concept into each domain instead is a conservation violation under the kernel's split and duplication policy.
- `Production Systems Layer` → TODO(profile) — where a concept goes when it is generic to production systems rather than owned by any one domain.
- `Cross-domain Concepts Layer` → TODO(profile) — where a term goes when it is genuinely cross-domain and has no natural owner. The kernel warns against this becoming an uncategorized, unboundedly growing glossary; state what bounds it.
- `Expression Layer Predicate` → TODO(profile) — the test a page must satisfy to belong in the expression layer instead of in canonical knowledge. Write it as a predicate that can return false, not as a description of the layer. The expression layer never becomes a term's owner; it only references one.
- `Case Study Layer` → TODO(profile) — where a page goes when it describes only how something was used inside one case. Its definitions still link back to the canonical note; that back-link is kernel-owned and not yours to drop.
- `Source Note Layer` → TODO(profile) — where a page goes when it records exactly one external source. It does not own general conclusions.
- `Research Synthesis Layer` → TODO(profile) — where a page goes when it synthesizes several sources but its conclusions are still forming. It must not pose as a stable definition.

### New Page Placement Rule

TODO(profile) — give an ordered decision rule that sends a new page to exactly one directory, phrased as the question the page answers. State what happens to a page that answers more than one question: under the kernel's conservation rules it is split along those lines, not filed in both places.

## Terminology Structure

TODO(profile) — give the directory tree that holds term notes, and state how a term note's destination follows from the placement layers registered above. The kernel owns term extraction, ownership, aliases, and reuse; this section only decides where the resulting files live.

The kernel names one anti-pattern here directly: an uncategorized, unboundedly growing global glossary folder. If your structure has a catch-all, say what keeps it bounded.

## Foundation Depth Requirements

TODO(profile) — state what makes a foundation-layer page deep enough to pass review, and give one concrete example of a page that fails the bar and why. This section is consumed by the Depth dimension of single-note review, so a vague answer here weakens every later depth judgment.

## Production System Reasoning Applicability

TODO(profile) — state which pages must carry design reasoning rather than description, and what that reasoning must contain. In most domains the useful form is: the constraint that forced the decision, the alternatives rejected, and the failure modes the current design accepts.

If reasoning of this kind does not apply to your domain, write that explicitly and say why. The interface requires this sub-item to be implemented; declaring it inapplicable with a reason is an implementation, silence is not.

## Representative Sample Set

TODO(profile) — name the sample pages written first, covering the note types this profile uses, before any template is applied in bulk. The kernel requires only that the set cover enough representative types to test how the templates behave; it does not supply the type list, and it does not copy yours.

TODO(profile) — name who confirms the samples. Bulk application is gated on that confirmation, so the gate needs a party, not a step. The samples exist to expose a template that is too heavy, too shallow, or duplication-producing while the cost of changing it is still one page.

## Dependency-ordered Build Sequence

TODO(profile) — name this profile's pipeline stages, in build order. The kernel requires vertical slices running from the foundational mechanism through runtime use, the production chain, evaluation, and expression-layer output; it does not name your stages.

State the order as a dependency order rather than a preference, because the kernel rules out both of the shortcuts it sees most: writing all foundations first, and jumping straight to the application mainline. Foundation coverage keeps advancing regardless, and cannot be declared complete merely because the mainline already runs.
