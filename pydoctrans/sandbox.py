"""Sandbox 模块：HOME 隔离沙箱。

LibreOffice 通过 HOME 环境变量的 hash 值生成命名管道路径。
不同 HOME → 不同管道 → 多个 LO 进程可真正并行运行。

每次转换创建独立的临时 HOME 目录，转换结束后自动清理。
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from types import TracebackType
from typing import Optional

logger = logging.getLogger(__name__)


def _get_tmp_parent() -> str:
    """获取沙箱父目录，默认 /tmp，可通过 TMP_DIR 环境变量配置。"""
    return os.environ.get("TMP_DIR", "/tmp")


def cleanup_orphan_sandboxes() -> None:
    """清理上次进程崩溃残留的沙箱目录。

    扫描 TMP_DIR/lo_sandbox_*，删除超过 1 小时的孤儿目录。
    """
    parent = _get_tmp_parent()
    pattern = os.path.join(parent, "lo_sandbox_*")
    now = time.time()
    for path in glob.glob(pattern):
        if not os.path.isdir(path):
            continue
        try:
            mtime = os.path.getmtime(path)
            if now - mtime > 3600:  # 1 小时
                shutil.rmtree(path, ignore_errors=True)
                logger.info("清理过期沙箱: %s", path)
        except OSError:
            pass


class Sandbox:
    """LO 隔离沙箱。

    为每个 LO 进程提供独立的运行环境：
    - HOME 指向临时目录 → 独立 ~/.config/libreoffice → 命名管道隔离
    - LD_LIBRARY_PATH 锁定 LO program 目录 → 避免 CUDA/system 库冲突
    - SAL_LOG 启用 LO 内部诊断日志

    用法::

        with Sandbox() as sandbox:
            env = sandbox.get_env()
            subprocess.run([soffice, ...], env=env)
    """

    def __init__(self, lo_program_dir: str | None = None) -> None:
        self._path: Optional[Path] = None
        self._lo_program_dir = lo_program_dir or ""

    @property
    def home(self) -> str:
        """沙箱 HOME 目录的路径字符串。"""
        if self._path is None:
            raise RuntimeError("Sandbox 未进入上下文")
        return str(self._path)

    def get_env(self) -> dict[str, str]:
        """返回沙箱隔离的环境变量。

        - HOME 指向沙箱目录 → LO 创建独立的配置和管道
        - LD_LIBRARY_PATH 仅含 LO program 目录 → 防止加载 CUDA 等冲突库
        - SAL_LOG 启用 LO 内部日志 → 方便诊断
        """
        env = os.environ.copy()
        env["HOME"] = self.home
        if self._lo_program_dir:
            env["LD_LIBRARY_PATH"] = self._lo_program_dir
        env["SAL_LOG"] = "+WARN+INFO"
        return env

    def __enter__(self) -> "Sandbox":
        parent = _get_tmp_parent()
        name = f"lo_sandbox_{uuid.uuid4().hex[:12]}"
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
