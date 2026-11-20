# Agent Reliability Lab

面向软件维护 Agent 的工具契约与可恢复执行：持久化工具进度、隔离代码改动，并生成可审阅的补丁与验证记录。


## 可恢复的维护运行器

`agent_lab/` 将 Deep Agents、LangGraph SQLite checkpoint 和隔离 Git worktree 接起来：固定任务与文件范围 → 虚拟文件编辑 → 导出补丁 → 显式命令验证 → `ready_for_review`。不会自动提交或合并。

- **33 条测试通过**：证据一致性、运行器、本地模型传输与有界修复，覆盖真实 SIGKILL、并发抢占、任务变更、人工修改保护、验证失败/超时、日志完整性与跨重启预算。
- **真实仓库四场景通过**：正常运行，以及检查点、补丁落地后、验证前的三处 SIGKILL。恢复后均完成两次工具操作，生成相同的 1573 字节补丁，分别通过 119 条上游测试。
- **验证进程运行中恢复通过**：观察到真实上游 pytest 进程后，仅杀 worker PID；监督进程在释放运行锁前终止旧验证。恢复后重新验证，补丁与正常运行一致，各通过 119 条测试。
- 上述实验使用固定工具计划，验证基础设施行为；没有声称模型自主修复能力。`local-openai` 已取得真实 CPU 模型响应；维护任务结果见下节。

[完整恢复协议与边界](docs/durable-worker.md) · [四场景报告](evidence/recovery/report.json) · [验证中断报告](evidence/verification-supervision/report.json) · [33 条测试日志](evidence/repair-loop/repair-full-tests.log)

```sh
uv sync
uv run agent-lab-worker --repo /path/to/deepagents \
  --task tasks/deepagents-path-maintenance.json --run-dir runs/maintenance-001
# 使用相同任务和 run-dir 恢复；验证依赖须先按任务说明准备。
```

故障矩阵入口：`benchmarks/recovery_matrix.py`。实验固定上游 commit 和任务哈希，先断言验证时导入的是 worktree 源码，再运行官方测试。检查点数据库与完整对话留在私人运行目录；仓库只保存检查过的结果与日志。

模型试验预设：[任务与独立验收](tasks/deepagents-path-model-baseline.json)、[正常/恢复两次试验入口](benchmarks/model_pilot.py)、[接入与验收自检报告](evidence/model-readiness/report.json)。基线保留 6 个独立契约失败，参考修复通过全部 28 个；模型文件已按固定版本逐文件校验。HTTP 测试服务是明确的假服务，不能计为模型自主修复结果。

## 无空闲 GPU 时的真实模型试验

在授权服务器的 CPU 上完成固定版本 Qwen3-4B-Instruct-2507 的 FP32 与动态 INT8 推理。两种配置各运行正常与检查点恢复模式：**四次维护尝试均未产出补丁，也未进入官方验收**。这是同一个公开问题的运行变体，不是四个独立基准任务。四次请求都触及生成时限且没有解析出的工具调用；恢复中断点工具结果为零，不能算模型工具进度恢复成功。

独立短诊断生成了括号包裹的工具 JSON，但没有原生标签，被严格解析器当作文本。生成速度、截断和格式互操作仍需分别排查。公开两份预声明协议、七次真实生成、精度和资源限制、源码快照及原始/公开哈希；没有把失败替换为参考修复。

[完整协议与复现](docs/cpu-model-pilot.md) · [全部失败记录](evidence/cpu-model/README.md) · [机器可读报告](evidence/cpu-model/report.json)。GPU 推理与模型自主修复通过结果仍待取得。新增 CPU 服务和快照校验入口已在服务器分别检查，未计入前述 33 条核心测试。

后续增加了[声明工具的格式兼容](docs/tool-format-compat.md)：原生标签模式保留，显式兼容完整 JSON / 括号 JSON；两种模式都校验工具名和参数 schema，拒绝未知函数、截断内容与无效批次。最终 14 项针对性服务器检查通过，四份历史维护输出仍为零工具调用。新鲜模型请求成功解析并执行了一次只读文件工具；但返回工具结果后，模型回答 `None`，未通过预先声明的完整往返验收。[原始响应与失败记录](evidence/tool-compat/report.json)均保留。新[文件清单任务](tasks/deepagents-path-model-grounded.json)只改提示词，验收和预算保持不变，后续运行见下文。

该文件清单任务随后在[原生 CPU 后端](docs/native-cpu-pilot.md)实际运行：固定权重转换为约 2.50 GB 的 Q4_K_M GGUF，以官方 llama.cpp、4 线程执行正常与检查点恢复模式。两种场景均在 600 秒上限终止，无导出补丁或官方验收；最后保存 9 / 13 条工具结果。中断前的两条目录查询状态得到保留，完整任务仍未通过。正常场景还留下含字面换行转义、静态语法无效的虚拟写入，已作为失败样例保留。[协议、派生模型身份及完整证据](evidence/native-cpu/README.md)。新增启动器的 3 项 Linux 进程清理检查通过，独立于前述测试组。

## 原版测试验收与语法导出保护

针对真实 CPU 维护失败增加两项显式策略：导出前检查指定 Python 文件语法；另建固定基线测试副本，在候选生产代码上执行未被改写的原版测试，同时保留候选自己的新增测试。验证后、缓存复用前和失败反馈前检查副本与日志完整性；修改验收副本，即使命令退出 0 也不接受。

本次完整服务器回归 **42 项通过、14 项跳过**（共 56 项，跳过项需要该环境未安装的 jsonschema），包含前述 33 项、3 项启动器检查和新增 6 项保护检查。14 项解析兼容检查曾在独立环境通过，未计为本次通过。新 [protected 模型任务](tasks/deepagents-path-model-protected.json) 尚未运行；原有模型失败记录保留，不声称模型修复成功率提高。

[配置、恢复与安全边界](docs/protected-grading.md) · [真实仓库脚本控制证据](evidence/protected-grading/README.md)。

## 有界的编辑、验收与修复

`python -m agent_lab.repair` 可以把完成的验收失败反馈给下一轮，继续编辑上一份候选。默认额外修复 0 次，可显式限制为 0–3 次；每轮有独立的检查点、Git worktree、补丁与日志，失败候选保留。反馈含日志哈希和最多 8 KiB 尾部；重启不会因为重置内存计数而增加轮次或重跑已有失败验收。日志或工作区被改动会停止自动流程。

[使用、预算与边界](docs/repair-loop.md) · [无固定计划的模型修复任务](tasks/openhands-undo-model-repair.json)。HTTP 测试使用假服务；真实仓库参考流程使用明确的固定计划，不是神经模型修复效果。

## OpenHands 撤销失败后的历史保留

在第二个框架 OpenHands SDK 中，通过真实只读目录复现：文件依次编辑为 0、1、2 后，撤销写入失败会提前消耗历史，恢复权限后重试错误地跳到 0。改为先读取历史、成功写回后再弹出，重试恢复 1，再次撤销恢复 0。

- [上游草稿 PR #7032](https://github.com/OpenHands/software-agent-sdk/pull/7032)：已提交，未合并；等待人类说明与维护者评审。
- 公共工具回归在原版失败、修复版通过；服务器上 185 条文件编辑器、规划编辑器与路径规则测试通过，相关 pre-commit 检查通过。
- [复现脚本、前后日志与哈希](evidence/openhands-undo/README.md) · [最小源码补丁](evidence/openhands-undo/fix.patch)。固定上游 `722e5d4`，Python 3.13.18，无模型或 GPU 调用。

这是受控的真实文件系统故障验证，不是生产事故或模型能力评测；不承诺历史缓存与文件写入跨崩溃的原子事务。

该缺陷也形成了第二个真实维护对象的[任务与复现协议](docs/openhands-maintenance.md)：模型任务无固定计划，参考任务仅用于故障验证；两者使用相同的操作者验收，且检查导入源来自 worktree。运行器本身仍为 Deep Agents / LangGraph，不声称已实现 OpenHands Agent 运行时适配器。

**OpenHands 维护任务四场景通过**：正常运行与检查点、落地后、验证前三处真实 SIGKILL 恢复，均完成三次工具操作，输出相同的 1,795 字节补丁，各通过同一组 184 条原有测试与独立权限验收。[自检与恢复证据](evidence/openhands-maintenance/report.json)。这是脚本计划驱动的运行器验证；184 不与 PR 的 185 重复累加，真实模型任务仍待运行。

[近期官方工程资料与本项目的取舍](docs/research-notes.md)记录了方向来源、推论和已验证边界。

## Google ADK 产物并发清理

[上游草稿 PR #8278](https://github.com/google/adk-python/pull/8278) 修复两个文件产物服务并发删除时的 `FileNotFoundError`：处理递归遍历中已消失的文件和目录，保留其他错误及嵌套产物。Python 3.11 / 3.13 各通过同一组 **2021 条相关测试、26 条预期失败**；原版的四项新检查为三失败、一项权限对照通过。无调度干预的公共 API 20 轮对照：原版每轮出现错误，最终候选均成功清理父版本并保留嵌套内容；不是通用成功率或速度对比。

这是第三个框架的存储贡献，未合并；没有新增 ADK 维护 Agent 运行时适配器。真实模型修复结果仍为此前的失败记录。新增复现脚本未改动运行器核心，本轮未重复执行不受影响的 42 项项目检查。[完整协议](docs/adk-artifact-cleanup.md) · [证据、初版失败和边界](evidence/adk-artifact-cleanup/README.md)。

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

公开日志替换了服务器私人路径，测试结论保持原样。Deep Agents 候选修复尚未提交上游 PR；OpenHands 草稿 PR 状态见上节。真实 CPU 模型尝试已记录，尚无通过验收的模型补丁。

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

项目不包含模型 API 凭据、服务器连接信息或上游环境。所含上游源码与补丁上下文归各上游项目及其贡献者所有，受对应 MIT 许可证约束；许可随各证据目录保留。
