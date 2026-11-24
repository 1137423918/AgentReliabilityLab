# LangGraph依赖升级审查工作台：实际服务器证据

[源码](../../agent_lab/review_workbench.py)、[使用方法](../../docs/dependency-workbench.md)、[12项测试源码](../../tests/test_review_workbench.py)。

主阶段[运行报告](operator/main/run-report.json)与[测试日志](operator/main/workbench-controls.log)确认12项通过；两份实际项目报告成功批处理，重复运行复用两项已完成图状态。[批次输出](examples/summary.md)、[Browser Use报告](examples/reviews/browser_use_1_0_8.md)、[FastMCP报告](examples/reviews/fastmcp_2_12_4.md)是服务器生成的原字节内容，不是手工重写的预期结果。

FastMCP成对279项上游测试由既有兼容性实验提供，本轮核对其测试ID、状态、源码清单与扫描锁文件归属，没有重跑279项测试或漏洞扫描。Browser Use被精确版本约束阻止，FastMCP具备限定范围测试通过的证据但仍有16个受影响解析项；均不代表发布批准。

[跨进程恢复报告](recovery/report.json)与[监督记录](operator/recovery/run-report.json)：collect节点提交后对唯一归属子进程实际SIGKILL，返回码-9；新的Python进程恢复后禁止重新读取已完成报告，四份单项JSON/Markdown与批次Markdown共五个文件，与正常路径字节一致。这是节点已持久化后的恢复，不是活跃SQLite写入、断电或对抗进程实验。12项测试与一个跨进程场景的范围不相加为模型能力。

框架实际版本为LangGraph1.2.24、SQLite Checkpointer3.1.3，沿用已有项目锁定环境。每阶段2核CPU/nice19，AS16GiB、归属RSS4GiB、主机准入16GiB/下限8GiB；两个监督任务均正常终止且归属进程为0。新模型调用0、GPU使用0。

[延期GPU源码CPU预检](operator/main/deferred-source-CPU-preflight.log)仅验证源码语法和当前Torch确定性API可用，CUDA未初始化，实际GPU续跑证明仍为false。不能将其写成GPU修复已通过。

[导出清单](export-manifest.json)保留原始与公开字节哈希；tested-source中的工作台、测试、样例清单、项目配置及延期研究源码均与对应本机文件逐字节核对。SQLite数据库、访问凭据、权重及私有运行目录未导出。源码、字段与文档中的模型调用0只指本轮没有真实神经/provider请求，既有9B模型结果另行记录。

[简历中提及的三条PR只读快照](portfolio-PR-state.json)独立保存，三条仍为正式开放、未合并。没有发送评论、创建issue或修改上游状态。个人主页/Profile/Pages保持冻结。
