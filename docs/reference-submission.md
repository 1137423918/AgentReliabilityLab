# 从实际 MCP 读取结果绑定事实引用

Agent 核对项目或实验报告时，既要选对证据、判断结论，也要把 JSON 数值、对象和来源复制到最终提交。真实9B运行中，三次失败已读到所需报告并调用提交工具，却分别出现多余引用、事实值不一致和输出截断。新增可选 `--submission-mode references`：模型提交结论、解释和 `report_id` / `pointer`，适配器从本次审计成功读取的 MCP 返回中绑定值及来源哈希，再交给原远端核验器。

[完整实际结果与失败记录](../evidence/reference-submission/README.md)区分已完成任务、未启动任务、脚本控制和模型请求。实际新模式完成两题、通过一题：VoltAgent的七项必需事实与结论通过；训练进度题生成了不存在的字段引用，被严格拒绝。两题都是操作者了解原报告后编写的开发任务；不是未知用户评测或通用准确率。此前真实9B失败保持原样。

## 接口行为

`agent_lab/evidence_submission.py` 只接收模型显式选出的引用与成功的读取返回，不读文件、不访问 gold、不推断结论，也不补齐缺失引用。引用须等于本次读取的 JSON pointer，或位于该读取对象的后代；严格检查转义、路径边界、重复字段和来源版本。值深拷贝自观察结果，引用列表仅包含模型实际使用的报告。模型不能覆盖值、哈希或引用列表。缺少证据、只给自由文本、额外提交值等仍会失败。

模型仍选择 `claim_supported`、解释及1–8个字段引用。原 `AuditAssessment`、MCP回执校验、来源哈希要求和固定题目评分没有修改。已读取的父对象可以覆盖其子字段，这是原评分规则已有的能力。结构化证据核验不证明自由文本解释正确，也不自动证明结论为真；固定任务评分另核对预声明结论和全部必需字段。

默认 `values` 模式保持：原工具 schema、提示和四场控制的九份模型请求正文均与此前版本逐字相同。新模式是显式可选的消费端行为，不是服务器接口、默认模式或原评分的改变。

## 在服务器使用

沿用 `extras/mcp-agent/uv.lock` 的服务器环境。MCP读取已有24报告快照；模型服务另行启动，绑定loopback并通过 `AGENT_LAB_EVIDENCE_KEY` 提供本次私有凭据。

```sh
PY=extras/mcp-agent/.venv/bin/python
$PY -m benchmarks.mcp_evidence_server \
  --root evidence/report-retrieval/corpus \
  --manifest evidence/report-retrieval/corpus/catalog.json --port 18871
```

另一终端运行已冻结的报告核对题，使用新的服务器状态目录：

```sh
extras/mcp-agent/.venv/bin/python -m benchmarks.llamaindex_mcp_audit \
  --mcp-url http://127.0.0.1:18871/mcp \
  --cases benchmarks/reference_audit_cases.json \
  --case separate_voltagent_validation_rounds \
  --state-dir /tmp/new-reference-audit \
  --base-url http://127.0.0.1:18870/v1 --model YOUR_LOCAL_MODEL \
  --catalog-policy bm25 --submission-mode references \
  --owner "$PROTOCOL_SHA256"
```

这只是运行入口，不包含模型部署和资源准入操作。真实实验使用固定9B Q4_K_M权重与原生后端、8192上下文、最多1024输出token；每题8次POST、600秒、7轮，SDK重试为0。模型仍通过真实MCP选择目录与读取字段，最终提交后直接结束。BM25同时带有轮次规划提示，两者的作用未单独分离。

## 验证范围

服务器完成8项模块控制与5场真实MCP/FunctionAgent/TCP脚本场景；模型回复由脚本给出，不算神经成功率。额外读取的报告不会自动进入引用，注入值、未读取提交及纯文字答案仍被拒绝。旧/新默认模式各4场脚本控制，九份对应模型请求正文完全相同。

真实模型的逐题成绩、请求字节、来源和完整回复哈希见[结果表](../evidence/reference-submission/README.md)。已完成模型结果的评分由导出器从保存结果只读重算，独立wire reader核对帧链和账本；未重新调用模型。新旧模式使用相同题目/gold、模型和每题预算，但改变了提交schema及对应提示，资源准入也有明确修订；单次已知任务回归不支持因果性能或泛化结论。任务只读项目报告，不代表模型自主修复仓库。

模型HTTP预留跨中断保留；旧12次请求继续计入同组32次上限。两次零请求的启动前失败没有变成模型失败分母。新运行结束后，MCP关闭、端口、进程与GPU释放均分别留证。个人主页保持冻结。
