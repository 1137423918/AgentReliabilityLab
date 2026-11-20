# 原生 CPU 推理后端的维护任务试验

本试验使用 llama.cpp 的官方 CPU 运行时，接入既有 Deep Agents / LangGraph
维护运行器。任务仍是同一个公开路径规范化问题，验收、文件范围和预算不变。
这是与早期 Transformers CPU 尝试不同的后端、精度及提示词变体，不是通用加速比
或模型能力排行榜。

## 本轮结果

两种场景均在预先声明的 600 秒墙钟上限被终止，未导出补丁，也没有进入官方验收。

| 场景 | 实际墙钟 | 保存的模型回复 / 工具结果 | 通过验收的补丁 |
| --- | ---: | ---: | ---: |
| 正常运行 | 600.115 秒 | 8 / 9 | 0 |
| 检查点中断后恢复 | 600.032 秒 | 12 / 13 | 0 |

恢复场景在两次 ls 目录查询完成后中断，随后继续执行 glob、读取、grep 等工具。
这支持导航状态得到保留，不能表述为已编辑文件恢复成功或整个维护任务完成。
服务日志记录 22 个模型任务启动、2 个取消；检查点保存 20 个模型回复。取消部分
没有完整回复，保存的 usage 不能当作完整 token 或费用统计。

正常场景曾把 47,177 字节、1,250 行的模块虚拟内容替换为 900 字节、单行文本，
其中保留了字面的反斜杠 n，静态语法解析失败。该文本没有导出、应用或执行；也没有
自动反转义修复它。恢复场景最后保存的两份虚拟文件内容仍与基线相同，包含一次
read_file 工具错误。时间消耗、工具使用和内容编码均是已观察到的问题，不能据此
归结为单一根因或模型能力上限。

[全部协议、轨迹摘要与失败证据](../evidence/native-cpu/README.md)。本轮结束后，
模型服务按进程身份核对并关闭，原生子进程正常退出，没有强制清理。服务的
0.5 秒采样最大 RSS 为 9,095,294,976 字节，不是整个节点的内存峰值。

## 固定输入与派生模型

原始模型是 Qwen3-4B-Instruct-2507，revision
`cdbee75f17c01a7cc42f958dc650907174af0554`。转换后重新校验原始 12 个文件，
8,060,915,998 字节全部匹配官方元数据；没有改写原始权重。

llama.cpp 固定为官方 b12576，源码 commit
`4783b1145c7073bb809f4c282ff4853cbfe42954`。未修改上游源码，先用官方转换器
生成 FP16 GGUF，再用同版本量化工具、4 个线程生成 Q4_K_M，不使用重要性矩阵。

| 派生文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| FP16 GGUF | 8,051,283,744 | `cf847ab70b480c27e53d241bc69c0be8c9385a00b7380e3680e1f4552c1b4f64` |
| Q4_K_M GGUF | 2,497,279,264 | `9f1c9b5bd32d1c37502b525a677b3245a1b91fb7b71c7464f4264647998e7a06` |

检查得到 398 个 tensor、4,022,468,096 个参数，其中 F32 145、Q6_K 37、Q4_K 216。
内嵌聊天模板 SHA-256 与固定 HF tokenizer 完全一致，EOS 为 151645。量化格式混合
使用不同精度，不能称为所有权重都是 4 bit，也不能把新结果归因于某一个改动。

官方二进制包按发布元数据的 SHA-256 校验。节点已有 C++ 运行库版本不足，因此把
校验过的 conda-forge libstdcxx / libgcc 解压到任务目录，通过子进程的
`LD_LIBRARY_PATH` 使用。系统、其他项目环境及其依赖没有改变。转换器的通用依赖
要求高于已有环境，本次只验证该 Qwen3 转换路径在实际版本上的结果，不声称全模型兼容。

## 执行边界

`benchmarks/serve_llama_cpu.py` 在启动前校验模型、可执行文件和库的哈希，并要求
至少 64 GiB 可用内存和足够 CPU 余量。只监听回环接口，显式设置 `--device none`
及 GPU layers 0；计算和预填充各 4 线程、1 HTTP 线程、1 个 32,768 token slot、
nice 19、48 GiB 地址空间和 36 GiB RSS 上限。服务最长 2,400 秒，退出时回收自己的
子进程组。3 项 Linux 进程检查覆盖模型被改动后的拒绝、墙钟终止及记录写入失败后
的子进程清理；这些检查不加载模型。

模型请求为贪心解码、seed 42、每次最多 1,536 输出 token，worker 请求超时
180 秒、零自动重试；每场景 600 秒、40 个持久化图步骤。原生 HTTP 的 180 秒参数
是读写超时，不等同于硬生成时限。提示缓存启用，关闭上下文移位，不据此声称严格
控制的延迟或恢复收益比较。

任务使用已准备的文件清单提示词变体，哈希
`1303a1af897a47cc10e30798733ea6efe2deea3f1ca018c8c290e568042d939c`。
不提供脚本计划或参考补丁。预设正常运行与工具检查点中断后恢复两个场景，均保留
失败；只有中断前实际完成过工具，才能检查相应的模型工具进度恢复。

目标 checkout 的 HEAD 保存着操作者此前的候选修复。试验前另行证明，模型的两份
初始虚拟文件都来自任务指定的未修复 `744a797e`，且不同于 checkout HEAD；
落地时也创建独立的固定基线 worktree。没有把操作者修复放入模型输入。

## 复现入口

按固定官方版本准备二进制、任务目录中的运行库及派生 GGUF，并先检查哈希和元数据。
不把权重或运行库随源码仓库上传。原始快照目录名使用
`Qwen3-4B-Instruct-2507-cdbee75f`；转换器可能把目录名写入元数据。可复现的准备步骤为：

```sh
# 在校验过的 b12576 源码目录中；使用独立转换运行时。
python convert_hf_to_gguf.py /path/to/Qwen3-4B-Instruct-2507-cdbee75f \
  --outfile /path/to/derived/model-f16.gguf --outtype f16

# 使用同版本、已校验的量化工具；4 个线程，不从另一量化模型再次量化。
/path/to/llama-quantize /path/to/derived/model-f16.gguf \
  /path/to/derived/model-q4_k_m.gguf Q4_K_M 4

# 生成新 manifest，核对架构、模板、参数量及文件身份；不加载模型。
python benchmarks/inspect_llama_model.py \
  --llama-source /path/to/pinned-llama-source --model-directory /path/to/derived \
  --server /path/to/llama-server --library-directory /path/to/runtime-libs/lib \
  --artifacts /path/to/verified-artifacts.json --output /path/to/new-manifest.json
```

本页哈希属于本轮实际文件。不同转换平台或元数据命名可能改变文件身份，应记录并
检查自己的产物，而不是冒充本轮文件。启动命令如下：

```sh
python benchmarks/serve_llama_cpu.py \
  --server /path/to/llama-server --model /path/to/model-q4_k_m.gguf \
  --manifest /path/to/native-manifest.json --library-dir /path/to/runtime-libs/lib \
  --output /path/to/new-service-run

# 另一个终端，worker 与上游 SDK 验证环境的选择沿用原协议。
AGENT_LAB_MODEL_URL=http://127.0.0.1:18844/v1 \
  /path/to/worker-env/bin/python benchmarks/model_pilot.py \
  --repo /path/to/deepagents --task tasks/deepagents-path-model-grounded.json \
  --output /path/to/new-pilot-run --case-deadline-seconds 600
```

三条验收依次检查工作区导入来源、官方测试以及模型不能编辑的 28 个生产代码契约。
运行器的 `ready_for_review` 仍需结合 diff 审阅，不能仅凭入口退出码、完成工具数或
生成了非空补丁就判定整个维护任务成功。验证环境不作为恶意代码沙箱。

资料：[固定 llama.cpp 版本](https://github.com/ggml-org/llama.cpp/tree/4783b1145c7073bb809f4c282ff4853cbfe42954)、
[官方函数调用说明](https://github.com/ggml-org/llama.cpp/blob/4783b1145c7073bb809f4c282ff4853cbfe42954/docs/function-calling.md)、
[Qwen 模型说明](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/tree/cdbee75f17c01a7cc42f958dc650907174af0554)。
