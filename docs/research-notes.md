# 从近期 Agent 工程资料到可验证任务

初次查阅：2026-11-20；后续核对日期见各节。以下区分原作者的主张、对本项目的推论和实际完成的实验。

## 持久会话、执行循环与工作区分别管理

Anthropic 在 2026-04-08 的 [Scaling Managed Agents](https://www.anthropic.com/research/managed-agents) 中，将持久事件记录、Agent 执行循环和执行环境分离，使其中一层失败时可以分别恢复或替换。原文也讨论了将运行代码的环境与服务凭据隔离。

对本项目的推论：checkpoint 不应仅存在于 worker 内存；验证进程的生命周期也需要独立管理。当前项目已有 SQLite 检查点、Git worktree 与验证监督进程，并有真实 SIGKILL 证据。它们仍在单机上，不等于该托管架构；没有多租户服务或主机故障保证。

## 完成条件需要外部证据

Anthropic 在 2026-03-24 的 [Harness design for long-running application development](https://www.anthropic.com/research/harness-design-long-running-apps) 中，讨论了把生成与评估分开，以及把任务拆解和结构化材料用于长时工作。其前端评价也涉及主观准则，不能直接当作本项目维护任务的量化结论。

对本项目的推论：模型说“完成”之后，仍应由固定版本上的独立命令验收。当前 Deep Agents 与 OpenHands 维护任务把验收代码固定在操作者任务定义中，允许编辑的生产文件不包含验收脚本。这里的判定来自真实工具结果与测试，不调用另一个模型评分。OpenHands 任务准备与执行结果以单独证据报告为准。

## Harness 之外仍有运行时需求

LangChain 在 2026-04-20 的 [The runtime behind production deep agents](https://www.langchain.com/blog/runtime-behind-production-deep-agents) 中，将持久执行、记忆、人工参与、观测与多租户等列为长期运行 Agent 的运行时需求。

对本项目的推论：不能用一个工具调用演示证明生产可用。当前只实现并验证了其中的维护任务恢复和补丁验收部分；模型效果、真实用户、多租户、远程调度与生产部署尚未验证。下一步先完成多任务模型试验，并保留失败轨迹，再决定是否扩大服务架构。

这些资料提供工程方向；本仓库的测试数字只来自自己的版本固定实验，没有套用原作者的性能提升或基准成绩。


## 2026-11-21: shared artifact cleanup as an engineering target

The [Google ADK contribution guide](https://github.com/google/adk-python/blob/c81876a49911745248f2b774c02770ed211ff460/CONTRIBUTING.md) permits a complete inline bug description when no issue exists, unlike several screened projects that require prior assignment or collaborator status. The [latest observed release](https://github.com/google/adk-python/releases/tag/v2.15.0) was v2.15.0; this contribution fixes and tests pinned main `c81876a`, not an assumed released-version matrix. The repository had 22,282 stars at intake; that is a dated observation, not a technical quality measure.

Artifact lifecycle is a practical boundary for multiple services sharing output storage. A real missing-entry race was reproduced, narrowed first and then expanded only after natural concurrent calls proved the root-only fix insufficient. [The final evidence](../evidence/adk-artifact-cleanup/README.md) separates deterministic tests, unforced filesystem observations, pre-commit setup failures and upstream draft status. The related cloud-adapter tests use fake storage; they do not show real cloud behavior or model task success.

## 2026-11-21：检索入口和主动 Agent 的结果反馈

LangChain 在 2026-10-23 的 [Context Engineering Starts with Retrieval](https://www.langchain.com/blog/context-engineering-starts-with-retrieval) 中，把检索问题分为搜索低效、单次结果过量，以及无关或过时内容；给出的文件工作流是先按名字或关键词定位，再分页读取。关键词不足时才考虑语义检索，不能据此推导所有任务都需要向量库。

对本项目的推论：先观察模型实际选择的入口及其完整请求，不能只提供一个新工具便假定它会被使用。已有[参考上下文审计](context-budget.md)在已知函数名的场景中发现 grep 的逻辑输入少于 AST；随后[真实模型尝试](long-cpu-maintenance.md)没有选用 AST 工具。因而实现了[首屏附加索引](read-index.md)，原始读取页完整保留、内容版本绑定；接口和恢复控制已验证，模型效果需要单独的真实试验。这不是对语义检索或通用性能的比较。

LangChain 在 2026-11-17 的 [What We’ve Learned Building Proactive Agents](https://www.langchain.com/blog/what-weve-learned-building-proactive-agents) 中，讨论由事件和调度触发的持续 Agent：记忆既来自已有材料，也来自用户反馈和行动结果；维护时要处理重要性、过期与重复，并用实际结果判断是否有益。

对本项目的推论：长期维护不能反复执行已知参考计划来增加数字，应保留失败如何改变下一步。当前记录已区分准备、脚本控制、真实模型结果及上游草稿状态；新一轮结果必须同时更新证据和求职表述。尚未实现学习型记忆、事件调度服务或生产主动 Agent，已有周期跟进也不证明这些能力。

较早的 Anthropic [Writing effective tools for agents](https://www.anthropic.com/research/writing-tools-for-agents)（2025-09-11）仍提供一个适用的评价准则：任务来自真实需求、结果可验证，除完成情况还记录调用、错误和资源消耗，并允许多条正确路径。这里据此记录模型的字面工具选择，避免把“必须调用某个工具”当作维护任务本身的成功条件；最终仍由固定原版测试与独立契约验收。
