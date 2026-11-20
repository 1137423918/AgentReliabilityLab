# 首屏 Python 索引：原文保留、版本与恢复

服务器 CPU 上执行，无 GPU 或新神经推理。真实模型未选择已有源码工具的失败触发了这次改进；本次固定参考计划只验证工程接口，不能证明模型定位、token 或修复效果提高。

- [完整说明](../../docs/read-index.md)：显式开启、规范路径限制、字节上限、回退与可见历史去重。
- [report.json](report.json)：真实 Deep Agents 固定 `744a797e`，关闭索引、开启索引、开启索引并在首读取检查点实际 SIGKILL 三场。均四次工具、相同 1573 字节参考补丁；原始两页分别跨场逐字节一致。编辑后索引 SHA 匹配最终虚拟内容，原版和候选索引均包含后部两个相关函数。
- [protocol.json](protocol.json)：开始前内部声明，不是外部预注册。故障前观察 180 秒、续跑每场 600 秒、整个矩阵控制器 2400 秒，三者分开记录。
- [runtime.json](runtime.json)：实际 Python、模块路径、依赖、源码与目标提交。复用现有专用环境，PYTHONPATH 指向新源码，验收 PATH 指向上游测试环境；未修改旧环境。
- [logs/full.log](logs/full.log)：完整 82 项通过、零跳过，包含本次八项检查；[针对性日志](logs/focused.log)和格式/静态检查保留。八项不与 82 累加。
- [controls-execution.json](controls-execution.json) 与 [logs/controls.log](logs/controls.log)：真实退出码与矩阵总耗时，不作性能比较。
- `cases/`：每场原始阶段事件、候选补丁、结果和四份验收日志。各通过复用的 113 条固定原版、119 条候选与 28 个路径契约；这些组重叠，不计新增唯一回归。`indexed-checkpoint/interrupted.stdout.jsonl` 记录首读后中断，续跑事件从第二条工具继续。
- `tasks/`：完整明确的读取和参考编辑计划。新神经任务预设另在 tasks 目录，尚未运行，未提供这些参考编辑。
- [artifacts.json](artifacts.json)：白名单原始/公开哈希。仅私人服务器路径和终端格式规范化，协议、任务与补丁保持原始字节；不发布 SQLite、完整对话、headers、权重或工作区。

原始读取文本保持完整不等于新工具回复或新模型请求完全相同：开启后会多出索引和通用提示。索引不是嵌套或语义分析，不保证包含被预算省略的后续声明。未测量新模型 usage、推理耗时或任务成功率。

参考补丁上下文依上游 MIT 许可，随附 [UPSTREAM_LICENSE](UPSTREAM_LICENSE)。
