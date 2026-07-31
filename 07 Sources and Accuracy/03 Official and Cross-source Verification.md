## Navigation

- Parent: [[Knowledge Base Standards/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]].
- Previous: [[Knowledge Base Standards/07 Sources and Accuracy/02 Claims Sources and Classification|Claims Sources and Classification]].
- Next: [[Knowledge Base Standards/07 Sources and Accuracy/04 Evaluation and Source Quality|Evaluation and Source Quality]].

## Official Company Source Policy

- OpenAI、Anthropic 等官方文章是一手 implementation evidence，适合分析其公开系统、实验和工程经验。
- 未披露组件不得通过常识补全成确定事实。
- 多家公司采用相似模式时，仍需比较任务、模型、Harness 和评估环境是否可比。
- Agent/Harness 的 P0 / P1 前沿问题应检查 OpenAI 与 Anthropic 是否都有直接相关的一手资料；存在直接相关一手资料时必须进行对照；没有相关资料时如实记录，不制造虚假对称。
- 厂商用语只有在边界稳定、可复用且通过术语审查后才提升为 canonical terminology。

## Cross-source Verification

综合多个来源时至少检查：

- 是否真正独立，还是互相转载同一结论。
- 是否使用相同定义、任务和评价维度。
- 一致之处是机制一致还是只有表面措辞相似。
- 冲突来自证据、环境、模型能力还是目标不同。
- 能否区分 vendor-specific implementation 与 generalizable pattern。
- 是否存在独立复现、反例或生产 postmortem。

来源数量不能替代证据质量。
