"""Sandbox 模块：HOME 隔离沙箱。

LibreOffice 通过 HOME 环境变量的 hash 值生成命名管道路径。
不同 HOME → 不同管道 → 多个 LO 进程可真正并行运行。

每次转换创建独立的临时 HOME 目录，转换结束后自动清理。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path
from types import TracebackType
from typing import Optional


def _get_tmp_parent() -> str:
    """获取沙箱父目录，默认 /tmp，可通过 TMP_DIR 环境变量配置。"""
    return os.environ.get("TMP_DIR", "/tmp")


class Sandbox:
    """LO 隔离沙箱。

    用法::

        with Sandbox() as home:
            env["HOME"] = home
            subprocess.run([soffice, ...], env=env)
    """

    def __init__(self) -> None:
        self._path: Optional[Path] = None

    @property
    def home(self) -> str:
        """沙箱 HOME 目录的路径字符串。"""
        if self._path is None:
            raise RuntimeError("Sandbox 未进入上下文")
        return str(self._path)

    def __enter__(self) -> "Sandbox":
        parent = _get_tmp_parent()
        name = f"lo_sandbox_{uuid.uuid4().hex}"
        self._path = Path(tempfile.mkdtemp(prefix=f"{name}_", dir=parent))
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._path is not None and self._path.exists():
            shutil.rmtree(self._path, ignore_errors=True)
