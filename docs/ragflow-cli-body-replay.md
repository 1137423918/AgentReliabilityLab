# RAGFlow CLI：服务端关闭连接后的JSON连续请求

[PR #22752](https://github.com/infiniflow/ragflow/pull/22752)已正式提交，开放待审、未合并。需求来自CLI benchmark的真实请求路径：一次发送成功后，服务端若关闭连接，后续迭代仍需发送相同JSON，而不是把空正文传给新连接。

修复位于`internal/cli/http_client.go`，后续迭代用`GetBody`取得独立正文，生产代码增加6行。真实HTTP服务器对照覆盖POST/PUT/PATCH、keep-alive与`Connection: close`、请求头、最后响应及业务计数；原版只在关闭连接的三个子例失败，每例成功1/失败2，候选通过。初始仅keep-alive测试在原版全部通过，保留为限定适用范围的证据。

服务器通过原有`build.sh`执行，3项新增顶层控制通过，完整CLI与filesystem包共51个顶层测试通过，wrapper附带的无模型原生单元层通过；子例范围重叠，不累加为新总分。Go格式检查通过。两个CPU、低优先级，GPU/模型生成/嵌入调用为0；未运行在线后端、模型集成测试或全仓CI。

[复现、日志、源码输入与边界](../evidence/ragflow-cli-body-replay/README.md) · [修复补丁](../evidence/ragflow-cli-body-replay/fix.patch) · [回归测试补丁](../evidence/ragflow-cli-body-replay/test.patch)。这是开源维护贡献，可与MCP鉴权/连接生命周期案例共同展示问题复现和工程取舍，不单独包装为已上线Agent应用。
