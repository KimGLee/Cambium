# Tools 机读状态层与确定性检查脚本

本目录是 Standards v2.3 的"机读状态层 + 确定性检查脚本层"。所有脚本只用
python3 标准库；YAML 解析使用 `kblib.py` 中的受限子集解析器。
本目录不修改任何标准 `.md` 文件；标准原文是所有词表与字段清单的 owner。

## 脚本用途与典型调用

| 脚本 | 用途 | 典型调用 |
|---|---|---|
| `duplicate_check.py` | 跨文件重复段落候选检测；默认全库，维护轮与 governance 使用，批次与单页层面不再调用 | `python3 Tools/duplicate_check.py .` 或 `python3 Tools/duplicate_check.py . --scope "Agent Knowledge"` |
| `check_links.py` | Wiki link missing / ambiguous / heading 校验（09/03、09/05） | `python3 Tools/check_links.py . --receipts Tools/receipts/links.jsonl` |
| `check_vocab.py` | frontmatter 受控词表校验（08 域；词表取自 `vocab.yaml`） | `python3 Tools/check_vocab.py . --scope "Agent Knowledge" --receipts Tools/receipts/vocab.jsonl` |
| `check_language.py` | 中文优先语言候选检测（10/05；**只产生候选**） | `python3 Tools/check_language.py . --receipts Tools/receipts/lang.jsonl` |
| `check_proof.py` | Terminal Proof 完整性与零值条件校验（12/06），可与 Coverage Ledger 交叉对账 | `python3 Tools/check_proof.py proof.yaml --ledger coverage_ledger.yaml` |
| `apply_delta.py` | 串行合并时确定性应用 coverage delta（02/05 Concurrent Batches；--apply 写盘、越界页拒绝、自动备份） | `python3 Tools/apply_delta.py ledger.yaml delta.yaml --apply` |
| `stamp_cards.py` | Runtime Cards source_hash 盖戳与校验（00/03 Write-back Checklist；--check 只校验、--set-version 统一版本戳含 Card Index） | `python3 Tools/stamp_cards.py . --check` |
| `check_moc.py` | domain MOC Module Index 与实际 H2 headings 一致性候选检测（12/05；**只产生候选**）；维护轮与 governance 使用 | `python3 Tools/check_moc.py .` |

调用分工（一险一闸）：

- **批次关闭** = Batch-close Closed List（owner：12/07，七项封闭清单，含 check_links 与 check_vocab 全库）；
- **note 关闭** = `check_links.py` / `check_vocab.py` 带 `--scope 本页` 自查（不产 receipt）；
- **维护轮** = `check_freshness.py`（轮开始一次）＋ `duplicate_check.py`（全库或 `--scope`，候选入 candidates 池）；
- `duplicate_check.py` 与 `check_freshness.py` 不在批次或单页检查中调用。

公共约定：
- 人读 summary 输出到 stdout；机读 receipts 用 `--receipts PATH` 追加写 JSONL；
- 退出码：`0` = 全部 pass；`1` = 存在 fail；`2` = 无 fail 但存在 candidate。
- `check_language.py` 永不返回 1：按 10/05 Acceptance And Audit，语言信号
  只能产生 review candidates，最终判定必须交人工/模型审阅。
- `check_language.py` 默认整体跳过路径含 `Knowledge Base Standards/` 的文件
  （10/05 Standards Corpus Exemption）；标准语料在别的位置时用 `--exempt` 追加。

## Receipts 流转（12/07 Audit Evidence Reuse and Invalidation）

```text
脚本运行 --receipts 产出 JSONL receipt（receipt_id: audit-<tool>-<时间戳>-<序号>）
 -> receipt 进入 Audit Receipt Register / Batch Contract；Coverage Ledger 的
    pages[].gate_receipts 只记录最新有效 receipt_id
 -> 批次关闭前生成一次 AuditPlan（schemas/audit_plan.template.yaml）：
    冻结快照、diff changed_objects、解析 direct/dependency invalidation
 -> 通过 Reuse Gate 的旧 receipt 记入 reused_receipts（必须写复用理由）；
    受变更影响的记入 invalidated_receipts；新结果 supersede 旧 receipt
 -> Terminal Audit 对最终冻结快照运行 Batch-close Closed List（12/07），结果集引用写入
    Terminal Proof 的 full_deterministic_results；unresolved_invalidations 必须为 0
```

脚本 receipt 是轻量层（字段见 `schemas/receipt.template.jsonl`）；进入
Register 时由 AuditPlan 层按 12/07 补齐 scope / acceptance_predicate /
fingerprint 等完整 AuditReceipt 字段，脚本 receipt_id 作为 evidence_ref。

## schemas/ 模板（模板即 schema 文档）

- `coverage_ledger.template.yaml` —— Coverage Ledger（owner: 02/03）
- `progress_ledger.template.yaml` —— Progress Ledger（owner: 02/05、02/01、02/02）
- `receipt.template.jsonl` —— 脚本级 receipt（概念 owner: 12/07）
- `coverage_delta.template.yaml` —— 并发批次的状态增量（owner: 02/05 Concurrent Batches；integrator 串行合并时应用；含 `watermark_advance` 水位线传值字段）
- `watermark.template.yaml` —— 外部水位线（owner: 06/03 Stage 1 增量扫描；实例在 Tools/state/watermark.yaml，由维护批次推进）
- `audit_plan.template.yaml` —— AuditPlan（owner: 12/07 Incremental Audit Planning）
- `terminal_proof.template.yaml` —— Terminal Proof 28 个字段逐字段照抄 12/06；
  同时是 `check_proof.py` 必填字段清单的单一事实来源

## 受限 YAML 子集语法

所有 `.yaml` 状态文件只允许（`kblib.parse_yaml_subset` 能解析的即合法）：

- `key: value` 标量：字符串（可带引号）、整数、浮点、布尔、空值、
  内联空列表 `[]` 与简单内联列表 `[a, b]`；
- `key:` 之后缩进的 `- 项` 列表；列表项可以是一层平铺 map；
- 两级缩进嵌套 map（解析器递归实现，但标准约定只用两级）；
- `#` 注释（引号内的 `#` 不算注释）。

不支持：锚点/别名、多行字符串（`|` `>`）、flow map `{}`、tag、多文档、Tab 缩进。

## 编译产物声明

`vocab.yaml`（以及 interview cards 等一切由标准派生的机读物）是**编译产物**：
权威定义在各 owner 标准文件（文件头注释列出映射）。修订 owner 标准后必须
重新生成这些文件；不得只改编译产物而不改 owner，也不得把编译产物当作
标准原文引用。

## check_freshness.py（v1.8 新增）

知识时效检查：按 volatility 与 last_verified 计算 review_by，输出按 priority 排序的过期清单（维护轮候选输入）。维护轮专属；不在批次检查中运行。规则 owner：08/05 Freshness And Review Due。典型调用：`python3 Tools/check_freshness.py <vault_root> --as-of 2026-07-21 --receipts receipts.jsonl`
