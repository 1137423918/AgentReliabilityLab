# 模型 HTTP 预算与恢复证据

在文档指定服务器 CPU 上执行，未使用 GPU 或神经模型。实现、配置和边界见 [完整说明](../../docs/model-request-budget.md)。

- [report.json](report.json)：固定真实 Deep Agents `744a797e` 的正常与首工具 checkpoint 后实际 SIGKILL/恢复。每场 3 次 HTTP；JSON 请求体字节数/哈希匹配发送前账本预留，两场请求体序列与补丁一致。每场分别通过 113 条固定原版、119 条候选和 28 个契约；验收组重叠。
- [protocol.json](protocol.json)：运行前内部固定的协议，不是外部预注册。每场 600 秒；3 次请求、单次 65536 字节、累计 196608 字节。工具编辑由明确的假 loopback 服务返回操作者计划，不是模型自主修复。
- [runtime.json](runtime.json)：Python、安装分布和实际最终源码哈希。新独立 venv 通过只读 `.pth` 引用既有 worker 依赖，新增 jsonschema 及其依赖，并以 editable 安装本项目；未修改旧环境。不是完全隔离的原冻结环境。基线和候选使用同一新环境。
- [logs/full.log](logs/full.log)：最终版本完整 74 项通过、无跳过，包含 11 项预算检查。新增检查与完整套件不累加；此前缺 jsonschema 而跳过的 14 项本轮实际执行。最终包含异步生成与流式两条入口的拒绝检查。
- [logs/focused.log](logs/focused.log)：先前 11 项预算检查通过；随后补充异步流式入口，再执行上述最终完整套件及真实仓库协议。不能把这个先前针对性日志当作最终源码完整记录。
- [baseline/report.json](baseline/report.json)：原版 `ce89faaaa7ca8a44cc1558f9c0900c8ee3d3582b` 的同一个旧任务，图预算 20，连续三次启动均遇到 503，却发出三次实际 HTTP。无补丁或成功结果。这是缺少可选请求限制的对照，不是既有请求预算的回归。
- [cases/checkpoint-sigkill/ledger-before-kill.json](cases/checkpoint-sigkill/ledger-before-kill.json) 与 [恢复后的账本](cases/checkpoint-sigkill/model-requests.json)：中断前预留 1 次，恢复后共 3 次，账本身份不变。另有实际 checkpoint 事件、worker 输出、补丁和四组验证日志。
- [preflight/uninstalled-package.log](preflight/uninstalled-package.log)：最初 11 项中三项失败，原因是验证监督子进程从临时工作区启动时找不到未安装的 `agent_lab` 包。[editable-install.log](preflight/editable-install.log) 保留独立新环境安装修正；之后才进行最终验证，没有修改验收断言以掩盖失败。
- [artifacts.json](artifacts.json)：白名单文本工件的原始与公开字节哈希。服务器私人路径和终端格式在日志/报告中规范化；请求账本与补丁字节未改。完整私人任务、SQLite 数据库、对话、headers、API key、依赖和权重不公开。

账本约束请求尝试次数与 JSON 请求体字节；失败、超时和未知在途预留不退款，可能先预留却尚未发送。`headers_received` 不是完成或付费证明。没有 token/费用上限、恰好一次、多主机或掉电恢复的成绩；checksum 也不是抵御拥有文件写权限的恶意用户的认证。新神经预算任务预设尚未运行。

上游测试补丁上下文依 MIT 许可，随附 [UPSTREAM_LICENSE](UPSTREAM_LICENSE)。
