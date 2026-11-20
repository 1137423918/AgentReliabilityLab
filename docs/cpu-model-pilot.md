# 真实模型 CPU 试跑与失败归因

本轮实际加载并运行了
[Qwen3-4B-Instruct-2507 的固定快照](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/tree/cdbee75f17c01a7cc42f958dc650907174af0554)。
这是小模型工程基线，不声称代表最新模型能力。此前的脚本与假 HTTP 验证仍按原范围保留。

## 结果

| 后端 | 正常场景 | 计划的检查点恢复场景 |
| --- | --- | --- |
| CPU FP32 | 无有效补丁，worker 返回 2 | 无有效补丁；中断时工具结果为 0 |
| CPU 动态 INT8 Linear | 无有效补丁，worker 返回 2 | 无有效补丁；中断时工具结果为 0 |

两种后端各尝试同一个公开维护任务两次，均没有补丁进入验收成功状态。两个恢复场景
未观测到有效工具进度，因此**不能算作真实模型的工具检查点恢复验证**。
脚本参考任务中已经通过的恢复实验不受影响。

FP32 的两个维护请求分别返回 32 / 45 个 token；INT8 返回 75 / 63 个。
四个请求均达到引擎的生成时间上限，没有返回可供当前解析器执行的工具调用。
运行器因没有补丁拒绝完成，没有把 HTTP 200 或模型自然语言当成维护任务成功。

这些结果受 CPU 预算与格式互操作影响，不能转写成通用模型成功率或 SWE-bench 成绩。
没有用成功样本替换失败，也没有改变原验收条件。

## 输入、运行时与预算

- 维护对象：Deep Agents `744a797e3b9495539ca35571eeffd112a205f5c8`。
- [原任务](../tasks/deepagents-path-model-baseline.json)保持不变，无固定工具计划，
  SHA-256 `ca52b3d3d66bbdf3df254fdafbb5359ffbe6255a5129694f0672782695a2407e`。
- 权重 revision `cdbee75f17c01a7cc42f958dc650907174af0554`；名义参数数目 4,022,468,096。
- CPU 为 Intel Xeon E5-2699 v4；Torch 2.8.0+cu128、Transformers 4.57.1，模型仅在 CPU。
- 4 个 Torch 计算线程、nice 19；实际 OS 线程还包括运行时和监控线程。
- 上下文 32768、每请求最多 1536 输出 token、seed 42、greedy、零传输重试。
- 引擎生成 `max_time=170` 秒、请求监控 180 秒、每任务场景 600 秒，服务最多 2400 秒。
  [Transformers 的 max_time](https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/text_generation)
  会完成当前计算步，因此观测到约 171 秒的返回，并非精确实时边界。
- 48 GiB 地址空间限制、36 GiB RSS 监控；64 GiB 空闲内存准入是本次共享服务器策略，
  不是该模型的普遍最低内存需求。

INT8 是单独预声明的 CPU 实验变体：用
[PyTorch 2.8 动态量化](https://docs.pytorch.org/docs/2.8/generated/torch.ao.quantization.quantize_dynamic.html)
转换 252 个 Linear，保留输出头、嵌入和归一化的 FP32 计算；原始权重文件不改写。
转换后权重另有哈希。它会改变数值与行为，不能把它与 FP32 的输出差异只归因于速度。
该固定环境打印了量化 API 弃用警告，日志保留；升级运行时需重新验证。

## 连接验证不等于任务验证

两个后端的短文本冒烟请求都实际生成了 `ready`，证明真实权重推理与 HTTP 接入可用。
这些短请求不计为维护成绩，也不能据此计算一般吞吐提升。

另外补做的短工具格式诊断，只用于排查互操作：模型生成了括号包裹的
`({"name":"read_file","arguments":{"file_path":"/sample.py"}})`，没有原生
`<tool_call>` 标签。当前严格解析器按普通文本返回，没有执行工具。
INT8 维护请求还出现了声明未提供函数的文本。可观察到格式偏离与时间截断，
尚不能据此认定单一根因。后续需要测试严格 JSON 格式兼容及模型获得的文件范围上下文。

## 复现

公开证据位于 [evidence/cpu-model/](../evidence/cpu-model/report.json)，含两个预声明协议、
对应源码快照、每次响应/原始生成文本、失败状态、原始与公开哈希。完整请求、checkpoint
和工作区保持私人，只公开请求摘要与哈希。

1. 按 [Hugging Face 下载说明](https://huggingface.co/docs/huggingface_hub/guides/download)
   获取固定 revision 的完整、非符号链接模型快照。
2. 在独立模型运行时中准备上述版本，先执行校验，再运行受限服务。
3. worker 使用自己的冻结环境；上游 SDK 验收环境放在 PATH 首位，保持原试验协议。

```sh
python benchmarks/verify_model_snapshot.py \
  --model-dir /path/to/model \
  --canonical evidence/cpu-model/model-files.json \
  --output /path/to/model/agentlab-download-validated.json

python benchmarks/cpu_model_service.py \
  --model-dir /path/to/model --output /path/to/new-service-run \
  --revision cdbee75f17c01a7cc42f958dc650907174af0554 \
  --threads 4 --quantization int8-dynamic

# 另一个终端；worker 与 SDK 验收环境的选择见原 pilot 文档。
AGENT_LAB_MODEL_URL=http://127.0.0.1:18843/v1 \
  /path/to/worker-env/bin/python benchmarks/model_pilot.py \
  --repo /path/to/deepagents --task tasks/deepagents-path-model-baseline.json \
  --output /path/to/new-pilot-run --case-deadline-seconds 600
```

复现 FP32 所用的服务实现可使用证据目录中的源码快照；当前入口也保留 `--quantization none`。
不同硬件及负载可能影响时间上限触发时的截断长度，不保证逐 token 输出一致。
这是实验性非流式接口子集，不是通用推理服务或恶意代码沙箱。
本轮服务已经按 PID、启动时间和命令身份核对后关闭，没有遗留模型进程。

后续入口已增加[显式 JSON 工具格式兼容与声明参数验证](tool-format-compat.md)。
本页的旧试验使用各自保存的原生标签解析器，结果及源码快照不变；不能用新的解析器
把旧四次维护尝试改记为成功。
