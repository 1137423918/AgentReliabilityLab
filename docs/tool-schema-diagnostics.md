# 已保存工具调用的 schema 诊断

在固定 Qwen2.5-3B / AgentRobustBench 真实生成结果上，分析“已解析调用是否符合声明的参数约束”。**结构有效不等于调用语义正确、官方匹配或真实工具执行成功。** 原实验没有重跑，官方评分保持不变。

## 数据与口径

输入来自[中断恢复评测](generation-recovery.md)：基线199条、Full32已完成的83条，Mixed32没有结果。累计284次尝试、282条已提交结果、2次未知；分析前后原账本SHA完全相同，新增模型调用和官方评分器调用均为0。

读取本次诊断的预测值前，固定[协议](../evidence/tool-schema-diagnostics/operator/protocol.json)、实现、13项边界控制与输入哈希。服务器实际使用Python3.11.4、jsonschema4.26.0、referencing0.37.0、rpds-py2026.9.1，两个CPU、nice19、2GiB地址空间；控制和分析均退出0，两阶段墙钟合计5.753秒，不含前置准入与源码复制。

输入包含Python类型别名，且没有声明JSON Schema版本，因此分开报告：

- **原始schema**：固定按Draft2020-12解释，不修复别名。源schema本身无效时标记无法评估，不当作模型违反约束。
- **上游FC投影**：使用固定上游`_normalize_tool_schema`函数，映射其支持的别名并约束根为object。仍不支持的`list(str)`不补修。原生成使用`use_fc=False`文本提示，**不能声称投影就是实际送给模型的schema**。

只消费原解析器保存的调用，不重新解析正文。空调用记为“未解析出调用”，不直接归为JSON语法错误；基准支持Python/XML/ReAct等多种格式。工具名必须精确匹配，名称不匹配也不直接等同于语义错误。没有gold填充、类型转换、默认值注入或参数修复。

未显式禁止的额外字段允许；`format`没有启用断言检查。参数要求为有限JSON对象，bool不当作integer；Draft2020-12允许整数值的浮点表示。使用显式本地registry，禁止远程引用下载；需要但无法解析的引用记为无法评估。[验证API与format约定](https://python-jsonschema.readthedocs.io/en/stable/validate/)、[引用配置与版本语义](https://python-jsonschema.readthedocs.io/en/stable/referencing/)。

## 结果

先清点全部输入工具，而非只挑模型实际调用的工具：199条样本共879个工具声明。原始视图中712个schema语法合格、167个不合格；投影后875个合格、4个仍不合格。语法合格不保证所有引用都可解析，也不保证声明充分表达了真实API约束。

| 已有结果的样本范围 | 保存的官方correct | 原始schema下全部调用有效 | 上游投影下全部调用有效 | 未解析出调用 |
| --- | ---: | ---: | ---: | ---: |
| 基线全部199例 | 118 / 199 | 105 / 199 | 158 / 199 | 23 / 199 |
| 基线匹配前83例 | 54 / 83 | 25 / 83 | 68 / 83 | 10 / 83 |
| Full32匹配前83例 | 50 / 83 | 21 / 83 | 64 / 83 | 16 / 83 |

“全部调用有效”要求至少一个调用、名称精确匹配、每次参数验证通过；其余样本包含空调用、源schema无法评估、名称不匹配或已知约束违反，**不能统称参数错误**。前83例是中断留下的固定前缀，仅覆盖32条BFCL与51条API-Bank，选择并非随机；没有完整Full199或Mixed对照，不推导因果训练收益。

基线199例的222个解析调用，在投影下分为：160个schema有效、5个违反约束（3个缺必填、2个类型问题）、3个源schema无法评估、54个工具名未精确匹配。名称不匹配分布于10例；其中一条记录有45个解析调用。调用级计数不代表独立样本数。原始视图有58个调用因源schema不合格无法评估，不把投影扩大覆盖误报成模型变好。

基线有41例全部调用符合投影schema，但官方correct仍为false；有1例官方correct为true、却不满足“全部调用精确匹配并有效”。这里只交叉统计已保存分数，不判断哪种评分应取代另一种。RoTBench21例中20例全部调用有效、官方correct仅2例，说明单独增加参数检查不足以解决任务匹配问题；没有真实工具执行，尚不能直接定位为某一种语义错误。

同一83例上，投影有效性为：两组均有效57例、仅基线有效11例、仅Full有效7例、两组均未满足8例。目前部分结果没有显示Full改进，不能用验证NLL下降代替自由生成能力验证。

## 实现与复查

[`Contract`与调用诊断](../agent_lab/tool_schema.py)接收schema与已解析调用，输出状态和约束关键字计数，不接收参考答案。[离线入口](../benchmarks/diagnose_saved_tool_calls.py)只从固定上游AST提取四个纯函数和加载字段常量，不导入模型客户端、解析器或评分器模块。13项控制覆盖必填/嵌套/数组/enum、额外字段、bool与integer、格式约定、本地及禁止的远程引用、无效schema、空调用、重复名称、falsey参数和输入不变性。

```sh
# 授权服务器；复用已按 extras/mcp-agent/uv.lock 建好的CPU环境。
extras/mcp-agent/.venv/bin/python benchmarks/test_tool_schema.py

# 需要原始私有进度；公开元数据不能重建预测或独立重评分。
extras/mcp-agent/.venv/bin/python benchmarks/diagnose_saved_tool_calls.py \
  --upstream /path/to/pinned-AgentRobustBench \
  --ledger /path/to/private/generation-progress.json \
  --source /path/to/identity-matching-source \
  --protocol /path/to/frozen/protocol.json \
  --output /path/to/new-output
```

入口拒绝身份变化，输出目录必须全新；本协议仅绑定这个快照，不能用于未来新数据。调用方仍需资源准入与监督，命令本身不提供资源隔离。核心运行器依赖不包含jsonschema，另建环境需要验证相应版本。

后续应分别研究输出协议、工具选择、参数结构与参数值匹配。当前仅新增诊断，没有接入模型反馈或训练奖励；新方法应先固定开发范围、预算和独立验证数据，不能针对这199例逐题修答案。

[汇总与逐例元数据](../evidence/tool-schema-diagnostics/README.md)保留分母、两种视图、原分数交叉表和服务器日志。完整提示、gold、参数、正文与权重留在私有服务器。个人主页保持冻结。
