## Navigation

- Parent: [[kernel/11 Expression Layer Standard|11 Expression Layer Standard]].
- Previous: [[kernel/11 Expression Layer/01 Expression Architecture and Separation|Expression Architecture and Separation]].
- Next: [[kernel/11 Expression Layer/04 Evidence-bound Expression|Evidence-bound Expression]].

## Expression Coverage And Readiness

表达层 readiness 是独立状态轴。字段、允许值与升级 gates 由所选 profile 注册，并服从 [[kernel/08 Metadata and Status/03 Status Axes#Profile Readiness Status|Profile Readiness Status]]；它不能从 `authoring_status`、`evidence_maturity`、学习进度、文件存在或其它状态轴自动推断。

一个可解析的表达产物 link 只证明目标已经映射，不能自动证明产物已完成、已审阅或可用于其目标场景。

一个表达产物可以绑定多个紧密相关的 canonical notes，但每个被绑定的 canonical note 都必须能导航到该产物，该产物也必须显式回链相应的 canonical owners。双向关系的 link semantics 见 [[kernel/09 Wiki Link and Navigation/02 Structural and Bidirectional Links#Bidirectional Knowledge Flow|Bidirectional Knowledge Flow]]。
