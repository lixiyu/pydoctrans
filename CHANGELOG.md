# Changelog

## [1.0.0] — 2026-07-10

### v0.1 — 核心引擎
- LO 引擎：`subprocess` 封装 LibreOffice headless 转换
- 沙箱隔离：每次转换独立 HOME 目录，支持真正并行
- 并发控制：`threading.Semaphore` 限制 LO 进程数
- 环境检测：自动发现 Linux/macOS 下 LO 安装路径

### v0.2 — HTTP 服务
- FastAPI 服务：`POST /convert`、`GET /health`、`GET /engines`
- CLI 转换：`python -m pydoctrans convert input.docx output.pdf`
- CLI 服务：`python -m pydoctrans serve --port 8000`
- Docker 镜像：Ubuntu + LO 26.2.3 开箱即用
- 公共 API：`from pydoctrans import convert`

### v0.3 — 可观测性
- Prometheus 指标：`GET /metrics`（请求数、耗时、槽位、文件大小）
- 优雅关闭：SIGTERM → 拒新请求(503) → 等在途 → 清理
- 文件大小限制：`MAX_FILE_SIZE`（默认 50MB）

### v0.4 — 扩展性
- 回调钩子：before/after 转换钩子
- `ConversionContext`：贯穿转换流程的上下文对象
- after 钩子容错：单钩子失败不阻断其他钩子，错误聚合抛出
