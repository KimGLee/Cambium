# Cambium Kernel EN Glossary (canonical, enforce exactly)

## Execution
批次 batch | 关批/批次关闭 batch close | 批内项 in-batch items | 全局项 global items
串行区 serial zone | 串行合并 serial merge | 写入权分区 write partition
准入(条件) admission (conditions) | 独占执行 exclusive execution | 枢纽页 hub pages
在途批次 in-flight batch | 停滞报警 stall alarm | 检查点 checkpoint | 恢复 resume
清单(页面清单) manifest | 增量 delta / incremental (delta 文件=delta; 增量对账=incremental reconciliation)
纵切片 vertical slice | 依赖序 dependency order | 交接 handoff

## Evidence & QA
凭证/回执 receipt | 分维度 dimension-specific | 指纹 fingerprint | 失效 invalidation
失效传播 invalidation propagation | 复用 reuse | 存量豁免 existing-content exemption
实质正确性复核 substantive correctness review | 确认轮 confirmation round
轮次上限 round cap | 升级用户裁决 escalate to the user | 有界抽样 bounded sampling
封闭清单 Closed List (Batch-close Closed List) | 一险一闸 one risk, one gate
对账 reconciliation | 守恒 conservation | 逐块映射 block-by-block mapping
渲染 rendering | 视觉升级 visual escalation | 确定性 deterministic
终审 Terminal Audit | 完成候选 completion candidate | 零值条件 zero-value conditions
抽查 spot check | 家族扩大 family expansion | 系统性 systemic

## Governance
治理 governance | 修订 revision | 回写 write-back | 版本自检 version self-check
增量采纳 incremental adoption | 变更谓词清单 changed-predicate list
控制义务增生规则 Control Accretion Rule | 三问 three questions
宪法常数→ fixed kernel constant | 内核默认值 kernel default | 覆写 override
登记/注册表 register / registry | 槽位 slot | 所选 profile the selected profile
编译产物 compiled artifact | 禁止手改 must not be hand-edited

## Content & metadata
页面/笔记 page / note | 正文 body | 空壳页 empty-shell page | 红链 unresolved link
canonical 唯一权威 (keep "canonical") | 唯一 owner single canonical owner
词表 vocabulary | 受控词表 controlled vocabulary | 状态轴 status axes
保质期/时效 freshness | 过期 overdue | 退役 retirement | 墓碑 tombstone
入链改指 incoming-link retargeting | 合并(页面) merge | 降级 demotion
配额 quota | 超配 over-allocation | 豁免 exemption | 分档 tiering | 档 tier
验收仪式 acceptance ceremony | 争议上调一档 escalate one tier when disputed
维护轮 maintenance run | 预算封套 budget envelope | 候选池 candidate pool
水位线 watermark | 有界完成 bounded completion | 表达层 expression layer

## Modality
必须 MUST | 不得/禁止 MUST NOT | 应 SHOULD | 可以 MAY | 仅/只有 only/exclusively
"X 是 Y 的 canonical owner" → "X is the canonical owner of Y"

## Hard invariants for translators (violating any = reject)
1. Headings: byte-identical to source, including bilingual parentheticals — they are link anchors.
2. Wiki link targets (path and #heading): byte-identical. Display aliases after | MAY be translated.
3. Code fences, YAML blocks, field names, file paths, schema names: byte-identical.
4. Every number, percentage, threshold, count: unchanged (S≤24/M≤10/L≤6, 15%/35%, cap 3, ≤60s, round cap 2, ÷6, max(2,20%), 120d/365d…).
5. Table row/column structure unchanged; translate cell prose only.
6. Bold/emphasis/list structure preserved; one-to-one sentence correspondence preferred, meaning-lossless required.
7. No Chinese characters may remain outside headings (and untouched code/fences/link targets).
8. Terminology: use this glossary exactly; never alternate synonyms for the same term.
