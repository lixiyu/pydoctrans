# pydoctrans

Python Document Transformer — 简单、稳定、快速的服务端文档格式转换。

基于 LibreOffice 引擎，支持 Word/Excel/PPT → PDF 及多种格式互转。

## 快速开始

```bash
pip install pydoctrans
```

```python
from pydoctrans import convert

with open("report.docx", "rb") as f:
    pdf = convert(f.read(), format="pdf", file_name="report.docx")

with open("report.pdf", "wb") as f:
    f.write(pdf)
```

## 特性

- **零依赖外部服务**：直接调用 LibreOffice，无需额外部署
- **沙箱隔离**：每次转换独立 HOME 目录，避免命名管道冲突，支持真正并行
- **并发控制**：Semaphore 限制 LO 进程数，防止 OOM
- **超时保护**：请求级超时，避免僵尸进程
- **回调钩子**：转换前/后注入自定义逻辑（水印、加密、上传）
- **HTTP API**：可独立部署为微服务，Docker 镜像开箱即用
- **Prometheus 指标**：请求数、耗时、槽位利用率实时监控
- **优雅关闭**：SIGTERM 下等在途任务完成，拒绝新请求

## 使用方式

### 命令行

```bash
# 基本转换
python -m pydoctrans convert input.docx output.pdf

# 指定格式（自动生成输出文件名）
python -m pydoctrans convert input.docx -f pdf

# 启动 HTTP 服务
python -m pydoctrans serve --port 8000
```

### Python API

```python
from pydoctrans import convert, ConversionContext

# 基本转换
pdf = convert(docx_bytes, format="pdf", file_name="report.docx")

# 带钩子
def log_size(ctx: ConversionContext) -> None:
    print(f"输出: {len(ctx.data)} 字节")

pdf = convert(docx, format="pdf", file_name="r.docx", after=[log_size])
```

### HTTP API

```
POST /convert   — 上传文件 → 转换 → 返回文件
GET  /health    — 健康检查
GET  /engines   — 可用引擎列表
GET  /metrics   — Prometheus 指标
```

```bash
curl -F "file=@report.docx" -F "to=pdf" http://localhost:8000/convert -o report.pdf
```

### Docker

```bash
docker build -t pydoctrans .
docker run -p 8000:8000 -e MAX_CONCURRENT=4 pydoctrans
```

## 配置

所有配置通过环境变量控制：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_CONCURRENT` | `10` | 最大并发转换数 |
| `LO_TIMEOUT` | `300` | LO 转换超时（秒） |
| `MAX_FILE_SIZE` | `52428800` | 上传文件大小限制（字节） |
| `GRACE_PERIOD` | `30` | 优雅关闭等待时间（秒） |
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
    docx_bytes, format="pdf", file_name="report.docx",
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
