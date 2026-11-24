# 带版本引用的研究资料检索服务

面向整理论文资料、项目说明和技术复盘：用实际 LlamaIndex `VectorStoreIndex` 管理文档，使用本地 multilingual-e5-small 在服务器 CPU 上编码，提供关键词、语义与混合检索，以及 MCP 工具接口。返回候选原文和出处，便于接入后续研究助手；当前没有生成答案的模型，也没有完整论文问答成绩。

```mermaid
flowchart LR
    A[明确指定的来源清单与原文哈希] --> B[文档增量对比]
    B --> C[LlamaIndex 分块与 CPU E5 编码]
    C --> D[不可变索引版本]
    D --> E[BM25 / 语义 / RRF 检索]
    E --> F[原文片段与行号、版本引用]
    D --> M[MCP 三个读取工具]
```

## 索引与引用

每份来源包含稳定ID、题名、URL、类型和原始UTF-8文件SHA-256。LlamaIndex按256个token分块、重叠32个token；来源元数据不进入嵌入文本。E5按模型要求使用`passage: `和`query: `前缀、注意力掩码均值池化及L2归一化；本应用拒绝超过512token的编码输入，不静默截断。[模型说明](https://huggingface.co/intfloat/multilingual-e5-small)与[文档管理接口](https://developers.llamaindex.ai/python/framework/module_guides/indexing/document_management/)说明底层能力，版本发布、原文校验和引用回读由应用实现。

索引版本绑定来源清单、嵌入配置、分块参数与框架版本。不变资料复用已有向量；更新文档先删除旧节点再编码，删除来源不再参与当前检索。新版本在完整写入后替换`CURRENT.json`，旧版本保留；相同输入再次导入不产生嵌入计算。模型或框架版本变化要求新建存储目录。

每条结果携带`generation:node_id`引用ID、来源哈希、不可变来源URL、字符范围、行号和精确原文。读取历史引用会明确返回`is_current_generation: false`。这些校验用于可信本机资料的完整性与版本区分，不构成针对能改写整个存储目录的攻击者的签名认证。发布中断测试覆盖异常发生在发布前的情况，不宣称断电持久性。

## 使用

需要Python3.11及已配置的LlamaIndex、PyTorch、Transformers环境。实际验证复用了服务器两个既有环境的依赖路径，版本为llama-index-core0.14.26、torch2.6.0+cu124、transformers4.57.6、numpy2.2.6、mcp2.3.0；全部张量在CPU，CUDA未初始化。本轮没有验证全新独立环境安装，根项目的`uv.lock`也不包含这些可选模型依赖。

从仓库根目录，在该依赖环境中执行：

```sh
python -m agent_lab.research_library ingest \
  --manifest /path/to/collection.json --store /tmp/research-library \
  --model-dir /path/to/verified-e5-model

python -m agent_lab.research_library search \
  --query '维护任务中断后怎样恢复？' --mode hybrid --top-k 3 \
  --store /tmp/research-library --model-dir /path/to/verified-e5-model

python -m agent_lab.research_library read \
  --store /tmp/research-library --citation-id '<generation>:<node_id>'

python -m agent_lab.research_mcp \
  --store /tmp/research-library --model-dir /path/to/verified-e5-model --port 18863
```

MCP绑定`127.0.0.1:18863`，接口为`/mcp`，提供`list_sources`、`search_sources`、`read_citation`。工具声明结构化输出，检索可指定来源ID；引用读取不重新编码原文。服务器端串行执行读取/编码，限制请求体大小；这不是远程多租户服务。CLI默认报告本进程编码次数，持久调用账本与硬额度由验证脚本实现，服务本身没有跨重启请求配额。

模型目录需包含固定revision的6份模型/分词文件和`model-manifest.json`，结构见[模型资产清单](../evidence/research-library/model-assets.json)；运行时离线核对每份文件的长度与SHA-256，使用本地权重，不启用远程模型代码。文件清单与[来源示例](../examples/research-library/README.md)公开，权重和索引向量保留私有。

## 实际资料与验证

初始集合包含20份来源、163个节点；更新后仍为20份来源、160个节点。来源是固定版本的项目文档、LS-DETR仓库README及BibTeX，**未取得或索引完整论文**。更新过程只对README和新增工作台文档的24个片段编码，其余向量复用；重复导入零编码，删除来源零查询编码，旧引用准确回读。

服务器上10项实际LlamaIndex生命周期测试通过，使用非神经固定测试嵌入；真实E5编码与实际MCP/TCP联调另行执行。首轮MCP因裸`dict`返回声明没有生成结构化输出而失败，102次已完成CPU前向及原索引完整保留；补充明确的`dict[str, Any]`返回类型后，复用同一索引，仅增加1次查询前向完成联调。验证覆盖工具枚举、结构化结果、来源过滤、精确引用、历史引用、无效引用和已删除来源。

| 固定24条已知来源诊断 | 文档覆盖@3 | MRR@3 |
| --- | --- | --- |
| Latin词／中文二元组BM25 | 21/24 | 0.6458 |
| 多语E5语义检索 | 20/24 | 0.7778 |
| RRF混合，k=60 | 20/24 | 0.7569 |

问题和指定来源在排名前冻结；三种方式使用同一B版本、候选窗口24、每份来源只保留首个片段、最终返回3份来源。问题与标注未进入索引。它们是操作者编写的已知来源导航诊断，部分其他文档也可能相关；不是盲测QA，也不能用来宣称混合检索、答案质量或实际Agent任务有提升。

本轮共103次已完成CPU嵌入前向：187个原文片段输入、49个查询输入、零未知；没有生成模型调用或GPU任务。两核CPU/nice19，主实验阶段峰值约1.26GB归属RSS；全部受管作业已结束、无归属子进程残留。原始失败、冻结输入、测试日志和来源哈希见[验证证据](../evidence/research-library/README.md)。
