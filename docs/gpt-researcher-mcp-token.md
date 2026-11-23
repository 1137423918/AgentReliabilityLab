# GPT Researcher 的 HTTP MCP 令牌连接修复

[正式 PR #2367](https://github.com/assafelovic/gpt-researcher/pull/2367) 修复文档所示 `connection_token` 配置无法发现远程工具的问题。转换器原来把 `token` 直接交给不接受此参数的 LangChain 适配器，实际连接抛出 TypeError，随后被捕获并返回空工具列表。私有研究数据源因而看起来没有工具。

修复将 HTTP 令牌放入 Bearer 授权头，保留其他请求头；调用者显式提供的 Authorization 无论大小写都优先，并且不修改原始配置。WebSocket/stdio 的不支持令牌配置明确报错；stdio 服务使用 `env` 配置凭据。两处文档同步说明 HTTP 范围。上游改动仅四个文件，没有添加依赖。

## 验证

Linux / Python3.12.16、langchain-mcp-adapters0.3.2、MCP SDK1.30.0。11项同字节回归在原版全部失败、修复后全部通过，其中3项启动真实受鉴权的 loopback MCP 服务，分别验证令牌配置、显式标准大小写授权头、显式小写授权头。每项均确认未授权 HTTP 请求得到401，再经真实适配器发现工具并调用。服务和工具内容是测试夹具，没有神经模型、生产端点或付费请求。

相邻 MCP 选择44项通过、2项跳过；仓库完整离线选择1112项通过、17项跳过、4项排除。测试范围重叠，不相加；17项跳过含2项收集阶段跳过。完整收集及库/ASGI导入通过。完整离线选择沿用上游CI排除现场演示模块的命令，并额外安装可选MCP适配器。未安装可选适配器的环境会跳过3项真实连接测试，本次服务器全部实际执行。

[源码、命令、环境约束与完整日志](../evidence/gpt-researcher-mcp-token/README.md)保留失败基线、最终提交哈希、EOF清理的AST等价证明、最终11项重复核对和进程清理记录。全部运行和测试在授权服务器完成，本机仅编辑、Git及元数据检查。

这些证据验证连接和工具边界，不代表模型自主研究、完整报告质量、生产服务行为，或所有支持的Python版本均已验证。服务器测试不替代上游CI/审查；合并状态以PR页面为准。个人主页保持冻结。

当前同一提交的上游 Tests 与 LLM Cost Analysis 均为 `action_required`，job数为0，需维护者批准运行；没有将这一状态写成CI通过。[状态证据](../evidence/gpt-researcher-mcp-token/PR-state.json)。
