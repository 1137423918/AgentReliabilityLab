# Semantic Kernel：取消回调的重入死锁

对固定 `microsoft/semantic-kernel` 主分支 `aa46eddff989c13fba70c15e0ae8715b75f3fe8d` 的 Python 实验性运行时，复现取消回调读取自身 token、追加清理回调，或等待其他线程读取 token 时的锁重入问题。发现来自源码比对，并在真实 `InProcessRuntime` 的待处理请求中验证；不是用户生产事故，也不涉及模型调用。

`CancellationToken.cancel()` 原来在持有不可重入锁时执行用户回调；已经取消后的 `add_callback()` 以及 `link_future()` 也有同类持锁调用。候选在锁内更新状态、复制并移出回调，然后释放锁执行。后续登记复用同一规则，future 关联通过 `add_callback()`；保留异常传播和重复取消的行为。

这与此前 AutoGen 候选属于同一类缺陷，本轮验证了另一个实际框架，不是新增算法、模型能力或维护运行器适配器。

## 实际结果及边界

- 原版新增检查 **6 失败、4 个兼容对照通过**；候选完整运行时与群聊目录 **103 项通过**，包含上述 10 项新增检查。六个线程同时取消的对照只调用一次已有清理。
- 更广范围包含编排目录，共 195 项：候选 **182 通过、12 失败、1 跳过**；相同环境的原版为 **176 通过、18 失败、1 跳过**。除六项新回归外，12 个失败用例 ID 完全一致；其根因未全部解决，不能称全仓库或所有 Python CI 通过。103 项包含在广泛范围内，不累加。
- 真实运行时原版在 `agent_waiting`、`cleanup_entered` 后挂起，堆栈显示 `is_cancelled()` 等待 `cancel()` 持有的锁；45 秒外层限时后，仅终止并回收本驱动拥有的子进程。候选同一驱动中，回调返回已取消状态、执行一次，请求和处理器都收到取消，运行时停止并关闭。限时不能作为加速比。
- 两处改动的 mypy 检查通过；wheel 构建成功且包内 token 文件字节与已测试源码一致。构建保留原有 uv prerelease 配置弃用警告。按上游原配置对改动文件执行的适用 pre-commit hooks 和传输镜像记录见证据。

完整 [报告](../evidence/semantic-kernel-cancellation/report.json)、[原版与候选日志](../evidence/semantic-kernel-cancellation/README.md)、[最小源码与测试补丁](../evidence/semantic-kernel-cancellation/fix.patch)。上游草稿 PR 地址和实际状态保存在 [upstream-status.json](../evidence/semantic-kernel-cancellation/upstream-status.json)，草稿不等于已合并贡献。

## 服务器复现

准备固定源码的独立环境，`uv sync --frozen --group dev` 只安装基础与开发依赖；运行时还需要同一锁文件中的 `protobuf==5.29.6`。本轮 Python 3.11.4 / Linux，基线和候选使用同一环境，通过工作目录和显式 PYTHONPATH 校验实际导入来源。没有安装可选云模型/GPU extras，没有修改原有实验环境。

```sh
# 在所选原版/候选 checkout 的 python/ 目录执行；候选先应用公开补丁。
uv sync --frozen --group dev
uv pip install --python .venv/bin/python --no-deps protobuf==5.29.6
export PYTHONPATH="$PWD"
.venv/bin/python -m pytest tests/unit/agents/runtime tests/unit/agents/test_group_chat
# 广泛范围保留原版也存在的失败，不是绿色验收命令：
.venv/bin/python -m pytest tests/unit/agents/runtime tests/unit/agents/orchestration tests/unit/agents/test_group_chat
# 在 Agent Reliability Lab 的环境中调用，--python 指向上面的解释器：
python benchmarks/semantic_kernel_cancel.py --repo /path/to/semantic-kernel \
  --python /path/to/semantic-kernel/python/.venv/bin/python --output /path/to/new-output
```

[预先固定协议](../benchmarks/semantic_kernel_cancel_protocol.json)要求观察到真实回调进入标记才将超时分类为该死锁；导入失败不算死锁。公开记录保留了缺 protobuf 的初次失败、候选文件准备顺序错误以及 pre-commit 缓存/网络问题。最终使用原始 hook tag 对应源码镜像，只改变命令作用域内的 Git 传输，不改配置或禁用 hooks；不适用文件类型由 pre-commit 正常跳过。

用户回调仍可因自身逻辑阻塞；回调异常仍可阻止当次后续回调执行。没有解决任意线程直接取消 asyncio future 的 loop 归属问题，不承诺并发登记之间的总顺序。接口被上游标为 experimental。本轮不包含神经维护任务或新的 worker 运行时适配器；此前模型失败记录保持原样。
