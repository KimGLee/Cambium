## Navigation

- Parent: [[Knowledge Base Standards/01 Scope and Architecture Standard|01 Scope and Architecture Standard]].
- Previous: [[Knowledge Base Standards/01 Scope and Architecture/02 Logical Architecture and Knowledge Spine|Logical Architecture and Knowledge Spine]].
- Next: [[Knowledge Base Standards/01 Scope and Architecture/04 Folder and Shared Ownership|Folder and Shared Ownership]].

## Foundation Preservation Rule

基础知识不是附录或速查表，必须保留独立的学习价值：

- Shared Foundations 解释数学、统计、优化、数据和通用系统概念。
- Machine Learning 解释监督、无监督、算法、评估、泛化和数据问题。
- Deep Learning 解释网络结构、训练、优化、表示学习和数值行为。
- LLM 解释 Transformer、生成、训练适配、上下文和推理机制。
- Retrieval、Vector Search 和 RAG 解释知识访问、检索、排序、grounding 和评估。

基础主题同样遵循 [[Knowledge Base Standards/04 Content Depth Standard|Content Depth Standard]]，不得因为它们是前置知识而只保留两三句定义。

当 Agent/Harness 页面依赖一个尚未讲清的基础概念时，应先补足 canonical foundation note，再继续系统页面；不得把缺失基础直接复制进 Agent 页面。

### Shared Foundations

负责可被 ML、DL、LLM、RAG 和 Agent 共同复用的知识：

- 数学、概率、统计、优化、信息论。
- 数据质量、预处理、采样和实验设计。
- 通用模型训练、评估和分布变化。
- 跨领域的系统、评估和安全术语。

现有 `Modeling Fundamentals` 属于这一层，但未来可能需要补充 Math、Data 和 Experimentation 子体系。

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

现有安全内容可以继续由 `Agent Knowledge/Safety Permission` 持有 Agent 专属部分，共享安全概念由未来共享层持有。

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
