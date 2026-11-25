# Agent Reliability Lab

研究工具调用的模型效果，并构建可复查、可恢复的 Agent 执行与证据核对工具。项目同时包含真实 3B 模型实验、可安装的 MCP 服务，以及面向真实开源仓库的维护运行器。

个人主页只保留论文与项目简介；本仓库的后续材料不会自动发布到主页。

| 使用目的 | 入口 | 运行条件 |
| --- | --- | --- |
| 查看已完成的阅读与来源核查演示 | [离线核查页](examples/research-review/source-review.html) / [使用说明](docs/research-source-review.md) | 下载HTML后在浏览器打开；无需模型或服务器，公开演示使用自有合成文本 |
| 导入自己的资料并检索 | [0.4.0独立检索包](packages/research-library/README.md) | Linux CPU环境、本地E5权重；PDF是数字文本提取，非OCR |
| 用本地模型阅读论文 | [阅读助手运行步骤](extras/research-assistant/README.md) | 独立模型与MCP服务；该助手的已验证安装仍用0.2.0检索wheel |
| 审查固定依赖升级证据 | [LangGraph工作台](docs/dependency-workbench.md) | CPU确定性流程；已有模型接入结果单列 |
| 选择简历项目 | [三项精选](portfolio/resume-shortlist-2026-11-25.md) / [两类岗位附件](portfolio/role-briefs/README.md) | 按实际承担和掌握内容使用；附件含既有结果及边界 |

## 模型研究

使用固定 Qwen2.5-3B-Instruct 与 AgentRobustBench 源码，先审计训练/验证样本复用，再构建同 ID 配对数据、文本关联分组和有效监督标签预算。Full/Mixed 各实际执行 32 次 LoRA 更新、65,536 个监督标签；输入暴露与计算量并不相同。

Full 原训练的最终核验中断，保存检查点的独立回放通过，原失败保留；Mixed 完整核验通过。两组参考答案条件下的验证 NLL 为 0.297599 / 0.297934，不能据此声称工具调用准确率或鲁棒性提升。

同后端三组 clean 生成对照已完成：**base 118/199、full32 107/199、mixed32 105/199**。本配方未显示微调后的 clean correct 提升；不能宣称扰动鲁棒性或泛化提升。 资源恢复保留全部旧结果，最终599次预留/597条已提交，两个历史未知仍扣额。[完整对照与边界](docs/generation-complete.md)。

- [数据复用审计](docs/training-data.md)与[开发集、真实分词和标签预算](docs/training-study.md)。
- [监督目标与行为审计](docs/training-alignment.md)：固定推理文本占Full监督标签16.7%；对全部597条已保存结果进行配对诊断，并准备只屏蔽固定正文的损失掩码，后续配对训练结果见下方。
- [迁移评测输入准入](docs/bfcl-transfer-admission.md)：在读取参考答案前锁定250条BFCL派生输入，完成保护数据关联检查和10项CPU控制；准入阶段不含模型推理，后续生成与评分见下文；不是完整BFCL成绩。
- [迁移评分与参考绑定](docs/bfcl-transfer-scoring.md)：14项CPU控制和250条参考构造校验调用通过；保留原匹配规则，并拦截表达式求值分支、单列解析状态。这是评分链路验证，尚无新模型成绩。
- [固定正文屏蔽配对试验](docs/fixed-reason-ablation.md)：同初始化、同输入与同卡的两组各32步训练及完整核验已完成，共2,666次逻辑前向／零未知。整段验证NLL为Reference0.297588、Masked0.671653；外部固定250题的生成对照已完成，见下一条的实际成绩与边界。
- [固定250题生成对照](docs/bfcl-transfer-generation.md)：三组各250题已完成并统一离线评分，750份结果／0新未知；工具题200分别为147/200（73.5%）、150/200（75.0%）、153/200（76.5%）；Masked对Reference差值+1.5个百分点，p=0.5078125，尚不足以证明稳定收益。
- [实际 LoRA 配方、结果与核验边界](docs/lora-pilot.md)及[完整证据](evidence/lora-pilot/README.md)。
- [持久生成进度与恢复阶段记录](docs/generation-recovery.md)：12 项服务器 CPU 控制通过，已评分结果不重新生成或评分；最终结果见上方完整对照。
- [已保存调用的schema诊断](docs/tool-schema-diagnostics.md)：分别核对原始schema和上游FC投影。基线158/199例符合投影约束，其中41例仍未通过官方匹配；结构有效性不等于任务成功，部分Full对照尚无提升证据。
- [原 P100 工具调用基线](docs/tool-use-baseline.md)：119/199 官方 correct，属于历史设备条件，不改判为新设备结果。
- [工具调用研究路线与评分器审计](docs/robust-tool-use.md)。

## Agent 应用

**研究资料检索与阅读助手**：[检索服务](docs/research-library.md)基于LlamaIndex与CPU多语E5，支持资料目录导入、文档增量索引、原文/历史版本引用和三个MCP工具，提供已验证的[独立CPU启动包](artifacts/agentlab-research-0.4.0-starter.zip)。[全文按页检索](docs/paper-library.md)实际接入LightRAG/MiniRAG共32页，保留原PDF哈希、物理页码及历史引用；[新增阅读助手](docs/research-assistant.md)通过LangGraph/SQLite连接本地4B模型与真实MCP检索、原文读取及回答提交，使用持久请求额度和回复缓存支持恢复。引用读取契约不等于陈述正确，真实模型结果单列；旧固定检索诊断未显示混合排序的覆盖收益。

新增[阅读报告导出](docs/research-reading-report.md)：模型和MCP服务关闭后，批量整理已有回答、PDF页引用和未完成原因，生成[可阅读的记录](examples/research-reports/reading-report.md)。已用三个真实关闭运行验证，四条历史页引用回读、重复导出字节一致，新增生成/嵌入/GPU均为0；原模型两项提交通过、一项失败的结果保持不变。

新增[前沿论文实际接入](docs/frontier-reading.md)：接入2026年11月RECEIPT全文，资料库扩展到三篇52页、240片段；旧148个向量复用，仅新增92个片段编码。一次新的CPU模型阅读用了4次调用，引用核对通过，但机制解释不完整；[原回答及复核](evidence/frontier-reading/README.md)单列，未重跑优化分数，全程GPU为0。

新增[离线阅读页](examples/research-view/README.md)：单个HTML集中查看已有回答、页引用和失败原因，可搜索、筛选、打印及下载JSON。已用四个真实关闭运行和实际浏览器验证，保留原回答与状态；日常打开不需要模型或服务，新增推理和GPU使用均为0。[桌面/手机截图与验证范围](evidence/research-view/README.md)。

新增[批量资料检索](docs/research-batch.md)：跨文档填充编码批次，复用捕获版本的索引/词法统计，同题语义与混合排序共享查询向量；在完整SciFact 5,183摘要、300题上，BM25/E5/RRF的nDCG@10分别为0.6409/0.6479/0.7040。961次CPU前向全部完成、0未知，独立NIST评分复核通过；这是摘要相关性评测，不是论文问答准确率或公开BEIR榜单成绩。

新增[离线原文对照与备注交付](docs/research-source-review.md)：将已有回答和历史引用原文并排显示，备注绑定回答及来源指纹，支持下载后重新导入，拒收错版本记录。真实运行的六条PDF引用已回读，10项后端控制和14项浏览器检查通过；公开页面只展示自有合成文本，不公开真实论文片段，也不冒充人工复核或新模型成绩。

新增[可恢复批量检索任务](docs/research-batch-recovery.md)：逐题保存LlamaIndex检索结果，恢复沿用原资料版本并跳过已完成题目；失败/未知尝试继续扣固定额度，提供无需模型的状态命令。0.4.0独立包的真实CPU三题验证在第一题提交后强杀，新进程只计算余下两题，完成后重放零前向；原SciFact及生成结果不变。[执行证据](evidence/batch-recovery/README.md)。

**真实依赖升级审查 Agent**：[使用与结果](docs/dependency-upgrade.md)。固定 Browser Use / FastMCP 发布源码，执行离线漏洞扫描、保持声明的真实解析和候选复扫，再通过 MCP 核对八项事实。两个项目分别得到“原精确版本未升级”和“Authlib 升级候选可进入兼容性测试”的结果。9项单元与4场真实MCP脚本控制通过；真实9B完成两题、通过一题，失败原因和6次请求账本保留。

新增[LightRAG实际维护案例](docs/lightrag-dependency-upgrade.md)：LangGraph/SQLite工作台已接入第三个项目，完成RAGAS评估依赖升级、固定库复扫及发布版/主线各自配对的21项离线测试；[正式PR #4647](https://github.com/HKUDS/LightRAG/pull/4647)开放待审，上游CI等待批准。新流程模型调用和GPU使用均为零。

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
| [DeepTutor #2930](https://github.com/HKUDS/DeepTutor/pull/2930) | 统一MCP连接与probe的分页发现，处理空中间页、过滤、游标循环、后页错误和超时 |
| [RAGFlow #22752](https://github.com/infiniflow/ragflow/pull/22752) | 服务端关闭连接后重放CLI benchmark的JSON正文，保留迭代成功/失败与最终响应 |
| [LightRAG #4647](https://github.com/HKUDS/LightRAG/pull/4647) | 更新评估extra的RAGAS锁定版本，固定库复扫及发布版/主线配对兼容验证 |
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

新增[RAGFlow CLI请求体重放](docs/ragflow-cli-body-replay.md)：原版仅在`Connection: close`场景下POST/PUT/PATCH三个子例失败；修复后对照及完整CLI范围51个顶层测试通过，原构建脚本附带的原生单元层通过。初始keep-alive复现通过结果保留，避免扩大缺陷范围。已正式提交#22752，未合并；本轮仅服务器CPU，无模型或GPU调用。

新增[DeepTutor MCP工具分页发现修复](docs/deeptutor-mcp-pagination.md)：真实SDK/HTTP同组10项原版9项失败、修复全部通过；完整MCP192项及其他相关范围分别记录。#2930已正式提交、尚未合并，提交时上游Actions要求批准运行；整仓pre-commit保留原版同样存在的SVG文件尾格式失败，不宣称全部上游CI通过。

## 复查材料

[简历项目精选（2026-11-25）](portfolio/resume-shortlist-2026-11-25.md) · [现有项目总结与证据](portfolio/project-summary-2026-11-24.md) · [历史详细表述](portfolio/resume-projects-2026-11-23.md) · [逐阶段记录与保留的失败](docs/project-history.md) · [两页中英介绍（2026-11-22历史快照）](portfolio/junzhe-wang-project-brief.pdf) · [快照正文与证据映射](portfolio/README.md)。

测试组有重叠，不能把历史数字累计成新的总成绩。完整提示、答案、token 向量、权重、服务器连接资料和凭据保留私有；公开材料提供来源、哈希、运行条件与结果边界。

[依赖升级鉴权兼容性](docs/dependency-upgrade-compatibility.md)：FastMCP原始与候选锁定环境执行相同279项上游鉴权测试，两组全部通过；源码与测试未改，完整CI和发布审批未执行。

[逐部分NLL诊断](docs/loss-parts.md)：276条已有输入的标签分区与9项服务器控制通过；831次教师前向已完成，整段与逐部分损失、参数冻结及旧账本核验通过；不计作新生成或准确率。

[LangGraph依赖审查工作台](docs/dependency-workbench.md)：批量汇总固定扫描与兼容证据、SQLite断点恢复和Markdown/JSON交付。首批Browser Use/FastMCP快照完成12项测试与一次跨进程SIGKILL恢复，后续接入第三个LightRAG快照，按各自证据范围报告；工作台为CPU确定性流程，历史279项上游测试结果仅做证据接入。
