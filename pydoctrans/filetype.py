"""文件类型自动检测。

通过文件头部魔术字节识别格式，补充文件扩展名缺失或错误的情况。
"""

from __future__ import annotations

import zipfile
from io import BytesIO

# 魔术字节 → 扩展名
_SIGNATURES: list[tuple[bytes, str]] = [
    # OLE2 容器 (.doc, .xls, .ppt)
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "doc"),
    # PDF
    (b"%PDF", "pdf"),
    # RTF
    (b"{\\rtf", "rtf"),
    # PNG
    (b"\x89PNG\r\n\x1a\n", "png"),
    # JPEG
    (b"\xff\xd8\xff", "jpg"),
    # GIF
    (b"GIF8", "gif"),
    # BMP
    (b"BM", "bmp"),
    # TIFF
    (b"\x49\x49\x2a\x00", "tiff"),
    (b"\x4d\x4d\x00\x2a", "tiff"),
]


def _detect_from_zip(data: bytes) -> str | None:
    """检测 ZIP 容器的实际文档类型（docx/xlsx/pptx/odt 等）。

    打开 ZIP，检查内部文件结构：
    - [Content_Types].xml 中包含 /word/ → docx
    - mimetype 文件内容 → odt/ods/odp
    """
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            names = z.namelist()

            # Office Open XML: 检查 [Content_Types].xml
            if "[Content_Types].xml" in names:
                ct = z.read("[Content_Types].xml").decode("utf-8", errors="ignore")
                if "/word/" in ct:
                    return "docx"
                if "/xl/" in ct or "spreadsheet" in ct.lower():
                    return "xlsx"
                if "/ppt/" in ct or "presentation" in ct.lower():
                    return "pptx"

            # OpenDocument: 检查 mimetype 文件
            if "mimetype" in names:
                mime = z.read("mimetype").decode("utf-8", errors="ignore").strip()
                mime_map = {
                    "application/vnd.oasis.opendocument.text": "odt",
                    "application/vnd.oasis.opendocument.spreadsheet": "ods",
                    "application/vnd.oasis.opendocument.presentation": "odp",
                }
                if mime in mime_map:
                    return mime_map[mime]

            return None
    except (zipfile.BadZipFile, OSError):
        return None


def _detect_from_signature(data: bytes) -> str | None:
    """通过文件头部魔术字节匹配。"""
    for magic, ext in _SIGNATURES:
        if data[: len(magic)] == magic:
            return ext
    return None


def detect(data: bytes) -> str | None:
    """从文件内容自动检测文件类型。

    检测顺序：
    1. ZIP 容器（docx/xlsx/pptx/odt/ods/odp）
    2. 魔术字节（PDF/OLE2/RTF/图片）
    3. 未识别返回 None

    Args:
        data: 文件内容（只需要头部数百字节即可）。

    Returns:
        扩展名字符串（如 "docx"、"pdf"），未识别返回 None。
    """
    # ZIP 容器（Office Open XML + OpenDocument）
    result = _detect_from_zip(data)
    if result:
        return result

    # 魔术字节匹配
    return _detect_from_signature(data)
