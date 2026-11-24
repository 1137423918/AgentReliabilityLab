# 研究资料检索服务：实际CPU验证

本轮交付是LlamaIndex增量检索与版本引用服务，可作为研究助手的工具层。没有生成式答案、完整论文问答或GPU训练。使用说明见[项目文档](../../docs/research-library.md)。

- [汇总](summary.json)：初始20来源/163片段，更新后20来源/160片段；更新只重算24片段，重复导入零编码；旧引用与删除来源检查通过。
- [24条冻结检索结果](results/retrieval-rows.json)：自编已知来源导航诊断，未把问题或指定来源写入索引。BM25/E5/混合的来源覆盖@3为21/20/20，MRR@3为0.6458/0.7778/0.7569；没有混合检索覆盖收益结论，不是盲测QA或生成答案准确率。
- [10项生命周期原始日志](results/lifecycle-tests.log)：实际LlamaIndex配合非神经固定嵌入，和真实E5语义验证区分。
- [首轮真实语义运行及失败](results/semantic-v1.json)：索引、增量更新、引用与24条检索均完成，随后MCP因裸dict输出声明无法取得structured_content而失败。102次CPU前向全部已知，原始ready=false不改写。
- [MCP修复后联调](results/mcp-followup.json)：三个工具改用显式dict[str, Any]声明，真实TCP/Streamable HTTP的结构化返回、过滤、原文与历史引用、无效引用和删除来源检查通过；复用同一索引，仅新增1次查询前向。
- [来源与版本](source-provenance.json)、[旧版本引用示例](results/old-citation-example.json)、[模型资产哈希](model-assets.json)。LS-DETR来源只有README和BibTeX，不是完整论文。模型资产清单中的local_neural_calls=0仅指桌面文件中转，实际服务器CPU计算见汇总103次前向。

[runs/](runs/)保留模型下载失败、生命周期测试、首轮MCP失败、修复后成功四种终态；[protocols/](protocols/)是私有冻结协议的选定字段及原协议SHA，不声称与原协议字节相同。[tested-source/](tested-source/)保存实际验证的应用、测试与分阶段脚本源码。首轮服务源码与当前版本只在结构化输出声明上不同，两个版本各自的哈希分别保留。测试和模型计算均在服务器执行。

主实验阶段90.426秒、峰值归属RSS1,264,234,496字节；MCP补充阶段24.558秒、峰值1,120,350,208字节。控制器总耗时另含CPU准入、文件校验与准备，不能当作在线检索延迟。使用两核CPU/nice19，全部作业终止、归属子进程为零，CUDA未初始化。总计103次CPU前向、187个原文片段输入、49个查询输入、零未知；生成模型调用0、GPU任务0。首轮102次账本关闭且哈希不变，补充1次单独记账；未重复原文编码或重跑24条检索。

旧599/750/831模型账本和84前向GPU对照记录保持不变；高资源GPU训练及未验证的GPU数值修复继续暂缓。模型权重、原始私有索引/向量和完整CPU事件账本归档在服务器；公开材料不包含这些资产。[私有归档回执](private-archive-receipt.json)提供文件数、哈希和边界。

验证导出归档SHA-256：`b6eb7920eaaf37015951c958be6c437370a27e3f6ad548182e8f654ba14eed4e`，31569字节、25个带哈希载荷；8份当前源码与服务器测试字节一致，详见[收集回执](collection-receipt.json)与[载荷清单](export-manifest.json)。后续新增的此README和收集回执不计入原25个载荷。
