# Card Structure And Answer Levels

## Required Card Structure

Every Interview Card contains these reader-facing sections in this order, with category-specific additions after `Deep-Dive Follow-up Tree（深挖追问树）` when required:

```text
Scope（范围）
Knowledge Prerequisites（知识前置）
Core Knowledge Links（核心知识链接）
30-Second Answer（30 秒回答）
  English（英文回答）
  中文
90-Second Answer（90 秒回答）
  English（英文回答）
  中文
Deep-Dive Follow-up Tree（深挖追问树）
Follow-up Answers（追问答案）
Common Misconceptions（常见误解）
Strong Answer Signals（强回答信号）
Weak Answer Signals（弱回答信号）
Comparison Questions（比较类问题）
Scenario Questions（场景类问题）
Self-test Questions（自测问题）
Related Interview Cards（相关面试卡片）
```

## Thirty-second Answer

The 30-second answer identifies the topic, the problem it solves, its core mechanism or decision, and the main value or boundary. It is a direct answer, not an outline of sections to be covered later.

## Ninety-second Answer

The 90-second answer forms one coherent chain:

```text
Problem
→ Core mechanism
→ Main components or decision steps
→ Key tradeoff or failure boundary
→ Representative use case
```

It must remain supportable by the Card's canonical links and cannot introduce an unsupported claim merely to improve fluency.

## Deep-dive Follow-ups

A Card that is required for a P0 or P1 topic provides at least three levels of substantive follow-up. The branches test causes, assumptions, alternatives, failures, evidence, and production consequences; every posed follow-up has an answer or an explicitly bounded unknown. Scoring signals and self-test questions must distinguish a defensible answer from keyword recall.
