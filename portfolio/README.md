# 中英项目与开源介绍

这是一份按已有证据编制的项目介绍，不是完整个人简历。当前侧重 Agent 工程，包含研究论文；不添加未提供的教育、实习、任职或产品上线经历。工程参考控制不计为神经模型自主维护能力，草稿 PR 不计为合并。

- `brief.json`：中英正文，网站与 PDF 共用。
- `evidence-map.json`：十四份原始证据的路径和 SHA-256、三份 PR 的带日期状态快照，以及论文 BibTeX 哈希。包括本机 ext4 恢复与存储准入、当前完整回归，以及历史三仓库 NFS 控制和两次 CPU 模型试验；它不是实时 PR 状态接口。
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

本轮按已有成果更新项目介绍，没有新增或重跑服务器实验。当前 100 项完整回归来自 `evidence/local-state/logs/full.log`，含十项存储检查；不与早期 74/82/90 项快照累加。Linux ext4 实测包括 Deep Agents 正常执行和首个检查点 SIGKILL 恢复；完整 macOS worker 矩阵未运行。备份重建相同只读审计，仅证明审计快照，不证明 worktree 迁移或跨主机恢复。

历史 Deep Agents、OpenHands SDK、Google ADK 三仓库控制使用固定参考计划，并运行于旧 NFS 条件，不能作为当前受支持存储下的恢复验证，也不计模型自主修复。最新 `indexed-cpu` 真实模型试验达到 1800 秒整场上限，保存四次回复、五条读取结果；无编辑、补丁或验收。早期 `long-cpu` 试验另行保留，两者不混写成一次运行。请求次数和 JSON 字节额度不是 token 或费用。

浏览器视觉及交互复查受此前确认的内核故障限制，不能用 PDF 的逐页渲染检查替代网页浏览器验收。
