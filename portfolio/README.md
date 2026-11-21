# 中英项目与开源介绍

这是按已有证据编制的两页A4项目介绍，侧重Agent工程与研究论文；不添加未提供的教育、实习、任职或上线经历。当前核验时间为2026-11-22 03:16:06（UTC+8）。

- `brief.json`：中英正文，网页、复制描述与PDF共用；包含独立MCP工具启动包、130项核心回归、8项安装控制、10场消费端控制及真实模型限制。控制范围分开，10场包含此前4场。
- `evidence-map.json`：33份原始证据的路径、URL和SHA256，五份PR的带日期状态，以及论文BibTeX哈希。五份均开放、四份草稿、零合并；Copilot Bot的COMMENTED不视作人工批准。
- `build_brief.py`：校验全部输入、字体覆盖、PR状态摘要与链接，生成两页A4和静态双语页面；超出版面会停止。PR标签由快照导出，非草稿显示Open/开放，不再强制全为草稿。
- `build-receipt.json`与`qa.json`：记录输入/字体/PDF哈希、13段完整正文每页、12个实际URI每页、字体嵌入、最新150dpi逐页视觉检查。网页交互未复查，不能由PDF渲染推定。
- `brief.css`与`brief.js`：响应式页面、语言切换及用户点击复制；复制保留验证限制，剪贴板失败时提供选中文本。两资产字节未改。

33份证据均能在不可变提交`d6b1aeed20144ed173c35f78544ac7583e25ebb9`找到相同Git blob；文档正文、生成器和PDF在随后提交。该引用是证据输入版本，不冒充包含本轮PDF的提交。可下载启动包的九份报告另外固定在较早cb67290快照，不是实时PR状态。

实际恢复使用参考计划，未证明神经模型自主维护成功。本地9B CPU报告审计三个已知问题中2个通过结构契约，仍有文字范围歧义；后续外部MCP首题600秒超时，无有效提交，第二题未跑。GPU真实维护未启动，短链路试验不能代替维护验收。HTTP次数/字节额度不等于token或费用。完整130项与8项安装控制来自已经结束的服务器验证，本次文档更新不重跑实验或制造新分数。

论文LS-DETR为第一作者IEEE GRSL2025记录，DOI和BibTeX保持不变。当前贡献表包含OpenHands7032/7050、ADK8278、Semantic Kernel14845/14853。103项与97项为两个Semantic Kernel修复的独立相关范围，各保留12项更广原版失败；不累加，也不宣称完整上游CI全绿。Codex辅助实现与验证，上游人工批准未核实。

PDF使用嵌入的TrueType字体。调用者提供字体，不随源码分发；TTC的SC子字体下标由具体字体决定，本次为1，普通TTF一般为0。相同内容/日期/字体输入保持确定性，任何实质改动后必须再次渲染和逐页检查。

```sh
# 使用独立文档环境，保持worker运行环境不变。
python -m venv /path/to/document-env
/path/to/document-env/bin/pip install -r portfolio/requirements.txt
/path/to/document-env/bin/python portfolio/build_brief.py \
  --output /path/to/output \
  --font-regular /path/to/cjk-regular.ttf \
  --font-bold /path/to/cjk-bold.ttf \
  --latin-regular /path/to/latin-regular.ttf \
  --latin-bold /path/to/latin-bold.ttf
pdftoppm -r 150 -png /path/to/output/junzhe-wang-project-brief.pdf /path/to/page
```

先核实来源、PR状态和论文，再改正文与快照；动态标签不代替内容更新。生成后检查正文提取、全部链接、字体和版面。部署时PDF放`downloads/`，其他生成资源放站点根目录，沿用现有`style.css`。旧23:39版PDF及2190219a开头哈希在Git`bd665463617748372312e61c92c7140a9afaa8d4:portfolio/`和私有归档保留；不覆写历史实验报告或重算旧成绩。
