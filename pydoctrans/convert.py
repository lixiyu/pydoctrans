"""公共转换 API。

用法::

    from pydoctrans import convert
    pdf_bytes = convert(docx_bytes, format="pdf")
"""

from __future__ import annotations

from pydoctrans.engine.libreoffice import ConversionError, LibreOfficeEngine

__all__ = ["convert", "ConversionError"]


def convert(
    data: bytes,
    format: str,
    *,
    file_name: str = "input.bin",
    timeout: int | None = None,
) -> bytes:
    """将文档转换为目标格式。

    Args:
        data: 源文档内容。
        format: 目标格式，如 ``"pdf"``。
        file_name: 源文件名（含扩展名，用于 LO 识别文件类型）。
        timeout: 超时秒数，None 使用默认值（300s）。

    Returns:
        bytes: 转换后的文件内容。

    Raises:
        ConversionError: 转换失败（格式不支持、LO 崩溃等）。
        TimeoutError: 转换超时。

    Example::

        from pydoctrans import convert

        with open("report.docx", "rb") as f:
            pdf_bytes = convert(f.read(), format="pdf", file_name="report.docx")
        with open("report.pdf", "wb") as f:
            f.write(pdf_bytes)
    """
    engine = LibreOfficeEngine()
    result = engine.convert(
        data=data,
        file_name=file_name,
        format=format,
        timeout=timeout,
    )
    return result.data
