## Navigation

- Parent: [[Knowledge Base Standards/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]].
- Previous: [[Knowledge Base Standards/07 Sources and Accuracy/04 Evaluation and Source Quality|Evaluation and Source Quality]].
- Next: [[Knowledge Base Standards/07 Sources and Accuracy/06 Source Maintenance and Acceptance|Source Maintenance and Acceptance]].

## Time-sensitive Content

以下主题需要 `last_verified`：

- MCP、tool calling、model API 等协议和接口。
- 模型规格、context window、价格、限制。
- 框架版本和库行为。
- 安全建议、法规和行业标准。
- 云服务、vector database 和推理平台能力。

时效性结论必须注明验证日期，不能只依赖模型记忆。

## Formula Verification

公式检查至少包括：

- 符号是否定义。
- 下标、求和范围和归一化是否正确。
- 输入输出维度是否匹配。
- loss、metric 和 probability 的方向是否正确。
- 边界情况是否成立。
- 公式与正文解释是否一致。
- 数值例子是否能复算。

## Terminology Accuracy

- 全称、缩写和大小写必须准确。
- 区分相似但不同的概念，例如 parameter vs hyperparameter、state vs memory。
- 协议定义与常见工程习惯分开描述。
- 中文翻译不能改变英文术语含义。
- 专有名词的 canonical definition 遵循 [[Knowledge Base Standards/05 Terminology Standard|Terminology Standard]]。

## Uncertainty And Disagreement

当结论不是普遍事实时，应说明：

- 适用条件。
- 不同观点或实现。
- 当前证据强弱。
- 本文采用哪一种定义以及原因。

禁止把经验性趋势写成无条件定律。
