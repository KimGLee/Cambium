## Navigation

- Profile: [[profiles/agent-atlas/profile|Agent Atlas Profile]].
- Parent: [[profiles/agent-atlas/interview/11 Interview Content Standard|11 Interview Content Standard]].
- Next: [[profiles/agent-atlas/interview/02 Card Granularity Coverage and Categories|Card Granularity Coverage and Categories]].
- Expression layer contract: [[kernel/11 Expression Layer Standard|11 Expression Layer Standard]].
- Kernel type contract: [[kernel/03 Note Types and Ownership/01 Note Type Catalog|Note Type Catalog]].

## Type Registration

- Kernel role: `Expression Layer Artifact`
- Profile type: `Interview Card`

## Interview Card

负责 30 秒、90 秒、追问树、误区、评分信号和自测。详细规则见 [[profiles/agent-atlas/interview/11 Interview Content Standard|Interview Content Standard]]。

## Purpose

本标准规定所有面试内容独立存放在 `Interview Preparation`，通过 wiki links 与知识体系连接，避免面试话术污染 canonical knowledge notes。

## Core Separation

```text
Knowledge Note = understand the subject
Interview Card = express and defend the subject
Question Bank = retrieve and practice questions
Roadmap = order preparation
Rubric = evaluate answer quality
```

核心知识页不再保存完整 `Interview Answer`、追问答案和自测题，只保留对应 Interview Card 的 wiki link。

## Folder Structure

```text
Interview Preparation/
├── Interview Overview.md
├── Competency Matrix.md
├── Roadmaps/
├── Topic Cards/
│   ├── Modeling Fundamentals/
│   ├── Machine Learning/
│   ├── Deep Learning/
│   ├── LLM/
│   ├── Retrieval RAG/
│   ├── Agent/
│   ├── AI Systems Engineering/
│   └── Evaluation Safety/
├── Question Banks/
├── System Design/
├── Project Deep Dives/
├── Cheat Sheets/
├── Mock Interviews/
└── Rubrics/
```

物理子目录按实际内容创建，不为尚无内容的类别建立空文件夹；目录迁移仍遵循 Migration Policy 和全库链接检查。

## Kernel Binding

- Extension point: `Expression Layer Artifact`
- Expression layer owner: [[kernel/11 Expression Layer Standard|11 Expression Layer Standard]]
- Profile manifest: `profiles/agent-atlas/profile.md`
