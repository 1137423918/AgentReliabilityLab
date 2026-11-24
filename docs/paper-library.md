# 完整论文导入、按页检索与历史引用

研究资料检索服务0.2.0增加实际论文流程：明确指定本地数字文本PDF，通过pypdf7.1.1按页提取，再交给已有LlamaIndex、CPU E5和MCP服务。它解决“检索片段来自哪个PDF版本、哪一页，以及删掉资料后能否回读原引用”的问题。返回原文候选，不生成论文答案。

现有[CPU启动包](../artifacts/agentlab-research-0.2.0-starter.zip)和[wheel](../artifacts/agentlab_research-0.2.0-py3-none-any.whl)包含新命令与冻结依赖；[示例清单](../examples/paper-library/intake.json)使用两篇固定版本的公开论文。包不包含模型权重、论文原文或私有索引。

## 使用

在计算服务器安装[独立CPU运行环境](../packages/research-library/README.md)，把可信PDF放在清单旁，使用与本地文件匹配的HTTPS来源URL：

```json
{"version":1,"pdfs":[{"path":"paper.pdf","url":"https://example.org/paper-v3.pdf","title":"Paper title"}]}
```

```sh
agentlab-research prepare-pdf --manifest /path/to/intake.json --output /tmp/paper-input
agentlab-research ingest --manifest /tmp/paper-input/collection.json \
  --store /tmp/paper-store --model-dir /path/to/e5
agentlab-research search --query 'dual level retrieval' --top-k 3 \
  --store /tmp/paper-store --model-dir /path/to/e5
agentlab-research read --citation-id '<generation>:<node_id>' --store /tmp/paper-store
agentlab-research serve --store /tmp/paper-store --model-dir /path/to/e5 --port 18863
```

`prepare-pdf`只读取显式本地文件，不下载或认证调用者声明的URL。它保存原始PDF及其SHA256、每页未改写的提取文本与哈希，以及提取器版本。无文本页会出现在提取清单中，不会悄悄当作已索引文本；整篇无文本或加密文件会失败，且不发布半成品目录。支持最多32份PDF、合计256个物理页、单份32MiB和总原文件64MiB；单页提取文本512KiB、总文本16MiB。以可信单用户资料为目标。

每个非空页是一个稳定的“相对文件路径＋物理页码”来源，再按256token/32重叠分块。MCP的来源ID对应页；一次检索可返回同一论文的不同页。正文元数据不进入嵌入文本，`#page=N`指向1起始物理页，PDF内的页标签另列，避免把罗马数字前言或自定义标签误作物理页。

索引版本保留该版本的原始PDF和提取文本。引用返回文件哈希、物理页、页标签、提取器版本及提取文本的字符范围/行号；读取时核验归档。删除当前资料或原始导入目录后，历史版本仍可回读。旧版本持续保留会增加存储空间；同一PDF字节变化会更新其页来源的原文件哈希。哈希提供版本绑定，不证明调用者的来源声明真实，也不提供对整个存储被改写的密码签名认证。

## 真实服务器验证

使用官方固定版本[LightRAG v3](https://arxiv.org/abs/2410.05779v3)和[MiniRAG v3](https://arxiv.org/abs/2501.06713v3)，分别16页，共32个非空页来源、148个索引片段。原始PDF的下载地址和哈希在[输入来源](../evidence/paper-library/input-provenance.json)中；没有拿论文摘要、README或人工摘要替代全文输入。LS-DETR全文尚未取得，原有README/BibTeX示例仍按原范围记录。

- 全新Linux x86_64/Python3.11 CPU环境完成锁文件解析、安装、0.2.0 wheel构建/安装及依赖检查。八个规范模块/数据文件与wheel逐字节一致，实际应用从安装命名空间导入，离开源码目录运行。
- 21项源码控制通过：既有10项索引生命周期、6项文本导入，加5项PDF生命周期控制；不与过去16项重复累计。新测试覆盖物理页/标签区分、空页记录、输入删除后原PDF保留、换版后旧引用、篡改检测及空白/加密文档失败。
- 两篇PDF的全部提取页与原文件对应物理页逐字核对。真实E5完成148个文本输入和3个查询输入，共58次已完成CPU前向，零未知；这是独立封闭账本，旧103次和6次验证账本未改动。不是58个问答案例。
- 原生控制台 `prepare-pdf`、`read`、真实嵌入API和MCP/TCP联调通过，三个结构化工具均返回页面来源信息；重复导入与删除整篇论文没有触发新编码，删除后旧页引用与原PDF哈希保持一致。

两条事先写入的已知主题查询用于验证真实流程，另一次查询用于MCP联调，没有计算问答准确率或与旧24条排名诊断作比较。旧诊断未重跑，也没有调参后宣称检索收益。真实应用阶段59.543秒、峰值归属RSS约1.08GB，是两核受监督批处理测量，不能当成在线查询延迟。生成模型调用0、GPU使用0。

主控制任务在全部应用验证完成后，因缺少Poppler停在视觉检查步骤，保留该失败。另建仅渲染环境，以PyMuPDF生成两篇首页和两条查询首位来源页，共4页，未重跑嵌入。渲染检查和完整原文件/索引/日志保留私有，公开目录只放元数据与哈希投影。[证据目录](../evidence/paper-library/README.md)分别记录成功的应用、渲染补充和原控制任务失败。

[pypdf文档](https://pypdf.readthedocs.io/en/7.1.1/user/extract-text.html)说明数字文本提取与扫描件OCR的区别；本项目不处理OCR，也不保证多栏阅读顺序、公式、图表结构或视觉位置完整重建。视觉抽查只确认所检查页面与提取片段的对应，不能证明整篇每个版面元素都被正确解析。
