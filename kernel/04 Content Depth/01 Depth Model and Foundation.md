## Navigation

- Parent: [[kernel/04 Content Depth Standard|04 Content Depth Standard]].
- Next: [[kernel/04 Content Depth/02 Core Concept Structure|Core Concept Structure]].

## Purpose

This standard defines a checkable meaning of "content is sufficiently detailed", to prevent core pages from stopping at a definition, two or three sentences of explanation, or a pros-and-cons list.

## Depth Is Question Coverage

Depth is not word count. Whether a topic is explained thoroughly SHOULD be checked by whether it can answer:

1. What problem does it solve?
2. Why does this problem arise?
3. Why is the naive solution insufficient?
4. What is the core mechanism?
5. What assumptions does the mechanism depend on?
6. What is the mathematics, data flow, or execution process?
7. What is a minimal example?
8. When should it be used?
9. When should it not be used?
10. What are the alternatives?
11. What are the main tradeoffs?
12. How does it fail?
13. How are failures detected and debugged?
14. How are results evaluated?
15. What else must be considered in a production system?

## Depth Classes

### Atomic

Suited to a single term or parameter, e.g. Timeout, Checksum, Lease.

Covers at least: definition, role, intuition, one example, boundaries, misconceptions, where it is used, and related concepts.

Soft length reference: 500–1200 content-length units as defined by the selected profile's `Language Contract`.

### Core

Suited to high-frequency core mechanisms, e.g. Transaction Isolation, Eventual Consistency, Control Loop, Caching.

Covers at least: problem origin, mechanism, formula or flow, assumptions, worked example, selection rules, alternatives, failure modes, evaluation, and engineering considerations.

Soft length reference: 1500–3000 content-length units as defined by the selected profile's `Language Contract`.

### System

Suited to components and complete systems, e.g. Task Scheduler, Message Broker, Order Processing Platform.

Covers at least: goals, non-goals, requirements, components, interfaces, data flow, state, lifecycle, concurrency, failure, security, observability, scaling, cost, and alternatives.

Soft length reference: 2500–6000 content-length units as defined by the selected profile's `Language Contract`.

Length is used only to detect anomalies; length MUST NOT be padded out with repeated content of no information density.

## Foundation Depth Rule

The selected profile's knowledge mainline does not lower the depth requirements of foundation pages.

Foundation knowledge pages SHOULD be learnable independently of profile application pages; profile application pages MUST be able to trace back along prerequisites to the complete foundational explanation. Per-discipline requirements are registered in the `Foundation Depth Requirements` of the `Profile Scope`.
