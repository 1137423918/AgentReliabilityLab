# 只读检查运行进度

长时任务失败后，直接查看 SQLite 中某个 checkpoint tuple 可能遗漏增量写入的消息。此前一次人工诊断错误地数出零条消息；使用同一图结构的 `get_state` 重建后，才读到了实际保存的工具进度。`agent-lab-inspect` 把这个已使用的读法做成可重复执行的命令。

```sh
python -m agent_lab.inspect_run --run-dir /path/to/existing-run
# 安装当前版本后也可以：
agent-lab-inspect --run-dir /path/to/existing-run
```

命令核对 manifest 内任务的规范 JSON 哈希和基线提交，验证当前 worker 支持该任务，再以 SQLite URI `mode=ro`、`query_only=ON` 和一个读事务连接已有数据库。图只使用固定的空脚本模型构造 schema，调用 `get_state`，不调用 `invoke`，不根据 manifest 构造真实模型，也不运行文件工具、恢复任务、Git 命令或验收命令。

## 输出与边界

- 输出一行 UTF-8 JSON，最多 8192 字节。包含 checkpoint step、待执行节点、模型回复与工具结果/错误数量、工具名计数，以及当前虚拟文件的字节数、行数和 SHA256。
- 显示已有首屏索引标记数量，不将标记本身当作内容正确或模型利用索引的证明。详细模型试验仍需要逐条结果审计和最终验收。
- 不输出任务提示、模型文字、工具参数、文件源码、环境变量或凭据。超量文件和过长名称显式标明省略或截断；路径及哈希仍是用户数据，发布前应检查用途和范围。
- 文件是否属于任务允许集合单独标明；额外虚拟文件会出现在数量中，便于排查后来导出时的拒绝。不会为了让审计通过而删除它们。
- `artifacts_observed_not_revalidated` 和 `observed_result_status` 只是额外观察已有文件，**没有重新核验补丁、测试日志或验收**。运行中的这些文件可能与读事务中的 checkpoint 属于不同瞬间；事务只保证 checkpoint 内部一致。
- 数据库、任务缺失或身份不符时退出非零，不创建新数据库或初始化表。JSON 输入上限为 4 MiB；这不是任意规模的任务查看器。

这是受信任的本项目 worker 数据的查看命令，不接收不可信上传的 SQLite，也不保证跨 LangGraph/Deep Agents 版本兼容。当前实现依赖固定安装版本的图与 saver 行为；`is_setup=True` 用于阻止只读路径初始化表。按 [SQLite 官方说明](https://sqlite.org/wal.html#read_only_databases)，只读 WAL 连接仍可能创建 `-shm` 或空 `-wal` 协调文件；不承诺目录文件集合完全不变。任务数据和已有 WAL 帧不应由读者改变；运行中的 worker 仍可独立推进。SQLite WAL 不支持网络文件系统，也不能由不同主机并发访问。实际核对发现旧实验目录为 nfs4；旧记录只能支持当时观察，不能作为受支持部署的保证。后续新任务须使用本机受支持的状态目录，并补充启动预检。

## 如何验证

新增检查覆盖真实 Deep Agents 图的增量消息和编辑后版本、禁止模型生成、数据库及运行工件字节保持、缺失数据库不创建、篡改 manifest 提前拒绝、Unicode 多文件输出上限、空检查点失败，以及已有结果状态不冒充重新验收。完整套件和实际运行上的命令记录以服务器证据为准；不把这些接口检查写成新模型任务成绩。
