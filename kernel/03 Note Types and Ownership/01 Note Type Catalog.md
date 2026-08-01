## Navigation

- Parent: [[kernel/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]].
- Next: [[kernel/03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]].

## Purpose

This standard defines the responsibilities of the different note types, to avoid mixing definitions, mechanisms, system designs, cases, and the expression content registered by the selected profile in the same file.

## Note Types

### Term Note

Responsible for one proper noun's canonical definition, aliases, intuition, formal meaning, examples, and misconceptions.

A Term Note is not responsible for explaining how a complete algorithm or system works, and does not store the complete expression artifacts registered by the selected profile.

### Concept Note

Responsible for explaining one mechanism or idea: problem origin, working principle, assumptions, boundaries, examples, failure modes, and applications.

Examples: Transaction Isolation, Eventual Consistency, Control Loop, Caching.

### Process / Flow Note

Responsible for explaining how a process advances from an entry state to a verifiable exit, including participants, authority, inputs, preconditions, ordering, decision points, branches, loops, state changes, external side effects, failure handling, and termination conditions.

Examples: Incident Response Flow, Order Fulfillment Flow, Release And Rollout Flow, Reconciliation Flow.

A Process / Flow Note does not own the complete internal mechanism of each component. It reuses component pages via wiki links, but MUST state, within the current flow:

- Who decides at each step, and who actually executes.
- How inputs, outputs, state, and authority change.
- Which steps merely propose actions, and which steps have validation and authorization completed by deterministic control.
- When to branch, loop, retry, timeout, cancel, pause, or handoff.
- How external side effects are recorded, confirmed, compensated, or reconciled.
- When it may stop, and how completion is independently verified.

A page with only a single happy-path arrow chain and no control or failure semantics does not satisfy Process / Flow Note.

### Algorithm Note

Responsible for an algorithm's goal, core idea, mathematical procedure, training and inference, complexity, hyperparameters, applicability conditions, strengths and weaknesses, overfitting control, and interpretation methods.

Examples: Binary Search, Dijkstra, Quicksort, Consistent Hashing.

### Metric Note

Responsible for the metric definition, formula, numeric examples, applicable scenarios, boundaries, thresholds, conflicts with other metrics, and common misreadings.

A Metric Note is not responsible for repeating the definition of an entire task type.

### System Component Note

Responsible for one system component's responsibilities, interfaces, inputs and outputs, state, lifecycle, dependencies, failure modes, observability, and security.

Examples: Scheduler, Message Queue, Cache, Rate Limiter.

### System Design Note

Responsible for a complete system: requirements, architecture, component relationships, data flow, API, state, reliability, security, scaling, cost, and alternatives.

Examples: Order Processing System, Event Processing Platform, Document Storage Service.

### Comparison Note

Responsible for comparing multiple options along unified dimensions, and providing selection rules and boundary cases.

Examples: Polling vs Subscription, Relational vs Document Store, Synchronous vs Asynchronous Interface.

A Comparison Note MUST NOT be merely a two-column list of pros and cons.

### Risk And Control Note

Responsible for the threat model, attack or failure paths, impact, detection, mitigation, residual risk, and verification methods.

Examples: Data Leakage, Injection, Secret Leakage, Rate Limit.

### Source Note

Responsible for faithfully recording one external source worth reusing or continuously tracking: source identity, problem background, key claims, evidence, limitations, unproven content, and the knowledge pages it may affect.

A Source Note does not own generic definitions, mechanisms, or industry conclusions, and a file is not required for every ordinary URL.

### Research Synthesis Note

Responsible for synthesizing multiple sources around one research question: terminology mapping, common observations, conflicts, evidence strength, vendor-specific choices, generalizable mechanisms, open questions, and proposed knowledge-graph changes.

A Research Synthesis MAY carry frontier questions still taking shape, but MUST NOT serve long-term as a substitute for already-stable canonical concept, system, or risk/control notes.

### Case Study

Responsible for applying existing knowledge to a real problem: requirements, constraints, decisions, architecture, end-to-end flow, tradeoffs, incidents, metric provenance, security, launch process, and retrospective.

A Case Study does not own basic concept definitions, MUST link to canonical notes, and MUST distinguish public facts, reasonable inferences, and knowledge-base recommendations.

### Overview / MOC

Responsible for domain boundaries, module relationships, main entry points, prerequisite chain, and coverage navigation. An Overview / MOC does not own the complete mechanisms of leaf knowledge, and MUST NOT substitute a list of links for the explanation of module relationships.

### Roadmap

Responsible for learning or preparation order, priorities, and acceptance milestones; it does not carry core knowledge explanation.

### Cheat Sheet

Responsible for compressed review and quick lookup; all detailed explanations MUST link back to canonical notes.

### Standards And Management Note

Responsible for rules, the Coverage Ledger, coverage matrices, progress, audit results, and migration records; it does not enter the normal knowledge learning mainline.

## Type And Depth Fit

Note type decides what responsibility a page carries; depth class decides to what extent questions must be answered:

- A Term Note is usually `atomic` and MAY be deliberately kept concise.
- Concept, Comparison, and Metric are usually `core`.
- Process / Flow MAY be `core` or `system` depending on scope.
- System Component and complete System Design are usually `system`.
- Source Note and Research Synthesis are determined by claim coverage and evidence boundary, and are not upgraded by length.

Line counts may only be used to detect anomalies; they cannot change the note type, and they cannot prove depth. A page that should explain a mechanism or a production flow MUST NOT be labeled a Term Note to evade the Core / System depth requirements.
