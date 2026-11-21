# 可恢复的维护任务运行器

状态：首轮基础设施验证已完成。该功能与原有工具契约共用仓库；[真实 CPU 模型尝试](cpu-model-pilot.md)已运行，四次均无补丁，尚无模型通过验收结果。

实际需求：长时间维护任务会遇到进程退出、重复启动、测试失败和人工修改。服务需要保留已经完成的工具步骤，恢复出同一份补丁，并把失败留在记录中。

## 执行路径

1. 固定仓库 commit、允许编辑的既有文本文件、任务提示词和显式验证命令。任务定义写入不可混用的 manifest。
2. Deep Agents 使用 `StateBackend` 编辑虚拟文件，LangGraph `SqliteSaver` 保存检查点。模型无法直接执行宿主 shell。
3. 完成后在任务专属的 detached Git worktree 中落地文件，生成真实 `git diff --binary`。
4. 执行操作者预先指定的验证命令，记录返回码、超时与日志哈希。
5. 成功时输出 `ready_for_review`、补丁和证据；不会自动提交、推送或合并。

运行目录由文件锁保护。相同目录不能同时交给两个 worker；重启时任务、仓库和 base commit 必须一致。已经成功的任务重放会验证原有补丁未被改动，并复用结果。

## 两种模型模式

- `scripted`：固定工具计划，下一步由检查点中的已完成工具结果决定，用于可重复的故障注入；不能用来报告模型能力。
- `local-openai`：显式连接本机推理服务。安装 `local-model` extra，设置 `AGENT_LAB_MODEL_URL` 和可选的 `AGENT_LAB_MODEL_KEY`。无云端回退；已取得真实 CPU 模型响应，尚无通过验收的模型补丁。

```sh
uv sync
uv run agent-lab-worker --repo /path/to/deepagents \
  --task tasks/deepagents-path-maintenance.json --run-dir /path/to/local-state/maintenance-001
# 中断后使用完全相同的命令与 run-dir 恢复。
```

示例任务作用于真实的 Deep Agents 仓库，固定到已知 commit，修改规范化逻辑并增加回归案例，再运行对应官方测试。固定脚本给出了候选编辑，不把它包装成模型自主修复。

## 验证范围与边界

33 条测试（8 条证据测试、15 条运行器测试、10 条 HTTP 传输与修复流程测试）已经通过，运行器覆盖：正常完成、检查点/落地后/验证前的真实 SIGKILL、重复执行、并发抢占、任务变更、输出越界、人工编辑冲突、验证失败、验证超时、日志完整性和跨重启的图步数预算。模型传输使用假 HTTP 服务验证；神经模型推理仍待运行。

可选的[修复入口](repair-loop.md)在单候选 worker 之外管理有限轮次，每轮有自己的检查点与工作区。原来的一次编辑后停止协议与新增的失败反馈修复协议分别保留；带额外轮次的任务不能交给单候选入口或其 pilot 静默执行。

- 运行环境为 Linux/Unix，使用 `flock`，不是跨平台托管服务。
- 文件范围限于 manifest 指定的既有 UTF-8 普通文件；新增文件、删除、二进制与符号链接暂不支持。
- 输入、输出文本总量均有 2 MiB 限制；图预算使用持久化 checkpoint step，并非 token/费用上限。
- 可选的 [模型请求预算](model-request-budget.md) 在 HTTP 发送前持久化预留次数与 JSON 请求体字节，跨重启和修复轮次共享；失败不退款。它与图步骤限制分别记账，不等于 token/费用上限。历史任务须显式增加 feature 和额度才启用。
- 验证命令是操作者明确提供的可信命令，不是面向恶意代码的安全沙箱。模型 API 凭据不会继承给验证子进程。
- 验证由独立监督进程管理。超时、worker 消失或命令结束时，清理命令的进程组；监督进程保留运行锁直到清理结束。Linux 上已测试只杀 worker PID 后恢复。未验证整机断电、监督进程自身被 SIGKILL、脱离原进程组的子进程；这不替代 cgroup 或恶意代码沙箱。
- 崩溃发生在命令结束与结果落盘之间时，验证命令可能重跑，须采用可重复执行的测试；不声称外部副作用 exactly-once。
- 保留 checkpoint 与完整运行目录供排查。不要将其中的仓库内容、对话或服务凭据直接公开；对外只发布经过检查的结果与复现材料。

## 真实仓库恢复实验

目标为 Deep Agents commit `744a797e3b9495539ca35571eeffd112a205f5c8`，任务哈希 `1f8426173527e962ee58b64d64929a7011d7cfbf1498617d73bb5ceb2c079aad`。脚本计划修改路径规范化并追加六个回归案例。

| 场景 | 恢复后的工具结果数 | 上游测试 | 补丁 |
| --- | --- | --- | --- |
| 正常完成 | 2 | 119 通过 | 与其余场景一致 |
| 第一次工具检查点后 SIGKILL | 2 | 119 通过 | 一致 |
| 补丁落地后 SIGKILL | 2 | 119 通过 | 一致 |
| 验证开始前 SIGKILL | 2 | 119 通过 | 一致 |

补丁 SHA-256：`f5ac2b13753a106a3b8f45fb308acddc3cfba477b841c5dbbcbf0d083f39d406`。检查点场景的恢复轨迹从已有 1 条工具结果继续到 2 条；两个后期中断场景没有再次执行模型图。

复现时，准备一份固定 SDK lock 的验证环境，把该环境的 Python 放在 PATH；worker 自身可使用单独的运行环境。任务首先检查 `deepagents.__file__` 位于当前 worktree，避免错误地测试另一份 editable 安装。

```sh
python benchmarks/recovery_matrix.py --repo /path/to/deepagents \
  --task tasks/deepagents-path-maintenance.json --output /path/to/local-state/matrix-001
```

CPU 实验曾遇到 data1 共享存储上的依赖冷导入超时；改用 home 中的独立环境后通过。没有把这次环境差异当作模型或算法速度提升。首轮原始失败日志保留在私人实验记录中。

## 验证进程运行时只杀 worker

首版实现仅在 worker 内处理验证超时。新增回归在旧运行器上真实失败：worker 被单独 SIGKILL 后，运行锁立即释放，验证命令及其子进程仍然存活。新 worker 可能与旧验证同时操作同一工作区。

现使用独立监督进程与 Unix pipe。只有 worker 持有管道写端，退出后产生 EOF；监督进程终止验证进程组，并持有继承的同一个 flock 描述符直到清理结束。验证子进程不会继承这两个资源。正常命令结束也会清理留在该组中的后台子进程。

在同一固定 Deep Agents 维护任务上，新增实验通过 `/proc` 观察到明确匹配任务 argv 的 pytest 进程，然后只向 worker PID 发 SIGKILL。监督进程清理旧验证后释放锁，恢复运行重新执行未完成的验证。正常参考与恢复场景均通过 119 条上游测试，补丁仍为同一 SHA-256。模型图已完成，无需再次执行两步编辑计划。

```sh
# Linux /proc；使用前述独立的 SDK 验证环境放入 PATH。
python benchmarks/active_verifier_recovery.py --repo /path/to/deepagents \
  --task tasks/deepagents-path-maintenance.json --output /path/to/local-state/active-verifier-001
```

证据：[修复前单项失败](../evidence/verification-supervision/parent-kill-baseline.log)、[修复后完整 21 条测试](../evidence/verification-supervision/worker-supervised-tests.log)、[真实仓库正常/恢复对照](../evidence/verification-supervision/active-report.json)。当前仍允许崩溃边界上的验证重跑，不保证任意外部副作用恰好一次。


显式 opt-in 的原版测试视图、导出前 Python 语法检查、缓存与失败反馈完整性协议见 [验收保护](protected-grading.md)。默认任务保持原有命令工作目录，新任务增加能力标记并在旧 worker 上于验收阶段拒绝继续。


后续版本已增加[本机状态准入与共享归档](local-state.md)。写入口不再接受旧NFS状态路径；原始试验记录保留，只读检查与本机新控制的范围分别说明。

## 独立会话子进程与源码绑定

A verification command could spawn a new-session child, exit successfully, and leave that child running. Original source408cd3ab reproduced this on the authorized Linux server; the probe was stopped. The new direct process-boundary checks both fail on the original supervisor.

The isolated Linux supervisor now uses PR_SET_CHILD_SUBREAPER before launching the command. Orphaned descendants, including double-forked children and new sessions, become its children. After the leader terminates it kills and reaps only its unreaped direct children, repeating as more descendants are adopted. The supervisor keeps the worker lock until cleanup completes. This does not depend on pidfd bindings or signal arbitrary PIDs from a system-wide snapshot.

A first candidate passed its two direct checks but failed three worker integration checks. Worker intentionally removes PYTHONPATH from the verification environment; python -m then resolved an older installed supervisor. The final worker starts the absolute verification.py file already loaded by itself. Verification commands still receive the filtered environment. Initial failure logs and candidate sources remain under attempt-1/.

## Server validation

- Original baseline: two new checks fail, as expected.
- Final focused group:5 pass, including strengthened existing timeout, worker SIGKILL/resume and normal leader-exit checks with new-session children.
- Complete suite:108 pass, zero skipped; the focused group and two new tests are included, not added to that count. Unittest 319.701s, controller phase wall 322.778s.
- New checks cover double-fork adoption/reaping and preservation of an unrelated process during timeout cleanup. Test probe readiness is atomic and failure cleanup checks its unique argv marker.
- No neural model, GPU, new upstream acceptance or autonomous repair result. Raw controller model_requests=0 denotes no real neural/provider requests; fake model HTTP services are exercised by the suite and their traffic is not claimed to be zero. Existing reports and dated portfolio snapshot retain their historical counts.

Every execution used four CPU cores/nice19, private ext4 state and fixed source hashes. Sampled16GiB tree RSS/12GiB available-memory guards and600s phase limits did not trigger; no observed owned process remained after final phase cleanup. Sampling is observational, not a claim about every transient process or unique-memory use.

## Boundaries

Linux only for descendant adoption; other Unix retains the original process-group cleanup. Procfs/subreaper setup must succeed before launching a Linux verifier. This is lifecycle management, not a hostile-process sandbox. External service managers/namespaces and killing the supervisor itself are not covered. SIGKILL cannot immediately end uninterruptible kernel waits: cleanup may keep the lock while waiting rather than report premature completion. Those OS failure modes were not fault-injected.

[Linux subreaper semantics](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html) · [waitpid child/reaping semantics](https://man7.org/linux/man-pages/man2/waitpid.2.html)

See protocol.json, report.json, reproduction.json, normal/ and attempt-1/ for exact source identities and normalized raw logs. Private root paths are replaced in public logs; original bytes and original/public SHA256 remain in manifests. No checkpoint databases or environment secrets are collected.
