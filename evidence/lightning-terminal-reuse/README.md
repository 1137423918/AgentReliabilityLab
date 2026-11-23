# Agent Lightning rollout ID 复用回归

2026-11-23，CPU-only，固定上游 `2070bad5113e52f1aa2e5bdba822d4b24b197c05`。新 [PR #707](https://github.com/microsoft/agent-lightning/pull/707) 提交时为 open/draft，HEAD `5d3342c07d849d4ce9c836e14d62d1ae8d91d9c9`。**原版四个状态回归失败；候选相关集合53项通过，另完成相同源码的静态检查。未运行 RL / GPU / 全部 CI。**

删除已完成 rollout 后复用 ID，会让原完成日志位置查询到替代任务。候选保留空位与游标，通过 ID → 日志位置索引在删除时撤销旧引用。[问题、取舍与命令](../../docs/lightning-terminal-reuse.md)。

| 证据目录 | 实际结果 |
| --- | --- |
| [original](original/run-report.json) | 原生产代码，5项聚焦4失败/1通过；排除四个新失败状态后的相关集合49通过；监督器按预先声明的复现预期退出0 |
| [candidate-v1](candidate-v1/run-report.json) | 聚焦5、相关53通过；Ruff因两行测试超长失败，整场退出2 |
| [candidate-v2](candidate-v2/run-report.json) | 修正测试排版；执行器的相对Git路径在测试前失败，退出2 |
| [candidate-v3](candidate-v3/run-report.json) | 聚焦5、相关53、Ruff和格式通过；Pyright自动Node引导失败，尚未进行类型分析，退出2 |
| [validation-v4](validation-v4/run-report.json) | 不重跑测试，核对并沿用V3字节相同源码；固定Node后Pyright与版权头脚本通过，退出0 |

全部监督器已终止、自有子进程为0、各自冻结源码未改变。V1/V2/V3 的失败始终保留；V4 绑定的是 V3 原始报告SHA，不补写前场成功。原版监督器返回0表示成功复现了声明的4个失败，不表示原生产代码通过这些回归。

## 核对入口

- [原版聚焦 XML](original/focused-original.xml)：5条testcase，4个failure；[原版相关 XML](original/related-original.xml)：49通过。
- [候选聚焦 XML](candidate-v3/focused-candidate.xml)：5通过；[候选相关 XML](candidate-v3/related-candidate.xml)：53通过、无错误或跳过。聚焦5项包含在53项中，不相加。
- [最终 Pyright 日志](validation-v4/pyright-selected.log)：四个修改文件0错误/0类型警告；[Node身份](validation-v4/node-identity.log)及[官方归档清单](validation-v4/node-manifest.json)。
- [四文件补丁](fix.patch)与[candidate-source](candidate-source/agentlightning/server/routes/rollouts.py)保留最终源码；[原版回归测试](original/test_endpoints.py)与最终测试仅排版不同，AST一致。
- 每个目录包含执行前固定的`protocol.json`、控制器及日志；原版协议绑定64个复制文件，Python项目与锁均来自固定上游，未安装VERL/Torch。测试使用上游FastAPI TestClient和模拟外部HTTP响应，不是模型或线上服务成绩。
- [artifacts.json](artifacts.json)记录55项payload / 245,173字节的公开SHA和尺寸；其中48项是从服务器传回的原始报告、协议、日志、XML和执行器，原始总181,984字节，规范化后180,619字节。另七项为原MIT许可证、实际补丁、原版测试和四份最终源码。

只规范化私有服务器根目录、临时工作目录及XML的hostname；原/公开SHA分别列明。协议中的执行器SHA、V4绑定的原V3报告SHA应与清单的`original_sha256`比较，不能误与规范化后的文件SHA比较。原版与候选协议没有使用结果调整回归断言；V2仅测试排版变化，AST核对保留。

日志中`test-secret-key`和随机rollout ID来自上游公开测试fixture，不是用户凭据或真实模型输入。没有导出环境、模型、权重或服务器连接资料。版权保留上游 [MIT LICENSE](UPSTREAM_LICENSE)。个人主页与历史PDF未更新。
