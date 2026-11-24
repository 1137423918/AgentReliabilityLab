# 阅读页浏览器验证环境

这是可选的开发验证环境，日常报告导出及打开HTML无需安装它。HTML由Python标准库生成，沿用[研究助手环境](../research-assistant/README.md)；本目录只提供固定的Playwright版本与服务器生成的冻结依赖锁。

在具备[Playwright受支持系统依赖](https://playwright.dev/python/docs/browsers)的Linux服务器上：

```sh
uv sync --project extras/research-view-checks --frozen --no-install-project
PLAYWRIGHT_BROWSERS_PATH=/path/to/browser-cache \
  extras/research-view-checks/.venv/bin/python -m playwright install --only-shell chromium
```

`benchmarks/research_view_browser.py`接收由`benchmarks/research_view_flow.py`生成的应用输出目录和新的检查输出目录。前者包含四个已关闭的真实运行报告及独立的注入/缺失记录夹具；检查脚本不会恢复图、启动模型或连接MCP。不要将缺失记录夹具算作第五个真实模型任务。

仓库本轮实际使用AlmaLinux服务器的独立库目录与私有字体配置完成验证，没有安装系统依赖；它不是官方支持平台的通用安装方案。[环境范围、保留的失败和实际浏览器结果](../../evidence/research-view/README.md)单列。
