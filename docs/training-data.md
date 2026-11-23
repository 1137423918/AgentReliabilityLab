# 训练前先排查验证样本复用

本文保留数据准备阶段的方法与当时状态；最新结果见[实际训练](lora-pilot.md)、[完整生成对照](generation-complete.md)与[监督目标审计](training-alignment.md)。

固定AgentRobustBench官方源码`111fd3db40491e0d7d8a5ec432b7ac1c6c64b2f1`，实际读取发布的三个训练Parquet。这里的`test.parquet`是训练期间的79条验证数据，**不是官方3721场景评测集**。本次数据审计未运行神经推理或训练，亦不据此重判论文的模型成绩。

## 实测发现

| 输入 | 行数 | 与79条验证数据的关系 |
| --- | ---: | --- |
| train.parquet / Full | 3905 | 原始ID、完整prompt、prompt+gold、输入历史及规范化完整user序列均未发现相同指纹 |
| mixed_train.parquet / Mixed | 4000 | 79个验证ID全部存在；其中4条完整prompt及gold逐字相同，63条输入历史逐字相同 |
| test.parquet / 训练验证 | 79 | 发布的公共验证输入，保持不修改 |

三个文件合计7984行的schema和冗余字段副本一致，original_id在各自文件内均唯一。Mixed与Full之间存在3905个相同ID是两种训练数据的比较关系，不能把它与训练/验证复用混为一谈。

官方转换源码先从扰动数据按记录切出验证，再独立导出Mixed；实际提供的Mixed因此不能直接作为与该验证集完全隔离的训练输入。4条完整prompt+gold相同是明确的文字复用；其他同ID或同用户文字仍有各自判断范围，不声称79条全部逐字相同。

与官方199条clean单轮数据的规范化user序列筛查均未发现相同项，**这不证明语义、工具家族或预训练来源不存在重叠**。没有把共享训练ID解读为官方最终评测集泄漏，也没有修改官方评价规则。

## 已完成的处理：另建配对研究输入

保留全部原始文件和第一次审计。另一个执行前冻结的配置，在服务器生成新的私有Parquet：Full与Mixed都取双方共有、且不属于79个验证ID的3905个ID，并按相同ID顺序排列。Mixed共排除95行：79个验证ID，另16个没有Full对应项的ID。验证79行保持原顺序和内容。

两组新训练输入与验证之间，完整prompt、prompt+gold、输入历史和规范化user序列的指纹交集均为零。三份新Parquet实际写入并重新读取，逐行内容与原schema相同；7889个选择记录又独立对照第一次审计的原始行号、ID和完整行SHA。新字节因重新编码而改变，文件SHA和规范化内容SHA分别提供。

这是基于发布元数据ID的配对策略，尚非独立的语义家族去重；并不自动保证训练token、更新步数、扰动比例或计算量相同。该配对阶段只保留了原扰动验证。后续已[按文本关联另建197条clean开发数据、实际分词并生成监督预算计划](training-study.md)，数据来源仍是同一个发布集；完整语义隔离、训练器消费及真实训练仍待执行。不能把本页当作已经完成训练、取得提升或可直接复现完整GRPO。

## 运行与复查

计算、安装与处理仅在获准服务器进行。只需Python3.11与单独环境中的[固定PyArrow22.0.0](https://pypi.org/project/pyarrow/22.0.0/)，不改主Agent/模型环境：

```bash
python -m venv /path/to/new-audit-env
/path/to/new-audit-env/bin/python -m pip install -r extras/training-audit/requirements.txt
/path/to/new-audit-env/bin/python benchmarks/audit_toolrl_training.py \
  --source /path/to/pinned-AgentRobustBench --output /path/to/new-audit
/path/to/new-audit-env/bin/python benchmarks/prepare_toolrl_pairs.py \
  --source /path/to/pinned-AgentRobustBench/training/data --output /path/to/new-paired-inputs
```

调用前核对上游commit和输入SHA，两条命令均拒绝已有输出目录。审计不自动修改数据；生成器按预声明策略选择，发现残余指纹重叠会停止，不静默调整规则。完整下游训练器对新Parquet的消费尚未执行。本次Linux/x86_64 wheel由官方PyPI元数据指定URL/大小/SHA，服务器下载47,699,480字节并核对后，offline/no-deps安装；不是新的最新版推荐或跨平台测试。

[原数据审计](../evidence/training-data-audit/results/report.json) · [7984条记录哈希](../evidence/training-data-audit/results/record-manifest.jsonl) · [重叠行号](../evidence/training-data-audit/results/overlap-details.jsonl) · [新输入结果](../evidence/training-data-audit/pairs/results/report.json) · [7889个选择记录](../evidence/training-data-audit/pairs/results/selection-manifest.jsonl) · [第一协议](../evidence/training-data-audit/operator/protocol.json) · [配对协议](../evidence/training-data-audit/pairs/operator/protocol.json) · [27份工件双哈希](../evidence/training-data-audit/artifacts.json)。

两个服务器CPU控制器均终止0，所有输入/脚本前后哈希不变、核心环境分发名称/版本对不变，未占GPU、未新开模型。新训练Parquet、完整prompt/gold与环境目录不公开；公开源码和行号/哈希可用于从固定官方输入重建。既有130项核心检查没有重跑，不与数据行数相加。
