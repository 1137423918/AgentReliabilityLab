# 离线阅读页示例

将同目录`report/reading-report.html`下载到本地，或克隆仓库后双击打开。它是单个HTML文件，不需要启动模型、MCP服务或网页服务器；GitHub代码预览不会执行其中的交互。

页面整理四个已经关闭的真实阅读运行：两项旧论文解释/比较、一项未完成的资料缺失题，以及新增RECEIPT阅读问题。原回答、状态、页引用与失败诊断均保持不变。三项“已提交”是原应用状态，不是三项语义满分回答；RECEIPT解释不完整的[来源复核](../../evidence/frontier-reading/README.md)仍然适用。

可搜索问题、回答和论文标题，按状态筛选，打印当前显示结果，或下载全部JSON。没有匹配项时可清除筛选。筛选不移除文件内其他记录，分享HTML或JSON前请检查所有内容。页面本身不自动联网，打开论文链接需要网络；禁用JavaScript时仍可阅读全部记录。

同目录Markdown与JSON适合其他工具读取，`report-manifest.json`绑定三种交付格式。原始论文全文、逐页提取文字、模型完整通信和数据库均未包含。[使用入口](../../docs/research-reading-report.md) · [实际验证与桌面/手机截图](../../evidence/research-view/README.md)。
