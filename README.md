# Agent Reliability Lab

研究工具调用的模型效果，并构建可复查、可恢复的 Agent 执行与证据核对工具。项目同时包含真实 3B 模型实验、可安装的 MCP 服务，以及面向真实开源仓库的维护运行器。

个人主页只保留论文与项目简介；本仓库的后续材料不会自动发布到主页。

## 模型研究

使用固定 Qwen2.5-3B-Instruct 与 AgentRobustBench 源码，先审计训练/验证样本复用，再构建同 ID 配对数据、文本关联分组和有效监督标签预算。Full/Mixed 各实际执行 32 次 LoRA 更新、65,536 个监督标签；输入暴露与计算量并不相同。

Full 原训练的最终核验中断，保存检查点的独立回放通过，原失败保留；Mixed 完整核验通过。两组参考答案条件下的验证 NLL 为 0.297599 / 0.297934，不能据此声称工具调用准确率或鲁棒性提升。

同后端三组 clean 生成对照已完成：**base 118/199、full32 107/199、mixed32 105/199**。本配方未显示微调后的 clean correct 提升；不能宣称扰动鲁棒性或泛化提升。 资源恢复保留全部旧结果，最终599次预留/597条已提交，两个历史未知仍扣额。[完整对照与边界](docs/generation-complete.md)。

- [数据复用审计](docs/training-data.md)与[开发集、真实分词和标签预算](docs/training-study.md)。
- [监督目标与行为审计](docs/training-alignment.md)：固定推理文本占Full监督标签16.7%；对全部597条已保存结果进行配对诊断，并准备只屏蔽固定正文的损失掩码，后续配对训练结果见下方。
- [迁移评测输入准入](docs/bfcl-transfer-admission.md)：在读取参考答案前锁定250条BFCL派生输入，完成保护数据关联检查和10项CPU控制；尚未运行新模型评测，不是完整BFCL成绩。
- [迁移评分与参考绑定](docs/bfcl-transfer-scoring.md)：14项CPU控制和250条参考构造校验调用通过；保留原匹配规则，并拦截表达式求值分支、单列解析状态。这是评分链路验证，尚无新模型成绩。
- [固定正文屏蔽配对试验](docs/fixed-reason-ablation.md)：同初始化、同输入与同卡的两组各32步训练及完整核验已完成，共2,666次逻辑前向／零未知。整段验证NLL为Reference0.297588、Masked0.671653；外部生成效果尚未验证。
- [固定250题生成对照](docs/bfcl-transfer-generation.md)：base／新Reference32／新Masked32的推理协议已冻结，8项CPU控制与输入身份核验通过；服务器生成正在执行，尚未评分；离线汇总另通过6项CPU控制。
- [实际 LoRA 配方、结果与核验边界](docs/lora-pilot.md)及[完整证据](evidence/lora-pilot/README.md)。
- [持久生成进度与恢复阶段记录](docs/generation-recovery.md)：12 项服务器 CPU 控制通过，已评分结果不重新生成或评分；最终结果见上方完整对照。
- [已保存调用的schema诊断](docs/tool-schema-diagnostics.md)：分别核对原始schema和上游FC投影。基线158/199例符合投影约束，其中41例仍未通过官方匹配；结构有效性不等于任务成功，部分Full对照尚无提升证据。
- [原 P100 工具调用基线](docs/tool-use-baseline.md)：119/199 官方 correct，属于历史设备条件，不改判为新设备结果。
- [工具调用研究路线与评分器审计](docs/robust-tool-use.md)。

## Agent 应用

**真实依赖升级审查 Agent**：[使用与结果](docs/dependency-upgrade.md)。固定 Browser Use / FastMCP 发布源码，执行离线漏洞扫描、保持声明的真实解析和候选复扫，再通过 MCP 核对八项事实。两个项目分别得到“原精确版本未升级”和“Authlib 升级候选可进入兼容性测试”的结果。9项单元与4场真实MCP脚本控制通过；真实9B完成两题、通过一题，失败原因和6次请求账本保留。

**MCP 报告证据服务**：读取固定来源 JSON，返回带来源哈希的回执，核对提交事实的值、类型和读取谱系。每次审计有独立句柄、TTL 和共享操作额度；事实核对不保证自由文本结论正确。

提供[独立启动包](artifacts/agentlab-evidence-0.1.0-starter.zip)和[wheel](artifacts/agentlab_evidence-0.1.0-py3-none-any.whl)，无需模型权重。已有 Python3.11 / uv 的服务器可从源码启动本机服务：

```sh
uv sync --project extras/mcp-evidence --frozen --no-install-project --no-default-groups
extras/mcp-evidence/.venv/bin/python -m benchmarks.mcp_evidence_server \
  --root evidence/mcp-evidence/corpus \
  --manifest evidence/mcp-evidence/corpus/catalog.json --port 18856
```

绑定 `127.0.0.1:18856`；[安装、客户端及接口](docs/mcp-evidence.md)说明独立启动包和自有报告目录的使用方式。服务器实测 130 项核心回归通过、零跳过，另八项安装控制通过；两种范围不累加，也不是神经模型成绩。[安装证据](evidence/evidence-package/README.md)。

外部 MCP Agent 已支持[通信证据持久化](docs/mcp-wire-journal.md)：进程强杀后保留已保存的回复，未知请求继续扣额；日志写入故障不会阻止对已知审计上下文的关闭尝试。8项日志控制、2项真实MCP故障控制及原有10项生命周期场景在服务器通过，模型回复按脚本提供。

真实Qwen3.5-9B GPU运行进一步保留了7份完整模型回复和40条通信事件，独立reader恢复验证通过，MCP关闭得到确认。首题因轮次上限未完成有效提交，第二题按规则未运行；[实际结果与失败分析](docs/mcp-agent.md)。

新增[报告目录词法检索](docs/report-retrieval.md)：在24份固定实际报告、19个预声明检索诊断中，BM25与关键词基线都覆盖必需报告，目录结果平均约1.5KB；三项真实MCP脚本集成场景通过。未显示BM25优于简单基线，真实模型任务收益仍待验证。

新增可选[字段引用提交](docs/reference-submission.md)：模型选择结论和字段，适配器从本次真实MCP读取绑定精确值与来源，原核验器和评分不变。真实9B在两项已知报告核对任务中通过一项；另一项因生成不存在的大小写路径被拒绝。此前三次失败、第四项未启动以及本次8次完整模型回复均保留，不据此宣称泛化能力或BM25收益。

**可恢复维护运行器**：结合 Deep Agents、LangGraph 检查点、隔离 Git worktree 和命令验收，保存工具进度、导出补丁并等待审阅。模型请求预算跨重启与修复轮次扣额，未知请求仍占额度。

[恢复与运行入口](docs/durable-worker.md) · [持久请求预算](docs/model-request-budget.md) · [本机状态与共享归档](docs/local-state.md) · [真实 MCP/Agent 接入](docs/mcp-agent.md)。真实仓库参考计划的恢复检查与真实模型任务分别记录；目前没有通过验收的模型自主仓库修复成果。

## 开源贡献

针对实际文件系统与异步生命周期缺陷提交修复，附原版失败/候选结果、固定源码和测试范围。贡献状态以[带时间戳的只读快照](evidence/upstream-current/README.md)及各 PR 为准，未将机器人评论当作人工批准。

| 上游 PR | 修复对象 |
| --- | --- |
| [GPT Researcher #2367](https://github.com/assafelovic/gpt-researcher/pull/2367) | 将HTTP MCP令牌转换为授权头，修复工具发现返回空列表的问题 |
| [Browser Use #6521](https://github.com/browser-use/browser-use/pull/6521) | 让云浏览器的分页下载查询和停止后补收沿用创建该会话的密钥 |
| [VoltAgent #1562](https://github.com/VoltAgent/voltagent/pull/1562) | 清理已结束的 MCP 会话注册，并保护已有连接与正在启动的传输 |
| [OpenHands #7032](https://github.com/OpenHands/software-agent-sdk/pull/7032) | 撤销写入失败后保留可重试的编辑历史 |
| [OpenHands #7050](https://github.com/OpenHands/software-agent-sdk/pull/7050) | 拒绝指向源文件自身的移动，避免删除源文件 |
| [Google ADK #8278](https://github.com/google/adk-python/pull/8278) | 并发删除产物目录时处理已消失的条目 |
| [Semantic Kernel #14845](https://github.com/microsoft/semantic-kernel/pull/14845) | 在锁外执行取消回调，避免重入死锁 |
| [Semantic Kernel #14853](https://github.com/microsoft/semantic-kernel/pull/14853) | 调用方取消后仍处理后续异常与队列记账 |
| [Agent Lightning #707](https://github.com/microsoft/agent-lightning/pull/707) | 删除后复用 rollout ID 时保留正确的完成分页与游标 |

2026-11-23 跟进时原六条 PR 均为正式待审，尚未合并。OpenHands 两条仍需符合上游就绪政策的关联 issue；Agent Lightning 的 Actions 需要维护者批准运行。ADK 合入新主干后的当前提交已在 Python3.11 / 3.13 复验相关集合，每版2021通过、26预期失败；[本次日志与源码哈希](evidence/pr-followup-2026-11-23/adk-validation.json)。这些范围不等于完整上游 CI。后续新贡献优先独立开发者与小团队维护的活跃高星 Agent 项目。

新增[GPT Researcher HTTP MCP令牌修复](docs/gpt-researcher-mcp-token.md)：原版11项回归失败、修复11项通过，其中3项经过真实受鉴权MCP/TCP；服务器完整离线选择1112项通过，跳过与排除范围单列。已正式提交#2367，尚未合并；服务器验证不等于上游CI通过。

新增[Browser Use 云会话下载修复证据](evidence/browseruse-cloud-download-key/README.md)：同一三入口回归原版失败、修复后通过，分页和停止后补收均保留会话授权；相邻与完整非Chrome检查通过，范围和跳过项单列。已正式提交#6521，未合并，服务器结果不等于上游CI通过。 后续评审补充修复超时创建的密钥清理与失败重试，最终服务器非Chrome选择969项通过；[补充证据](evidence/browseruse-cloud-download-key/review-followup/README.md)单列原生CI和两种不同失败基线。

新增[VoltAgent MCP 连接归属修复证据](evidence/voltagent-mcp-connection-ownership/README.md)：按审查补上会话清理和连接归属保护；拒绝第二次连接时保留已连接或正在启动的传输。上一版在同一组11项生命周期测试中2项失败，修复后11项及完整MCP包26项通过，源码与两份新增测试的严格类型检查、构建通过。保留[前一轮清理记录](evidence/voltagent-mcp-cleanup/README.md)；#1562为正式待审，服务器检查不等于上游CI通过。

[Agent Lightning 实际复现与修复](docs/lightning-terminal-reuse.md)：原版四个状态回归失败，候选相关53项通过；类型检查单独完成，未宣称全仓库或训练栈验证。

## 复查材料

[简历可用表述与证据（2026-11-23）](portfolio/resume-projects-2026-11-23.md) · [逐阶段记录与保留的失败](docs/project-history.md) · [两页中英介绍（2026-11-22历史快照）](portfolio/junzhe-wang-project-brief.pdf) · [快照正文与证据映射](portfolio/README.md)。

测试组有重叠，不能把历史数字累计成新的总成绩。完整提示、答案、token 向量、权重、服务器连接资料和凭据保留私有；公开材料提供来源、哈希、运行条件与结果边界。

[依赖升级鉴权兼容性](docs/dependency-upgrade-compatibility.md)：FastMCP原始与候选锁定环境执行相同279项上游鉴权测试，两组全部通过；源码与测试未改，完整CI和发布审批未执行。
