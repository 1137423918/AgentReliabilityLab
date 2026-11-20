# Agent Reliability Lab

面向软件维护 Agent 的工具契约与可恢复执行：持久化工具进度、隔离代码改动，并生成可审阅的补丁与验证记录。


## 可恢复的维护运行器

`agent_lab/` 将 Deep Agents、LangGraph SQLite checkpoint 和隔离 Git worktree 接起来：固定任务与文件范围 → 虚拟文件编辑 → 导出补丁 → 显式命令验证 → `ready_for_review`。不会自动提交或合并。

- **21 条测试通过**：证据一致性与运行器流程，覆盖真实 SIGKILL、并发抢占、任务变更、人工修改保护、验证失败/超时与跨重启预算。
- **真实仓库四场景通过**：正常运行，以及检查点、补丁落地后、验证前的三处 SIGKILL。恢复后均完成两次工具操作，生成相同的 1573 字节补丁，分别通过 119 条上游测试。
- **验证进程运行中恢复通过**：观察到真实上游 pytest 进程后，仅杀 worker PID；监督进程在释放运行锁前终止旧验证。恢复后重新验证，补丁与正常运行一致，各通过 119 条测试。
- 上述实验使用固定工具计划，验证基础设施行为；没有声称模型自主修复能力。`local-openai` 适配器已实现，真实模型调用尚待验证。

[完整恢复协议与边界](docs/durable-worker.md) · [四场景报告](evidence/recovery/report.json) · [验证中断报告](evidence/verification-supervision/report.json) · [21 条测试日志](evidence/verification-supervision/worker-supervised-tests.log)

```sh
uv sync
uv run agent-lab-worker --repo /path/to/deepagents \
  --task tasks/deepagents-path-maintenance.json --run-dir runs/maintenance-001
# 使用相同任务和 run-dir 恢复；验证依赖须先按任务说明准备。
```

故障矩阵入口：`benchmarks/recovery_matrix.py`。实验固定上游 commit 和任务哈希，先断言验证时导入的是 worktree 源码，再运行官方测试。检查点数据库与完整对话留在私人运行目录；仓库只保存检查过的结果与日志。

## 工具契约验证边界

`prepare.py` 从指定 Deep Agents checkout 提取 `to_posix_path` 与 `validate_path` 的**原始函数源码**，生成无第三方依赖的最小复现模块；`audit.py` 在服务器运行固定契约用例，保存逐例输入、期望、观察和判定。

这是隔离函数的契约检查，不代表完整包集成测试、Agent 成功率或模型能力评测。报告包含原始源码 SHA-256、上游 commit 和提取范围。后续扩展跨框架适配器与模型自主维护任务评测。

## 已完成的包级验证

在同一上游基线中新增 6 条路径规范化案例和 1 条实际 Agent 图回归：混合分隔符路径写入后，再通过规范路径读取。模型返回由固定脚本驱动，用于检查框架行为。

原版在两个相关测试文件中得到 **124 通过、7 失败**。候选修复恢复这 7 条回归，并在覆盖路径工具、同步/异步文件工具及权限判断的四个测试文件中取得 **380 通过**；Ruff、格式与 `ty` 类型检查均通过。

- [包级验证范围与结果](evidence/package-regression.json)
- [修复前测试日志](evidence/package-baseline.log)
- [修复后测试日志](evidence/package-candidate.log)
- [候选上游补丁](evidence/deepagents-normalize-separators.patch)
- [网站与复现记录](https://1137423918.github.io/#lab)

公开日志只替换了服务器绝对路径，测试结论保持原样。候选修复尚未提交上游 PR；模型自主完成维护任务的效果评测尚未运行。

包级复现：从 `langchain-ai/deepagents` 的 `744a797e3b9495539ca35571eeffd112a205f5c8` 创建独立 checkout，应用 `evidence/deepagents-normalize-separators.patch`，在 `libs/deepagents` 中执行 `uv sync --all-groups --frozen`，再运行：

```sh
make test TEST_FILE="tests/unit_tests/backends/test_utils.py tests/unit_tests/test_file_system_tools.py tests/unit_tests/test_file_system_tools_async.py tests/unit_tests/test_permissions.py" PYTEST_EXTRA="-n 2" COV_ARGS=
```

候选源码分支：[1137423918/deepagents](https://github.com/1137423918/deepagents/tree/1137423918/sdk/normalize-backslash-paths)。上游代码片段及补丁上下文的 MIT 许可见 [evidence/UPSTREAM_LICENSE](evidence/UPSTREAM_LICENSE)。

```sh
python3 prepare.py --checkout /path/to/deepagents --out prepared
# 在服务器上运行：
python3 audit.py --module prepared/baseline.py --cases cases/path_contracts.json --output outputs/baseline.json
```

退出码：0 全部通过，1 契约存在不符，2 配置或加载错误。报告失败不等价于安全漏洞；须结合实际调用链确认影响。

## 比较修复前后

```sh
python3 compare.py outputs/baseline.json outputs/candidate.json --output outputs/comparison.json
python3 -m unittest discover -s tests -v
```

比较器要求测试集哈希、验证范围和逐例输入/期望相同，拒绝缺失或重复案例，分别报告修复、新回归和仍失败的案例。候选仍有失败时退出 1；输入不兼容时退出 2。

评测脚本自身的 8 条单元测试已在授权 Linux 服务器上通过，覆盖数据集变化、伪一致哈希、结果缺失/重复、新回归和未预期工具异常。运行日志见 [evidence/evidence-tests.log](evidence/evidence-tests.log)。

项目不包含模型 API 凭据、服务器连接信息或上游环境。上游源码归 LangChain 及其贡献者所有，受上游 MIT 许可证约束。
