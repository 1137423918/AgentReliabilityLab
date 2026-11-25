# 离线引用核查演示

下载同目录的 [source-review.html](source-review.html) 后用浏览器打开，或保存本目录全部文件。无外部服务、字体或模型依赖；页面包含自有示例原文。

三个条目分别演示已提交、未完成和缺失记录。这是**自有合成文本＋脚本化回复**经过实际LangGraph/SQLite终态导出的UI演示，不是新的真实模型任务、论文结论或独立人类核查。初始标注均为待核对/不可核对；可在本地演示编辑、下载备注，再重新打开页面并导入继续。

`source-review.json`绑定原记录与片段指纹，`review-notes.json`是未填写的初始备注，`review-manifest.json`校验三份交付文件。Chrome服务器验证包含1000码点备注、120码点显示名、错版本/重复/混入记录拒收、完整校验后导入、打印、390px手机和无JS阅读。

[实际4个已停止运行、6条私有PDF引用回读与验证边界](../../evidence/research-review/README.md)另列；原论文片段不在此目录发布。[操作说明](../../docs/research-source-review.md)。
