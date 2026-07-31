## Navigation

- Parent: [[Knowledge Base Standards/01 Scope and Architecture Standard|01 Scope and Architecture Standard]].
- Previous: [[Knowledge Base Standards/01 Scope and Architecture/03 Foundation Preservation|Foundation Preservation]].

## Physical Folder Policy

逻辑上属于某一层，不代表必须立即移动现有文件。

目录迁移必须满足：

1. 新 ownership 已明确。
2. 所有 incoming links 已盘点。
3. 新路径不会产生同名歧义。
4. Overview、Roadmap 和 graph group 可以同步更新。
5. 迁移所在批次关闭的 Batch-close Closed List（[[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]]）覆盖全库链接验证。

禁止为了目录看起来整齐而进行没有知识收益的大规模移动。

## Shared Ownership Rule

一个概念的归属由“最低合理公共层”决定：

- 只服务单一领域：放在该领域。
- 多领域复用且有自然基础归属：放在 Shared Foundations。
- 生产系统通用：放在 AI Systems Engineering。
- 只描述面试表达：放在 Interview Preparation。
- 只描述案例中的使用方式：放在 Case Study，但定义仍回链 canonical note。
- 只记录单一外部来源：放在 Source Note，不拥有通用结论。
- 综合多个来源但结论仍在形成：放在 Research Synthesis，不提前伪装成稳定定义。

## Architecture Anti-patterns

- 每出现一个新词就新建顶层文件夹。
- 同一概念在 ML、DL、LLM、Agent 下分别复制一份。
- Roadmap、Cheat Sheet 和主题页都保存同一段解释。
- 把所有共享概念丢进一个无分类的 Glossary。
- 先移动文件，再考虑引用和 ownership。
- 用图谱颜色代替真实的知识层级设计。
- 为突出 Agent/Harness 而删除或过度压缩 ML、DL、LLM 和 Retrieval 基础。
- 按文章标题建立 canonical note，未经过 claim extraction 和 graph impact 判断。

## Related

- [[Knowledge Base Standards/03 Note Types and Ownership Standard|Note Types and Ownership Standard]]
- [[Knowledge Base Standards/05 Terminology Standard|Terminology Standard]]
- [[Knowledge Base Standards/11 Interview Content Standard|Interview Content Standard]]
- [[Knowledge Base Standards/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
