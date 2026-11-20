# 固定原版验收与导出前语法检查

维护 Agent 需要修改生产文件，也可能合理地新增测试。如果只执行候选补丁自己的测试，候选能够通过跳过原有用例掩盖回归。因此保留候选测试，同时增加一个使用固定基线测试文件的独立验证视图。新策略是显式 opt-in，旧任务默认行为保留。

## 任务配置

`tasks/deepagents-path-model-protected.json` 从 grounded 模型任务继承固定基线、文件范围、模型和预算。它添加两份 Python 文件的语法检查与一条原版测试命令，原有三条验收命令保持不变。该阶段新模型任务尚未运行；后续沿用相同验收的 [Qwen3.5-9B 实际 CPU 试验](qwen35-maintenance.md)已完成，两场均在请求超时前没有编辑，未进入验收，不代表模型修复质量已有提高。

```json
{
  "required_features": ["python_syntax_v1", "baseline_verification_v1"],
  "python_syntax_files": ["path/to/module.py", "path/to/test_module.py"],
  "verify": [{
    "argv": ["python", "-m", "pytest", "tests/test_module.py"],
    "cwd": ".",
    "baseline_files": ["path/to/test_module.py"]
  }]
}
```

上例仅展示字段，实际可执行命令与原版测试 SHA 在完整任务文件中。`python_syntax_files` 必须属于可编辑文件；`baseline_files` 为固定 commit 中的普通、已跟踪相对文件，不允许重复规范路径。

## 文件与记录协议

导出前，运行器对全部声明的 Python 文件调用自身 Python 的 `ast.parse`。任一失败，整个导出在创建候选 worktree 或 patch 前停止，原始文本保留；不会自动解释字面反斜杠转义。这里使用 Python 3.11 语法，不能直接当作 Python 3.13 等其他版本语法的通用验证器。它也不保证语义、类型或业务正确。

带 `baseline_files` 的命令在 `verification-worktrees/NNN` 中运行：从固定 commit 创建 detached worktree，复制候选可编辑文件，指定的原版文件保持基线字节。候选自身测试仍在主候选 worktree 中运行并保留其新增内容。原版和候选测试有重叠，不累加成独立覆盖数量。

运行器记录验证视图路径、冻结文件清单、diff 哈希、日志哈希、退出码和超时状态。命令执行后及缓存复用前检查已跟踪内容、HEAD、允许改动范围和证据；验证命令改写视图，即使退出 0 也不接受。修复反馈同样复核失败视图，避免把已损坏的验收证据反馈成普通测试失败。

中断发生在视图准备阶段时，仅允许文件处于原版或预期候选字节的已知状态，恢复后完成导出；无法解释的人工改动会停止。通过后的缓存重新核对视图和日志，不重复执行已完成命令。

## 旧运行器与边界

新任务的固定验收命令先断言 `AGENT_LAB_BASELINE_VIEW=1`，再核对原版测试 SHA 和真实导入来源。新 worker 仅在独立固定视图中设置该标记，普通命令环境不继承外部同名变量。旧 worker 忽略新字段，但在此命令处失败，不能误记成功；它不是启动阶段的能力拒绝。`required_features` 的未知能力由新 worker 拒绝。

这是受控运行器中的完整性协议，不是恶意 Python 代码的系统隔离沙箱。视图不是操作系统级只读挂载，不覆盖所有未跟踪文件、依赖供应链或主机写入行为，也未证明消除所有测试投机。实际维护任务仍受独立路径契约、原版测试及候选测试共同验收。

## 服务器复现

准备与现有 Deep Agents 任务相同的固定 checkout 和 Python 验证环境，将该环境的 `python` 放入 PATH；worker 使用安装了项目依赖的 Python。只在授权服务器运行：

```sh
python -m unittest discover -s tests -v
python benchmarks/protected_grading.py --repo /path/to/deepagents \
  --output /path/to/fresh-output --legacy-source /path/to/preserved-old-worker
```

旧运行器使用本项目 commit `9c2dfe7ce0859df6b83ee62f2e9915706cd5e3ba` 的独立 checkout；其 worker SHA 在驱动中固定并在启动前校验，避免意外用新实现充当旧对照。首次 preflight 触发 pytest 插件重写警告，正常参考也失败，未计为有效对照；修正为导入断言后 exec 全新 Python 解释器，重新执行全部控制，保留首次日志。

控制使用显式脚本计划：正常参考修复、故意破坏 `regex_literal_hint` 并跳过对应测试的候选，以及旧 worker 的降级拒绝。没有神经模型生成。另一项重放直接使用先前真实模型留下的 900 字节无效文本；拒绝它不等于模型已学会修复。

逐场景结果、补丁、日志和源码哈希见 [公开证据](../evidence/protected-grading/README.md)。历史模型任务与失败记录保持原样。
