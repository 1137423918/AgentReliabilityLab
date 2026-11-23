# 固定250题生成与离线评分对照

在[配对训练](fixed-reason-ablation.md)完成后，使用已经锁定的250条输入比较base、新Reference32和新Masked32。**三组各250题已生成并统一离线评分，全部6个执行段正常退出。** 推理协议和评分代码均在相应执行前公开核验，输入、来源和旧账本保持原哈希。

每组完整250题，分别为live_simple、live_multiple、parallel、parallel_multiple和irrelevance各50题。不替换任务、提示、函数声明或参考答案；不复用旧Full32的生成分数，也不重新生成旧199题。新参考与屏蔽适配器均固定为各自已核验的最终step32。

Qwen2.5-3B-Instruct固定revision，原生SDPA、基座FP16/适配器FP32、关闭TF32，batch1、greedy、seed42、最多1,536新token。输入保持原生chat template的已准入token，最长2,969；没有截断或schema修复。三组及其所有执行段要求相同物理GPU和后端，每次重新检查资源与参数身份。

## 执行与记账

新实验最多759次生成尝试，每组253次、每题2次。其中750次对应固定预测，最多9次为预先声明的未知资源尝试余量。未知继续扣额；只有原监督器已停止并清理、且有允许的资源中断证据时，才可能在原限额内授权重试。格式错误或任务失败的已提交输出同样不可替换，没有评分后的质量重试。

每段最多生成125条新结果，复用所有已提交结果。接近1,200秒段预算时，在下一次扣额前合作结束；每次生成有90秒软时间上限，已返回的部分输出照样提交。分段不缩小每组250题的范围。每次调用前持久化预留，返回后原子提交私有原文、生成token和来源哈希，后续恢复不重新调用已完成任务。

原base参数使用规范化名称建立指纹，PEFT包装前后保持可比；适配器文件与参数指纹必须匹配训练结果。模型生成进程只接收固定token输入和模型，不导入评分器，也不读取新参考答案。原输出留私有，公共材料只导出计数、哈希、耗时与后续评分标记。

## 评价口径

在全部750份输出保存后，才执行[带限制的BFCL派生Python匹配](bfcl-transfer-scoring.md)。主要比较200条需工具题的Masked32与Reference32，同时分别报告50条irrelevance、解码失败、显式空列表和AST拦截。总体250题是等额分层诊断；恒不调用策略按规则可得20%，这只是规则基线，不是模型成绩。

不将这一子集称作完整BFCL分数、实际工具执行成功率、语义/预训练隔离或一般泛化证明。评分器自身异常不伪造成模型答错，也不据此删题。新预算不改动旧599次生成尝试及两次未知，也不改变已完成的2,666次训练前向账本。

[生成入口](../benchmarks/bfcl_generation.py) · [输入准备](../benchmarks/prepare_bfcl_generation.py) · [8项控制](../extras/lora-training/test_bfcl_generation.py) · [冻结协议与CPU证据](../evidence/bfcl-transfer-generation/README.md)。

离线汇总入口另有6项服务器控制通过：完整750份输出门槛、评分器异常保留、irrelevance解码失败计分可见、安全拦截单列，以及逐题配对和精确双侧McNemar统计。主比较预先固定为200条工具题的Reference32→Masked32；未定义评分存在时不报告完整准确率或检验值。控制不代表模型成绩。见[评分入口](../benchmarks/score_bfcl_generation.py)、[控制测试](../extras/lora-training/test_bfcl_generation_scoring.py)和[服务器证据](../evidence/bfcl-transfer-generation/scoring-controls/export-manifest.json)。

## 实际生成与评分结果

| 模型 | 工具题200 | irrelevance50 | 等额分层250，仅诊断 |
| --- | ---: | ---: | ---: |
| base | 147/200（73.5%） | 35/50（70.0%） | 182/250（72.8%） |
| reference32 | 150/200（75.0%） | 34/50（68.0%） | 184/250（73.6%） |
| masked32 | 153/200（76.5%） | 34/50（68.0%） | 187/250（74.8%） |

Reference32→Masked32主比较：只Masked正确6题，只Reference正确3题；差值+1.5个百分点，配对精确双侧McNemar p=0.5078125。这是本固定子集的配对描述，不外推总体或跨种子稳定性。当前小预算、单种子结果不足以证明稳定方法收益。

所有750份结果先保存，全部监督器终态清理后才启动评分。新账本共750次扣额、0次终态未知；原599次账本和两次历史未知保持不变。三组均固定最终step32／原始base，没有生成后选择检查点、修复输出或重试质量失败。

| 模型 | AST拦截 | 解码失败，拦截外 | 显式空列表 | irrelevance解码失败却获分 | 未定义评分 |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 0 | 41 | 0 | 35 | 0 |
| reference32 | 0 | 38 | 0 | 34 | 0 |
| masked32 | 0 | 36 | 0 | 34 | 0 |

保留原irrelevance解码失败获分规则，因此该组成绩必须与显式空列表和解码失败同时阅读。本次三组irrelevance获分项全部来自解码失败，显式空列表均为0；这组分数不能证明模型正确输出了结构化的无需调用结果。AST拦截无分、无限制官方结果未知；评分器异常保留未定义，不删题或伪造成错误。各类别与逐题标记见[完整评分报告](../evidence/bfcl-transfer-generation/scoring/results/report.json)和[逐题标记](../evidence/bfcl-transfer-generation/scoring/results/case-flags.jsonl)。恒不调用规则可得50/250，只是20%的派生规则基线，不是神经模型表现。

| 模型 | 生成token位置总数 | 中位数／p95长度 | EOS终止 | 达到1536上限 |
| --- | ---: | ---: | ---: | ---: |
| base | 9200 | 28.0／94 | 250/250 | 0 |
| reference32 | 8901 | 28.0／88 | 250/250 | 0 |
| masked32 | 8820 | 27.0／87 | 250/250 | 0 |

三组完整提示token位置总数一致，为172731。长度、EOS和本次顺序运行耗时用于解释输出成本，不构成FLOPs、速度提升或生产任务完成率。

协议中的CPU scope及`new_generation_calls_this_CPU_profile:0`是继承的预检元数据；实际生成由`phase=bfcl_generation`、`new_generation_allocation=759`和独立新账本约束，原协议不追改。公开预注册提交0ac45b2与评分代码提交8c9d7ac的原始字节核验回执均保留。

原输出、token向量、输入和参考答案保持私有；关闭后的完整实验已一致性归档到服务器稳定私有目录，见[归档回执](../evidence/bfcl-transfer-generation/gpu/results/private-archive-receipt.json)。该备份不能用于重置预算或质量重跑。
