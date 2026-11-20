# 声明工具的格式兼容

此前真实 CPU 模型的短诊断输出了括号包裹的 JSON，而服务只识别原生标签，
因此没有执行工具。新增显式 `--tool-format json-object-compat` 模式，处理这个
已观察到的互操作缺口。原来的四次维护失败及其源码快照保持不变。

## 接收范围

默认 `native` 模式继续要求完整的 `<tool_call>...</tool_call>`；兼容模式另接受
**整个响应**为单个 JSON 对象，或只用一对括号包裹的同一个对象。调用对象必须
恰含 `name` 与 `arguments`。不从说明文字、Markdown 代码块、列表或函数 schema
示例中提取调用，也不补全被截断的内容。

两种模式均核对本次请求中声明的工具名，并用 Draft 2020-12 schema 验证参数。
根参数须为声明了 properties 的 object，拒绝未列出的根参数名；支持本地 schema
引用，不获取远程 schema。兼容既有 JSON 字符串形式的 arguments，但不猜测、
转换参数类型或修复语法。重复 JSON 键、非有限数字、缺少必填项、类型/范围错误
都会拒绝。同一原生标签批次中有一条无效调用时，整个批次不返回可执行调用。

拒绝后保留原始文本、零工具调用和解析错误记录。这里仅验证格式和声明参数；
文件权限、任务范围和验证命令仍由执行器负责。它不是恶意代码沙箱。

## 服务器验证

最终 14 项针对性检查已在 Linux 模型运行时通过，重放了保存的真实输出：
旧短诊断在原生模式仍为文本，在兼容模式转为一个已声明的 `read_file` 调用；
四份截断维护输出在兼容模式仍然没有工具调用。还覆盖了不完整批次、未知函数、
未知/缺失/错误参数、重复键、非有限数字、远程引用拒绝，以及字符串参数中的
字面标签。它们是解析器检查，不是新模型生成或维护任务成绩。

原有 33 项核心测试的代码路径未改动，未重复运行。新增测试需要单独 CPU 运行时的
jsonschema；缺少该可选依赖时跳过，不给默认 worker 环境增添模型运行库。
服务器另行确认默认 worker 环境的 14 项均被正确跳过。真实模型调用完成后，
另发现并修复完整 JSON 字符串中的字面工具标签被误当作原生边界的问题；新增
回归在模型试验所用版本上失败，当前版本全部通过。模型试验的精确源码另行保存，
当前解析器对两份新鲜模型输出的重放也已验证，未声称为该边界再次加载模型。

## 新鲜模型调用的实际结果

独立协议在启动前保存。CPU3 节点上使用相同固定权重和动态 INT8 指纹，先发送与
旧诊断相同的请求：模型生成 20 token，接口解析出一个 `read_file /sample.py`，
操作者执行器实际读取测试文件一次。第二次请求已包含该工具结果，模型仅返回文本
`None`，没有逐字返回文件内容。因此 **`roundtrip_verified=false`**，入口退出 1。
已完成一次合法工具调用不等于整个往返通过。

停掉模型后，另用相同固定 tokenizer 重建第二次输入：250 token、一个真实文件标记、
完整 `<tool_response>` 标签。这个检查没有加载权重；它支持工具结果确实进入了
渲染后的提示，不足以归因模型返回 `None` 的根因。两次请求均未触及时限。

本次真实推理使用服务源码 `883db1be34f330f2015811e5fd6248e7a42478d95307be0995cae633fe56ea03`；
后续字面标签边界修复的源码及重放证据分别记录。旧四次维护失败保持原样。
[协议、精确源码、响应与失败报告](../evidence/tool-compat/report.json)公开保存，
服务已按进程身份核对后关闭。本结果仅验证一个短只读测试路径中的部分互操作，
不构成维护成功、模型自主修复或模型能力上限的结论。

## 后续维护任务的文件上下文

原始任务把允许编辑的路径放在操作者任务定义中，模型提示只说“两份提供的文件”。
模型可用 ls 自行发现，但首次请求中没有明确文件清单。新增
[带路径清单的任务变体](../tasks/deepagents-path-model-grounded.json)，只在原提示末尾
列出两条虚拟路径；生产问题、文件范围、独立验收、模型版本及所有预算完全相同，
仍不提供实现计划或参考补丁。任务哈希为
`1303a1af897a47cc10e30798733ea6efe2deea3f1ca018c8c290e568042d939c`。
这个任务变体尚未运行，不声称减少了失败；旧任务和旧结果不改写。

## 使用与复现

独立环境依赖见 [requirements-cpu-model.txt](../requirements-cpu-model.txt)。
实验使用已有 Torch 2.8.0+cu128、Transformers 4.57.1、jsonschema 4.26.0，
CPU 推理显式隐藏 CUDA。不要在其他任务正在使用的环境中安装或更新依赖。

```sh
# 在独立 CPU 模型运行时或已有相同版本的运行时执行：
python -m unittest discover -s tests -p test_cpu_tool_parser.py -v

python benchmarks/cpu_model_service.py \
  --model-dir /path/to/validated-model --output /path/to/fresh-service-run \
  --revision cdbee75f17c01a7cc42f958dc650907174af0554 \
  --threads 4 --quantization int8-dynamic --tool-format json-object-compat \
  --wall-seconds 900

# 另一个终端，最多两次真实模型请求、一次只读测试文件读取：
python benchmarks/tool_roundtrip.py \
  --diagnostic evidence/cpu-model/int8/logs/cpu-model-tool-diagnostic-20261120-02.json \
  --output /path/to/fresh-roundtrip-run
```

往返入口首个请求与已保存的短诊断请求相同。它只允许 `read_file /sample.py`，
将该虚拟路径映射到新建运行目录的一份固定测试文件；返回真实读取结果后，再请求
模型逐字返回文件内容。最多两次请求，不自动重试，不执行模型生成的系统命令。
是否通过以报告的 `roundtrip_verified` 判断；服务启动成功或入口退出本身不算通过。
这个短的明确指示测试不替代 Deep Agents 维护任务与独立验收。

依据：[Transformers 工具模板](https://huggingface.co/docs/transformers/v4.57.1/en/chat_extras)、
[jsonschema 验证接口](https://python-jsonschema.readthedocs.io/en/stable/validate/)。
