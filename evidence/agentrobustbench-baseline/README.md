# 199条真实3B工具调用基线

Qwen/Qwen2.5-3B-Instruct revision aa8e7253，固定AgentRobustBench111fd3db，获准服务器P10016GB/FP16/greedy，无项目训练、反馈或重试。全部199条完成、199预留/199完成/0未知，官方correct 119/199（59.80%），score_sum 120.666667。必填参数缺失3条，其中0条仍满足官方correct规则；检查范围不等于完整schema或真实工具执行。

[方法、分项及复查](../../docs/tool-use-baseline.md) · [汇总](results/summary.json) · [逐题指标](results/case-metrics.jsonl) · [执行前协议](operator/protocol.json) · [控制器终态](operator/run-report.json) · [模型报告](results/model-report.json) · [工件双哈希](artifacts.json)。

共36份清单工件，另加本README与artifacts.json。公开逐题行和token预检将原始ID转为UTF-8 SHA256与顺序号（部分原ID含完整问题）。完整消息、原始生成、token IDs和模型权重不发布；对应私有JSONL整体哈希及每题输出哈希保留。汇总器仅重建既有记录的计数、耗时与既存分数，不再调用模型或重跑评分器。

控制器返回0，三阶段无资源保护触发，所有自有子进程回收、自有GPU上下文消失；原上游源码/数据、驱动和包装器哈希保持。既有130项worker回归未重跑、未加入本轮计数。首次官方主机下载失败、独立环境安装、官方CDN续传与传输及推理前的完整哈希核验分别保留，不把失败或准备当神经生成。

原始协议、模型清单、锁及终态报告保留原字节。operator脚本/安装日志中的运行路径按清单规范化，公开SHA与原始SHA分别列出；token预检和逐题指标为注明派生的公开元数据。首次解析的53包URL/SHA锁在CPU安装前冻结，模型11文件共6,183,463,416字节均与官方固定revision核对。临时签名地址没有写入文件/argv，所属SSH ControlMaster已关闭。

仅199条clean单轮预测，未评22种扰动/全部3721场景、未训练、未运行真实工具或仓库修复。不重判历史CPU/GPU失败，不宣称ToolRL-DR复现、算法提升或通用应用成功率。主页、GitHub个人资料与Pages保持冻结。
