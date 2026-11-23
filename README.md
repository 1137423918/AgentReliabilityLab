# Agent Reliability Lab

研究工具调用的模型效果，并构建可复查、可恢复的 Agent 执行与证据核对工具。项目同时包含真实 3B 模型实验、可安装的 MCP 服务，以及面向真实开源仓库的维护运行器。

个人主页只保留论文与项目简介；本仓库的后续材料不会自动发布到主页。

## 模型研究

使用固定 Qwen2.5-3B-Instruct 与 AgentRobustBench 源码，先审计训练/验证样本复用，再构建同 ID 配对数据、文本关联分组和有效监督标签预算。Full/Mixed 各实际执行 32 次 LoRA 更新、65,536 个监督标签；输入暴露与计算量并不相同。

Full 原训练的最终核验中断，保存检查点的独立回放通过，原失败保留；Mixed 完整核验通过。两组参考答案条件下的验证 NLL 为 0.297599 / 0.297934，不能据此声称工具调用准确率或鲁棒性提升。

同后端 clean 生成评测的新基线为 **118/199**。Full32 因共享显卡资源保护中断，恢复机制实际跳过 81 条旧结果并完成 2 条新结果；目前累计 83/199，Mixed32 尚未生成。未知尝试继续扣额，完整三组对照未完成。

- [数据复用审计](docs/training-data.md)与[开发集、真实分词和标签预算](docs/training-study.md)。
- [实际 LoRA 配方、结果与核验边界](docs/lora-pilot.md)及[完整证据](evidence/lora-pilot/README.md)。
- [持久生成进度、真实恢复与当前部分结果](docs/generation-recovery.md)：12 项服务器 CPU 控制通过，已评分结果不重新生成或评分。
- [原 P100 工具调用基线](docs/tool-use-baseline.md)：119/199 官方 correct，属于历史设备条件，不改判为新设备结果。
- [工具调用研究路线与评分器审计](docs/robust-tool-use.md)。

## Agent 应用

**MCP 报告证据服务**：读取固定来源 JSON，返回带来源哈希的回执，核对提交事实的值、类型和读取谱系。每次审计有独立句柄、TTL 和共享操作额度；事实核对不保证自由文本结论正确。

提供[独立启动包](artifacts/agentlab-evidence-0.1.0-starter.zip)和[wheel](artifacts/agentlab_evidence-0.1.0-py3-none-any.whl)，无需模型权重。已有 Python3.11 / uv 的服务器可从源码启动本机服务：

```sh
uv sync --project extras/mcp-evidence --frozen --no-install-project --no-default-groups
extras/mcp-evidence/.venv/bin/python -m benchmarks.mcp_evidence_server \
  --root evidence/mcp-evidence/corpus \
  --manifest evidence/mcp-evidence/corpus/catalog.json --port 18856
```

绑定 `127.0.0.1:18856`；[安装、客户端及接口](docs/mcp-evidence.md)说明独立启动包和自有报告目录的使用方式。服务器实测 130 项核心回归通过、零跳过，另八项安装控制通过；两种范围不累加，也不是神经模型成绩。[安装证据](evidence/evidence-package/README.md)。

**可恢复维护运行器**：结合 Deep Agents、LangGraph 检查点、隔离 Git worktree 和命令验收，保存工具进度、导出补丁并等待审阅。模型请求预算跨重启与修复轮次扣额，未知请求仍占额度。

[恢复与运行入口](docs/durable-worker.md) · [持久请求预算](docs/model-request-budget.md) · [本机状态与共享归档](docs/local-state.md) · [真实 MCP/Agent 接入](docs/mcp-agent.md)。真实仓库参考计划的恢复检查与真实模型任务分别记录；目前没有通过验收的模型自主仓库修复成果。

## 开源贡献

针对实际文件系统与异步生命周期缺陷提交修复，附原版失败/候选结果、固定源码和测试范围。贡献状态以[带时间戳的只读快照](evidence/upstream-current/README.md)及各 PR 为准，未将机器人评论当作人工批准。

| 上游 PR | 修复对象 |
| --- | --- |
| [OpenHands #7032](https://github.com/OpenHands/software-agent-sdk/pull/7032) | 撤销写入失败后保留可重试的编辑历史 |
| [OpenHands #7050](https://github.com/OpenHands/software-agent-sdk/pull/7050) | 拒绝指向源文件自身的移动，避免删除源文件 |
| [Google ADK #8278](https://github.com/google/adk-python/pull/8278) | 并发删除产物目录时处理已消失的条目 |
| [Semantic Kernel #14845](https://github.com/microsoft/semantic-kernel/pull/14845) | 在锁外执行取消回调，避免重入死锁 |
| [Semantic Kernel #14853](https://github.com/microsoft/semantic-kernel/pull/14853) | 调用方取消后仍处理后续异常与队列记账 |

## 复查材料

[简历可用表述与证据（2026-11-23）](portfolio/resume-projects-2026-11-23.md) · [逐阶段记录与保留的失败](docs/project-history.md) · [两页中英介绍（2026-11-22历史快照）](portfolio/junzhe-wang-project-brief.pdf) · [快照正文与证据映射](portfolio/README.md)。

测试组有重叠，不能把历史数字累计成新的总成绩。完整提示、答案、token 向量、权重、服务器连接资料和凭据保留私有；公开材料提供来源、哈希、运行条件与结果边界。
