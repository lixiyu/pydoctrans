"""公共转换 API。

用法::

    from pydoctrans import convert
    pdf_bytes = convert(docx_bytes, to="pdf")
"""

from __future__ import annotations

from typing import Sequence

from pydoctrans.engine.libreoffice import ConversionError, LibreOfficeEngine
from pydoctrans.hooks import (
    AfterHook,
    BeforeHook,
    ConversionContext,
    run_after_hooks,
    run_before_hooks,
)

__all__ = ["convert", "ConversionError", "ConversionContext", "BeforeHook", "AfterHook"]


def convert(
    data: bytes,
    to: str,
    *,
    file_name: str = "input.bin",
    timeout: int | None = None,
    before: Sequence[BeforeHook] | None = None,
    after: Sequence[AfterHook] | None = None,
) -> bytes:
    """将文档转换为目标格式。

    Args:
        data: 源文档内容。
        to: 目标格式，如 ``"pdf"``。
        file_name: 源文件名（含扩展名，用于 LO 识别文件类型）。
        timeout: 超时秒数，None 使用默认值（300s）。
        before: 转换前钩子列表。可修改 data/file_name，抛异常可中止转换。
        after: 转换后钩子列表。可修改输出 data、写入 meta。

    Returns:
        bytes: 转换后的文件内容。

    Raises:
        ConversionError: 转换失败（格式不支持、LO 崩溃等）。
        TimeoutError: 转换超时。
        HookExecutionError: after 钩子执行失败。

    Example::

        from pydoctrans import convert

        # 基本用法
        with open("report.docx", "rb") as f:
            pdf_bytes = convert(f.read(), to="pdf", file_name="report.docx")

        # 带钩子
        def log_size(ctx):
            print(f"输出文件大小: {len(ctx.data)} 字节")

        pdf = convert(docx, to="pdf", file_name="r.docx", after=[log_size])
    """
    # 1. Run before hooks
    ctx = ConversionContext(
        data=data,
        file_name=file_name,
        to=to,
        engine="libreoffice",
    )
    run_before_hooks(before, ctx)

    # 2. Convert
    engine = LibreOfficeEngine()
    result = engine.convert(
        data=ctx.data,
        file_name=ctx.file_name,
        to=to,
        timeout=timeout,
    )
    ctx.data = result.data

    # 3. Run after hooks
    run_after_hooks(after, ctx)

    return ctx.data
