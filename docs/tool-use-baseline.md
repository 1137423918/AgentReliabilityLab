# 3B 工具调用基线

使用发布的 Qwen2.5-3B-Instruct，在获准服务器的一张 P100 16GB 上运行 AgentRobustBench 官方 clean 单轮数据。使用同一份官方提示构造、输出解析器与评分器，没有本项目新增训练、参数反馈或重试。这是后续训练与执行前检查的对照，不是 ToolRL-DR 复现或完整鲁棒性成绩。

2026-11-23整场终止0，完成199/199条、199次真实生成。官方`correct`为**119/199（59.80%）**；混合评分规则下`score_sum`为120.666667，与官方correct计数分别报告。

| 官方子集 | 条数 | 官方correct | score_sum |
| --- | ---: | ---: | ---: |
| bfcl_v3 | 32 | 26 | 26.000000 |
| apibank | 74 | 43 | 43.000000 |
| tooleyes | 51 | 47 | 47.000000 |
| toolalpaca | 21 | 1 | 1.000000 |
| rotbench | 21 | 2 | 3.666667 |

必填参数缺失出现在3条；其中0条同时被官方规则判为correct。24条没有解析出的工具调用，不能一概当格式失败（部分题本来可以不调用工具）。未以EOS结束的生成3条，仍按原输出评分，没有补发。

实际输入193,895 tokens，生成21,284个token IDs（含可能的终止符）；本地账本199预留/199完成/0未知，不是API费用统计。分词器与模型初始化4.86秒，神经阶段1776.996秒；只是本次观察，不作跨硬件速度比较。所有自有子进程退出，GPU上下文已确认消失，上游三份固定输入/源码与驱动/包装器哈希未变。

## 固定条件

- 上游源码：`111fd3db40491e0d7d8a5ec432b7ac1c6c64b2f1`；模型：`Qwen/Qwen2.5-3B-Instruct`，revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`。11份模型/配置文件合计6,183,463,416字节，逐份核对官方LFS SHA256或Git blob SHA1；模型不重新分发。
- FP16、无量化、PyTorch2.6.0+cu124、Transformers4.57.6、SDPA，模型3,085,938,688参数全部位于一张P100。独立环境支持sm_60；完整53包URL/SHA锁见证据。它是本次研究的固定环境，不表示已验证其他平台或后端。
- 全部199条按官方文件顺序运行。CPU tokenizer预检最长输入4633 tokens；上下文32768，单题最多1024新token，不截输入、不删除过长题。提示、输入token IDs与样本哈希在推理前固定，实际调用逐题复核。
- 单题一次greedy生成：seed42、temperature0、do_sample=false、beams1、repetition_penalty1；没有gold反馈或自动修复。生成soft max_time120秒，独立调用watchdog180秒，神经阶段2400秒，整场3000秒。seed不承诺跨硬件逐bit相同。
- CPU4核/nice19；两次空卡样本间隔5秒，再持共享advisory UUID锁重新检查。GPU进程不设虚拟地址空间上限，单独监测RSS24GiB、显存14336MiB和16GiB系统可用内存下限；发现外来计算进程或遥测陈旧即停。锁不能替代调度器预留。

## 如何解读

官方匹配分数与必填参数检查分别报告。官方BFCL兼容规则允许省略部分参数，ToolEyes子集按工具名称匹配；本项目保持原规则，额外检查顶层required字段是否出现。该检查不验证类型、嵌套结构、值域，也没有执行真实工具；通过任一项都不能直接推导完整schema有效、应用任务完成或自然语言事实正确。

这是199条clean单轮工具调用预测，不是全部3721场景、22种扰动、实际仓库修复或真实工具执行。底座是已有指令模型，尚未进行项目训练；不拿它与不同精度/后端的论文成绩作因果比较。先前32个gold派生评分器诊断仍是CPU控制，与这里的真实神经推理分开。

## 准备失败也保留

首次服务器直接访问Hugging Face下载失败（网络不可达），冻结解析结果与失败终态保留。随后从官方PyTorch/PyPI安装同一次解析的完整哈希锁；CPU导入确认sm_60兼容后，才准入GPU模型。

模型传输先由本机只下载不执行，随后确认服务器能访问官方源生成的CDN地址，停止本机慢传输并复用811,597,824字节的两个分片前缀，由服务器补齐其余字节。11文件完整哈希与共享缓存复制均重新核对成功。本机没有模型推理。临时签名地址仅在内存及认证SSH标准输入内传递，不写入命令行或工件；所属SSH ControlMaster已关闭。没有因为观察超时而重启神经任务。

## 复查

[驱动源码](../benchmarks/agentrobustbench_baseline.py)直接调用固定上游的`build_messages`、`run_single_pass`和`score_record`。准备只分词；运行要求新输出目录，并且逐题写入fsync的预留/完成事件。未知调用仍占用原预留，不重置或自动重试。完整提示、原始答案与token IDs私有保存；部分记录ID含完整问题，公开时以原ID的UTF-8 SHA256及顺序号替代；公开逐题元数据包含原始工件/输出哈希，可独立按原输入复查。

```bash
# 只在已核对模型版本、源码SHA、环境与资源准入的服务器运行。
python benchmarks/agentrobustbench_baseline.py prepare \
  --upstream /path/to/pinned-AgentRobustBench --model /path/to/verified-model \
  --output /path/to/new-admission.json
python benchmarks/agentrobustbench_baseline.py run \
  --upstream /path/to/pinned-AgentRobustBench --model /path/to/verified-model \
  --admission /path/to/new-admission.json --output /path/to/new-private-run
```

逐题CUDA内存峰值字段是该进程启动以来的累计高水位，不是每题重置的峰值。

CLI本身提供固定生成与持久记录；本次外部资源准入、超时和仅清理自有进程的控制器另见证据。直接调用CLI不能视为已有相同监督保护。Qwen研究许可证下仅作非商业研究评测，没有权重再分发或商业服务。

[汇总与限制](../evidence/agentrobustbench-baseline/results/summary.json) · [199条逐题元数据](../evidence/agentrobustbench-baseline/results/case-metrics.jsonl) · [执行前协议](../evidence/agentrobustbench-baseline/operator/protocol.json) · [终态与清理](../evidence/agentrobustbench-baseline/operator/run-report.json) · [依赖锁](../evidence/agentrobustbench-baseline/runtime/requirements.lock) · [工件双哈希](../evidence/agentrobustbench-baseline/artifacts.json)。
