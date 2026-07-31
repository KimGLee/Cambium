## Navigation

- Parent: [[Knowledge Base Standards/10 Writing and Formatting Standard|10 Writing and Formatting Standard]].
- Previous: [[Knowledge Base Standards/10 Writing and Formatting/01 Naming Language and Prose|Naming Language and Prose]].
- Next: [[Knowledge Base Standards/10 Writing and Formatting/03 Diagrams and Assets|Diagrams and Assets]].

## Mathematics

- 行内公式使用 `$...$`。
- 独立公式使用 `$$...$$`。
- 每个符号首次出现时解释含义和维度。
- 公式后说明直觉、假设和边界。
- 重要公式至少配一个数值或形状例子。
- 不把纯文本伪公式写成难以渲染的符号串。
- 全库数学格式需要统一检查。

## Tables

- 表格只用于需要统一维度比较的数据。
- 每一列维度必须明确且对所有行一致。
- 面向读者的表头、比较维度和解释性单元格遵循
  [[Knowledge Base Standards/10 Writing and Formatting/05 Chinese-first Technical Language#Tables（表格）|Chinese-first Technical Language]]；
  本页只负责表格结构和渲染边界。
- 表格中的 wiki alias 使用 `\|` 转义。
- 单元格内容过长时改为段落或多个 section。
- 不在表格中放难以渲染的多行代码块。

## Code And Pseudocode

- 使用 fenced code block 并标注语言。
- 知识库可以使用伪代码、接口和数据结构，不必复制大量 Python。
- 代码示例必须服务于机制解释。
- 示例应说明输入、输出、关键状态和错误路径。
- `Python Algorithm Agent Training` 中的代码不在本标准任务中重构。
