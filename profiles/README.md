## Profile Loading Contract

生效标准由 `kernel + one selected profile` 合成。Kernel 只引用稳定 slot 名；所选 profile 的 manifest 将这些 slot 绑定到具体实现。缺少当前任务所需 slot 时不得把组合标准判为完整加载。

## Profile Scope Slot

`Profile Scope` 必须声明目标、内容优先因素、排除清单、逻辑架构、knowledge spine、基础层目录和共享层名注册。它可以替换具体领域承诺，但不能覆写 kernel 的保全、ownership、迁移或质量不变量。

对于内容深度，`Profile Scope` 还必须实现 `Foundation Depth Requirements` 和 `Production System Reasoning Applicability` 两个子项。

## Priority Rubric Slot

`Priority Rubric` 绑定所选 profile 的 P0 / P1 授予条件。它必须消费 kernel 固定的 P0 / P1 / P2 三级轴，不能改名、增删或重定义该轴，也不能覆写 tier 派生、配额挂钩、默认阈值或豁免机制。

## Vocabulary Extensions Slot

`Vocabulary Extensions` 绑定 profile-owned 的 frontmatter 扩展字段、type / domain / scope / status 追加值和 domain → volatility 派发表。它只能追加已注册值，不能删除、重命名或重定义 kernel base；含行为规则的字段必须指向 manifest 登记的唯一 prose owner。`Tools/vocab.yaml` 是后续由 kernel base 与 selected profile extensions 合成的生成物，不是 canonical owner。

## Language Contract Slot

`Language Contract` 绑定 profile 的正文语言、显示标签和内容长度单位。它可以把 kernel 的软性篇幅范围解释为 profile 单位，但不能改变数值范围，也不能把软性参考改成硬 gate。

## Expression Layer Entry Slot

`Expression Layer Entry` 把 kernel 的 `Expression Layer Link` 绑定到 profile 的显示标签和已注册表达产物。它只负责路由与命名，不复制表达层规则。

## Source Policy Slot

`Source Policy` 绑定 profile-owned 的具名一手来源集合、扫描 / 核验入口、适用范围或 priority trigger、对照与缺失记录规则，以及 profile-specific evaluation provenance extensions。它可以加严，但不得削弱或替代 kernel 的 source hierarchy、authority / evidence role / applicability / bias 四维判断、cross-source independence / comparability、十要素 provenance、`unknown`、source quality 或 promotion gate。

## Role Registry Slot

`Role Registry` 可以为 kernel 的 `proposer`、`gatekeeper`、`executor`、`stopper` 登记 profile 角色名并增加扩展角色，但不能降低四问下限。同一主体可以承担多个角色。

## Routing And Gate Registry Slot

`Routing And Gate Registry` 将 profile-owned task routes、Read Sets 和扩展 gates 绑定到 kernel role；未注册的 profile route 不能由 kernel 暗示为已加载。
