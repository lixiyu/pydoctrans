"""HTTP API 服务。

FastAPI 应用，提供文档转换的 HTTP 接口。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response

from pydoctrans.engine.libreoffice import ConversionError, LibreOfficeEngine
from pydoctrans.pool import ConversionPool

logger = logging.getLogger(__name__)

# ---- 全局状态 ----
app = FastAPI(
    title="pydoctrans",
    description="Python Document Transformer — HTTP API",
    version="0.1.0",
)

_engine: Optional[LibreOfficeEngine] = None
_pool: Optional[ConversionPool] = None

MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50MB


def _get_engine() -> LibreOfficeEngine:
    global _engine
    if _engine is None:
        _engine = LibreOfficeEngine()
    return _engine


def _get_pool() -> ConversionPool:
    global _pool
    if _pool is None:
        _pool = ConversionPool()
    return _pool


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
    health_info = engine.health()
    return health_info


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


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    format: str = Form(default="pdf"),
    timeout: Optional[int] = Form(default=None),
) -> Response:
    """上传文件并转换为目标格式。

    Args:
        file: 源文件（multipart 上传）。
        format: 目标格式，如 "pdf"、"odt"、"docx"。
        timeout: 可选，本次转换的超时秒数。

    Returns:
        转换后的文件（Content-Disposition: attachment）。
    """
    # 读取上传文件
    file_data = await file.read()

    # 文件大小检查
    if len(file_data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制（{MAX_FILE_SIZE} 字节）",
        )

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="缺少文件名",
        )

    # 执行转换
    engine = _get_engine()
    try:
        result = engine.convert(
            data=file_data,
            file_name=file.filename,
            format=format,
            timeout=timeout,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ConversionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e)) from e

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
