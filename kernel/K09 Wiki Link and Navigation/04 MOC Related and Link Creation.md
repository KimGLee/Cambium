## Navigation

- Parent: [[kernel/K09 Wiki Link and Navigation Standard|K09 Wiki Link and Navigation Standard]].
- Previous: [[kernel/K09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]].
- Next: [[kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]].

## Overview And MOC

Each top-level domain requires at least:

- Overview: domain boundaries, core modules, and relationships.
- Sequence view: learning or execution order; the concrete implementation is bound by the selected profile's routing mechanism.
- Coverage map: covered, missing, and priorities.

An Overview is not a file list; it SHOULD explain the dependencies and responsibilities between modules.

The coverage map is the reader view of the [[kernel/K02 Build Execution/03 Inventory and Coverage Reconciliation#Phase 1: Inventory|Coverage Ledger]]; it does not maintain a separate set of completion states. A page having an incoming link, a sequence-view entry, or a resolvable wiki link can only prove navigability; it cannot prove that authoring, profile readiness, or evidence status is complete.

## Related Section

`Related` supplements neighboring pages; it does not carry the causal and dependency explanations that belong in the body.

Related links SHOULD be organized semantically, avoiding unordered accumulation. When content is large, they MAY be split into:

- Prerequisites
- Components
- Alternatives
- Applications
- Evidence And Sources
- Supersedes / Superseded By
- Expression Layer

## Link Creation Policy

- When the canonical page to reference already exists, link it directly.
- When a new page is needed, sufficient content MUST be created at the same time; merely producing an unresolved link is not allowed.
- Before bulk creation, first check whether synonymous pages already exist.
- Term extraction follows the [[kernel/K05 Terminology Standard|Terminology Standard]].
- New links and pages triggered by external sources follow the [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]].
- An article MUST NOT establish weak connections to all terms merely because it contains multiple terms; link only the knowledge objects actually affected by its claims.
