## Navigation

- Parent: [[kernel/05 Terminology Standard|05 Terminology Standard]].
- Next: [[kernel/05 Terminology/02 Ownership and Term Structure|Ownership and Term Structure]].

## Purpose

本标准规定专有名词如何拆分成可复用的 canonical Term Notes，避免主题页面反复解释同一概念，也避免知识库因过度拆分而碎片化。

## Core Rule

```text
Term Note owns the definition.
Concept Note owns the mechanism.
System Note owns component interaction.
Case Study owns application.
Expression Layer Artifact owns expression.
```

专有名词只在一个独立 Markdown 文件中完整解释。其它页面只说明该名词在当前主题中的作用，并通过 wiki link 引用。

## Extraction Criteria

满足以下任一条件时，应考虑创建独立 Term Note：

- 在两个或以上页面中使用。
- 完整解释需要超过两三句话。
- 有独立的形式化定义、符号、数据结构或生命周期。
- 有常见误区或容易混淆的相似概念。
- 会被多个顶层领域复用。
- 定义随协议、框架或版本变化，需要独立维护。

所选 profile 可以通过 `Expression Layer Entry` 注册扩展提取条件。

## Do Not Extract

以下内容通常不应单独创建文件：

- 只在一个页面中使用的局部变量或临时分类。
- 一句话即可解释的普通词。
- 没有独立知识价值的语法性名称。
- 拆分后只能形成两三句空壳的内容。
- 必须依赖当前页面上下文才有意义的局部概念。
- 只在单一文章中出现、边界不清且尚未被其它来源采用的新标签。

## Source-discovered Terminology

从官方文章、论文或社区讨论发现的新词，先判断它是：

- 已有概念的新名称。
- 特定厂商或实现的局部术语。
- 对多个现象的模糊总称。
- 边界清晰、可复用的新知识对象。

新词进入 canonical terminology 前需要：

1. 收集来源中的原始定义和使用上下文。
2. 检查其它来源是否使用同一词表达同一含义。
3. 检查现有知识库是否已有同义概念。
4. 明确包含什么、不包含什么。
5. 判断它应成为 alias、Research Synthesis 中的临时标签，还是独立 Term / Concept Note。

术语仍在演化时，应在 Research Synthesis 中维护 terminology mapping，并标注 provisional definition。不能为了跟随社区热点立即建立稳定 Term Note。
