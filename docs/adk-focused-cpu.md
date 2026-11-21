# 真实 ADK 维护：定位到实现，仍未形成补丁

既有模型试验在 Deep Agents 任务上耗尽 CPU 时间，最新一次读到了相关函数但没有编辑。本次改用已经校验的 Qwen3-4B Q4_K_M，在 Google ADK 的实际产物并发删除问题上验证更小模型与显式符号定位提示。任务仍只允许修改固定生产文件，不提供参考实现、替换内容或工具计划。模型、任务、采样、提示与存储同时改变，因此不作单因素因果或通用能力比较。

[预声明协议](../benchmarks/adk_focused_cpu_protocol.json)绑定任务字节与规范化哈希、十三份运行源码、模型/二进制哈希、ADK基线c81876a与所有限制。输入任务见[精确配置](../tasks/adk-artifact-delete-model-focused-cpu.json)。源代码与只读报告可在共享存储，活动SQLite检查点、worktree和TMPDIR必须放在已准入的本机ext4；沿用[本机存储策略](local-state.md)。

模型运行913.965秒，完成八次请求后在下一次发送前被持久化请求守卫拒绝，worker返回2，未达到1800秒整场上限。先依次查询四级目录，再读取模块定义、删除实现、list_versions和类首屏。虽然读到了问题相关实现，**没有任何虚拟编辑、补丁导出或验收执行**。固定原版1863/26预期失败组与四个独立契约保持，但没有在本次未完成候选上执行；不新增测试成绩，也不改变既有100项项目回归的来源。

预算为每请求600秒、整场1800秒、服务2400秒，最多8次请求、单份JSON65536字节/累计262144字节，输出1536token、40graph steps、零重试/修复/故障注入。实际最大单份22509字节、累计119155字节，触发的是请求次数限制。只运行一个预先声明的正常轨迹，没有为补成功重置额度或延长时限。

八份已保存回复usage为input29591/cache-read24026/output451，输入减缓存5565与八份完成的原生prefill计数之和一致；这些不是全场账单或一般性能结论。CPU四线程、nice19，沿用64GiB可用内存准入/48GiB地址空间/36GiB RSS上限。服务退出0、无强制回收，端口关闭、原生子进程消失，最终未发现本次拥有的worker/verifier。完整数据库、对话、权重、headers和worktree不公开。

[证据、日志与逐文件哈希](../evidence/adk-focused-cpu/README.md)保留全部失败。下一步应验证“完整文件清单下的任务级工具裁剪是否减少目录遍历”，先定义契约和对照，再做新试验；目前不能宣称有效。本轮没有改worker核心，也没有重复模型试验、100项回归或参考恢复场景。

## 独立复现入口

复用已安装的独立worker环境、固定ADK测试环境、模型及原生后端，先核对协议中的哈希。不要覆盖旧运行目录。模型准备方法见[既有原生CPU说明](native-cpu-pilot.md)；本轮没有重新下载、转换或全局安装依赖。ADK仓库必须包含任务固定的c81876a提交；测试命令会核对worktree内的生产导入与原版测试哈希。

第一个终端运行服务，metadata目录使用新路径：

```sh
/path/to/worker-env/bin/python benchmarks/serve_llama_cpu.py \
  --server /path/to/llama-server \
  --model /path/to/model-q4_k_m.gguf \
  --manifest /path/to/native-manifest.json \
  --library-dir /path/to/runtime-libs/lib \
  --output /path/to/new-metadata/service \
  --port 18848 --threads 4 --alias agentlab-qwen3-4b \
  --wall-seconds 2400
```

健康检查返回200后，在第二个终端设置当前源码路径与ADK验证环境；local-state和local-scratch必须是已存在的、本机准入文件系统上的私人目录。输出trial子目录必须不存在：

```sh
CUDA_VISIBLE_DEVICES= TMPDIR=/path/to/local-scratch \
AGENT_LAB_MODEL_URL=http://127.0.0.1:18848/v1 \
PATH=/path/to/adk-env/bin:$PATH PYTHONPATH=/path/to/AgentReliabilityLab \
/path/to/worker-env/bin/python benchmarks/single_model_trial.py \
  --repo /path/to/adk-checkout \
  --task tasks/adk-artifact-delete-model-focused-cpu.json \
  --protocol benchmarks/adk_focused_cpu_protocol.json \
  --output /path/to/local-state/trial
```

任务结束后，在第一个终端用Ctrl+C停止自己启动的launcher，让其清理拥有的原生子进程，并检查shutdown记录与端口关闭。本次记录由私人调度器自动执行这些生命周期步骤；公共入口使用相同任务、源码哈希、限制和验证程序，但不同主机负载或采样实现不保证复现同一条模型轨迹。不得用新源码替换协议固定文件而继续声称同一次复现。
