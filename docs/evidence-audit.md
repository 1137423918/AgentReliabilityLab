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

`FunctionAgent`自动选工具、`streaming=False`、无return_direct；`output_cls`会在自由回答后增加一次真实模型格式化调用，也占次数/字节/总时间。八次请求上限、单次65536/累计262144字节、七次迭代、1024输出token、600秒；格式化不豁免。预声明评分要求结构化verdict、准确facts和读取谱系，不把看似正确的自然语言当作通过。完整wire记录body的base64/长度/SHA，不保存请求头；客户端尝试钩子早于额度准入，不能直接当实际HTTP成功次数。

当前124项回归通过，另两场假回复SDK控制均通过。真实CPU模型在第五次结构化调用超时，零已验证审计，后两题未运行。原样失败、未知额度、前两次预模型准备失败和所有源哈希公开；报告目录保持旧116快照。[完整材料](../evidence/evidence-audit/README.md)。

后续应先在独立预声明配置中测试更短自由回答/直接结构化Agent策略，以减少额外格式化开销，并保留相同问题和严格验收；不能回溯改变本次限额或分数。当前不声称一般准确率、模型自主修复、自由文字语义验证或性能收益。
