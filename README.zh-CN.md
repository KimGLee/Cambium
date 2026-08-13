# Cambium

[English](README.md) | 简体中文

Cambium 是一套面向由 LLM Agent 维护的知识语料库的治理标准和参考工具集。
它定义了 Agent 如何加载规则、限定工作范围、维护权威归属、吸收来源、
管理长期变更，以及在宣称完成之前生成可审计的证据。

Cambium 不提供知识语料库、RAG 引擎或默认的领域策略。它治理的是操作方和
Agent 如何持续维护一个语料库。

## 架构

```text
effective standard = domain-neutral kernel + exactly one selected profile
```

内核负责跨领域规则。Profile 为一个具体语料库提供明确的范围、语言、架构、
语料库规划绑定与规模、优先级、来源、角色、表达产物、审计绑定、扫描项及
补充门禁。Profile 可以扩展已定义的接口，但不能替换、禁用或削弱内核。

| 组件 | 职责 |
|---|---|
| 内核模块（`K00`-`K13`） | 规范性的跨领域规则文本 |
| 运行时路由（`R01`-`R13`） | 针对具体任务的加载与执行路径；`Kxx` 与 `Rxx` 是彼此独立的命名空间 |
| Read Sets | 当 Runtime Card 要求回读时使用的、特定于路由的来源加载边界 |
| Runtime Cards | 由内核拥有、为日常 Agent 执行编译的快捷入口；绝不是第二套规则来源 |
| 选定的 Profile | 采用方针对 Profile 接口给出的具体答案 |
| 采用方运行时命名空间（`.cambium/`） | Coverage 对象状态、权威的 Required Queue、任务级 Progress、以哈希绑定的复杂批次 Work Specs、包括活动任务 Standards 采用在内的受控计划、delta、receipt 和派生报告 |
| 工具 | 确定性检查、受控状态写入器、schema、receipt 及派生/编译产物生成器；不负责最终的语义判断 |

在内核模块命名空间中，[K02 知识工作构建](<kernel/K02 Knowledge Work Construction Standard.md>)
负责知识对象清单、Coverage 语义、Corpus Planning、架构与依赖规划、
知识批次生产及迁移安全。[K13 任务运行时与执行控制](<kernel/K13 Task Runtime and Execution Control Standard.md>)
负责持久运行时命名空间、Task Contract 与任务状态、Guidance/Amendments、
Progress Ledger、Required Queue、批次转换、以哈希绑定的批次 Work Specs、
受控的活动任务 Standards 采用状态写入、完成绑定、交接及中断恢复。K12 仍是
唯一负责判定哪些已变更 Standards 谓词会影响活动任务、以及哪些门禁必须重跑
的模块。这一边界将知识对象的处置与批次/工作单元生命周期分离，同时要求两个
状态层相互核对一致。

日常工作从 Runtime Cards 开始。当某张 Card 不完整、有争议，或不足以处理
例外时，Agent 回读它的 Read Set 以及其中引用的内核模块。规范性来源文本
始终优先。

本仓库有意保持未实例化状态。采用方特定的活动状态位于
[`K00/03 Standards Governance`](<kernel/K00 Standards Control/03 Standards Governance.md>)，
其中仍含占位符，并且尚未选定任何 Profile。因此，本仓库没有为某个特定知识
语料库定义活动标准，也不分发特定于 Profile 的 `Tools/vocab.yaml` 或虚构的
`.cambium/state/`。

## 执行模型

Cambium 将持久工作单元与执行上下文分离。

- **批次（batch）** 是一个独立验收的工作单元，拥有自己的 manifest、依赖、
  receipt、delta 和生命周期。
- **Required Queue** 是与模型无关的持久所有者，负责这些批次 manifest、
  它们的确定性顺序、依赖、hold 和生命周期。
- **Agent** 是被分配执行工作的上下文。一个 Agent 可以依次执行多个批次，
  而相互隔离的 Agent 可以并发执行互不相交的批次。
- **subagent** 是由运行时创建的子执行上下文。它不是独立的 Cambium 工作单元
  或权限类别，可以担任执行者、研究者或独立审阅者。担任独立审阅者是这些角色
  中边界最窄的一种：[`K12/12 Substantive Correctness
  Review`](<kernel/K12 Quality Assurance/12 Substantive Correctness Review.md>)
  要求 subagent 以干净上下文启动，不携带作者上下文，其输入只能是笔记正文及其
  Sources。继承作者上下文的普通子上下文不满足该要求。
- 一个逻辑上的 **integrator** 独占控制
  [`K13/10 Batch Admission Transitions and Serial Integration`](<kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration.md>)
  中指定的共享状态：Guidance 处置、Queue 结构修订、Queue 状态转换、Contract
  变更、Standards 采用、批次激活及合并。该模块给出完整枚举；这里的列表只是
  面向读者的摘要。

活动批次的并发上限不是 Agent 数量上限。并发执行者生成隔离的批次输出；
integrator 逐个合并这些输出，并在每次合并后运行全局检查。

三个机器可读的控制对象被刻意赋予不同职责：

| 状态对象 | 负责内容 |
|---|---|
| Coverage Ledger | 知识对象、处置、权威所有者和对象侧的批次分配 |
| Required Queue | 批次/工作单元 manifest、顺序、依赖、生命周期、hold 和转换证据 |
| Progress Ledger | Task Contract、整体任务状态、Guidance/Amendments、检查点和已接受的 Queue 指纹 |

它们需要相互核对一致，而不能被当作可互换的任务列表。

## 仓库结构

| 路径 | 内容 |
|---|---|
| [`kernel/`](kernel/) | 跨领域标准、Read Sets 和编译后的 Runtime Cards |
| [`profiles/README.md`](profiles/README.md) | 权威的 Profile 槽位接口与填写规则 |
| [`profiles/_template/`](profiles/_template/) | 可复制并填写的领域中立表单；不是可运行或默认的 Profile |
| [`profiles/examples/`](profiles/examples/) | 非规范性的完整参考；示例不是采用起点，也不能被直接选用 |
| [`Tools/`](Tools/) | 标准库 Python 检查、schema、receipt 和编译产物生成器 |
| [`ROADMAP.md`](ROADMAP.md) | 非规范性的实现方向；不代表当前能力 |

内含的 [`Agent Systems Atlas`](profiles/examples/agent-atlas/README.md)
Profile 是答案形式和具体程度的示例。它不是 Cambium 的默认配置，也不包含
Atlas 知识语料库。

## 采用方运行时状态

长期、可恢复或多批次工作在采用方仓库中使用一个固定命名空间。每项任务首先
检查该命名空间是否已经存在，因为一个看似有界的新请求可能进入了此前持久任务
被中断的仓库：

```text
.cambium/
├── state/       # Coverage, Required Queue, and Progress
├── work_specs/  # immutable restricted-YAML contracts for complex batches
├── deltas/      # worker deltas and restricted-YAML controlled-operation plans
├── receipts/    # deterministic and transition evidence
├── reports/     # derived human-readable views
└── tmp/         # recovery locks and incomplete-write metadata
```

`state/`、`work_specs/`、`deltas/` 和 `receipts/` 是持久的。报告是投影，
而不是工具输入；`tmp/` 被 Git 忽略，残留的写入器锁在其操作完成核对之前仍是
恢复证据。Cambium 在 `Tools/schemas/` 下发布 schema；一致性 fixture 套件仍处于
规划中而尚未随项目发布，当前仓库也不包含这类套件（参见
[`ROADMAP.md`](ROADMAP.md) 中的 `Observability And Conformance`）。采用方在
选定 Profile 并定义任务后，使用 `Tools/init_state.py` 创建自己的运行时状态。该工具
要求显式提供 objective 与 exclusions，不会凭空编造 Required 工作，也不会覆盖任何
已有的 `.cambium/` 命名空间。
如果该命名空间已存在，重启或新分配的 Agent 会先运行
`Tools/check_queue.py . --resume-status`，以发现已记录的任务、它的 `build` 或
`maintenance` 完成语义、检查点绑定、最新任务转换、进行中的批次、待处理的
控制输入/delta、适用的完成区块、maintenance candidate SHA/partition 及先前的
完成锚点、hold、写入器锁证据和准确的机器可读 `next_action`。完整的开放批次
交接会报告为 `admit-delta`；没有 apply receipt 的 merge-ready 批次会变为
`apply-delta`；已应用但没有当前 close bundle 的批次会变为
`run-batch-close-gate`。只有当前 bundle 才授权四 ID 的
`close-applied-batch` 操作及其可精确复制的关闭命令。这可以防止新的 Agent
上下文误把中断的仓库当成尚未使用的仓库。

## 当前实现边界

内核和工具现在提供持久的任务及 Required Queue 状态、可选的以哈希绑定的复杂
批次 Work Specs、显式的 Global Map / Capability Matrix / Gap Register 验证，
以及确定性的初始化、编译、验证、任务/批次转换、活动任务 Standards/Profile
采用、中断恢复、build Terminal 闭合、有界 maintenance 闭合和派生报告
生成。页面级契约族同样具有确定性：组合后的 frontmatter 页面契约
（K08/06-08，建议性的 `page-contract` 门禁）、Structure Registry 解析
（K01/05-06，`structure-registry` 门禁）及其 marker-block coverage 投影，
以及页面边界契约（K08/09，建议性的 `boundary-contract` 门禁）及其由工具
拥有的边界投影区块。
它们不会调度 Agent。执行者调度、工作区隔离、事件投递和 integrator 循环仍须
由采用方运行时或人工操作方提供。

随项目提供的 Amendment 接口首先针对准确的当前状态登记一项已批准的操作决策，
随后在范围/处置重新规划或批次取消事务中使用该授权。待处理的 registration
receipt 授权当前执行；在写回验证完成后，它们只用于证明历史。另一个独立的
Standards 采用事务仅同步三项 Standards/Profile 标识、Progress load set 及结构性
Queue 修订，同时保留任务以及每个批次的生命周期/hold。Queue 实体化后，若主机
没有提供等价的受控写入器，则对其他任何 Task Contract 字段的变更都会被拒绝；
基线恢复路径是暂停或取消当前任务、保留其运行时，并启动一个后继任务。目前有
一个非范围 Contract 字段拥有受控写入器：`apply_contract_amendment.py` 在单一
锚定事务中修订 Contract 的 `policy_exceptions`（K00/07 有界政策豁免登记）。
覆盖其余非范围字段（objective、acceptance、timing）的通用写入器仍属于路线图
工作。

这些写入器只接受当前公开的 schema 和 receipt 协议。采用方已有的运行时如果
包含旧版或未登记的操作性 Amendment 状态，必须在公共执行路径之外完成转换后
才能加载；Standards 采用不会猜测或静默升级这些状态。

Profile 设置由 Agent 基于显式契约主导：`scaffold_profile.py` 按受版本控制的
白名单创建候选包，机器可读的访谈契约（`profiles/interview.yaml`）承载任何
协助 Agent 要提出的问题并把操作者确认的答案投影进对应文件，`check_profile.py`
验证结果。在文本编辑器里按同一套契约手工填写仍是无 Agent 的后备路径。此版本
不捆绑自动化的访谈 runner；无论由谁主持访谈，产出都只是候选——不发明领域
政策、不批准 Profile、也不选定它。规划中的便捷层与运行时层见
[`ROADMAP.md`](ROADMAP.md)。

Cambium 的 receipt 与 Terminal Proof 在采用方仓库的本地信任边界内运作。
随项目提供的检查可以验证 receipt 结构、声明的 producer 与版本标签、与当前
状态和内容准确绑定的 SHA-256、转换链一致性，以及证据是否过期。这些哈希是
完整性绑定，而不是签名：如果没有外部签名或受控执行系统，Cambium 无法认证
究竟运行了哪个可执行文件、哪个操作系统账户提供了 actor 标签，或记录的
审阅者是否确实是另一个人或进程。能够重写仓库、工具和证据的攻击者可以构造
一套内部一致的历史。因此，基线可以检测意外漂移、不完整转换及过期或不一致
的证据；更强的来源可追溯性需要本仓库之外的控制措施。

## 采用 Cambium

无论目标语料库已经存在还是将从零开始构建，Profile 采用都遵循同一套流程，
Cambium 在设置期间也从不创建语料库。两者只有一处不同，见下面的**采用进空
语料库**：已有页面的语料库按它**包含什么**来描述，还没有页面的语料库按有界
founding **将要创建什么**来描述。首先确认语料库位置与 Profile ID，然后为该
语料库 scaffold 一个候选 Profile。不要直接编辑共享模板，也不要复制示例作为
起点。

```text
python3 Tools/scaffold_profile.py . --profile-id my-profile           # dry-run
python3 Tools/scaffold_profile.py . --profile-id my-profile --apply
```

scaffolder 精确复制 [`profiles/template-files.yaml`](profiles/template-files.yaml)
中的白名单、派生机械的身份与自路径单元格，并拒绝已存在的目标；手工按白名单
复制是无 Agent 的后备路径。

模板出厂即预关闭：所有具备合法退出态的槽位开关已处于关闭态，运营性答案预填待
确认，只保留模板无法替你回答的决策。若想现在就逐一回答全部开关，采纳面试会在
同一次填充中走完这些关闭项。两条路径产出的 Profile 同等合规；填充深度契约见
[`profiles/README.md`](profiles/README.md)。

1. 回答 `profiles/my-profile/` 中剩余的 `TODO(profile)` 决策——通过
   [采纳访谈](profiles/interview.yaml) 或手工填写。保持 `profile_id`
   与目录名相同，并以 [`profiles/README.md`](profiles/README.md) 作为接口权威。
2. 验证填写后的副本：

   ```text
   python3 Tools/check_profile.py profiles/my-profile
   ```

3. 通过完整的 [`R09 Standards Governance Read Set`](<kernel/Read Sets/R09 Standards Governance Read Set.md>)
   执行初始采用。在 K00/03 中记录采用方的 Standards version、状态 `approved`、
   effective date 以及准确的 `profiles/my-profile/profile.md` 路径。目录存在、
   Profile discovery、示例或生成的文件都不能选定 Profile。
4. 这些候选状态字段就位后，组合 Profile vocabulary 与 frontmatter 页面契约，
   并为已采用的 Standards version 重新生成 Runtime Cards：

   ```text
   python3 Tools/compose_vocab.py
   python3 Tools/compose_page_contract.py
   python3 Tools/stamp_cards.py . --set-version YOUR_VERSION
   python3 Tools/stamp_cards.py . --check
   ```

5. 在开始语料库内容工作前完成 R09 治理门禁。[`Tools/README.md`](Tools/README.md)
   记录了各项命令、receipt 和退出语义；工具成功本身不能证明完整的治理门禁已经通过。

### 采用进空语料库

Profile 里有几项答案是在描述语料库，而没有页面的语料库还给不出它们。这不需要
放宽任何合同，也不需要任何尚不存在的机制——空语料库需要的是先被**建立起来**，
而建立它是普通的创作工作。

- **残留扫描**。它的 matcher 通常取自真实页面携带的字符串。没有页面时，就
  **声明**你将使用的结构类，并由有界 founding 在接受根下创建一个携带它的
  页面——残留见证页，在任何批次或运行时状态存在之前写成。生产扫描
  会拒绝一个在仓库里认不出任何文件的配置，所以声明的结构类必须被物化；正对照
  只证明 matcher 与 `mandated_headings` 自洽，在空仓库上照样通过。
- **Coverage**。尚未创建的知识对象同样有记录，所以第一份 Queue 是从你**打算
  建**的页面编译出来的，而不是从你**已经有**的页面。这些计划中的页面通过
  大规模任务里由用户确认的 Task Plan 进入 Coverage；Profile 永远不生成
  Coverage。
- **Corpus Planning** 在初始采用时保持 `not-applicable`，其理由授权有界
  founding，并**推迟**而非禁止大规模工作。Global Map 点名的是已存在
  的 canonical owner，所以 founding 创建出属主之后，这份规划才通过第二次
  R09 修订变得可证明；而
  [`K00/13`](<kernel/K00 Standards Control/13 Runtime Admission and Recovery.md>)
  只在规划已证明的前提下准入大规模工作。这是下面那条顺序，不是阻碍。
  （已有页面的语料库跳过这一步：属主已存在，初始采用即可直接配置该槽。）

### 先建立语料库，再构建它

创建一个空语料库的头几页是**有界创作工作**。它不是 `K00/13` 所准入的大规模
创建，因此既不选 R11 也不需要 Corpus Planning；而且既然有界，它根本不初始化
`.cambium/` 运行时状态。

1. 通过 R09 采用 Profile。
2. 为 `Profile Scope` 的每一层各写出至少一个 canonical owner，加上面试中声明的
   残留见证页（语义自然兼容时，一个页面可以同时承担 owner 与 witness；不能
   为了少建文件而强行合并）。普通的单页与模块路线；没有 Queue、没有
   Coverage、没有准入门禁。
3. 属主落盘之后，由第二次 R09 修订配置 Corpus Planning 槽：R13 在该开放修订
   内，针对 `configured` 的 after Profile 准备 Global Map、Capability Matrix
   与 Gap Register
   （[`K02/03`](<kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md>)
   的 candidate preparation）；修订以采用该 after-image 闭合时，它们才成为
   权威。
4. 大规模构建是随后的那个任务：初始化运行时状态、过 `K00/13` 的准入条件、编译
   Queue、跑批次。

从第 4 步起，那几页就是普通的 Required 对象，与其余页一样进批次复查。没有任何
内容被建两遍；这条顺序的代价是一个任务边界，加上把槽配置成 `configured` 的那
一次 R09。

复制、填写、验证 Profile 或记录 manifest 路径本身都不会激活它。只有完整的
R09 初始采用变更闭合后，该 manifest 才会成为内容工作的选定 Profile。应验证
填写后的副本，而不是 `_template`；组合后的 vocabulary 在采用前并不存在。

## 将新的 Standards 版本采用到活动任务中

R09 治理 Standards 修订，并记录其准确的 changed predicates。当现有
`.cambium/` 任务仍冻结在此前的 Standards/Profile 标识上时，R09 使用
[`Tools/schemas/standards_adoption_plan.template.yaml`](Tools/schemas/standards_adoption_plan.template.yaml)
生成一个 restricted-YAML 计划：

```text
.cambium/deltas/standards-adoptions/<adoption-id>.yaml
```

该计划是任务的权威机器修订记录。它绑定完整且已批准的 K00/03 字节、`kernel/`
与选定 Profile 目录在变更后的确定性快照，以及准确的 changed-predicate、
invalidated-evidence dimension/boundary 与 rerun scope。不存在第二份修订 YAML
或散文式采用副本。

R07 执行或恢复该计划。先进行 dry-run；只有 integrator 可以写入：

```text
python3 Tools/adopt_standards.py . \
  --plan .cambium/deltas/standards-adoptions/SA-001.yaml

python3 Tools/adopt_standards.py . \
  --plan .cambium/deltas/standards-adoptions/SA-001.yaml \
  --apply --actor-role integrator
```

写入器只接受 `active` 或 `paused` 任务。如果一个 build 任务已处于
`completion-candidate`，先使用合法的 Task 转换使其回到 `paused` 或
`active`；如果新的 Standards 无法验证已绑定的 Work Spec，则在采用前通过其
归属流程升级该 specification。相同的准备工作会正式回滚任何受影响的
`merge-ready` 批次，并将每个受影响的 `open` 批次置于
`revalidation-required` 下；写入器会验证生命周期/hold 变更，但不会创建它们。
随后，该事务保留 Task 状态以及每个批次的状态/hold，保持 Queue 成员及顺序不变，
递增结构性 `queue_revision`，更新同步的 Contract/Standards/Profile/load set，
并追加可恢复证据。历史 receipt 的字节保持不变。

每次采用都要求 staged after bytes 立即满足 Queue 一致性。Changed predicates
会选择任何额外的延迟证据边界：batch-close 或 Terminal 门禁仅在到达该边界时
重跑，不会阻塞此前不相关的工作。历史上已关闭的转换仍按生成它们时的标识进行
验证；已声明失效的证据不能在新谓词下被重新用作当前证据。当前使用的 receipt
catalog 会排除已提交采用所累计的每一个 invalidated-evidence receipt ID。

该计划和仅追加的 receipt 是 Agent 接口。Cambium 不创建或使用持久的 Markdown
采用报告。

## 启动受治理任务

初始采用完成后：

```text
Standards Overview
  -> Card Index
  -> R01 Core Bootstrap Card + the task-specific Runtime Card
  -> selected-profile bindings
  -> Read Set and kernel source read-back when required
  -> applicable gates, deterministic checks, and receipts
```

从 [`Standards Overview`](<kernel/K00 Standards Overview.md>) 和
[`Kernel Runtime Card Index`](<kernel/Cards/Card Index.md>) 开始。只加载当前
任务所需的路由、Profile bindings 和来源模块。仅当 Card Index 的触发条件适用时
组合其他路由；它们不会替代工作本身对应的路由。

对每项任务，先检查目标仓库中是否存在 `.cambium/`。如果存在，不要写入内容
或状态，也不要初始化或覆盖它：先检查并核对其中的当前任务。如果不存在，则只有
长期、可恢复或多批次任务才初始化它；有界工作继续执行而不创建空的运行时状态。

```text
# Existing runtime state: always inspect before writing.
python3 Tools/check_queue.py . --resume-status

# No .cambium/ exists and persistent state applies: initialize once.
python3 Tools/init_state.py . \
  --task-id YOUR_TASK \
  --objective "State the concrete outcome this task must achieve" \
  --exclude "State one explicit out-of-scope boundary" \
  --completion-semantics build \
  --scope-version s1 \
  --standards-version YOUR_VERSION \
  --profile-manifest profiles/my-profile/profile.md \
  --apply
```

对于语料库构建工作，选择 `build`；此类工作通过 `completion-candidate`、R08
和 Terminal Proof 闭合。对于 R10 budget-envelope 运行，选择 `maintenance`；
此类工作通过 maintenance completion gate 闭合，而不进入 `completion-candidate`。该选择是
必填项，并被冻结在 Task Contract 中；初始化从不猜测它。一个有界的单笔记任务
不会仅为记录此选择而初始化 `.cambium/`。

报告的写入器锁可能属于仍在运行的写入器，也可能来自中断的写入。在确认没有
写入器残留，并对状态文件、receipt、revision/fingerprint、待处理 delta 及任何
已记录的 archive move 完成核对前，不要删除它。JSONL receipt 仅可追加；不确定的
receipt append 会保留锁，而不是删除或重写证据。新任务不会复用旧命名空间，
即使旧任务已完成或已取消；必须通过显式的 archive/rollover 流程处理该历史。
Cambium 尚未实现 rollover 自动化。

确认当前任务已知且有效后，将 Required 对象清点到 Coverage 中，声明显式的
`batch_specs`，编译 Queue，并在激活批次前运行 `check_queue.py`。简单的
单笔记工作无需仅为满足形式要求而创建空 Queue。初次编译在 Progress 中存储一份
不可变的 origin receipt；后续同范围重新规划使用 staged Coverage proposal，
登记其已批准的准确 diff，并且绝不要求预先编辑权威 Coverage。

大规模构建、迁移或持久多批次语料库工作还需要配置选定 Profile 的
`Corpus Planning` 槽位。通过 R13 维护其 restricted-YAML Global Map、
Capability Matrix 和 Gap Register，然后运行 `check_corpus_plan.py`。Agent 使用其
确定性 JSON 投影和独立的 semantic-acceptance 状态，而不是存储复制的报告。
一个受 Profile 绑定的权威角色使用 `record_corpus_acceptance.py`，从
restricted YAML 记录已接受/已拒绝的 Capability 决策；证据采用仅追加 JSONL。
这些产物提供显式的 topology、capability、priority、evidence 和 gap-handoff
输入。它们不调度 Queue 工作，也不替代 Coverage。

简单批次记录 `work_spec_path: null` 和 `work_spec_sha256: null`。
只有复杂批次才会直接在 `.cambium/work_specs/` 下，根据
`Tools/schemas/batch_work_spec.template.yaml` 创建 restricted-YAML 契约，然后在 Queue 编译前将该
准确路径和 SHA-256 绑定到 Coverage 的 `batch_specs` 中。Work Spec 承载批次
特定的 outcome、instructions、acceptance conditions 和 constraints；Queue 顺序、
生命周期、hold 及 receipt 仍保留在 Required Queue 中。

`init_state.py` 不推断任何内容，因此任务合同的五个选择字段与 Coverage Ledger
建出来都是空的。**不要手工填写它们。** 依据
`Tools/schemas/task_plan.template.yaml` 写一份计划，确认之后再应用：这份事务
本身就是「当时确认了什么」的记录，手改的状态不是。尚未创建的对象同样要写进
计划——Queue 是从任务打算构建的内容编译出来的，不只是文件系统已有的内容。

计划里写的是路由，不是路径。`selected_card_paths`、`selected_read_sets` 与
`loaded_module_paths` 由 `selected_route_ids` 经规范索引与加载边界的传递闭包
解析得到；只选 R01 一条就会闭合到其余全部路由与一百多个模块。只有在需要加入
profile 补充 Read Set（它没有可解析的注册表）时，才手写路径。

```text
# 一份已确认的计划填入任务合同与 Coverage（K13/18）。
cp Tools/schemas/task_plan.template.yaml \
  .cambium/deltas/task-plans/TP-001.yaml
# 编辑它，替换掉每一处 TODO(plan)，然后先 dry-run 再 apply：
python3 Tools/apply_task_plan.py . --plan .cambium/deltas/task-plans/TP-001.yaml
python3 Tools/apply_task_plan.py . --plan .cambium/deltas/task-plans/TP-001.yaml --apply
# 它会打印下一条命令，Queue 的 revision 与 SHA 已经填好：
python3 Tools/compile_queue.py . --apply --actor-role integrator \
  --expected-queue-revision 1 \
  --expected-sha256 SHA_PRINTED_BY_APPLY_TASK_PLAN
python3 Tools/check_queue.py .
python3 Tools/render_queue.py .
```

生命周期写入在未提供 `--apply` 时是 dry run；apply 还要求使用状态工具打印的
当前 revision/fingerprint。转换命令、退出码 2 的 hold、receipt、Amendment 登记
与执行、中断恢复及两种完成路径，参见 [`Tools/README.md`](Tools/README.md)。

## 许可证

Cambium 按路径为其维护并纳入版本跟踪的发行文件分配许可证：

- [`Tools/`](Tools/) 下的软件和实现材料采用 Apache License 2.0。
- [`kernel/`](kernel/)、[`profiles/`](profiles/)、本 README 及
  [`ROADMAP.md`](ROADMAP.md) 下的标准、Profile 材料和项目文档采用 CC BY 4.0。

权威的适用范围见 [`LICENSE.md`](LICENSE.md)，署名指南见
[`ATTRIBUTION.md`](ATTRIBUTION.md)，完整许可证文本见
[`LICENSES/`](LICENSES/)。

采用方生成的 Profile、vocabulary、receipt 和运行时证据不会仅仅因为存储在这些
目录中就自动适用 Cambium 许可证。
