# 可部署的 MCP 报告证据服务

基于固定 MCP2.3.0 / MCP-types2.3.0 / HTTPX2 2.16.2，把已有报告读取与事实核对暴露为6个真实MCP工具。MCP负责发现/消息传输；审计上下文、回执和额度是本项目实现。固定8份公开报告，业务JSON最多8KiB、请求体最多16KiB，默认loopback单worker，无模型调用。

完整服务器130项通过、零跳过（新增6项包含在内）；另6场真实SDK/TCP控制通过，不累加。覆盖正确读取与验证、不同上下文回执隔离、未知路径/无效pointer/布尔伪造/HTTP413、六并发争最后一次额度（1成功/5工具级拒绝）、重连不重领额度、真实读完但回复被扣留后的取消与重新读取。

SDK追踪57次HTTP尝试、57次收到响应头、56份完整回复；被扣留后取消的一份没有完整响应体，不能算57次成功。另有独立超限HTTP413；健康检查和测试gate控制HTTP不计入57。MCP业务拒绝可能仍是HTTP200，要检查isError。

两次服务生命周期事先声明：普通CLI服务后启动测试fixture，旧进程句柄在新进程无效。两个服务均按计划SIGTERM退出，returncode=-15，未强杀；端口关闭、观察自有进程残留0。fixture只在benchmark里，扣留真实读结果正文后再由客户端取消，没有伪造MCP/报告回复。

- [完整汇总与限制](report.json) · [六场控制、全部SDK请求/回复](network/report.json)
- [取消前后计数与重新读取](network/cancel_unknown.json) · [并发额度](network/concurrent_cap.json) · [回执隔离](network/receipt_isolation.json)
- [完整130项日志](normal/full-core.log) · [6项定向检查](normal/focused.log) · [服务器及控制器终态](normal/run-report.json)
- [固定8报告目录](corpus/catalog.json) · [实际测试源码](tested-source) · [原始/公开工件SHA](artifacts.json)
- [依赖锁](bootstrap/uv.lock) · [PyPI制品信息](pypi-intake.json) · [已部署接口与使用](../../docs/mcp-evidence.md)

句柄是可分享的审计能力，不是用户认证或SDK传输会话ID。进程内状态有TTL，不承诺掉电/多机恢复；重启后旧句柄失效，重连复用同一有效句柄则保留计数。业务操作额度不限制所有HTTP流量，也不是模型次数/费用预算；新上下文不应重置调用方模型账本。

回执证明调用方持有某次读取结果，不证明理解了内容；事实校验不验证任意verdict真假或自由文字语义。原目录仍是旧116快照，新130回归不倒填。所有记录中的测试句柄/回执在服务结束后均失效；它们不是账号凭据。只归一化元数据/日志/控制脚本私人路径，业务JSON、wire、目录和测试源码保持原字节。账本/执行身份取原始协议SHA，公开归一化协议SHA另列。

SDK上游只读；没有新建issue/comment/PR，也不声称通过SDK全部conformance/跨平台测试。初始Ruff未使用导入诊断作为准备记录保留，不改称运行期失败。旧模型/论文/PR证据均保持原样。
