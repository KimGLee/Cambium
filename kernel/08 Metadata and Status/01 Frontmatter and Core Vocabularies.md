## Navigation

- Parent: [[kernel/08 Metadata and Status Standard|08 Metadata and Status Standard]].
- Next: [[kernel/08 Metadata and Status/02 Scope Level Depth and Priority|Scope Level Depth and Priority]].

## Purpose

本标准定义知识文件的机器可读元数据、优先级和成熟度，使超长任务可以追踪覆盖范围，而不是依赖文件是否存在。

## Frontmatter Schema

```yaml
---
type: concept
domain:
scope: domain-specific
level: intermediate
depth: core
authoring_status: drafted
learning_status:
priority: P0
coverage_disposition: required
deferred_reason:
next_batch:
aliases: []
prerequisites: []
evidence_maturity:
first_seen:
last_reviewed:
last_verified:
volatility:
review_by:
lifecycle: active
---
```

该 schema 是 kernel 基础字段集；所选 profile 可通过 `Vocabulary Extensions` 注册扩展字段和示例值。新建或实质重写页面按适用字段使用；是否批量应用到全部现有知识文件仍需进入单独 task contract。批量迁移前由 Coverage Ledger 保存权威状态。标准文件不保存容易过时的固定文件数量，实际规模由 inventory 生成。

## Type Vocabulary

允许值：

- `term`
- `concept`
- `process-flow`
- `algorithm`
- `metric`
- `system-component`
- `system-design`
- `comparison`
- `risk-control`
- `source-note`
- `research-synthesis`
- `case-study`
- `cheat-sheet`
- `overview`
- `standard`
- `management`
- `runtime-card`（仅用于 `Runtime Card Provider` 提供的编译产物，不属于知识笔记类型）
- `card-index`（仅用于该 provider 的编译产物层索引）

所选 profile 可以通过 `Vocabulary Extensions` 追加已注册的 type 值，但不能删除、重命名或重定义 kernel base 值。

类型职责见 [[kernel/03 Note Types and Ownership Standard|Note Types and Ownership Standard]]。

## Domain Vocabulary

具体 domain 值由所选 profile 的 `Vocabulary Extensions` 注册。

Domain 使用受控词表，不能随意创建大小写或同义变体。

## Freshness And Lifecycle Vocabulary

- `volatility`：允许值 `fast` / `slow` / `stable`。三档定义、domain 默认派发和复验间隔的 canonical owner 是 [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]]。
- `review_by`：由 `Tools/check_freshness.py` 生成的复验截止日期；脚本生成，只读，不手工填写。
- `lifecycle`：允许值 `active` / `retired` / `merged`，默认 `active`。退役与合并流程的定义 owner 见 [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]。
