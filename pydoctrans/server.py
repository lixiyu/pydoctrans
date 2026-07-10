"""HTTP API 服务。

FastAPI 应用，提供文档转换的 HTTP 接口。
支持 Prometheus 监控和优雅关闭。
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from prometheus_client import generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from pydoctrans.engine.libreoffice import ConversionError, LibreOfficeEngine
from pydoctrans.metrics import (
    file_size_bytes,
    pool_slots_available,
    pool_slots_in_use,
    pool_slots_max,
    request_duration_seconds,
    requests_in_flight,
    requests_total,
)

logger = logging.getLogger(__name__)

# ---- 配置 ----
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50MB
GRACE_PERIOD = int(os.environ.get("GRACE_PERIOD", "30"))  # 优雅关闭等待秒数
TMP_DIR = os.environ.get("TMP_DIR", "/tmp")

# ---- 全局状态 ----
_engine: Optional[LibreOfficeEngine] = None
_shutdown_event = threading.Event()
_active_requests = 0
_active_requests_lock = threading.Lock()


def _get_engine() -> LibreOfficeEngine:
    global _engine
    if _engine is None:
        _engine = LibreOfficeEngine()
    return _engine


# ---- 生命周期 ----


class ShutdownMiddleware(BaseHTTPMiddleware):
    """在关闭期间拒绝新请求的中间件。"""

    async def dispatch(self, request: Request, call_next):
        if _shutdown_event.is_set():
            return Response(
                content="服务正在关闭",
                status_code=503,
                media_type="text/plain",
            )
        # 排除 /metrics, /health, /engines 等非转换端点
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    engine = _get_engine()
    engine_health = engine.health()
    logger.info(
        "pydoctrans v%s starting — engine: %s %s",
        app.version,
        engine_health["engine"],
        engine_health.get("version", "")[:40] if engine_health.get("version") else "",
    )

    # 初始化池指标
    pool = engine_health.get("pool", {})
    pool_slots_max.set(pool.get("max_concurrent", 10))

    # 启动池指标更新线程
    stop_event = threading.Event()

    def _update_pool_metrics() -> None:
        while not stop_event.is_set():
            try:
                engine = _get_engine()
                health = engine.health()
                pool = health.get("pool", {})
                mx = pool.get("max_concurrent", 10)
                av = pool.get("available", mx)
                pool_slots_max.set(mx)
                pool_slots_available.set(av)
                pool_slots_in_use.set(mx - av)
            except Exception:
                pass
            stop_event.wait(5)

    updater = threading.Thread(target=_update_pool_metrics, daemon=True)
    updater.start()

    yield  # 应用运行中

    # 关闭流程
    logger.info("收到关闭信号，进入优雅关闭（grace period: %ss）", GRACE_PERIOD)
    _shutdown_event.set()
    stop_event.set()

    # 等待在途请求完成
    waited = 0
    while waited < GRACE_PERIOD:
        with _active_requests_lock:
            if _active_requests == 0:
                break
        time.sleep(0.5)
        waited += 0.5
    with _active_requests_lock:
        remaining = _active_requests
    if remaining > 0:
        logger.warning("优雅关闭超时，强制终止 %d 个进行中的请求", remaining)

    logger.info("pydoctrans 已关闭")


# ---- 连接池指标上下文 ----


@contextmanager
def _track_request(format: str, file_size: int):
    """跟踪单个请求的指标。"""
    global _active_requests
    with _active_requests_lock:
        _active_requests += 1
    requests_in_flight.inc()
    file_size_bytes.observe(file_size)
    start = time.monotonic()

    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        request_duration_seconds.labels(format=format).observe(elapsed)
        requests_in_flight.dec()
        with _active_requests_lock:
            _active_requests -= 1


# ---- FastAPI 应用 ----

app = FastAPI(
    title="pydoctrans",
    description="Python Document Transformer — HTTP API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(ShutdownMiddleware)


# ---- Exception handlers ----

@app.exception_handler(ConversionError)
async def conversion_error_handler(request: Request, exc: ConversionError) -> Response:
    return Response(
        content=exc.args[0],
        status_code=400,
        media_type="text/plain",
    )


@app.exception_handler(TimeoutError)
async def timeout_error_handler(request: Request, exc: TimeoutError) -> Response:
    return Response(
        content=str(exc),
        status_code=504,
        media_type="text/plain",
    )


# ---- 辅助函数 ----

DOWNLOAD_RETRIES = int(os.environ.get("DOWNLOAD_RETRIES", "3"))


def _attachment_response(data: bytes, filename: str, engine: str, elapsed_s: float) -> Response:
    """构造文件下载响应，安全处理中文文件名。

    HTTP header 只支持 latin-1，含非 ASCII 字符的文件名必须
    用 RFC 5987 的 ``filename*=UTF-8''...`` 格式。
    """
    encoded = urllib.parse.quote(filename, safe="")
    disposition = f"attachment; filename*=UTF-8''{encoded}"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": disposition,
            "X-Engine": engine,
            "X-Elapsed": str(elapsed_s),
        },
    )
DOWNLOAD_RETRIES = int(os.environ.get("DOWNLOAD_RETRIES", "3"))
DOWNLOAD_RETRY_BASE_DELAY = float(os.environ.get("DOWNLOAD_RETRY_BASE_DELAY", "1.0"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "60"))


def _apply_from_format(file_name: str, from_format: str | None) -> str:
    """如果指定了源格式，重命名文件使其带有正确的扩展名。"""
    if from_format is None:
        return file_name
    stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    return f"{stem}.{from_format}"


_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/msword": "doc",
    "application/vnd.ms-excel": "xls",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/vnd.oasis.opendocument.presentation": "odp",
    "text/plain": "txt",
    "text/html": "html",
    "text/csv": "csv",
    "text/markdown": "md",
    "application/pdf": "pdf",
    "application/rtf": "rtf",
}


def _infer_filename(url: str, headers: dict[str, str], content_type: str | None) -> str:
    """从 HTTP 响应中推断合理的文件名。

    优先级：Content-Disposition > URL path > Content-Type > 随机名
    """
    import cgi

    # 1. Content-Disposition: attachment; filename="report.docx"
    cd = headers.get("Content-Disposition", "")
    if cd:
        _, params = cgi.parse_header(cd)
        fname = params.get("filename", "")
        if fname and "." in fname:
            return fname

    # 2. URL path
    path = urllib.parse.urlparse(url).path
    name = Path(path).name
    if name and "." in name:
        return name

    # 3. Content-Type → 推测扩展名
    if content_type:
        ext = _CONTENT_TYPE_TO_EXT.get(content_type.split(";")[0].strip().lower())
        if ext:
            return f"download.{ext}"

    # 4. fallback
    return f"download_{uuid.uuid4().hex[:8]}.bin"


def _download_with_retries(url: str, tmpdir: str) -> tuple[str, bytes]:
    """下载 URL 内容到临时目录，支持指数退避重试。返回 (文件名, 内容)。"""
    last_error: Optional[Exception] = None

    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "pydoctrans/1.0"},
            )
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
                content = resp.read()
                headers = dict(resp.headers.items())
                content_type = resp.headers.get_content_type()
                content_length = resp.headers.get("Content-Length")
                if content_length and len(content) != int(content_length):
                    raise IOError(
                        f"下载不完整：预期 {content_length} 字节，收到 {len(content)} 字节"
                    )
            file_name = _infer_filename(url, headers, content_type)
            logger.info("URL 下载成功: %s → %s (%d bytes, attempt %d/%d)",
                        url, file_name, len(content), attempt, DOWNLOAD_RETRIES)
            return file_name, content
        except Exception as e:
            last_error = e
            if attempt < DOWNLOAD_RETRIES:
                delay = DOWNLOAD_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "URL 下载失败 (attempt %d/%d): %s — %.1fs 后重试",
                    attempt, DOWNLOAD_RETRIES, e, delay,
                )
                time.sleep(delay)

    raise IOError(
        f"URL 下载失败（已重试 {DOWNLOAD_RETRIES} 次）: {url} — {last_error}"
    )

@app.get("/health")
async def health() -> dict:
    """服务健康检查。"""
    engine = _get_engine()
    return engine.health()


@app.get("/engines")
async def list_engines() -> dict:
    """列出所有可用引擎及其状态。"""
    engine = _get_engine()
    return {
        "engines": [
            {
                "name": engine.name,
                "version": engine.health()["version"],
                "status": "available",
            }
        ]
    }


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus 指标端点。"""
    return Response(
        content=generate_latest(),
        media_type="text/plain; charset=utf-8",
    )


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    format: str = Form(default="pdf"),
    from_: str | None = Form(default=None, alias="from"),
    timeout: Optional[int] = Form(default=None),
) -> Response:
    """上传文件并转换为目标格式。

    Args:
        file: 源文件（multipart 上传）。
        format: 目标格式（如 pdf），默认 pdf。
        from_: 源格式（如 docx），未指定则从文件名自动推断。
        timeout: 可选，本次转换的超时秒数。
    """
    # 读取上传文件
    file_data = await file.read()
    file_len = len(file_data)

    # 文件大小检查
    if file_len > MAX_FILE_SIZE:
        requests_total.labels(status="413", format=format).inc()
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制（{MAX_FILE_SIZE} 字节）",
        )

    if not file.filename:
        requests_total.labels(status="400", format=format).inc()
        raise HTTPException(
            status_code=400,
            detail="缺少文件名",
        )

    file_name = _apply_from_format(file.filename, from_)

    engine = _get_engine()

    with _track_request(format=format, file_size=file_len):
        try:
            result = engine.convert(
                data=file_data,
                file_name=file_name,
                format=format,
                timeout=timeout,
            )
        except ValueError as e:
            logger.error("转换参数错误: %s — %s", file.filename, e)
            requests_total.labels(status="400", format=format).inc()
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ConversionError as e:
            logger.error("转换失败: %s → %s — %s", file.filename, format, e)
            requests_total.labels(status="400", format=format).inc()
            raise HTTPException(status_code=400, detail=str(e)) from e
        except TimeoutError as e:
            logger.error("转换超时: %s → %s — %s", file.filename, format, e)
            requests_total.labels(status="504", format=format).inc()
            raise HTTPException(status_code=504, detail=str(e)) from e

    requests_total.labels(status="200", format=format).inc()

    # 构造输出文件名
    stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    output_filename = f"{stem}.{format}"

    return _attachment_response(
        result.data, output_filename, result.engine,
        result.meta.get("elapsed_s", ""),
    )


@app.post("/convert/url")
async def convert_url(
    url: str = Form(...),
    format: str = Form(default="pdf"),
    from_: str | None = Form(default=None, alias="from"),
    timeout: Optional[int] = Form(default=None),
) -> Response:
    """从 URL 下载文件并转换为目标格式。

    Args:
        url: 源文件下载地址。
        format: 目标格式，如 "pdf"、"odt"、"docx"。
        timeout: 可选，本次转换的超时秒数。
    """
    tmpdir = tempfile.mkdtemp(prefix="pydoctrans_url_", dir=TMP_DIR)
    try:
        try:
            file_name, file_data = _download_with_retries(url, tmpdir)
        except IOError as e:
            logger.error("URL 下载最终失败: %s — %s", url, e)
            requests_total.labels(status="502", format=format).inc()
            raise HTTPException(status_code=502, detail=str(e)) from e

        file_name = _apply_from_format(file_name, from_)
        file_len = len(file_data)
        logger.info("URL 转换开始: %s → %s (%d bytes, file=%s)", url, format, file_len, file_name)

        if file_len > MAX_FILE_SIZE:
            requests_total.labels(status="413", format=format).inc()
            raise HTTPException(
                status_code=413,
                detail=f"文件大小超过限制（{MAX_FILE_SIZE} 字节）",
            )

        engine = _get_engine()

        with _track_request(format=format, file_size=file_len):
            try:
                result = engine.convert(
                    data=file_data,
                    file_name=file_name,
                    format=format,
                    timeout=timeout,
                )
            except ValueError as e:
                logger.error("URL 转换参数错误: %s — %s", url, e)
                requests_total.labels(status="400", format=format).inc()
                raise HTTPException(status_code=400, detail=str(e)) from e
            except ConversionError as e:
                logger.error("URL 转换失败: %s → %s — %s", url, format, e)
                requests_total.labels(status="400", format=format).inc()
                raise HTTPException(status_code=400, detail=str(e)) from e
            except TimeoutError as e:
                logger.error("URL 转换超时: %s → %s — %s", url, format, e)
                requests_total.labels(status="504", format=format).inc()
                raise HTTPException(status_code=504, detail=str(e)) from e

        requests_total.labels(status="200", format=format).inc()

        stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
        output_filename = f"{stem}.{format}"

        return _attachment_response(
            result.data, output_filename, result.engine,
            result.meta.get("elapsed_s", ""),
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

