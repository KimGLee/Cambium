---
type: card-index
compiled_from: v2.3
---
# 00 Card Index（卡片索引）

## What This Layer Is（卡片层是什么）

Cards/ 是 Standards 的编译产物层：标准原文是源码，Runtime Card 是编译产物。每张卡把一个任务类型对应 Read Set 的 Start/Triggered/Gate 模块忠实压缩为单页执行卡（Tiering / Before Start / During / Gate / Escalation 五节），供日常任务替代全量 Read Set 阅读。卡片不发明规则；卡片与标准原文冲突时，一律以原文为准并触发重新生成。

## Card Table（十张卡对应表）

| 任务类型 | Read Set | Card |
|---|---|---|
| 所有任务共同控制边界 | [[Knowledge Base Standards/Read Sets/01 Core Bootstrap Read Set\|RS 01]] | [[Knowledge Base Standards/Cards/01 Core Bootstrap Card\|Card 01]] |
| 新建或定向扩展一个 canonical note | [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set\|RS 02]] | [[Knowledge Base Standards/Cards/02 Single Note Authoring Card\|Card 02]] |
| 建设完整知识模块 | [[Knowledge Base Standards/Read Sets/03 Module Build Read Set\|RS 03]] | [[Knowledge Base Standards/Cards/03 Module Build Card\|Card 03]] |
| 来源驱动扩展 | [[Knowledge Base Standards/Read Sets/04 Source-driven Expansion Read Set\|RS 04]] | [[Knowledge Base Standards/Cards/04 Source-driven Expansion Card\|Card 04]] |
| 面试内容建设与迁移 | [[Knowledge Base Standards/Read Sets/05 Interview Content Read Set\|RS 05]] | [[Knowledge Base Standards/Cards/05 Interview Content Card\|Card 05]] |
| 批量移动、重命名、拆分、合并、目录重构 | [[Knowledge Base Standards/Read Sets/06 Migration and Refactor Read Set\|RS 06]] | [[Knowledge Base Standards/Cards/06 Migration and Refactor Card\|Card 06]] |
| 长任务 batch、checkpoint、resume | [[Knowledge Base Standards/Read Sets/07 Long-running Execution Read Set\|RS 07]] | [[Knowledge Base Standards/Cards/07 Long-running Execution Card\|Card 07]] |
| 审计、Completion Gate、Terminal Audit | [[Knowledge Base Standards/Read Sets/08 Audit and Completion Read Set\|RS 08]] | [[Knowledge Base Standards/Cards/08 Audit and Completion Card\|Card 08]] |
| 修改 Standards 或控制面（必须通读原文） | [[Knowledge Base Standards/Read Sets/09 Standards Governance Read Set\|RS 09]] | [[Knowledge Base Standards/Cards/09 Standards Governance Card\|Card 09]] |
| 周期性知识库更新 / 保鲜（Maintenance Run） | [[Knowledge Base Standards/Read Sets/10 Maintenance Run Read Set\|RS 10]] | [[Knowledge Base Standards/Cards/10 Maintenance Run Card\|Card 10]] |

## Usage Protocol（使用协议）

1. 默认卡片优先：日常任务读对应 Card 替代全量 Read Set（见 [[Knowledge Base Standards/00 Standards Control/01 Operating Role and Reading Protocol|00/01]] Card-first Reading Mode）。
2. 例外回读原文：卡片未覆盖或存疑、规则争议、L 档页面深度规则和 Governance 任务必须回读 source_files 原文。
3. 卡片禁止手改：标准修订后按 [[Knowledge Base Standards/00 Standards Control/03 Standards Governance|00/03]] 的 Revision Write-back Checklist 重新生成受影响 Cards。

## Source Hash（source_hash 机制）

每张卡 frontmatter 记录 compiled_from（编译时标准版本）、source_files（编译输入清单）和 source_hash（编译时 source_files 内容摘要）。校验方式：重新计算 source_files 当前内容摘要，与 source_hash 不一致即视为卡片过期——记录 candidate（入 candidates 池），以标准原文为准继续执行；卡片重新生成排入下一次 governance 或维护轮，不阻断当前任务。