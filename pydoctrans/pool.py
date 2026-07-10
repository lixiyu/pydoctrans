"""Pool 模块：Semaphore 并发控制。

每个 LO 进程峰值内存 ~500MB-1GB。通过 Semaphore 限制同时运行的
LO 进程数，防止 OOM。默认并发数为 10，可通过 MAX_CONCURRENT 环境变量调整。
"""

from __future__ import annotations

import os
import threading
from types import TracebackType
from typing import Optional


class ConversionPool:
    """基于 Semaphore 的并发控制池。

    用法::

        pool = ConversionPool()
        with pool.acquire():
            # 在信号量保护下运行 LO
            subprocess.run([soffice, ...])

    默认最大并发数 10，通过环境变量 ``MAX_CONCURRENT`` 调整::

        MAX_CONCURRENT=4 python -m pydoctrans
    """

    def __init__(self, max_concurrent: Optional[int] = None) -> None:
        if max_concurrent is None:
            max_concurrent = int(os.environ.get("MAX_CONCURRENT", "10"))
        if max_concurrent < 1:
            raise ValueError(f"max_concurrent 必须 >= 1，当前值: {max_concurrent}")
        self._semaphore = threading.Semaphore(max_concurrent)
        self.max_concurrent = max_concurrent

    def acquire(self, timeout: Optional[float] = None) -> _Slot:
        """获取一个并发槽位。

        Args:
            timeout: 等待超时秒数，None 表示无限等待。

        Returns:
            _Slot 上下文管理器，退出时自动释放信号量。

        Raises:
            RuntimeError: 在 timeout 秒内未能获取到槽位。
        """
        acquired = self._semaphore.acquire(timeout=timeout)
        if not acquired:
            raise RuntimeError(
                f"未能获取转换槽位（已等待 {timeout}s，"
                f"当前 max_concurrent={self.max_concurrent}）"
            )
        return _Slot(self._semaphore)

    @property
    def available(self) -> int:
        """当前可用槽位数（近似值）。"""
        return self._semaphore._value  # type: ignore[attr-defined]


class _Slot:
    """信号量槽位的上下文管理器。"""

    def __init__(self, semaphore: threading.Semaphore) -> None:
        self._semaphore = semaphore

    def __enter__(self) -> "_Slot":
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self._semaphore.release()
