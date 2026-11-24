# 已有研究助手的离线阅读页 · 2026-11-25

本轮扩展报告交付能力：`research_report`在已有Markdown/JSON之外生成单文件HTML，提供问题/回答/来源搜索、状态筛选、打印及完整JSON下载。不添加模型推理、检索、答案补写或评分功能。[打开方式与示例](../../examples/research-view/README.md) · [使用说明](../../docs/research-reading-report.md)。

## 真实结果与验证范围

- [真实交付](application.json)：四个已停止运行，原状态依次为`submitted / submitted / turn_limit / submitted`，共六条PDF页引用；旧引用保留归档版本，新引用保留当前版本。未完成题仍没有已接受的回答，原有诊断不变。导出耗时1.169秒，两次输出逐字节一致，原运行、资料库和所有受保护旧归档/账本哈希不变。
- 新增5项页面控制测试通过，覆盖三类状态、HTML样式文本注入、数据往返、来源URL拒收、CSP脚本/样式哈希与输出清单；原9项报告工作流因导出格式新增HTML而重新回归并通过。它们是工程验证，使用真实LangGraph/SQLite和非神经夹具，不能当作模型问答质量；旧16项助手及21项全文测试未重跑累加。
- [实际浏览器检查](browser.json)：Chromium159.0.8154.6、Playwright1.65.2在服务器通过12项交互检查，含组合筛选、空状态、全角关键词归一化、页链接、筛选后下载完整JSON、打印样式、手机宽度及禁用JavaScript。另有独立的缺失记录/文本注入夹具，不算第五个真实模型案例。浏览器阶段3.153秒，进程树峰值约626MiB，页面错误与自动联网请求均为0。
- [桌面截图](screenshots/desktop.png)与[390px手机截图](screenshots/mobile.png)均由服务器实际浏览器生成，助手检查中文可读、按钮与引用显示完整、无观察到的裁切或重叠；不是独立人工可用性评估，也不宣称覆盖所有浏览器和屏幕尺寸。

全部测试、安装和浏览器执行在服务器进行；本轮新增生成请求、嵌入前向与GPU使用均为0。导出进程未载入Torch/Transformers，不连接原模型或MCP服务。桌面只进行源码/静态资产准备、哈希核对和截图检查。

## 状态与分享边界

“已提交”表示原运行接受了最终回答，不自动证明解释完整或陈述正确。RECEIPT原回答的定义及因果机制不完整，仍保留[原复核结论](../frontier-reading/README.md)；旧三题2/3和新问题的历史结果不重新判分或合并成新准确率。

筛选只改变显示和打印结果。HTML中始终有全部记录，“下载全部JSON”也保留全部记录；它不是删除或脱敏功能。正常阅读无需网络或服务，用户主动点击来源时才打开在线论文。关闭JavaScript后原静态卡片仍可阅读。

## 环境与保留的失败

[环境元数据](environment.json)固定浏览器、原生文件哈希、冻结Python依赖和私有字体来源。AlmaLinux9.7不在Playwright官方支持平台内，本次使用其Ubuntu24.04回退构建，实际验证范围仅为记录的独立库环境。日常生成/打开阅读页不需要该浏览器验证环境。

[三个环境准备失败](environment-failures.json)及`operators/`原始退出元数据保留：首次Node缺少libatomic；随后原始字体下载超过150秒阶段上限；浏览器下载成功后又发现13个缺失的原生库。后续复用已下载环境/浏览器/字体，在新目录中核对23个官方AlmaLinux RPM签名，仅提取库并建立校验过的SONAME别名，未安装系统包或执行RPM脚本。原应用代码、模型回答和原有账本未因这些环境问题修改或重跑。

[私有冻结归档回执](private-archive-receipt.json)绑定182个文件、26,970,079字节，包含六个已结束配置、环境失败、测试源码/日志、报告与截图；所属子进程均为0。不重复复制旧模型/索引、浏览器二进制或环境。公开清单不含字体、原生库、论文原文、原始模型通信、SQLite或凭据。

参考：[Playwright浏览器说明](https://playwright.dev/python/docs/browsers)、[MDN内联脚本哈希规则](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src)。实际实现以源码与`protocols/`中的冻结哈希为准。
