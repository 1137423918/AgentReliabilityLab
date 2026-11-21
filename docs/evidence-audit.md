# 用实际实验报告约束 Agent 的项目表述

`agent_lab.evidence_audit.EvidenceCatalog` 是不依赖 LlamaIndex 的标准库组件。操作者提供受信目录，Agent只能调用列目录、读取明确的JSON pointer两种工具。每份报告固定SHA、最多256KiB；一次1–8字段、回复最多8192字节，超限拒绝而不截断。未知ID、路径逃逸/链接、无效pointer、非有限JSON及类型不一致均拒绝。最终facts必须能回溯到实际成功读取，父对象读取可支持其后代字段；citation必须匹配报告SHA。目录不提供对恶意owner的认证。

可选SDK依赖不加入原worker：在服务器独立venv安装 `extras/evidence-audit/requirements.lock`，使用uv的`pip sync --require-hashes`。活动账本在本机ext4新目录，不能用共享NFS。`AGENT_LAB_EVIDENCE_KEY`只从执行环境提供，不放入日志；不要把云API凭据交给本地端点。HTTP客户端仅允许loopback chat POST，使用既有异步持久预算；重试0、不退款。

示例在服务器运行（先启动经身份及资源校验的本地服务）：

```sh
python -m benchmarks.evidence_audit_case \
  --root evidence/evidence-audit/corpus \
  --cases evidence/evidence-audit/normal/cases.json --case gpu_claim \
  --state-dir /path/to/new-local-state \
  --base-url http://127.0.0.1:18854/v1 --model agentlab-evidence-qwen35-9b \
  --owner ORIGINAL_PROTOCOL_SHA256 --timeout 600
```

默认`two_step`的`FunctionAgent`自动选工具、`streaming=False`、无return_direct；`output_cls`会在自由回答后增加一次真实模型格式化调用，也占次数/字节/总时间。八次请求上限、单次65536/累计262144字节、七次迭代、1024输出token、600秒；格式化不豁免。预声明评分要求结构化verdict、准确facts和读取谱系，不把看似正确的自然语言当作通过。完整wire记录body的base64/长度/SHA，不保存请求头；客户端尝试钩子早于额度准入，不能直接当实际HTTP成功次数。

首轮124项回归通过，另两场假回复SDK控制均通过。首轮真实CPU模型在第五次结构化调用超时，零已验证审计，后两题未运行。原样失败、未知额度、前两次预模型准备失败和所有源哈希公开；报告目录保持旧116快照。[完整材料](../evidence/evidence-audit/README.md)。

后续应先在独立预声明配置中测试更短自由回答/直接结构化Agent策略，以减少额外格式化开销，并保留相同问题和严格验收；不能回溯改变本次限额或分数。当前不声称一般准确率、模型自主修复、自由文字语义验证或性能收益。

## 可选：由模型调用校验工具提交最终结论

在上述命令增加 `--strategy submit_tool`。保留原 `two_step` 默认，调用方必须明确选择新策略。FunctionAgent增加真实的`submit_assessment`工具，使用相同`AuditAssessment`严格schema；模型填写参数，经JSON值/来源SHA/实际读取谱系校验后，工具以return_direct结束，不启用output_cls，也不在后面增加模型格式化。拒绝的提交同样结束，纯自然语言或多次提交不能通过；没有自动修复/兜底填数。自由解释语义仍不自动验证。

同一模型、原问题与目录字节、同一评分函数AST和600秒/8请求/1024输出token/7迭代等额度。在服务器重新通过124项（未新增核心测试），另6场SDK假回复控制共26POST，含原默认2场及新策略4场；原默认10份请求体哈希与首轮相同。伪造事实、未读取事实和纯文字都被拒绝。

三道已知固定问题全部实跑：GPU题491.049秒/4请求，判断与事实正确，但缺整体结果和HTTP次数两项约定覆盖字段，完整契约未通过；测试范围题505.781秒/5请求、正确陈述题266.420秒/3请求均通过预声明结构化契约。共12次HTTP200/72683请求字节，不是一般准确率或仓库修复成绩。新提示及工具schema改变，不能归因于单一格式化步骤或宣称速度提升。旧首轮600秒超时保留不改判。[新策略完整证据](../evidence/evidence-direct/README.md)。

解释文字复核：测试范围题虽通过预声明结构化契约，解释仍称116+203=319的算术成立，却未清楚否定把319标为核心检查数，存在口径歧义。模型原文保留，不将结构化通过描述为所有文字都正确；自由解释语义仍不在自动评分范围。
