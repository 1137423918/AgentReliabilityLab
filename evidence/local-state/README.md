# 本机状态准入和 ext4 恢复证据

[使用与边界](../../docs/local-state.md) · [summary.json](summary.json) · [report.json](report.json)。本轮无神经模型/GPU；两个完成场景使用明确参考计划，不新增自主修复成绩。

- [protocol.json](protocol.json)：运行前内部固定的协议，源文件/原任务哈希与本机根路径哈希绑定，不是外部预注册。故障观察180秒、续跑600秒、全控制器2400秒分别计时。
- [logs/full.log](logs/full.log)、[execution.json](execution.json)：最终100项通过、零跳过，包含十项新增存储检查，不能累加成110项；此前检查保持。同一专用依赖、显式本机ext4 TMPDIR，源码/普通日志仍在共享位置。
- [controls/reject-new.stderr.log](controls/reject-new.stderr.log)：实际nfs4拒绝，返回2，新运行目录未创建。[旧目录拒绝](controls/reject-old.stderr.log)同为2，既有控制文件字节和mtime保持；没有打开SQLite、恢复任务、创建额度或返回旧缓存成功。
- [cases/local-normal/result.json](cases/local-normal/result.json)、[cases/local-checkpoint/result.json](cases/local-checkpoint/result.json)：同一个既有四步参考任务，正常及首读checkpoint实际SIGKILL后恢复，均在ext4完成。补丁1573字节且SHA一致；各复用113固定原版/119候选/28契约，组间重叠，不计新唯一测试。
- [controls/source-inspection.json](controls/source-inspection.json)、[controls/backup-inspection.json](controls/backup-inspection.json)：源worker结束后，持原排他锁，用SQLite backup API产生本机独立DELETE-journal快照，源数据及原WAL帧保持，快照quick_check通过；审计JSON完全一致。私人数据库/ZIP留在服务器，不在公开材料中；不包含可迁移worktree，没有从归档启动worker或声称跨主机恢复。
- [runtime.json](runtime.json)、[test-storage.json](test-storage.json)、[source.json](source.json)：实际模块位置、依赖、文件系统和源哈希。结束后没有本控制根目录下的worker/验证监督进程。Linux ext4真实运行；macOS只有APFS原生元数据观察及适配器fixture测试，不是完整平台矩阵。
- [wheel-audit.json](wheel-audit.json)：wheel中storage/worker/repair字节吻合，实际从解包wheel元数据加载worker入口后拒绝NFS、返回2且不创建目录；复用依赖，无全局环境安装。
- [controls-execution.json](controls-execution.json)、[logs/controls.log](logs/controls.log)：全组172.879秒及实际返回0；不是性能提升对照。
- [artifacts.json](artifacts.json)：50份白名单工件的原始与公开哈希。规范化私人服务器/本机状态/测试路径和终端格式，协议/任务/补丁原始字节不变。完整SQLite、对话、私人ZIP、headers、权重和worktree不公开。

文件系统类型准入不能证明磁盘硬件耐久，也不能抵御特权重挂载或恶意路径替换；tmpfs易失，overlay/FUSE/未知类型不默认接受。旧NFS历史试验保持，不追溯改写为受支持部署。当前只复核Deep Agents的本机正常/首checkpoint恢复，未重跑全部历史故障点或其余维护框架。

参考补丁上下文遵循随附的上游 [MIT许可](UPSTREAM_LICENSE)。
