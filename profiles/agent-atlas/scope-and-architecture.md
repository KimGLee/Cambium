## Navigation

- Profile: [[profiles/agent-atlas/profile|Agent Atlas Profile]].
- Kernel contract: [[kernel/01 Scope and Architecture Standard|01 Scope and Architecture Standard]].

## Target

知识库默认面向大厂 `Agent / LLM Systems Engineer` 技术面试和工程实践。整体叙事以 Agent 如何作出决策、Harness 如何让决策可执行、可控制、可观测和可恢复为主线。

以 Agent 和 Harness 为中心不等于删除、压缩或弱化基础知识。ML、DL、LLM、Retrieval、RAG、数据、评估、优化和系统基础仍然是完整知识层，必须能够独立解释其机制，并为 Agent 系统提供可追溯的前置知识。

它不是研究生课程全集，也不是所有 AI 论文百科。内容优先级由以下因素共同决定：

- 是否属于目标岗位核心能力。
- 是否是后续知识的前置条件。
- 是否能解释 Agent 决策或 Harness 执行背后的模型、数据与系统机制。
- 是否是高频面试问题。
- 是否影响生产系统设计和故障判断。
- 是否能连接多个已有模块。

## Excluded Scope

本 profile 当前不声明额外排除项。

## Logical Architecture

未来知识库采用“基础层支撑、Agent/Harness 组织、生产系统落地、评估与安全横切”的结构：

```text
Foundational Knowledge
  -> Agent Decision And Reasoning
  -> Harness Runtime And Control
  -> Production Agent Systems

Evaluation / Reliability / Safety / Governance
  -> cross-cut every layer

Source Notes / Research Synthesis
  -> continuously update the knowledge graph

Case Studies / Interview Preparation
  -> reuse canonical knowledge
```

## Knowledge Spine

Agent/Harness 主线按以下端到端链路组织：

```text
User Goal
 -> Agent Decision And Planning
 -> Harness Context And Policy
 -> Orchestration
 -> Tool And Environment Execution
 -> State And Artifacts
 -> Verification
 -> Recovery
 -> Outcome And Evaluation
```

## Foundation Preservation Rule

- Shared Foundations 解释数学、统计、优化、数据和通用系统概念。
- Machine Learning 解释监督、无监督、算法、评估、泛化和数据问题。
- Deep Learning 解释网络结构、训练、优化、表示学习和数值行为。
- LLM 解释 Transformer、生成、训练适配、上下文和推理机制。
- Retrieval、Vector Search 和 RAG 解释知识访问、检索、排序、grounding 和评估。

### Shared Foundations

负责可被 ML、DL、LLM、RAG 和 Agent 共同复用的知识：

- 数学、概率、统计、优化、信息论。
- 数据质量、预处理、采样和实验设计。
- 通用模型训练、评估和分布变化。
- 跨领域的系统、评估和安全术语。

未来可能需要补充 Math、Data 和 Experimentation 子体系。

### Model Knowledge

负责模型本身的原理和训练：

- `Machine Learning Knowledge`
- `Deep Learning Knowledge`
- `LLM Knowledge`

模型层不承担通用部署、平台治理或面试话术，但需要完整解释 Agent 系统所依赖的模型行为、限制和评估前提。

### Agent And Harness Core

这是知识库的组织中心，负责连接模型能力与可运行系统：

- Agent loop、planning、reasoning、reflection、delegation 和 stop condition。
- Harness runtime、tool registry、context、state、memory、workspace 和 sandbox。
- Permission、policy、budget、scheduler、checkpoint、retry 和 recovery。
- Single-agent、workflow、router、orchestrator-worker 和 multi-agent coordination。
- Tool Calling、MCP、filesystem、shell、browser 和其它 execution environments。

Agent 负责目标驱动的决策过程；Harness 负责把决策约束为可执行、可追踪和可恢复的运行过程。二者必须分别解释，也必须说明接口和耦合关系。

### Retrieval And Application Systems

负责模型如何组成应用：

- Retrieval、Vector Search、RAG、grounded generation 和 citation。
- Agent/Harness 如何使用这些能力完成开放式任务。

该层重点是组件交互和任务流程，而不是重复模型定义或检索算法定义。

### AI Systems Engineering

负责跨 ML、LLM、RAG、Agent 的生产基础设施：

- Serving、gateway、routing、queue、cache、storage。
- Deployment、CI/CD、model registry、feature/index pipeline。
- Reliability、SLO、capacity、cost、multi-tenancy。
- Secret、credential、policy、artifact、checkpoint、scheduler。
- Logging、tracing、metrics、incident response。

这是当前知识库最大的结构性缺口之一。

### Evaluation Safety Governance

负责跨系统质量和风险：

- ML、LLM、RAG、Agent 的 offline / online evaluation。
- Human evaluation、LLM-as-judge、A/B testing、regression testing。
- Privacy、permission、prompt injection、red teaming、audit。
- 数据访问、retention、合规和供应链风险。

Agent 专属安全内容可以继续由本 profile 注册的安全内容 owner 持有，共享安全概念由未来共享层持有。

### Architecture Case Studies

负责把多个领域串成完整系统，而不是创造新定义：

- Enterprise RAG。
- Customer Support Agent。
- Coding Agent。
- Data Analysis Agent。
- Model Serving Platform。
- Agent Evaluation Platform。

Case Study 必须基于已核验来源，区分公开事实、合理推断和知识库建议。具体准入过程见 [[Knowledge Base Standards/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]。

### Knowledge Intake And Research Synthesis

负责把官方文章、论文、postmortem、benchmark 和社区讨论转化为可维护知识：

- Source discovery and capture。
- Claim extraction and evidence classification。
- Cross-source synthesis and disagreement analysis。
- Knowledge gap and graph impact decision。
- Canonical note promotion and supersession。

来源本身不直接决定知识结构。一个来源可以更新多个页面，多个来源也可以共同支撑一个新的 canonical note。

### Interview Preparation

负责表达、题库、追问、系统设计面试、项目深挖和评分，详细规则见 [[Knowledge Base Standards/11 Interview Content Standard|Interview Content Standard]]。

## Shared Ownership Rule

| Kernel role | Agent Atlas layer |
|---|---|
| `Shared Foundation Layer` | `Shared Foundations` |
| `Production Systems Layer` | `AI Systems Engineering` |
| `Expression Layer Predicate` | `只描述面试表达` |
| `Expression Layer` | `Interview Preparation` |
| `Case Study Layer` | `Case Study` |
| `Source Note Layer` | `Source Note` |
| `Research Synthesis Layer` | `Research Synthesis` |

## Foundation Depth Requirements

- Knowledge mainline: `Agent/Harness`
- Application page: `Agent 页面`
- 数学与统计页面要解释定义、公式、假设、直觉、数值例子和边界。
- ML/DL 页面要解释训练或推理机制、数据要求、评估、失败和选择依据。
- LLM 页面要解释模型行为的来源，不能只写“Agent 会使用它”。
- Retrieval/RAG 页面要解释检索、排序、grounding 和 evaluation，不能退化为 Agent 工具清单。
- Agent/Harness 页面通过 wiki links 使用基础知识，只补充当前系统语境，不复制完整基础机制。

## Production System Reasoning Applicability

- Covered pages: `P0 / P1 Agent、Harness 和 AI Systems 页面`
