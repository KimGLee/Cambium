## Navigation

- Profile: [[profiles/agent-atlas/profile|Agent Atlas Profile]].
- Kernel closed list: [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|Batch-close Closed List]].
- Audit dimensions: [[profiles/agent-atlas/registries/audit-dimensions|Audit Dimension Registry]].

## Scan Registrations

| Scan ID | Activation role | Verifier | Candidate boundary and acceptance owner |
|---|---|---|---|
| `agent-atlas-language-candidates` | changed / invalidated scope | `Tools/check_language.py` | 只产生 review candidates，永不直接判失败；最终判断由 [[profiles/agent-atlas/language-contract#Acceptance And Audit（验收与审计）|Language Contract / Acceptance And Audit]] 拥有 |
| `agent-atlas-interview-residuals` | changed / owned scope；Batch-close Closed List 第 6 项的 residual-content scan | deterministic grep-level heading scan | 只报告 [[profiles/agent-atlas/interview/07 Migration Audit and Acceptance#Migration Audit|Migration Audit]] 登记的候选；逐项 disposition 与完成判断由 [[profiles/agent-atlas/interview/07 Migration Audit and Acceptance#Acceptance Criteria|Acceptance Criteria]] 拥有 |

本注册表只绑定 kernel 已预留的 scan roles，不新增、删除或重排 Batch-close Closed List。`Tools/check_language.py` 的物理位置不改变其 profile semantic ownership。

Frontmatter 受控词表校验仍是 kernel 封闭清单第 7 项，不是本注册表新增的 scan；其 profile 输入由 [[profiles/agent-atlas/profile#Implemented Slots|Vocabulary Extensions]] 提供。
