# Semantic Kernel 取消回调证据

[完整协议与复现](../../docs/semantic-kernel-cancellation.md)。固定真实源码 `aa46eddff989c13fba70c15e0ae8715b75f3fe8d`，使用 Python 3.11.4 / Linux 服务器 CPU；无 GPU 或模型推理。API 是上游的实验性 Python 运行时。

- [report.json](report.json) 汇总范围、数值和实际草稿 PR；[upstream-status.json](upstream-status.json) 记录提交状态，不把草稿写成合并。
- [fix.patch](fix.patch) 只改取消 token 与新增测试；[baseline-new-tests.log](logs/baseline-new-tests.log) 为 6 失败、4 通过。
- [runtime-groupchat.log](logs/runtime-groupchat.log) 完整 103 项通过，含 10 项新增检查。**更广范围仍有失败**：[候选](logs/candidate-broad.log) 为 182 通过、12 失败、1 跳过；[原版](logs/baseline-broad.log) 为 176 通过、18 失败、1 跳过。除六项修复外，12 项旧失败 ID 相同；根因仍未全部解决。两个范围有重叠，不相加。
- [原版实际运行时](cases/baseline/report.json) 有 `agent_waiting` 和 `cleanup_entered`，堆栈显示回调读 token 被锁阻塞；45 秒后终止并回收驱动拥有的进程。仅超时而没有进入标记不能证明该问题。
- [候选实际运行时](cases/candidate/report.json) 使用相同驱动和协议；清理回调只执行一次，等待的请求与处理器都取消，运行时正常停止并关闭。另附两场 stdout 事件及 stderr 堆栈；这不是模型修复或超时前后的速度比较。
- [runtime.json](runtime.json) 绑定实际导入位置、安装版本、源码及 wheel 哈希；wheel 包内 token 与已测试源码字节一致。独立环境按上游 lock 安装基础/开发组，再补同一 lock 的 protobuf 5.29.6；不声称全 extras 环境。
- [mypy.log](logs/mypy.log) 检查两处改动；[precommit.log](logs/precommit.log) 与 [tooling.json](tooling.json) 记录原始 hook 配置、精确 tag commit 的镜像、适用检查及源码未改。仅命令环境改写下载传输，未修改全局 Git 配置。不适用 hooks 正常跳过。
- [build.log](logs/build.log) wheel 构建成功，原有 uv prerelease 配置弃用警告保留。没有声称完整上游 CI 矩阵通过。
- `preflight/` 保留缺 protobuf 的收集与运行失败（没有死锁标记）、候选文件准备顺序错误，以及 pre-commit 缓存所有权和 GitHub 空响应失败。准备错误没有计入缺陷证据。对旧下载进程的核对显示它已自行退出，没有因观察超时重启或终止活跃实验。
- [artifacts.json](artifacts.json) 对白名单文本保留原始和公开哈希；规范化服务器私人路径与终端格式，补丁及协议字节未改。各探针 `traceback_sha256` 指原始 stderr；其规范化映射在清单中。

回调异常传播、未知外部工作阻塞、跨线程 asyncio future loop 归属和并发登记排序等边界见协议。没有实现额外的维护 worker 适配器。上游源码/补丁上下文采用 MIT 许可，随附 [UPSTREAM_LICENSE](UPSTREAM_LICENSE)。
