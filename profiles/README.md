## Profile Loading Contract

生效标准由 `kernel + one selected profile` 合成。Kernel 只引用稳定 slot 名；所选 profile 的 manifest 将这些 slot 绑定到具体实现。缺少当前任务所需 slot 时不得把组合标准判为完整加载。

## Profile Scope Slot

`Profile Scope` 必须声明目标、内容优先因素、排除清单、逻辑架构、knowledge spine、基础层目录和共享层名注册。它可以替换具体领域承诺，但不能覆写 kernel 的保全、ownership、迁移或质量不变量。

对于内容深度，`Profile Scope` 还必须实现 `Foundation Depth Requirements` 和 `Production System Reasoning Applicability` 两个子项。

## Language Contract Slot

`Language Contract` 绑定 profile 的正文语言、显示标签和内容长度单位。它可以把 kernel 的软性篇幅范围解释为 profile 单位，但不能改变数值范围，也不能把软性参考改成硬 gate。

## Expression Layer Entry Slot

`Expression Layer Entry` 把 kernel 的 `Expression Layer Link` 绑定到 profile 的显示标签和已注册表达产物。它只负责路由与命名，不复制表达层规则。

## Role Registry Slot

`Role Registry` 可以为 kernel 的 `proposer`、`gatekeeper`、`executor`、`stopper` 登记 profile 角色名并增加扩展角色，但不能降低四问下限。同一主体可以承担多个角色。

## Routing And Gate Registry Slot

`Routing And Gate Registry` 将 profile-owned task routes、Read Sets 和扩展 gates 绑定到 kernel role；未注册的 profile route 不能由 kernel 暗示为已加载。
