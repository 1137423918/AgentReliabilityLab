# AgentRobustBench 数据与评分器 CPU 审计

固定官方commit111fd3db40491e0d7d8a5ec432b7ac1c6c64b2f1，在获准服务器运行一次独立标准库审计；54份执行输入哈希前后不变，控制器退出0，ext4状态，4CPU/nice19、8GiB地址空间、4GiB采样RSS上限、180秒墙钟上限；实际0.854秒，无保护触发，子进程已回收。没有GPU、神经推理、训练或旧核心回归重跑。

17份JSONL/2718记录，2527单轮、191多轮跳过、199clean；运行时1194场景只是按公开构造计算，本次未执行。32份gold派生的clean BFCL诊断中，参考参数与空参数均获官方评分通过，而空参数均缺少匹配工具声明的必填键。评分器源码明确采用省略参数兼容口径；官方规则保持，必填键诊断不等于完整schema或真实执行，也不是模型准确率。

没有创建训练划分；语义任务家族、训练Parquet、训练/验证/评测隔离仍待独立审计。不要用相同ID重叠断言无数据泄漏，也不要把2718记录或32控制相加到130工程检查。

[结果](results/report.json) · [逐记录哈希](results/record-manifest.jsonl) · [32控制](results/scorer-controls.json) · [执行协议](operator/protocol.json) · [终态](operator/run-report.json) · [11工件双哈希](artifacts.json) · [研究与应用路线](../../docs/robust-tool-use.md)。官方数据和训练权重不在此重新分发；评分器归档附带上游Apache2.0许可证，其余来源以固定commit和文件SHA核对。
