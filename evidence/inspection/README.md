# 只读运行审计证据

[命令与边界](../../docs/run-inspection.md) · [report.json](report.json)。无神经推理或新维护任务验收；八项检查包含于最新完整90项，不累加。

- [logs/full.log](logs/full.log)：最终90项通过、零跳过；既有字节保持检查补充关闭写入者的情形。初次90项通过的日志在 preflight/ 保留，不是额外90项成绩。
- [final-execution.json](final-execution.json)：补充后的格式、静态、针对性与完整回归实际退出码；[execution.json](execution.json)保留初始构建与验证。
- [source.json](source.json) 与 [runtime.json](runtime.json)：最终模块、测试、配置和既有worker源码哈希及固定依赖。未修改旧环境；测试在服务器执行。
- [indexed-trial-live.json](indexed-trial-live.json)：真实正在运行的任务中读到一份模型回复、两条工具结果、两个索引标记，待执行model，无编辑导出工件。这是早期快照，不是完整模型结果。
- [wheel-audit.json](wheel-audit.json)：构建wheel中的模块字节与实际源码一致，console_scripts包含agent-lab-inspect。[wheel-entrypoint-live.json](wheel-entrypoint-live.json)记录直接从解包wheel元数据加载入口并执行的返回码0，模型端点刻意不可用；该快照已是两份回复、三条工具结果。复用依赖，无全局安装，不声称隔离依赖矩阵已通过。
- [historical-inspections.json](historical-inspections.json)：读取已有Deep Agents/ADK参考检查点，恢复四/三条工具结果，持久数据和原有WAL帧字节保持。没有重新推理或验收，不新增修复成绩。
- [historical-adk-diagnostic.json](historical-adk-diagnostic.json)：初次探针错误要求目录内WAL文件集合也完全不变；SQLite只读连接可以创建空WAL/SHM协调文件。诊断核对主数据库、manifest、结果和补丁哈希及时间不变。已补充关闭写入者检查并明确边界，没有用immutable模式忽略活跃WAL。
- [artifacts.json](artifacts.json)：白名单原始与公开哈希，仅私人路径/终端格式规范化。不发布SQLite、完整对话、工具参数或源码内容。

只读审计不是验收重跑：已有结果状态仅作观察。实际旧状态目录为nfs4，SQLiteWAL不支持网络文件系统；旧实验只证明当时观察，不证明这种存储部署受支持。后续新任务需使用本机受支持状态目录并增加启动预检。
