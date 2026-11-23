# 实际 GPU Agent 消费 MCP：共享显卡保护中止

固定协议下，真实Qwen3.5-9B量化模型、LlamaIndex FunctionAgent和已安装的独立MCP服务完成启动；日志确认33/33层GPU卸载、8192上下文。首题运行44.008秒时检测到同卡其他计算客户端，按预声明保护终止；第二题未启动，零已完成评分。这是基础设施中止，没有可报的题目通过率，也不是语义失败。

账本保存5次模型POST预留/37004请求正文字节：4次收到HTTP200头，第5次未知且继续扣额。驱动SIGTERM退出前未落盘result.json中的内存wire事件，故没有完整回复、工具轨迹或最终答案可复核。不能由HTTP头推导4份完整回复、正确工具执行或已关闭审计。

模型退出0，MCP按计划SIGTERM(-15)退出；两个端口关闭、自有进程归零、自己的GPU上下文消失、临时密钥删除。无强杀；监控线程退出。没有close_audit确认；进程内能力随服务退出失效。未改28份冻结来源、两道已知题/gold、模型权重、提示与额度；没有重试或延长运行。CUDA二进制、清理实现和安装服务入口较旧CPU记录不同，不能归因GPU加速。旧CPU600秒超时不重评。

当前冻结配置不使用GPU7；用户后来告知GPU7恢复，后续新任务可重新做资源准入，这不追改旧协议。预声明的岗位假设也保留原字节，后续已明确同时关注算法/模型与Agent应用。

[结果与局限](report.json) · [原运行终态](operator/run-report.json) · [预声明协议](operator/protocol.json) · [持久账本](cases/inflated_merged_claim/journal/model-requests.json) · [GPU资源采样](service/gpu-monitor.jsonl) · [原生日志脱敏副本](service/server-public.log) · [49份工件双哈希](artifacts.json)。一个空journal锁不公开；无凭据、私有数据库或原始server.log。
