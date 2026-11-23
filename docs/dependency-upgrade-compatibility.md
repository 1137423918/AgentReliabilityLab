# FastMCP 升级候选的配对鉴权兼容性验证

此前[依赖审查应用](dependency-upgrade.md)只完成锁文件解析和固定漏洞库复扫。本次继续检验历史 FastMCP 2.12.4 候选：在两个独立项目环境中，使用原始锁文件和已保存的候选锁文件，执行同一份上游鉴权相关测试。

| 实际环境 | Authlib | joserfc | 相同测试清单 |
| --- | --- | --- | --- |
| 原始锁文件 | 1.6.1 | 未安装 | 279 通过，0 失败／错误／跳过 |
| 候选锁文件 | 1.9.10 | 1.8.0 | 279 通过，0 失败／错误／跳过 |

这证明该候选在本次鉴权测试范围内兼容；两组使用同一批279项测试，不能相加成558个独立场景。实际环境同时增加了joserfc，结果不能归因于仅改变Authlib。

## 固定输入与执行

源码固定为 `b96e6ebbb269a241801554383671ba9f2876901e`。两个完整 Git 克隆均检出这一提交，只替换候选的 `uv.lock`，原始 `pyproject.toml`、源码、测试和快照不修改。614份跟踪文件的逐文件哈希在测试后复核；两组只有锁文件不同。原始和候选锁文件及完整文件清单随证据保存。

服务器 Python 3.11.4、pytest 8.4.1。每个新环境分别执行 `uv sync --frozen --all-extras`，保留默认dev依赖组；不重新解析锁文件或替换包。安装可以访问注册表并执行隔离构建元数据。安装后的实际发行包清单显示，两个环境只有Authlib版本和新增joserfc不同。

选择范围在运行前固定：`tests/server/auth`、`tests/client/auth`、HTTP bearer/backend与auth middleware、server auth integration、deprecated bearer provider。沿用上游 `not integration and not client_process` 标记选择、5秒超时和禁用快照写入设置；两组实际选中node ID完全一致。覆盖JWT验证、OAuth/OIDC代理、重定向、令牌到期及多个鉴权提供方，包括模拟提供方的本机OAuth流程。测试期间对外部地址的socket connect/connect_ex被拒绝，允许本机回环；这不是生产云服务验收，也不宣称完整网络沙箱。

可在分别装好原始与候选锁文件的独立检出目录中复核相同选择：

```sh
python -m pytest -m 'not integration and not client_process' \
  tests/server/auth tests/client/auth \
  tests/server/http/test_bearer_auth_backend.py \
  tests/server/http/test_http_auth_middleware.py \
  tests/server/test_auth_integration.py \
  tests/deprecated/test_bearer_auth_provider.py
```

实际运行器、两项环境/结果采集辅助代码、安装日志、完整测试日志、JUnit XML与node ID／各阶段结果保存在[证据目录](../evidence/fastmcp-authlib-compatibility/README.md)。运行器使用2个新准入CPU、nice19、16GiB地址空间与8GiB自有RSS上限；原始输入保持不变，终态自有进程为零。首次准备因执行器要求Git绝对路径而在克隆前失败，未安装或执行测试；原失败记录保留。

## 结果边界

本次覆盖鉴权相关测试，没有执行完整仓库CI、多平台验证、pre-commit或发布审批。候选保留Authlib JOSE/httpx接口等弃用警告，日志未过滤。此前固定漏洞库仍记录16个受影响registry resolutions，本次未重新扫描，不把兼容性通过解释为所有依赖安全。没有新增模型调用，也没有据此重跑已知模型任务来提高成绩；历史发布快照不代表项目当前部署。
