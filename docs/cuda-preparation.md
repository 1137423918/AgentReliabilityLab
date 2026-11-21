# CUDA运行时的CPU准备

这是Agent实验部署准备，不是模型修复实验。原服务包没有CUDA后端；本次用服务器CPU编译独立依赖，GPU推理尚未测试。

固定源码归档到`4783b1145c7073bb809f4c282ff4853cbfe42954`，41个工具链包逐份校验SHA256，再离线安装。四个逻辑CPU/nice19下，初次本机配置18.123秒退出0，编译1325.688秒在最后的OpenMP依赖链接处失败；补充依赖搜索路径后，单独配置2.051秒、增量链接2.05秒退出0。4496份源码前后匹配。增量链接耗时不是干净构建耗时。CPU解析ELF确认sm_86和后端注册符号，未执行新服务。

## 复现材料

先从[上游固定归档](https://codeload.github.com/ggml-org/llama.cpp/tar.gz/4783b1145c7073bb809f4c282ff4853cbfe42954)获取源码并核对公开SHA256。按[工具链锁](../evidence/cuda-build/toolchain-lock.json)核对41份归档、安装到隔离目录；实际使用CMake3.31.8、GCC/G++13.4.0、Ninja1.12.1和系统CUDA12.9.86。当前产物只面向实查的RTX3090/compute8.6，不能用于P100。

本次完整命令数组保存在[实际启动记录](../evidence/cuda-build/link-correction/started.json)，[选定配置](../evidence/cuda-build/link-correction/configuration.json)来自生成后的CMakeCache。路径已用占位符替换，按自己的源码、工具链和新建输出目录还原；不要直接把带尖括号的记录当作shell命令执行。最终可执行文件链接显式添加`-Wl,-rpath-link,<toolchain-prefix>/lib`，从已校验的工具链查找libgomp.so.1，不允许未解析符号。构建目标是llama-server，显式GGML_CUDA=ON、GGML_NATIVE=OFF、CMAKE_CUDA_ARCHITECTURES=86、动态后端；关闭NCCL/UI下载/OpenSSL。CPU编译不需要分配GPU。

## 资源与失败记录

先前共享NFS上的配置触发300秒上限，未进入CUDA编译；失败及前后源码哈希保留。随后源码/工具链/构建/TMPDIR移到私人本机ext4；同归档及包集合不变，源码核对阶段加120秒上限。两个尝试有缓存和存储等差异，不作单因素性能比较。

Ninja创建独立编译进程组，原父组RSS并非全树内存。从343.86秒起补充完整进程树监控，并沿用原2400秒编译期限。早期缺少连续树覆盖，不能报告全场内存峰值；该段树监控没有触发限制或发送清理信号；不能据此声称强制清理分支经过测试。详见[完整证据与限制](../evidence/cuda-build/README.md)。这些是操作层检查，106项Agent核心回归没有重跑或新增计分。

## 下一步

有合适空闲的8.6架构GPU后，另立协议验证动态加载、实际卸载、模型身份和HTTP工具往返，再运行受保护维护任务。当前没有GPU运行、加速、成功率或自主修复成绩；私有临时路径的可迁移性也未验证。现有CPU包和历史模型失败保持独立。

## 后续GPU接口验证

单张RTX3090已实际加载33/33层并完成三次HTTP回复；两个受约束工具/JSON检查通过，原样文本含空标签，原判失败保留。完整[协议、结果和先前启动失败](../evidence/gpu-smoke/README.md)另存；不计自主修复或新的核心测试。
