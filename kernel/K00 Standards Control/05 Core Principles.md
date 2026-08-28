## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/04 Control State and Scope|Control State and Scope]].
- Next: [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]].

## Core Principles

1. One canonical source: a concept is maintained in full in exactly one canonical note.
2. Separation of concerns: knowledge, terminology, system design, cases, and expression artifacts each carry distinct responsibilities.
3. Depth over volume: the standard is whether a question is explained thoroughly, not file count or word count.
4. Explain the why: explain not only what it is, but also why it exists, why it is designed this way, and why the naive approach fails.
5. Reusable knowledge: shared definitions are reused via wiki links, not copied across pages.
6. Local readability: after referencing an external term, the current paragraph SHOULD still be understandable on its own.
7. Evidence first: key facts, formulas, protocols, and time-sensitive content MUST have reliable sources.
8. Foundations remain complete: the application focus of the selected `Profile Scope` does not mean its foundational knowledge may be deleted or compressed.
9. Source-to-knowledge: external sources first pass through claim extraction, synthesis, and ownership determination before changing canonical knowledge.
10. Expression separation: derived expression material is registered by the `Expression Layer Entry` and stored independently of canonical knowledge.
11. No empty completion: empty-shell pages, placeholder links, and core pages of only two or three sentences do not count as complete.
12. Continuous verification: every content batch runs link, formula, rendering, source, duplication, and coverage checks.
13. State separation: task, authoring, expression, evidence, and learning states MUST NOT substitute for one another.
14. Durable coverage: every in-scope page and Required knowledge object has a Coverage Ledger disposition.
15. Time is not proof: earliest run time, checkpoints, and hard stops cannot replace the Completion Gate.
16. Deterministic-first rendering: check source files in full, with static compile / parse triggered by content; UI, screenshots, and visual models are used only when deterministic evidence cannot eliminate a specific display uncertainty; screen recording is used only for timing or interaction issues that static evidence cannot express.
17. Guidance is durable: mid-task user guidance enters the Amendment Log and MUST NOT be kept only in ephemeral conversation context.
18. Authority is not evidence: the user decides what the current task does; whether a technical claim holds is still decided by sources and verification.
19. Incremental amendment: new guidance modifies only the contract dimensions it explicitly touches; non-conflicting constraints remain in effect.
20. Modular ownership: every rule has a canonical owner in one leaf module; Standard Module MOCs provide navigation only.
21. Content conservation: Standards splits and migrations MUST use block-by-block mapping; without separate authorization, rules MUST NOT be trimmed, summarized, or deleted under cover of structural adjustment.
22. Language contract: reader-facing language, canonical identity, display order, and exception boundaries are registered by the selected `Language Contract`; the kernel does not hard-code a specific language.

Which file owns each cross-domain object, and which stable Gate identity checks each risk object, are registered in [[kernel/K00 Standards Control/11 Standards Map and Rule Registry#Cross-domain Rule Registry|Standards Map and Rule Registry]] and [[kernel/K00 Standards Control/12 Control Registry#Control Registry|Control Registry]]. The former maps semantic owners; the latter is the machine owner of Gate identity and consumption position. Neither duplicates the rule or implementation it references.
