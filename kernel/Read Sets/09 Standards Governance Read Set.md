## Purpose

用于修改 Standards 的规则内容、模块边界、Read Sets、版本、目录结构或控制面。普通知识内容任务不得隐式进入本 Read Set。

## Start

先读取：

- [[kernel/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]]
- [[Knowledge Base Standards/00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]]
- [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]]
- [[Knowledge Base Standards/00 Standards Control/03 Standards Governance|Standards Governance]]
- [[Knowledge Base Standards/00 Standards Control/04 Control State and Scope|Control State and Scope]]
- [[Knowledge Base Standards/00 Standards Control/05 Core Principles and Standards Map|Core Principles and Standards Map]]
- [[Knowledge Base Standards/00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]]
- [[kernel/02 Build Execution/02 Mid-task Guidance and Amendment|Mid-task Guidance and Amendment]]（修订流程涉及 Amendment Log）
- [[kernel/09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]]
- 所选 profile 的 `Language Contract`。
- [[kernel/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]

## Required Controls

- 用户必须明确授权 governance change。
- 变更前冻结 Standards version、受影响模块、incoming links 和 active task impact。
- 结构迁移必须建立旧内容块到新 owner 的完整映射。
- 拆分不能被用作缩减、摘要或静默删除规则。
- Read Set 和总体 Index 必须与模块路径同步。
- 受影响的 active、paused 和 completion-candidate tasks 必须重新解析 loaded set（`Runtime Card Provider` artifacts 与升级回读的 modules）。
- Governance change 仍遵循确定性优先的渲染边界；仅修改 Markdown 规则不自动触发所选 knowledge-host role 的 interactive UI、截图或录屏。

## Gate

- 使用 [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]] 验证目录、MOC 和 coverage。
- 使用 [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] 记录受影响 active task 的 receipt compatibility、失效范围和 adoption plan。
- 使用 [[kernel/09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]] 验证全库 incoming links。
- 涉及 rendering policy、diagram、table、formula、asset 或 host behavior 时，使用 [[kernel/12 Quality Assurance/02 Rendering Verification|Rendering Verification]] 选择并记录实际级别。
- 使用 [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]] 关闭 governance task。

## Related

- [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[Knowledge Base Standards/00 Standards Overview|Standards Overview]]
