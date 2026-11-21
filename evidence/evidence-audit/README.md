# LlamaIndex 报告证据审计

让真实 FunctionAgent 核对简历说法背后的实验报告，而不是生成没有证据的项目成绩。八份报告固定在公开 commit `2c977ec8404c9ebfd159a7addb1d97b7500407ff`，包括当时116项回归、OpenHands203/22重叠测试、GPU未通过和未启动结果。

工程完整124项通过、零跳过，新增8项包含在内；两场真实 SDK + 假HTTP回复控制单列（10次POST），覆盖正确引用与将116伪造成布尔true的拒绝，不计神经推理。

真实9B CPU模型首题在600秒整体上限超时，驱动609.197秒退出：5次额度预留、27926请求字节、4次HTTP200、最后一次未知。模型自动选择目录和两次字段读取，第四条回复已用自由文字否认错误说法；最终结构化模型调用未完成，没有通过预声明验收。另两题按原协议未运行；没有重启、延长额度或把自由文字改算成功。

- [汇总与限制](report.json) · [固定问题与外部评分条件](normal/cases.json)
- [原始模型回复、工作流和工具轨迹](cases/gpu_claim/result.json) · [真实请求账本](cases/gpu_claim/journal/model-requests.json)
- [完整124项日志](normal/full-core.log) · [CPU服务日志](normal/server.log) · [终态与清理](normal/run-report.json)
- [实际SDK假服务控制](controls/report.json) · [正常结果](controls/normal-result.json) · [伪造事实拒绝](controls/forged_fact-result.json)
- [固定目录](corpus/catalog.json) · [早期控制目录](control-corpus/catalog.json) · [实际测试的源码附件](tested-source)
- [神经试验工件原始/公开哈希](neural-artifacts.json) · [控制工件哈希](control-artifacts.json)
- [第一版守卫失败](attempt-1/run-report.json) · [第二版漏打包样本失败](attempt-2/full-core.log)

元数据和日志中的私人路径被归一化；请求/回复体、账本、目录报告和源码附件保持原字节。公开协议经路径归一化后SHA不同，账本owner绑定的是manifest所记原始协议SHA，不是公开文件SHA。请求钩子记录客户端尝试，不能把每条尝试当成服务端已执行。最后未知请求和原生warmup/取消计算不进入已保存回复usage。

bootstrap目录也保留未执行的准备元数据，详见report注释；仅functional-protocol/functional-preflight绑定真实两场控制。六项早期定向检查、最终八项以及受影响的旧测试组与完整124重叠，不累加。

这套检查验证JSON值、来源SHA及实际读取谱系，不验证所有解释文字，也不为可篡改的操作者目录提供认证。三题是已知固定问题，不是盲测；精确量化器原权重revision未知。模型和自有源码均未修改上游仓库，无新增PR。
