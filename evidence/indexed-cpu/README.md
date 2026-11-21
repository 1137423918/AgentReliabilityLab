# 附索引入口：真实神经模型运行证据

[协议和结果解释](../../docs/indexed-cpu-maintenance.md) · [report.json](report.json)。一次预先固定的正常CPU场景，整场上限1800.035秒终止；4份保存回复、5次读取、2份附加索引，0编辑/补丁/验收。不是脚本参考编辑，也不是已完成修复。

- [protocol.json](protocol.json)、[task.json](task.json)：原始字节不变。保持模型、采样、症状提示及保护验收；新增索引输出与通用提示，不作单因素归因。任务说明中的prepared/unrun是封存时状态，本次已执行。
- [pilot.json](pilot.json)：实际worker `-9` / timed_out、1800.035秒；不是请求次数或字节配额耗尽。
- [audit/report.json](audit/report.json)：在结束后以只读事务和图get_state重建消息，不新增推理。保存字面路径/offset/limit及索引身份；相关生产函数出现在所读821–920行，但没有编辑。
- [normal/model-requests.json](normal/model-requests.json)：5份请求/143169字节，最后一份未知在途仍扣额度；8次、单份65536、累计262144字节上限保持。
- [runtime.json](runtime.json)、[service/service.json](service/service.json)：实际worker位置、依赖、CPU/线程/模型/原生二进制身份及资源门槛。未加载GPU。
- [logs/server.log](logs/server.log)：保存回复的四条原生prefill计数合计9005，与输入26043减报告缓存17038一致。第五份未完成工作不在完整usage里；不是全场成本或计算总量。
- [service/shutdown.json](service/shutdown.json)、[service/stopped.json](service/stopped.json)：原生进程宽限后强制回收，returncode=-9、forced_cleanup=true；端口关闭、对应子进程不在。没有称为优雅退出。
- [artifacts.json](artifacts.json)：18份白名单原始/公开SHA，私人服务器路径及终端格式规范化。协议、任务和请求账本字节不改；不公开SQLite、完整对话、headers、权重或整个工作区。

报告另记录实际nfs4存储发现：SQLiteWAL不支持网络文件系统，本次仅为实际观察；后续先改本机状态存储和启动预检。不把历史过程强杀控制写成这种部署的可靠性保证。保留上游与推理后端许可证。
