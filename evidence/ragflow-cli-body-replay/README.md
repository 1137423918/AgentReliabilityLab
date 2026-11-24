# RAGFlow CLI JSON请求体重放 · 2026-11-25

[正式PR #22752](https://github.com/infiniflow/ragflow/pull/22752)修复CLI benchmark在服务端关闭连接后重复发送JSON的问题。上游基线`8c68034679bf3f5aa6ad5d14ce3899b8915db1ea`，提交`e26909ee6cc0946fe2dfbbfc8bbabf6311bc1b5a`；仅两个Go文件，生产代码增加6行，未改依赖、接口或其他历史实现。当前为开放、非草稿、未合并，[状态快照](pr-state.json)不代表实时CI结论。

## 复现与修复

真实`httptest` TCP服务在响应中返回`Connection: close`。三次POST、PUT、PATCH各自只成功一次、失败两次：同一个请求体已读完，新连接不会通过Go的旧连接重试路径自动重建正文。修复在后续迭代前调用已有`GetBody`，每次发送相同JSON，保留原有鉴权、其他头、返回最后响应及成功/失败计数。

[同字节对照](validation.json)：原版三个关闭连接子例失败，三个keep-alive子例、应用错误计数和无正文POST通过；修复后3项新增顶层控制及其中6个方法/连接子例通过。子例与父测试不相加成独立案例。完整`internal/cli/...`选择通过51个顶层测试，209是含嵌套子例的通过事件数；三个包没有测试文件，没有跳过单独测试。[事件口径](full-cli-event-details.json)另列。

初始keep-alive-only复现全部通过，**没有证明所有连续请求都会失败**。该[原始结果](initial-keepalive-baseline.json)和[日志](logs/initial-keepalive-baseline.log)保留，随后根据Go真实传输行为增加正常的关闭连接场景，并重新固定输入；没有把原来的通过结果改写成失败。原始源码见[Go 1.27.4 transport](https://github.com/golang/go/blob/go1.27.4/src/net/http/transport.go)。

## 执行范围

所有安装、格式检查、构建与测试在Linux服务器完成，使用原仓库`bash build.sh --cpp`及`bash build.sh --test`，未提取或重写被测函数规避原生依赖。候选回归与完整CLI命令附带的model-free native单元层均通过；未跑模型集成层、在线RAGFlow服务或完整仓库CI。全程GPU、模型生成与嵌入调用均为0。

Go1.27.4、Clang/LLD20.1.8、CMake4.4.5、GCC14头文件、PCRE2 10.40与固定原生库均位于独立目录。12个官方AlmaLinux RPM签名核对后仅提取文件，不安装系统包或执行RPM脚本；四个原生发布资产与官方release摘要相符。PCRE2旧发布无官方摘要，记录实际下载哈希，不冒充官方校验值。仅构建CPU分词器，未调用会下载模型权重的完整依赖脚本。[环境](environment.json)、[资产来源](assets/native-source-downloaded.json)和`protocols/`固定实际输入。

最终配对配置168.504秒；原版67.703秒、候选74.928秒、完整CLI10.794秒，含编译与wrapper工作，并非业务请求延迟。两个空闲逻辑CPU、nice19，候选阶段树峰值约2.04GiB。初次网络准备因官方Go代理不可达而终止，保留[记录](network-preparation-failure.json)，之后使用原仓库默认代理；不把环境失败算成缺陷复现。

[私有冻结回执](private-archive-receipt.json)绑定82文件、1,462,094字节和5个终态配置，所属子进程为0；旧已关闭账本与归档哈希不变。未重复归档模型、Go工具链、原生二进制或模块缓存。`patch-inputs.json`是运行前冻结清单，其准备时状态不代替`validation.json`执行结果。公开的是源码补丁、归一化日志及元数据，不含凭据、数据库或论文原文。

本修复由Codex辅助实现和服务器验证。上游首次核查没有当前提交的Actions运行记录、审查意见或未解决线程，不能宣传为上游CI全绿或已合并。
