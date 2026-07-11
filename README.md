# pydoctrans

把 LibreOffice 驯服成可靠的服务端文档转换引擎。

`pip install pydoctrans`，三行代码把 Word/Excel/PPT 转成 PDF。**不会卡死、不会僵尸进程、不会一个文件拖垮整个服务。**

---

### 如果你在服务端用过 LibreOffice，这些场景你大概率见过

```
# 同时来两个请求，第二个悄悄丢了——LO 单实例锁，根本不能并行
# 文件大一点就卡住，没超时，没响应，整个队列堵死
# 和 CUDA / 其他系统库冲突，莫名其妙 Signal 11 崩溃
# 僵尸进程堆了几十个，没人回收
# 并发一多直接 OOM，一个 soffice.bin 吃 1G 内存
```

### pydoctrans 怎么解决的

| 你的痛点 | pydoctrans 的做法 |
|----------|------------------|
| 不能并行 | **HOME 目录隔离**：每次转换独立 `~/.config/libreoffice`，管道名不同，真正并行跑 |
| 卡死没响应 | **请求级超时**：`subprocess.run(timeout)` → SIGTERM → SIGKILL → waitpid，不留僵尸 |
| 库冲突崩溃 | **LD_LIBRARY_PATH 锁定**：LO 只加载自己 `program/` 下的 `.so`，不碰 CUDA 或系统库 |
| OOM | **Semaphore 槽位控制**：`LO_MAX_CONCURRENT` 限制同时在跑的 LO 进程数 |
| 一个坏文件堵全部 | **独立进程 + 超时兜底**：坏文件超时被杀，不影响其他请求 |
| 关闭丢任务 | **优雅关闭**：SIGTERM → 拒新请求 → 等在途完成 → 清理沙箱 |

### 可靠性的底线

- **中文字体开箱即用**：Docker 镜像预装 Noto CJK，不再满屏豆腐块
- **文件类型自动检测**：URL 下载的文件没扩展名？读魔术字节，PDF/DOCX/ODT 自己认
- **指数退避重试**：URL 下载失败 1s → 2s → 4s 自动重试
- **孤儿沙箱自动清理**：进程崩溃残留的临时目录，启动时扫描清理

## 快速开始

```bash
pip install pydoctrans
```

```python
from pydoctrans import convert

with open("report.docx", "rb") as f:
    pdf = convert(f.read(), to="pdf", file_name="report.docx")

with open("report.pdf", "wb") as f:
    f.write(pdf)
```

## 特性

- **真正并行**：每个转换独立 HOME 目录，不受 LO 单实例限制
- **超时兜底**：请求级超时，超时即杀，不留僵尸进程
- **库冲突隔离**：LD_LIBRARY_PATH 锁定 LO 自身目录，不与 CUDA 等组件冲突
- **并发槽位**：Semaphore 控制 LO 进程上限，防止 OOM
- **中文字体**：Docker 镜像预装 Noto CJK，中文文档不出乱码
- **文件类型检测**：魔术字节自动识别，无扩展名的文件也能正确转换
- **回调钩子**：转换前/后注入自定义逻辑（校验、水印、上传 S3）
- **HTTP API**：独立微服务部署，Docker 开箱即用
- **Prometheus 指标**：请求数、耗时、槽位利用率实时可观测
- **优雅关闭**：SIGTERM 下等在途任务完成，不丢请求

## 纯 Python，怎么用都行

整项目都是 Python 代码，零二进制依赖，模块边界干净。没有"下载个 Java 服务"、"装个 Go 二进制"这种事。

```
pydoctrans/
├── engine/        ← 转换引擎抽象（加新引擎只需实现 Engine 基类）
├── sandbox.py     ← HOME 隔离，独立模块，可单独拿出来用
├── pool.py        ← 并发控制，Semaphore 封装，不绑死 LO
├── env.py         ← 环境检测，支持 Linux/macOS/手动安装/Snap/Flatpak
├── filetype.py    ← 魔术字节检测，独立可复用
├── hooks.py       ← 回调钩子系统，Protocol 协议，不侵入引擎
├── convert.py     ← 公共 API，三行代码接入
├── server.py      ← FastAPI 服务，可独立部署
└── __main__.py    ← CLI 入口
```

### 五种调用方式，同一套内核

```python
# ① 代码调用 — 嵌入你的 Python 项目
from pydoctrans import convert
pdf = convert(docx_bytes, to="pdf", file_name="report.docx")
```

```bash
# ② 命令行 — 运维脚本、CI/CD
python -m pydoctrans convert report.docx -t pdf
```

```bash
# ③ HTTP 服务 — 跨语言调用（Java/Go/Node 都能用）
python -m pydoctrans serve --port 8000
curl -F "file=@report.docx" -F "to=pdf" http://localhost:8000/api/v1/convert

# 也可以直接给 URL，自动下载后转换
curl -F "url=https://example.com/report.docx" -F "to=pdf" \
     http://localhost:8000/api/v1/convert/url -o report.pdf
```

```yaml
# ④ Docker — 一条命令拉起
docker run -p 8000:8000 pydoctrans

# ⑤ Docker Compose — 生产部署
docker compose up -d
```

不管你是在 FastAPI 项目里当库使、在 Airflow 里用命令行调、还是微服务架构里独立部署，内核完全一样，没学两套东西。

## 使用方式

### 命令行

```bash
# 基本转换
python -m pydoctrans convert input.docx output.pdf

# 指定格式（自动生成输出文件名）
python -m pydoctrans convert input.docx -t pdf

# 启动 HTTP 服务
python -m pydoctrans serve --port 8000
```

### Python API

```python
from pydoctrans import convert, ConversionContext

# 基本转换
pdf = convert(docx_bytes, to="pdf", file_name="report.docx")

# 带钩子
def log_size(ctx: ConversionContext) -> None:
    print(f"输出: {len(ctx.data)} 字节")

pdf = convert(docx, to="pdf", file_name="r.docx", after=[log_size])
```

### HTTP API

```
POST /api/v1/convert       — 上传文件 → 转换 → 返回文件
POST /api/v1/convert/url   — 从 URL 下载 → 转换
GET  /api/v1/health        — 健康检查
GET  /api/v1/engines       — 可用引擎列表
GET  /metrics              — Prometheus 指标
```

```bash
curl -F "file=@report.docx" -F "to=pdf" http://localhost:8000/api/v1/convert -o report.pdf
```

### Docker

```bash
docker build -t pydoctrans .
docker run -p 8000:8000 -e LO_MAX_CONCURRENT=4 -e GRACE_PERIOD=30 pydoctrans
```

## 配置

所有配置通过环境变量控制：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LO_MAX_CONCURRENT` | `10` | 最大并发转换数 |
| `LO_TIMEOUT` | `300` | LO 转换超时（秒） |
| `MAX_FILE_SIZE_MB` | `50` | 上传文件大小限制（MB） |
| `GRACE_PERIOD` | `0` | 优雅关闭最长等待（秒），0=不等待，超时强制终止 |
| `TMP_DIR` | `/tmp` | 沙箱父目录 |

## 回调钩子

```python
from pydoctrans import ConversionContext, convert

def validate_size(ctx: ConversionContext) -> None:
    """转换前校验文件大小。"""
    if len(ctx.data) > 10 * 1024 * 1024:
        raise ValueError("文件超过 10MB")

def upload_to_s3(ctx: ConversionContext) -> None:
    """转换后上传到 S3。"""
    ctx.meta["s3_url"] = s3_client.put(ctx.data)

pdf = convert(
    docx_bytes, to="pdf", file_name="report.docx",
    before=[validate_size],
    after=[upload_to_s3],
)
```

## 路线图

- [x] LibreOffice 引擎 — Sandbox 隔离 + 并发控制 + HTTP API
- [x] 回调钩子 — 转换前/后注入自定义逻辑
- [x] Prometheus 指标 + 优雅关闭
- [ ] **Pandoc 引擎** — 纯文本格式转换（Markdown、LaTeX、reST 等），高语义保真
- [ ] **WeasyPrint 引擎** — HTML/CSS → PDF，适合报表、发票等排版场景

## 许可

MIT License
