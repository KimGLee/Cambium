## Navigation

- Parent: [[kernel/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]].
- Previous: [[kernel/07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles|Source Hierarchy and Evidence Roles]].
- Next: [[kernel/07 Sources and Accuracy/03 Official and Cross-source Verification|Official and Cross-source Verification]].

## Claims Requiring Sources

以下内容必须有来源：

- 数学定义和重要公式。
- 算法原始机制、复杂度和理论性质。
- 协议角色、生命周期和安全要求。
- 框架、库、模型的当前能力和限制。
- Benchmark、性能、价格和版本数据。
- 安全攻击、风险分类和 mitigation 建议。
- 有争议或依赖条件的工程结论。
- 行业案例中的架构、指标、用户规模、成本和效果数据。
- 从官方文章或社区讨论综合出的新系统 / 运行控制模式。

常识性连接句不需要逐句引用，但不能用“常见做法”掩盖未经验证的事实。

## Source Placement

每个 Core / System 页面至少包含 `## Sources`。

推荐格式：

```markdown

## Sources

- [Descriptive source title](https://example.com)
- Paper title, authors, year.
```

时效性强、容易误解或直接引用官方行为的结论，应在相关段落附近放链接，同时在 Sources 汇总。

只有会被复用、比较或持续追踪的来源才建立 Source Note。普通 supporting citation 直接保留在 canonical note 的相关段落或 Sources 中即可。

## Claim Classification

来源驱动内容应区分：

- `Reported Claim`：来源直接报告。
- `Reasoned Inference`：根据来源推断。
- `Cross-source Synthesis`：比较多个来源后形成的判断。
- `Engineering Recommendation`：结合证据和约束给出的建议。

正文语气必须与 claim 类型和 `evidence_maturity` 一致。单一社区讨论不能写成“业界已经证明”，单一厂商案例不能写成“所有系统都应该”。
