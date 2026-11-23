# 固定250题的未评分生成对照

在[配对训练](fixed-reason-ablation.md)完成后，使用已经锁定的250条输入比较base、新Reference32和新Masked32。当前8项CPU控制和全部输入/token身份核验通过，推理协议已冻结；**三组生成正在服务器执行，尚未评分新的模型输出**。

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
