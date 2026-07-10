"""Engine 抽象基类。

所有文档转换引擎必须实现此接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversionResult:
    """转换结果。"""

    data: bytes
    """转换后的文件内容。"""

    engine: str
    """执行转换的引擎名称。"""

    format: str
    """输出格式。"""

    meta: dict[str, Any] = field(default_factory=dict)
    """引擎附加元数据（如 LO 版本、耗时等）。"""


class Engine(ABC):
    """文档转换引擎的抽象基类。

    子类实现::

        class MyEngine(Engine):
            @property
            def name(self) -> str:
                return "my-engine"

            def convert(self, data, file_name, format, timeout=None):
                ...
                return ConversionResult(data=..., engine=self.name, format=format)

            def health(self) -> dict:
                return {"status": "ok"}
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """引擎名称，如 "libreoffice"。"""
        ...

    @abstractmethod
    def convert(
        self,
        data: bytes,
        file_name: str,
        format: str,
        timeout: int | None = None,
    ) -> ConversionResult:
        """将源文件转换为目标格式。

        Args:
            data: 源文件内容。
            file_name: 源文件名（含扩展名，如 "report.docx"）。
            format: 目标格式（如 "pdf"、"odt"）。
            timeout: 单次转换超时秒数。

        Returns:
            ConversionResult 包含转换后的文件数据。

        Raises:
            ConversionError: 转换失败。
            TimeoutError: 转换超时。
        """
        ...

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """返回引擎健康状态信息。"""
        ...
