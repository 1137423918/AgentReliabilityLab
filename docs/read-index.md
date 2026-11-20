# 给已有文件读取附上当前 Python 定义索引

真实的 [30 分钟 CPU 维护尝试](long-cpu-maintenance.md)保存了五次模型回复和六条工具结果，却没有使用已提供的 `inspect_python`。五次 `read_file` 多次读取无关的前部代码，没有产生编辑或补丁。这一失败促成一个待检验的假设：把有限的定位信息放进模型已经选择的读取入口，可能比再提供一个工具更容易被使用。尚未运行新神经模型，不能声称定位或修复成功率提高。

任务的 `required_features` 显式添加 `python_read_index_v1` 才启用。它通过工具中间件给 `read_file` 的首屏补充索引，工具参数和完整原始页保持不变；不新增工具 schema，也不改文件读取本身的校验、分页或错误。新任务预设为 [deepagents-path-model-read-index.json](../tasks/deepagents-path-model-read-index.json)，仅准备，未推理。

## 返回内容和限制

- 仅任务允许的规范绝对路径、至少 400 行的 `.py`、`offset=0` 首页；相对路径别名仍可由原工具读取，但不附索引。
- 从当前检查点虚拟内容做 AST 解析，绝不导入或执行被检查源码。只列直接位于模块体的函数、异步函数和类，包含装饰器起始行。不是嵌套定义或语义依赖索引。
- 带当前源码 SHA256、单基行号及省略项数量。名字最多 80 字符，截断会标明；按源码顺序装入，超出预算的后续定义省略，没有针对任务名选择目标。
- 原始源码最多 2 MiB；附加内容最多 2048 UTF-8 字节，附加后整个回复最多 8192 字节。预算装不下时保留原回复，不裁掉用户请求的源码。行号转读取参数为 `offset=start_line-1`。
- 非 Python、小文件、语法错误、非物理换行字符、无法核对的回复格式、原文截断或超限均返回原回复。索引不是所有合法读取的保证。

`ToolMessage.additional_kwargs` 保存可见版本标记。同一路径、同一源码版本已在当前消息历史展示过索引时不重复补充；编辑改变哈希后可再附一次，检查点恢复沿用消息中的标记。历史被压缩移除后可能重现，不承诺跨所有上下文永久去重。混有 `edit_file` / `write_file` 的并行工具批次不附索引，避免拿批次前快照描述正在写入的版本；同批重复首屏仅第一条有资格补充。

[实际三场对照、完整回归与哈希](../evidence/read-index/README.md)。

## 验证与复现

服务器完整回归 **82 项通过、零跳过**，其中八项是本次索引检查，包含完整原文与消息元数据保留、边界回退、字节上限、版本去重、实际图的检查点与编辑刷新、旧任务不变，以及异步取消传播。八项已经包含在 82 内。此前安装 jsonschema 后恢复执行的 14 项也包含其中。

[真实仓库对照驱动](../benchmarks/read_index_recovery.py)执行同一明确的 `read → 两次参考编辑 → read` 计划：关闭索引、开启索引、开启索引并在首次读取保存后实际 SIGKILL。它核对原始读取页字节、编辑前后索引版本、补丁一致和固定原版验收。该计划提供了参考编辑，不是模型自主检索或修复；复用的 113 条原版、119 条候选和 28 个路径契约存在重叠，不累加为新增覆盖。

```sh
python -m unittest discover -s tests -v
python benchmarks/read_index_recovery.py --repo /path/to/pinned-deepagents --output /path/to/fresh-output
```

使用固定 Deep Agents `744a797e3b9495539ca35571eeffd112a205f5c8`，验收环境的 Python 放在 PATH；运行器环境安装本项目及固定依赖。输出目录必须不存在。内部预声明 [协议](../benchmarks/read_index_protocol.json)将故障前观察上限 180 秒、每次续跑 600 秒和整个对照控制器 2400 秒分开记录；不能把故障前加续跑称为合计 600 秒。

新索引会增加完整请求的上下文，尚未测量新真实模型的 token、净耗时、费用或修复效果。旧 `inspect_python` 与历史失败证据保留；新入口并不证明模型会依据索引跳转。

实现接口参考 [LangChain 工具中间件](https://docs.langchain.com/oss/python/langchain/middleware/custom)。实际兼容性以服务器固定安装版本及集成检查为准。
