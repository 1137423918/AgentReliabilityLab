# MCP Agent 中断通信证据：服务器实测

2026-11-23，Linux CPU；MCP/SDK/TCP、私有报告和预算均真实，模型回复明确按脚本提供。**原版 SIGKILL 后没有wire文件；候选恢复了15条已落盘事件与两份完整回复，第三次未知请求仍扣额。** 不表示Agent工作流恢复或神经模型成绩。

[实现、边界与运行命令](../../docs/mcp-wire-journal.md) · [四文件补丁](adapter-wire.patch) · [汇总](summary.json) · [65项工件清单](artifacts.json)

## 已发生的验证

| 场景 | 原版 / 候选结果 |
| --- | --- |
| 第三次POST等待时SIGKILL | 原版已收到2份回复却无持久wire；候选15事件、3请求、2完整回复，结果文件仍不存在 |
| 清理阶段日志写入故障 | 候选报告故障，Agent仍关闭同一个已知上下文，独立查询确认关闭 |
| 标准库日志控制 | 8通过：部分写入、完整帧损坏、身份、边界、复用拒绝、CLI正文隔离等 |
| 原有MCP生命周期场景 | 10通过；正常/伪造事实/无读取/纯文字/状态错误/超时/取消/过期等范围保留 |
| Ruff与格式 | 四个修改文件通过 |

原版父控制器退出0表示按声明复现了“无持久wire”的失败；[原控制报告](baseline/controls/crash-control/report.json)的`passed=false`保留。候选父控制器退出0、源未变、自有子进程为0。两场都没有加载模型或使用GPU。原版44.830秒、候选138.471秒对应不同检查集合，不作速度对比。

候选12个独立运行的预算合计27次脚本模型POST，其中24次有完整回复正文、3次HTTP状态未知继续占额；246条wire事件只导出元数据。原版3次POST/1未知另列。8项日志控制与10项既有清理控制不计入此前130项核心快照；没有重跑历史9B或GPU实验。

## 来源与核对

- [原版协议](baseline/protocol.json) SHA `9a695099bcb359b4cb0ef4d3380b92ef5966a4d6b33a0911b7a6a5293cc27da2`；[候选协议](candidate/protocol.json) SHA `b1f78b35790358825aa011b8617f5331a0aee0e42a269e3dc3f0a0803b52b289`，运行前固定86 / 88份源码、配置与报告文件。
- [原版终态](baseline/run-report.json)与[候选终态](candidate/run-report.json)保留各阶段退出、内存采样峰值、范围和清理。候选复用同一独立SDK，原Python锁及原始源文件未改；依赖版本在运行前后相同。
- [标准库8控制日志](candidate/wire-unit-controls.log)、[原有九场](candidate/controls/cleanup-nine/report.json)、[合法业务错误场景](candidate/controls/cleanup-tool-error/report.json)分列。
- [强杀报告](candidate/controls/crash-control/report.json)证明原始两份正文逐字节匹配控制服务回复、随机认证头未进入日志、文件权限0600；[清理日志故障报告](candidate/controls/cleanup-failure/report.json)证明关闭及故障报告。
- `candidate/budgets/`保留12份原预算JSON，可校验checksum、请求正文SHA/长度、27次预留及3次未知。`candidate/wire-prefixes/`为对应的246事件摘要，模型请求SHA/长度与各自预算逐项对应。
- [原版适配器](baseline/adapter-before-wire.py)、[原版强杀控制](baseline/mcp_wire_controls.py)与`tested-source/`保留实际源码。强杀控制函数的AST未改；新增清理存储故障场景单列。

原始metadata tar为37,633字节、SHA `4da090204902bf119fd4c908e5b89642615e0bae1406ca93688748c4aa4465fa`，已核对56项服务器payload；连同服务器manifest及8份来源/补丁，公开清单共65项payload、305,230字节。`artifacts.json`不包含自身和本README。

只规范化服务器私有根目录和临时路径，原/公开SHA分列。协议中的执行器SHA应与清单的`original_sha256`比较；公开控制器用路径占位符，不是服务器的配置副本。模型请求预算文件与wire摘要不包含正文或审计能力；raw `wire-events.jsonl`、Agent结果中的回执/句柄和环境没有传回或公开。公开摘要不能独立重建原始正文的hash链或判断答案语义。

强杀场景由测试操作者关闭遗留能力，`agent_close_confirmed=false`；日志故障场景才有Agent自身关闭确认。没有把这两种清理当作同一件事，也没有重放请求、续期审计或退还未知额度。个人主页和历史PDF未改。
