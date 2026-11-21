# 检查点留在本机，归档另行保存

上一轮[真实模型试验](indexed-cpu-maintenance.md)之后，实际核对发现运行目录位于 nfs4。[SQLite 明确不支持在网络文件系统上使用 WAL](https://sqlite.org/wal.html)。此前的强杀控制只能说明当时观察，不能证明这种部署受支持。新的 worker 和 repair 写入口因此强制检查状态存储，原始试验与失败记录保留。

[真实NFS拒绝、ext4恢复、备份和完整回归证据](../evidence/local-state/README.md)。

## 新建和恢复使用同一准入

```sh
python -m agent_lab.worker --repo /path/to/source-repository \
  --task tasks/deepagents-path-maintenance.json \
  --run-dir /path/to/local-state/maintenance-001
# 在同一节点、同一位置用相同命令恢复。
```

代码仓库、依赖、模型权重与最终归档可以留在各自原位置。`--run-dir` 的可变检查点、锁和额度文件使用已识别的本机文件系统；不是简单把共享代码目录下的相对 `runs/` 当作本机状态。

共享 `run_lock` 在创建目录之前检查最近存在的目录，创建后再检查，并在拿到排他锁后重查。已有 SQLite 主文件/WAL/SHM、worker 锁、manifest、状态/结果/验收 JSON 和请求额度/锁必须是普通文件，不能是符号链接；已有文件也分别核对文件系统，避免只看父目录。锁文件使用 `O_NOFOLLOW` 打开。修复轮次不再提前创建子目录，子轮次同样先准入。

Linux 使用 [findmnt](https://man7.org/linux/man-pages/man8/findmnt.8.html) 的明确 FSTYPE 列和目标路径；缺少命令、识别失败、未知类型均停止，不回退为允许。macOS 通过原生命令查询磁盘及文件系统元数据；当前只做过 APFS 元数据观察和服务器上的适配器检查，没有完整 macOS worker 回归。

允许名单为 ext2/ext3/ext4、xfs、btrfs、f2fs、zfs、tmpfs、apfs、hfs。这是准入范围，不是对每种存储驱动、磁盘或硬件耐久性的认证。tmpfs 明确易失；本次真实运行验证的是 Linux ext4。NFS、SMB、FUSE、overlay 和其他未识别类型不作为已知本机状态存储接受。没有任务字段或开关绕过检查。

## 旧任务不会被自动改写

新的写入口也会拒绝旧 NFS 运行目录，包括已经完成、原本可能直接返回缓存结果的任务。对这些已识别的不合格目录，首次拒绝发生在创建状态目录、打开锁、初始化检查点、预留模型额度之前；不移动数据库，不重置额度，不重新调用模型。已有本机任务继续沿用原 manifest 身份规则，不添加导致旧 manifest 失配的新字段。

[只读查看命令](run-inspection.md)保持独立，可用于检查已有受信任记录；它不恢复工作，也不把历史 NFS 观察变成受支持的写部署。读取活跃 WAL 必须在原主机进行，并满足 SQLite 的文件系统要求；`immutable=1` 不能用来忽略正在推进的 WAL。

## 验证和归档范围

服务器完整 **100 项通过、零跳过**，其中十项新增存储检查已经包含在总数内。覆盖新建/缓存恢复拒绝、真实临时文件系统、控制文件链接与特殊文件、独立组件类型、目录别名、持锁后的复查，以及修复父目录和嵌套轮次。旧模型和 HTTP 接口检查不重复累加。

[真实路径控制驱动](../benchmarks/local_state_recovery.py)使用固定 Deep Agents 参考任务：验证真实 nfs4 上的新建拒绝及旧状态字节/mtime 保持；正常运行和首检查点 SIGKILL 恢复在已确认的 ext4 上进行。复用的 113 条固定原版、119 条候选和 28 个路径契约相互重叠，不计新增唯一回归，更不是模型自主修复成绩。

归档控制仅在源 worker 已退出、能拿到其原有排他锁之后执行：使用 [SQLite backup API](https://www.sqlite.org/backup.html)在本机生成独立 DELETE-journal 快照，关闭后再放入私人 ZIP；检查源数据与原 WAL 帧保持，以及备份的只读审计 JSON 一致。数据库、完整对话和 ZIP 不发布到网站或公共仓库。该快照不包含可搬迁的 Git worktree，**只验证审计重建，不声称可执行任务跨主机迁移或恢复**。

本次本机临时目录只用于验证；长期任务需要管理的本机存储及明确保留策略。准入不能抵御拥有挂载权限的外部更换、恶意路径替换或磁盘故障，也不提供主机断电恢复保证。未移动任何活跃旧 WAL，未运行新的神经模型试验。
