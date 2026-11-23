# 训练Parquet审计与配对研究输入

官方commit111fd3db的Full3905/Mixed4000/训练期验证79条实际在GPU7节点CPU解析：Mixed包含全部79验证ID，其中4条完整prompt+gold相同、63条完整输入历史相同。Full与验证在本次五种指纹中无相同项。这里的验证不是官方3721场景评测，负指纹匹配也不证明语义或预训练隔离。

另立协议生成Full/Mixed各3905条同ID研究输入；Mixed排除79验证ID和16无Full对应ID，验证79条内容/顺序保持。四种内容指纹交集为0，真实Parquet写入重读逐行/schema一致；7889条选择已独立匹配首次7984行审计的原始行号/ID/SHA。仅基于ID的配对，不是完整语义去重或等token训练，也未在下游训练器运行。

首次审计新建ext4隔离venv，官方PyPI固定Arrow22.0.0 wheel实际47,699,480字节/SHA35ad0f0378c9359b3f297299c3309778bb03b8612f987399a0333a560b43862d，下载核对后offline/no-deps安装并pipcheck。核心环境不变；配对复用该隔离环境。两配置4CPU/nice19/8GiBAS/4GiB采样RSS/180秒数据阶段/12GiB准入与8GiB内存下限，均terminal0、无保护、子进程回收。第一次数据阶段2.871秒，配对6.39秒，仅本次观察。

零GPU/神经推理/训练，不增加或重跑原130工程回归。原输入和9份首次来源/两个操作脚本的原SHA保留；两份协议在各自执行前冻结。公开27工件加本README/manifest，原始Parquet、生成Parquet、完整prompt/gold和环境不重新分发。可读operator私有路径规范化，结果/源附件和原协议原字节保留。

[结果](results/report.json) · [原行哈希](results/record-manifest.jsonl) · [重叠行号](results/overlap-details.jsonl) · [配对结果](pairs/results/report.json) · [选择记录](pairs/results/selection-manifest.jsonl) · [工件清单](artifacts.json) · [方法、复查命令与局限](../../docs/training-data.md)。
