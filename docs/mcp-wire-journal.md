# 中断后保留 MCP Agent 的通信证据

真实 Agent 运行可能在资源保护、取消或进程强杀后没有最终结果文件。[此前一次 GPU 运行](../evidence/mcp-agent-gpu/README.md)保留了请求额度和 HTTP 头观察，内存中的完整通信轨迹却丢失。本次为外部 MCP 审计 Agent 接入私有 wire 日志，逐条保存已观察到的请求和完整回复；读取器可以核对中断后的有效前缀。

**服务器验证已通过：**原版收到两份完整脚本模型回复、第三次 POST 等待时被 SIGKILL，没有可恢复的 wire 文件；候选在相同控制下恢复15条事件，包括3条模型请求、2份完整回复及一次真实 MCP 报告读取。第三次未知请求仍占原额度，最终结果文件仍不存在。[完整证据](../evidence/mcp-wire-journal/README.md)。

## 日志与读取边界

[`wire_journal.py`](../agent_lab/wire_journal.py) 将 `wire-events.jsonl` 放在原预算的私有 state 目录，权限0600。首帧绑定协议owner、预算journal ID和日志边界，后续帧包含序号、前帧SHA及本帧SHA。每条写入执行 `fsync`，成功后才更新内存列表。数据来自真实 HTTPX2 hooks，不生成替代内容。

只接受原hook的字段，并核对base64正文的长度和SHA。认证头不在字段集合中；原始正文仍可能包含审计句柄、回执或用户数据，保持私有。默认192个事件、全文件8MiB、单帧1MiB。这些是日志边界，不替代模型请求、主存、token或费用预算。

读取器只读，不修复、截断或续写旧日志。完整帧校验或身份错误直接拒绝；最后一行未完成时，返回此前已校验帧及尾部字节数。有效前缀不证明工作流完成，也不能证明未记录的动作未发生。整条末尾帧被删、操作者重写等情况不能仅靠前缀排除；它不是恶意所有者防篡改或 exactly-once 协议。

[`llamaindex_mcp_audit.py`](../benchmarks/llamaindex_mcp_audit.py) 保持原模型、提示、接纳规则和请求额度，增加持久日志及输出中的 `wire_journal` 状态。正常业务阶段写入失败会抛出异常；关闭已知审计上下文时，记录失败单列到 `cleanup_wire_error_count`，不能阻止既有的一次关闭尝试。状态查询2秒、整体清理10秒的边界不变，不重放业务工具或新建审计。

## 服务器检查入口

使用源码根目录及 Python3.11；读取器本身只用标准库。原state目录应在已准入的本机文件系统，owner和journal ID来自该运行的 `model-requests.json`：

```sh
python -m agent_lab.wire_journal /path/to/private-state/wire-events.jsonl \
  --owner "$PROTOCOL_SHA256" --journal-id "$BUDGET_JOURNAL_ID"
```

CLI只输出身份、前缀长度、尾部字节数、正文SHA和长度等元数据，不打印正文。程序接口 `read_wire_journal(path, owner, journal_id)` 返回原始事件，适合在同一私有服务器深入检查。

这是通信证据恢复，没有实现Agent工作流恢复、模型请求重发或工具重放。强杀后的Agent没有关闭确认；故障控制由测试操作者关闭同一个遗留上下文，与Agent自身关闭分开计数。预算与未知扣额保持不变，旧GPU运行缺失的正文仍缺失。

## 实际验证

独立Linux CPU环境沿用原 `extras/mcp-agent/uv.lock`：MCP2.3.0、HTTPX2 2.16.2、LlamaIndex Core0.14.26 / Workflows2.26.1、OpenAI3.57.0；模型运行环境未改。

| 范围 | 结果 |
| --- | --- |
| 8项标准库日志控制 | 通过；含部分写入、完整帧损坏、身份不符、上限、文件复用拒绝、CLI正文隔离 |
| 真实MCP/TCP强杀 | 原版丢失wire；候选恢复15事件 / 2份完整回复，未知仍扣额 |
| 清理时日志写入故障 | Agent仍关闭已知上下文，独立查询确认；写入故障明确报告 |
| 原有10个MCP生命周期场景 | 全通过，含取消、超时、过期、业务错误和不合法提交 |
| Ruff与格式 | 四个修改文件通过 |

回复在控制中明确按脚本提供，不是神经推理或模型准确率。候选合计27次脚本模型POST、24份完整正文、3次HTTP状态未知仍扣额；原版复现的3次请求另列。原有130项核心快照及真实9B实验未重跑。

```sh
python -m unittest discover -s extras/mcp-agent -p 'test_wire_journal.py' -v

# 使用原锁定的可选MCP环境；state必须是新的私有目录。
extras/mcp-agent/.venv/bin/python -m benchmarks.mcp_wire_controls \
  --code evidence/mcp-agent --state /tmp/new-wire-crash --owner "$PROTOCOL_SHA256"
extras/mcp-agent/.venv/bin/python -m benchmarks.mcp_wire_controls \
  --code evidence/mcp-agent --state /tmp/new-wire-disk-fault --owner "$PROTOCOL_SHA256" \
  --cleanup-write-error
```

两场自行启动、关闭本机控制服务，不需模型权重。公开证据只有事件摘要、正文SHA、预算和协议，无法独立重建私有正文的整条hash链或评价答案语义。项目资料继续完善，个人主页保持冻结。
