## Navigation

- Parent: [[Knowledge Base Standards/11 Interview Content Standard|11 Interview Content Standard]].
- Previous: [[Knowledge Base Standards/11 Interview Content/03 Card Structure and Answer Levels|Card Structure and Answer Levels]].
- Next: [[11 Interview Content/05 Knowledge Links and Preparation|Knowledge Links and Preparation]].

## System And Project Deep Dive

企业对 Agent/Harness 项目的追问通常不是基础定义题，而是检查系统推理和证据链。System Design Card 和 Project Deep Dive Card 至少覆盖：

```text
Problem And Success Criteria
Why Agent / Why This Harness
End-to-end Execution Path
State Ownership And Persistence
Agent Coordination And Handoff
Tool And Permission Boundaries
Evaluation Provenance
Offline Replay / Regression / Backtesting
Failure Propagation And Recovery
Observability And Incident Diagnosis
Latency Cost And Scale
Alternatives And Rejected Designs
```

典型追问包括：

- “这个准确率或成功率是怎么得到的？”
- “Agent 之间如何分工、同步和合并结果？”
- “历史回放、回测和 regression suite 如何构建？”
- “中断后如何恢复，副作用如何回滚？”
- “如果模型、prompt、工具或数据变化，如何知道系统退化了？”

答案必须链接回 canonical evaluation、orchestration、state、reliability 和 case-study pages。Interview Card 负责表达顺序，不独立发明系统事实。

## Bilingual Policy

- 30 秒和 90 秒回答必须完整中英文。
- Follow-up question 使用中英文标题。
- 支撑推理以中文为主，保留准确英文术语。
- 每个需要实际口述的 follow-up 应提供英文回答或英文回答骨架。
- 中英文答案含义必须一致，不能英文版遗漏关键限制。
