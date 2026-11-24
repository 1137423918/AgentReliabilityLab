# LightRAG 依赖维护的实际输入与验证

[项目说明](../../docs/lightrag-dependency-upgrade.md) · [工作台报告](workbench/reviews/lightrag_1_5_8.md) · [正式 PR #4647](https://github.com/HKUDS/LightRAG/pull/4647)

`corpus` 是固定 v1.5.8 的准备阶段报告和指向独立已发布提交的来源目录。报告中的 `compatibility_tests_run=false`描述准备阶段；实际后续测试单独记录于 `compatibility`，绑定同一发布版源码。`main-validation`是不同的当前主线源码的独立验证，不把发布版结果冒充 PR 基线结果。

`scans` 只发布去除公告叙述、归一化来源路径的 OSV 字段投影，保留原始扫描 SHA256；完整扫描、冻结数据库、关闭后的 SQLite 状态、成功/失败日志保留在服务器只读归档。`runs` 为选定字段且路径归一化的运行回执，不是私有原始控制协议。runtime-proof 保留原始哈希并显式标记路径归一化。JUnit 和源码清单保留原始字节以核验绑定；测试主机名不是可复用连接凭据。

`candidate` 包含 uv 原始候选锁文件、未变依赖声明及上游 MIT LICENSE。`input-provenance.json`记录来源 commit、学术组织自述、观察到的星数；不推断团队人数。`new-pr-action-jobs.json`记录 UTC 14:39 的 5 个审批门禁、零任务；不是 CI 成功。

初次 Git 路径错误发生在扫描前；首次安装超时发生在测试前；首次主线拉取 HTTP/2 失败发生在环境建立前。旧失败回执保留，后续针对环境/传输的继续执行单列。总共两次实际扫描；新模型调用和 GPU 使用均为零。未启动暂缓的 GPU 研究。
