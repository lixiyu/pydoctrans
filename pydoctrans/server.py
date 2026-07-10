"""HTTP API 服务。

FastAPI 应用，提供文档转换的 HTTP 接口。
支持 Prometheus 监控和优雅关闭。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager, contextmanager
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
    version="0.3.0",
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


# ---- Endpoints ----

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
    timeout: Optional[int] = Form(default=None),
) -> Response:
    """上传文件并转换为目标格式。"""
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

    engine = _get_engine()

    with _track_request(format=format, file_size=file_len):
        try:
            result = engine.convert(
                data=file_data,
                file_name=file.filename,
                format=format,
                timeout=timeout,
            )
        except ValueError as e:
            requests_total.labels(status="400", format=format).inc()
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ConversionError as e:
            requests_total.labels(status="400", format=format).inc()
            raise HTTPException(status_code=400, detail=str(e)) from e
        except TimeoutError as e:
            requests_total.labels(status="504", format=format).inc()
            raise HTTPException(status_code=504, detail=str(e)) from e

    requests_total.labels(status="200", format=format).inc()

    # 构造输出文件名
    stem = file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename
    output_filename = f"{stem}.{format}"

    return Response(
        content=result.data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{output_filename}"',
            "X-Engine": result.engine,
            "X-Elapsed": str(result.meta.get("elapsed_s", "")),
        },
    )
