# 文本分组、干净开发集与监督 token 计划

全部7,889条在获准服务器CPU实际分词。新输入为Full/Mixed各3,700条配对训练、197条干净开发、原79条扰动验证。194开发分组涉及204个配对ID，另1对超4,096长度成对排除，无截断。原验证Parquet字节保持。文本规范化/词三元组Jaccard规则下，训练与开发/验证/官方clean保护分组无交集；候选ID命中原验证/官方保护分组为0，不能解读为语义或预训练来源完全隔离。

32更新×2,048监督标签的计划分别覆盖65,536标签；实际落盘向量逐段重建、因果移位计数及ID/cycle区间连续性通过。Full/Mixed输入暴露573,843/537,483、前向段774/772，计算和数据覆盖仍不同。没有运行模型、损失、反向或优化器，不构成训练或效果提升。

[方法、命令和局限](../../docs/training-study.md) · [准备结果](results/report.json) · [逐行元数据](results/row-metadata.jsonl) · [实际选择记录](results/selected-rows.jsonl) · [消费检查](results/consumption-check.json) · [Full计划](results/train-schedule.json) · [Mixed计划](results/mixed_train-schedule.json) · [工件清单](artifacts.json)。

24份清单工件，另加本README与artifacts.json。首次失败v1和修订v2均保留原协议/报告；只规范化标明的operator脚本/日志运行路径，原/公开SHA分开。原ID、提示、答案、token向量、Parquet、权重与环境均不发布。首次解码错误v1 terminal2、owned0，修订v2 terminal0、无保护、99.078秒/峰值1,577,672,704字节、owned0；来源、输入、tokenizer九文件和core分发不变。私人tokenized/Parquet八工件SHA再次验证，公开7,676条选择记录指向原7,889条元数据；3700配对ID顺序一致。

训练器消费与真实训练仍待执行，既有130项核心回归和199条神经基线未重跑，不叠加为新测试成绩。无主页/Profile/Pages/Sites更新，无PR/issue/评论或人工证明操作。
