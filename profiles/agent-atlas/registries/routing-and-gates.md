## Navigation

- Profile: [[profiles/agent-atlas/profile|Agent Atlas Profile]].
- Kernel contract: [[kernel/04 Content Depth Standard|04 Content Depth Standard]].
- Quality kernel: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].

## Expression Layer Read Set

- Kernel role: `Expression Layer Read Set`
- Agent Atlas binding: [[profiles/agent-atlas/interview/05 Interview Content Read Set|Interview Content Read Set]]

## Expression Layer Quality Gates

- Kernel role：[[kernel/11 Expression Layer/07 Expression Migration Audit and Acceptance|Expression Migration Audit and Acceptance]]。
- Readiness axis：`interview_status`。
- Completion value：`interview-ready`。
- Upgrade gate：P0 / P1 topics 必须通过 [[profiles/agent-atlas/interview/07 Migration Audit and Acceptance#Interview Review|Interview Review]]，`interview_status` 才能升级为 `interview-ready`。
- Batch migration gate：[[profiles/agent-atlas/interview/07 Migration Audit and Acceptance#Migration Audit|Migration Audit]] 已完成，或每个 candidate 都有明确 disposition；[[profiles/agent-atlas/interview/07 Migration Audit and Acceptance#Acceptance Criteria|Acceptance Criteria]] 仍是 canonical acceptance owner。
- Module 与 Terminal synchronization gate：active Overview、[[profiles/agent-atlas/interview/06 Roadmap and Question Bank|Roadmap]]、Cheat Sheet 与 [[profiles/agent-atlas/expression-layer|Interview Preparation]] routes 必须反映当前 module structure 与 canonical owners。
- Final-report projection：报告哪些 topics 已达到 `interview-ready`、还有哪些 profile expression gaps，以及它们的 dispositions。
- Specialized audit gate：Interview Audit 检查 P0 / P1 coverage、Card granularity、migration、bidirectional navigation 与 scoring structure；它复用仍有效的 canonical content receipts，不重复无关的 content review。
- Audit dimension binding：[[profiles/agent-atlas/registries/audit-dimensions|Audit Dimension Registry]]。
- Registered scan binding：[[profiles/agent-atlas/registries/registered-scans|Registered Scan Registry]]。
- Language quality owner：[[profiles/agent-atlas/language-contract#Acceptance And Audit（验收与审计）|Language Contract / Acceptance And Audit]]。
- Profile scope quality owners：[[profiles/agent-atlas/scope-and-architecture#Target|Profile Scope / Target]]、[[profiles/agent-atlas/scope-and-architecture#Foundation Depth Requirements|Foundation Depth Requirements]] 与 [[profiles/agent-atlas/scope-and-architecture#Production System Reasoning Applicability|Production System Reasoning Applicability]]。
