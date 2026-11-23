# 3B LoRA pilot：实际更新与未完成的核验

2026-11-23，固定预算 SFT，不是 GRPO 或 ToolRL-DR 复现。本快照记录 Full/Mixed 实际优化和各自核验边界；生成式工具调用对照尚未进行。个人主页未更新。

| 记录 | 实际结果 |
| --- | --- |
| 隔离运行时准备 | 退出0；32,475 个复制文件、11 个数据文件、11 个模型文件核对；CPU身份与 pip check 通过 |
| 首次 GPU 准入 | 退出2；监控查询超时；零模型前向、零更新、未创建自有 GPU 上下文 |
| Full 原训练 | 控制器退出2；子进程 SIGTERM；32 更新 / 65,536 标签 / 774 反向片段已完成，训练后最终核验中断 |
| Mixed 首轮完整训练 | 控制器/子进程均退出0；32更新 / 65,536标签 / 772反向片段；最终冻结参数与step32重载核验通过 |
| Full32 独立只读回放 | 子进程退出0，277次前向/0更新；全部197+79逐例损失与原结果完全相同；监督器在退出边界触发保护，整体仍失败 |
| step32 文件核验 | 五个文件与清单哈希匹配；未导出权重或优化器/RNG payload |
| 原卡后续准入等待 | 600.504 秒后退出2；仍有外部计算进程；零新模型前向 / 更新，自有进程已清理 |
| 持续 NVML 监控短测试 | 退出0；8 个样本；零模型或训练；不代表 GPU 空闲准入通过 |

Full 原训练最后持久化 driver report 记到第 1,320 次前向；每次 fsync 的 journal 和独立损失文件证明实际完成到 1,329 次。保留两份原状，不把 report 改成成功。预期总 1,331 次，最后两个 canary 未执行；最终内存中冻结参数哈希、检查点重新加载核验缺失。

Full 只优化 1,843,200 个 FP32 LoRA 参数；初始基座 3,085,938,688 参数 FP16。每步有限梯度、梯度裁剪、AdamW step、adapter 哈希变化均有检查，不能代替缺失的最终全量冻结参数核验。32 个已完成更新各有 2,048 个标签；输入暴露共 573,843。标准/选择位置损失和初始零 B canary 通过，原训练最终两个 canary 未执行；后续独立回放验证了保存适配器和关闭适配器的基座 canary，不回填原训练缺口。

Full 训练前/后 clean 开发 NLL 为 1.489357 / 0.277476，原扰动验证为 1.442288 / 0.297599。全量逐样本文件分别记录 197/79 条；这些是参考答案条件下的 teacher-forced 损失，不是自由生成评分。独立只读回放的277次调用另计，不增加优化器预算；不能用它补写原进程最终冻结参数指纹。Mixed 同起点开发损失为0.275333、原扰动验证0.297934；开发略低而验证略高，单种子32步没有验证损失优势，不能推出鲁棒性提升。最终三组生成评测与实际工具执行效果尚缺。

Mixed 实际输入暴露537,483、前向1,329预留/1,329完成/0未知，4次checkpoint提交，冻结参数全哈希、禁用adapter、最终adapter重载和canary均通过。GPU模型阶段455.992秒/整场479.411秒，未触发保护，owned0/GPU上下文消失。Full原失败、只读回放监督失败分别保留。两组共64次更新/131,072个标签；连同一次277前向回放，共2,935次已完成神经前向，六项CPU控制不混入。

## 复查入口

- [Mixed完整终态](mixed-v5/run-report.json)、[其driver报告](mixed-v5/driver-report.json)、[持久journal](mixed-v5/events.jsonl)、[step32元数据](mixed-v5/checkpoint-metadata.json)、[监督采样](mixed-v5/monitor.jsonl)、[协议](mixed-v5/protocol.json)、[控制器](mixed-v5/operator.py)、[所有权分类](mixed-v5/gpu_ownership.py)。
- [Mixed训练前开发](mixed-v5/before_dev.json)、[训练后开发](mixed-v5/after_dev.json)、[训练前验证](mixed-v5/before_val.json)、[训练后验证](mixed-v5/after_val.json)。
- [数值汇总](summary.json)、[原控制器终态和账本计数](full-original/run-report.json)、[原 driver 最后快照](full-original/driver-last-report.json)、[持久 journal](full-original/events.jsonl)。
- [训练前开发](full-original/before_dev.json)、[训练后开发](full-original/after_dev.json)、[训练前验证](full-original/before_val.json)、[训练后验证](full-original/after_val.json)。仅 ID/分组哈希、计数和损失。
- [step32 文件元数据](full-original/checkpoint-metadata.json)、[执行前协议](full-original/protocol.json)、[原控制器参考源码](full-original/operator.py)、[实际神经训练器](../../benchmarks/train_toolrl_lora.py)。
- [零模型准入失败](admission-failed-v1/run-report.json)、[其原协议](admission-failed-v1/protocol.json)、[其控制器](admission-failed-v1/operator.py)。
- [运行时准备](setup/run-report.json)、[准备协议](setup/protocol.json)、[准备控制器](setup/operator.py)、[子进程父身份绑定](operator/exec_child.py)。
- [Full32独立回放报告](full-replay-v4/report.json)、[其整体失败终态](full-replay-v4/run-report.json)、[开发逐例比对](full-replay-v4/dev.json)、[验证逐例比对](full-replay-v4/val.json)、[前向账本](full-replay-v4/events.jsonl)、[原退出附近监控](full-replay-v4/monitor-last-rows.json)、[冻结协议](full-replay-v4/protocol.json)、[核验源码](full-replay-v4/audit_driver.py)、[监督器](full-replay-v4/operator.py)。
- [真实进程所有权六项控制](monitor/ownership-test-report.json)、[其协议](monitor/ownership-test-protocol.json)、[PID/start_ticks分类](monitor/gpu_ownership.py)、[测试入口](monitor/check_gpu_ownership.py)。
- [原卡等待终态](followup-same-card-no-admission/run-report.json)、[其协议](followup-same-card-no-admission/protocol.json)、[其控制器](followup-same-card-no-admission/operator.py)。
- [NVML短测试](monitor/watch-test-report.json)、[其协议](monitor/watch-test-protocol.json)、[缓存句柄 watcher](monitor/nvml_watch.py)、[测试控制器](monitor/watch_test.py)。
- [环境依赖锁](../../extras/lora-training/requirements.lock)、[方法、限制和服务器调用入口](../../docs/lora-pilot.md)、[文件清单](artifacts.json)。

控制器源码中的私人工作根路径替换为 `/path/to/private-agent-lab`，仅用于审阅；协议和 manifest 另列原始与公开哈希。它们依赖经验证的私人输入与准入环境，不能原样复制运行。神经训练器及原训练协议未改字节；Mixed协议的私人已完成audit根路径另替换为 `/path/to/private-full-audit`，原/公开SHA分列。原提示、gold、token IDs、Parquet、权重、优化器和 RNG 张量不公开。公开资料中的模型文件哈希不等于模型权重再分发。

原归档客户端退出255，进程消失但缺失完成报告，不能记作成功；后续单独重建来源清单、核对已有 tar 的全部名称和大小，再在目标核对每个实际文件 SHA/模式。未证实首次归档退出的根因。准备、监控、训练的计数分别列出，不把 CPU 准备或监控样本算作神经实验。

退出边界的旧集合差集会把刚退出的自有PID误报外部；真实CPU子进程控制复现该缺陷，并验证未知/启动身份不符的PID仍被识别为外部。原v4没有记录触发PID，故不据此断言该次原触发根因，也不把原整体终态改判。后续不再重复已完成回放，以新协议复用不可变报告和账本；资源保护仍保留。

没有重跑或改判旧 199 条 P100 基线，未运行新的核心回归；原 130 项测试与本阶段模型结果分别记录。训练状态虽保存，恢复功能未实现。完整目标继续推进；本快照不证明生成式工具调用或实际应用效果。
