# 独立CPU研究检索包：安装与实际应用验证

已交付[wheel](../../artifacts/agentlab_research-0.1.0-py3-none-any.whl)和[启动包](../../artifacts/agentlab-research-0.1.0-starter.zip)，使用说明见[包文档](../../packages/research-library/README.md)及[应用指南](../../docs/research-library.md)。应用能力仍为检索/版本引用与MCP工具，不是生成式研究Agent。

## 实际安装

从官方PyPI及显式PyTorch CPU索引锁定Linux x86_64 / Python3.11依赖，在新venv中冻结同步，安装torch2.6.0+cpu；没有旧环境PYTHONPATH或系统site-packages复用。只复用Python解释器与已验证模型资产。源模块复制到独立agentlab_research命名空间，wheel不包含Deep Agents、维护运行器、权重、私有索引或连接信息。

- [依赖/CPU版本](runtime.json)、[构建回执](build-receipt.json)、[实际依赖检查](logs/installed-dependency-check.log)、[控制台帮助](logs/installed-cli-help.log)。构建回执中的installed_or_executed=false描述构建时刻；后续安装和执行证据分列，不覆盖原记录。
- [原10项生命周期测试](logs/source-lifecycle-controls.log)、[新增6项导入测试](logs/source-intake-controls.log)：本次范围共16项，不和历史10项累加成26项。
- [首次参数失败](runs/install-v1.json)及[原始错误](logs/first-sync-argument-failure.log)：UV_NO_SOURCES环境项与frozen同步冲突，发生在依赖同步/模型加载之前，0NN。移除冲突后复用同一锁文件，[新安装全部通过](runs/install-v2.json)，没有重新解析锁文件。

## 安装包应用

两份真实维护文档通过原生控制台prepare命令生成清单；check-model完成6份固定资产校验且未改写有效清单；使用已安装CLI的同一main callable和真实E5完成索引/查询；另一个进程重复导入零编码；原生read控制台精确回读引用。之后启动已安装MCP服务，通过实际TCP/Streamable HTTP列举来源、过滤检索、原文引用和无效引用检查。

[应用结果](application.json)、[来源清单](source-provenance.json)、[查询与出处示例](query-example.json)和[控制器终态](runs/application.json)给出范围。模型命令由隔离Python -I调用已安装main，观察器只记录与限额，没有替换或模拟E5输出；prepare/check-model/read/help另走实际生成的控制台入口。源码checkout与Deep Agents无法导入，所有7份wheel模块/数据与规范源码逐字节相同。这里验证接口、安装与来源完整性，带来源过滤的查询不当作无过滤检索准确率。

初次导入2来源/12片段；重复导入零编码。新持久账本上限32前向/128片段输入/8查询，实际6次CPU前向全部完成（12片段＋2查询），无未知、生成模型调用0、GPU0。该账本属于验证工具，不是服务新增的跨重启配额。旧103次CPU账本和24条检索排名未改动或重跑，也没有把CPU构建切换当作同数值环境。

安装控制器396.648秒，其中依赖同步359.182秒；应用阶段56.295秒、峰值归属RSS955,932,672字节。两核CPU/nice19，所有归属进程终止。它们是安装/测试阶段耗时，不是单次在线检索延迟。

## 来源和归档

[冻结协议选定字段](protocols/)保留私有原协议SHA和源码哈希，导出的选定字段不是完整协议原字节；[当前规范源码哈希](canonical-source-sha256.json)绑定实际验证代码。启动包包含wheel、CPU运行时锁与两份自有文档，不包含模型权重。启动包与wheel哈希见[汇总](summary.json)。

[私有归档回执](private-archive-receipt.json)：96份文件、779660字节，包含实际源文件、构建/安装结果、索引和新CPU账本；不重复复制venv/cache或权重。旧599/750/831/84及103CPU记录核验不变，大GPU研究仍未启动。

[收集回执](collection-receipt.json)：导出SHA-256 `c2eec3096e0b80b72f541c88e4202209c5a5430b0bfdbc6e495322d9c20ed951`，70821字节、21个带哈希载荷；[载荷清单](export-manifest.json)可复核全部文件。此README与收集回执在收集后新增，不计入原21载荷。
