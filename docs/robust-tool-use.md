# 工具调用鲁棒性：连接模型研究与实际应用

工作方向同时覆盖算法与模型研发、Agent应用开发。已经完成数据/评分器审计、真实基线、32步LoRA试验和部分生成对照；尚无已证实的训练准确率提升或应用上线指标。

## 真实需求与研究问题

已有项目证据服务可独立安装，供 Agent 读取报告、核对来源与事实。自然语言消费端仍有超时、重复读取和未提交问题。应用目标是辅助开发者核对项目/贡献表述，例如避免把重叠测试范围相加、把开放PR写成合并；当前尚未证明能自动可靠完成任意审计。

研究问题是：在工具说明变化、参数约束和运行错误下，能否用适合现有算力的数据与模型训练方法，提高等预算调用有效性，并在独立应用任务上保持效果？这是待验证假设。

## 已完成：公开数据与评分口径核验

选用[AgentRobustBench论文v3](https://arxiv.org/abs/2605.11928v3)与[官方实现](https://github.com/WillChow66/AgentRobustBench/tree/111fd3db40491e0d7d8a5ec432b7ac1c6c64b2f1)，固定源码到`111fd3db40491e0d7d8a5ec432b7ac1c6c64b2f1`。论文的ToolRL-DR提供工具调用扰动训练方向；不是本人的方法或复现成绩。

获准服务器CPU实际审计17个JSONL：2718条静态记录，2527条单轮可评、191条多轮按官方默认跳过，clean单轮199条。按官方构造还应有199×6=1194个运行时错误场景；本次没有执行这些场景，也没有跑完3721题模型评测。

额外在32个满足限定条件的clean BFCL样本上运行官方评分器：参考答案构造的调用32个通过；清空参数但保留名称的调用也32个通过，同时均存在声明必填参数缺失。它们是从gold构造的评分器诊断，**零模型调用**。官方BFCL兼容评分器源码明确允许省略参数；本项目保持原评分规则，补充区分基准匹配与工具可执行性，不把32个控制当准确率或指控官方模型结果无效。检查只涉及顶层必填字段，尚非完整JSON Schema或真实工具执行。

部分same_name记录ID与clean不能直接一一对应；ID重叠不等于语义家族已核验。首轮没有解析训练Parquet；后续已实际审计、发现Mixed复用验证样本并生成新配对研究输入，见[训练数据记录](training-data.md)。仍不据此宣称完整语义隔离。评测数据没有用于训练，也没有按记录随机切出新训练集。

## 已完成：3B真实clean基线

固定发布的Qwen2.5-3B-Instruct，在P100/FP16上完成199/199条、199次真实生成，官方correct 119/199（59.80%）。未做本项目训练、反馈或重试；3条有必填参数缺失，其中0条仍满足官方规则。分项、哈希、用量和终态见[独立基线记录](tool-use-baseline.md)。这不替代22种扰动评测或应用验收。

## 当前算法实验与后续验证

- 已完成[训练Parquet审计与同ID配对输入](training-data.md)，排除Mixed中的79个验证ID及16个无Full对应ID；又[按文本关联留出197条clean开发、准备3700对训练输入和固定监督token计划](training-study.md)。数据来源独立性及完整语义家族隔离仍未证明，不针对官方测试逐题调参。
- [Full/Mixed各实际执行32步LoRA更新](lora-pilot.md)，各65,536个有效监督标签。Full原最终核验中断、保存检查点独立回放通过；Mixed完整核验通过。两组参考答案条件下验证NLL为0.297599/0.297934，不是自由生成准确率。
- [同后端生成与恢复](generation-recovery.md)：新基线官方correct118/199；Full已完成83/199条，Mixed尚未生成。共享显卡保护中断，完整三组对照未完成；历史P100119/199保持独立，不把现成ToolRL-DR checkpoint分数写成本人训练成果。
- [已保存调用的schema诊断](tool-schema-diagnostics.md)在原始/上游投影两视图下分别核对；基线投影有效158/199，其中41例仍不满足官方匹配。完整JSON Schema解释是辅助诊断，尚非工具执行；原顶层必填控制和官方分数均保留。
- 配对消融：原模型、仅执行前参数检查、仅数据训练、训练加检查。检查器只反馈错误、不填gold，不在测试轨迹反向优化。完整GRPO是否可行需实测显存、吞吐和训练栈，尚无48GB单卡可复现论文训练的承诺。
- 同时报告原官方分数、完整schema有效性、受控执行结果、clean/扰动分项、失败类型与实际用量；按任务家族聚类计算区间，避免把同题变体视为独立样本。没有真实模型结果前不填写提升数字。

## 应用开发线

继续完善“项目证据核对助手”：使用[已安装验证的MCP服务](mcp-evidence.md)和固定真实报告，读取后提交带来源的结构化事实；在自然语言模型、参数检查、后端事实验证与最终解释之间明确验收。需要把相同模型/预算下的策略迁移到独立任务，再判断有无应用收益。启动包已可供开发者使用，公网多用户自然语言产品尚未交付。

早期9B GPU消费实验加载后因同卡其他计算进程按协议中止，零已完成评分，见[原记录](../evidence/mcp-agent-gpu/README.md)。后续[带持久通信记录的9B运行](mcp-agent.md)首题保存7份完整回复、40条事件，但未完成有效提交，第二题未启动；业务失败与通信保存验证分别报告。3B训练与部分对照已实际执行，见上文。后续启动须重新检查资源，旧快照不构成预留。

## 复查入口

[审计源码](../benchmarks/audit_agentrobustbench.py) · [数据/诊断结果](../evidence/agentrobustbench-audit/results/report.json) · [2718条记录哈希](../evidence/agentrobustbench-audit/results/record-manifest.jsonl) · [32个控制](../evidence/agentrobustbench-audit/results/scorer-controls.json) · [执行资源与终态](../evidence/agentrobustbench-audit/operator/run-report.json) · [执行前协议](../evidence/agentrobustbench-audit/operator/protocol.json) · [来源工件哈希](../evidence/agentrobustbench-audit/artifacts.json)。

复查命令（计算只在获准服务器）：

```bash
git clone https://github.com/WillChow66/AgentRobustBench.git /path/to/AgentRobustBench
git -C /path/to/AgentRobustBench checkout 111fd3db40491e0d7d8a5ec432b7ac1c6c64b2f1
python benchmarks/audit_agentrobustbench.py --source /path/to/AgentRobustBench --output /path/to/new-audit
```

使用Python3.11标准库；不安装模型/SDK，不调用网络API。调用方应核对固定源码和协议哈希，并给出新的输出目录。脚本审计数据与评分器，不能替代官方推理程序。
