# 中英项目与开源介绍

这是一份按已有证据编制的项目介绍，不是完整个人简历。当前侧重 Agent 工程，包含研究论文；不添加未提供的教育、实习、任职或产品上线经历。工程参考控制不计为神经模型自主维护能力，草稿 PR 不计为合并。

- `brief.json`：中英正文，网站与 PDF 共用。
- `evidence-map.json`：十一份原始证据的路径和 SHA-256、三份 PR 的带日期状态快照，以及论文 BibTeX 哈希。新增 Google ADK 维护恢复与真实模型长预算试验；它不是实时 PR 状态接口。
- `build_brief.py`：生成两页 A4 PDF、静态双语页面及其资源，校验输入证据和字体字符覆盖，超出版面时停止。
- `brief.css` / `brief.js`：响应式展示、语言切换和按用户点击复制项目描述。复制包括验证边界；剪贴板不可用时提供选中文本。禁用 JavaScript 时中文正文与 PDF 下载仍可使用。

PDF 使用嵌入的 TrueType 字体。字体文件由调用者提供，不随仓库分发；换字体后必须重新检查排版。TTC 的中文 SC 子字体下标由所选字体决定，本轮系统字体使用 1；普通 TTF 通常使用 0。PDF 元数据日期来自核验快照，输出对相同输入与字体保持确定性。

```sh
# 使用独立文档环境，保持 worker 的依赖环境不变。
python -m venv /path/to/document-env
/path/to/document-env/bin/pip install -r portfolio/requirements.txt
/path/to/document-env/bin/python portfolio/build_brief.py \
  --output /path/to/output \
  --font-regular /path/to/cjk-regular.ttf \
  --font-bold /path/to/cjk-bold.ttf \
  --latin-regular /path/to/latin-regular.ttf \
  --latin-bold /path/to/latin-bold.ttf
pdftoppm -png /path/to/output/junzhe-wang-project-brief.pdf /path/to/page
```

更新正文前，先核实原报告、PR 与论文。若 PR 状态变化，应同时更新正文的状态表述和快照；不要只改一个计数。更新后渲染、逐页目视检查 PDF，核对文字提取、链接和字体，再发布。静态页面部署时，PDF 放在 `downloads/`，其余生成资源放站点根目录，并沿用现有 `style.css`。

本轮是已有成果的整理和文档产出，没有新增或重跑服务器实验，worker 核心与其历史 74 项测试证据保持原样。浏览器视觉及交互复查受当前环境限制，不能用 PDF 的渲染检查替代网页浏览器验收。

三仓库结果均为明确参考计划的运行器验证。新增 ADK 每场 1863 条原版测试、26 条预期失败与四个复用契约，不与更广的 ADK 包级套件或各恢复场景相加。真实模型试验达到 1800 秒整场上限，保存五次回复和六条工具结果，无虚拟修改或验收；不计自主修复成功。
