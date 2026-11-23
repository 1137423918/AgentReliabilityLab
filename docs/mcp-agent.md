# LlamaIndex 通过外部 MCP 读取报告

面向项目、实验和贡献记录的核对：Agent 可以自己选择报告及 JSON 字段；外部 MCP 服务负责读取来源、发放回执及核对提交事实。适配层持有审计句柄和回执，模型只看到报告数据及事实 schema。它不在本地重新实例化 EvidenceCatalog，也不在远程失败后退回本地读取。

`benchmarks/llamaindex_mcp_audit.py` 使用实际 LlamaIndex FunctionAgent、OpenAILike、MCP2 Client 和 Streamable HTTP。服务仍是 [原六工具 MCP 服务](mcp-evidence.md)，没有为 Agent 增加文件修改或模型调用入口。两边都是显式 loopback；没有公网认证、多租户或在线网站后端。

## 在服务器运行

从仓库根目录使用独立锁定环境。安装和实验均在授权服务器执行，不向原维护 worker 增加依赖：

```sh
uv sync --project extras/mcp-agent --frozen --no-install-project --no-default-groups
PY=extras/mcp-agent/.venv/bin/python
$PY -m benchmarks.mcp_evidence_server \
  --root evidence/mcp-agent/corpus \
  --manifest evidence/mcp-agent/corpus/catalog.json --port 18859
```

另一个服务器终端可运行显式脚本模型控制；这里只伪造模型回复，MCP SDK、TCP、服务、报告和回执全部真实：

```sh
extras/mcp-agent/.venv/bin/python -m benchmarks.mcp_agent_controls \
  --code evidence/mcp-agent --state /tmp/new-mcp-agent-controls \
  --mcp-url http://127.0.0.1:18859/mcp --owner "$PROTOCOL_SHA256"
```

`--state` 必须是新的服务器本地目录，`--owner` 为操作者冻结协议的 SHA256。四场控制分别是正常提交、布尔值冒充整数、未读取就提交，以及只有自由文字答案。预声明共九个脚本模型 POST，不是九个神经请求或模型成绩。

真实模型审计还需要单独的兼容 OpenAI chat API 的本机模型服务；通过环境变量 `AGENT_LAB_EVIDENCE_KEY` 传入该服务凭据。该凭据只用于模型 HTTP 请求，MCP 请求不携带它。不要把密钥、服务器连接文档或有活跃能力的原始运行目录提交到仓库。

```sh
extras/mcp-agent/.venv/bin/python -m benchmarks.llamaindex_mcp_audit \
  --mcp-url http://127.0.0.1:18859/mcp \
  --cases evidence/mcp-agent/normal/cases.json --case supported_contribution \
  --state-dir /tmp/new-mcp-agent-case \
  --base-url http://127.0.0.1:18858/v1 --model YOUR_LOCAL_MODEL \
  --owner "$PROTOCOL_SHA256"
```

模型只能调用 `list_reports`、`read_report` 和最终 `submit_assessment`。目录描述不算证据；精确字段读取返回的数据不包含句柄/回执。最后一项工具直接返回结构化核对结果，不再隐式追加格式化模型请求。没有一次有效最终提交、只有文字答案或远端拒绝都不会被接纳。

## 两条独立额度与两种判断

每题模型 POST 使用原持久账本：最多八次、单正文 65536 字节、累计 262144 字节，SDK 重试为零。只计 HTTP 尝试和 JSON 正文字节，不是 token、费用或模型全部资源；未知结果保留预留。MCP 业务操作另有每次审计16次、八个读取回执及600秒TTL，发现、状态与关闭不计入模型 POST。

远端 `evidence_verified` 只确认 JSON 值/类型、来源 SHA 与本次提交回执的覆盖。接口显式保留 `verdict_truth_verified=false` 和 `free_prose_semantics_verified=false`。外部固定题目评分另外判断已知结论及必需字段覆盖；不会把模型解释中的所有语义都自动判为正确。

模型工作流最多600秒、七次 Agent iteration，没有隐式重试或修复。工作流退出后，清理另有最多10秒，使用新传输关闭同一个审计上下文：状态查询只占其中最多2秒，即使查询失败也尝试关闭一次。不会新建/续期审计、重放业务工具或退还未知模型请求。服务不可达、再次取消或能力已过期仍可能清理失败，结果会记录错误。它不恢复整个 Agent 工作流，也不承诺跨进程复用进程内回执、工具恰好一次或恶意操作者防护。模型账本的持久性不等于这些能力。

## 结果与来源

以 [实际结果及完整轨迹](../evidence/mcp-agent/README.md) 为准。新目录固定在 `cb67290a9ced302834f8458adf94b78bc64246bd`，含九份已知报告；旧八份报告的字节不改。新两题针对已知贡献表述，gold 不在 MCP 工具目录中。它们不是 held-out 通用准确率、神经仓库修复或生产用户评测，不能与此前三题相加。

此前130项完整回归是共享核心、测试、评分和服务源码不变的验证快照；新适配器控制不增加这个计数。历史两阶段审计的600秒超时、新版三题结构2/3及文字歧义均独立保留，不用新实验覆盖。


## 2026-11-22 完成的服务器验证

四场脚本模型加真实 MCP 控制全部通过，共九次脚本模型 POST，零神经调用。33份共享源码保持不变，沿用已验证130项快照，没有新增核心测试或重复跑完整套件。实际9B CPU首题600秒超时：六次模型预留、五份完整HTTP200回复、一次未知仍扣额，47,710正文字节；读到四份报告回执但没有最终提交，第二题未运行。模型又读取两份非必需历史报告，不据此推断因果性能。600秒后远端能力过期，状态查询明确失败，不能声称显式关闭成功；最终两服务均退出、端口关闭、无任务遗留进程。

首轮 SDK 导入180秒受限、独立120秒堆栈诊断、顺序复制900秒受限及第二轮异常类型控制失败均保留。8,999个相同文件转移到本地ext4并逐哈希核对后导入通过；缓存影响未单独隔离。只将相同接纳判定移出 MCP 异步上下文，未扩大检查接受范围、改 gold 或延长模型预算。完整原始及公开哈希、双通道字节和局限见上方结果入口。


## 状态查询失败仍应关闭：后续实际修复

此前把状态查询和关闭放在同一个 try 块内，查询失败就不会发出 close_audit。新版将清理移到工作流传输上下文退出后，用新连接保留同一个句柄；可选查询最多2秒，整个清理最多10秒，关闭只尝试一次。取消继续向调用者传播，未知模型预留继续扣额，审计TTL、接纳判定和模型额度不变。这个新连接用于清理，不恢复工作流、续期上下文或重放工具。

在授权CPU服务器上，真实MCP2.3.0/LlamaIndex及TCP、报告、回执不伪造，只按脚本提供模型回复并在测试边界注入故障。九场基线6过/3失败，候选9过；基线的延迟查询本已最终关闭，过期上下文本已失效，这不表示三处资源泄漏。正常/伪造事实/无读取/纯文字四场及模型超时、外部取消原本就通过，现继续通过。

首轮 status_error 返回缺少 MCP2 resultType，实际覆盖畸形响应；原源码和结果保留，没有改名重算。之后单独补一场合法 resultType=complete/isError=true 的工具错误，基线0过/1失败、新版1过，适配器字节与前九场完全相同，九场未重跑。候选共10个不同控制场景（包括此前四场）；每侧21次脚本模型POST，两个中断请求保留未知扣额。候选每场只创建一个审计并发一次关闭；过期场景正确记录失败，不声称有确认。全程零神经/GPU调用、不重跑真实9B实验、不增加130项核心快照。

```sh
# 在授权服务器，从源码根目录运行；state为新的本地目录。
extras/mcp-agent/.venv/bin/python -m benchmarks.mcp_cleanup_controls \
  --code evidence/mcp-agent --state /tmp/new-mcp-cleanup-controls \
  --owner "$PROTOCOL_SHA256"
# 上一命令是原九场；合法业务错误另用新目录单独运行。
extras/mcp-agent/.venv/bin/python -m benchmarks.mcp_cleanup_controls \
  --code evidence/mcp-agent --state /tmp/new-mcp-tool-error \
  --owner "$PROTOCOL_SHA256" --case status_tool_error
```

控制自行启动并关闭仅loopback的测试MCP服务，不需要另启MCP服务或真实模型。环境仍用已锁定的 extras/mcp-agent，不安装新依赖。[全部结果、失败、协议和原始/公开哈希](../evidence/mcp-cleanup/README.md)以及[精确适配器补丁](../evidence/mcp-cleanup/adapter.patch)可核对。SDK可能把关闭工具异常包装成ExceptionGroup，原工具错误保留在wire中；不可达服务、再次取消和过期能力仍可能没有关闭确认。历史600秒真实模型失败保持原样。


## 后续GPU消费实验

[独立记录](../evidence/mcp-agent-gpu/README.md)：已安装服务与真实9B GPU启动成功，但共享显卡保护中止首题；零已完成评分，缺完整wire/最终答案。旧CPU记录及后续十控制保持各自范围。后续[算法与应用路线](robust-tool-use.md)单列准备/实测状态。

## 中断通信证据持久化

后续[私有wire日志](mcp-wire-journal.md)已接入本适配器。服务器真实MCP/TCP强杀控制恢复了15条事件与2份完整脚本模型回复，第三次未知继续扣额；日志故障场景仍完成已知上下文关闭。另8项日志控制与原10项清理场景通过。这些验证不加载模型、不补写旧GPU轨迹，也不恢复整个Agent工作流；[元数据与各自分母](../evidence/mcp-wire-journal/README.md)单列保存。


## 真实9B运行与持久通信记录（2026-11-23）

使用当前已提交的适配器、原MCP服务wheel、原问题顺序和固定九份报告，在授权GPU7的A6000上运行Qwen3.5-9B Q4_K_M。CUDA实际完整卸载33/33层，8192上下文；每题仍最多8次模型POST、7轮工作流，模型SDK重试为0。原报告目录和gold保持历史固定快照，题目明确不查询当前GitHub状态；它是已知问题的应用接入验证，不是held-out模型准确率。

首题实际预留7次POST、58,111正文字节，取得7份完整HTTP200模型回复。模型执行了目录查询和5次报告读取，没有请求`submit_assessment`；第7份回复又要求读取一份报告，固定SDK在`parse_agent_output`处报`WorkflowRuntimeError`：达到7轮上限。结果未通过事实覆盖和最终提交验收；第二题按预声明的工作流失败终止规则未运行，不给它补算分数。

40条通信事件、7份完整模型回复通过独立进程的只读reader恢复，帧链和writer关闭记录一致，尾部缺失字节为0。私有wire文件139,577字节、权限0600；模型账本7次预留均有完整回复匹配，本次没有未知请求。MCP返回`closed=true`确认同一审计上下文关闭；原生模型与MCP服务退出，两个端口关闭，自有进程为0，GPU上下文已释放。原始正文和审计能力留在服务器，公开[字段与哈希元数据](../evidence/mcp-gpu-wire/report.json)、[逐题结果](../evidence/mcp-gpu-wire/cases-summary.json)、[7次回复的工具选择和token统计](../evidence/mcp-gpu-wire/model-response-metadata.json)及[完整通信元数据](../evidence/mcp-gpu-wire/inflated_merged_claim/wire-metadata.json)。这验证了真实模型运行中的证据保留与关闭，不是整个Agent工作流恢复。

启动前V1曾在共享存储完整文件核对的180秒限额处退出，当时模型未启动、神经请求为0。随后单独将22项运行文件与模型共6,701,572,936字节流式复制到节点本地ext4并核对SHA，耗时189.886秒；V2从本地副本复核相同字节，完成本次运行。模型、输入、评分与每题额度未因此改变。两场启动记录、实际执行器、协议、源码哈希与运行库元数据均随本目录保留；这不是单变量硬件速度比较，旧CPU超时和旧GPU中断仍按原结果保留。

失败轨迹显示，在读取两份必需报告后，模型又读取了3份本题不需要的报告。轮次边界也已有上游[PR #23259](https://github.com/run-llama/llama_index/pull/23259)，未重复提交；第7份模型回复并非最终提交，因此不能推断边界修复单独就会让本题通过。后续应独立评估检索范围与预算感知策略，保留本场原始失败。上述结果不增加130项核心或脚本控制的计数。[公开文件清单与原始/规范化SHA](../evidence/mcp-gpu-wire/artifacts.json)。


## 目录检索策略后续

[新增可选词法目录策略](report-retrieval.md)，默认完整目录模式保持。24份实际报告、19项预声明诊断及真实MCP脚本控制已运行；BM25没有优于简单词法基线，未重跑或修改上面的真实9B失败记录。筛选策略与轮次规划提示一起改变，仍需相同模型和预算下的实际任务验证。
