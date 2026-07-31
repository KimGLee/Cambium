## Navigation

- Parent: [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]].
- Previous: [[kernel/06 Knowledge Intake and Evolution/01 Intake Scope and Knowledge Model|Intake Scope and Knowledge Model]].
- Next: [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]].

## User Guidance, Hypotheses And Source Leads

用户在长任务中提供的引导可能同时改变 task contract 并触发知识调查。执行控制遵循 [[Knowledge Base Standards/02 Build Execution/02 Mid-task Guidance and Amendment#Mid-task Guidance And Contract Amendment|Mid-task Guidance And Contract Amendment]]；本节只规定其证据角色。

必须区分：

| User Input | Authority | Evidence Treatment |
|---|---|---|
| 学习目标、scope、优先级、格式和停止要求 | 用户对当前任务具有 authority | 直接进入 task amendment，不需要外部来源证明用户偏好 |
| 技术看法或行业判断 | 用户可以触发调查 | 默认是 `research signal`，不能直接成为 canonical fact |
| 官方文章、论文、链接或文档线索 | 用户决定需要检查该来源 | 实际文档是 Source，仍需核验 identity、date、claim 和 scope |
| 用户项目经历、指标或事故描述 | 用户是该上下文的一方 | 作为 bounded first-party context；未经其它证据不能推广为行业规律 |
| 对现有知识的纠正 | 触发定向审计 | 根据公式、规范、原始来源或实现证据确认后再改 canonical note |
| 可复用的建设规则 | 用户可以授权 governance change | 只有明确要求修改 Standards 时才改变 `standards_version` |

用户提出“Topic X 是近期热点”可以提升研究优先级并触发 environmental scanning，但在找到和比较来源前只能写成 signal。用户提出“增加 Topic X 部分”则同时是 scope amendment；是否建立新页面、扩写现有页面或形成 system vertical slice，仍由 gap analysis 和 canonical ownership 决定。

处理流程为：

```text
User Guidance Event
 -> Task Authority And Scope Classification
 -> Research Signal / Source Lead Classification
 -> Amendment Record
 -> Source Capture When Needed
 -> Claim Extraction And Evidence Review
 -> Existing Graph Gap Analysis
 -> Canonical Integration Or Justified Deferral
```

以下规则始终适用：

- 不为一条没有外部证据的用户观点单独创建 Source Note。
- 用户提供 URL 时，记录文档自身的 organization、author、date 和 applicability，不把“用户发来的”当作 source authority。
- 用户提供的项目事实必须注明 system、time、dataset、role 和可验证边界；缺失信息保持 unknown。
- 用户观点与可靠来源冲突时，保留冲突并说明，不静默选择更方便的说法。
- 用户只是表达兴趣时，不自动把所有相关页面改为 P0；priority 仍要结合 `Profile Scope` 声明的目标、依赖和明确 task intent。
- 用户要求立即纳入范围时，先更新 scope / queue，再按 source-to-knowledge pipeline 建设，不能把未经验证的观点直接写成稳定结论。
