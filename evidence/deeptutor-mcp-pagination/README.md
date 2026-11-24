# DeepTutor MCP 工具分页修复 · 2026-11-25

[正式 PR #2930](https://github.com/HKUDS/DeepTutor/pull/2930)，目标 `dev`，提交 `be11576d26d0ccdc59130cba1c69857d56756a95`，开放、未合并。它是开源贡献，不是独立商业项目；上游工作流状态另见 [Actions 快照](upstream-actions.json)，服务器通过不能替代上游 CI 或维护者批准。

连接管理与设置页 Test/probe 原来各只调用一次 `ClientSession.list_tools()`。Python MCP SDK1.30.0 返回一页而不自动收集 `nextCursor`，后续工具因此缺失。修复共用私有分页函数，原样传递不透明游标，允许空中间页，完成全部发现后才过滤/发布工具；重复游标或后页错误不发布部分结果，分页阶段有既有连接超时边界，probe保留调用者超时。没有修改认证策略、依赖或公共配置。

## 真实 SDK/HTTP 验证

Linux 服务器、两个空闲逻辑 CPU、nice19、RSS8GiB/地址空间16GiB、内存余量及阶段/作业上限。完整源依赖、editable --no-deps 和官方 dev extras 安装后，仅补装匹配 CI 的 Ruff0.16；MCP1.30.0、pytest9.2.0、httpx0.28.1、Node22.23.5。测试使用真实 SDK/JSON-RPC/loopback HTTP、连接管理器、工具注册和后页工具实际调用，无抽取的生产函数、替代 SDK 或外部模型服务。

同样的十项用例在固定原版 `14796c70f622dc96b4d28a482c975c452d44f34e` 上 **9失败/1单页控制通过**，修复后 **10通过**，均0错误/跳过。包含空中间页、不透明游标、后页工具可调用、允许/拒绝过滤、游标循环、后页RPC错误，以及管理器/probe慢后页超时。完整MCP **192通过**（已包含新增10项），API **28通过**，注册/授权选择 **31通过**；不把嵌套范围或历史8项初版累计为额外案例。[完整配对](validation.json)、[JUnit](junit/candidate-new.xml)及日志保留原始结果。

## 全文件检查的既有失败

完整 Ruff check/format、架构、模块 requirements、一致性/导入边界和仓库卫生通过。`pre-commit run --all-files` 在原版与候选都完成，15个hooks中14个通过，唯一失败同为上游 `assets/figs/partners/siliconflow.svg` 缺最后换行。证明它只增添一个LF后，恢复两边原始字节；PR未包含该SVG。**所有配置 hooks 在本次三个文件上通过**，实际Git提交回传服务器后干净工作区检查通过。[对照回执](hooks-reconciliation.json)、[实际提交](clean-workspace.json)明确保留此边界，不能写成整仓pre-commit全绿。

第一次完整验证因 pytest 临时目录父路径未创建，8个错误发生在测试体之前，不当作产品复现。后续最终10项已真实执行。两次整仓工具初始化分别遇GitHub HTTP2与443连接超时；传送官方固定tag Git源码缓存后在服务器正常安装/运行全部hooks。初始环境准备的绝对Git路径与缺Ruff元数据问题、SVG对照、归档模板路径大小写失误都保留；不是模型质量重试。桌面只准备源码/Git/哈希与文档，安装、格式化、测试全部在服务器。

[私有归档回执](private-archive-receipt.json)核对178文件/11,193,536字节，九个实际CPU测试配置全部终态、归属进程0，六个失败配置保留；原封闭账本和归档未变。新增生成、嵌入和GPU使用均0。私有缓存/环境不发布；[贡献补丁](contribution.patch)来自实际提交，遵循随附上游Apache2许可。由Codex辅助实现、执行及核查。

上游CI快照：三个GitHub Actions工作流均为`action_required`、各0个jobs，需要上游批准后执行，尚无CI测试通过证据。

公开日志与JUnit为路径归一化的展示副本，失败文本的行尾空格已清理；原始逐字节输出保存在私有归档，[转换回执](projection-notes.json)保留原始与公开哈希，测试计数与断言不变。
