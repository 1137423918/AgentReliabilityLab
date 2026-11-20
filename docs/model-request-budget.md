# 重启后仍然生效的模型请求预算

维护任务失败后常会重启，但图的已完成步骤数不能限制失败的 HTTP 请求。原版同一个任务保持 `max_graph_steps=20`，连续三次启动都遇到假服务的 503，仍发出了三次请求，没有生成补丁。这是原来缺少的可选限制，不是声称旧版已有请求预算却失效。

## 配置和恢复

在 `local-openai` 任务中同时声明 feature 和三个正整数额度：

```json
{
  "required_features": ["model_request_budget_v1"],
  "model": {
    "mode": "local-openai",
    "model": "your-local-model",
    "request_budget": {
      "max_requests": 8,
      "max_request_bytes": 65536,
      "max_total_request_bytes": 262144
    }
  }
}
```

以上片段须合并进完整任务。实际 Qwen3.5 维护预设见 [deepagents-path-model-budgeted.json](../tasks/deepagents-path-model-budgeted.json)，保留既有提示、固定原版验收和运行上限；它**尚未运行神经模型**。只声明 feature、遗漏额度、使用布尔值或更改恢复任务中的额度都会被拒绝。未启用该 feature 的历史任务保持原有行为。

```sh
# 在服务器已准备的项目环境中执行；模型服务必须在 loopback。
export AGENT_LAB_MODEL_URL=http://127.0.0.1:8000/v1
python -m agent_lab.worker --repo /path/to/deepagents \
  --task tasks/deepagents-path-model-budgeted.json --run-dir runs/budgeted-001
# 恢复使用完全相同的 task 和 run-dir；不要删除 journal 或 manifest。
```

HTTPX 同步 transport 在实际发送前读取 SDK 序列化后的请求 JSON，取得字节数和 SHA-256，然后在锁内检查并预留额度。`model-requests.json` 经临时文件、fsync、原子替换及目录 fsync 写入后才允许发送。SDK 与 transport 的连接重试均为零；重定向关闭，忽略代理环境变量。只支持 loopback 的 chat completions，同步 worker 使用该客户端；异步生成及异步流式入口明确拒绝。

**这三个额度分别限制请求次数、单次 JSON 请求体字节和累计请求体字节。** 不包含 HTTP headers、响应或模型服务内部操作，也不是 tokenizer 上下文窗口、生成 token、GPU 时间、费用或端到端时限。现有图步骤、验证超时和外层运行时限仍各有作用。

## 失败不退款，修复轮次共用一个账本

503、网络失败、超时，以及发送前后被 SIGKILL 的未知在途请求都保留预留。进程可能刚预留就退出，实际没有发出 HTTP，此时仍消耗额度。这是有意的保守上限；不承诺请求恰好执行一次。

独立 worker 的 manifest 绑定 journal ID、任务哈希和额度。`agent_lab.repair` 的所有候选共用父运行 journal，失败验收和下一轮编辑都不能重新领取额度。子目录不能通过独立 worker CLI 恢复，必须走原来的 repair 入口。缺 journal、checksum 不符、manifest 丢失但已有 checkpoint/attempt/result 时停止，不把它们当新任务重置。完成结果缓存复用不发起新 HTTP，结果中的预算 snapshot 是当时快照。

账本仅含序号、JSON 字节数和哈希、时间、路径以及 transport 观察。`headers_received` 只表示收到响应头，不能证明响应体完整、模型生成成功或已计费。完整对话、API key 和 headers 不写进这个账本；worker 原有私人 checkpoint 仍可能含任务上下文。

## 复现与证据

先准备 Deep Agents 固定基线 `744a797e3b9495539ca35571eeffd112a205f5c8` 及其官方测试依赖，再执行：

```sh
# 在新的项目环境准备 HTTP adapter 和解析检查依赖；不要覆盖既有实验环境。
uv sync --extra local-model
uv pip install --python .venv/bin/python jsonschema==4.26.0
# 激活该环境后：
python -m unittest discover -s tests -p test_request_budget.py -v
python -m unittest discover -s tests -v
# PATH 中的 python 须指向已准备好的上游测试环境；worker 使用运行本驱动的解释器。
PATH=/path/to/deepagents-test-venv/bin:$PATH /path/to/worker-venv/bin/python \
  benchmarks/request_budget_recovery.py --repo /path/to/deepagents \
  --output /path/to/new-reference-output
```

[运行前固定协议](../benchmarks/request_budget_protocol.json) 将正常和首工具 checkpoint 后的实际 SIGKILL/恢复各限为 600 秒，额度为 3 次、单次 65536 字节、累计 196608 字节。服务明确返回操作者提供的两处编辑计划，经真实 Deep Agents、ChatOpenAI 和 HTTP transport 执行，属于基础设施控制。恢复须保留 journal ID，不重复第一处编辑；两场的请求体哈希、补丁哈希必须一致，原版测试、候选测试及独立契约分别验收，不相加。

[完整报告](../evidence/model-request-budget/report.json)、[测试日志](../evidence/model-request-budget/logs/full.log)、[工件与失败记录](../evidence/model-request-budget/README.md)保留实际结果和源码哈希。该环境新装了 jsonschema，不能把此前 14 项跳过直接当作先前已经通过，也不能把新增检查与完整套件重复累加。

## 边界与设计来源

文件锁和 fsync 的保证依赖部署文件系统。本次在文档指定服务器运行，不宣称已覆盖多主机竞争、机器掉电或所有 NFS 实现。checksum 用于发现意外损坏，不能抵御可同时重写 manifest 和 journal 的恶意所有者；这也不是隔离不可信代码的系统沙箱。

[LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) 说明 checkpoint 保存图状态；[HTTPX transport](https://www.python-httpx.org/advanced/transports/) 提供发送请求的底层边界。把“已完成图步骤”与“尝试发送 HTTP”分别记账是本项目据此作出的工程设计，不是引用上游对本实现的认证。
