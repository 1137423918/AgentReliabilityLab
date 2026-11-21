# 中英项目与开源介绍

这是一份按已有证据编制的项目介绍，不是完整个人简历。当前侧重 Agent 工程，包含研究论文；不添加未提供的教育、实习、任职或产品上线经历。工程参考控制不计为神经模型自主维护能力，草稿 PR 不计为合并。

- `brief.json`：中英正文，网站与 PDF 共用。
- `evidence-map.json`：二十五份原始证据的路径和 SHA-256、四份 PR 的带日期状态快照，以及论文 BibTeX 哈希。包括本机 ext4 恢复与存储准入、当前完整回归，以及历史三仓库 NFS 控制和两次 CPU 模型试验；它不是实时 PR 状态接口。
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

此前生命周期阶段完整108项工程回归来自 `evidence/verification-tree/normal/full.log`；新增2项已计入，3项旧检查加强为独立会话子进程，不与早期100/106项快照累加。原版2项失败、首版3项worker集成失败及最终源码绑定/子进程回收的证据均保留。Linux监督器在释放worker锁前回收自己的孤儿后代；不是恶意代码沙箱，不覆盖监督器自身被强杀，也不承诺不可中断内核等待下的硬性清理期限。

本机ext4恢复包括Deep Agents正常执行和首个检查点SIGKILL控制；历史三仓库NFS控制使用明确参考计划并单列，不计模型自主修复。最新9B ADK CPU轨迹用完8次请求、读取1-800行，无编辑、补丁或验收。GPU33/33层加载与三个短请求仅验证链路，原样文本因标签失败，强制工具选择和受约束JSON通过；GPU真实维护因无合适空闲卡未启动。请求额度不等于token或费用。

此前PDF快照及其原始哈希在Git历史 `adf8d4eb3a95a1d201ae59a73a3566d92bea734f:portfolio/` 保留；本轮私人归档也保留了原PDF、正文、映射和构建收据。PDF逐页渲染检查只验证文档；此前浏览器内核故障未解决，不声称网页交互复查通过。

本次异步组件更新：完整116项检查通过（含新增8项），4场Pydantic AI SDK/真实工具控制单列，不与116相加。8次POST、3250字节均为明确假服务，无神经推理；在途取消保留未知占用，SDK重试受同一额度约束。8.4KB独立wheel与3个规范源码模块逐字节一致，安装后亦验证丢失账本拒绝重建。现有同步worker及68项依赖版本不变。此前108项结果及PDF保留于Git `be5fca0ef4663a4d0416e0e1672b1e8bd9c945d3:portfolio/`，历史叙述对应当时快照。

当前2026-11-21晚间快照：25份证据，124项完整回归通过（含新增8项证据检查），另列2场LlamaIndex假回复控制；真实9B CPU审计在600秒上限超时、零验收完成，后两题未运行。四份PR均为未合并草稿，OpenHands两项同组展示且分别提供链接。旧116项/三草稿PDF字节保留在Git `2c977ec8404c9ebfd159a7addb1d97b7500407ff:portfolio/`；本地旧工件另存归档。
