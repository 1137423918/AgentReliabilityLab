# 完整训练的数据准备与检查点 CPU 控制

状态：数据准备完成，完整三种子训练尚未启动，尚无本轮3B模型准确率或GPU恢复结论。该目录不代表训练/生成额度已经分配。

- [CPU运行与10项控制](cpu/operator/run-report.json)、[调度汇总](cpu/schedules/report.json)：三组种子42/43/44，每组原始3700条完整样本、164次更新、2791090输入token；reference335822监督标签，masked279751。每条原始样本和对应监督区域恰好一次，不截断上下文，不丢弃正常回复。
- 完整固定调度：[42](cpu/schedules/seed-42-schedule.json)、[43](cpu/schedules/seed-43-schedule.json)、[44](cpu/schedules/seed-44-schedule.json)。2048是参考标签的软分组目标，实际每步标签数用于各分支的损失分母。
- [新250题准入报告](cpu/admission/report.json)、[固定题号及关联组](cpu/admission/admission.json)：每类50题，共250个唯一文本关联组，与旧250题的ID和关联组均不重叠。复用经哈希核验且未变化的原始文本隔离图，保护Full/Mixed训练、开发、验证和旧199；没有重复执行图计算或读取答案/模型预测来选题。
- [最终6项检查点控制](checkpoint/v2/operator/checkpoint-controls.log)、[v2运行报告](checkpoint/v2/operator/run-report.json)：CPU微型随机网络的连续执行与保存后恢复逐位一致，涵盖权重、AdamW、GradScaler以及Python/NumPy/Torch随机数流；拒绝错误身份/参数顺序/损坏/覆盖，故障注入确认未完成写盘不会提交快照。先前[v1](checkpoint/v1/operator/run-report.json)5项也保留，不能把两版重复案例合并为11项独立能力。

两版检查点控制实际共34次微型CPU前向和34次优化器更新，预训练模型前向/更新均为0，CUDA未初始化。准备阶段的10项控制和原始数据处理没有模型调用。全部任务已终止，归属子进程为0；原始数据、源文件与旧599/750/831次账本未修改。

该检查点组件只提供身份绑定、张量/类型化JSON、原子目录提交与状态恢复；不自动授权中断更新的重放、返还未知调用或资源失败后的重试。生产训练仍需独立预算、持久化扣额、分段驱动和实际GPU跨进程恢复控制，不能用微型CPU结果代替。

[预先声明的完整研究政策](study-intent.json)固定完整一轮的最终检查点、三组种子以及主要比较：同一200条正例上，每种子masked−reference准确率差的均值，同时报告全部三个差值、离散程度和各自配对检验；不把600个相关模型/题目组合当独立样本。50条irrelevance与显式空调用、解码失败等分开披露。尚未生成或绑定新预测成绩。

新题只是未用于模型预测的队列。先前研究已持有答案资产，本阶段未打开答案；不宣称绝对gold盲化、语义/预训练隔离、完整BFCL或实际工具执行效果。

[CPU导出清单](cpu/export-manifest.json)、[检查点导出清单](checkpoint/export-manifest.json)记录每个导出原字节与公开字节的哈希；输入向量、标签、问题原文、提示、权重和私有快照不公开。[服务器私有稳定归档回执](cpu/operator/private-archive-receipt.json)保留完整准备输入和源文件，不能据此重启关闭实验。个人主页/Profile/Pages保持冻结。
