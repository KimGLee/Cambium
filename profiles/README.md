## Profile Loading Contract

生效标准由 `kernel + one selected profile` 合成。Kernel 只引用稳定 slot 名；所选 profile 的 manifest 将这些 slot 绑定到具体实现。缺少当前任务所需 slot 时不得把组合标准判为完整加载。

## Profile Scope Slot

`Profile Scope` 必须声明目标、内容优先因素、排除清单、逻辑架构、knowledge spine、基础层目录和共享层名注册。它可以替换具体领域承诺，但不能覆写 kernel 的保全、ownership、迁移或质量不变量。
