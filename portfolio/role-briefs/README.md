# 按岗位整理的项目经历附件

本目录保存2026-11-25版的两类项目经历：算法与模型研发、Agent应用开发。每份选择两个已验证模块，加第一作者论文和一条正式提交的开源贡献；它们来自同一Agent Reliability Lab。正文不添加未提供的教育、实习、任职、联系信息或已合并经历。

- [算法与模型研发 PDF](../../output/pdf/algorithm-project-experience-2026-11-25.pdf) / [可编辑 HTML](algorithm-project-experience-2026-11-25.html)：工具调用训练与误差分析、研究资料检索。
- [Agent 应用开发 PDF](../../output/pdf/agent-app-project-experience-2026-11-25.pdf) / [可编辑 HTML](agent-app-project-experience-2026-11-25.html)：本地研究助手、依赖审查工作台。

两份均为单页A4；每份30段必需文字及9个链接核对通过。Poppler和PyMuPDF各渲染两页，并检查全部四张150dpi页面；[验证记录](../../evidence/role-briefs/qa.json)保留前期失败及修正原因。浏览器将派生CFF字形嵌入为Type3程序，PDF含字形与Unicode映射；无需读者安装该字体。HTML可使用系统中文字体。

`content.json`是可编辑正文，`evidence.json`将15组陈述绑定23份固定证据文件与Git提交。算法版强调配对LoRA训练、目标分解及完整摘要检索评测，保留“未证明稳定收益”；应用版强调论文资料的恢复、引用、交付和依赖审查工作台，区分确定性流程与模型能力。

生成器只创建独立文档，不会生成或更新个人网站。HTML与PDF使用同一份正文；旧版2026-11-22双语PDF保留历史，不能以其旧PR状态代替本版快照。修改内容后应重新核对来源、生成并检查最新渲染。

运行步骤（全部在授权服务器的独立CPU环境）：

1. `build_role_briefs.py --root <仓库根目录> --content <content.json> --evidence <evidence.json> --output <新HTML目录>`，核对来源哈希并生成两份HTML。
2. 使用独立FontTools4.61.1环境运行 `prepare_font.py --font <原始NotoSansCJKsc-Regular.otf> --html <HTML目录> --output <新文档字体目录>`；保留CFF字形ID，仅保留文档字符映射，并为派生字体改名。设置 `FONTCONFIG_FILE=<新文档字体目录>/fonts.conf`，原字体不变。
3. 使用Playwright1.65.2/Chromium159运行 `render_role_briefs.py --content <content.json> --source <HTML目录> --output <新原始PDF目录>`。
4. 使用pypdf7.1.1运行 `verify_role_briefs.py --content <content.json> --source <HTML目录> --raw <原始PDF目录> --output <新最终PDF目录>`，核对完整正文、链接、A4页数和实际使用字体嵌入。
5. 用Poppler将最终PDF渲染到PNG，另以 `inspect_role_briefs.py`/PyMuPDF1.26.6复核正文与页内边界并独立渲染；检查所有最新页面后才交付。

文档环境复用只读的已安装工具，Poppler缺失依赖仅从签名验证的官方RPM提取到本次私有前缀，未执行包脚本或修改系统。字体原文件、浏览器二进制和原生库不随此目录发布。正文日期与PR快照是固定时刻，不是实时状态。
