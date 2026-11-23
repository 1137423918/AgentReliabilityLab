# Agent Lightning：复用 rollout ID 后的完成分页修复

针对 Agentic RL 基础设施 [Agent Lightning](https://github.com/microsoft/agent-lightning)，复现并修复了 rollout 生命周期与完成游标之间的关联错误。已提交 [PR #707](https://github.com/microsoft/agent-lightning/pull/707)，提交时为 **draft / open**；2026-11-23已转为正式待审，尚无合并结论。PR 披露了 OpenAI Codex 辅助，未作人工审阅或 CLA 证明。

## 触发与影响

服务端允许调用方预先指定 rollout ID，也提供幂等删除。以下使用公开 API 的顺序会触发问题：

1. 创建任务 A，并使其进入 `succeeded` 终态。
2. 删除 A，再使用相同 ID 创建输入、`data_id` 和 `is_train` 不同的任务 B。
3. 读取 `/api/rollouts/terminal` 的旧完成记录位置。

原版仅删除 rollout 和事件对象，完成日志中的 ID 仍保留。读取时按 ID 查询当前对象，旧记录因此指向 B：B 处于 `queuing` 或 `running` 时也会作为完成任务返回，B 后来完成时会在两个位置重复返回。依赖完成游标收集 rollout 的调用方可能读到错误的任务生命周期或输入身份。此次未运行 RL 训练，不能据此声称已经测量了训练效果影响。

原版 commit `2070bad5113e52f1aa2e5bdba822d4b24b197c05` 上，四种重建状态的回归均实际失败；另一个删除、重复删除与旧游标控制通过。

## 修复取舍

每次进入终态时记录 ID 对应的完成日志位置。删除时将那个位置置为 `None` 并移除索引，查询跳过空位；同 ID 的新任务只有真正完成后才追加自己的记录。

保留日志位置，使已经发给客户端的 `next_after` 游标保持有效。直接从列表删除旧项会移动后续位置，可能令已有游标跳过任务。索引也避免在每次删除时扫描全部历史完成记录。`total_terminal` 和游标继续计数日志位置，包括删除留下的空位；响应结构和状态转换规则保持。

修改两个生产文件、一个共享测试 fixture 和一个端点测试文件，补丁共75行新增、4行删除。最终提交为 `5d3342c07d849d4ce9c836e14d62d1ae8d91d9c9`，来自独立修复分支；[完整补丁](../evidence/lightning-terminal-reuse/fix.patch)。

## 服务器验证

独立 Linux / Python 3.12.16 环境使用原始 `uv.lock`，仅安装上游 `dev` extra/group，没有安装 VERL / Torch 训练栈。测试运行固定四个 CPU 核、nice19，采样限制自有 RSS 和主存余量；所有任务已退出，自有子进程为0。没有加载模型或占用 GPU。

| 范围 | 原版 | 候选 |
| --- | --- | --- |
| 四种重建状态 + 游标控制，5项 | 4 failed / 1 passed | 5 passed |
| 服务端与客户端相关集合 | 排除四个新失败状态后49 passed | 全部53 passed，0跳过 |
| 四个修改文件的 Ruff / 格式 | 本阶段不作原版结果声明 | 通过 |
| 四个修改文件的 Pyright 1.1.410 | 本阶段不作原版结果声明 | 0 errors / 0类型警告 |
| 上游版权头脚本 | 本阶段不作原版结果声明 | 复制的源码 / 测试快照通过 |

5项聚焦用例包含在53项候选集合中，不将它们相加为58项。实际命令：

```sh
python -m pytest -v tests/server/test_endpoints.py \
  -k 'do_not_reuse_deleted_completion or deletion_preserves_existing_cursors'
python -m pytest -v tests/server tests/test_client.py
python -m ruff check agentlightning/server/{store.py,routes/rollouts.py} tests/server/{conftest.py,test_endpoints.py}
python -m ruff format --diff agentlightning/server/{store.py,routes/rollouts.py} tests/server/{conftest.py,test_endpoints.py}
python -m pyright agentlightning/server/{store.py,routes/rollouts.py} tests/server/{conftest.py,test_endpoints.py}
python scripts/check_headers.py
```

原失败、测试结果和验证工具故障分开保留：V1 的53项测试通过，但两行测试超长；V2 已调整排版，执行器因相对 Git 路径在测试前退出；V3 的53项测试、Ruff 和格式通过，但 Pyright 的 Node 安装助手选中了预发布版本，未进入类型分析。V4 沿用字节相同的 V3 源码，隔离下载并校验固定 Node 22.23.5，再完成 Pyright 与版权头检查；没有重复已通过的53项测试，也不将 V3 整场失败改判成功。

Node 来自[官方固定版本目录](https://nodejs.org/dist/v22.23.5/SHASUMS256.txt)，归档SHA与[清单](../evidence/lightning-terminal-reuse/validation-v4/node-manifest.json)相符。官方 Python 锁、依赖和候选源码没有因此改变。这里只验证了列明的 CPU API / 静态范围，未运行完整仓库、VERL、包构建或文档构建，不声明上游 CI 全绿。

[原始 / 规范化证据与SHA](../evidence/lightning-terminal-reuse/README.md)。项目资料继续完善，个人主页保持冻结。
