# 训练输入、开发集与监督 token 预算

同 ID 配对仍可能留下开发样本关联、序列过长和监督量差异。本次在服务器实际处理上一阶段的 3,905 对 Full/Mixed 输入与 79 条验证数据，使用与[3B基线](tool-use-baseline.md)相同的 Qwen2.5-3B-Instruct `aa8e72537993ba99e69dfaafa59ed015b17504d1` tokenizer，生成可复查的开发划分、私有训练文件和监督位置计划。**本页记录的数据准备阶段未执行模型前向、反向或优化器更新。** 后续实际 Full32 训练及未完成的核验见 [LoRA 试验](lora-pilot.md)，两阶段证据分别保留。

## 实际输出

| 数据 | 行数 | 处理 |
| --- | ---: | --- |
| Full 训练 | 3,700 | 与 Mixed 按相同 ID、相同顺序配对 |
| Mixed 训练 | 3,700 | 保留原记录内容及各自 schema |
| 干净开发集 | 197 | 来自 Mixed 的 `perturbation.type=none`，完整关联分组留出、精确 prompt+gold 去重 |
| 原扰动验证 | 79 | 顺序、内容和 Parquet 字节保持，SHA 与前阶段相同 |

实际读取并分词全部 7,889 条。194 个开发分组涉及 204 个配对 ID，整组从两种训练输入中移除；另有 1 对完整序列长达 4,370 tokens，超过预声明的 4,096 上限，成对排除，未截断。剩余 3,700 对记录各自真实写入并重读 Parquet，逐行内容和 schema 一致；标签 JSONL 也实际写入、重读并核对。

全量原配对输入的 Full/Mixed 最长 prompt 都是 4,130 tokens，分别有 12/9 条超过 2,048；原验证最长完整序列 1,657。本次只定义自己的完整序列准入，不据此推断原 GRPO 训练器如何处理长样本。

## 可复查的文本关联范围

先联合同一 metadata ID 及完整用户序列的 NFKC、casefold、空白规范化匹配，再将至少八词的序列按词三元组集合 Jaccard ≥ 4/5 连接，取传递闭包。实际检查 710,854 个候选序列对，得到 225 条近似边；未跳过高频候选。超过一千万候选会停止，不静默放松规则。

原验证与官方 199 条 clean 评测的用户文本也进入保护分组，分组不读取其 gold 或模型评分。本次候选训练 ID 命中这些保护分组为 0。按固定种子哈希从 1,941 个合格干净分组取前 194 个作为开发分组；训练、开发、原验证及官方评测在该连接规则下没有跨组交集。

这是**文本规则下的分组隔离**。它没有证明低于阈值的改写、工具家族或预训练来源独立；开发集也来自发布训练数据，未获得外部采集的独立分布。原文件保持不变，新划分另存，首次配对审计继续保留。

## 按实际标签位置规划训练量

使用同一固定 tokenizer 直接 `apply_chat_template(tokenize=True)`。完整训练对话追加 assistant 参考输出，并设置 `add_generation_prompt=False`；另构造生成提示以核对其 token 序列是完整对话的严格前缀。全部 7,889 条均通过边界检查。提示位置标为 `-100`，assistant 内容及模板结束位置保留真实 token ID，逐条核对因果移位后的有效标签数。[Transformers 聊天模板说明](https://huggingface.co/docs/transformers/v4.57.1/chat_templating#model-training)支持这种完整对话预处理；本项目额外验证自己的标签边界。

两种训练数据各有 3,700 行，但原始监督 token 总量为 335,822 / 336,489，完整序列总量也不同。因此另生成以下计划：

| 计划量 | Full | Mixed |
| --- | ---: | ---: |
| 优化器更新数（本阶段计划） | 32 | 32 |
| 每更新监督位置 | 2,048 | 2,048 |
| 总监督位置 | 65,536 | 65,536 |
| 完整序列前向段数（计划） | 774 | 772 |
| 输入 token 暴露量（计划） | 573,843 | 537,483 |
| 涉及 ID 数（计划） | 743 | 741 |

采用同一固定种子的 ID 顺序；监督片段跨更新边界时，保留完整上下文，只移动参与损失的标签区间。服务器独立从落盘文件重建所有片段，逐更新核对恰好 2,048 个有效移位标签，区间按 ID/cycle 连续，两组共同经过的前 741 个 ID 顺序一致。

将来训练必须把每段交叉熵求和后除以 2,048，并避免再按累积段数平均；`ignore_index=-100` 和 `sum/mean` 的含义见 [PyTorch 交叉熵文档](https://docs.pytorch.org/docs/stable/generated/torch.nn.CrossEntropyLoss.html)。**本阶段验证的是数据和标签计划。** 后续训练的实际消费和终态以 [LoRA 试验](lora-pilot.md) 为准。 监督 token 与更新数相同，仍有输入暴露、前向段数、数据覆盖和 FLOPs 差异，不能称计算量完全相同。这是 SFT 研究准备，与原 ToolRL-DR 的 GRPO 配方分别记录。

## 运行与证据

```bash
# 只在核对输入、tokenizer、依赖与资源后的服务器运行；输出目录必须新建。
python benchmarks/prepare_toolrl_study.py \
  --source /path/to/verified-paired-parquets \
  --model /path/to/verified-Qwen2.5-3B-tokenizer \
  --benchmark /path/to/pinned-api_eval/clean.jsonl \
  --output /path/to/new-private-study
```

复用独立 Python3.11 / Transformers4.57.6 / PyArrow22.0.0 环境，不新安装依赖。4CPU、nice19、32GiB AS、8GiB RSS、系统可用内存准入16GiB/下限12GiB、阶段1200秒；GPU不可见，离线分词，无模型权重加载。修订执行终止0，99.078秒、采样峰值约1.47GiB，无保护触发、自有进程0，来源/输入/tokenizer九个小文件与核心分发名称/版本对保持。

首轮终止2：读取官方 JSONL 时漏处理 `conversation` 的 JSON 字符串形式，发生 TypeError，尚未实例化 tokenizer。原脚本、协议、日志和失败终态完整保留；修订只补充字段解码与结构验证，使用新配置、新输出目录，分组、种子、预算均未改动。

公开逐行/选择记录使用 ID 哈希、原记录哈希和位置；完整提示、答案、token 向量、Parquet、权重及环境保留私有。操作脚本中的私有路径按清单规范化，原始/公开 SHA 分列。只更新项目仓库，个人主页继续冻结；旧 199 条基线和 130 项核心检查未重跑。

[准备源码](../benchmarks/prepare_toolrl_study.py) · [结果](../evidence/training-study/results/report.json) · [逐行 token 元数据](../evidence/training-study/results/row-metadata.jsonl) · [实际选择记录](../evidence/training-study/results/selected-rows.jsonl) · [标签消费核验](../evidence/training-study/results/consumption-check.json) · [Full计划](../evidence/training-study/results/train-schedule.json) · [Mixed计划](../evidence/training-study/results/mixed_train-schedule.json) · [执行前协议](../evidence/training-study/candidate-v2/protocol.json) · [终态](../evidence/training-study/candidate-v2/run-report.json) · [首次失败](../evidence/training-study/failed-v1/run-report.json) · [工件哈希](../evidence/training-study/artifacts.json)。
