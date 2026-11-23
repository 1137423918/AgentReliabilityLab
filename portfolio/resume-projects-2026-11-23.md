# 简历项目表述 · 更新至2026-11-24

根据已保存的运行与代码证据整理，面向算法 / 模型研发和 Agent 应用开发。项目持续推进；本页列出的结果对应这个日期的快照。

## 工具调用模型训练与可恢复评测

**PyTorch · Transformers · PEFT / LoRA · Qwen2.5-3B · AgentRobustBench**

- 审计工具调用训练 / 验证数据复用，构建同 ID 配对数据、文本关联分组与有效监督标签预算；在真实 3B 模型上完成 Full / Mixed 各 32 步 LoRA 训练，每组使用 65,536 个监督标签，保存检查点与逐步来源记录。
- 实现跨进程的生成预算与结果恢复机制，模型调用前持久化扣额，恢复时复用首个已提交结果，未知尝试保留扣额；12 项 Linux CPU 控制通过，并在真实 GPU 中断后复用已提交结果，最终三组各199条完成；599次预留中两次历史未知继续占额。
- 完成同设备、相同199条输入的三组生成对照，官方correct：base 118/199、full32 107/199、mixed32 105/199；按同例哈希统计配对变化。本配方未显示微调后的 clean correct 提升；不能宣称扰动鲁棒性或泛化提升。
- 对已保存预测补充双视图schema诊断，区分无效源声明、名称不匹配与参数约束问题；基线158/199例符合上游投影约束，其中41例仍未通过官方匹配，为后续方法选择提供错误分布，未宣称准确率提升。[方法与证据](../docs/tool-schema-diagnostics.md)
- 重新对齐原始训练文本、token偏移与标签，量化固定推理正文占Full监督标签16.7%，并对全部597条已保存预测作配对诊断；保留正常无需工具样本，准备只屏蔽固定正文的消融数据。10项服务器CPU控制通过；新掩码尚未训练，不作因果或改进结论。[审计与边界](../docs/training-alignment.md)

这组经历能够支持数据审计、训练实现、实验可追溯与恢复工程的表述。Full 原训练的最终内存核验存在缺口，保存检查点的独立回放通过；Mixed 完整核验通过。当前生成证据不能支持微调准确率或扰动鲁棒性提升的结论。

[训练配方与边界](../docs/lora-pilot.md) · [完整生成对照](../docs/generation-complete.md) · [历史恢复设计](../docs/generation-recovery.md) · [逐例证据](../evidence/lora-generation/README.md)

## 可恢复 Agent 工作流与 MCP 证据服务

**Python · MCP SDK · Deep Agents · LangGraph · Git worktree**

- 实现带持久检查点的维护任务运行器，通过隔离 Git worktree 保存修改与验收记录，支持工具进度恢复和补丁导出；模型请求额度跨重启扣除，未确认完成的请求继续占额。
- 实现并提供可安装的 MCP 报告证据服务，核对提交事实的值、类型和读取来源；按审计句柄管理 TTL、共享操作额度与来源哈希，输出可复查的结构化回执。
- 为外部 MCP Agent 加入绑定请求账本身份的私有通信日志，强杀后可恢复已保存正文，未知请求继续占额；通过真实MCP故障控制验证中断证据保留，以及日志故障时仍关闭已知审计上下文。[实现与证据](../docs/mcp-wire-journal.md)
- 为MCP消费端加入有界报告元数据检索与完整目录回退，在24份实际报告上对比BM25和关键词基线，并通过真实SDK/TCP验证读取回执、最终提交和关闭；目录回复平均约1.5KB，未宣称模型任务成功率提升。[方法与范围](../docs/report-retrieval.md)
- 将MCP审计的模型输出与精确值装配分离：模型显式选择字段引用，消费端仅从本次实际读取绑定值、来源哈希及回执核验。服务器8项模块及5场真实MCP脚本控制通过；真实9B在两项已知报告核对任务中通过一项，另一项无效字段路径被拒绝，保留完整失败与请求账本。[实现与实际结果](../docs/reference-submission.md)
- 在真实 Qwen3.5-9B / MCP 运行中持久保存7份完整模型回复与40条通信事件，并由独立进程核对恢复结果和审计关闭；本次业务任务因轮次上限未完成，按原失败记录。[运行范围与原始结果](../docs/mcp-agent.md)
- 在服务器完成 130 项核心回归，另完成 8 项独立安装控制；提供 wheel、独立启动包与真实 MCP SDK 客户端示例。

验证覆盖任务恢复、事实回执与安装链路。结构化事实核对不保证自由文本结论正确；目前没有通过验收的模型自主仓库修复成果。wheel 与启动包发布在 GitHub 项目中。

[维护运行器](../docs/durable-worker.md) · [跨重启请求预算](../docs/model-request-budget.md) · [MCP 服务与安装](../docs/mcp-evidence.md)

## 真实开源项目依赖升级审查 Agent

**Python · OSV-Scanner · uv · MCP · LlamaIndex FunctionAgent · Qwen3.5-9B**

- 面向依赖维护流程，固定两个真实 Agent 项目的源码提交、锁文件与漏洞库，执行原始扫描、声明不变的目标解析和候选复扫；输出实际差异、目标残留及新增包/公告匹配，为兼容性测试准备证据。
- 显式处理开发/可选/条件 registry resolutions 与 editable/root 来源，拒绝未声明扫描条目；通过9项服务器单元控制，保留准备阶段失败及固定来源哈希。
- 将外部项目扫描事实接入真实 MCP 服务，模型选择字段引用，消费端绑定本次读取的精确值与回执；4场脚本场景覆盖正常审查、跨项目引用和错误结论。真实9B完成两项已知任务、通过一项，共6次请求，另一项遗漏必要事实而失败，未宣称泛化准确率。

[实现、实际结果与运行入口](../docs/dependency-upgrade.md)。候选扫描未替代兼容性测试或发布审批；FastMCP候选仍有16个受影响 registry resolutions。历史发布快照不代表项目当前部署。

## Agent 开源项目缺陷修复

为独立维护的 GPT Researcher 提交 HTTP MCP 令牌连接修复：将不受支持的顶层参数转换为授权头，保护显式授权优先级、请求头大小写兼容和原配置不变；覆盖真实受鉴权服务上的工具发现、调用与401拒绝。原版11项回归全部失败，修复后11项通过，另完成服务器完整离线选择1112项通过，17项跳过、4项排除；范围重叠不相加。[PR #2367](https://github.com/assafelovic/gpt-researcher/pull/2367) 已正式提交，尚未合并。[实际源码与验证边界](../docs/gpt-researcher-mcp-token.md)

在独立小团队维护的 Browser Use 中修复云会话下载未沿用创建密钥的问题，覆盖分页查询、切换模型后的保活会话及停止后的文件补收。使用真实鉴权、请求和落盘代码配合HTTP边界模拟，原版三个入口回归失败，候选通过；pre-commit、锁定工具检查及完整非Chrome选择通过，具体范围与跳过项见[证据](../docs/browseruse-cloud-download-key.md)。[PR #6521](https://github.com/browser-use/browser-use/pull/6521) 已正式提交，尚未合并。 同一PR继续落实评审反馈，补齐超时创建的停止后凭据清理与失败重试；最终服务器非Chrome选择969项通过，原始及补充回归分别保留失败基线，范围不相加。

在小团队维护的 VoltAgent 中修复 MCP 断连通知报错、已结束会话注册累积，以及第二次连接被拒绝时误关活跃传输的问题；通过真实 HTTP/MCP 客户端和可控启动时序复现，上一版在同一组11项生命周期测试中2项失败，修复后11项及完整MCP包26项通过，并完成源码、两份新增测试的严格类型检查及构建。清理保留活跃流、基座重连和正在启动的连接。已正式提交 [PR #1562](https://github.com/VoltAgent/voltagent/pull/1562)，尚未合并。[源码与验证证据](../evidence/voltagent-mcp-connection-ownership/README.md)

为 OpenHands SDK、Google ADK、Semantic Kernel 和 Agent Lightning 提交文件系统与异步生命周期修复，提供原版失败、候选回归、固定源码与测试范围。具体提交包括写入失败后的编辑历史保留、移动到源文件自身时的数据保护、并发删除目录处理，以及取消回调重入和调用方取消后的异常 / 队列记账。

在 Agent Lightning 中复现删除后复用 rollout ID 导致完成分页引用新任务的问题，使用日志空位与位置索引保持既有游标有效；原版四种状态回归失败，候选服务端与客户端53项测试通过，修改文件类型检查通过。已提交PR，并于2026-11-23转为正式待审；尚未合并。[修复与证据](../docs/lightning-terminal-reuse.md) · [PR #707](https://github.com/microsoft/agent-lightning/pull/707)

这些是已提交的贡献，合并状态以 PR 页面为准。可按岗位选取一两个能够说明触发条件、修复取舍与测试范围的例子。

[OpenHands #7032](https://github.com/OpenHands/software-agent-sdk/pull/7032) · [OpenHands #7050](https://github.com/OpenHands/software-agent-sdk/pull/7050) · [Google ADK #8278](https://github.com/google/adk-python/pull/8278) · [Semantic Kernel #14845](https://github.com/microsoft/semantic-kernel/pull/14845) · [Semantic Kernel #14853](https://github.com/microsoft/semantic-kernel/pull/14853)
