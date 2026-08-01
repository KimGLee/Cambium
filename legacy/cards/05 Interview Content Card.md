---
type: runtime-card
compiled_from: v2.3
source_files:
  - Read Sets/05 Interview Content Read Set.md
  - 11 Interview Content/01 Interview Architecture and Separation.md
  - 11 Interview Content/02 Card Granularity Coverage and Categories.md
  - 11 Interview Content/03 Card Structure and Answer Levels.md
  - 11 Interview Content/04 System Deep Dive and Bilingual Policy.md
  - 11 Interview Content/05 Knowledge Links and Preparation.md
  - 11 Interview Content/07 Migration Audit and Acceptance.md
  - 05 Terminology/04 Interview and Acceptance.md
source_hash: 789b68d9de5a
---
# 05 Interview Content Card（面试内容卡）

> 本卡为编译产物，禁止手改；标准修订后用治理流程重新生成。规则争议以 source_files 原文为准。

## Tiering（分档）

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 12/03 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋本卡 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页、System Deep Dive、Interview Card 集 | 完整流程：12/01 全量 review＋独立 note gate＋interview 迁移核对 |

争议时上调一档。分档规则 owner：[[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]]。

## Before Start（开工前）

- 分离：知识页管理解，Card 管表达；面试内容只放 `Interview Preparation/`，知识页（含 Term Note）只留 Card link，建卡后换可解析链接；知识不足先补知识页。
- 粒度：单独卡＝高频核心＋≥3 追问＋独立机制/tradeoff/失败＋超 90 秒；合并卡＝同机制参数、同题指标、拆开碎片化。
- 类别：Concept/System Design/Project Deep Dive。

## During（执行中）

- 结构（11/03）：Scope>Prerequisites>Knowledge Links>30s/90s（英＋中）>Follow-up Tree/Answers>Misconceptions>Signals>比较/场景/自测>Related。
- 30s＝定义＋问题＋价值；90s＝Problem>Mechanism>Components>Tradeoff>Use case；Deep Dive＝追问树，P0/P1≥3 层有答案。
- 双语两句（11/04）：①30s/90s 完整中英文，follow-up 中英标题、需口述的给英文答/骨架；②中英含义一致，英文不得漏关键限制。
- System DD 骨架（照抄 11/04）：Problem And Success Criteria/Why Agent/Why This Harness/End-to-end Execution Path/State Ownership And Persistence/Agent Coordination And Handoff/Tool And Permission Boundaries/Evaluation Provenance/Offline Replay/Regression/Backtesting/Failure Propagation And Recovery/Observability And Incident Diagnosis/Latency Cost And Scale/Alternatives And Rejected Designs；答案回链 canonical，不造事实。
- interview_status：missing>mapped>drafted>reviewed>interview-ready；not-required 须给归并说明/理由；有链接只算 mapped。
- 迁移：先建完整 Card＋过链接检查再删旧答案；候选四分 Migrate/Minimal Context/Card Link/Not Interview Content；禁先删后补。

## Gate（关闭前）

验收（owner 11/07）：
- [ ] P0/P1 有 Card；无「missing 且无 disposition」项
- [ ] 知识页无重复答案；页↔Card 双向导航
- [ ] 30s/90s/DD 层次明确；follow-up 有答案；中英一致
- [ ] emerging/contested 有限定；指标可溯源；Signals 可评分
- [ ] check_links、check_vocab `--scope 本页` 自查（不产 receipt）；语言候选由 check_language 入 candidates 池；批级 gate＝Batch-close Closed List（12/07，七项，含 check_vocab 全库）

## Escalation（例外跳转）

| 情形 | 读原文 |
|---|---|
| Roadmap/Question Bank | [[Knowledge Base Standards/11 Interview Content/06 Roadmap and Question Bank\|11/06]] |
| 迁移旧答案 | [[Knowledge Base Standards/11 Interview Content/07 Migration Audit and Acceptance\|11/07]] |
| 双语/骨架争议 | [[Knowledge Base Standards/11 Interview Content/04 System Deep Dive and Bilingual Policy\|11/04]] |
| 知识不足 | [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set\|RS 02]] |
| Review 细则 | [[Knowledge Base Standards/12 Quality Assurance/04 Guidance Source and Interview Review\|12/04]] |
