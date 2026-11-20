# 第二个真实维护对象：OpenHands SDK

运行器仍使用 Deep Agents / LangGraph。这里把 OpenHands SDK 作为待维护的真实
代码库，并使用其公共文件编辑器验收；不是另一个 OpenHands Agent 运行时适配器。

## 固定任务

- 基线：`OpenHands/software-agent-sdk@722e5d403cf75d4e032b79296cfaf178f8678a93`。
- 仅允许编辑 `editor.py` 和 `utils/history.py` 两份既有生产文件。
- [模型任务](../tasks/openhands-undo-model-baseline.json)：只提供故障现象，无参考工具计划。
- [参考任务](../tasks/openhands-undo-maintenance.json)：三步固定编辑，仅用于运行器故障验证。
- 两者共享完全相同的操作者验收命令；验收脚本不在可编辑文件范围。

验收先运行固定基线中的 184 条文件编辑器、规划编辑器和路径规则测试，再执行
真实只读目录故障检查。每条命令都显式从 worktree 导入 SDK 与工具模块，并核对
`__file__`，防止错误地使用其他 editable 安装中的修复版。

这里的 184 与 PR 证据中的 185 范围不同：后者额外包含 PR 新增的永久回归测试。
维护任务只修改生产文件，用操作者固定的权限检查补足原测试的盲点；不能将两个
数字累加或当作模型成功率。

## 准备运行环境

在 Linux 普通用户下，先按固定上游 `uv.lock` 完成 OpenHands 的 `make build`，
准备 CPython 3.13 环境；运行器使用其自身的冻结环境，不混装两套依赖。
将 OpenHands 环境的 `bin` 放在 PATH 首位，使显式验证命令 `python3.13`
选择该环境。下面所有绝对路径都由操作者填写：

```sh
export PATH=/path/to/openhands-env/bin:$PATH
/path/to/agentlab-env/bin/python benchmarks/validate_model_task.py \
  --repo /path/to/software-agent-sdk \
  --task tasks/openhands-undo-model-baseline.json \
  --reference-patch evidence/openhands-undo/maintenance-reference.patch \
  --output /path/to/new-selfcheck-directory

/path/to/agentlab-env/bin/python benchmarks/recovery_matrix.py \
  --repo /path/to/software-agent-sdk \
  --task tasks/openhands-undo-maintenance.json \
  --output /path/to/new-recovery-directory
```

输出目录须新建，失败材料需保留；不要覆盖旧实验或用 root 运行权限复现。
验证命令仍是可信操作者代码，不构成恶意代码安全沙箱。

## 实际证据

验收自检已在授权 Linux 服务器运行：原版 184 条原有测试通过，但真实权限验收
失败；参考修复 184 条通过、真实权限验收通过。原版错误地从 2 跳到 0，参考
修复依次恢复 1、0。没有使用模型推理。

正常执行与三处 SIGKILL（工具检查点、补丁落地后、验证前）均完成，恢复后各有
三次工具操作，输出同一份 1,795 字节补丁，各通过同一组 184 条原有测试与权限验收。
补丁 SHA-256：`026981ba94bccb42cb210dc5ff99a3ce050a9d566051f0e06ecd9cedd951177e`。
[公开报告](../evidence/openhands-maintenance/report.json)与原始 / 公开日志哈希保留。
该实验使用固定工具计划，不能写成模型自主修复或多框架 Agent 能力。
真实模型任务须另行报告全部试验与失败。

原始 OpenHands 代码及补丁上下文受 MIT 许可约束，见
[上游许可](../evidence/openhands-undo/UPSTREAM_LICENSE)。工程方向与外部资料见
[带来源的研究笔记](research-notes.md)。
