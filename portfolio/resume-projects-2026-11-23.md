# 简历项目表述 · 2026-11-23

根据已保存的运行与代码证据整理，面向算法 / 模型研发和 Agent 应用开发。项目持续推进；本页列出的结果对应这个日期的快照。

## 工具调用模型训练与可恢复评测

**PyTorch · Transformers · PEFT / LoRA · Qwen2.5-3B · AgentRobustBench**

- 审计工具调用训练 / 验证数据复用，构建同 ID 配对数据、文本关联分组与有效监督标签预算；在真实 3B 模型上完成 Full / Mixed 各 32 步 LoRA 训练，每组使用 65,536 个监督标签，保存检查点与逐步来源记录。
- 实现跨进程的生成预算与结果恢复机制，模型调用前持久化扣额，恢复时复用首个已提交结果，未知尝试保留扣额；12 项 Linux CPU 控制通过，并在真实 GPU 中断后跳过 81 条旧结果、完成 2 条新增结果。
- 完成新同后端基线全部 199 条生成评测，官方 correct 118/199；Full32 当前为 83/199、Mixed32 尚未生成，完整微调效果对照仍在进行。
- 对已保存预测补充双视图schema诊断，区分无效源声明、名称不匹配与参数约束问题；基线158/199例符合上游投影约束，其中41例仍未通过官方匹配，为后续方法选择提供错误分布，未宣称准确率提升。[方法与证据](../docs/tool-schema-diagnostics.md)

这组经历能够支持数据审计、训练实现、实验可追溯与恢复工程的表述。Full 原训练的最终内存核验存在缺口，保存检查点的独立回放通过；Mixed 完整核验通过。当前生成证据不能支持微调准确率或扰动鲁棒性提升的结论。

[训练配方与边界](../docs/lora-pilot.md) · [生成与恢复](../docs/generation-recovery.md) · [逐例证据](../evidence/lora-generation/README.md)

## 可恢复 Agent 工作流与 MCP 证据服务

**Python · MCP SDK · Deep Agents · LangGraph · Git worktree**

- 实现带持久检查点的维护任务运行器，通过隔离 Git worktree 保存修改与验收记录，支持工具进度恢复和补丁导出；模型请求额度跨重启扣除，未确认完成的请求继续占额。
- 实现并提供可安装的 MCP 报告证据服务，核对提交事实的值、类型和读取来源；按审计句柄管理 TTL、共享操作额度与来源哈希，输出可复查的结构化回执。
- 为外部 MCP Agent 加入绑定请求账本身份的私有通信日志，强杀后可恢复已保存正文，未知请求继续占额；通过真实MCP故障控制验证中断证据保留，以及日志故障时仍关闭已知审计上下文。[实现与证据](../docs/mcp-wire-journal.md)
- 在真实 Qwen3.5-9B / MCP 运行中持久保存7份完整模型回复与40条通信事件，并由独立进程核对恢复结果和审计关闭；本次业务任务因轮次上限未完成，按原失败记录。[运行范围与原始结果](../docs/mcp-agent.md)
- 在服务器完成 130 项核心回归，另完成 8 项独立安装控制；提供 wheel、独立启动包与真实 MCP SDK 客户端示例。

验证覆盖任务恢复、事实回执与安装链路。结构化事实核对不保证自由文本结论正确；目前没有通过验收的模型自主仓库修复成果。wheel 与启动包发布在 GitHub 项目中。

[维护运行器](../docs/durable-worker.md) · [跨重启请求预算](../docs/model-request-budget.md) · [MCP 服务与安装](../docs/mcp-evidence.md)

## Agent 开源项目缺陷修复

在小团队维护的 VoltAgent 中修复 MCP 断连通知报错及已结束会话注册累积；通过真实 HTTP/MCP 客户端复现首版PR的8项生命周期失败，修复后8项及完整MCP包23项测试通过，并完成源码、两份新增测试的严格类型检查及构建。清理覆盖响应结束、异常和会话关闭，同时保留活跃流与基座重连。已正式提交 [PR #1562](https://github.com/VoltAgent/voltagent/pull/1562)，尚未合并。[源码与验证证据](../evidence/voltagent-mcp-cleanup/README.md)

为 OpenHands SDK、Google ADK、Semantic Kernel 和 Agent Lightning 提交文件系统与异步生命周期修复，提供原版失败、候选回归、固定源码与测试范围。具体提交包括写入失败后的编辑历史保留、移动到源文件自身时的数据保护、并发删除目录处理，以及取消回调重入和调用方取消后的异常 / 队列记账。

在 Agent Lightning 中复现删除后复用 rollout ID 导致完成分页引用新任务的问题，使用日志空位与位置索引保持既有游标有效；原版四种状态回归失败，候选服务端与客户端53项测试通过，修改文件类型检查通过。已提交PR，并于2026-11-23转为正式待审；尚未合并。[修复与证据](../docs/lightning-terminal-reuse.md) · [PR #707](https://github.com/microsoft/agent-lightning/pull/707)

这些是已提交的贡献，合并状态以 PR 页面为准。可按岗位选取一两个能够说明触发条件、修复取舍与测试范围的例子。

[OpenHands #7032](https://github.com/OpenHands/software-agent-sdk/pull/7032) · [OpenHands #7050](https://github.com/OpenHands/software-agent-sdk/pull/7050) · [Google ADK #8278](https://github.com/google/adk-python/pull/8278) · [Semantic Kernel #14845](https://github.com/microsoft/semantic-kernel/pull/14845) · [Semantic Kernel #14853](https://github.com/microsoft/semantic-kernel/pull/14853)
