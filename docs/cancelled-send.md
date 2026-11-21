# 调用方取消之后，后续异常不能阻塞正常停机

Semantic Kernel 实验性 Python `InProcessRuntime` 的直接发送路径：调用方取消等待 `send_message()` 的 Task 时，响应 Future 一同被取消。Agent 处理函数或异步工厂随后抛出普通异常，原版仍对该 Future 调用 `set_exception()`，产生 `InvalidStateError`，跳过 `task_done()`；正常空闲停机于是等不到未完成任务数归零。

[草稿 PR#14853](https://github.com/microsoft/semantic-kernel/pull/14853) 只增加一个 `future.cancelled()` 保护，之后仍完成队列记账和错误记录。正常等待的调用方仍收到原异常；已经取消的调用方维持取消状态。这不强制取消 Agent 的工作，也不改变公开 API。

## 实际对照

冻结基线 `aa46eddff989c13fba70c15e0ae8715b75f3fe8d`，候选 `9eadf24486464a146f3168035769cc071a8182bf`。四个参数化用例以 `asyncio.Event` 固定顺序：处理函数或异步工厂，各配取消/未取消调用方。使用实际公开运行时与受控错误，没有模型、GPU、外部模型 API 或真实用户流量。

| 范围 | 原版 | 候选 |
| --- | --- | --- |
| 相同四用例 | 2通过、2失败；均为取消调用方的停机超时 | 4通过 |
| 运行时和群聊目录 | 原版对照包含在下方共同185个用例内 | 97通过、零跳过；含四用例 |
| 共同185个扩展用例 | 172通过、12失败、1跳过 | 共同用例结果逐项相同 |
| 扩展范围加入四新用例 | 四新用例另测 | 176通过、12失败、1跳过 |

97项与176项有重叠；不相加，也不加入维护运行器此前130项核心快照。12项编排失败和1项跳过均保留，不能称整个SDK或CI全绿。原配置所有适用pre-commit钩子通过，两文件mypy通过；源码未被钩子修改。只在服务器Linux/Python3.11.4验证，没有跨版本、操作系统或泛化成功率结论。

## 服务器复现

在授权服务器上取得该候选checkout，按[对应版本开发说明](https://github.com/microsoft/semantic-kernel/blob/aa46eddff989c13fba70c15e0ae8715b75f3fe8d/python/DEV_SETUP.md)建立单独Python3.11环境。本次复用既有隔离测试环境，基础依赖来自原uv.lock，并已有同锁的`protobuf==5.29.6`；没有修改该测试环境。完整实际分发版本保存在[身份记录](../evidence/sk-cancelled-send/candidate-v1/identity.log)。从checkout的`python/`目录运行：

```sh
# SK_TEST_PYTHON 指向服务器上的专用测试环境解释器
"$SK_TEST_PYTHON" -m pytest   tests/unit/agents/runtime/test_runtime.py::test_late_send_failure_after_sender_cancellation
"$SK_TEST_PYTHON" -m pytest tests/unit/agents/runtime tests/unit/agents/test_group_chat
"$SK_TEST_PYTHON" -m pytest tests/unit/agents/runtime tests/unit/agents/test_group_chat   tests/unit/agents/orchestration
```

检查原版时保留同一份新测试文件，再将生产源码还原到基线。包含四个用例的测试文件前后字节相同，固定5秒事件/空闲停机等待；测试在失败后也关闭实际运行时，未遗留任务进程。以[原版JUnit](../evidence/sk-cancelled-send/baseline/junit.xml)和[候选JUnit](../evidence/sk-cancelled-send/candidate-v1/focused.xml)为准。

## 构建与范围

最初控制器在测试环境执行`python -m build`时发现缺少构建前端；该失败及退出码2保留。随后建立独立uv锁定构建环境，使用`build==1.3.0`及项目允许范围内的`flit-core==3.12.0`完成构建。原测试环境版本、两棵冻结源码均未改，已通过的测试没有重跑。952729字节wheel的运行时代码与实际测试文件逐字相同；没有安装、执行或上传这份wheel，也不称官方发行版。

该修复与[取消回调锁PR#14845](https://github.com/microsoft/semantic-kernel/pull/14845)及[已合并的拦截器记账PR#14656](https://github.com/microsoft/semantic-kernel/pull/14656)分属不同路径；没有把前一PR未合并代码作为本轮依赖。当前#14845已由外部操作变为非草稿，观察到一条Copilot机器人`COMMENTED`记录、无行内修改意见；不代表人工批准。

[全部证据与SHA](../evidence/sk-cancelled-send/README.md)包括原版失败、完整扩展失败清单、原配置钩子、类型检查、构建工具锁和提交描述。源码副本保留上游版权及许可证。Codex辅助实现与验证，人工作者复核和上游人工评审待完成；PR未合并。本页新增贡献不重建此前有日期的双语PDF。
