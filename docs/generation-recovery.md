# 中断后的工具调用评测恢复

共享显卡上的评测可能在已经生成一部分结果后中断。直接重跑会浪费调用，也可能把失败样本换成另一个答案。本项目为固定的 Qwen2.5-3B / AgentRobustBench 评测接入了持久化进度：保存首个已提交的结果，恢复时跳过生成与评分；尚未确认完成的尝试继续占用预算。

**当前三组已全部完成**：[最新同后端对照](generation-complete.md)。599次预留/597条结果，两个历史未知继续扣额。

下文保留恢复V2的历史设计与部分结果语境：当时基线199条、Full83条、Mixed未启动，完整对照尚未完成。 [本次证据快照](../evidence/lora-generation/README.md)保留了两次资源保护中断。

## 实际发生了什么

两组适配器来自[已保存的 32 步 LoRA 试验](lora-pilot.md)，本阶段没有训练、挑选检查点或修改解码参数。三组计划使用同一张 RTX 3090、FP16 基座 / FP32 适配器、原生 SDPA、相同依赖、固定原始样本顺序和官方评分器。输入完整保留，最长 4,633 token；context 32,768，greedy / seed 42，每例最多生成 1,024 token，无参数反馈或答案修复。

| 截至恢复 V2 终态 | 已评分 / 计划 | 已预留尝试 | 未确认完成、仍扣额 |
| --- | ---: | ---: | ---: |
| 新同后端基线 | 199 / 199 | 199 | 0 |
| Full32 | 83 / 199 | 85 | 2 |
| Mixed32 | 0 / 199 | 0 | 0 |
| 累计 | 282 / 597 | 284 | 2 |

新基线官方 `correct` 为 **118/199（59.30%）**，score sum 为 119.666667；与[历史 P100 基线](tool-use-baseline.md)的 119/199 分开保留，不能将差别因果归于某一个设备或软件设置。官方评分包含名称匹配、缺省参数等兼容规则；不等于完整 JSON Schema 验证或真实工具执行。

首次 Full 评测在第 82 条预留后触发 foreign-client 保护，留下 81 条已评分和 1 次未知。之后冻结新的有界资源恢复协议，导入全部 281 次历史尝试 / 280 条结果。服务器 CPU 实际分派这 280 个缓存，模型和评分回调均为零；新 tokenizer admission 的 199 个输入与旧版逐例一致。

恢复模型运行实际跳过 81 条 Full 结果，新增完成第 82、83 条；第 84 条预留后再次触发保护。清理前的私有 PID/start 记录表明一个不同于自有 driver 的 CUDA 计算进程进入同一卡，没有终止该外部进程。首次中断未持久化触发身份，不能倒推它的根因。两个失败监督器均保留，当前没有活动模型任务。

## 恢复约束

[`GenerationProgress`](../benchmarks/generation_progress.py) 在模型调用前持久化预留，在评分后原子提交结果。定义绑定模型 revision、适配器文件、数据、每例消息 / token 输入指纹、推理设置和总 / 变体 / 单例预算。状态使用文件锁、checksum、`fsync` 和原子替换；每个变体另有进程工作锁，缺失或损坏状态直接拒绝继续。

[导入与缓存分派](../benchmarks/generation_resume.py)核对历史文件 SHA、wire 记录、原始结果和新输入 admission，不重新生成或评分。包括 0 分、没有解析调用或非 EOS 的已提交结果都保持原样；可以新增来源证明字段，不能替换原结果。

原无重试协议最多 597 次，现仍是不完整的失败记录。新增资源恢复协议在首次新增调用前另固定为 **总 603 / 每变体 201 / 每例 3 次尝试上限**。只有已终止且清理完毕的资源保护事件可以由操作者明确授权下一次有界尝试；模型超时、解析或质量问题不能授权。未知记录不删除、不退额，没有自动重试循环。本快照第 281 次未知已获资源授权并有后续已提交结果；第 284 次未知尚未授权。

预算是本地生成尝试数，不是 HTTP 计费或 token 费用保证。文件校验防止意外损坏，操作者是受信任的；没有实现对恶意所有者的防篡改、跨机器崩溃恢复或 exactly-once 计算。如果 wire 已完成而评分尚未提交，必须先核对现有 wire，不能直接再调用模型。训练检查点恢复也不由这个模块提供。

## 验证与运行入口

固定 Linux / Python 3.11 服务器上 **12 项 CPU 控制通过**：真实 SIGKILL 后保留扣额、进程锁释放、四进程争抢两个额度、状态丢失 / 损坏与身份变化拒绝、禁止质量重试、分级上限、结果不可替换，以及历史导入和实际缓存回调分派。它们不加载模型，不计为额外神经成绩；之后真实 GPU 恢复运行的 81 个缓存跳过和 2 个新结果单独记录。

```sh
# 在授权的 Linux CPU 环境运行；不需要模型权重。
python -m unittest discover -s extras/lora-training -p 'test_generation_*.py' -v
```

[`agentrobustbench_baseline.py`](../benchmarks/agentrobustbench_baseline.py) 增加可选 `--adapter`、`--progress-dir` 和 `--variant`。恢复需要已经验证、初始化一次的私有 `definition.json` 与进度文件；输出目录必须全新。它不会自行寻找或重建丢失状态，也不提供 GPU 资源隔离。

```sh
# 先核对模型、输入 admission、固定定义及资源监督协议；此命令本身不预留显卡。
python -m benchmarks.agentrobustbench_baseline run \
  --upstream /path/to/pinned-AgentRobustBench \
  --model /path/to/verified-Qwen2.5-3B \
  --adapter /path/to/fixed-full32 \
  --admission /path/to/new-admission.json \
  --progress-dir /path/to/existing-private-progress \
  --variant full32 --output /path/to/new-segment-output
```

原始消息构造、模型生成、解码和官方评分调用保持一致；原 driver 与恢复 driver 均封存在证据中。资源监督仍要求空卡新样本、UUID 建议锁、外部进程 / 遥测过期 / 显存与主存上限。建议锁不能阻止其他用户使用 GPU，已通过准入不保证整轮独占。

公开快照包含逐例 ordinal / ID 哈希、官方 correct / score、token 数、来源哈希、尝试状态、协议、CPU 日志和规范化控制器源码。完整提示、答案、输出正文、token 向量、权重、服务器路径和原进程身份不公开。元数据可核对汇总和来源一致性，不能独立重评分私有输出。个人主页继续冻结。
