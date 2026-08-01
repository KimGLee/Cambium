## Navigation

- Profile: [[profiles/agent-atlas/profile|Agent Atlas Profile]].
- Kernel contract: [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Dimension-specific Audit Receipt|Dimension-specific Audit Receipt]].
- Registered scans: [[profiles/agent-atlas/registries/registered-scans|Registered Scan Registry]].

## Dimension Registrations

| Registration | Dimension | Canonical owners |
|---|---|---|
| Interview semantic quality and readiness | `interview`（profile extension） | [[profiles/agent-atlas/interview/07 Migration Audit and Acceptance#Interview Review|Interview Review]]；[[profiles/agent-atlas/interview/07 Migration Audit and Acceptance#Acceptance Criteria|Acceptance Criteria]] |
| Interview mapping, migration, and coverage invalidation | `interview`（profile extension） | [[profiles/agent-atlas/expression-layer#Expression Layer Link|Expression Layer Link]]；[[profiles/agent-atlas/interview/07 Migration Audit and Acceptance#Migration Audit|Migration Audit]] |
| Language acceptance and invalidation | `content_and_depth`（kernel base binding） | [[profiles/agent-atlas/language-contract#Acceptance And Audit（验收与审计）|Language Contract / Acceptance And Audit]]；[[profiles/agent-atlas/language-contract#Migration And Invalidation（迁移与失效）|Language Contract / Migration And Invalidation]] |
| Profile mainline and foundation completeness | `content_and_depth`、`coverage_and_integration`（kernel base bindings） | [[profiles/agent-atlas/scope-and-architecture#Target|Profile Scope / Target]]；[[profiles/agent-atlas/scope-and-architecture#Foundation Depth Requirements|Foundation Depth Requirements]]；[[profiles/agent-atlas/scope-and-architecture#Production System Reasoning Applicability|Production System Reasoning Applicability]] |

`interview` 是本 profile 登记的扩展维度。Kernel 的七个基础维度保持固定；上表中的 base bindings 只指向既有 profile predicates，不复制或重定义这些 predicates。

每张 profile-dimension receipt 必须引用上表对应的 canonical owner 和具体 acceptance predicate；仅写 `interview passed`、`language passed` 或 `scope passed` 不构成可复用证据。
