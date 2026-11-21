# 本机 MCP 报告证据服务

面向多个Agent客户端共用同一批实验报告的情况：提供固定来源读取，分开维护每次审计的读数、回执和操作额度。MCP2.3.0本身提供协议和工具发现；本项目的`EvidenceService`实现独立上下文与回执核对。不会调用模型，原维护worker的依赖与模型额度账本不变。

## 下载启动包，脱离源码运行

现在提供[独立启动包](../artifacts/agentlab-evidence-0.1.0-starter.zip)、[原始wheel](../artifacts/agentlab_evidence-0.1.0-py3-none-any.whl)和[完整性收据](../artifacts/agentlab-evidence-0.1.0-starter.json)。解压启动包后不需要项目checkout、Deep Agents、LlamaIndex、模型权重或模型API key。使用已有Python3.11及uv，在获准服务器的解压目录执行：

```sh
uv sync --python python3.11 --project runtime --frozen \
  --no-install-project --no-default-groups
uv pip install --python runtime/.venv/bin/python --offline --no-deps \
  ./agentlab_evidence-0.1.0-py3-none-any.whl
uv pip check --python runtime/.venv/bin/python
runtime/.venv/bin/agentlab-evidence --root reports \
  --manifest reports/catalog.json --check
runtime/.venv/bin/agentlab-evidence --root reports \
  --manifest reports/catalog.json --port 18856
```

冻结依赖同步会从PyPI下载；随后安装本项目wheel时使用offline/no-deps。`--check`检查每份报告的固定哈希后退出，不监听端口；正常启动也会先检查。`python -m agentlab_evidence`为相同安装入口。停止前台服务即可结束；不会建立公开监听或网站在线后端。

启动包内是九份真实公开报告的历史目录，来源固定在`cb67290a9ced302834f8458adf94b78bc64246bd`，不是最新GitHub PR状态或本轮130项结果。`CHECKSUMS.json`逐项记录payload字节；外层zip SHA256为`654fd47fa0c494fb5d032d7b5521acbdc9d117a4b430e2826984995470615347`，wheel SHA256为`1a79b4535dae12717133a4a07f61f63bb52d217d86b994d9d4c034393105b720`。这是完整性元数据，不是发布者认证。

可用自有目录和manifest替换报告：`version:1`、`source_commit`、`source_base`及`reports:[{id,path,description,sha256}]`，示例见启动包`reports/catalog.json`。每份文件必须为根目录内的相对JSON路径，最多32份、每份最多262144字节；报告symlink不接纳。目录由可信操作者配置，不要加入连接文档、凭据或活跃任务状态。

本次确实安装/执行了9033字节wheel：新的最小锁定环境、源码目录之外、隔离Python `-I`，`agent_lab`/`benchmarks`/Deep Agents/LlamaIndex均不能导入。八项安装后控制通过，覆盖CLI/模块入口、篡改报告启动前拒绝、真实回执核对、串用回执/错误JSON类型拒绝、运行中哈希复查、计划重启使旧能力失效及额度耗尽后关闭。两个服务SIGTERM(-15)结束、端口关闭、自有进程归零。共享导入调整后原130项完整回归再次通过、零跳过，没有增加测试函数；八项控制与其分开。原core/builder环境版本不变，新runtime仅在冻结依赖上安装本项目wheel。

三个规范模块字节原样进入独立`agentlab_evidence`命名空间，没有通过源码路径别名导入旧环境。最终启动zip将实际测试的wheel、相同报告和未改依赖锁逐项打包并核对字节，未为它再完整重跑启动流程。[安装证据和全部边界](../evidence/evidence-package/README.md)。只实测Linux/Python3.11.4，不宣称其他系统、完整MCP合规、公网认证或真实模型成绩；没有上传PyPI。

## 从源码启动

以下在服务器的源码checkout根目录运行，使用独立环境：

```sh
uv sync --project extras/mcp-evidence --frozen --no-install-project --no-default-groups
extras/mcp-evidence/.venv/bin/python -m benchmarks.mcp_evidence_server \
  --root evidence/mcp-evidence/corpus \
  --manifest evidence/mcp-evidence/corpus/catalog.json --port 18856
```

只绑定`127.0.0.1:18856`，MCP路径`/mcp`、健康路径`/health`。支持该协议版本的本机客户端可连接；没有公网发布或用户认证功能。使用同一独立Python环境的最小客户端：

```python
import asyncio
from mcp import Client

async def main():
    async with Client("http://127.0.0.1:18856/mcp", cache=None) as client:
        tools = await client.list_tools()
        print([t.name for t in tools.tools])
        context = (await client.call_tool("begin_audit", {})).structured_content
        audit_id = context["audit_id"]
        reply = await client.call_tool("read_report", {
            "audit_id": audit_id, "report_id": "core_current",
            "pointers": ["/full_suite_passed"],
        })
        if reply.is_error:
            raise RuntimeError(reply.content)
        print(reply.structured_content)
        await client.call_tool("close_audit", {"audit_id": audit_id})

asyncio.run(main())
```

六个工具：`begin_audit`创建上下文；`list_reports`列可信目录；`read_report`读取1–8个JSON pointer并返回`receipt`和`report`；`verify_assessment`接收同一上下文的回执及原事实schema；`audit_status`查看已用计数；`close_audit`释放上下文，额度耗尽也可关闭。MCP返回HTTP200仍可能`is_error=True`，不能只检查HTTP状态。

`verify_assessment`需要`{audit_id, assessment:{claim_supported,explanation,facts,citations}, receipts:[...]}`。facts为`{report_id,pointer,value}`、citations为`{report_id,sha256}`。值、精确类型、来源哈希和读取谱系沿用既有EvidenceCatalog，还必须由本次提交的回执覆盖。返回`evidence_verified=True`只代表这些事实检查通过，`verdict_truth_verified=False`和`free_prose_semantics_verified=False`明确保留。

默认最多32个活跃上下文、每个600秒绝对TTL、16次有代价业务操作及8次已发回执的读取。业务JSON最多8192字节（目录/读取内部7168），MCP协议封装可能更大；请求体上限16384字节。参数层先拒绝的请求、状态/关闭不记作昂贵业务操作；这不是全HTTP限流器。并发在同一锁内扣额度，失败尝试不退款。失去网络回复时，服务端可能已读完并扣额，调用方没有收到的回执不能用于核对；重新读取产生新回执，也再占一次操作。

句柄是随机生成的进程内能力，持有人可以主动分享并在重连后继续使用；不是客户端身份。TTL在后续访问/创建时清理，数量始终有界。进程退出或重新部署使旧句柄失效，不声称持久恢复、工具恰好一次、跨机共享或恶意操作者防护。固定目录及文件由可信操作者配置；服务会拒绝运行中目录字节改变及报告哈希不符。

服务器实测完整130项通过、零跳过（新6项已包含），另6场真实MCP/TCP控制通过。测试fixture扣留实际完成的读取正文再取消，未提供假工具回复。SDK追踪57尝试/56完整正文，另有HTTP413；2个预声明生命周期SIGTERM(-15)退出、未强杀、端口关闭。所有runtime都在服务器，零模型/GPU调用。[完整证据](../evidence/mcp-evidence/README.md)。

依赖固定PyPI MCP2.3.0及hash锁；上游main77001c...仅用于API/贡献政策参考，不等同wheel构建revision。本轮不修改或向上游投稿，遵守其issue资格和人工参与要求。[官方SDK](https://github.com/modelcontextprotocol/python-sdk) · [2.3.0制品](https://pypi.org/project/mcp/2.3.0/)。
