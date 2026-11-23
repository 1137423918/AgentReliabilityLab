# Agent Reliability Lab

面向软件维护 Agent 的工具契约与可恢复执行：持久化工具进度、隔离代码改动，并生成可审阅的补丁与验证记录。

[两页中英项目介绍（2026-11-22快照）](portfolio/junzhe-wang-project-brief.pdf) · [正文、证据映射与生成方式](portfolio/README.md)。原始报告和开源贡献按日期核验，最新研究记录见本仓库。个人主页只保留论文与项目简介，后续实验材料不自动发布到主页。

## 3B真实工具调用基线

在单张P100上完成官方clean单轮199/199条，Qwen2.5-3B-Instruct/FP16，一题一次greedy生成，无本项目训练、反馈或重试。官方correct为119/199（59.80%）；3条存在声明必填参数缺失，其中0条仍满足官方匹配规则。官方分数、参数诊断和真实工具执行分别看待，不当完整鲁棒性或算法提升。199预留/199完成/0未知，子进程及GPU上下文均已清理。[分项、条件与复查](docs/tool-use-baseline.md) · [逐题指标及完整证据](evidence/agentrobustbench-baseline/README.md)。

## 训练输入已排除验证样本复用

实际读取官方Full3905/Mixed4000/训练验证79条：Mixed含全部79验证ID，其中4条完整prompt+gold相同。新生成两组各3905个同ID研究输入，排除79验证ID和16无Full对应ID；四种验证指纹交集为0，真实Parquet逐行重读一致、7889选择记录与原行哈希匹配。零模型/训练；完整语义去重、等token预算和训练器消费尚待验证。[方法、源码与完整证据](docs/training-data.md)。

最新[上游只读快照](evidence/upstream-current/README.md)：5开放/1草稿/0合并，两份Copilot COMMENTED非人工批准。ADK外部合入main形成新head，两个目标文件与历史已测版本相同，但不把旧2021项结果标为整个新head通过。

## 工具调用鲁棒性：算法研究与应用开发

后续同时关注算法/模型与Agent应用。已完成固定AgentRobustBench源码的数据和评分器CPU审计：2718静态记录、2527单轮可评；32个gold派生控制显示官方匹配分数需与工具必填参数有效性区分，该次审计零神经调用、无训练或准确率提升。计划把扰动数据训练与执行前检查做等预算消融，再迁移到实际项目证据核对助手；clean模型基线已单列于上文，训练数据的语义家族隔离、等预算训练和产品自然语言质量尚待验证。[源码、结果与路线](docs/robust-tool-use.md)。

真实9B GPU接入已安装MCP服务后，33/33层加载成功；首题44.008秒时检测到同卡其他计算进程，按协议中止。5次预留中4次HTTP200头、1次未知；没有落盘完整wire/最终答案，零已完成评分。自有模型/服务已退出、端口关闭，未重试。[原协议、账本与资源记录](evidence/mcp-agent-gpu/README.md)。这不替代旧CPU超时或构成GPU加速成绩。

## Semantic Kernel：取消调用方之后的后续异常

新增[草稿PR #14853](https://github.com/microsoft/semantic-kernel/pull/14853)：调用方取消响应Future后，Agent处理函数或异步工厂报错会触发InvalidStateError，跳过队列记账、阻塞空闲停机。仅增加一个保护条件；同四用例在原版2通过/2失败，候选4通过。服务器运行时/群聊97项通过（含四项），扩展176通过/12失败/1跳过，共同185个原版用例结果逐项相同；不累加范围、不称完整CI绿色。原配置钩子、两文件mypy与独立构建通过，无模型/GPU。源码和测试字节绑定完整前后对照，人工复核待完成。[使用、验证及局限](docs/cancelled-send.md) · [完整证据](evidence/sk-cancelled-send/README.md)。

## 实际 Agent 通过外部 MCP 核对贡献记录

接入实际 LlamaIndex FunctionAgent 与 MCP2 Client，句柄/回执由适配器保管，模型只选择报告字段和提交事实。四场真实SDK/TCP加脚本模型控制通过，共九次假回复，不是神经成绩。真实9B CPU首题600秒超时：六次预留、五份完整回复、一次未知仍扣额；四次读到报告回执但没有有效提交，第二题未运行。原130项核心快照的33份共享源码未改，本轮不增加或重跑该计数。服务已退出、端口关闭，准备与联调失败记录也公开。[使用与边界](docs/mcp-agent.md) · [完整轨迹和实际结果](evidence/mcp-agent/README.md)。

后续补上实际适配器清理缺陷：状态查询报错曾跳过关闭；现在工作流退出后用新传输关闭同一个审计，清理共10秒、可选状态查询最多2秒，不新建上下文或重试模型。10场真实MCP/LlamaIndex加脚本模型控制通过，包括畸形响应和合法工具错误两种独立故障；过期能力仍记关闭失败。21次假模型POST/零神经调用，不增加此前130项核心计数，也不覆盖历史模型超时。[源码、基线与全部结果](evidence/mcp-cleanup/README.md)。

## MCP：把真实报告核对做成可调用服务

可直接下载[独立启动包](artifacts/agentlab-evidence-0.1.0-starter.zip)：9033字节wheel、冻结依赖锁与九份固定公开报告。无需源码checkout或主Agent依赖，CLI启动前检查报告哈希。真实安装后八项控制通过，原130项完整回归再次通过、零跳过；两种范围分开，零神经/GPU调用。[安装命令](docs/mcp-evidence.md) · [实际安装证据](evidence/evidence-package/README.md)。

提供可运行的MCP2.3.0本机服务，独立审计上下文、读取回执、TTL和并发共享操作额度。完整130项回归通过、零跳过（新增6项包含在内）；另6场真实SDK/TCP控制通过，覆盖回执隔离、重连、最后一次额度争抢及读完但回复未收到时的取消。57次SDK尝试/56份完整回复，另测超限HTTP413；两个预定服务进程已退出、端口关闭。零模型/GPU调用，不计神经审计成绩。[部署、客户端与边界](docs/mcp-evidence.md) · [全部实际轨迹](evidence/mcp-evidence/README.md)。

## LlamaIndex：审计真实报告中的项目表述

实际 FunctionAgent / OpenAILike 接入8份固定真实报告，核对JSON事实、来源SHA与读取谱系。新增可选校验提交工具，保留原两步默认；服务器完整124项再次通过、零跳过（无新增核心测试），另6场SDK假回复控制单列。真实9B CPU三道固定问题中2题通过预声明结构化契约；GPU题判断与事实正确但缺2个约定字段，仍未通过。12次模型HTTP200/72683请求字节，保留全部wire/账本，不推导一般准确率或自主修复能力。[接口与复现](docs/evidence-audit.md) · [新策略完整证据](evidence/evidence-direct/README.md)。

[首轮两步方式](evidence/evidence-audit/README.md)在额外结构化调用遇600秒上限、零验收完成，后两题未运行；旧失败保留不改判。新策略提示与schema也改变，不宣称因果速度收益。

## OpenHands 补丁工具：避免同路径移动删掉源文件

最新上游版本中，普通、`./` 和符号链接别名指向源文件时，工具会报告成功但删除文件。通过真实公开入口复现，修复为执行任何排队写入前拒绝；正常移动保持可用。原版3项新检查失败，候选相关203项通过（含22项补丁工具检查，不相加），无模型推理。[源码、前后对照和完整日志](evidence/apply-move/README.md)。 [上游草稿 PR #7050](https://github.com/OpenHands/software-agent-sdk/pull/7050) 已提交、未合并，测试 CI 待维护者放行。

## 异步请求额度与 Pydantic AI 接入

新增独立 asyncio/HTTPX2 预算适配层与 8.4KB 小包，直接复用原请求账本；取消、并发、重启和 SDK 自动重试共享次数及 JSON 字节额度。服务器完整116项回归通过（新增8项已计入），另有4场真实 Pydantic AI SDK/工具控制：8次假服务POST、3250字节，一次在途取消保持未知并占用额度；不计神经推理或模型修复。创建必须使用新目录，恢复时缺失账本拒绝重建。[证据、保留的失败和边界](evidence/async-budget/README.md) · [独立包用法](packages/durable-budget/README.md)。

## 验证生命周期：清理独立会话子进程

验证命令退出0后遗留后台子进程的缺陷已在服务器复现。Linux监督器改为接管并回收孤儿后代，同时绑定worker已加载的监督器源码，避免过滤环境后命中旧安装包。定向5项、完整108项回归通过，新增2项已计入；覆盖双重fork、超时、worker强杀恢复与无关进程隔离。[结果、首版集成失败与限制](evidence/verification-tree/README.md)。这是CPU工程验证，没有新的模型修复分数。

## GPU链路：工具往返通过，原样文本检查失败

单张空闲RTX3090加载固定9B社区Q4模型，原生日志33/33层卸载与32K上下文、三次HTTP200/2209字节。强制函数参数和受约束结果JSON通过；原样READY因空think标签失败，保持整场未通过。服务退出0并释放端口与GPU上下文。两次零请求启动检查失败、三份预声明协议和原始请求/回复/账本均保留。[完整结果与限制](evidence/gpu-smoke/README.md)。没有自主仓库修复或新增106项回归成绩。

## CPU构建CUDA依赖的准备记录

固定llama.cpp源码与41份工具链包，服务器CPU实际编译独立llama-server及CUDA后端，前后4496份源码哈希一致；ELF静态检查确认sm_86及后端入口。没有执行新服务或模型，不计GPU加速/修复或新增106项回归成绩。NFS配置超时与Ninja独立进程组造成的早期内存采样缺口均保留。[复现材料](docs/cuda-preparation.md) · [完整日志与限制](evidence/cuda-build/README.md)。

## 9B CPU后续：连续读取，仍无修复

独立预声明轨迹保持ADK症状、清单策略、受保护验收与预算，改用已校验Qwen3.5-9B社区Q4_K_M及presence1.5；1721.383秒后八次请求用尽，八次read_file依次读取1–800行，没有编辑、补丁或验收。201769请求字节，原生服务正常退出，完整失败公开。106项工程回归未重跑，不作模型或性能收益结论。[协议、版本限制与实际轨迹](evidence/adk-9b-cpu/README.md)。

原CPU包继续独立保留；新的CUDA依赖已完成CPU编译，GPU短请求验证已有独立记录；实际维护任务与输出解析配置另立协议。

## 已知文件任务的工具范围

新增显式`file_inventory_v1`：从固定任务生成完整有界路径清单，模型请求不含ls，仍发出的调用在后端前明确拒绝。按图创建，保留同别名其他任务的默认工具；glob、读取、搜索和编辑仍可用，版本哈希、额度与验收没有放宽。

文件清单阶段的服务器完整回归**106项通过、零跳过**（六项新增检查包含在内）；实际HTTP、后端未执行、同别名隔离、首屏索引组合、真实SIGKILL恢复和wheel入口覆盖。[配置契约](docs/file-inventory.md) · [完整日志与准备失败](evidence/file-inventory/README.md)。这些是明确假模型的接口检查，不计神经修复成绩。

保持原ADK症状、模型、采样、验收与预算的独立真实轨迹运行1525.938秒，八次请求后停止：零ls，但仍无编辑、补丁或验收。一次符号查询因漏传版本哈希被拒绝，之后继续重叠读取；SDK工具状态错误计数0与实际结构化错误1分别记录。累计205121请求字节，未耗尽字节或整场时间上限；没有回溯增加额度。[协议、实际选择与用量](evidence/inventory-cpu/README.md)。没有证明性能或模型收益，原失败保持。

## ADK真实模型：八次请求，未形成编辑

在既有产物并发删除问题上，用固定Qwen3-4B Q4_K_M运行一个新正常轨迹，加入现有源码工具的导航提示但不提供修改方案。**913.965秒后触发请求次数上限，零通过补丁**：先查询四级目录，再定位删除实现、list_versions与类首屏；八条工具结果，无虚拟编辑、补丁导出或验收执行。下一次在网络发送前被额度守卫拒绝，实际累计119155字节，未耗尽字节或整场时间上限。活动状态放本机ext4，服务退出0、端口关闭，未用GPU。

[固定任务和协议、实际顺序及全部日志](evidence/adk-focused-cpu/README.md) · [复现边界与下一假设](docs/adk-focused-cpu.md)。模型、任务、提示与存储同时变化，不作因果或一般成功率比较；旧失败和脚本参考控制分别保留。本轮未改worker核心，也未重跑100项项目回归。

## 本机状态准入与共享归档

已修正实际发现的NFS/WAL放置问题：worker和repair在创建状态目录前、拿锁前及持锁后检查本机文件系统和既有持久控制文件，拒绝网络/未知类型及控制文件链接；不自动迁移旧状态或重置模型额度。代码与便携工件可保留共享位置，活动检查点留在已确认的本机存储。

存储修正版本的服务器完整回归 **100项通过、零跳过**（含十项新增存储检查）。真实NFS新建拒绝未创建目录，旧NFS状态字节与mtime保持；Deep Agents在ext4上的正常/首读SIGKILL恢复补丁一致，各通过复用的113/119/28验收组。关闭任务后的SQLite备份重建相同审计JSON，完整数据库/私人ZIP不公开，也不声称可执行任务迁移。仅这两个本机参考场景，不新增神经修复成绩；其余历史仓库控制仍是原条件下的观察。[准入和操作](docs/local-state.md) · [协议、源哈希与实测](evidence/local-state/README.md)。

## 只读检查运行进度

`python -m agent_lab.inspect_run --run-dir /path/to/run` 使用只读SQLite事务及图的get_state重建增量消息，不调用模型、工具、恢复或验收。输出最多8KiB元数据，含工具进度、待执行节点和当前虚拟文件SHA，不输出提示、参数或源码。现有结果状态仅作观察，不冒充重新验收。

该审计版本服务器完整回归 **90项通过、零跳过**，含八项新增审计检查。已查看正在运行的真实模型任务、两个历史参考检查点，并通过解包wheel入口的实际调用；无新增修复成绩。只读SQLite仍可能创建空WAL/SHM协调文件。实际旧状态路径为nfs4，后续已加入本机状态准入（见[本机状态策略](docs/local-state.md)）；旧控制不代表网络WAL部署受支持。[接口与限制](docs/run-inspection.md) · [完整日志与包验证](evidence/inspection/README.md)。

## 模型请求预算：跨重启、跨修复轮次

新增显式 `model_request_budget_v1`：在实际发送 HTTP 前持久化预留请求次数、单次请求体字节和累计请求体字节。503、超时和未知在途请求不退款；恢复不会重领额度，修复候选共用父运行账本。缺失或损坏的账本停止执行，完成缓存不新增请求。

该预算版本的服务器完整套件 **74 项通过、无跳过**，含 11 项预算故障检查；独立新环境安装了 jsonschema，因此此前跳过的 14 项现在实际运行。新增检查包含真实 SIGKILL、六进程争抢三份额度、HTTP 503/超时、共享修复预算和异步入口拒绝。

真实 Deep Agents 仓库的正常 / checkpoint 后 SIGKILL 恢复控制各发送 3 次 HTTP，中断前后账本身份不变，两场获得相同请求体哈希与补丁；各通过 113 条固定原版测试、119 条候选测试和 28 个契约，三组重叠不累加。响应由明确的操作者假服务计划驱动，不计神经模型自主修复。这是请求传输上限，不是 token、费用或恰好执行一次的承诺。

[配置、恢复及边界](docs/model-request-budget.md) · [完整测试与实际请求账本](evidence/model-request-budget/README.md)。新 Qwen3.5 预算预设已准备，神经运行尚未进行。


## 可恢复的维护运行器

`agent_lab/` 将 Deep Agents、LangGraph SQLite checkpoint 和隔离 Git worktree 接起来：固定任务与文件范围 → 虚拟文件编辑 → 导出补丁 → 显式命令验证 → `ready_for_review`。不会自动提交或合并。

- **首轮 33 条测试通过**：证据一致性、运行器、本地模型传输与有界修复，覆盖真实 SIGKILL、并发抢占、任务变更、人工修改保护、验证失败/超时、日志完整性与跨重启预算。
- **真实仓库四场景通过**：正常运行，以及检查点、补丁落地后、验证前的三处 SIGKILL。恢复后均完成两次工具操作，生成相同的 1573 字节补丁，分别通过 119 条上游测试。
- **验证进程运行中恢复通过**：观察到真实上游 pytest 进程后，仅杀 worker PID；监督进程在释放运行锁前终止旧验证。恢复后重新验证，补丁与正常运行一致，各通过 119 条测试。
- 上述实验使用固定工具计划，验证基础设施行为；没有声称模型自主修复能力。`local-openai` 已取得真实 CPU 模型响应；维护任务结果见下节。

[完整恢复协议与边界](docs/durable-worker.md) · [四场景报告](evidence/recovery/report.json) · [验证中断报告](evidence/verification-supervision/report.json) · [33 条测试日志](evidence/repair-loop/logs/repair-full-tests.log)

```sh
uv sync
uv run agent-lab-worker --repo /path/to/deepagents \
  --task tasks/deepagents-path-maintenance.json --run-dir /path/to/local-state/maintenance-001
# 使用相同任务和 run-dir 恢复；验证依赖须先按任务说明准备。
```

故障矩阵入口：`benchmarks/recovery_matrix.py`。实验固定上游 commit 和任务哈希，先断言验证时导入的是 worktree 源码，再运行官方测试。检查点数据库与完整对话留在私人运行目录；仓库只保存检查过的结果与日志。

模型试验预设：[任务与独立验收](tasks/deepagents-path-model-baseline.json)、[正常/恢复两次试验入口](benchmarks/model_pilot.py)、[接入与验收自检报告](evidence/model-readiness/report.json)。基线保留 6 个独立契约失败，参考修复通过全部 28 个；模型文件已按固定版本逐文件校验。HTTP 测试服务是明确的假服务，不能计为模型自主修复结果。

## 第三个维护目标：Google ADK

同一 Deep Agents 编辑运行器已接入 Google ADK 的真实文件产物维护任务：只允许修改一份生产文件，固定原版测试副本，并运行四个独立文件系统契约。正常运行、首次工具检查点后、补丁落地后和验证前三处真实 SIGKILL 恢复均完成三次编辑，补丁一致，生产代码与此前已验证的 PR 候选字节一致。

每场通过 1863 条原版测试、26 条预期失败及四个外部契约；测试组重叠且复用既有回归，不能累加为新测试成绩。四场整组用时 470.386 秒。使用明确的参考编辑计划，只验证第三个真实仓库的执行与恢复；不是新增 ADK agent runner 适配器或模型自主修复结果，当时独立模型任务尚未运行；后续新[4B导航提示变体](evidence/adk-focused-cpu/README.md)已实跑但无编辑，原始预设仍未运行。

[复现与计时边界](docs/adk-maintenance.md) · [负对照、四场日志和补丁](evidence/adk-maintenance/README.md)。原有运行器核心未改，74 项核心测试未重复执行。

## 无空闲 GPU 时的真实模型试验

在授权服务器的 CPU 上完成固定版本 Qwen3-4B-Instruct-2507 的 FP32 与动态 INT8 推理。两种配置各运行正常与检查点恢复模式：**四次维护尝试均未产出补丁，也未进入官方验收**。这是同一个公开问题的运行变体，不是四个独立基准任务。四次请求都触及生成时限且没有解析出的工具调用；恢复中断点工具结果为零，不能算模型工具进度恢复成功。

独立短诊断生成了括号包裹的工具 JSON，但没有原生标签，被严格解析器当作文本。生成速度、截断和格式互操作仍需分别排查。公开两份预声明协议、七次真实生成、精度和资源限制、源码快照及原始/公开哈希；没有把失败替换为参考修复。

[完整协议与复现](docs/cpu-model-pilot.md) · [全部失败记录](evidence/cpu-model/README.md) · [机器可读报告](evidence/cpu-model/report.json)。GPU 推理与模型自主修复通过结果仍待取得。新增 CPU 服务和快照校验入口已在服务器分别检查，未计入前述 33 条核心测试。

后续增加了[声明工具的格式兼容](docs/tool-format-compat.md)：原生标签模式保留，显式兼容完整 JSON / 括号 JSON；两种模式都校验工具名和参数 schema，拒绝未知函数、截断内容与无效批次。最终 14 项针对性服务器检查通过，四份历史维护输出仍为零工具调用。新鲜模型请求成功解析并执行了一次只读文件工具；但返回工具结果后，模型回答 `None`，未通过预先声明的完整往返验收。[原始响应与失败记录](evidence/tool-compat/report.json)均保留。新[文件清单任务](tasks/deepagents-path-model-grounded.json)只改提示词，验收和预算保持不变，后续运行见下文。

该文件清单任务随后在[原生 CPU 后端](docs/native-cpu-pilot.md)实际运行：固定权重转换为约 2.50 GB 的 Q4_K_M GGUF，以官方 llama.cpp、4 线程执行正常与检查点恢复模式。两种场景均在 600 秒上限终止，无导出补丁或官方验收；最后保存 9 / 13 条工具结果。中断前的两条目录查询状态得到保留，完整任务仍未通过。正常场景还留下含字面换行转义、静态语法无效的虚拟写入，已作为失败样例保留。[协议、派生模型身份及完整证据](evidence/native-cpu/README.md)。新增启动器的 3 项 Linux 进程清理检查通过，独立于前述测试组。

## 原版测试验收与语法导出保护

针对真实 CPU 维护失败增加两项显式策略：导出前检查指定 Python 文件语法；另建固定基线测试副本，在候选生产代码上执行未被改写的原版测试，同时保留候选自己的新增测试。验证后、缓存复用前和失败反馈前检查副本与日志完整性；修改验收副本，即使命令退出 0 也不接受。

本次完整服务器回归 **42 项通过、14 项跳过**（共 56 项，跳过项需要该环境未安装的 jsonschema），包含前述 33 项、3 项启动器检查和新增 6 项保护检查。14 项解析兼容检查曾在独立环境通过，未计为本次通过。该阶段新 [protected 模型任务](tasks/deepagents-path-model-protected.json) 尚未运行；后续仅更换模型预设的实际试验见下节。原有模型失败记录保留，不声称模型修复成功率提高。

[配置、恢复与安全边界](docs/protected-grading.md) · [真实仓库脚本控制证据](evidence/protected-grading/README.md)。

## Qwen3.5-9B 的受保护维护试验

在服务器以固定第三方 Q4_K_M 和官方 llama.cpp、4 线程 CPU 实际运行同一个维护问题的正常与检查点恢复场景。**两场均因单次请求 180 秒超时失败**，分别耗时 185.324 / 376.219 秒，未触及 600 秒场景上限；无虚拟文件改动、导出补丁或官方验收。恢复前保存两条 read_file 结果，续跑后共四条，只验证读取状态继续，不能称编辑恢复或任务完成。

普通运行处理 2442 个提示 token 用时 172.58 秒，显示当前 CPU 与请求预算的约束。模型、采样与验收策略和旧 4B 运行同时有变化，不据此作能力或性能的因果比较。新增显式采样传输和模型别名，历史任务默认参数保持；生成前完整服务器回归为 **43 通过、14 跳过**（57 项，含此前 42 项和新增 1 项 HTTP 测试）。模型/模板/二进制/依赖哈希、预声明协议、失败日志与服务强制回收记录均保留。

[复现协议](docs/qwen35-maintenance.md) · [全部结果与边界](evidence/qwen35-cpu/README.md) · [机器可读报告](evidence/qwen35-cpu/report.json)。新权重由量化方发布，未声明精确原权重 revision；参考模型卡不等于已验证转换血缘。两场不是独立基准任务，无模型自主修复成功声明。

后续单独声明的 [30 分钟正常场景](docs/long-cpu-maintenance.md)已执行：同一模型、任务提示与验收，加入源码工具和持久化请求预算，单请求 600 秒、整场 1800 秒。最终在整场上限终止，保存 5 次回复、6 条工具结果（5 次读取、1 次 grep），无虚拟改动、补丁或验收；模型没有选用已提供的 `inspect_python`。

六次请求共预留 174278 字节，未耗尽八次/262144 字节预算，最后一份在途请求仍占用额度。已保存五份回复的输入/缓存读取/输出分别为 32015/23338/415 token，原生日志中的已完成请求新 prefill 合计 8677；这些统计不含第六份请求的未完成工作，不是全场算力或账单。首份实际请求与参考 AST 控制体哈希一致，且实际报告输入同为 2732 token；工具可用不代表模型会使用它。新 CPU 主机、工具与预算都有变化，不作因果或通用成功率比较。[全部失败与 usage 证据](evidence/long-cpu/README.md)保留，服务已清理。

## 附索引入口的真实模型运行

独立声明的一次正常CPU试验已运行，在1800.035秒整场上限结束：4份回复、5次读取、2份附加索引，0虚拟改动/补丁/验收。第三份回复选择生产文件821–920行，覆盖相关函数，随后继续读取；这不证明索引导致收益，也不等于完成修复。5份请求共143169字节，最后在途仍扣额度，次数和字节预算未耗尽。

保存回复的输入/缓存读取/输出为26043/17038/380token，输入减缓存9005与四条原生prefill计数一致；第五份未完成工作不含在完整usage内。原生进程宽限后强制回收，端口关闭。另确认旧状态路径为nfs4，SQLiteWAL不支持这种部署；后续已加入本机状态准入，见[本机状态策略](docs/local-state.md)；本次旧试验保持原记录。[声明、选择与边界](docs/indexed-cpu-maintenance.md) · [全部证据](evidence/indexed-cpu/README.md)。

## 让已有文件读取带上定位信息

针对实际模型未选用源码工具的问题，新增显式开启的 `python_read_index_v1`：在大型 Python 文件首屏前附最多 2 KiB 当前定义索引，原始页完整保留，总回复最多 8 KiB；检查点中的可见版本标记去重，编辑后刷新，混有写入的批次跳过。

该索引版本服务器完整回归 **82 项通过、零跳过**（含八项新增检查）。真实仓库关闭/开启/开启后首读 SIGKILL 三场，原始读取页逐字节一致、索引跟随编辑、四次工具与参考补丁一致，各通过复用的 113 / 119 / 28 验收组。明确的参考计划，不是模型自主修复；该接口阶段只准备新模型任务；后续独立实跑见上节，尚未证明净收益。[接口和复现](docs/read-index.md) · [日志与完整边界](evidence/read-index/README.md)。

## 当前虚拟源码的符号定位

新增可选 `python_source_v1`：通过 AST 列出函数、类与嵌套方法，再按位置读取有限源码片段；每页最多 8192 UTF-8 字节，以内容哈希绑定分页和符号 ID，编辑后旧哈希拒绝。工具只读当前检查点内的虚拟文件，避免从旧 checkout 生成索引；非 Python 或语法错误仍可用现有文件工具。

服务器完整回归 **49 通过、14 跳过**（63 项，含此前 43 项和新增 6 项）；真实 Deep Agents 参考编辑在正常运行与生产文件编辑后 SIGKILL 恢复两场中生成一致补丁，各通过 113 原版 / 119 候选测试与 28 契约，且索引哈希匹配已编辑内容。目标符号与编辑计划由操作者提供，不计模型自主定位或修复成绩。

[工具接口、预算和使用](docs/source-navigation.md) · [源片段、恢复与回归证据](evidence/source-navigation/README.md)。新增工具会增加 schema 和提示开销；片段字节数不等于净 token、耗时或费用节省。新神经模型预设已准备，尚未运行。

## 完整请求的上下文预算审计

通过实际 worker、Deep Agents 和 ChatOpenAI HTTP 传输，对同一已知函数目标比较三种操作者检索计划，逐行核对86行目标原文与虚拟文件未改动。14份真实请求JSON体、完整提示和原生GGUF词表token序列公开；参考渲染包含系统提示、所有工具schema和历史。顺序读取、grep后读span、AST检索的累计逻辑输入分别为 **43990 / 11341 / 19054 token**，AST首请求额外286。

这个已知名称的场景里grep更省。后续CPU回放通过固定原生服务库的实际请求转换函数，14份提示字节与完整token数组均与参考结果一致（仅限这些输入和配置）。逻辑输入重复计算可缓存前缀，不等于净推理耗时、费用或成功率。固定计划与假模型只验证真实工具和传输，不计模型自主定位或修复；运行器核心未改、63项原项目测试未重复跑。[协议与完整口径](docs/context-budget.md) · [14份请求、token序列与哈希](evidence/context-budget/README.md)。


新增[原生服务转换回放](docs/native-template.md)：不创建推理上下文，直接调用原版 `oaicompat_chat_params_parse`，核对原有14份输入；[逐请求证据](evidence/native-template/README.md)与准备失败均公开。这14项不累加到既有74项核心回归，也没有新增神经模型成绩。

## 有界的编辑、验收与修复

`python -m agent_lab.repair` 可以把完成的验收失败反馈给下一轮，继续编辑上一份候选。默认额外修复 0 次，可显式限制为 0–3 次；每轮有独立的检查点、Git worktree、补丁与日志，失败候选保留。反馈含日志哈希和最多 8 KiB 尾部；重启不会因为重置内存计数而增加轮次或重跑已有失败验收。日志或工作区被改动会停止自动流程。

[使用、预算与边界](docs/repair-loop.md) · [无固定计划的模型修复任务](tasks/openhands-undo-model-repair.json)。HTTP 测试使用假服务；真实仓库参考流程使用明确的固定计划，不是神经模型修复效果。

## OpenHands 撤销失败后的历史保留

在第二个框架 OpenHands SDK 中，通过真实只读目录复现：文件依次编辑为 0、1、2 后，撤销写入失败会提前消耗历史，恢复权限后重试错误地跳到 0。改为先读取历史、成功写回后再弹出，重试恢复 1，再次撤销恢复 0。

- [上游草稿 PR #7032](https://github.com/OpenHands/software-agent-sdk/pull/7032)：已提交，未合并；等待人类说明与维护者评审。
- 公共工具回归在原版失败、修复版通过；服务器上 185 条文件编辑器、规划编辑器与路径规则测试通过，相关 pre-commit 检查通过。
- [复现脚本、前后日志与哈希](evidence/openhands-undo/README.md) · [最小源码补丁](evidence/openhands-undo/fix.patch)。固定上游 `722e5d4`，Python 3.13.18，无模型或 GPU 调用。

这是受控的真实文件系统故障验证，不是生产事故或模型能力评测；不承诺历史缓存与文件写入跨崩溃的原子事务。

该缺陷也形成了第二个真实维护对象的[任务与复现协议](docs/openhands-maintenance.md)：模型任务无固定计划，参考任务仅用于故障验证；两者使用相同的操作者验收，且检查导入源来自 worktree。运行器本身仍为 Deep Agents / LangGraph，不声称已实现 OpenHands Agent 运行时适配器。

**OpenHands 维护任务四场景通过**：正常运行与检查点、落地后、验证前三处真实 SIGKILL 恢复，均完成三次工具操作，输出相同的 1,795 字节补丁，各通过同一组 184 条原有测试与独立权限验收。[自检与恢复证据](evidence/openhands-maintenance/report.json)。这是脚本计划驱动的运行器验证；184 不与 PR 的 185 重复累加，真实模型任务仍待运行。

[近期官方工程资料与本项目的取舍](docs/research-notes.md)记录了方向来源、推论和已验证边界。

## Google ADK 产物并发清理

[上游草稿 PR #8278](https://github.com/google/adk-python/pull/8278) 修复两个文件产物服务并发删除时的 `FileNotFoundError`：处理递归遍历中已消失的文件和目录，保留其他错误及嵌套产物。Python 3.11 / 3.13 各通过同一组 **2021 条相关测试、26 条预期失败**；原版的四项新检查为三失败、一项权限对照通过。无调度干预的公共 API 20 轮对照：原版每轮出现错误，最终候选均成功清理父版本并保留嵌套内容；不是通用成功率或速度对比。

这是第三个框架的存储贡献，未合并；没有新增 ADK 维护 Agent 运行时适配器。真实模型修复结果仍为此前的失败记录。新增复现脚本未改动运行器核心，本轮未重复执行不受影响的 42 项项目检查。[完整协议](docs/adk-artifact-cleanup.md) · [证据、初版失败和边界](evidence/adk-artifact-cleanup/README.md)。

## Langflow / LFX 检查点的数值保真

在活跃发布分支复现 NaN、正负 Infinity 经真实 SQLite 保存/重开后静默变为 None，生产节点却仍被标记 built。候选在模型 JSON 导出前检查原始字段，复用已有 opaque-drop 与恢复重算机制；不改通用输出序列化或 wire 格式。

原版新增检查 **12 失败 / 2 个有限对照通过**；候选完整检查点与持久化目录 **105 通过 / 5 项既有弃用警告**，含14项新增检查。实际连接图验证生产节点重算及下游结果。广泛图目录为 **682 通过 / 3 失败 / 6 跳过 / 1 预期失败**，失败及原版对照完整披露，不声称全仓库 CI 通过。

**候选尚未推送、PR 尚未创建**：GitHub 因当前令牌缺少 workflow 权限拒绝导入上游发布分支；四文件补丁未改工作流，等待授权；[复现协议](docs/lfx-checkpoint-numeric.md) · [日志、哈希与边界](evidence/lfx-checkpoint-numeric/README.md)。无模型或 GPU 调用，不计模型自主修复；旧检查点已丢失的数值不可恢复，重算仍可能重复副作用。本轮未改运行器核心，63项项目检查未重复运行。

## Semantic Kernel 取消回调的重入死锁

在另一个真实框架的实验性 Python 运行时中复现同类锁范围缺陷：用户清理回调读取 token、登记回调或等待其他读取线程时阻塞。候选在锁内切换状态并取出回调，释放锁后执行；future关联复用同一规则，保留异常传播和幂等取消。

原版新检查6失败/4通过；候选运行时与群聊目录 **103项通过**。真实 InProcessRuntime 的待处理请求在原版进入清理后卡住，候选只清理一次、取消请求和处理器并正常关闭。[开放PR #14845](https://github.com/microsoft/semantic-kernel/pull/14845)未合并；2026-11-22刷新状态时已非草稿，收到一条Copilot机器人COMMENTED记录，无行内修改意见，人工批准仍待完成。以下103项等数字保留该轮原始验证口径。

更广范围为182通过/12失败/1跳过，原版同一范围176通过/18失败/1跳过；除六项新回归外，12个失败ID完全一致，不能声称完整Python CI绿色。103项与新10项都包含于广泛范围，不累加。mypy两文件和适用pre-commit通过，wheel字节核验通过；一项原有uv配置弃用警告保留。无模型/GPU，也未添加新的维护worker适配器。

[复现与边界](docs/semantic-kernel-cancellation.md) · [日志、堆栈、补丁与哈希](evidence/semantic-kernel-cancellation/README.md)。本轮未改动自身worker核心，既有74项项目回归未重复执行；103项属于上游单独验证。

## AutoGen 取消回调的锁范围

在 AutoGen 的真实公共 API 中复现取消死锁：回调查询自身 token、登记另一个清理回调，或等待其他线程读取 token 时，会再次申请仍被持有的锁。候选在锁内修改状态并复制回调列表，再释放锁执行；已取消 token 的回调登记和 future 关联复用同一逻辑。

原版六项新死锁检查失败，三项旧检查及一项新增兼容检查通过；候选完整 **autogen-core 测试目录 233 项通过、3 项既有警告**，七项新增检查包含在内。真实 AgentRuntime 公共流程也由卡在清理回调，变为只清理一次、取消请求和处理器并关闭运行时。没有模型或 GPU 调用，不作超时前后的加速比。

修复已推送到 [个人 fork](https://github.com/1137423918/autogen/tree/fix/cancellation-callback-deadlock)。**上游已归档只读，创建 PR 被 HTTP 403 拒绝，没有新建 AutoGen PR。** 当前仅为候选修复；AutoGen 的新项目迁移方向是 Microsoft Agent Framework。本轮未修改运行器核心，63 项项目检查未重复执行；233 项属于 AutoGen 单独的包级验证。

[复现与边界](docs/autogen-cancellation.md) · [日志、最小补丁与发布状态](evidence/autogen-cancellation/README.md)。

## 工具契约验证边界

`prepare.py` 从指定 Deep Agents checkout 提取 `to_posix_path` 与 `validate_path` 的**原始函数源码**，生成无第三方依赖的最小复现模块；`audit.py` 在服务器运行固定契约用例，保存逐例输入、期望、观察和判定。

这是隔离函数的契约检查，不代表完整包集成测试、Agent 成功率或模型能力评测。报告包含原始源码 SHA-256、上游 commit 和提取范围。后续扩展跨框架适配器与模型自主维护任务评测。

## 已完成的包级验证

在同一上游基线中新增 6 条路径规范化案例和 1 条实际 Agent 图回归：混合分隔符路径写入后，再通过规范路径读取。模型返回由固定脚本驱动，用于检查框架行为。

原版在两个相关测试文件中得到 **124 通过、7 失败**。候选修复恢复这 7 条回归，并在覆盖路径工具、同步/异步文件工具及权限判断的四个测试文件中取得 **380 通过**；Ruff、格式与 `ty` 类型检查均通过。

- [包级验证范围与结果](evidence/package-regression.json)
- [修复前测试日志](evidence/package-baseline.log)
- [修复后测试日志](evidence/package-candidate.log)
- [候选上游补丁](evidence/deepagents-normalize-separators.patch)
- [网站与复现记录](https://1137423918.github.io/#lab)

公开日志替换了服务器私人路径，测试结论保持原样。Deep Agents 候选修复尚未提交上游 PR；OpenHands 草稿 PR 状态见上节。真实 CPU 模型尝试已记录，尚无通过验收的模型补丁。

包级复现：从 `langchain-ai/deepagents` 的 `744a797e3b9495539ca35571eeffd112a205f5c8` 创建独立 checkout，应用 `evidence/deepagents-normalize-separators.patch`，在 `libs/deepagents` 中执行 `uv sync --all-groups --frozen`，再运行：

```sh
make test TEST_FILE="tests/unit_tests/backends/test_utils.py tests/unit_tests/test_file_system_tools.py tests/unit_tests/test_file_system_tools_async.py tests/unit_tests/test_permissions.py" PYTEST_EXTRA="-n 2" COV_ARGS=
```

候选源码分支：[1137423918/deepagents](https://github.com/1137423918/deepagents/tree/1137423918/sdk/normalize-backslash-paths)。上游代码片段及补丁上下文的 MIT 许可见 [evidence/UPSTREAM_LICENSE](evidence/UPSTREAM_LICENSE)。

```sh
python3 prepare.py --checkout /path/to/deepagents --out prepared
# 在服务器上运行：
python3 audit.py --module prepared/baseline.py --cases cases/path_contracts.json --output outputs/baseline.json
```

退出码：0 全部通过，1 契约存在不符，2 配置或加载错误。报告失败不等价于安全漏洞；须结合实际调用链确认影响。

## 比较修复前后

```sh
python3 compare.py outputs/baseline.json outputs/candidate.json --output outputs/comparison.json
python3 -m unittest discover -s tests -v
```

比较器要求测试集哈希、验证范围和逐例输入/期望相同，拒绝缺失或重复案例，分别报告修复、新回归和仍失败的案例。候选仍有失败时退出 1；输入不兼容时退出 2。

评测脚本自身的 8 条单元测试已在授权 Linux 服务器上通过，覆盖数据集变化、伪一致哈希、结果缺失/重复、新回归和未预期工具异常。运行日志见 [evidence/evidence-tests.log](evidence/evidence-tests.log)。

项目不包含模型 API 凭据、服务器连接信息或上游环境。所含上游源码与补丁上下文归各上游项目及其贡献者所有，受对应 MIT 许可证约束；许可随各证据目录保留。

解释文字复核：测试范围题虽通过预声明结构化契约，解释仍称116+203=319的算术成立，却未清楚否定把319标为核心检查数，存在口径歧义。模型原文保留，不将结构化通过描述为所有文字都正确；自由解释语义仍不在自动评分范围。
