# 同后端生成与恢复：部分结果快照

2026-11-23，固定 Qwen2.5-3B-Instruct / AgentRobustBench clean 199。**本目录不是三组已完成对照：基线完成，Full32 中断两次，Mixed32 尚未启动。** 当前自有模型已退出。新结果只发布至项目仓库，个人主页保持冻结。

| 变体 | 已评分 / 计划 | 已预留 | 未知仍扣额 | 官方 correct |
| --- | ---: | ---: | ---: | --- |
| 新 RTX 3090 基线 | 199 / 199 | 199 | 0 | 118/199（59.30%） |
| 固定 Full32 | 83 / 199 | 85 | 2 | 50 个，仅为前 83 条部分结果 |
| 固定 Mixed32 | 0 / 199 | 0 | 0 | 尚无结果 |

Full 的前 83 条仅覆盖 BFCL 和部分 APIbank，不能与完整基线的比例比较，也没有用于调整模型、数据、阈值或生成参数。还没有全 199 条配对差异或扰动鲁棒性结论。[总快照](summary.json)、[基线汇总](base/summary.json)、[Full 部分汇总](full32/summary.json)保留原分母。

## 来源与实际终态

- 固定模型 revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`；AgentRobustBench commit `111fd3db40491e0d7d8a5ec432b7ac1c6c64b2f1`。使用原 `run_eval.py` 消息 / 解析及官方 `eval_results.py`，三份源 / 数据 SHA 和 LICENSE SHA 在协议中。
- 相同物理 RTX 3090 / sm86 / driver 575.57.08；Python 3.11.4、Torch 2.6.0+cu124、Transformers 4.57.6、PEFT 0.18.0。FP16 基座、FP32 固定 LoRA、SDPA；greedy / seed42 / new1024 / context32768 / batch1 / TF32false，无反馈、质量修复或新训练。Full/Mixed 检查点来自[已公开训练元数据](../lora-pilot/README.md)，私有权重没有发布。
- [原无重试协议](original-v1/protocol.json) SHA `9c8d63f9f47e4873401a5fff23ca5bba71485a2f4f1a028be459bbd14f84c49d`。基线监督器 / 子进程退出0，199 次预留及完成；1,109.269 秒模型阶段 / 1,150.243 秒整场。Full 原监督器退出2，foreign-client 保护，82 次预留、81 次完成、1 次未知；模型阶段306.708秒。原 597 次无重试 profile 保持未完成，不改判。
- [恢复 CPU 协议](recovery-v2/CPU-protocol.json) SHA `395fad903d807b6f4389690cad07e44c1ae99d55a3fbda9af1ea27078a91790c`。12 项 Linux CPU 控制通过；全199新 admission 与旧输入逐例一致。实际导入281历史尝试 / 280结果，分派280缓存，模型 / 评分回调均0；[准备报告](recovery-v2/setup-report.json)保留耗时、来源 SHA 和清理结果。
- [恢复生成协议](recovery-v2/generation-protocol.json) SHA `deb3d48f4cb5b781cc3333ea6c74e5c5a5a44406aeba5587762736c4d23b122c`。在新增调用前冻结总603 / 变体201 / 单例3尝试上限，所有历史未知继续占额。实际跳过81个 Full 缓存，新3次预留 / 2次已提交 / 1未知；70.640秒模型阶段 / 165.335秒整场，再次 foreign-client 保护，监督器退出2。累计284预留 / 282结果 / 2未知。
- 两次 Full 终态均证明自有进程树清理、GPU 上下文消失、源未改。V2 清理前的私有身份记录表明另一个不同于自有 driver 的 CUDA PID；[公开触发摘要](recovery-v2/guard-metadata.json)仅保留计数与原记录 SHA。原 V1 没有触发身份，不能推定其根因；未终止外部计算进程。

基线分项 correct：BFCL 26/32、APIbank 42/74、ToolEyes 47/51、ToolAlpaca 1/21、RoTBench 2/21。总 score sum 为119.666667，和 correct 个数是不同指标；required-key 窄筛查3例、非EOS3例。官方兼容评分不保证完整 schema 或真实执行。历史 P100 的119/199单列，不重评分、不拿它替代新基线。

## 文件与可核对范围

| 文件 | 含义 |
| --- | --- |
| [summary.json](summary.json) | 变体完成范围、累计尝试、两个未知及权限状态 |
| [definition.json](definition.json) | 固定模型 / 权重 / 输入指纹、推理设置、同物理卡约束和分级预算 |
| [attempt-metadata.json](attempt-metadata.json) | 284次持久尝试，282已完成 / 2未知；不包含原消息 |
| [base/case-metrics.jsonl](base/case-metrics.jsonl) | 199条逐例评分、token长度和来源指纹 |
| [full32/case-metrics.jsonl](full32/case-metrics.jsonl) | 83条首个已提交结果；前81条保留原行哈希 |
| [mixed32/summary.json](mixed32/summary.json) | 未开始的0条状态，case-metrics为空 |
| [原 base 控制器结果](original-v1/base-controller.json) / [原 Full 控制器结果](original-v1/full32-controller.json) | 原profile的成功基线与失败Full，均不覆盖 |
| [恢复 V2 控制器结果](recovery-v2/full32-controller.json) | 新段和共享累计账目、保护及清理终态 |
| [CPU-controls.log](recovery-v2/CPU-controls.log) | 12项通过，测试源码同目录；不是模型成绩 |
| [source-identities.json](source-identities.json) | 执行源码原SHA与公开规范化源码SHA |
| [export-manifest.json](export-manifest.json) | 服务器只读导出的32项payload及导出器源码SHA |
| [artifacts.json](artifacts.json) | 本目录35项payload（另含两份绑定测试源码与原导出manifest）的SHA/尺寸 |

`definition.json` owner digest 为 `7ae60226d469106e53513224aebfbf0e371b0e21388e9206caf44f24614ea7ef`。第281次尝试是Full第82例的旧未知，授权后第282次完成该例，但旧未知不删除。第284次是Full第84例的新未知，本快照尚未授权。恢复跳过已提交的0分或非EOS，不能挑选更优答案。仅资源保护且终态清理证据匹配才允许明确授权；没有自动重试循环。

逐例 `generation_metadata.sequence` 是各原始段的本地序号，`progress_metadata.attempt_sequence` 是累计尝试序号；不能用本地序号覆盖共享账目。旧结果带 `legacy_row_sha256`，新结果带 wire / 预留来源哈希。ID 使用SHA，prompt、gold、输出正文和token向量均保留私有；公开元数据能验证汇总、身份与来源一致性，无法独立重评分私有输出。

服务器原 tar 为179,642字节、SHA `8ddf726ae5c8c5e1df9873f7b154811ece1e4cc18fe06f3ef1dd6768571a1576`，已传回并核对32项payload。控制器源码仅将私有根目录改为占位符，原/公开SHA分别记录；协议、控制器终态、准备报告和CPU日志保留原字节。`definition.json` 为便于阅读重新缩进的导出JSON，其对象owner digest不变；协议中的原文件SHA对应排序、紧凑JSON加换行的私有序列化，公开文件SHA另列清单。两份额外测试与CPU协议的源码哈希匹配。这个快照不构成可回滚的实时进度备份授权，不得据此重建空账本。

[机制、验证和运行说明](../../docs/generation-recovery.md)。12项CPU控制与既有130项核心测试分别报告，本阶段未重跑核心测试，未更新历史PDF。
