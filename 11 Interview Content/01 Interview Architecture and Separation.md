## Navigation

- Parent: [[Knowledge Base Standards/11 Interview Content Standard|11 Interview Content Standard]].
- Next: [[11 Interview Content/02 Card Granularity Coverage and Categories|Card Granularity Coverage and Categories]].

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

这是已批准的 logical structure。物理子目录按实际内容创建，不为尚无内容的类别建立空文件夹；目录迁移仍遵循 Migration Policy 和全库链接检查。
