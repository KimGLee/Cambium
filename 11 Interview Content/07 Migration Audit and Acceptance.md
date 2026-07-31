## Navigation

- Parent: [[Knowledge Base Standards/11 Interview Content Standard|11 Interview Content Standard]].
- Previous: [[Knowledge Base Standards/11 Interview Content/06 Roadmap and Question Bank|Roadmap and Question Bank]].

## Migration Policy

未来迁移现有内容时：

1. 盘点所有 `Interview Answer`、follow-ups、self-test 和 roadmap。
2. 按核心概念卡或主题组合卡建立映射。
3. 先创建完整 Interview Card，再删除知识页中的重复答案。
4. 在原位置添加 Interview Card link。
5. 更新 Roadmap、Cheat Sheet、Question Bank 和 graph group。
6. 验证没有内容丢失、重复或断链。

禁止先删除旧答案，再等待未来补卡。

## Migration Audit

每个内容 batch 扫描其 changed/owned scope；全库残留扫描由批次关闭封闭清单第 6 项承担（[[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]]）；Terminal Audit 仅验证相应 receipts。语义深审复用仍有效的 interview/content receipts，只覆盖 changed、invalidated、overdue 和抽样对象。候选章节扫描至少检查：

- `## Interview Answer`
- `30-Second Answer` / `90-Second Answer`
- `Common Follow-ups` 或完整 follow-up answers
- `Common Misconceptions`
- `Strong Answer Signals` / `Weak Answer Signals`
- `Self-test Questions`

扫描结果必须逐项分类：

| Disposition | Meaning |
|---|---|
| Migrate | 完整内容应进入已有或新建 Interview Card |
| Minimal Context | 只保留当前知识段落可读所需的一句最小解释 |
| Card Link | 正文只保留可解析的 Interview Card wiki link |
| Not Interview Content | 标题相似但实际属于 canonical mechanism 或 evaluation |

迁移完成后：

- 先确认 Interview Card 内容完整并通过链接检查。
- 再删除 canonical page 中的重复话术。
- 更新 `interview_status`、Roadmap、Cheat Sheet 和 Question Bank。
- 确认合并 Card 的每个 canonical topic 都有双向导航。

自动扫描只能发现候选章节，不能直接删除内容。没有建立完整 Card 前不得清空旧答案。

## Acceptance Criteria

- P0 / P1 主题拥有对应 Interview Card。
- 核心知识页不再维护重复的完整面试答案。
- Coverage Ledger 中没有 P0 / P1 `interview_status: missing` 且无明确 disposition 的主题。
- 30 秒、90 秒和 Deep Dive 层次明确。
- 中英文表达一致。
- Follow-ups 能追问原因、假设、失败和工程实现。
- System / Project Deep Dive 按 [[Knowledge Base Standards/11 Interview Content/04 System Deep Dive and Bilingual Policy|11/04]] 的骨架要素逐项覆盖。
- 所有项目指标都能回溯到 evaluation provenance，而不是只有孤立数字。
- Emerging 或 contested 结论在答案中有清楚限定。
- Strong / Weak Signals 可以实际用于评分。
- Question Bank、Roadmap 和 Card 之间链接完整。
- Canonical pages 中遗留的 Interview Answer、follow-up 和 self-test 候选已经完成 Migration Audit。

## Related

- [[kernel/04 Content Depth Standard|Content Depth Standard]]
- [[kernel/05 Terminology Standard|Terminology Standard]]
- [[Knowledge Base Standards/09 Wiki Link and Navigation Standard|Wiki Link and Navigation Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
